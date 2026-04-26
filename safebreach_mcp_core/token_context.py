"""
Per-request user auth context for RBAC token propagation (SAF-29974).

Provides a ContextVar that carries the user's auth artifacts through the
async call chain within a single request, and a session store for SSE
transport resilience.
"""

import contextvars
import hashlib
import os
import time
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Per-request ContextVar — set at the ASGI middleware layer, read by tool functions
# via get_auth_headers_for_console().
_user_auth_artifacts: contextvars.ContextVar[Optional[Dict[str, str]]] = \
    contextvars.ContextVar('user_auth_artifacts', default=None)

# Session artifact store — backup for SSE transport where headers may not be
# present on /messages/ POST requests. Keyed by session_id.
_session_auth_artifacts: Dict[str, Tuple[Dict[str, str], float]] = {}

_SESSION_ARTIFACTS_TTL = 3600  # matches existing semaphore cleanup TTL

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


def _keep_only_cookie(raw_cookie: str, cookie_name: str) -> str:
    """Parse a raw cookie header and return only the named cookie entry.

    Returns e.g. "X-Token=<value>" or empty string if not found.
    """
    if not raw_cookie:
        return ''
    for part in raw_cookie.split(';'):
        part = part.strip()
        if '=' in part:
            name, _, value = part.partition('=')
            if name.strip().lower() == cookie_name.lower():
                return f'{cookie_name}={value.strip()}'
    return ''


def mask_artifacts(bundle: Optional[Dict[str, str]]) -> Dict[str, str]:
    """For logging only — returns keys with masked values."""
    if not bundle:
        return {}
    return {k: '***' + v[-4:] if len(v) > 4 else '****' for k, v in bundle.items()}


def get_cache_user_suffix() -> str:
    """Return a user-scoped cache key suffix based on the current auth artifacts.

    Returns '_' + first 8 chars of SHA-256 hex digest of the most stable
    artifact present, or '' when no user bundle is set.
    """
    bundle = _user_auth_artifacts.get()
    if not bundle:
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
        return ''

    return '_' + hashlib.sha256(value.encode()).hexdigest()[:8]


def cleanup_stale_artifacts(ttl: int = None) -> int:
    """Remove stale entries from the session artifact store.

    Returns the number of entries evicted.
    """
    if ttl is None:
        ttl = _SESSION_ARTIFACTS_TTL
    now = time.time()
    stale_keys = [k for k, (_, ts) in _session_auth_artifacts.items() if now - ts > ttl]
    for k in stale_keys:
        _session_auth_artifacts.pop(k, None)
    if stale_keys:
        logger.info(f'Evicted {len(stale_keys)} stale auth artifact entries, '
                     f'{len(_session_auth_artifacts)} remaining')
    return len(stale_keys)
