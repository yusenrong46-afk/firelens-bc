"""HTTP response helpers for official live adapters."""

from __future__ import annotations

from typing import Any

import httpx

_WIRE_BODY_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})
_TRUE_FLAGS = frozenset({"y", "yes", "true", "1"})


def official_flag(value: Any) -> bool:
    return str(value or "").strip().casefold() in _TRUE_FLAGS


def decoded_response_headers(headers: httpx.Headers) -> httpx.Headers:
    """Keep metadata headers, not encodings that applied to the wire bytes.

    ``aiter_bytes()`` already decompresses gzip. Rebuilding a response with the
    original ``Content-Encoding`` makes httpx decode the JSON a second time and
    fail closed as an unavailable live layer.
    """

    return httpx.Headers(
        [
            (name, value)
            for name, value in headers.multi_items()
            if name.lower() not in _WIRE_BODY_HEADERS
        ]
    )
