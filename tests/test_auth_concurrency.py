"""
Tests for concurrency-safe auth bundle resolution (SAF-29974 Slice 6).

Verifies that auth is resolved only from the MCP SDK's request_ctx (the live
request) — the process-global bundle, the per-request ContextVar and the SSE
session store are all gone (SAF-29974 / SAF-32359 / SAF-32387).
"""

import pytest
from unittest.mock import MagicMock, patch

from safebreach_mcp_core.token_context import (
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

    def test_ignores_legacy_sse_query_param(self):
        """The legacy SSE session_id query param is no longer consulted (SAF-32387)."""
        req = _mock_request(headers={}, query_params={'session_id': 'from-query'})
        ctx = _mock_request_ctx(req)
        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            result = _get_session_id_from_mcp_ctx()
        assert result is None


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


class TestGetCacheUserSuffix:

    def test_uses_mcp_request_ctx(self):
        """get_cache_user_suffix derives the suffix from the live MCP request."""
        req = _mock_request(headers={'x-apitoken': 'stable-token-123'})
        ctx = _mock_request_ctx(req)

        with patch(_REQUEST_CTX_PATCH) as mock_rc:
            mock_rc.get.return_value = ctx
            suffix = get_cache_user_suffix()

        assert suffix.startswith('_')
        assert len(suffix) == 9  # '_' + 8 hex chars

    def test_returns_empty_when_no_context(self):
        """Returns empty string when request_ctx has no auth."""
        suffix = get_cache_user_suffix()
        assert suffix == ''

    def test_suffix_is_stable_hash_of_request_token(self, mcp_request_auth):
        """The suffix is a stable hash of the request's token."""
        import hashlib
        expected = '_' + hashlib.sha256('from-request'.encode()).hexdigest()[:8]
        with mcp_request_auth({'x-apitoken': 'from-request'}):
            suffix = get_cache_user_suffix()
        assert suffix == expected


class TestLegacyAuthStateRemoved:

    @pytest.mark.parametrize('name', [
        '_last_user_auth_bundle',      # SAF-29974 Slice 6
        '_user_auth_artifacts',        # SAF-32387
        '_session_auth_artifacts',     # SAF-32387
        '_SESSION_ARTIFACTS_TTL',      # SAF-32387
        'cleanup_stale_artifacts',     # SAF-32387
    ])
    def test_module_no_longer_exports_legacy_auth_state(self, name):
        """token_context must expose no auth source other than the live request."""
        import safebreach_mcp_core.token_context as tc
        assert not hasattr(tc, name), f'{name} should have been removed'


class TestGetAuthHeadersForConsole:

    def test_raises_when_no_auth_in_embedded_mode(self):
        """Raises AuthenticationRequired in embedded mode (SAFEBREACH_LOCAL_ENV set)."""
        with patch.dict('os.environ', {'SAFEBREACH_LOCAL_ENV': '{"default":{}}'}):
            with pytest.raises(AuthenticationRequired):
                get_auth_headers_for_console('default')

    def test_falls_back_to_api_key_in_standalone_mode(self):
        """Falls back to get_secret_for_console() in standalone mode (no SAFEBREACH_LOCAL_ENV)."""
        with patch.dict('os.environ', {}, clear=False):
            # Ensure SAFEBREACH_LOCAL_ENV is not set
            import os
            os.environ.pop('SAFEBREACH_LOCAL_ENV', None)
            with patch('safebreach_mcp_core.secret_utils.get_secret_for_console',
                       return_value='standalone-api-key') as mock_secret:
                result = get_auth_headers_for_console('staging')
                assert result == {'x-apitoken': 'standalone-api-key'}
                mock_secret.assert_called_once_with('staging')

    def test_request_ctx_is_the_source(self, mcp_request_auth):
        """The live request's headers are the auth source."""
        with mcp_request_auth({'x-token': 'ctx-jwt', 'cookie': 'X-Token=ctx'}):
            result = get_auth_headers_for_console('default')
        assert result['x-token'] == 'ctx-jwt'

    def test_returns_copy_not_original(self, mcp_request_auth):
        """Returns a fresh dict per call so callers can mutate it safely."""
        with mcp_request_auth({'x-token': 'jwt1'}):
            result = get_auth_headers_for_console('default')
            result['x-token'] = 'mutated'
            again = get_auth_headers_for_console('default')
        assert again['x-token'] == 'jwt1'
