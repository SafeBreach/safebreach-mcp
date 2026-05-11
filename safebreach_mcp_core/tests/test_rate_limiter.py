"""Unit tests for rate_limiter module."""

import asyncio

import pytest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError
from safebreach_mcp_core.rate_limiter import (
    RateLimiter,
    get_caller_identity,
    _rate_limit_store,
    cleanup_stale_rate_limits,
    start_rate_limit_cleanup,
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
    """Hybrid caller identity: auth token hash > session ID > anonymous."""

    # -- Auth token hash (highest priority) --

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="session-abc",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    def test_returns_apitoken_hash_when_auth_present(
        self, mock_auth_var, _mock_session
    ):
        mock_auth_var.get.return_value = {"x-apitoken": "my-secret-token"}
        result = get_caller_identity()
        # Should be SHA256[:16] of "my-secret-token", NOT the session ID
        import hashlib
        expected = hashlib.sha256("my-secret-token".encode()).hexdigest()[:16]
        assert result == expected

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="session-abc",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    def test_x_token_fallback_when_no_apitoken(self, mock_auth_var, _mock_session):
        mock_auth_var.get.return_value = {"x-token": "x-token-value"}
        import hashlib
        expected = hashlib.sha256("x-token-value".encode()).hexdigest()[:16]
        assert get_caller_identity() == expected

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="session-abc",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    def test_cookie_fallback_when_no_tokens(self, mock_auth_var, _mock_session):
        mock_auth_var.get.return_value = {"cookie": "X-Token=cookie-secret"}
        import hashlib
        expected = hashlib.sha256("cookie-secret".encode()).hexdigest()[:16]
        assert get_caller_identity() == expected

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="session-abc",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    def test_priority_apitoken_over_x_token(self, mock_auth_var, _mock_session):
        """x-apitoken wins over x-token when both present."""
        mock_auth_var.get.return_value = {
            "x-apitoken": "apitoken-val",
            "x-token": "xtoken-val",
        }
        import hashlib
        expected = hashlib.sha256("apitoken-val".encode()).hexdigest()[:16]
        assert get_caller_identity() == expected

    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    def test_hash_is_stable(self, mock_auth_var):
        """Same token always produces the same identity."""
        mock_auth_var.get.return_value = {"x-apitoken": "stable-token"}
        first = get_caller_identity()
        second = get_caller_identity()
        assert first == second

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value=None,
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._get_auth_from_mcp_request_ctx",
        return_value={"x-apitoken": "from-request-ctx"},
    )
    def test_mcp_request_ctx_fallback(
        self, _mock_req_ctx, mock_auth_var, _mock_session
    ):
        """Falls back to _get_auth_from_mcp_request_ctx when ContextVar is empty."""
        mock_auth_var.get.return_value = None
        import hashlib
        expected = hashlib.sha256("from-request-ctx".encode()).hexdigest()[:16]
        assert get_caller_identity() == expected

    # -- Session ID fallback --

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value="test-session-123",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._get_auth_from_mcp_request_ctx",
        return_value=None,
    )
    def test_returns_session_id_when_no_auth(
        self, _mock_req_ctx, mock_auth_var, _mock_session
    ):
        mock_auth_var.get.return_value = None
        assert get_caller_identity() == "test-session-123"

    # -- Anonymous fallback --

    @patch(
        "safebreach_mcp_core.rate_limiter._get_session_id_from_mcp_ctx",
        return_value=None,
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._user_auth_artifacts",
    )
    @patch(
        "safebreach_mcp_core.rate_limiter._get_auth_from_mcp_request_ctx",
        return_value=None,
    )
    def test_returns_anonymous_when_neither_available(
        self, _mock_req_ctx, mock_auth_var, _mock_session
    ):
        mock_auth_var.get.return_value = None
        assert get_caller_identity() == "anonymous"


# ---------------------------------------------------------------------------
# Stale entry cleanup
# ---------------------------------------------------------------------------
class TestCleanupStaleRateLimits:
    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_stale_entries_removed(self, mock_time, limiter):
        """Entries with last_activity older than TTL are evicted."""
        mock_time.time.return_value = 1000.0
        limiter.record_action("stale-caller", "manage_test")

        # Advance past 1-hour TTL (3600s)
        mock_time.time.return_value = 1000.0 + 3601.0
        removed = cleanup_stale_rate_limits()
        assert removed == 1
        assert "stale-caller" not in _rate_limit_store

    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_recent_entries_preserved(self, mock_time, limiter):
        """Entries with recent activity are kept."""
        mock_time.time.return_value = 1000.0
        limiter.record_action("active-caller", "manage_test")

        # Only 100s later — well within TTL
        mock_time.time.return_value = 1100.0
        removed = cleanup_stale_rate_limits()
        assert removed == 0
        assert "active-caller" in _rate_limit_store

    @patch("safebreach_mcp_core.rate_limiter.time")
    def test_mixed_callers_only_stale_removed(self, mock_time, limiter):
        """Only stale callers removed; active ones kept."""
        mock_time.time.return_value = 1000.0
        limiter.record_action("old-caller", "manage_test")

        mock_time.time.return_value = 5000.0
        limiter.record_action("new-caller", "manage_test")

        # At t=5000, old-caller last_activity=1000 (4000s ago > 3600 TTL)
        removed = cleanup_stale_rate_limits()
        assert removed == 1
        assert "old-caller" not in _rate_limit_store
        assert "new-caller" in _rate_limit_store


class TestStartRateLimitCleanup:
    @pytest.fixture(autouse=True)
    def reset_cleanup_flag(self):
        """Reset the singleton flag between tests."""
        import safebreach_mcp_core.rate_limiter as rl
        rl._cleanup_started = False
        yield
        rl._cleanup_started = False

    def test_singleton_only_starts_once(self):
        """Calling start_rate_limit_cleanup() twice returns same task."""
        async def _run():
            task1 = start_rate_limit_cleanup()
            task2 = start_rate_limit_cleanup()
            assert task1 is task2
            task1.cancel()

        asyncio.run(_run())
