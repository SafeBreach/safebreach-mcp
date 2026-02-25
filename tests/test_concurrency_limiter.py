"""
Tests for the per-agent concurrency limiter in SafeBreachMCPBase.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock

from safebreach_mcp_core.safebreach_base import (
    SafeBreachMCPBase,
    _session_semaphores,
    _mcp_session_id,
    _concurrency_limit,
    _cleanup_stale_semaphores,
    _SEMAPHORE_MAX_AGE,
)


@pytest.fixture(autouse=True)
def cleanup_session_state():
    """Clean up module-level session state between tests."""
    _session_semaphores.clear()
    token = _mcp_session_id.set(None)
    yield
    _session_semaphores.clear()
    _mcp_session_id.reset(token)


def make_scope(path="/messages/", scope_type="http", query_string=b""):
    """Create a minimal ASGI scope for testing."""
    return {
        "type": scope_type,
        "path": path,
        "method": "POST",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "query_string": query_string,
    }


def _make_app():
    """Create a concurrency-limited app wrapping a passthrough."""
    base = SafeBreachMCPBase("test-server")
    original_app = AsyncMock()
    return base._create_concurrency_limited_app(original_app), original_app


class TestConcurrencyLimiter:
    """Tests for _create_concurrency_limited_app."""

    def test_non_http_passes_through(self):
        """Non-HTTP scopes (websocket, lifespan) pass through without limiting."""
        async def run():
            app, original = _make_app()
            scope = make_scope(scope_type="websocket")
            await app(scope, AsyncMock(), AsyncMock())
            original.assert_awaited_once()
        asyncio.run(run())

    def test_sse_creates_session(self):
        """SSE endpoint creates a new session ID and semaphore."""
        async def run():
            app, original = _make_app()
            scope = make_scope(path="/sse")
            await app(scope, AsyncMock(), AsyncMock())
            assert len(_session_semaphores) == 1
            session_id = list(_session_semaphores.keys())[0]
            assert len(session_id) > 0
            original.assert_awaited_once()
        asyncio.run(run())

    def test_message_under_limit_passes_through(self):
        """Message requests within concurrency limit pass through."""
        async def run():
            app, original = _make_app()
            # Establish a session via SSE
            sse_scope = make_scope(path="/sse")
            await app(sse_scope, AsyncMock(), AsyncMock())
            session_id = list(_session_semaphores.keys())[0]
            _mcp_session_id.set(session_id)
            # Send a message — should pass through
            msg_scope = make_scope(path="/messages/")
            await app(msg_scope, AsyncMock(), AsyncMock())
            assert original.await_count == 2  # SSE + message
        asyncio.run(run())

    def test_message_over_limit_returns_429(self):
        """Requests exceeding the concurrency limit get HTTP 429."""
        async def run():
            app, _ = _make_app()
            # Create a session with limit=1
            session_id = "test-session-429"
            sem = asyncio.Semaphore(1)
            _session_semaphores[session_id] = (sem, time.time())
            _mcp_session_id.set(session_id)
            # Exhaust the semaphore
            await sem.acquire()
            # Second request should get 429
            msg_scope = make_scope(path="/messages/")
            send = AsyncMock()
            await app(msg_scope, AsyncMock(), send)
            assert send.await_count == 2
            start_call = send.call_args_list[0][0][0]
            assert start_call["status"] == 429
            headers_dict = dict(start_call["headers"])
            assert headers_dict[b"retry-after"] == b"5"
            body_call = send.call_args_list[1][0][0]
            body_json = json.loads(body_call["body"])
            assert body_json["error"] == "Too Many Requests"
            sem.release()
        asyncio.run(run())

    def test_different_sessions_independent_limits(self):
        """Different sessions have independent semaphores."""
        async def run():
            app, original = _make_app()
            session_a = "session-a"
            session_b = "session-b"
            sem_a = asyncio.Semaphore(1)
            sem_b = asyncio.Semaphore(1)
            _session_semaphores[session_a] = (sem_a, time.time())
            _session_semaphores[session_b] = (sem_b, time.time())
            # Exhaust session A
            await sem_a.acquire()
            # Session B should still work
            _mcp_session_id.set(session_b)
            msg_scope = make_scope(path="/messages/")
            await app(msg_scope, AsyncMock(), AsyncMock())
            original.assert_awaited_once()
            sem_a.release()
        asyncio.run(run())

    def test_no_session_passes_through(self):
        """Message requests without a session ID pass through (fallback)."""
        async def run():
            app, original = _make_app()
            _mcp_session_id.set(None)
            msg_scope = make_scope(path="/messages/")
            await app(msg_scope, AsyncMock(), AsyncMock())
            original.assert_awaited_once()
        asyncio.run(run())

    def test_non_sse_non_message_passes_through(self):
        """Paths other than /sse and /messages/ pass through without limiting."""
        async def run():
            app, original = _make_app()
            scope = make_scope(path="/api/some/other/endpoint")
            await app(scope, AsyncMock(), AsyncMock())
            original.assert_awaited_once()
        asyncio.run(run())

    def test_sse_cleanup_on_end(self):
        """Session semaphore is cleaned up when SSE connection ends."""
        async def run():
            async def fake_sse_app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"done", "more_body": False})

            base = SafeBreachMCPBase("test-server")
            app = base._create_concurrency_limited_app(fake_sse_app)
            sse_scope = make_scope(path="/sse")
            send = AsyncMock()
            await app(sse_scope, AsyncMock(), send)
            # Semaphore should be cleaned up after end-of-body
            assert len(_session_semaphores) == 0
        asyncio.run(run())

    def test_env_var_default(self):
        """Default concurrency limit is 2."""
        assert _concurrency_limit == 2

    def test_retry_after_header_in_429(self):
        """HTTP 429 response includes Retry-After header."""
        async def run():
            app, _ = _make_app()
            session_id = "test-retry"
            sem = asyncio.Semaphore(1)
            _session_semaphores[session_id] = (sem, time.time())
            _mcp_session_id.set(session_id)
            await sem.acquire()
            send = AsyncMock()
            await app(make_scope(path="/messages/"), AsyncMock(), send)
            start_call = send.call_args_list[0][0][0]
            headers_dict = dict(start_call["headers"])
            assert b"retry-after" in headers_dict
            assert headers_dict[b"retry-after"] == b"5"
            sem.release()
        asyncio.run(run())

    def test_sse_stores_semaphore_as_tuple(self):
        """SSE endpoint stores (Semaphore, timestamp) tuple."""
        async def run():
            app, _ = _make_app()
            scope = make_scope(path="/sse")
            await app(scope, AsyncMock(), AsyncMock())
            assert len(_session_semaphores) == 1
            session_id = list(_session_semaphores.keys())[0]
            entry = _session_semaphores[session_id]
            assert isinstance(entry, tuple)
            assert len(entry) == 2
            sem, created_at = entry
            assert isinstance(sem, asyncio.Semaphore)
            assert isinstance(created_at, float)
            assert created_at <= time.time()
        asyncio.run(run())


class TestConcurrencyLimiterSAF28585:
    """SAF-28585: Reproduce the concurrency limiter bypass.

    In production, uvicorn handles SSE GET and POST /messages/ as separate async tasks.
    ContextVar set in the SSE task is invisible in the POST task, so the limiter
    never finds a session_id and every request falls through unthrottled.

    These tests run SSE and POST in separate asyncio.create_task() calls to simulate
    the real uvicorn behavior.  They assert the CORRECT (fixed) behavior, so they
    FAIL on the current buggy code (TDD red).
    """

    def test_contextvar_not_propagated_between_tasks(self):
        """ContextVar set in SSE task is invisible in a separate POST task."""
        async def run():
            app, _ = _make_app()

            # SSE runs in its own task (like uvicorn handles it)
            async def sse_handler():
                await app(make_scope(path="/sse"), AsyncMock(), AsyncMock())
                # ContextVar is set inside this task by the middleware
                return _mcp_session_id.get()

            sse_task = asyncio.create_task(sse_handler())
            sse_session_id = await sse_task

            # ContextVar was set in the SSE task
            assert sse_session_id is not None

            # POST runs in a different task — ContextVar should be None
            async def post_handler():
                return _mcp_session_id.get()

            post_task = asyncio.create_task(post_handler())
            post_session_id = await post_task

            # Root cause of SAF-28585: ContextVar does NOT propagate
            assert post_session_id is None, (
                "ContextVar should be None in separate task (proving the root cause)"
            )
        asyncio.run(run())

    def test_separate_task_post_bypasses_exhausted_semaphore(self):
        """POST in a separate task passes through even when the semaphore is exhausted.

        This documents the current buggy behavior: the middleware falls through to
        the passthrough path because _mcp_session_id.get() returns None.
        """
        async def run():
            app, original = _make_app()

            # SSE creates the session in its own task
            async def sse_handler():
                await app(make_scope(path="/sse"), AsyncMock(), AsyncMock())

            await asyncio.create_task(sse_handler())
            assert len(_session_semaphores) == 1
            session_id = list(_session_semaphores.keys())[0]

            # Exhaust the semaphore — next request SHOULD get 429
            sem, _ = _session_semaphores[session_id]
            await sem.acquire()

            # POST in a separate task (like a real uvicorn request)
            send = AsyncMock()

            async def post_handler():
                await app(make_scope(path="/messages/"), AsyncMock(), send)

            await asyncio.create_task(post_handler())

            # BUG: request passed through to original_app instead of getting 429
            # The middleware fell through because _mcp_session_id.get() returned None
            original.assert_awaited()  # called for both SSE and POST
            # send was NOT called with 429 — it was never used by the middleware
            assert send.await_count == 0, (
                "send should not be called because middleware fell through (bug)"
            )

            sem.release()
        asyncio.run(run())

    def test_query_string_session_id_should_produce_429(self):
        """POST with session_id in query string should get 429 when semaphore is exhausted.

        The fix should parse session_id from the query string instead of ContextVar.
        This test FAILS on the current code (TDD red) and will PASS after the fix.
        """
        async def run():
            app, _ = _make_app()

            # Manually register a session with an exhausted semaphore
            session_id = "test-qs-session"
            sem = asyncio.Semaphore(1)
            _session_semaphores[session_id] = (sem, time.time())
            await sem.acquire()

            # POST with session_id in query string (as FastMCP clients actually send)
            send = AsyncMock()
            msg_scope = make_scope(
                path="/messages/",
                query_string=f"session_id={session_id}".encode(),
            )
            await app(msg_scope, AsyncMock(), send)

            # Expected after fix: middleware parses query string → finds exhausted sem → 429
            assert send.await_count == 2, (
                "Expected 429 response (start + body), but middleware did not send it"
            )
            start_msg = send.call_args_list[0][0][0]
            assert start_msg["status"] == 429, (
                f"Expected HTTP 429, got {start_msg.get('status')}"
            )

            sem.release()
        asyncio.run(run())

    def test_query_string_session_id_under_limit_acquires_semaphore(self):
        """POST with session_id in query string, under limit, should acquire the semaphore.

        This test FAILS on the current code (TDD red) because the middleware
        doesn't parse query_string and falls through to the passthrough path
        WITHOUT acquiring the semaphore.
        """
        async def run():
            app, original = _make_app()

            # Register a session — track whether the semaphore is actually acquired
            session_id = "test-qs-under-limit"
            acquired = []

            class TrackingSemaphore(asyncio.Semaphore):
                async def __aenter__(self):
                    acquired.append(True)
                    return await super().__aenter__()

            sem = TrackingSemaphore(_concurrency_limit)
            _session_semaphores[session_id] = (sem, time.time())

            # POST with session_id in query string
            msg_scope = make_scope(
                path="/messages/",
                query_string=f"session_id={session_id}".encode(),
            )
            await app(msg_scope, AsyncMock(), AsyncMock())

            # Expected after fix: semaphore was acquired during processing
            assert len(acquired) == 1, (
                f"Semaphore should have been acquired once, was acquired {len(acquired)} times"
            )
            original.assert_awaited_once()
        asyncio.run(run())

    def test_sse_migration_cleanup_no_leak(self):
        """SSE session_id migration cleans up properly — no semaphore leak.

        When the SSE response contains the real FastMCP session_id, the middleware
        migrates the semaphore from the middleware key to the real key. On SSE
        disconnect, the migrated key (not the stale middleware key) must be removed.
        """
        async def run():
            real_session_id = "abc123def456"

            async def fake_sse_app(scope, receive, send):
                # Simulate FastMCP sending the endpoint event with session_id
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({
                    "type": "http.response.body",
                    "body": f"event: endpoint\ndata: /messages/?session_id={real_session_id}\n\n".encode(),
                    "more_body": True,
                })
                # SSE connection ends
                await send({
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                })

            base = SafeBreachMCPBase("test-server")
            app = base._create_concurrency_limited_app(fake_sse_app)
            await app(make_scope(path="/sse"), AsyncMock(), AsyncMock())

            # After SSE disconnect: zero semaphores — no leak
            assert len(_session_semaphores) == 0, (
                f"Expected 0 semaphores after SSE disconnect, "
                f"got {len(_session_semaphores)}: {list(_session_semaphores.keys())}"
            )
        asyncio.run(run())

    def test_sse_migration_rekeys_semaphore(self):
        """SSE migration moves the semaphore from middleware key to FastMCP key.

        After migration, the POST query string lookup should find the semaphore
        under the real session_id, not the middleware-generated UUID.
        """
        async def run():
            real_session_id = "abc123def456"

            async def fake_sse_app(scope, receive, send):
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({
                    "type": "http.response.body",
                    "body": f"event: endpoint\ndata: /messages/?session_id={real_session_id}\n\n".encode(),
                    "more_body": True,
                })
                # Keep SSE alive (don't send more_body=False)

            base = SafeBreachMCPBase("test-server")
            app = base._create_concurrency_limited_app(fake_sse_app)

            # Run SSE — the fake app keeps the connection alive
            await app(make_scope(path="/sse"), AsyncMock(), AsyncMock())

            # After SSE sends the endpoint event, the semaphore should be under the real key
            assert real_session_id in _session_semaphores, (
                f"Semaphore should be keyed by real session_id '{real_session_id}', "
                f"but found: {list(_session_semaphores.keys())}"
            )
            # Only one semaphore — the migrated one (no duplicate)
            assert len(_session_semaphores) == 1, (
                f"Expected exactly 1 semaphore (migrated), got {len(_session_semaphores)}"
            )
        asyncio.run(run())


class TestStaleSemaphoreCleanup:
    """Tests for stale semaphore cleanup logic."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        _session_semaphores.clear()
        yield
        _session_semaphores.clear()

    def test_cleanup_removes_stale_semaphores(self):
        """Semaphores older than _SEMAPHORE_MAX_AGE are removed."""
        _session_semaphores["fresh"] = (asyncio.Semaphore(1), time.time())
        _session_semaphores["stale"] = (asyncio.Semaphore(1), time.time() - _SEMAPHORE_MAX_AGE - 1)

        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)

        assert "fresh" in _session_semaphores
        assert "stale" not in _session_semaphores
        assert len(_session_semaphores) == 1

    def test_cleanup_preserves_fresh_semaphores(self):
        """Semaphores newer than _SEMAPHORE_MAX_AGE are preserved."""
        _session_semaphores["s1"] = (asyncio.Semaphore(1), time.time())
        _session_semaphores["s2"] = (asyncio.Semaphore(1), time.time() - 100)

        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)

        assert len(_session_semaphores) == 2

    def test_cleanup_handles_empty_dict(self):
        """Cleanup is a no-op when there are no semaphores."""
        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)
        assert len(_session_semaphores) == 0

    def test_cleanup_all_stale(self):
        """All stale entries are removed."""
        for i in range(5):
            _session_semaphores[f"stale_{i}"] = (
                asyncio.Semaphore(1), time.time() - _SEMAPHORE_MAX_AGE - i - 1
            )

        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)

        assert len(_session_semaphores) == 0
