"""
Per-caller rate limiting for MCP write operations.

Two-phase gate pattern:
  - check_limit(caller_id, tool_name): pre-check, raises ToolError if exceeded
  - record_action(caller_id, tool_name): post-success increment

Cross-server shared state via module-level dict (all servers in same process).
"""

import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

from mcp.server.fastmcp.exceptions import ToolError

from safebreach_mcp_core.token_context import (
    _get_session_id_from_mcp_ctx,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read at module load, patchable in tests)
# ---------------------------------------------------------------------------
_rate_limit_enabled: bool = os.environ.get(
    "SAFEBREACH_MCP_RATE_LIMIT_ENABLED", "true"
).strip().lower() in ("true", "1", "yes")

_action_limit: int = int(os.environ.get("SAFEBREACH_MCP_ACTION_LIMIT", "10"))

_identical_action_limit: int = int(
    os.environ.get("SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT", "5")
)

_window_seconds: int = (
    int(os.environ.get("SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES", "30")) * 60
)

# ---------------------------------------------------------------------------
# Shared state (cross-server via module-level dict)
# ---------------------------------------------------------------------------


@dataclass
class CallerRateLimitData:
    total_actions: List[float] = field(default_factory=list)
    per_tool_actions: Dict[str, List[float]] = field(default_factory=dict)
    last_activity: float = 0.0


_rate_limit_store: Dict[str, CallerRateLimitData] = {}


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------
class RateLimiter:
    """Sliding-window rate limiter with two-phase gate API."""

    def _prune(self, timestamps: List[float], now: float) -> List[float]:
        """Remove timestamps older than the sliding window."""
        cutoff = now - _window_seconds
        return [t for t in timestamps if t > cutoff]

    def check_limit(self, caller_id: str, tool_name: str) -> None:
        """Pre-check: verify counts are below limits. Raises ToolError if exceeded."""
        if not _rate_limit_enabled:
            return

        data = _rate_limit_store.get(caller_id)
        if data is None:
            return  # no actions recorded yet

        now = time.time()

        # Prune and update in-place
        data.total_actions = self._prune(data.total_actions, now)

        total_count = len(data.total_actions)
        if total_count >= _action_limit:
            oldest = data.total_actions[0]
            retry_after = math.ceil(_window_seconds - (now - oldest))
            raise ToolError(
                f"Rate limit exceeded: total actions "
                f"({total_count}/{_action_limit} in last "
                f"{_window_seconds // 60} min). "
                f"Try again in {retry_after} seconds."
            )

    def record_action(self, caller_id: str, tool_name: str) -> None:
        """Post-success: increment counters after action truly applied."""
        if not _rate_limit_enabled:
            return

        now = time.time()
        data = _rate_limit_store.get(caller_id)
        if data is None:
            data = CallerRateLimitData()
            _rate_limit_store[caller_id] = data

        data.total_actions.append(now)

        if tool_name not in data.per_tool_actions:
            data.per_tool_actions[tool_name] = []
        data.per_tool_actions[tool_name].append(now)

        data.last_activity = now

        logger.info(
            "Rate limit recorded: caller=%s... tool=%s total=%d per_tool=%d",
            caller_id[:8],
            tool_name,
            len(data.total_actions),
            len(data.per_tool_actions[tool_name]),
        )


# Module-level singleton
rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Caller identity helper
# ---------------------------------------------------------------------------
def get_caller_identity() -> str:
    """
    Hybrid caller identification.

    Phase 1: session ID only. Auth token hash added in Phase 5.
    """
    session_id = _get_session_id_from_mcp_ctx()
    if session_id:
        logger.debug("Caller identity from session: %s...", session_id[:8])
        return session_id

    logger.debug("Caller identity: anonymous (no session)")
    return "anonymous"
