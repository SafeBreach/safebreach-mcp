"""
End-to-End Tests for run_scenario (SAF-29967 — Slice 1: OOB Ready-to-Run)

Tests the complete scenario execution pipeline using real API calls.
Pattern: queue → wait for >5 simulations (filtered by test_id) → cancel.

ZERO MOCKS — all calls hit real SafeBreach APIs on pentest01.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import time
import logging
import pytest
import os
import requests

from safebreach_mcp_studio.studio_functions import (
    sb_run_scenario,
    compute_scenario_readiness,
    _fetch_all_scenarios,
    _fetch_all_plans,
)
from safebreach_mcp_data.data_functions import (
    sb_get_test_simulations,
    simulations_cache,
)
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


# ---------------------------------------------------------------------------
# E2E helpers — real API calls, zero mocks
# ---------------------------------------------------------------------------


def _cancel_test(test_id, console):
    """Cancel a running/queued test via DELETE on the queue API. Best-effort."""
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'orchestrator')
        account_id = get_api_account_id(console)
        api_url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}"
        response = requests.delete(api_url, headers={"x-apitoken": apitoken}, timeout=30)
        logger.info(f"Cancel test {test_id}: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to cancel test {test_id}: {e}")


def _get_simulation_count_for_test(test_id, console):
    """Get simulation count for a specific test using the Data Server function.

    Uses sb_get_test_simulations which POSTs to executionsHistoryResults
    with runId filter — correctly scoped to this test only.
    """
    try:
        simulations_cache.clear()  # Force fresh fetch
        result = sb_get_test_simulations(test_id=test_id, console=console, page_number=0)
        total = result.get('total_simulations', 0)
        return total
    except Exception as e:
        logger.debug(f"Error getting simulation count for {test_id}: {e}")
        return 0


def _wait_for_simulations(test_id, console, min_count=5, timeout=600):
    """Poll until at least min_count simulations exist for THIS specific test.

    Uses sb_get_test_simulations (Data Server) which filters by runId.
    """
    start = time.time()
    while time.time() - start < timeout:
        count = _get_simulation_count_for_test(test_id, console)
        if count >= min_count:
            logger.info(f"Test {test_id}: {count} simulations (>= {min_count})")
            return count
        logger.info(
            f"Test {test_id}: {count} simulations so far, "
            f"need {min_count} ({int(time.time() - start)}s elapsed)"
        )
        time.sleep(15)
    raise TimeoutError(
        f"Test {test_id} did not reach {min_count} simulations within {timeout}s"
    )


# ---------------------------------------------------------------------------
# E2E Tests
# ---------------------------------------------------------------------------


@skip_e2e
@pytest.mark.e2e
class TestRunScenarioE2E:
    """E2E tests for OOB scenario execution against real SafeBreach console."""

    def test_run_ready_oob_scenario(self):
        """Queue a ready-to-run OOB scenario, wait for simulations, then cancel."""
        # Find a ready-to-run scenario
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready_scenario = None
        for s in scenarios:
            if compute_scenario_readiness(s):
                ready_scenario = s
                break

        assert ready_scenario is not None, (
            f"No ready-to-run OOB scenario found on {E2E_CONSOLE}"
        )

        test_id = None
        try:
            # Queue the scenario
            result = sb_run_scenario(
                scenario_id=str(ready_scenario['id']),
                console=E2E_CONSOLE,
            )

            # Verify queue response
            test_id = result['test_id']
            assert test_id, "test_id should be non-empty"
            assert result['scenario_id'] == str(ready_scenario['id'])
            assert result['step_count'] > 0
            assert len(result['step_run_ids']) > 0
            assert result['status'] == 'queued'

            # Wait for at least 5 simulations to complete FOR THIS TEST
            _wait_for_simulations(test_id, E2E_CONSOLE, min_count=5, timeout=600)

        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)

    def test_run_scenario_not_found(self):
        """Non-existent scenario ID raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            sb_run_scenario(
                scenario_id="00000000-0000-0000-0000-000000000000",
                console=E2E_CONSOLE,
            )

    def test_run_scenario_not_ready(self):
        """Non-ready scenario raises ValueError (if one exists on the console)."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        not_ready_scenario = None
        for s in scenarios:
            if not compute_scenario_readiness(s):
                not_ready_scenario = s
                break

        if not_ready_scenario is None:
            pytest.skip("All scenarios on this console are ready-to-run")

        with pytest.raises(ValueError, match="not ready to run"):
            sb_run_scenario(
                scenario_id=str(not_ready_scenario['id']),
                console=E2E_CONSOLE,
            )

    def test_run_scenario_custom_name(self):
        """Custom test_name appears in the response."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready_scenario = None
        for s in scenarios:
            if compute_scenario_readiness(s):
                ready_scenario = s
                break

        assert ready_scenario is not None, (
            f"No ready-to-run OOB scenario found on {E2E_CONSOLE}"
        )

        custom_name = "E2E Test - Custom Name Verification"
        test_id = None
        try:
            result = sb_run_scenario(
                scenario_id=str(ready_scenario['id']),
                console=E2E_CONSOLE,
                test_name=custom_name,
            )

            test_id = result['test_id']
            assert test_id, "test_id should be non-empty"
            assert result['test_name'] == custom_name

            # Wait for at least 5 simulations to complete FOR THIS TEST
            _wait_for_simulations(test_id, E2E_CONSOLE, min_count=5, timeout=600)

        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)

    # --- Slice 2: Custom Plan E2E Tests ---

    def test_run_ready_custom_plan(self):
        """Queue a ready-to-run custom plan, wait for simulations, then cancel."""
        plans = _fetch_all_plans(E2E_CONSOLE)
        ready_plan = None
        for p in plans:
            if compute_scenario_readiness(p):
                ready_plan = p
                break

        assert ready_plan is not None, (
            f"No ready-to-run custom plan found on {E2E_CONSOLE}"
        )

        test_id = None
        try:
            result = sb_run_scenario(
                scenario_id=str(ready_plan['id']),
                console=E2E_CONSOLE,
            )

            test_id = result['test_id']
            assert test_id, "test_id should be non-empty"
            assert result['scenario_id'] == str(ready_plan['id'])
            assert result['scenario_name'] == ready_plan['name']
            assert result['step_count'] > 0
            assert result['status'] == 'queued'
            assert result['predicted_simulations'] > 0

            _wait_for_simulations(test_id, E2E_CONSOLE, min_count=5, timeout=600)

        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)
