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

    @patch("safebreach_mcp_core.rate_limiter._action_limit", 2)
    @patch("safebreach_mcp_core.rate_limiter._window_seconds", 60)
    def test_total_action_limit_enforced(self):
        """Pause (1) -> resume (2) -> cancel (3, rate-limited)."""
        scenario = _find_ready_scenario(E2E_CONSOLE)
        test_id = None
        try:
            # Queue a real test
            queue_result = sb_run_scenario(
                scenario_id=str(scenario["id"]),
                console=E2E_CONSOLE,
                test_name="E2E: rate_limit_total_action_test",
            )
            test_id = queue_result["test_id"]
            logger.info("Queued test %s for rate limit E2E", test_id)

            # Action 1: pause (should succeed)
            result = sb_manage_test(
                test_id=test_id,
                action="pause",
                console=E2E_CONSOLE,
                reason="E2E rate limit test - pause",
            )
            assert result["status"] == "success"

            time.sleep(1)

            # Action 2: resume (should succeed — hits limit of 2)
            result = sb_manage_test(
                test_id=test_id,
                action="resume",
                console=E2E_CONSOLE,
                reason="E2E rate limit test - resume",
            )
            assert result["status"] == "success"

            # Action 3: cancel (should be rate-limited)
            with pytest.raises(ToolError, match="total actions") as exc_info:
                sb_manage_test(
                    test_id=test_id,
                    action="cancel",
                    console=E2E_CONSOLE,
                    reason="E2E rate limit test - should fail",
                )

            error_msg = str(exc_info.value)
            assert "2/2" in error_msg
            # Verify retry-after seconds is present (a number)
            assert any(c.isdigit() for c in error_msg)
            logger.info("Rate limit correctly enforced: %s", error_msg)

        finally:
            if test_id:
                _cancel_test_best_effort(test_id, E2E_CONSOLE)
