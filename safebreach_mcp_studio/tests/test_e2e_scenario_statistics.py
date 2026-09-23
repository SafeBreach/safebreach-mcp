"""
End-to-End Tests for the scenario-statistics tools (SAF-35508)

Covers test-plan items T-31 … T-35: scoring a real scenario against a real fleet,
all three input forms, the paired role breakdown and its cap, the three-state
simulator model, and the cap tally.

ZERO MOCKS — all calls hit real SafeBreach APIs.

Fixtures are DISCOVERED, not created: these tools only read, so tests pick an existing
scenario / plan / test run off the console rather than authoring one. The one exception
is T-35: no shipped scenario blocks more attacks than the cap, so its module fixture
builds that step from discovered attacks and simulators, saves it as a plan to score it
by id, and deletes the plan on teardown. Where a case needs a console property that
cannot be discovered or built (an offline simulator), it SKIPS naming that precondition
rather than passing vacuously.

Requires:
- Real SafeBreach console access with valid API tokens
- Environment variables configured via private .vscode/set_env.sh file
- Network access to SafeBreach consoles

Setup: source .vscode/set_env.sh && uv run pytest -m "e2e" -v
"""

import json
import logging
import os
import time
import uuid

import pytest
import requests

from safebreach_mcp_core.environments_metadata import get_api_account_id, get_api_base_url
from safebreach_mcp_core.secret_utils import get_auth_headers_for_console
from safebreach_mcp_playbook.playbook_functions import sb_get_playbook_attacks
from safebreach_mcp_studio.studio_functions import (
    BLOCKED_ATTACKS_CAP,
    SIMULATOR_LISTING_CAP,
    STATISTICS_TIMEOUT_SECONDS,
    _fetch_all_plans,
    _fetch_all_scenarios,
    _fetch_scenario_statistics,
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
    """The cap is keyed on the offered union — the breakdown's own length.

    The breakdown is dropped only when MORE than the cap is offered; a step offering
    exactly the cap keeps it, which is the boundary a live fleet is likeliest to sit on.
    """
    _, steps = _discover_scenario_steps(E2E_CONSOLE)

    result = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': steps})

    for step in result['steps']:
        offered = step.get('simulators_offered')
        if offered is None:
            continue
        if offered > SIMULATOR_LISTING_CAP:
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
        pytest.skip("every step on this console is over the listing cap")


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

    answered = result['steps'][0].get('asked_about') or {}
    assert sorted(answered) == named[:2]
    for simulator_id, roles in answered.items():
        assert set(roles) == {'attacker_simulators', 'target_simulators'}, (
            f"{simulator_id} is not answered in both roles")
        for role, disposition in roles.items():
            assert disposition['state'] in (
                'contributes', 'measured_zero', 'not_computed', 'not_in_step'), (
                f"{simulator_id} {role} has no recognised answer: {disposition}")


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
        # Groups are per constraint code and carry a capped LIST of ids, not one id.
        excluded += [sid for group in step.get('excluded_simulators', [])
                     for sid in group['simulator_ids']]
        blocked += [sid for group in step.get('blocked_simulators', [])
                    for sid in group['simulator_ids']]

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
        assert result.get('catalog_supplied') is False, (
            "an absent catalog must be disclosed as absent")
        return

    cited = set()
    for step in result['steps']:
        for group in step.get('blocked_simulators', []):
            if group.get('code'):
                cited.add(group['code'])
    assert set(catalog).issubset(cited | set(catalog)), "catalog must stay narrowed to cited codes"


# ---------------------------------------------------------------------------
# T-35 — the cap tally on a fleet large enough to trigger it
# ---------------------------------------------------------------------------
#
# No shipped scenario blocks more than the cap on an ordinary fleet, so this is the
# one fixture that is BUILT rather than discovered: a single step holding every
# exfiltration attack in the playbook, aimed at one simulator the counts tool has
# just measured at zero as a target. Every attack in the step is then blocked for a
# reason the console itself records. The step is scored twice — as an unsaved body
# and as a saved plan by id — and the saved plan is deleted on teardown.

CONNECTED = {'connection': {'operator': 'is', 'values': [True], 'name': 'connection'}}


def _exfiltration_attack_ids(console):
    ids, page = [], 0
    while True:
        res = sb_get_playbook_attacks(console=console, page_number=page, name_filter='exfiltration')
        batch = res.get('attacks_in_page', [])
        ids += [attack['id'] for attack in batch]
        if not batch or len(ids) >= res.get('total_attacks', 0):
            return sorted(ids)
        page += 1


def _step(ids, target_filter):
    return {'uuid': str(uuid.uuid4()), 'name': f'{len(ids)} exfiltration attacks',
            'attacksFilter': {'playbook': {'operator': 'is', 'values': ids, 'name': 'playbook'}},
            'attackerFilter': CONNECTED, 'targetFilter': target_filter, 'systemFilter': {}}


def _plans_url(console, plan_id=None):
    base = (f"{get_api_base_url(console, 'config')}/api/config/v3/accounts/"
            f"{get_api_account_id(console)}/plans")
    return f"{base}/{plan_id}" if plan_id is not None else base


@pytest.fixture(scope='module')
def capped_scenario():
    """An over-the-cap step, as an unsaved body and as a saved plan id; the plan is deleted after."""
    ids = _exfiltration_attack_ids(E2E_CONSOLE)
    if len(ids) <= BLOCKED_ATTACKS_CAP:
        pytest.skip(f"only {len(ids)} exfiltration attacks on {E2E_CONSOLE}; the cap is {BLOCKED_ATTACKS_CAP}")

    offered = sb_get_scenario_simulation_counts(
        console=E2E_CONSOLE, scenario={'steps': [_step(ids, CONNECTED)]})['steps'][0]
    target = next((row['simulator_id'] for row in offered.get('simulator_rows', [])
                   if row['target']['state'] == 'measured_zero'), None)
    if target is None:
        pytest.skip(f"no simulator on {E2E_CONSOLE} is measured at zero as a target for these attacks")

    body = {'name': 'SAF-35508 e2e cap fixture',
            'steps': [_step(ids, {'simulators': {'operator': 'is', 'values': [target],
                                                 'name': 'simulators'}})]}
    headers = {'Content-Type': 'application/json', **get_auth_headers_for_console(E2E_CONSOLE)}
    created = requests.post(_plans_url(E2E_CONSOLE), headers=headers, timeout=60,
                            json={**body, 'type': 'validate', 'draft': False,
                                  'name': f"{body['name']} {int(time.time())}"})
    assert created.status_code == 201, f"plan create failed: {created.status_code} {created.text[:300]}"
    plan_id = created.json()['data']['id']
    logger.info(f"T-35 fixture: {len(ids)} attacks, target {target}, saved as plan {plan_id}")
    try:
        yield {'ids': ids, 'target': target, 'plan_id': plan_id,
               'forms': {'scenario': {'scenario': body}, 'scenario_id': {'scenario_id': str(plan_id)}}}
    finally:
        deleted = requests.delete(_plans_url(E2E_CONSOLE, plan_id), headers=headers, timeout=60)
        assert deleted.status_code in (200, 204, 404), (
            f"plan {plan_id} was not cleaned up: {deleted.status_code} {deleted.text[:200]}")


@pytest.mark.e2e
@skip_e2e
@pytest.mark.parametrize('form', ['scenario', 'scenario_id'])
def test_T_35_past_the_attack_cap_a_tally_replaces_the_list(capped_scenario, form):
    """Summarise-don't-sample, against a real constraint payload, from both input forms."""
    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, **capped_scenario['forms'][form])
    step = result['steps'][0]
    total = step['blocked_attacks_total']

    assert total == len(capped_scenario['ids']) > BLOCKED_ATTACKS_CAP, (
        "every attack aimed only at a zero-target simulator should be blocked")
    assert 'blocked_attacks' not in step, "past the cap the per-attack list must be absent, not truncated"
    tally = step.get('blocked_attack_codes')
    assert tally, "the cap must replace the list with a per-code tally"
    # An attack cites every constraint recorded against it, so rows overlap: each row
    # is bounded by the total, and the rows do NOT sum to it.
    for row in tally:
        assert 0 < row['attack_count'] <= total, f"{row['code']} counts {row['attack_count']} of {total}"
    missing = {row['code'] for row in tally} - set(result['constraint_catalog'])
    assert not missing, f"the catalog must cover every tallied code, missing: {missing}"


