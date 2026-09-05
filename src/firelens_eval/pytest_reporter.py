"""Minimal pytest event adapter; no product decisions live here."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

import pytest

_rows: dict[str, list[dict[str, Any]]] = {}
_collected: list[str] = []


def pytest_collection_finish(session: Any) -> None:
    _collected.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report: Any) -> None:
    _rows.setdefault(report.nodeid, []).append(
        {
            "phase": report.when,
            "outcome": report.outcome,
            "duration_s": report.duration,
            "detail": str(report.longrepr) if report.failed else None,
        }
    )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    del session
    target = os.environ.get("FIRELENS_LOCAL_REPORT")
    if target:
        Path(target).write_text(
            json.dumps(
                {"collected": _collected, "events": _rows, "exit_code": int(exitstatus)},
                indent=2,
            )
        )


@pytest.fixture(autouse=True)
def deny_external_sockets(monkeypatch: Any) -> None:
    original = socket.socket.connect

    def connect(instance: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("External network is forbidden in local diagnostic adapters")
        return original(instance, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
