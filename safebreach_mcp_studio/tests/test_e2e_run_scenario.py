"""
End-to-End Tests for run_scenario (SAF-29967 — Slice 1: OOB Ready-to-Run)

Tests the complete scenario execution pipeline using real API calls.
Pattern: queue → wait for test start → wait for >5 simulations → cancel.

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
# E2E helpers — direct API calls, zero mocks
# ---------------------------------------------------------------------------


def _get_auth(console):
    """Get auth headers and base URLs for direct API calls."""
    apitoken = get_secret_for_console(console)
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
    return apitoken, account_id, headers


def _cancel_test(test_id, console):
    """Cancel a running/queued test via DELETE on the queue API. Best-effort."""
    try:
        apitoken, account_id, _ = _get_auth(console)
        base_url = get_api_base_url(console, 'orchestrator')
        api_url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}"
        response = requests.delete(api_url, headers={"x-apitoken": apitoken}, timeout=30)
        logger.info(f"Cancel test {test_id}: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"Failed to cancel test {test_id}: {e}")


def _get_simulation_count(test_id, console):
    """Get the count of completed simulations for a test via the Data API.

    Uses the executionsHistoryResults endpoint directly — works even for
    tests that haven't finished (partial results are available).
    """
    apitoken, account_id, headers = _get_auth(console)
    base_url = get_api_base_url(console, 'data')

    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"
    params = {
        "planRunId": test_id,
        "page": 1,
        "pageSize": 1,  # We only need the total count, not the data
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        # The total count is usually in a 'totalRecords' or pagination field
        if isinstance(data, dict):
            total = data.get('totalRecords', data.get('total', 0))
            if total:
                return total
            # Some APIs return the count in the items length
            items = data.get('data', data.get('items', data.get('results', [])))
            if isinstance(items, list) and len(items) > 0:
                # If we got data back, there are at least some simulations
                return len(items)
        elif isinstance(data, list):
            return len(data)
    except Exception as e:
        logger.debug(f"Error getting simulation count for {test_id}: {e}")
    return 0


def _wait_for_simulations(test_id, console, min_count=5, timeout=600):
    """Poll simulation count until at least min_count simulations exist.

    Uses direct Data API call to executionsHistoryResults endpoint.
    """
    start = time.time()
    while time.time() - start < timeout:
        count = _get_simulation_count(test_id, console)
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

            # Wait for at least 5 simulations to complete
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

            # Wait for at least 5 simulations to complete
            _wait_for_simulations(test_id, E2E_CONSOLE, min_count=5, timeout=600)

        finally:
            if test_id:
                _cancel_test(test_id, E2E_CONSOLE)
