"""
SafeBreach User Lookup

Cached user ID → name resolution via the config API.
Always-on cache (not gated by is_caching_enabled) since users change
infrequently and the lookup is a cross-cutting concern.

Usage::

    from safebreach_mcp_core.user_lookup import get_user_name

    name = get_user_name(347116670300007, "pentest01")
    # Returns "Yossi" or None if lookup fails
"""

import logging
from typing import Dict, Optional

import requests
from .safebreach_cache import SafeBreachCache
from .secret_utils import get_auth_headers_for_console, check_rbac_response
from .token_context import get_cache_user_suffix
from .environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

# Always-on cache — users rarely change, 1 hour TTL
users_cache = SafeBreachCache(name="users", maxsize=5, ttl=3600)


def _fetch_users_map(console: str) -> Dict[int, str]:
    """
    Fetch all users from the config API and return a {user_id: user_name} map.

    Results are cached per console (always-on, not gated by is_caching_enabled).
    On any error (403, network, etc.), returns empty dict — best-effort.
    """
    cache_key = f"users_{console}{get_cache_user_suffix()}"
    cached = users_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)
        url = (
            f"{base_url}/api/config/v1/accounts/{account_id}"
            f"/users?details=false&deleted=true"
        )
        headers = {"accept": "application/json", **get_auth_headers_for_console(console)}

        response = requests.get(url, headers=headers, timeout=30)
        check_rbac_response(response)
        data = response.json()

        users_list = data.get('data', []) if isinstance(data, dict) else []
        users_map = {
            u['id']: u.get('name', u.get('email', str(u['id'])))
            for u in users_list
            if 'id' in u
        }

        users_cache.set(cache_key, users_map)
        logger.info("Cached %d users for console '%s'", len(users_map), console)
        return users_map

    except Exception as e:
        logger.warning("Failed to fetch users for console '%s': %s", console, e)
        return {}


def get_user_name(user_id: Optional[int], console: str) -> Optional[str]:
    """
    Resolve a numeric user ID to a username. Best-effort.

    Args:
        user_id: SafeBreach user ID (e.g., 347116670300007)
        console: SafeBreach console identifier

    Returns:
        Username string or None if user ID is None or not found.
    """
    if user_id is None:
        return None
    users_map = _fetch_users_map(console)
    return users_map.get(user_id)
