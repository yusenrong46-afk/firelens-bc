from __future__ import annotations

import unittest

from firelens.request_guard import AnonymousRequestGuard


class RequestGuardTests(unittest.IsolatedAsyncioTestCase):
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
