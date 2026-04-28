"""
Tests for concurrency-safe auth bundle resolution (SAF-29974 Slice 6).

Verifies that _last_user_auth_bundle (global variable) has been removed and
replaced by per-request auth extraction from the MCP SDK's request_ctx.
"""

import pytest
from unittest.mock import MagicMock, patch

from safebreach_mcp_core.token_context import (
    _user_auth_artifacts,
    _session_auth_artifacts,
    _get_auth_from_mcp_request_ctx,
    _get_session_id_from_mcp_ctx,
    get_cache_user_suffix,
)
from safebreach_mcp_core.secret_utils import (
    get_auth_headers_for_console,
    AuthenticationRequired,
)

# Patch target: the SDK module where request_ctx lives.
# The helper functions import it via `from mcp.server.lowlevel.server import request_ctx`.
_REQUEST_CTX_PATCH = 'mcp.server.lowlevel.server.request_ctx'


@pytest.fixture(autouse=True)
def cleanup_auth_state():
    """Reset ContextVar and session store between tests."""
    token = _user_auth_artifacts.set(None)
    _session_auth_artifacts.clear()
    yield
    _user_auth_artifacts.set(None)
    _session_auth_artifacts.clear()
    _user_auth_artifacts.reset(token)


def _mock_request(headers=None, query_params=None):
    """Build a mock Starlette-like Request object."""
    req = MagicMock()
    req.headers = headers or {}
    req.query_params = query_params or {}
    return req


def _mock_request_ctx(request):
    """Build a mock MCP SDK RequestContext holding the given request."""
    ctx = MagicMock()
    ctx.request = request
    return ctx


class TestGetAuthFromMcpRequestCtx:

    def test_returns_none_outside_tool_context(self):
        """When request_ctx has no value (outside tool handler), returns None."""
        result = _get_auth_from_mcp_request_ctx()
        assert result is None

    def test_extracts_x_apitoken(self):
        """Extracts x-apitoken from the POST request headers."""
        req = _mock_request(headers={'x-apitoken': 'tok123'})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result == {'x-apitoken': 'tok123'}

    def test_extracts_x_token(self):
        """Extracts x-token (JWT) from the POST request headers."""
        req = _mock_request(headers={'x-token': 'jwt-abc'})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result == {'x-token': 'jwt-abc'}

    def test_extracts_and_scrubs_cookie(self):
        """Extracts cookie header and scrubs non-auth cookies."""
        raw_cookie = 'X-Token=jwt123; _ga=GA1.2; __secure-Fgp=fp456; _csrf=abc'
        req = _mock_request(headers={'cookie': raw_cookie})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result is not None
        assert 'cookie' in result
        assert 'X-Token=jwt123' in result['cookie']
        assert '__secure-Fgp=fp456' in result['cookie']
        assert '_ga' not in result['cookie']
        assert '_csrf' not in result['cookie']

    def test_extracts_all_artifacts(self):
        """Extracts all three auth artifacts when all present."""
        req = _mock_request(headers={
            'x-apitoken': 'api-key',
            'x-token': 'jwt-val',
            'cookie': 'X-Token=jwt123',
        })
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result is not None
        assert result['x-apitoken'] == 'api-key'
        assert result['x-token'] == 'jwt-val'
        assert 'X-Token=jwt123' in result['cookie']

    def test_returns_none_when_no_auth_headers(self):
        """Returns None when the request has no auth headers."""
        req = _mock_request(headers={'content-type': 'application/json'})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result is None

    def test_returns_none_when_request_is_none(self):
        """Returns None when request_ctx has no request attribute."""
        ctx = MagicMock()
        ctx.request = None
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_auth_from_mcp_request_ctx()
        assert result is None


class TestGetSessionIdFromMcpCtx:

    def test_returns_none_outside_tool_context(self):
        """When request_ctx has no value, returns None."""
        result = _get_session_id_from_mcp_ctx()
        assert result is None

    def test_extracts_session_id_from_query_params_sse(self):
        """SSE: session_id is in query_params."""
        req = _mock_request(query_params={'session_id': 'abc123hex'})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_session_id_from_mcp_ctx()
        assert result == 'abc123hex'

    def test_extracts_session_id_from_header_streamable_http(self):
        """Streamable-HTTP: session_id is in mcp-session-id header."""
        req = _mock_request(
            headers={'mcp-session-id': 'stream-sess-xyz'},
            query_params={},
        )
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_session_id_from_mcp_ctx()
        assert result == 'stream-sess-xyz'

    def test_prefers_query_param_over_header(self):
        """When both are present, query_params (SSE) takes precedence."""
        req = _mock_request(
            headers={'mcp-session-id': 'from-header'},
            query_params={'session_id': 'from-query'},
        )
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_session_id_from_mcp_ctx()
        assert result == 'from-query'