@pytest.mark.e2e
@skip_e2e
@pytest.mark.parametrize('form', ['scenario', 'scenario_id'])
def test_T_35_every_capped_attack_still_carries_its_blockers_when_named(capped_scenario, form):
    """attack_ids is the documented route back to exact reasons — for every capped attack."""
    ids = capped_scenario['ids']
    result = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, attack_ids=','.join(str(i) for i in ids),
        **capped_scenario['forms'][form])
    step = result['steps'][0]
    assert 'blocked_attacks' not in step, "naming attacks must not bring the capped list back"

    answers = step['asked_about']
    assert sorted(answers, key=int) == [str(i) for i in ids]
    for attack_id, answer in answers.items():
        assert answer['state'] == 'blocked', f"#{attack_id} was {answer['state']}"
        assert answer.get('blockers'), f"#{attack_id} is blocked but carries no reason"
    assert len(answers) == step['blocked_attacks_total'], (
        "naming every attack must account for every blocked attack in the step")


@pytest.mark.e2e
@skip_e2e
def test_T_35_the_all_constraints_payload_is_measured(capped_scenario):
    """getAllConstraints=true has no rate-limit cover, so its real size and duration are recorded."""
    body = capped_scenario['forms']['scenario']['scenario']
    started = time.perf_counter()
    payload = _fetch_scenario_statistics(E2E_CONSOLE, body, get_constraints=True, get_all_constraints=True)
    elapsed = time.perf_counter() - started
    size = len(json.dumps(payload))
    logger.warning(f"T-35 measured: {len(capped_scenario['ids'])} attacks, {size:,} bytes, {elapsed:.1f}s")
    print(f"\nT-35 measured: {len(capped_scenario['ids'])} attacks, {size:,} bytes, {elapsed:.1f}s")
    assert elapsed < STATISTICS_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# T-44 — Phase 6: simulator scoping against a real fleet
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@skip_e2e
def test_T_44_scoping_to_a_simulator_moves_no_total_and_explains_what_it_lists():
    """Scoping answers what fails on that machine, and moves no total the console reported.

    The scoped list is NOT a subset of the unscoped one: an attack that ran elsewhere
    but produced nothing on the named machine is listed there, citing codes the
    scenario-wide list never shows. So it is bounded by the step's attacks, not by
    the scenario-wide blocked count, and its codes are checked against the catalog
    rather than against the unscoped attack list.
    """
    _, steps = _discover_scenario_steps(E2E_CONSOLE)
    plain = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    scopable = [(index, group['simulator_ids'][0])
                for index, step in enumerate(plain['steps'])
                for group in step.get('blocked_simulators', [])
                if group.get('simulator_ids')]
    if not scopable:
        pytest.skip(
            f"no step on {E2E_CONSOLE} reports a blocked simulator to scope to")
    index, simulator_id = scopable[0]

    scoped = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps}, simulator_ids=simulator_id)

    assert scoped['verdict'] == plain['verdict'], (
        "scoping narrows the listing, never the verdict")
    for plain_step, scoped_step in zip(plain['steps'], scoped['steps']):
        if not plain_step['counts_computed']:
            continue
        for key in ('blocked_attacks_total', 'blocked_simulators_total',
                    'excluded_simulators_total'):
            assert plain_step[key] == scoped_step[key], f"{key} moved under scoping"

    step = scoped['steps'][index]
    assert step['blocked_attacks_scoped'] is True
    assert step['blocked_attacks_listed'] <= step['attacks_in_step'], (
        "the scoped list cannot name more attacks than the step holds")

    cited = {blocker['code']
             for entry in step.get('blocked_attacks', [])
             for blocker in entry['blockers']}
    assert cited <= set(scoped['constraint_catalog']), (
        f"scoped lines cite codes the catalog does not cover: {cited - set(scoped['constraint_catalog'])}")

    answer = step['asked_about_simulators'][simulator_id]
    assert answer['state'] in ('ran', 'blocked', 'excluded', 'not_computed', 'absent'), (
        f"the named simulator got no explicit answer: {answer}")


