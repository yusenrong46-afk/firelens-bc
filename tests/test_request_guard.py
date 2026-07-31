from __future__ import annotations

import unittest

from starlette.requests import Request

from firelens.request_guard import AnonymousRequestGuard


class RequestGuardTests(unittest.IsolatedAsyncioTestCase):
    def test_untrusted_forwarding_headers_cannot_rotate_identity(self) -> None:
        guard = AnonymousRequestGuard(
            limit=2,
            window_seconds=60,
            max_body_bytes=1024,
            secret=b"test-secret",
        )

        def request(forwarded: str) -> Request:
            return Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/ask",
                    "headers": [(b"x-forwarded-for", forwarded.encode())],
                    "client": ("198.51.100.20", 1234),
                }
            )

        self.assertEqual(
            guard.anonymous_key(request("203.0.113.1")),
            guard.anonymous_key(request("203.0.113.2")),
        )

    def test_vercel_identity_uses_only_the_platform_owned_header(self) -> None:
        guard = AnonymousRequestGuard(
            limit=2,
            window_seconds=60,
            max_body_bytes=1024,
            trusted_proxy_platform="vercel",
            secret=b"test-secret",
        )

        def request(vercel_ip: str, spoofed_xff: str) -> Request:
            return Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/ask",
                    "headers": [
                        (b"x-vercel-forwarded-for", vercel_ip.encode()),
                        (b"x-forwarded-for", spoofed_xff.encode()),
                    ],
                    "client": ("198.51.100.20", 1234),
                }
            )

        first = guard.anonymous_key(request("203.0.113.7", "192.0.2.1"))
        same = guard.anonymous_key(request("203.0.113.7", "192.0.2.2"))
        other = guard.anonymous_key(request("203.0.113.8", "192.0.2.1"))
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)

    async def test_limit_is_bounded_and_resets(self) -> None:
        now = 100.0
        guard = AnonymousRequestGuard(
            limit=2,
            window_seconds=60,
            max_body_bytes=1024,
            clock=lambda: now,
            secret=b"test-secret",
        )
        first = await guard.check("anonymous-a")
        second = await guard.check("anonymous-a")
        denied = await guard.check("anonymous-a")
        self.assertTrue(first.allowed)
        self.assertEqual(second.remaining, 0)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.retry_after_seconds, 60)

        now = 161.0
        reset = await guard.check("anonymous-a")
        self.assertTrue(reset.allowed)
        self.assertEqual(reset.remaining, 1)

    async def test_clients_have_independent_non_raw_keys(self) -> None:
        guard = AnonymousRequestGuard(
            limit=1,
            window_seconds=60,
            max_body_bytes=1024,
            secret=b"test-secret",
        )
        self.assertTrue((await guard.check("hashed-a")).allowed)
        self.assertTrue((await guard.check("hashed-b")).allowed)
        self.assertFalse((await guard.check("hashed-a")).allowed)
