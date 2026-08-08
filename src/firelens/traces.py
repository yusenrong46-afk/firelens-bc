"""Small local JSON traces with secrets and raw content excluded by default."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TraceRecorder:
    def __init__(
        self,
        directory: Path,
        *,
        include_content: bool = False,
        include_question_fingerprint: bool = True,
        max_files: int = 250,
        max_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.directory = directory
        self.include_content = include_content
        self.include_question_fingerprint = include_question_fingerprint
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    async def record(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> bool:
        try:
            await asyncio.to_thread(
                self._record_sync,
                trace_id,
                question=question,
                payload=payload,
            )
        except OSError:
            return False
        return True

    def _record_sync(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            self._record_locked(trace_id, question=question, payload=payload)

    def _record_locked(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{trace_id}.json"
        now = datetime.now(UTC).isoformat()
        trace: dict[str, Any] = {
            "trace_version": "firelens_trace.v2",
            "trace_id": trace_id,
            "created_at": now,
            "updated_at": now,
            "events": [],
        }
        if self.include_question_fingerprint:
            import hashlib

            trace["question_sha256"] = hashlib.sha256(question.encode("utf-8")).hexdigest()
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
        serialized = json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            prefix=f".{trace_id}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        self._enforce_retention(exclude=path)

    def _enforce_retention(self, *, exclude: Path) -> None:
        traces = sorted(
            (
                item
                for item in self.directory.glob("*.json")
                if item.is_file() and item != exclude
            ),
            key=lambda item: item.stat().st_mtime,
        )
        total_bytes = exclude.stat().st_size + sum(item.stat().st_size for item in traces)
        while traces and (len(traces) + 1 > self.max_files or total_bytes > self.max_bytes):
            oldest = traces.pop(0)
            total_bytes -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
