"""Privacy-preserving request bounds for the anonymous public API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


@dataclass
class _Window:
    started_at: float
    count: int


class AnonymousRequestGuard:
    """Bound requests per warm instance without retaining raw client addresses."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        max_body_bytes: int,
        max_clients: int = 10_000,
        trusted_proxy_platform: str = "none",
        clock: Callable[[], float] = time.monotonic,
        secret: bytes | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_body_bytes = max_body_bytes
        self.max_clients = max_clients
        if trusted_proxy_platform not in {"none", "vercel"}:
            raise ValueError("trusted_proxy_platform must be none or vercel")
        self.trusted_proxy_platform = trusted_proxy_platform
        self.clock = clock
        self._secret = secret or os.urandom(32)
        self._windows: dict[str, _Window] = {}
        self._lock = asyncio.Lock()

    def anonymous_key(self, request: Request) -> str:
        peer = request.client.host if request.client is not None else "unknown"
        raw = peer
        if self.trusted_proxy_platform == "vercel":
            forwarded = (
                request.headers.get("x-vercel-forwarded-for", "").split(",", 1)[0].strip()
            )
            try:
                raw = str(ipaddress.ip_address(forwarded))
            except ValueError:
                raw = peer
        return hmac.new(self._secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()

    async def check(self, key: str) -> RateLimitDecision:
        now = self.clock()
        async with self._lock:
            expired = [
                item_key
                for item_key, window in self._windows.items()
                if now - window.started_at >= self.window_seconds
            ]
            for item_key in expired:
                self._windows.pop(item_key, None)

            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= self.max_clients:
                    oldest = min(
                        self._windows,
                        key=lambda item_key: self._windows[item_key].started_at,
                    )
                    self._windows.pop(oldest, None)
                window = _Window(started_at=now, count=0)
                self._windows[key] = window

            elapsed = now - window.started_at
            if elapsed >= self.window_seconds:
                window.started_at = now
                window.count = 0
                elapsed = 0

            if window.count >= self.limit:
                retry_after = max(1, int(self.window_seconds - elapsed + 0.999))
                return RateLimitDecision(False, 0, retry_after)

            window.count += 1
            return RateLimitDecision(True, self.limit - window.count, 0)
