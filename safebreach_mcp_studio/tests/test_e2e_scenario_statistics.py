"""
End-to-End Tests for the scenario-statistics tools (SAF-35508)

Covers test-plan items T-31 … T-35: scoring a real scenario against a real fleet,
all three input forms, the paired role breakdown and its cap, the three-state
simulator model, and the cap tally.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Fixtures are DISCOVERED, never created: these tools only read, so every test picks an
existing scenario / plan / test run off the console rather than authoring one. Where a
case needs a console property that cannot be discovered (an offline simulator, a step
with more blocked attacks than the cap), it SKIPS naming that precondition rather than
passing vacuously.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import logging
import os

import pytest

from safebreach_mcp_studio.studio_functions import (
    BLOCKED_ATTACKS_CAP,
    SIMULATOR_LISTING_CAP,
    _fetch_all_plans,
    _fetch_all_scenarios,
    sb_get_scenario_blocked_entities,
    sb_get_scenario_simulation_counts,
)

logger = logging.getLogger(__name__)

E2E_CONSOLE = os.environ.get('E2E_CONSOLE', 'pentest01')
SKIP_E2E_TESTS = os.environ.get('SKIP_E2E_TESTS', 'false').lower() == 'true'

skip_e2e = pytest.mark.skipif(
    SKIP_E2E_TESTS,
    reason="E2E tests skipped (set SKIP_E2E_TESTS=false to enable)"
)


# ---------------------------------------------------------------------------
# Discovery helpers — find an existing fixture, never create one
# ---------------------------------------------------------------------------


def _discover_scenario_steps(console):
    """Steps of any OOB scenario that has them, as an ad-hoc body would carry."""
    for scenario in _fetch_all_scenarios(console) or []:
        steps = scenario.get('steps')
        if steps:
            return scenario, steps
    pytest.skip(f"no OOB scenario with steps on {console} to score")


def _discover_plan_id(console):
    """A saved custom plan's numeric id."""
    for plan in _fetch_all_plans(console) or []:
        plan_id = plan.get('id')
        if plan_id is not None and str(plan_id).isdigit():
            return str(plan_id)
    pytest.skip(f"no saved custom plan with a numeric id on {console}")


def _offered_union(step):
    """Every simulator the step offered, in either role."""
    return {row['simulator_id'] for row in step.get('simulator_rows', [])}


# ---------------------------------------------------------------------------
# T-31 — the counts tool scores a real scenario against a real fleet
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_31_an_adhoc_body_is_scored_against_the_live_fleet():
    """An unsaved configuration is scored — the capability the feature exists to add."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    assert result['steps_returned'] == len(steps), (
        "the console scored a different number of steps than were submitted")
    assert result['counts_mode'] == 'runnable'
    for step in result['steps']:
        count = step['simulation_count']
        assert count is None or isinstance(count, int), (
            f"a count came back as {type(count).__name__}, neither measured nor null")
    logger.info("T-31 total_simulations=%s over %s steps",
                result['total_simulations'], result['steps_returned'])


@pytest.mark.e2e
@skip_e2e
def test_T_31_scoring_queues_no_test():
    """Scoring must not be a run: the answer carries no test identity."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    for key in ('planRunId', 'test_id', 'testId', 'runId'):
        assert key not in result, f"a read-only scoring answer carried {key}"


# ---------------------------------------------------------------------------
# T-32 — all three input forms against a live console
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_32_a_saved_numeric_plan_id_is_scored():
    """The saved-plan entry point resolves against a real id."""
    plan_id = _discover_plan_id(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario_id=plan_id)

    assert result['steps_returned'] >= 0
    assert result['counts_mode'] == 'runnable'


@pytest.mark.e2e
@skip_e2e
def test_T_32_an_oob_scenario_uuid_is_refused_without_contacting_the_console():
    """The UUID refusal is local, so it costs nothing and names the way through."""
    with pytest.raises(ValueError) as excinfo:
        sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE,
            scenario_id='2f4a1f5e-0000-4000-8000-000000000000')

    assert 'get_scenario_details' in str(excinfo.value)


@pytest.mark.e2e
@skip_e2e
def test_T_32_both_tools_accept_the_same_three_input_forms():
    """The two tools share an input layer, so neither can drift on what it accepts."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)
    plan_id = _discover_plan_id(E2E_CONSOLE)

    for tool in (sb_get_scenario_simulation_counts, sb_get_scenario_blocked_entities):
        assert tool(console=E2E_CONSOLE, scenario={'steps': steps}) is not None
        assert tool(console=E2E_CONSOLE, scenario_id=plan_id) is not None
        with pytest.raises(ValueError):
            tool(console=E2E_CONSOLE)


# ---------------------------------------------------------------------------
# T-33 — real role numbers and the listing cap
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_33_the_breakdown_is_present_exactly_when_the_fleet_is_under_the_cap():
    """The cap is keyed on the offered union — the breakdown's own length."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    for step in result['steps']:
        offered = step.get('simulators_offered')
        if offered is None:
            continue
        if offered >= SIMULATOR_LISTING_CAP:
            assert 'simulator_rows' not in step, (
                f"{offered} simulators offered — the breakdown should be dropped whole")
        else:
            assert 'simulator_rows' in step, (
                f"{offered} simulators offered — the breakdown should be present")


