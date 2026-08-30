"""
End-to-End Tests for get_plan_statistics (SAF-35508)

Scores real plans against a real console and checks the numbers are usable,
self-consistent, and explained by Core's own constraint catalog.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v

Note: this tool queues nothing and changes nothing, so these tests need no
cleanup epilogue.
"""

import json
import logging
import os

import pytest

from safebreach_mcp_studio.studio_functions import (
    sb_get_plan_statistics,
    _fetch_all_scenarios,
    _fetch_all_plans,
)

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


def _first_scenario_with_steps():
    """A real scenario carrying at least one step, discovered at runtime.

    Nothing is hardcoded: which scenarios exist is a property of the console.
    """
    try:
        scenarios = _fetch_all_scenarios(E2E_CONSOLE)
    except Exception as e:
        pytest.skip(f"Could not list scenarios on {E2E_CONSOLE}: {e}")

    for scenario in scenarios:
        if scenario.get('steps'):
            return scenario
    pytest.skip(f"No scenario on {E2E_CONSOLE} carries any steps.")


@skip_e2e
@pytest.mark.e2e
class TestPlanStatisticsE2E:
    """T-28, T-29, T-30, T-31, T-40 — the tool against a real console."""

    def test_ad_hoc_plan_returns_usable_numbers(self):
        """T-28 — a plan body that was never saved is scored and comes back usable."""
        scenario = _first_scenario_with_steps()
        plan = json.dumps({"name": "", "steps": scenario['steps'][:1]})

        result = sb_get_plan_statistics(console=E2E_CONSOLE, plan=plan)

        assert result['steps'], "a scored plan must return at least one step"
        step = result['steps'][0]
        assert isinstance(step['simulation_count'], int)
        for field in ('attacks', 'simulators', 'attacker_simulators', 'target_simulators'):
            assert isinstance(step[field], dict)
            assert all(v is None or isinstance(v, int) for v in step[field].values())

        # Every conflict references the catalog; none passes a bare code off as meaning.
        for conflict in step['conflicts']:
            assert conflict['code'] in result['constraint_catalog']
            assert 'description' not in conflict
        for code, entry in result['constraint_catalog'].items():
            assert entry['description'] != code

    def test_scenario_id_and_ad_hoc_body_agree(self):
        """T-29 — scoring by id agrees with scoring the same scenario's body."""
        scenario = _first_scenario_with_steps()

        by_id = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id']
        )
        ad_hoc = sb_get_plan_statistics(
            console=E2E_CONSOLE,
            plan=json.dumps({"name": "", "steps": scenario['steps']}),
        )

        # plan_step_count is None by design on the scenario_id path, so the
        # comparable facts are the returned count and the per-step numbers.
        assert by_id['returned_step_count'] == ad_hoc['returned_step_count']
        assert (
            [s['simulation_count'] for s in by_id['steps']]
            == [s['simulation_count'] for s in ad_hoc['steps']]
        )

    def test_custom_plan_integer_string_id_is_accepted(self):
        """T-29 — an integer-as-string plan id resolves as readily as a UUID."""
        try:
            plans = _fetch_all_plans(E2E_CONSOLE)
        except Exception as e:
            pytest.skip(f"Could not list custom plans on {E2E_CONSOLE}: {e}")
        if not plans:
            pytest.skip(f"Console '{E2E_CONSOLE}' has no custom plans to score.")

        result = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=str(plans[0]['id'])
        )

        assert 'steps' in result

    def test_runnable_never_exceeds_expected(self):
        """T-30 — the ordering relation, asserted unconditionally."""
        scenario = _first_scenario_with_steps()

        runnable = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id']
        )
        expected = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id'], include_disabled=True
        )

        pairs = list(zip(runnable['steps'], expected['steps']))
        assert pairs, "both calls must return steps to be comparable"
        for run_step, exp_step in pairs:
            if run_step['counts_computed'] and exp_step['counts_computed']:
                assert run_step['simulation_count'] <= exp_step['simulation_count']

    def test_offline_reason_explains_the_delta(self):
        """T-30 — the conditional half, skipped explicitly when the console cannot show it."""
        scenario = _first_scenario_with_steps()

        runnable = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id']
        )
        expected = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id'], include_disabled=True
        )

        # The unconditional claim is asserted before any skip, so a skip can
        # never stand in for a passing assertion.
        for run_step, exp_step in zip(runnable['steps'], expected['steps']):
            if run_step['counts_computed'] and exp_step['counts_computed']:
                assert run_step['simulation_count'] <= exp_step['simulation_count']

        deltas = [
            exp['simulation_count'] - run['simulation_count']
            for run, exp in zip(runnable['steps'], expected['steps'])
            if run['counts_computed'] and exp['counts_computed']
        ]
        offline_codes = {
            conflict['code']
            for step in runnable['steps'] for conflict in step['conflicts']
            if conflict['code'] == 'simulator_is_offline'
        }

        if not any(d > 0 for d in deltas) and not offline_codes:
            pytest.skip(
                f"Console '{E2E_CONSOLE}' has no disabled, unapproved or offline simulator: "
                f"every step's runnable simulation_count equals expected and no "
                f"simulator_is_offline conflict was reported. The delta and offline-reason "
                f"assertions require that precondition; the runnable <= expected ordering "
                f"relation was asserted above and holds."
            )

        assert any(d > 0 for d in deltas), (
            "an offline simulator was reported, so at least one step must differ"
        )
        assert offline_codes, "a positive delta must be explained by the offline reason"
        expected_offline = {
            conflict['code']
            for step in expected['steps'] for conflict in step['conflicts']
            if conflict['code'] == 'simulator_is_offline'
        }
        assert not expected_offline, (
            "expected counts score every simulator, so offline is never reported there"
        )

    def test_step_less_plan_yields_the_typed_error(self):
        """T-31 — the guard fires before the request; no raw 400 reaches the caller."""
        with pytest.raises(ValueError) as excinfo:
            sb_get_plan_statistics(console=E2E_CONSOLE, plan='{"steps": []}')

        message = str(excinfo.value)
        assert 'steps' in message.lower()
        assert '400' in message or 'NOT_ALLOWED' in message

    def test_real_console_supplies_the_descriptions(self):
        """T-40 — the only test that can falsify the relay design."""
        scenario = _first_scenario_with_steps()

        result = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id']
        )
        catalog = result['constraint_catalog']

        referenced = {
            conflict['code']
            for step in result['steps'] for conflict in step['conflicts']
        }
        if not referenced:
            pytest.skip(
                f"Scenario '{scenario['id']}' on console '{E2E_CONSOLE}' produced no "
                f"conflicts, so there is no catalog to check. The relay assertions require "
                f"at least one conflict."
            )

        # Unconditional: every referenced code has an entry, and no entry ever
        # echoes the code back as its own explanation.
        for code in referenced:
            assert code in catalog, f"conflict code {code} has no catalog entry"
            assert catalog[code]['description'] != code

        described = [c for c, e in catalog.items() if e['description']]
        if not described:
            pytest.skip(
                f"Console '{E2E_CONSOLE}' returned no constraintCatalog carrying a non-null "
                f"description — its orchestrator predates SAF-35568. The verbatim-relay "
                f"assertions require that precondition; the R11 degradation (conflicts "
                f"surfaced, every description null, key present) was asserted instead and holds."
            )

        for code in described:
            assert isinstance(catalog[code]['description'], str)
            assert catalog[code]['description'].strip()

    def test_catalog_is_scoped_to_referenced_codes(self):
        """T-40 — the catalog carries this response's codes, not the whole vocabulary."""
        scenario = _first_scenario_with_steps()

        result = sb_get_plan_statistics(
            console=E2E_CONSOLE, scenario_id=scenario['id']
        )

        referenced = {
            conflict['code']
            for step in result['steps'] for conflict in step['conflicts']
        }
        # Subset, not equality: a code on a suppressed limit-reached step is
        # referenced by nothing and so is correctly absent.
        assert set(result['constraint_catalog']) <= referenced or not referenced
        assert len(result['constraint_catalog']) < 97, (
            "the full vocabulary is 97 codes; the catalog must be scoped to this response"
        )
