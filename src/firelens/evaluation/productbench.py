"""Load the 50-journey ProductBench catalog into the product-question probe."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from firelens.evaluation.product_question_cases import (
    LocationExpectation,
    ProductQuestionCase,
)
from firelens.operational_logging import LOGGER_NAME

CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "data/evaluation/productbench_journeys_50.json"
)
_LOCATION: dict[str, LocationExpectation] = {
    "none": "none",
    "inferred": "inferred",
    "required": "required",
}
_ANSWER_MODES = {"live", "grounded", "mixed", "partial", "capability", "background"}


class OperationalToolCapture(logging.Handler):
    def __init__(
        self,
        logger: logging.Logger,
        *,
        previous_level: int,
        previous_propagate: bool,
    ) -> None:
        super().__init__()
        self.by_trace: dict[str, list[str]] = {}
        self._logger = logger
        self._previous_level = previous_level
        self._previous_propagate = previous_propagate
        self._detached = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        trace_id = payload.get("trace_id")
        names = payload.get("tool_names")
        if isinstance(trace_id, str) and isinstance(names, list):
            self.by_trace[trace_id] = [str(name) for name in names]

    def detach(self) -> None:
        """Undo the temporary logger configuration used for an isolated replay."""

        if self._detached:
            return
        self._logger.removeHandler(self)
        self._logger.setLevel(self._previous_level)
        self._logger.propagate = self._previous_propagate
        self._detached = True


def attach_tool_capture() -> tuple[logging.Logger, OperationalToolCapture]:
    logger = logging.getLogger(LOGGER_NAME)
    previous_level = logger.level
    previous_propagate = logger.propagate
    # `log_operation()` emits at INFO while a normal library logger inherits the
    # root WARNING level.  Make the capture self-contained for the replay and
    # restore both settings through `detach()`; no application-wide logging
    # configuration is retained after ProductBench finishes.
    logger.setLevel(logging.INFO)
    logger.propagate = False
    capture = OperationalToolCapture(
        logger,
        previous_level=previous_level,
        previous_propagate=previous_propagate,
    )
    logger.addHandler(capture)
    return logger, capture


def load_productbench_cases() -> list[ProductQuestionCase]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "firelens.productbench_journeys.v1":
        raise ValueError("unexpected ProductBench catalog schema")
    rows = payload.get("cases")
    if not isinstance(rows, list) or len(rows) != 50:
        raise ValueError("ProductBench catalog must contain 50 cases")
    cases: list[ProductQuestionCase] = []
    for row in rows:
        location = _LOCATION[str(row["location_expectation"])]
        kinds = tuple(row.get("live_result_kinds") or ())
        cases.append(
            ProductQuestionCase(
                id=str(row["id"]),
                bucket=str(row["family"]),
                question=str(row["question"]),
                expected_modes=tuple(str(item) for item in row["expected_modes"]),
                location_expectation=location,
                context_fixture=(
                    "first_incident"
                    if row.get("context_fixture") == "first_incident"
                    else "none"
                ),
                history=tuple(row.get("history") or ()),
                notes="; ".join(str(item) for item in row.get("assertions") or ()),
                required_live_kinds=kinds,
                empty_live_results_allowed=bool(row.get("empty_live_results_allowed") or kinds),
                latency_band=row.get("latency_band"),
                safety_disposition=row.get("safety_disposition"),
            )
        )
    return cases


def productbench_result_fields(
    payload: dict[str, Any],
    *,
    tool_names: list[str],
) -> dict[str, Any]:
    results = payload.get("live_results")
    live = results if isinstance(results, list) else []
    return {
        "trace_id": payload.get("trace_id"),
        "visible_answer": payload.get("answer"),
        "live_result_count": len(live),
        "map_relevant_ids": [
            item.get("result_id")
            for item in live
            if isinstance(item, dict) and item.get("result_id")
        ],
        "tool_names": tool_names,
        "safety_disposition": payload.get("reason_code") or payload.get("response_mode"),
    }


def productbench_extra_issues(
    case: ProductQuestionCase,
    payload: dict[str, Any],
    *,
    latency_ms: float,
) -> list[str]:
    issues: list[str] = []
    if case.latency_band == "fast" and latency_ms >= 1_000:
        issues.append(f"latency_band:{latency_ms}")
    wanted = case.safety_disposition
    mode = payload.get("response_mode")
    if wanted == "answer" and mode not in _ANSWER_MODES:
        issues.append(f"safety_disposition:{mode}")
    elif (
        wanted
        and wanted != "answer"
        and mode != wanted
        and payload.get("reason_code") != wanted
    ):
        issues.append(f"safety_disposition:{mode}")
    return issues
