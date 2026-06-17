"""
Root conftest.py — provides auth context for E2E tests (SAF-29974).

E2E tests call tool functions directly (not through the MCP ASGI chain),
so the _user_auth_artifacts ContextVar is not set by the middleware.
This fixture reads the API token from the environment (same as set_env.sh)
and sets the ContextVar so get_auth_headers_for_console() works.
"""

import os
import pytest
from safebreach_mcp_core.token_context import _user_auth_artifacts
from safebreach_mcp_core.rate_limiter import _rate_limit_store


def _resolve_api_token(console: str):
    """Resolve API token for a console from environment variables."""
    token_key = f"{console.replace('-', '_')}_apitoken"
    return os.environ.get(token_key) or os.environ.get('SB_API_KEY')


@pytest.fixture(autouse=True, scope="session")
def set_e2e_auth_context():
    """Set auth ContextVar for E2E tests using the environment API token.

    Session-scoped so it runs before class-scoped fixtures that call tool
    functions (e.g., sample_test_id, sample_simulation_id).
    """
    console = os.environ.get('E2E_CONSOLE', 'default')
    api_token = _resolve_api_token(console)

    if not api_token:
        yield
        return

    token = _user_auth_artifacts.set({"x-apitoken": api_token})
    yield
    _user_auth_artifacts.reset(token)


@pytest.fixture
def e2e_auth_for_console():
    """Factory fixture: temporarily swap ContextVar to a different console's token.

    Usage in tests that target a non-default console:
        def test_something(self, e2e_auth_for_console):
            with e2e_auth_for_console('staging'):
                result = sb_some_tool(console='staging')
    """
    import contextlib

    @contextlib.contextmanager
    def _swap(console: str):
        api_token = _resolve_api_token(console)
        if not api_token:
            pytest.skip(f"No API token found for console '{console}'")
        old = _user_auth_artifacts.set({"x-apitoken": api_token})
        try:
            yield
        finally:
            _user_auth_artifacts.reset(old)

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
    ctx = _user_auth_artifacts.set({"x-apitoken": api_token}) if api_token else None
    try:
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
    finally:
        if ctx is not None:
            _user_auth_artifacts.reset(ctx)
        _E2E_CREATED_TESTS.clear()
