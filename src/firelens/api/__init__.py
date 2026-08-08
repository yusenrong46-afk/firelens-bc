"""Backward-compatible public FastAPI entrypoint."""

from firelens.api.factory import create_app
from firelens.api.responses import ERROR_RESPONSES

__all__ = ["ERROR_RESPONSES", "app", "create_app"]

app = create_app()
