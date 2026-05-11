"""Unit tests for rate_limiter module — Phase 1: total action limit + get_caller_identity."""

import pytest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError
from safebreach_mcp_core.rate_limiter import (
    RateLimiter,
    get_caller_identity,
    _rate_limit_store,
)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear shared rate limit state between tests."""
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


@pytest.fixture
def limiter():
    return RateLimiter()


# ---------------------------------------------------------------------------
# check_limit basics
# ---------------------------------------------------------------------------
class TestCheckLimitBasic:
    def test_check_limit_passes_when_count_is_zero(self, limiter):
        limiter.check_limit("caller-1", "manage_test")  # should not raise

    def test_check_limit_passes_when_count_below_total_limit(self, limiter):
        # Use different tool names to avoid per-tool limit (5) while testing total (10)
        for i in range(9):
            limiter.record_action("caller-1", f"tool_{i}")
        limiter.check_limit("caller-1", "manage_test")  # 9 < 10, should not raise

    def test_check_limit_raises_tool_error_when_total_limit_reached(self, limiter):
        for _ in range(10):
            limiter.record_action("caller-1", "manage_test")
        with pytest.raises(ToolError):
            limiter.check_limit("caller-1", "manage_test")

    def test_check_limit_does_not_increment_counters(self, limiter):
        limiter.record_action("caller-1", "manage_test")  # 1 action
        limiter.check_limit("caller-1", "manage_test")
        limiter.check_limit("caller-1", "manage_test")
        limiter.check_limit("caller-1", "manage_test")
        assert len(_rate_limit_store["caller-1"].total_actions) == 1


# ---------------------------------------------------------------------------
# record_action
# ---------------------------------------------------------------------------
class TestRecordAction:
    def test_record_action_increments_total_count(self, limiter):
        for _ in range(3):
            limiter.record_action("caller-1", "manage_test")
        assert len(_rate_limit_store["caller-1"].total_actions) == 3


# ---------------------------------------------------------------------------
# Sliding window
# ---------------------------------------------------------------------------
class TestSlidingWindow:
    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_sliding_window_prunes_expired_actions(self, mock_time, limiter):
        mock_time.time.return_value = 1000.0
        for _ in range(10):
            limiter.record_action("caller-1", "manage_test")

        # Advance past default 30-min window (1800s)
        mock_time.time.return_value = 1000.0 + 1801.0
        limiter.check_limit("caller-1", "manage_test")  # should not raise
        assert len(_rate_limit_store["caller-1"].total_actions) == 0


# ---------------------------------------------------------------------------
# Error message content
# ---------------------------------------------------------------------------
class TestErrorMessage:
    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_error_message_contains_total_actions_and_retry_after(
        self, mock_time, limiter
    ):
        mock_time.time.return_value = 1000.0
        for _ in range(10):
            limiter.record_action("caller-1", "manage_test")

        # 100s later — retry_after = 1800 - (1100 - 1000) = 1700
        mock_time.time.return_value = 1100.0
        with pytest.raises(ToolError, match="total actions") as exc_info:
            limiter.check_limit("caller-1", "manage_test")

        error_msg = str(exc_info.value)
        assert "10/10" in error_msg
        assert "1700" in error_msg


# ---------------------------------------------------------------------------
# Multiple callers
# ---------------------------------------------------------------------------
class TestMultipleCallers:
    def test_multiple_callers_are_independent(self, limiter):
        for _ in range(10):
            limiter.record_action("caller-a", "manage_test")
        with pytest.raises(ToolError):
            limiter.check_limit("caller-a", "manage_test")
        # caller-b should be unaffected
        limiter.check_limit("caller-b", "manage_test")  # should not raise


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class TestConfiguration:
    @patch("safebreach_mcp_core.rate_limiter._rate_limit_enabled", False)
    def test_disabled_check_limit_passes(self, limiter):
        for _ in range(15):
            limiter.record_action("caller-1", "manage_test")
        limiter.check_limit("caller-1", "manage_test")  # should not raise

    @patch("safebreach_mcp_core.rate_limiter._rate_limit_enabled", False)
    def test_disabled_record_action_is_noop(self, limiter):
        limiter.record_action("caller-1", "manage_test")
        assert "caller-1" not in _rate_limit_store

    @patch("safebreach_mcp_core.rate_limiter._action_limit", 3)
    def test_custom_action_limit(self, limiter):
        for _ in range(2):
            limiter.record_action("caller-1", "manage_test")
        limiter.check_limit("caller-1", "manage_test")  # 2 < 3, should pass

        limiter.record_action("caller-1", "manage_test")  # now 3
        with pytest.raises(ToolError):
            limiter.check_limit("caller-1", "manage_test")

    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_custom_window(self, mock_time, limiter):
        mock_time.time.return_value = 1000.0
        for _ in range(10):
            limiter.record_action("caller-1", "manage_test")

        # Advance past 60s window
        mock_time.time.return_value = 1061.0
        limiter.check_limit("caller-1", "manage_test")  # should not raise


# ---------------------------------------------------------------------------
# Per-tool-name limit (Phase 2)
# ---------------------------------------------------------------------------
class TestPerToolNameLimit:
    def test_check_limit_raises_when_per_tool_limit_reached(self, limiter):
        for _ in range(5):
            limiter.record_action("caller-1", "manage_test")
        with pytest.raises(ToolError, match="manage_test"):
            limiter.check_limit("caller-1", "manage_test")

    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_error_message_contains_tool_name_and_retry_after(
        self, mock_time, limiter
    ):
        mock_time.time.return_value = 1000.0
        for _ in range(5):
            limiter.record_action("caller-1", "manage_test")

        mock_time.time.return_value = 1100.0  # 100s later
        # retry_after = 1800 - (1100 - 1000) = 1700
        with pytest.raises(ToolError, match="manage_test") as exc_info:
            limiter.check_limit("caller-1", "manage_test")
        error_msg = str(exc_info.value)
        assert "5/5" in error_msg
        assert "1700" in error_msg

    def test_per_tool_limit_independent_from_total(self, limiter):
        """Hit per-tool limit (5) before total limit (10)."""
        for _ in range(5):
            limiter.record_action("caller-1", "manage_test")
        # Per-tool at 5/5, total at 5/10
        with pytest.raises(ToolError, match="manage_test"):
            limiter.check_limit("caller-1", "manage_test")

    def test_multiple_tool_names_tracked_independently(self, limiter):
        for _ in range(4):
            limiter.record_action("caller-1", "manage_test")
        for _ in range(4):
            limiter.record_action("caller-1", "run_scenario")
        # Both tools at 4, below per-tool limit of 5
        limiter.check_limit("caller-1", "manage_test")  # should not raise
        limiter.check_limit("caller-1", "run_scenario")  # should not raise

    @patch("safebreach_mcp_core.rate_limiter._identical_action_limit", 2)
    def test_custom_identical_action_limit(self, limiter):
        limiter.record_action("caller-1", "manage_test")
        limiter.check_limit("caller-1", "manage_test")  # 1 < 2, should pass
        limiter.record_action("caller-1", "manage_test")  # now 2
        with pytest.raises(ToolError):
            limiter.check_limit("caller-1", "manage_test")

    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_per_tool_window_pruning(self, mock_time, limiter):
        mock_time.time.return_value = 1000.0
        for _ in range(5):
            limiter.record_action("caller-1", "manage_test")
        # Advance past 60s window
        mock_time.time.return_value = 1061.0
        limiter.check_limit("caller-1", "manage_test")  # should not raise


# ---------------------------------------------------------------------------
# get_caller_identity
# ---------------------------------------------------------------------------
class TestGetCallerIdentity:
    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="test-session-123",
    )
    def test_returns_session_id_when_no_auth(self, _mock_session):
        assert get_caller_identity() == "test-session-123"

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value=None,
    )
    def test_returns_anonymous_when_neither_available(self, _mock_session):
        assert get_caller_identity() == "anonymous"
