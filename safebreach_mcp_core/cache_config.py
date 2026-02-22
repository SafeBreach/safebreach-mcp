"""
SafeBreach MCP Cache Configuration

Centralized cache configuration for all MCP servers.
Caching is opt-in and controlled by per-server environment variables:

    SB_MCP_CACHE_CONFIG=true/false      Config server
    SB_MCP_CACHE_DATA=true/false        Data server
    SB_MCP_CACHE_PLAYBOOK=true/false    Playbook server
    SB_MCP_CACHE_STUDIO=true/false      Studio server

By default, caching is DISABLED to prevent memory exhaustion.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Environment variable names
_SERVER_ENV_PREFIX = "SB_MCP_CACHE_"

_TRUTHY = frozenset(("true", "1", "yes", "on"))

# Cached resolved values
_per_server_cache: dict[str, bool] = {}


def _parse_bool_env(value: str) -> bool:
    """Parse an env var string as boolean."""
    return value.lower().strip() in _TRUTHY


def is_caching_enabled(server_name: str | None = None) -> bool:
    """
    Check if local caching is enabled for a specific server.

    Args:
        server_name: Server identifier (e.g. "config", "data",
            "playbook", "studio"). Case-insensitive.
            If ``None``, returns ``False``.

    Returns:
        True if caching is enabled for the given server.
    """
    if server_name is None:
        return False

    # Per-server lookup (cached per server_name)
    key = server_name.lower()
    if key not in _per_server_cache:
        env_name = f"{_SERVER_ENV_PREFIX}{key.upper()}"
        env_value = os.environ.get(env_name)
        if env_value is not None:
            _per_server_cache[key] = _parse_bool_env(env_value)
            if _per_server_cache[key]:
                logger.info(
                    "Local caching ENABLED for %s via %s=%s.",
                    server_name,
                    env_name,
                    env_value.strip(),
                )
        else:
            _per_server_cache[key] = False

    return _per_server_cache[key]


def reset_cache_config() -> None:
    """
    Reset all cached configuration state.

    Clears per-server resolved values so they will be re-evaluated
    from environment variables on next access.
    """
    _per_server_cache.clear()