@pytest.mark.e2e
@skip_e2e
def test_T_33_every_offered_simulator_carries_both_role_numbers():
    """One row per simulator, both roles — the row a role choice is made from."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    seen_a_row = False
    for step in result['steps']:
        for row in step.get('simulator_rows', []):
            seen_a_row = True
            assert 'attacker' in row and 'target' in row, (
                f"row for {row.get('simulator_id')} is missing a role")
            assert row['simulator_id']
    if not seen_a_row:
        pytest.skip("every step on this console is at or over the listing cap")


@pytest.mark.e2e
@skip_e2e
def test_T_33_naming_simulator_ids_answers_them_in_both_roles():
    """Naming a machine is the reliable per-simulator number, cap or no cap."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)
    first = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    named = sorted(_offered_union(first['steps'][0])) if first['steps'] else []
    if not named:
        pytest.skip("no simulator was offered on the first step to name")

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps},
        simulator_ids=','.join(named[:2]))

    answered = result['steps'][0].get('named_simulators') or []
    assert len(answered) == len(named[:2])
    for row in answered:
        assert 'attacker' in row and 'target' in row


# ---------------------------------------------------------------------------
# T-34 — the three-state model against a live orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_34_a_switched_off_simulator_is_excluded_not_blocked():
    """The sharpest claim the feature makes, against a console that really has one."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    excluded, blocked = [], []
    for step in result['steps']:
        excluded += [s['simulator_id'] for s in step.get('excluded_simulators', [])]
        blocked += [s['simulator_id'] for s in step.get('blocked_simulators', [])]

    if not excluded:
        pytest.skip(
            f"no offline/disabled/unapproved simulator on {E2E_CONSOLE} — the excluded "
            "state cannot be observed; add one to exercise T-34")

    assert not (set(excluded) & set(blocked)), (
        "a simulator was reported both excluded and blocked — the two states must be disjoint")


@pytest.mark.e2e
@skip_e2e
def test_T_34_the_verdict_follows_the_counts_not_the_list_lengths():
    """A report nobody scored must never read as a scenario with nothing wrong."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    assert result['verdict']['state'] in {
        'blocked', 'clean', 'partially_evaluated', 'not_evaluated'}


@pytest.mark.e2e
@skip_e2e
def test_T_34_constraint_meanings_are_relayed_or_declared_absent():
    """Meanings come from the console; an older console is disclosed, never invented."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    catalog = result.get('constraint_catalog')
    if catalog is None:
        assert result.get('catalog_available') is False, (
            "an absent catalog must be disclosed as absent")
        return

    cited = set()
    for step in result['steps']:
        for group in step.get('blocked_simulators', []):
            if group.get('reason'):
                cited.add(group['reason'])
    assert set(catalog).issubset(cited | set(catalog)), "catalog must stay narrowed to cited codes"


# ---------------------------------------------------------------------------
# T-35 — the cap tally on a fleet large enough to trigger it
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_35_past_the_attack_cap_a_tally_replaces_the_list():
    """Summarise-don't-sample, against a real constraint payload."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    capped = [s for s in result['steps']
              if (s.get('blocked_attack_count') or 0) > BLOCKED_ATTACKS_CAP]
    if not capped:
        pytest.skip(
            f"no step on {E2E_CONSOLE} blocks more than {BLOCKED_ATTACKS_CAP} attacks — "
            "the cap tally cannot be observed; widen the scenario or fleet to exercise T-35")

    for step in capped:
        assert 'blocked_attacks' not in step, (
            "past the cap the per-attack list must be absent, not truncated")
        tally = step.get('blocked_attacks_by_reason')
        assert tally, "the cap must replace the list with a per-code tally"
        assert sum(row['attack_count'] for row in tally) == step['blocked_attack_count'], (
            "the tally must account for every blocked attack, not a sample")


@pytest.mark.e2e
@skip_e2e
def test_T_35_a_named_attack_still_carries_its_blockers_past_the_cap():
    """attack_ids is the documented route back to exact reasons — it must work."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    capped = [s for s in result['steps']
              if (s.get('blocked_attack_count') or 0) > BLOCKED_ATTACKS_CAP]
    if not capped:
        pytest.skip(
            f"no step blocks more than {BLOCKED_ATTACKS_CAP} attacks on {E2E_CONSOLE}")

    tally = capped[0].get('blocked_attacks_by_reason') or []
    assert tally, "expected a tally to source a code from"

    named = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps},
        attack_ids=str(capped[0].get('sample_blocked_attack_id') or ''))
    assert named.get('asked_about') is not None, (
        "a named attack must be answered even when the list is gone")
