"""
SafeBreach MCP Cache Configuration

Centralized cache configuration for all MCP servers.
Caching is opt-in and controlled by environment variables:

Global toggle:
    SB_MCP_ENABLE_LOCAL_CACHING=true    Enable caching for all servers

Per-server overrides (take precedence over global):
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
CACHE_ENV_VAR = "SB_MCP_ENABLE_LOCAL_CACHING"
_SERVER_ENV_PREFIX = "SB_MCP_CACHE_"

_TRUTHY = frozenset(("true", "1", "yes", "on"))

# Cached resolved values
_caching_enabled: bool | None = None
_per_server_cache: dict[str, bool] = {}


def _parse_bool_env(value: str) -> bool:
    """Parse an env var string as boolean."""
    return value.lower().strip() in _TRUTHY


def is_caching_enabled(server_name: str | None = None) -> bool:
    """
    Check if local caching is enabled.

    When *server_name* is ``None`` (default), checks the global toggle only
    (backward compatible). When a server name is provided, checks the
    server-specific env var first, falling back to the global toggle.

    Args:
        server_name: Optional server identifier (e.g. "config", "data",
            "playbook", "studio"). Case-insensitive.

    Returns:
        True if caching is enabled for the given scope.
    """
    global _caching_enabled

    # Resolve global toggle (cached)
    if _caching_enabled is None:
        env_value = os.environ.get(CACHE_ENV_VAR, "")
        _caching_enabled = _parse_bool_env(env_value)

        if _caching_enabled:
            logger.info(
                "Local caching ENABLED via %s=%s. "
                "Warning: This may lead to memory growth in long-running servers.",
                CACHE_ENV_VAR,
                env_value.strip(),
            )
        else:
            logger.info(
                "Local caching DISABLED (default). Set %s=true to enable caching.",
                CACHE_ENV_VAR,
            )

    if server_name is None:
        return _caching_enabled

    # Per-server lookup (cached per server_name)
    key = server_name.lower()
    if key not in _per_server_cache:
        env_name = f"{_SERVER_ENV_PREFIX}{key.upper()}"
        env_value = os.environ.get(env_name)
        if env_value is not None:
            _per_server_cache[key] = _parse_bool_env(env_value)
        else:
            _per_server_cache[key] = _caching_enabled

    return _per_server_cache[key]


def reset_cache_config() -> None:
    """
    Reset all cached configuration state.

    Clears both the global toggle and per-server resolved values so they
    will be re-evaluated from environment variables on next access.
    """
    global _caching_enabled
    _caching_enabled = None
    _per_server_cache.clear()