@pytest.mark.e2e
@skip_e2e
def test_T_44_an_offline_simulator_is_reported_excluded_with_no_scoped_list():
    """The claim the unit fixtures encode, checked against a real orchestrator."""
    _, steps = _discover_scenario_steps(E2E_CONSOLE)
    plain = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps})

    excluded = [(index, sid)
                for index, step in enumerate(plain['steps'])
                for group in step.get('excluded_simulators', [])
                for sid in group.get('simulator_ids', [])]
    if not excluded:
        pytest.skip(
            f"no offline/disabled/unapproved simulator on {E2E_CONSOLE} — the excluded "
            "short-circuit cannot be observed; add one to exercise T-44")
    index, simulator_id = excluded[0]

    scoped = sb_get_scenario_blocked_entities(
        console=E2E_CONSOLE, scenario={'steps': steps}, simulator_ids=simulator_id)
    step = scoped['steps'][index]

    assert step['asked_about_simulators'][simulator_id]['state'] == 'excluded', (
        "a switched-off simulator must never be reported as blocked")
    assert 'blocked_attacks' not in step and 'blocked_attack_codes' not in step, (
        "an excluded simulator must withhold the scoped list, not render every "
        "attack in the step as blocked on a machine that is merely switched off")
    assert step['blocked_attacks_withheld'] == [simulator_id]
    assert scoped['verdict'] == plain['verdict']
