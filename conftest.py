"""
Root conftest.py — provides auth context for tests (SAF-29974 / SAF-32387).

Production delivers the user's auth on the live MCP request: tool code reads it
via token_context._get_auth_from_mcp_request_ctx(), which looks at the MCP SDK's
request_ctx ContextVar. Tests call tool functions directly (no ASGI request), so
the fixtures here set request_ctx to a fake request carrying the auth headers —
the same path production uses, with no bridging shim.
"""

import contextlib
import os
from types import SimpleNamespace

import pytest
from mcp.server.lowlevel.server import request_ctx
from safebreach_mcp_core.rate_limiter import _rate_limit_store


def _resolve_api_token(console: str):
    """Resolve API token for a console from environment variables."""
    token_key = f"{console.replace('-', '_')}_apitoken"
    return os.environ.get(token_key) or os.environ.get('SB_API_KEY')


@contextlib.contextmanager
def _request_ctx_with_auth(bundle):
    """Set the MCP SDK request_ctx to a fake request whose headers carry `bundle`.

    `bundle` is a dict of auth headers (x-apitoken / x-token / cookie) or None
    for a request without user auth.
    """
    fake_ctx = SimpleNamespace(request=SimpleNamespace(headers=dict(bundle or {})))
    token = request_ctx.set(fake_ctx)
    try:
        yield
    finally:
        request_ctx.reset(token)


@pytest.fixture(scope="session")
def mcp_request_auth():
    """Factory fixture: run a block as if inside an MCP request carrying `bundle`.

    Usage:
        @pytest.fixture(autouse=True)
        def set_auth_context(self, mcp_request_auth):
            with mcp_request_auth({"x-apitoken": "test-token"}):
                yield

        with mcp_request_auth(None):   # request with no user auth
            ...
    """
    return _request_ctx_with_auth


@pytest.fixture(autouse=True, scope="session")
def set_e2e_auth_context():
    """Provide request auth for E2E tests using the environment API token.

    Session-scoped so it runs before class-scoped fixtures that call tool
    functions (e.g., sample_test_id, sample_simulation_id).
    """
    console = os.environ.get('E2E_CONSOLE', 'default')
    api_token = _resolve_api_token(console)

    if not api_token:
        yield
        return

    with _request_ctx_with_auth({"x-apitoken": api_token}):
        yield


@pytest.fixture
def e2e_auth_for_console():
    """Factory fixture: temporarily switch request auth to a different console's token.

    Usage in tests that target a non-default console:
        def test_something(self, e2e_auth_for_console):
            with e2e_auth_for_console('staging'):
                result = sb_some_tool(console='staging')
    """

    @contextlib.contextmanager
    def _swap(console: str):
        api_token = _resolve_api_token(console)
        if not api_token:
            pytest.skip(f"No API token found for console '{console}'")
        with _request_ctx_with_auth({"x-apitoken": api_token}):
            yield

    return _swap


@pytest.fixture(autouse=True)
def clear_rate_limit_store():
    """Clear rate limit state between tests to prevent cross-test accumulation."""
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


# ---------------------------------------------------------------------------
# E2E test-run registry + session epilogue (SAF-31468 follow-up)
#
# E2E tests queue REAL tests on the console. If they are not cancelled they pile
# up in the orchestrator queue and clog the console's test pipeline (observed:
# freshly-queued tests then take many minutes/hours to start and ingest).
#
# Tests register every run they queue here; the session epilogue cancels any that
# are still cancellable at the end. The registry guarantees we only ever cancel
# tests OUR suite initiated — never tests started by other users/automation.
# ---------------------------------------------------------------------------

_E2E_CREATED_TESTS = []  # list of (test_id, console) queued by this E2E session


def register_e2e_test(test_id, console):
    """Record a test queued by the E2E suite so the session epilogue can cancel it
    if it is still running at the end. Only tests registered here are cancelled."""
    if test_id:
        _E2E_CREATED_TESTS.append((str(test_id), console))


@pytest.fixture(autouse=True, scope="session")
def cancel_e2e_leftovers():
    """Session epilogue: best-effort cancel every test OUR E2E suite queued that is
    still running/queued at the end, so they don't accumulate on the console.

    Scoped strictly to registered (our-initiated) test_ids. Clears the rate-limit
    store first so cleanup cancels are not themselves blocked by a limit exhausted
    during the run. Tests already in a terminal state are skipped (best-effort)."""
    yield

    if not _E2E_CREATED_TESTS:
        return

    # Cleanup cancels must not be blocked by rate limiting exhausted during tests.
    try:
        _rate_limit_store.clear()
    except Exception:
        pass

    # Ensure an auth token is active for the cancel calls (independent of other
    # session fixtures' teardown ordering).
    console_default = os.environ.get('E2E_CONSOLE', 'default')
    api_token = _resolve_api_token(console_default)
    auth_ctx = _request_ctx_with_auth({"x-apitoken": api_token}) if api_token else contextlib.nullcontext()
    with auth_ctx:
        from safebreach_mcp_studio.studio_functions import sb_manage_test
        seen = set()
        cancelled = 0
        for test_id, console in _E2E_CREATED_TESTS:
            if test_id in seen:
                continue
            seen.add(test_id)
            try:
                sb_manage_test(test_id=test_id, action="cancel", console=console)
                cancelled += 1
            except Exception:
                # A PAUSED test cannot be cancelled directly ("resume first, then
                # cancel") — resume then cancel. Other failures (already terminal,
                # API error) are fine to ignore (best-effort).
                try:
                    sb_manage_test(test_id=test_id, action="resume", console=console)
                    sb_manage_test(test_id=test_id, action="cancel", console=console)
                    cancelled += 1
                except Exception:
                    pass
        print(f"\n[E2E epilogue] cancelled {cancelled} leftover test(s) of "
              f"{len(seen)} registered")
    _E2E_CREATED_TESTS.clear()
