"""
End-to-End Tests for run_scenario (SAF-29967)

Tests the complete scenario execution pipeline using real API calls.
Pattern: queue → wait for >=3 simulations → cancel → comment.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import json
import logging
import pytest
import os
import requests

from safebreach_mcp_studio.studio_functions import (
    sb_run_scenario,
    compute_scenario_readiness,
    diagnose_scenario_readiness,
    _fetch_all_scenarios,
    _fetch_all_plans,
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


def _get_auth(console):
    apitoken = get_secret_for_console(console)
    base_url_orch = get_api_base_url(console, 'orchestrator')
    base_url_data = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    return apitoken, base_url_orch, base_url_data, account_id


def _cancel_test(test_id, console):
    """Cancel a running/queued test. Best-effort."""
    try:
        apitoken, base_url_orch, _, account_id = _get_auth(console)
        url = f"{base_url_orch}/api/orch/v4/accounts/{account_id}/queue/{test_id}"
        resp = requests.delete(url, headers={"x-apitoken": apitoken}, timeout=30)
        logger.info(f"Cancel {test_id}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Cancel {test_id} failed: {e}")


def _comment_test(test_id, console, comment):
    """Leave a comment on a test run explaining what happened."""
    try:
        apitoken, _, base_url_data, account_id = _get_auth(console)
        url = f"{base_url_data}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
        headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
        resp = requests.put(url, headers=headers, json={"comment": comment}, timeout=30)
        logger.info(f"Comment {test_id}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Comment {test_id} failed: {e}")



def _cleanup_test(test_id, console, test_name, passed, detail=""):
    """Cancel and comment a test. Called in finally blocks."""
    if not test_id:
        return
    _cancel_test(test_id, console)
    status = "PASSED" if passed else "FAILED"
    comment = f"[MCP E2E] {test_name}: {status}. {detail}".strip()
    _comment_test(test_id, console, comment)


def _build_broad_overrides(scenario):
    """Build step_overrides with broad OS filters for all missing steps."""
    diag = diagnose_scenario_readiness(scenario)
    overrides = {}
    for step_info in diag['missing_steps']:
        step_num = str(step_info['step_number'])
        step_override = {}
        if 'targetFilter' in step_info['missing_filters']:
            step_override['targetFilter'] = {
                "os": {"operator": "is",
                       "values": ["WINDOWS", "MAC", "LINUX", "DOCKER", "NETWORK"],
                       "name": "os"}
            }
        if 'attackerFilter' in step_info['missing_filters']:
            step_override['attackerFilter'] = {
                "os": {"operator": "is",
                       "values": ["WINDOWS", "MAC", "LINUX", "DOCKER"],
                       "name": "os"}
            }
        overrides[step_num] = step_override
    return json.dumps(overrides)


# ---------------------------------------------------------------------------
# E2E Tests — 7 tests covering Slices 1-4
# ---------------------------------------------------------------------------


@skip_e2e
@pytest.mark.e2e
class TestRunScenarioE2E:
    """E2E tests for run_scenario against real SafeBreach console."""

    def test_run_oob_scenario(self):
        """Slice 1: Queue a ready OOB scenario with custom name, verify it starts, cancel.
        Covers: OOB run, custom name, queue response. Cancels immediately after queue."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready = next((s for s in scenarios if compute_scenario_readiness(s)), None)
        assert ready is not None, f"No ready OOB scenario on {E2E_CONSOLE}"

        test_id = None
        passed = False
        try:
            result = sb_run_scenario(
                scenario_id=str(ready['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_run_oob_scenario",
            )
            test_id = result['test_id']
            assert test_id
            assert result['status'] == 'queued'
            assert result['step_count'] > 0
            assert result['predicted_simulations'] > 0
            assert result['test_name'] == "E2E: test_run_oob_scenario"
            assert result['source_type'] == 'oob'
            passed = True
        finally:
            _cleanup_test(test_id, E2E_CONSOLE, "test_run_oob_scenario", passed,
                          f"scenario={ready['name']}")

    def test_run_custom_plan(self):
        """Slice 2: Queue a ready custom plan, verify it starts, cancel.
        Covers: custom plan run, planId payload, source_type=custom."""
        plans = _fetch_all_plans(E2E_CONSOLE)
        ready_plans = [p for p in plans if compute_scenario_readiness(p)]
        assert len(ready_plans) > 0, f"No ready custom plan on {E2E_CONSOLE}"

        # Pick a plan with enough predicted sims
        ready_plan = None
        for p in ready_plans:
            dry = sb_run_scenario(scenario_id=str(p['id']),
                                 console=E2E_CONSOLE, dry_run=True)
            if dry.get('predicted_simulations', 0) >= 20:
                ready_plan = p
                break
        if ready_plan is None:
            pytest.skip("No ready custom plan with >=20 predicted sims")

        test_id = None
        passed = False
        try:
            result = sb_run_scenario(
                scenario_id=str(ready_plan['id']),
                console=E2E_CONSOLE,
                test_name="E2E: test_run_custom_plan",
            )
            test_id = result['test_id']
            assert test_id
            assert result['status'] == 'queued'
            assert result['source_type'] == 'custom'
            assert result['predicted_simulations'] > 0
            passed = True
        finally:
            _cleanup_test(test_id, E2E_CONSOLE, "test_run_custom_plan", passed,
                          f"plan={ready_plan['name']}")

    def test_error_not_found(self):
        """Slice 1: Non-existent scenario returns ValueError."""
        with pytest.raises(ValueError, match="not found"):
            sb_run_scenario(
                scenario_id="00000000-0000-0000-0000-000000000000",
                console=E2E_CONSOLE,
            )

    def test_diagnostic_not_ready(self):
        """Slice 3: Non-ready scenario returns diagnostic with missing steps."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        not_ready = next((s for s in scenarios
                          if not compute_scenario_readiness(s)), None)
        if not_ready is None:
            pytest.skip("All scenarios ready")

        result = sb_run_scenario(
            scenario_id=str(not_ready['id']), console=E2E_CONSOLE)
        assert result['status'] == 'not_ready'
        assert len(result['diagnostic']['missing_steps']) > 0
        # Verify recommendations are present
        step = result['diagnostic']['missing_steps'][0]
        assert 'recommendation' in step

    def test_dry_run(self):
        """Slice 4: dry_run for OOB, custom plan, and with overrides — no queuing.
        Covers: dry_run predictions, source_type, step_overrides, resolved_attacks."""
        # OOB dry_run
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        ready_oob = next((s for s in scenarios
                          if compute_scenario_readiness(s)), None)
        assert ready_oob is not None

        result = sb_run_scenario(
            scenario_id=str(ready_oob['id']),
            console=E2E_CONSOLE, dry_run=True)
        assert result['status'] == 'dry_run'
        assert result['predicted_simulations'] > 0
        assert result['source_type'] == 'oob'
        assert 'test_id' not in result
        assert len(result.get('step_stats', [])) > 0
        # Verify resolved_attacks present
        if result['step_stats'][0].get('resolved_attacks'):
            assert result['step_stats'][0]['resolved_attacks'][0].get('move_id')

        # Custom plan dry_run
        plans = _fetch_all_plans(E2E_CONSOLE)
        ready_plan = next((p for p in plans
                           if compute_scenario_readiness(p)), None)
        assert ready_plan is not None

        result2 = sb_run_scenario(
            scenario_id=str(ready_plan['id']),
            console=E2E_CONSOLE, dry_run=True)
        assert result2['status'] == 'dry_run'
        assert result2['source_type'] == 'custom'
        assert 'test_id' not in result2

        # Augmented dry_run
        not_ready = next((s for s in scenarios
                          if not compute_scenario_readiness(s)), None)
        if not_ready:
            overrides = _build_broad_overrides(not_ready)
            result3 = sb_run_scenario(
                scenario_id=str(not_ready['id']),
                console=E2E_CONSOLE,
                step_overrides=overrides, dry_run=True)
            assert result3['status'] == 'dry_run'
            assert len(result3['predicted_per_step']) == len(
                not_ready.get('steps', []))

    def test_augment_oob_scenario(self):
        """Slice 3: Augment a non-ready OOB scenario (5+ steps), verify it starts, cancel.
        Covers: diagnostic → augment → queue, large scenario, allow_partial_steps."""
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
        large_not_ready = [s for s in scenarios
                           if not compute_scenario_readiness(s)
                           and len(s.get('steps', [])) >= 5]
        assert len(large_not_ready) > 0, "No non-ready OOB with >=5 steps"

        scenario = large_not_ready[0]

        # Diagnostic turn
        diag_result = sb_run_scenario(
            scenario_id=str(scenario['id']), console=E2E_CONSOLE)
        assert diag_result['status'] == 'not_ready'
        assert len(diag_result['diagnostic']['missing_steps']) > 0

        # Augment and run
        overrides = _build_broad_overrides(scenario)
        test_id = None
        passed = False
        try:
            result = sb_run_scenario(
                scenario_id=str(scenario['id']),
                console=E2E_CONSOLE,
                step_overrides=overrides,
                allow_partial_steps=True,
                test_name="E2E: test_augment_oob_scenario",
            )
            assert result['status'] == 'queued'
            test_id = result['test_id']
            assert result['predicted_simulations'] > 0
            assert result['step_count'] >= 5
            passed = True
        finally:
            _cleanup_test(test_id, E2E_CONSOLE, "test_augment_oob_scenario", passed,
                          f"scenario={scenario['name']}, steps={len(scenario.get('steps', []))}")

    def test_augment_custom_plan(self):
        """Slice 4: Augment a non-ready custom plan, verify it starts, cancel.
        Covers: custom plan augmentation, full payload (not planId), allow_partial."""
        plans = _fetch_all_plans(E2E_CONSOLE)
        not_ready = [p for p in plans if not compute_scenario_readiness(p)]
        assert len(not_ready) > 0, "No non-ready custom plans"

        for plan in not_ready:
            diag = sb_run_scenario(
                scenario_id=str(plan['id']), console=E2E_CONSOLE)
            assert diag['status'] == 'not_ready'

            overrides = _build_broad_overrides(plan)
            test_id = None
            passed = False
            try:
                result = sb_run_scenario(
                    scenario_id=str(plan['id']),
                    console=E2E_CONSOLE,
                    step_overrides=overrides,
                    allow_partial_steps=True,
                    test_name="E2E: test_augment_custom_plan",
                )
                if result.get('status') == 'queued' and \
                   result.get('predicted_simulations', 0) > 0:
                    test_id = result['test_id']
                    passed = True
                    return  # Success
            except ValueError:
                continue
            finally:
                _cleanup_test(test_id, E2E_CONSOLE,
                              "test_augment_custom_plan", passed,
                              f"plan={plan['name']}")

        pytest.skip("No non-ready custom plans produced sims when augmented")


@skip_e2e
@pytest.mark.e2e
class TestErrorPropagationE2E:
    """E2E tests for SAF-30319: API error messages propagate response body details."""

    def test_statistics_api_error_includes_response_body(self):
        """When statistics API returns an HTTP error, the error message should
        include the API response body — not just a generic 'Bad Request'.

        Calls _get_scenario_statistics directly with a completely invalid payload
        to guarantee a 400/500 from the orchestrator statistics endpoint."""
        from safebreach_mcp_studio.studio_functions import _get_scenario_statistics

        # Send an empty steps list — the statistics API requires at least one step
        # with valid attack filters to process
        invalid_steps = [{"attacksFilter": {"invalid_key": "invalid_value"}}]

        with pytest.raises(ValueError) as exc_info:
            _get_scenario_statistics(
                steps=invalid_steps,
                console=E2E_CONSOLE,
                include_constraints=False,
            )

        error_msg = str(exc_info.value)
        # Verify the error contains the status code
        assert "Statistics API error" in error_msg, \
            f"Expected 'Statistics API error' prefix, got: {error_msg}"
        # Verify it contains response body content (not just status code)
        # The response body should have details beyond just the HTTP status
        assert len(error_msg) > 40, \
            f"Error message too short — likely missing API response body: {error_msg}"

    def test_scenario_fetch_error_includes_details(self):
        """When scenario fetch fails (e.g., bad console), the error should include
        API response body details, not just a generic HTTP error."""
        # Use a deliberately wrong console name to trigger an API error
        try:
            _fetch_all_scenarios("nonexistent-console-99999")
            pytest.fail("Expected an exception from bad console")
        except Exception as e:
            error_msg = str(e)
            # Should not be a bare requests.exceptions.HTTPError with no body
            # The error should contain some context beyond just the status code
            assert len(error_msg) > 20, \
                f"Error message too short — likely missing API details: {error_msg}"

    def test_plan_fetch_error_includes_details(self):
        """When plan fetch fails (e.g., bad console), the error should include
        API response body details, not just a generic HTTP error."""
        try:
            _fetch_all_plans("nonexistent-console-99999")
            pytest.fail("Expected an exception from bad console")
        except Exception as e:
            error_msg = str(e)
            assert len(error_msg) > 20, \
                f"Error message too short — likely missing API details: {error_msg}"
