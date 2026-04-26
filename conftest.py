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
