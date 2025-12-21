"""
SafeBreach MCP Cache Configuration

This module provides centralized cache configuration for all MCP servers.
Caching is opt-in and controlled by the SB_MCP_ENABLE_LOCAL_CACHING environment variable.

By default, caching is DISABLED to prevent memory exhaustion in long-running servers.
Set SB_MCP_ENABLE_LOCAL_CACHING=true to enable caching.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Environment variable name for cache configuration
CACHE_ENV_VAR = "SB_MCP_ENABLE_LOCAL_CACHING"

# Cache state - evaluated once at module load time
_caching_enabled: bool | None = None


def is_caching_enabled() -> bool:
    """
    Check if local caching is enabled.

    Caching is controlled by the SB_MCP_ENABLE_LOCAL_CACHING environment variable.
    Valid true values: 'true', '1', 'yes', 'on' (case-insensitive)
    Default (if not set or any other value): False (caching disabled)

    Returns:
        bool: True if caching is enabled, False otherwise
    """
    global _caching_enabled

    if _caching_enabled is None:
        env_value = os.environ.get(CACHE_ENV_VAR, "").lower().strip()
        _caching_enabled = env_value in ("true", "1", "yes", "on")

        if _caching_enabled:
            logger.info(
                "Local caching ENABLED via %s=%s. "
                "Warning: This may lead to memory growth in long-running servers.",
                CACHE_ENV_VAR,
                env_value
            )
        else:
            logger.info(
                "Local caching DISABLED (default). Set %s=true to enable caching.",
                CACHE_ENV_VAR
            )

    return _caching_enabled


def reset_cache_config() -> None:
    """
    Reset the cache configuration state.

    This is primarily useful for testing where the environment variable
    may be modified between tests.
    """
    global _caching_enabled
    _caching_enabled = None
