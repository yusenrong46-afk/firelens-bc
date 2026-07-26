"""Small local JSON traces with secrets and raw content excluded by default."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceRecorder:
    def __init__(self, directory: Path, *, include_content: bool = False) -> None:
        self.directory = directory
        self.include_content = include_content

    def record(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{trace_id}.json"
        now = datetime.now(timezone.utc).isoformat()
        trace = {
            "trace_version": "firelens_trace.v2",
            "trace_id": trace_id,
            "created_at": now,
            "updated_at": now,
            "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
            "events": [],
        }
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if (
                    isinstance(existing, dict)
                    and existing.get("trace_id") == trace_id
                    and isinstance(existing.get("events"), list)
                ):
                    trace = existing
                    trace["updated_at"] = now
            except (json.JSONDecodeError, OSError):
                pass
        if self.include_content:
            trace["question"] = question
        trace["events"].append(payload)
        path.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
