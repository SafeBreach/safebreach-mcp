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
    _concurrency_limit,
    _concurrency_key,
    _cleanup_stale_semaphores,
    _SEMAPHORE_MAX_AGE,
)


@pytest.fixture(autouse=True)
def cleanup_session_state():
    """Clean up module-level session state between tests."""
    _session_semaphores.clear()
    yield
    _session_semaphores.clear()


def make_scope(path="/mcp", scope_type="http", session_id=None, method="POST"):
    """Create a minimal streamable-http ASGI scope for testing."""
    headers = [(b"mcp-session-id", session_id.encode())] if session_id else []
    return {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }


def _sh_scope(session_id, token, path="/mcp"):
    """A streamable-http POST scope carrying an mcp-session-id and an x-token JWT."""
    return {
        "type": "http",
        "path": path,
        "method": "POST",
        "headers": [(b"mcp-session-id", session_id.encode()), (b"x-token", token.encode())],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }


def _make_app():
    """Create a concurrency-limited app wrapping a passthrough."""
    base = SafeBreachMCPBase("test-server")
    original_app = AsyncMock()
    return base._create_concurrency_limited_app(original_app), original_app


class TestConcurrencyLimiter:
    """Tests for _create_concurrency_limited_app (streamable-http, single /mcp endpoint)."""

    def test_non_http_passes_through(self):
        """Non-HTTP scopes (websocket, lifespan) pass through without limiting."""
        async def run():
            app, original = _make_app()
            scope = make_scope(scope_type="websocket")
            await app(scope, AsyncMock(), AsyncMock())
            original.assert_awaited_once()
        asyncio.run(run())

    def test_other_paths_pass_through(self):
        """Paths other than the MCP endpoint pass through without limiting."""
        async def run():
            app, original = _make_app()
            await app(make_scope(path="/api/some/other/endpoint", session_id="s1"), AsyncMock(), AsyncMock())
            original.assert_awaited_once()
            assert len(_session_semaphores) == 0
        asyncio.run(run())

    def test_legacy_sse_paths_are_not_special(self):
        """/sse and /messages/ are plain unknown paths now — no session bookkeeping (SAF-32387)."""
        async def run():
            app, original = _make_app()
            await app(make_scope(path="/sse", method="GET"), AsyncMock(), AsyncMock())
            await app(make_scope(path="/messages/", session_id="s1"), AsyncMock(), AsyncMock())
            assert original.await_count == 2
            assert len(_session_semaphores) == 0
        asyncio.run(run())

    def test_initialize_without_session_passes_through(self):
        """The initialize POST has no mcp-session-id yet and is never limited."""
        async def run():
            app, original = _make_app()
            await app(make_scope(), AsyncMock(), AsyncMock())
            original.assert_awaited_once()
            assert len(_session_semaphores) == 0
        asyncio.run(run())

    def test_session_post_creates_bucket(self):
        """A POST with mcp-session-id registers a (Semaphore, timestamp) bucket keyed per server."""
        async def run():
            app, original = _make_app()
            await app(make_scope(session_id="sess-1"), AsyncMock(), AsyncMock())
            original.assert_awaited_once()
            assert list(_session_semaphores) == ["test-server::sess-1"]
            sem, created_at = _session_semaphores["test-server::sess-1"]
            assert isinstance(sem, asyncio.Semaphore)
            assert isinstance(created_at, float)
            assert created_at <= time.time()
        asyncio.run(run())

    def test_request_under_limit_passes_through(self):
        """Requests within the concurrency limit pass through."""
        async def run():
            app, original = _make_app()
            await app(make_scope(session_id="sess-1"), AsyncMock(), AsyncMock())
            await app(make_scope(session_id="sess-1"), AsyncMock(), AsyncMock())
            assert original.await_count == 2
        asyncio.run(run())

    def test_request_over_limit_returns_429(self):
        """Requests exceeding the concurrency limit get an immediate HTTP 429 with Retry-After."""
        async def run():
            app, original = _make_app()
            sem = asyncio.Semaphore(1)
            _session_semaphores["test-server::sess-429"] = (sem, time.time())
            await sem.acquire()  # exhaust the bucket
            send = AsyncMock()
            await app(make_scope(session_id="sess-429"), AsyncMock(), send)
            original.assert_not_awaited()
            assert send.await_count == 2
            start_call = send.call_args_list[0][0][0]
            assert start_call["status"] == 429
            assert dict(start_call["headers"])[b"retry-after"] == b"5"
            body_json = json.loads(send.call_args_list[1][0][0]["body"])
            assert body_json["error"] == "Too Many Requests"
            sem.release()
        asyncio.run(run())

    def test_different_sessions_independent_limits(self):
        """Different sessions (no JWT) have independent buckets."""
        async def run():
            app, original = _make_app()
            sem_a = asyncio.Semaphore(1)
            _session_semaphores["test-server::session-a"] = (sem_a, time.time())
            await sem_a.acquire()
            await app(make_scope(session_id="session-b"), AsyncMock(), AsyncMock())
            original.assert_awaited_once()
            sem_a.release()
        asyncio.run(run())

    def test_env_var_default(self):
        """Default concurrency limit is 2."""
        assert _concurrency_limit == 2


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


