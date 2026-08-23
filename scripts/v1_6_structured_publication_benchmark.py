#!/usr/bin/env python3
"""Deterministic zero-provider benchmark for structured-publication compilation."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Any


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _workload(root: Path) -> tuple[list[Any], list[str], Any]:
    from firelens.answering.typed_records import load_inventory
    from firelens.contracts import (
        AuthorityClass,
        EvidencePacket,
        EvidenceQuoteCandidate,
        EvidenceSpan,
        TemporalClass,
    )
    from firelens.publication.records import get_versioned

    packets: list[Any] = []
    claim_ids: list[str] = []
    for record in load_inventory(str(root)).records:
        if not get_versioned(record.claim_id, root=str(root)).available_for_structured_support:
            continue
        claim_ids.append(record.claim_id)
        evidence_id = f"E-{record.claim_id}"
        packets.append(
            EvidencePacket(
                question="What does the reviewed official guidance say?",
                corpus_version="v1.6-benchmark",
                items=[
                    EvidenceSpan(
                        evidence_id=evidence_id,
                        primary_chunk_ids=list(record.source_span_ids),
                        chunk_ids=list(record.source_span_ids),
                        primary_text=record.source_span_text,
                        context_text=record.source_span_text,
                        source_id="benchmark-source",
                        title="Structured publication benchmark source",
                        publisher=record.authority,
                        canonical_url="https://example.test/official-source",
                        page_number=None,
                        section_title=None,
                        locator=record.source_revision,
                        temporal_class=TemporalClass.STABLE_GUIDANCE,
                        authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                        document_sha256=(
                            getattr(record, "source_document_sha256", None) or "a" * 64
                        ),
                    )
                ],
                quote_candidates=[
                    EvidenceQuoteCandidate(
                        quote_id=f"{evidence_id}Q1",
                        evidence_id=evidence_id,
                        text=record.source_span_text[:500],
                    )
                ],
            )
        )

    order = next(
        record
        for record in load_inventory(str(root)).records
        if record.claim_id == "TC-EVAC-ORDER-001"
    )
    unrelated_text = "On your way out close doors and windows."
    unrelated_packet = EvidencePacket(
        question="What should I do with doors and windows?",
        corpus_version="v1.6-benchmark",
        items=[
            EvidenceSpan(
                evidence_id="E-UNRELATED",
                primary_chunk_ids=list(order.source_span_ids),
                chunk_ids=list(order.source_span_ids),
                primary_text=unrelated_text,
                context_text=unrelated_text,
                source_id="benchmark-source",
                title="Structured publication benchmark source",
                publisher=order.authority,
                canonical_url="https://example.test/official-source",
                page_number=None,
                section_title=None,
                locator=order.source_revision,
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                authority_class=AuthorityClass.PROVINCIAL_GOVERNMENT,
                document_sha256=(getattr(order, "source_document_sha256", None) or "a" * 64),
            )
        ],
        quote_candidates=[
            EvidenceQuoteCandidate(
                quote_id="E-UNRELATEDQ1",
                evidence_id="E-UNRELATED",
                text=unrelated_text,
            )
        ],
    )
    return packets, claim_ids, unrelated_packet


def _run(root: Path, iterations: int) -> dict[str, Any]:
    from firelens.publication import records
    from firelens.publication.compiler import (
        compile_structured_claim,
        select_typed_claim_ids,
    )

    clear_caches = getattr(records, "clear_authority_caches", None)
    if clear_caches is not None:
        clear_caches()
    packets, claim_ids, unrelated_packet = _workload(root)
    for packet in packets:
        select_typed_claim_ids(packet)
    for index, claim_id in enumerate(claim_ids, start=1):
        compile_structured_claim(
            typed_claim_id=claim_id,
            public_claim_id=f"C{index}",
        )

    samples_ms: list[float] = []
    checksum = 0
    for _ in range(iterations):
        started = perf_counter_ns()
        for packet in packets:
            checksum += len(select_typed_claim_ids(packet))
        for index, claim_id in enumerate(claim_ids, start=1):
            compiled = compile_structured_claim(
                typed_claim_id=claim_id,
                public_claim_id=f"C{index}",
            )
            checksum += len(compiled.claim.text)
        samples_ms.append((perf_counter_ns() - started) / 1_000_000)

    unrelated_selection = select_typed_claim_ids(unrelated_packet)
    return {
        "schema_version": "firelens.structured_publication_benchmark.v1",
        "evidence_class": "EXECUTED_OFFLINE",
        "root": str(root.resolve()),
        "iterations": iterations,
        "workload_packet_count": len(packets),
        "workload_claim_ids": claim_ids,
        "provider_calls": 0,
        "timing_ms": {
            "p50": round(_percentile(samples_ms, 0.50), 6),
            "p95": round(_percentile(samples_ms, 0.95), 6),
            "minimum": round(min(samples_ms), 6),
            "maximum": round(max(samples_ms), 6),
        },
        "unrelated_same_chunk_selected": unrelated_selection,
        "checksum": checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 10:
        parser.error("--iterations must be at least 10")
    sys.path.insert(0, str(args.root.resolve() / "src"))
    report = _run(args.root.resolve(), args.iterations)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
