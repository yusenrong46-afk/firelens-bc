"""Capture and independently verify bounded official-live SLO observations."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from firelens.contracts import LiveMapResponse, LiveResultKind, LocationInput
from firelens.live import LAYER_URLS, LiveDataService
from firelens.storage import atomic_text_writer

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "data" / "evaluation" / "live_slo.v1.yaml"
DEFAULT_OUTPUT = ROOT / "output" / "qualification" / "v1_5_2_live_slo.json"
SCHEMA_VERSION = "firelens.live_slo_evidence.v1"
CANONICAL_LAYERS = tuple(LiveResultKind)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError as exc:
        raise ValueError("live SLO protocol must be inside the repository") from exc


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _git_identity() -> tuple[str | None, bool]:
    revision = _git(["rev-parse", "HEAD"])
    commit = revision.stdout.strip() if revision.returncode == 0 else None
    status = _git(["status", "--porcelain=v1", "--untracked-files=all"])
    return commit, status.returncode != 0 or bool(status.stdout.strip())


def _timestamp(value: object, *, context: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} must be a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")
    return parsed


def _number(value: object, *, context: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{context} is outside the allowed range")
    return number


def _signed_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{context} is outside the allowed range")
    return number


def _integer(value: object, *, context: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{context} must be an integer")
    return value


def _exact_keys(payload: object, expected: set[str], *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError(f"{context} does not match the canonical schema")
    return payload


def load_protocol(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    protocol = _exact_keys(
        payload,
        {
            "schema_version",
            "status",
            "qualification_eligible",
            "layers",
            "regions",
            "phases",
            "default_repetitions",
            "max_repetitions",
            "thresholds",
            "limitations",
        },
        context="live SLO protocol",
    )
    if protocol["schema_version"] != "firelens_live_slo_protocol.v1":
        raise ValueError("live SLO protocol version is unsupported")
    if protocol["status"] != "proposed_unratified":
        raise ValueError("live SLO protocol must remain explicitly unratified")
    if protocol["qualification_eligible"] is not False or protocol["thresholds"] is not None:
        raise ValueError("unratified live SLO protocol cannot define qualification thresholds")
    if protocol["layers"] != [kind.value for kind in CANONICAL_LAYERS]:
        raise ValueError("live SLO protocol layer roster is not canonical")
    if protocol["phases"] != ["cold", "cached"]:
        raise ValueError("live SLO protocol phase roster is not canonical")
    _validate_regions(protocol["regions"])
    _validate_protocol_bounds(protocol)
    return protocol


def _validate_regions(regions: object) -> None:
    if not isinstance(regions, list) or len(regions) != 3:
        raise ValueError("live SLO protocol requires exactly three BC regions")
    region_ids: list[str] = []
    for index, raw_region in enumerate(regions):
        region = _exact_keys(
            raw_region,
            {"id", "latitude", "longitude", "radius_km"},
            context=f"live SLO region {index}",
        )
        region_id = region["id"]
        if not isinstance(region_id, str) or not region_id.replace("_", "").isalnum():
            raise ValueError("live SLO region ID is invalid")
        region_ids.append(region_id)
        latitude = _signed_number(region["latitude"], context=f"{region_id} latitude")
        longitude = _signed_number(region["longitude"], context=f"{region_id} longitude")
        radius = _number(region["radius_km"], context=f"{region_id} radius", minimum=1)
        if not 48 <= latitude <= 61 or not -140 <= longitude <= -113 or radius > 200:
            raise ValueError("live SLO region is outside the bounded BC scope")
    if len(region_ids) != len(set(region_ids)):
        raise ValueError("live SLO region IDs must be unique")


def _validate_protocol_bounds(protocol: dict[str, Any]) -> None:
    default_repetitions = _integer(
        protocol["default_repetitions"], context="default repetitions", minimum=1
    )
    maximum = _integer(protocol["max_repetitions"], context="max repetitions", minimum=1)
    if default_repetitions > maximum or maximum > 10:
        raise ValueError("live SLO repetition bounds are invalid")
    limitations = protocol["limitations"]
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(item, str) or not item.strip() for item in limitations)
    ):
        raise ValueError("live SLO protocol limitations are incomplete")


def _nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def _layer_observations(response: LiveMapResponse) -> list[dict[str, Any]]:
    return [
        {
            "kind": status.kind.value,
            "source_url": str(status.source_url),
            "available": status.available,
            "source_updated_at": (
                status.source_updated_at.isoformat()
                if status.source_updated_at is not None
                else None
            ),
            "retrieved_at": (
                status.retrieved_at.isoformat() if status.retrieved_at is not None else None
            ),
            "freshness": status.freshness.value if status.freshness is not None else None,
            "matching_result_count": status.matching_result_count,
        }
        for status in response.layer_statuses
    ]


async def _observe(
    service: Any,
    *,
    target_id: str,
    target_type: str,
    repetition: int,
    phase: str,
    layers: tuple[LiveResultKind, ...],
    location: LocationInput | None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    try:
        if location is None:
            response = await service.map_results(layers=layers)
        else:
            response = await service.nearby_results(location, layers=layers)
        latency_ms = (time.perf_counter() - started) * 1_000
        completed_at = datetime.now(UTC)
        layer_observations = _layer_observations(response)
        unavailable = [kind.value for kind in response.unavailable_layers]
        return {
            "target_id": target_id,
            "target_type": target_type,
            "repetition": repetition,
            "phase": phase,
            "requested_layers": [kind.value for kind in layers],
            "location": location.model_dump(mode="json") if location is not None else None,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "latency_ms": latency_ms,
            "status": "available" if not unavailable else "partial_or_unavailable",
            "error_kind": None,
            "result_count": len(response.results),
            "unavailable_layers": unavailable,
            "aggregate_freshness": (
                response.aggregate_freshness.value
                if response.aggregate_freshness is not None
                else "unavailable"
            ),
            "layer_observations": layer_observations,
        }
    except asyncio.CancelledError:
        raise
    except Exception:  # capture continues, but never records private exception details
        return {
            "target_id": target_id,
            "target_type": target_type,
            "repetition": repetition,
            "phase": phase,
            "requested_layers": [kind.value for kind in layers],
            "location": location.model_dump(mode="json") if location is not None else None,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "status": "error",
            "error_kind": "unexpected",
            "result_count": 0,
            "unavailable_layers": [kind.value for kind in layers],
            "aggregate_freshness": "unavailable",
            "layer_observations": [],
        }


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    keys = sorted({(str(row["target_id"]), str(row["phase"])) for row in rows})
    for target_id, phase in keys:
        group_rows = [
            row for row in rows if row["target_id"] == target_id and row["phase"] == phase
        ]
        latencies = [float(row["latency_ms"]) for row in group_rows]
        source_ages: list[float] = []
        freshness_observation_count = 0
        stale_layer_observation_count = 0
        for row in group_rows:
            completed_at = _timestamp(row["completed_at"], context="row completed_at")
            for observation in row["layer_observations"]:
                if not observation["available"]:
                    continue
                freshness_observation_count += 1
                if observation["freshness"] == "stale":
                    stale_layer_observation_count += 1
                updated_at = _timestamp(
                    observation["source_updated_at"], context="source_updated_at"
                )
                source_ages.append((completed_at - updated_at).total_seconds() / 60)
        summaries.append(
            {
                "target_id": target_id,
                "phase": phase,
                "sample_count": len(group_rows),
                "available_sample_count": sum(
                    row["status"] == "available" for row in group_rows
                ),
                "availability_rate": (
                    sum(row["status"] == "available" for row in group_rows) / len(group_rows)
                ),
                "latency_p50_ms": _nearest_rank(latencies, 0.50),
                "latency_p95_ms": _nearest_rank(latencies, 0.95),
                "freshness_observation_count": freshness_observation_count,
                "stale_layer_observation_count": stale_layer_observation_count,
                "min_source_age_minutes": min(source_ages) if source_ages else None,
                "max_source_age_minutes": max(source_ages) if source_ages else None,
            }
        )
    return summaries


async def capture(
    *,
    protocol_path: Path,
    repetitions: int,
    service_factory: Callable[[], Any] = LiveDataService,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    maximum = int(protocol["max_repetitions"])
    if not 1 <= repetitions <= maximum:
        raise ValueError(f"repetitions must be between 1 and {maximum}")
    commit, worktree_dirty = _git_identity()
    rows: list[dict[str, Any]] = []
    for repetition in range(1, repetitions + 1):
        service = service_factory()
        try:
            targets: list[tuple[str, str, tuple[LiveResultKind, ...], LocationInput | None]] = [
                (f"layer:{kind.value}", "layer", (kind,), None) for kind in CANONICAL_LAYERS
            ]
            targets.extend(
                (
                    f"region:{region['id']}",
                    "region",
                    CANONICAL_LAYERS,
                    LocationInput(
                        latitude=region["latitude"],
                        longitude=region["longitude"],
                        radius_km=region["radius_km"],
                    ),
                )
                for region in protocol["regions"]
            )
            for target_id, target_type, layers, location in targets:
                for phase in ("cold", "cached"):
                    rows.append(
                        await _observe(
                            service,
                            target_id=target_id,
                            target_type=target_type,
                            repetition=repetition,
                            phase=phase,
                            layers=layers,
                            location=location,
                        )
                    )
        finally:
            await service.aclose()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": commit,
        "worktree_dirty": worktree_dirty,
        "protocol_path": _repository_path(protocol_path),
        "protocol_sha256": _sha256(protocol_path),
        "harness_sha256": _sha256(Path(__file__).resolve()),
        "source_urls": {kind.value: LAYER_URLS[kind] for kind in CANONICAL_LAYERS},
        "repetitions": repetitions,
        "row_count": len(rows),
        "rows": rows,
        "summaries": _summaries(rows),
        "thresholds": None,
        "qualification_eligible": False,
        "status": "diagnostic_only",
        "limitations": list(protocol["limitations"]),
    }


def verify(report: dict[str, Any], *, protocol_path: Path) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    payload = _exact_keys(
        report,
        {
            "schema_version",
            "generated_at",
            "commit",
            "worktree_dirty",
            "protocol_path",
            "protocol_sha256",
            "harness_sha256",
            "source_urls",
            "repetitions",
            "row_count",
            "rows",
            "summaries",
            "thresholds",
            "qualification_eligible",
            "status",
            "limitations",
        },
        context="live SLO evidence",
    )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("live SLO evidence version is unsupported")
    _timestamp(payload["generated_at"], context="live SLO generated_at")
    commit = payload["commit"]
    if commit is not None and (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("live SLO commit identity is invalid")
    if type(payload["worktree_dirty"]) is not bool:
        raise ValueError("live SLO worktree state must be a strict boolean")
    if payload["protocol_sha256"] != _sha256(protocol_path):
        raise ValueError("live SLO evidence does not match the protocol")
    if payload["protocol_path"] != _repository_path(protocol_path):
        raise ValueError("live SLO evidence protocol path is not canonical")
    if payload["harness_sha256"] != _sha256(Path(__file__).resolve()):
        raise ValueError("live SLO evidence does not match the current harness")
    if payload["thresholds"] is not None or payload["qualification_eligible"] is not False:
        raise ValueError("unratified live SLO evidence cannot qualify")
    if payload["status"] != "diagnostic_only":
        raise ValueError("live SLO evidence status is invalid")
    if payload["limitations"] != protocol["limitations"]:
        raise ValueError("live SLO evidence limitations differ from the protocol")
    if payload["source_urls"] != {kind.value: LAYER_URLS[kind] for kind in CANONICAL_LAYERS}:
        raise ValueError("live SLO evidence source identities differ from the protocol")
    repetitions = _integer(payload["repetitions"], context="repetitions", minimum=1)
    if repetitions > int(protocol["max_repetitions"]):
        raise ValueError("live SLO repetitions exceed the protocol")
    rows = payload["rows"]
    if not isinstance(rows, list):
        raise ValueError("live SLO rows must be a list")
    expected_targets = [f"layer:{kind.value}" for kind in CANONICAL_LAYERS] + [
        f"region:{region['id']}" for region in protocol["regions"]
    ]
    expected_roster = [
        (repetition, target, phase)
        for repetition in range(1, repetitions + 1)
        for target in expected_targets
        for phase in ("cold", "cached")
    ]
    observed_roster: list[tuple[int, str, str]] = []
    row_keys = {
        "target_id",
        "target_type",
        "repetition",
        "phase",
        "requested_layers",
        "location",
        "started_at",
        "completed_at",
        "latency_ms",
        "status",
        "error_kind",
        "result_count",
        "unavailable_layers",
        "aggregate_freshness",
        "layer_observations",
    }
    for index, raw_row in enumerate(rows):
        row = _exact_keys(raw_row, row_keys, context=f"live SLO row {index}")
        repetition = _integer(row["repetition"], context="row repetition", minimum=1)
        target_id = row["target_id"]
        phase = row["phase"]
        if not isinstance(target_id, str) or phase not in {"cold", "cached"}:
            raise ValueError("live SLO row target or phase is invalid")
        observed_roster.append((repetition, target_id, phase))
        if target_id.startswith("layer:"):
            expected_layer = target_id.removeprefix("layer:")
            if (
                row["target_type"] != "layer"
                or row["requested_layers"] != [expected_layer]
                or row["location"] is not None
            ):
                raise ValueError("live SLO layer row differs from its target")
        else:
            region_id = target_id.removeprefix("region:")
            region = next(
                (item for item in protocol["regions"] if item["id"] == region_id), None
            )
            expected_location = (
                {
                    "label": None,
                    "latitude": region["latitude"],
                    "longitude": region["longitude"],
                    "radius_km": region["radius_km"],
                }
                if region is not None
                else None
            )
            if (
                row["target_type"] != "region"
                or row["requested_layers"] != protocol["layers"]
                or row["location"] != expected_location
            ):
                raise ValueError("live SLO region row differs from its target")
        started_at = _timestamp(row["started_at"], context="row started_at")
        completed_at = _timestamp(row["completed_at"], context="row completed_at")
        if completed_at < started_at:
            raise ValueError("live SLO row timestamps are reversed")
        _number(row["latency_ms"], context="row latency")
        result_count = _integer(row["result_count"], context="row result count")
        unavailable = row["unavailable_layers"]
        if (
            not isinstance(unavailable, list)
            or len(unavailable) != len(set(unavailable))
            or any(layer not in row["requested_layers"] for layer in unavailable)
        ):
            raise ValueError("live SLO unavailable-layer evidence is invalid")
        status = row["status"]
        if status not in {"available", "partial_or_unavailable", "error"}:
            raise ValueError("live SLO row status is invalid")
        error_kind = row["error_kind"]
        valid_status = bool(
            (status == "available" and not unavailable and error_kind is None)
            or (status == "partial_or_unavailable" and bool(unavailable) and error_kind is None)
            or (
                status == "error"
                and error_kind == "unexpected"
                and unavailable == row["requested_layers"]
                and result_count == 0
            )
        )
        if not valid_status:
            raise ValueError("live SLO row status differs from its raw failure evidence")
        layer_observations = row["layer_observations"]
        if not isinstance(layer_observations, list):
            raise ValueError("live SLO layer observations must be a list")
        observed_layers: list[str] = []
        observed_result_count = 0
        for observation_index, raw_observation in enumerate(layer_observations):
            observation = _exact_keys(
                raw_observation,
                {
                    "kind",
                    "source_url",
                    "available",
                    "source_updated_at",
                    "retrieved_at",
                    "freshness",
                    "matching_result_count",
                },
                context=f"live SLO row {index} observation {observation_index}",
            )
            kind = observation["kind"]
            if not isinstance(kind, str) or kind not in row["requested_layers"]:
                raise ValueError("live SLO layer observation identity is invalid")
            observed_layers.append(kind)
            if observation["source_url"] != payload["source_urls"][kind]:
                raise ValueError("live SLO layer observation source URL is invalid")
            if type(observation["available"]) is not bool:
                raise ValueError("live SLO layer observation availability is invalid")
            matching_count = _integer(
                observation["matching_result_count"],
                context="layer matching result count",
            )
            observed_result_count += matching_count
            if observation["available"]:
                _timestamp(
                    observation["source_updated_at"],
                    context="layer source_updated_at",
                )
                _timestamp(observation["retrieved_at"], context="layer retrieved_at")
                if observation["freshness"] not in {"fresh", "stale"}:
                    raise ValueError("live SLO layer freshness is invalid")
            elif (
                any(
                    observation[field] is not None
                    for field in ("source_updated_at", "retrieved_at", "freshness")
                )
                or matching_count
            ):
                raise ValueError("unavailable live SLO layers cannot claim observations")
        if observed_layers and observed_layers != row["requested_layers"]:
            raise ValueError("live SLO layer observation roster differs from the request")
        if status != "error" and not observed_layers:
            raise ValueError("live SLO non-error rows require layer observations")
        if observed_result_count != result_count:
            raise ValueError("live SLO result count differs from its layer observations")
        observed_unavailable = [
            observation["kind"]
            for observation in layer_observations
            if not observation["available"]
        ]
        if status != "error" and observed_unavailable != unavailable:
            raise ValueError("live SLO unavailable layers differ from layer observations")
        observed_freshness = {
            str(observation["freshness"])
            for observation in layer_observations
            if observation["available"] and observation["matching_result_count"]
        }
        expected_aggregate = (
            "unavailable"
            if not observed_freshness
            else next(iter(observed_freshness))
            if len(observed_freshness) == 1
            else "mixed"
        )
        if row["aggregate_freshness"] != expected_aggregate:
            raise ValueError("live SLO aggregate freshness differs from its layer observations")
    if observed_roster != expected_roster:
        raise ValueError("live SLO observation roster differs from the protocol")
    if _integer(payload["row_count"], context="row count") != len(rows):
        raise ValueError("live SLO row count differs from its raw rows")
    recomputed = _summaries(rows)
    if payload["summaries"] != recomputed:
        raise ValueError("live SLO summaries differ from the raw observations")
    return {
        "verified": True,
        "qualification_eligible": False,
        "worktree_dirty": payload["worktree_dirty"],
        "row_count": len(rows),
        "summary_count": len(recomputed),
    }


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_text_writer(path) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    capture_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    capture_parser.add_argument("--repetitions", type=int)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    verify_parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture":
        protocol = load_protocol(args.protocol)
        repetitions = args.repetitions or int(protocol["default_repetitions"])
        report = asyncio.run(capture(protocol_path=args.protocol, repetitions=repetitions))
        verify(report, protocol_path=args.protocol)
        _write_new(args.output, report)
        print(json.dumps({"status": "captured_diagnostic", "output": str(args.output)}))
        return
    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(verify(report, protocol_path=args.protocol), indent=2))


if __name__ == "__main__":
    main()
