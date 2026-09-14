"""
User auth extraction from the live MCP request for RBAC token propagation (SAF-29974).

All readers take the user's auth artifacts from the live MCP request
(_get_auth_from_mcp_request_ctx) — the single source of truth, so a value
captured from an earlier request can never be reused (SAF-32359, SAF-32387).
"""

import hashlib
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = os.environ.get('SAFEBREACH_MCP_AUTH_COOKIE_NAME', 'X-Token')


def extract_auth_bundle(scope: dict) -> Optional[Dict[str, str]]:
    """Extract x-apitoken/x-token/cookie(filtered) from ASGI scope headers.

    Returns a dict with only the non-empty auth artifacts, or None if none present.
    """
    raw_headers = dict(scope.get('headers', []))
    bundle: Dict[str, str] = {}

    apitoken = raw_headers.get(b'x-apitoken', b'').decode('utf-8', errors='ignore')
    if apitoken:
        bundle['x-apitoken'] = apitoken

    x_token = raw_headers.get(b'x-token', b'').decode('utf-8', errors='ignore')
    if x_token:
        bundle['x-token'] = x_token

    raw_cookie = raw_headers.get(b'cookie', b'').decode('utf-8', errors='ignore')
    scrubbed = _keep_only_cookie(raw_cookie, AUTH_COOKIE_NAME)
    if scrubbed:
        bundle['cookie'] = scrubbed

    return bundle or None


def _get_auth_from_mcp_request_ctx() -> Optional[Dict[str, str]]:
    """Extract user auth headers from the MCP SDK's request context.

    Inside a tool handler, the SDK's request_ctx ContextVar holds a
    RequestContext whose .request attribute is the Starlette Request from
    the POST that triggered the tool call.  The request carries the user's
    auth headers that SIMP forwarded.

    Returns auth bundle dict or None if request_ctx is not available.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
        ctx = request_ctx.get()
    except (ImportError, LookupError):
        return None

    request = getattr(ctx, 'request', None)
    if request is None:
        return None

    headers = getattr(request, 'headers', None)
    if headers is None:
        return None

    bundle: Dict[str, str] = {}
    apitoken = headers.get('x-apitoken', '')
    if apitoken:
        bundle['x-apitoken'] = apitoken
    x_token = headers.get('x-token', '')
    if x_token:
        bundle['x-token'] = x_token
    raw_cookie = headers.get('cookie', '')
    scrubbed = _keep_only_cookie(raw_cookie, AUTH_COOKIE_NAME)
    if scrubbed:
        bundle['cookie'] = scrubbed
    return bundle or None


def _get_session_id_from_mcp_ctx() -> Optional[str]:
    """Extract the streamable-http session id ('mcp-session-id' header) from
    the MCP SDK's request context.

    Returns None if request_ctx is not available or has no session_id.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
        ctx = request_ctx.get()
    except (ImportError, LookupError):
        return None

    request = getattr(ctx, 'request', None)
    if request is None:
        return None

    hdrs = getattr(request, 'headers', None) or {}
    return hdrs.get('mcp-session-id') or None


# Cookies to keep when scrubbing — auth token + fingerprint needed for JWT validation.
_ALLOWED_COOKIE_NAMES = frozenset()  # populated at module load from AUTH_COOKIE_NAME + fingerprint

# The ui-server's JWT validation requires the __secure-Fgp (user fingerprint) cookie
# alongside the JWT. Without it, x-token auth returns 401.
_FINGERPRINT_COOKIE_NAME = '__secure-Fgp'


def _keep_only_cookie(raw_cookie: str, cookie_name: str) -> str:
    """Parse a raw cookie header and keep only auth-related cookies.

    Keeps the auth cookie (X-Token) and the fingerprint cookie (__secure-Fgp)
    needed for JWT validation. Drops all other cookies (analytics, CSRF, etc.).

    Returns e.g. "X-Token=<value>; __secure-Fgp=<value>" or empty string.
    """
    if not raw_cookie:
        return ''
    allowed = {cookie_name.lower(), _FINGERPRINT_COOKIE_NAME.lower()}
    kept = []
    for part in raw_cookie.split(';'):
        part = part.strip()
        if '=' in part:
            name, _, value = part.partition('=')
            if name.strip().lower() in allowed:
                kept.append(f'{name.strip()}={value.strip()}')
    return '; '.join(kept)


def get_cache_user_suffix() -> str:
    """Return a user-scoped cache key suffix based on the current auth artifacts.

    Returns '_' + first 8 chars of SHA-256 hex digest of the most stable
    artifact present, or '' when the current request carries no user bundle.
    """
    bundle = _get_auth_from_mcp_request_ctx()
    if not bundle:
        logger.debug("get_cache_user_suffix() → '' (no user bundle)")
        return ''

    # Priority: x-apitoken (most stable) > x-token > cookie value
    value = bundle.get('x-apitoken')
    if not value:
        value = bundle.get('x-token')
    if not value:
        cookie = bundle.get('cookie', '')
        if '=' in cookie:
            value = cookie.split('=', 1)[1]
    if not value:
        logger.debug("get_cache_user_suffix() → '' (bundle present but no usable value)")
        return ''

    suffix = '_' + hashlib.sha256(value.encode()).hexdigest()[:8]
    logger.info("get_cache_user_suffix() → '%s' (from token ***%s)", suffix, value[-4:])
    return suffix

