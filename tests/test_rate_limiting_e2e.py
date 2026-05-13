"""E2E tests for rate limiting — requires real SafeBreach environment."""

import os
import time
import logging

import pytest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError
from safebreach_mcp_studio.studio_functions import (
    sb_run_scenario,
    sb_manage_test,
)
from safebreach_mcp_core.rate_limiter import _rate_limit_store

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get("E2E_CONSOLE", "pentest01")
SKIP_E2E_TESTS = os.environ.get("SKIP_E2E_TESTS", "false").lower() == "true"

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)",
)


def _cancel_test_best_effort(test_id: str, console: str) -> None:
    """Best-effort cleanup — cancel a queued/running test."""
    try:
        sb_manage_test(test_id=test_id, action="cancel", console=console)
    except Exception:
        pass


def _find_ready_scenario(console: str) -> dict:
    """Find a ready-to-run scenario on the console."""
    from safebreach_mcp_studio.studio_functions import (
        _fetch_all_scenarios,
        compute_scenario_readiness,
    )

    scenarios = _fetch_all_scenarios(console)
    ready = next((s for s in scenarios if compute_scenario_readiness(s)), None)
    assert ready is not None, f"No ready scenario found on {console}"
    return ready


@skip_e2e
@pytest.mark.e2e
class TestRateLimitingE2E:
    """E2E: verify total action limit on manage_test against a real console."""

    @pytest.fixture(autouse=True)
    def clear_rate_limit_store(self):
        _rate_limit_store.clear()
        yield
        _rate_limit_store.clear()

    @patch("safebreach_mcp_core.rate_limiter._action_limit", 3)
    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    def test_total_action_limit_enforced(self):
        """run_scenario (1) -> pause (2) -> resume (3, hits limit) -> cancel (rate-limited)."""
        scenario = _find_ready_scenario(E2E_CONSOLE)
        test_id = None
        try:
            # Queue a real test — action 1 (run_scenario records an action)
            queue_result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                test_name="E2E: rate_limit_total_action_test",
            )
            test_id = queue_result["test_id"]
            logger.info("Queued test %s for rate limit E2E", test_id)

            # Action 2: pause (should succeed)
            result = sb_manage_test(
                test_id=test_id,
                action="pause",
                console=E2E_CONSOLE,
                reason="E2E rate limit test - pause",
            )
            assert result["status"] == "success"

            time.sleep(1)

            # Action 3: resume (should succeed — hits limit of 3)
            result = sb_manage_test(
                test_id=test_id,
                action="resume",
                console=E2E_CONSOLE,
                reason="E2E rate limit test - resume",
            )
            assert result["status"] == "success"

            # Action 4: cancel (should be rate-limited)
            with pytest.raises(ToolError, match="total actions") as exc_info:
                sb_manage_test(
                    test_id=test_id,
                    action="cancel",
                    console=E2E_CONSOLE,
                    reason="E2E rate limit test - should fail",
                )

            error_msg = str(exc_info.value)
            assert "3/3" in error_msg
            # Verify retry-after seconds is present (a number)
            assert any(c.isdigit() for c in error_msg)
            logger.info("Rate limit correctly enforced: %s", error_msg)

        finally:
            if test_id:
                _cancel_test_best_effort(test_id, E2E_CONSOLE)

    @patch("safebreach_mcp_core.rate_limiter._identical_action_limit", 1)
    @patch("safebreach_mcp_core.rate_limiter._action_limit", 10)
    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    def test_per_tool_name_limit_enforced(self):
        """Call manage_test once OK, 2nd call hits per-tool limit of 1."""
        scenario = _find_ready_scenario(E2E_CONSOLE)
        test_id = None
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                test_name="E2E: rate_limit_per_tool_test",
            )
            test_id = queue_result["test_id"]

            # Action 1: pause (should succeed — hits per-tool limit of 1)
            result = sb_manage_test(
                test_id=test_id,
                action="pause",
                console=E2E_CONSOLE,
                reason="E2E per-tool rate limit test",
            )
            assert result["status"] == "success"

            time.sleep(1)

            # Action 2: resume (same tool, should be rate-limited)
            with pytest.raises(ToolError, match="manage_test") as exc_info:
                sb_manage_test(
                    test_id=test_id,
                    action="resume",
                    console=E2E_CONSOLE,
                    reason="E2E per-tool rate limit - should fail",
                )

            error_msg = str(exc_info.value)
            assert "1/1" in error_msg
            assert any(c.isdigit() for c in error_msg)

        finally:
            if test_id:
                _cancel_test_best_effort(test_id, E2E_CONSOLE)

    @patch("safebreach_mcp_core.rate_limiter._identical_action_limit", 1)
    @patch("safebreach_mcp_core.rate_limiter._action_limit", 10)
    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    def test_run_scenario_per_tool_limit_enforced(self):
        """run_scenario (1, hits per-tool limit of 1) -> 2nd run_scenario (rate-limited)."""
        scenario = _find_ready_scenario(E2E_CONSOLE)
        test_id = None
        try:
            # Action 1: run_scenario succeeds — hits per-tool limit of 1
            queue_result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                test_name="E2E: run_scenario_rate_limit_test",
            )
            test_id = queue_result["test_id"]
            assert queue_result["status"] == "queued"

            # Action 2: run_scenario again — same tool, should be rate-limited
            with pytest.raises(ToolError, match="run_scenario") as exc_info:
                sb_run_scenario(
                    scenario_id=str(scenario["id"]),
                    console=E2E_CONSOLE,
                    test_name="E2E: run_scenario_rate_limit_should_fail",
                )

            error_msg = str(exc_info.value)
            assert "1/1" in error_msg
            assert any(c.isdigit() for c in error_msg)
            logger.info("run_scenario rate limit correctly enforced: %s", error_msg)

        finally:
            if test_id:
                _cancel_test_best_effort(test_id, E2E_CONSOLE)

    @patch("safebreach_mcp_core.rate_limiter._identical_action_limit", 5)
    @patch("safebreach_mcp_core.rate_limiter._action_limit", 10)
    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    def test_run_scenario_dry_run_bypasses_rate_limit(self):
        """dry_run=True does not consume rate limit quota."""
        scenario = _find_ready_scenario(E2E_CONSOLE)
        # Multiple dry runs should all succeed — none count toward limit
        for i in range(3):
            result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                dry_run=True,
            )
            assert result["status"] == "dry_run", f"dry_run #{i+1} should succeed"

        # Real run should still work (no quota consumed by dry runs)
        test_id = None
        try:
            queue_result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                test_name="E2E: dry_run_bypass_test",
            )
            test_id = queue_result["test_id"]
            assert queue_result["status"] == "queued"
        finally:
            if test_id:
                _cancel_test_best_effort(test_id, E2E_CONSOLE)