class TestConcurrentSessionIsolation:
    """The core safety test: two concurrent sessions must not leak credentials."""

    def test_two_sessions_different_tokens_get_own_credentials(self):
        """Simulate two tool handlers with different request_ctx values.

        Each should get its own auth headers, not the other's.
        """
        req_a = _mock_request(headers={'x-token': 'token-user-A'})
        ctx_a = _mock_request_ctx(req_a)
        req_b = _mock_request(headers={'x-token': 'token-user-B'})
        ctx_b = _mock_request_ctx(req_b)

        # Simulate User A's tool handler context
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx_a
            result_a = get_auth_headers_for_console('default')

        # Simulate User B's tool handler context
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx_b
            result_b = get_auth_headers_for_console('default')

        assert result_a['x-token'] == 'token-user-A'
        assert result_b['x-token'] == 'token-user-B'
        assert result_a['x-token'] != result_b['x-token']

    def test_session_store_fallback_isolates_sessions(self):
        """When request_ctx headers are empty, session store provides isolation."""
        # Pre-populate session store with different bundles
        _session_auth_artifacts['sess-A'] = ({'x-token': 'token-A'}, 1000.0)
        _session_auth_artifacts['sess-B'] = ({'x-token': 'token-B'}, 1000.0)

        # User A: request_ctx has session_id in query_params but no auth headers
        req_a = _mock_request(
            headers={},
            query_params={'session_id': 'sess-A'},
        )
        ctx_a = _mock_request_ctx(req_a)

        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx_a
            result_a = get_auth_headers_for_console('default')

        assert result_a['x-token'] == 'token-A'

        # User B: different session_id
        req_b = _mock_request(
            headers={},
            query_params={'session_id': 'sess-B'},
        )
        ctx_b = _mock_request_ctx(req_b)

        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx_b
            result_b = get_auth_headers_for_console('default')

        assert result_b['x-token'] == 'token-B'


class TestGetCacheUserSuffix:

    def test_uses_mcp_request_ctx_when_contextvar_empty(self):
        """get_cache_user_suffix falls back to MCP request_ctx when ContextVar is None."""
        req = _mock_request(headers={'x-apitoken': 'stable-token-123'})
        ctx = _mock_request_ctx(req)

        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            suffix = get_cache_user_suffix()

        assert suffix.startswith('_')
        assert len(suffix) == 9  # '_' + 8 hex chars

    def test_returns_empty_when_no_context(self):
        """Returns empty string when neither ContextVar nor request_ctx has auth."""
        suffix = get_cache_user_suffix()
        assert suffix == ''

    def test_contextvar_takes_priority_over_request_ctx(self):
        """When ContextVar has a value, request_ctx is not consulted."""
        _user_auth_artifacts.set({'x-apitoken': 'from-contextvar'})

        import hashlib
        expected = '_' + hashlib.sha256('from-contextvar'.encode()).hexdigest()[:8]
        suffix = get_cache_user_suffix()
        assert suffix == expected


class TestLastUserAuthBundleRemoved:

    def test_module_no_longer_exports_last_user_auth_bundle(self):
        """_last_user_auth_bundle must not exist in token_context module."""
        import safebreach_mcp_core.token_context as tc
        assert not hasattr(tc, '_last_user_auth_bundle'), \
            '_last_user_auth_bundle should have been removed (Slice 6 concurrency fix)'


class TestGetAuthHeadersForConsole:

    def test_raises_when_no_auth_available(self):
        """Raises AuthenticationRequired when no auth is found anywhere."""
        with pytest.raises(AuthenticationRequired):
            get_auth_headers_for_console('default')

    def test_contextvar_primary_path(self):
        """ContextVar is the primary source when available."""
        _user_auth_artifacts.set({'x-token': 'ctx-jwt', 'cookie': 'X-Token=ctx'})
        result = get_auth_headers_for_console('default')
        assert result['x-token'] == 'ctx-jwt'

    def test_returns_copy_not_original(self):
        """Returns a copy of the bundle so callers can mutate it safely."""
        _user_auth_artifacts.set({'x-token': 'jwt1'})
        result = get_auth_headers_for_console('default')
        result['x-token'] = 'mutated'
        assert _user_auth_artifacts.get()['x-token'] == 'jwt1'