class TestPerJwtConcurrency:
    """SAF-31903: concurrency is bucketed per-JWT, not per shared mcp-session-id."""

    def test_key_prefers_jwt_and_is_session_independent(self):
        k1 = _concurrency_key({"x-token": "tok"}, "sessionA")
        k2 = _concurrency_key({"x-token": "tok"}, "sessionB")
        assert k1 == k2 and k1.startswith("jwt:")
        assert _concurrency_key({"x-token": "a"}, "s") != _concurrency_key({"x-token": "b"}, "s")
        assert _concurrency_key({}, "sid-fallback") == "sid-fallback"
        assert _concurrency_key(None, None) is None

    def test_two_jwts_have_independent_limits(self):
        async def run():
            base = SafeBreachMCPBase("test-perjwt")
            original = AsyncMock()
            app = base._create_concurrency_limited_app(
                original, endpoint_path="/mcp"
            )
            session_id = "shared-session"
            # Saturate JWT A's bucket (limit 1, no release)
            key_a = base._bucket_key({"x-token": "tokenA"}, session_id)
            sem_a = asyncio.Semaphore(1)
            await sem_a.acquire()
            _session_semaphores[key_a] = (sem_a, time.time())

            # Request as JWT A on the shared session → 429 (its bucket is full)
            send_a = AsyncMock()
            await app(_sh_scope(session_id, "tokenA"), AsyncMock(), send_a)
            assert send_a.call_args_list[0][0][0]["status"] == 429

            # Request as JWT B on the SAME session → passes (independent bucket)
            send_b = AsyncMock()
            await app(_sh_scope(session_id, "tokenB"), AsyncMock(), send_b)
            original.assert_awaited_once()
            assert send_b.await_count == 0

            sem_a.release()
        asyncio.run(run())

    def test_same_jwt_shares_bucket_across_sessions(self):
        async def run():
            base = SafeBreachMCPBase("test-perjwt2")
            original = AsyncMock()
            app = base._create_concurrency_limited_app(
                original, endpoint_path="/mcp"
            )
            # Saturate the JWT's bucket, computed with one session id
            key = base._bucket_key({"x-token": "tok"}, "session-1")
            sem = asyncio.Semaphore(1)
            await sem.acquire()
            _session_semaphores[key] = (sem, time.time())

            # Same token but a DIFFERENT session id → same bucket → 429
            send = AsyncMock()
            await app(_sh_scope("session-2", "tok"), AsyncMock(), send)
            assert send.call_args_list[0][0][0]["status"] == 429
            original.assert_not_awaited()

            sem.release()
        asyncio.run(run())


class TestPerServerConcurrencyBucket:
    """SAF-33239: servers in one process must not share a concurrency bucket."""

    def test_bucket_key_namespaced_per_server(self):
        studio = SafeBreachMCPBase("studio")
        playbook = SafeBreachMCPBase("playbook")
        bundle = {"x-token": "svc"}
        assert studio._bucket_key(bundle, "s") != playbook._bucket_key(bundle, "s")
        assert studio._bucket_key(bundle, "s").startswith("studio::")
        assert studio._bucket_key(None, None) is None

    def test_servers_do_not_share_a_bucket_under_one_token(self):
        """The regression: one service token that starves studio must not starve playbook."""
        async def run():
            studio = SafeBreachMCPBase("studio")
            playbook = SafeBreachMCPBase("playbook")
            orig_p = AsyncMock()
            app_s = studio._create_concurrency_limited_app(
                AsyncMock(), endpoint_path="/mcp"
            )
            app_p = playbook._create_concurrency_limited_app(
                orig_p, endpoint_path="/mcp"
            )
            token = "service-token"
            sem = asyncio.Semaphore(1)
            await sem.acquire()
            _session_semaphores[studio._bucket_key({"x-token": token}, "sess-studio")] = (sem, time.time())

            send_s = AsyncMock()
            await app_s(_sh_scope("sess-studio", token), AsyncMock(), send_s)
            assert send_s.call_args_list[0][0][0]["status"] == 429

            send_p = AsyncMock()
            await app_p(_sh_scope("sess-pb", token), AsyncMock(), send_p)
            orig_p.assert_awaited_once()
            assert send_p.await_count == 0

            sem.release()
        asyncio.run(run())

    def test_streamable_get_channel_does_not_hold_a_slot(self):
        """A long-lived GET SSE channel passes through even when the bucket is saturated."""
        async def run():
            base = SafeBreachMCPBase("studio")
            original = AsyncMock()
            app = base._create_concurrency_limited_app(
                original, endpoint_path="/mcp"
            )
            token = "tok"
            sem = asyncio.Semaphore(1)
            await sem.acquire()
            _session_semaphores[base._bucket_key({"x-token": token}, "s1")] = (sem, time.time())

            get_scope = {**_sh_scope("s1", token), "method": "GET"}
            send = AsyncMock()
            await app(get_scope, AsyncMock(), send)
            original.assert_awaited_once()
            assert send.await_count == 0

            sem.release()
        asyncio.run(run())

    def test_refresh_across_servers_under_one_token_no_429(self):
        """Reproduces breach-genie refreshing tools across every server under one token."""
        async def run():
            names = ["configuration", "data", "playbook", "studio"]
            gate = asyncio.Event()

            async def original(scope, receive, send):
                if scope.get("method") == "GET":
                    await gate.wait()

            apps = {
                n: SafeBreachMCPBase(n)._create_concurrency_limited_app(
                    original, endpoint_path="/mcp"
                )
                for n in names
            }
            token = "service-token"
            gets = [
                asyncio.create_task(
                    apps[n]({**_sh_scope(f"sess-{n}", token), "method": "GET"}, AsyncMock(), AsyncMock())
                )
                for n in names
            ]
            for _ in range(3):
                await asyncio.sleep(0)

            sends = {}
            for n in names:
                sends[n] = AsyncMock()
                await apps[n](_sh_scope(f"sess-{n}", token), AsyncMock(), sends[n])

            for n in names:
                statuses = [c[0][0].get("status") for c in sends[n].call_args_list if c[0]]
                assert 429 not in statuses, f"{n} unexpectedly rate-limited: {statuses}"

            gate.set()
            await asyncio.gather(*gets)
        asyncio.run(run())
