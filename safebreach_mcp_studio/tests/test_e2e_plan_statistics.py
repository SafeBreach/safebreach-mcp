"""
End-to-End Tests for get_plan_statistics (SAF-35508)

Scores real plans against a real console and checks the numbers are usable,
self-consistent, and explained by the orchestrator's own constraint catalog.

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
    sb_get_scenario_simulation_counts,
    sb_get_scenario_blocked_entities,
    sb_get_scenario_attack_blockers,
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


def _blocker_codes(result):
    """Every constraint code the blocked-entities answer actually cites.

    The projections drop the conflicts list, so a code reaches a caller only
    through a reported blocker. Reading `step['conflicts']` here — as the
    pre-split tests did — would find nothing on any of the three tools.
    """
    return {
        blocker['code']
        for step in result['steps']
        for entry in (step['zero_impact_attacks'] + step['zero_impact_simulators'])
        for blocker in entry['blockers']
    }


VERDICT_STATES = {'blocked', 'clean', 'clean_where_measured',
                  'partially_evaluated', 'not_evaluated'}

DISPOSITIONS = {'ran', 'blocked', 'blocked_where_measured', 'not_computed',
                'count_map_truncated', 'absent'}

SCENARIO_TOOLS = (
    sb_get_scenario_simulation_counts,
    sb_get_scenario_blocked_entities,
    sb_get_scenario_attack_blockers,
)


def _required_kwargs(tool):
    """The extra input the blockers tool cannot be called without.

    It explains attacks the caller names; naming none is a different question
    with its own tool. Without this a shared assertion would meet that error
    instead of the one it is checking.
    """
    if tool is sb_get_scenario_attack_blockers:
        return {'attack_ids': '9012'}
    return {}


@skip_e2e
@pytest.mark.e2e
class TestScenarioStatisticsToolsE2E:
    """T-28, T-29, T-30, T-31, T-40, T-48 — the three tools against a real console."""

    def test_ad_hoc_scenario_returns_usable_numbers(self):
        """T-28 — a scenario body that was never saved is scored and comes back usable."""
        scenario = _first_scenario_with_steps()
        body = json.dumps({"name": "", "steps": scenario['steps'][:1]})

        counts = sb_get_scenario_simulation_counts(console=E2E_CONSOLE, scenario=body)
        assert counts['steps'], "a scored scenario must return at least one step"
        step = counts['steps'][0]
        assert isinstance(step['simulation_count'], int)
        for field in ('attacks', 'attacker_simulators', 'target_simulators'):
            assert isinstance(step[field], dict)
            assert all(v is None or isinstance(v, int) for v in step[field].values())

    def test_the_blocked_entities_tool_returns_a_shipped_verdict_state(self):
        """T-28 — the verdict is one of the five shipped states, whatever the console holds."""
        scenario = _first_scenario_with_steps()
        body = json.dumps({"name": "", "steps": scenario['steps'][:1]})

        blocked = sb_get_scenario_blocked_entities(console=E2E_CONSOLE, scenario=body)

        assert blocked['verdict']['state'] in VERDICT_STATES
        assert blocked['verdict']['summary'].strip()
        # Every cited code has an entry, and none is its own explanation.
        for code in _blocker_codes(blocked):
            assert code in blocked['constraint_catalog']
            assert blocked['constraint_catalog'][code]['description'] != code

    def test_the_blockers_tool_answers_every_named_id(self):
        """T-28 — a named id gets exactly one disposition, from the six shipped values."""
        scenario = _first_scenario_with_steps()
        body = json.dumps({"name": "", "steps": scenario['steps'][:1]})

        counts = sb_get_scenario_simulation_counts(console=E2E_CONSOLE, scenario=body)
        attack_ids = list(counts['steps'][0]['attacks'])
        if not attack_ids:
            pytest.skip(
                f"The first step of scenario '{scenario['id']}' on '{E2E_CONSOLE}' "
                f"resolved no attacks, so there is no id to ask about."
            )

        blockers = sb_get_scenario_attack_blockers(
            console=E2E_CONSOLE, scenario=body, attack_ids=attack_ids[0])

        assert len(blockers['dispositions']) == 1
        assert blockers['dispositions'][0]['disposition'] in DISPOSITIONS

    def test_scenario_id_and_ad_hoc_body_agree(self):
        """T-29 — scoring by id agrees with scoring the same scenario's body."""
        scenario = _first_scenario_with_steps()

        by_id = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        ad_hoc = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE,
            scenario=json.dumps({"name": "", "steps": scenario['steps']}))

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

        result = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=str(plans[0]['id']))

        assert 'steps' in result

    def test_runnable_never_exceeds_expected(self):
        """T-30 — the ordering relation, asserted unconditionally."""
        scenario = _first_scenario_with_steps()

        runnable = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        expected = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=scenario['id'], include_disabled=True)

        pairs = list(zip(runnable['steps'], expected['steps']))
        assert pairs, "both calls must return steps to be comparable"
        for run_step, exp_step in pairs:
            if run_step['counts_computed'] and exp_step['counts_computed']:
                assert run_step['simulation_count'] <= exp_step['simulation_count']

    def test_offline_reason_explains_the_delta(self):
        """T-30 — the conditional half, skipped explicitly when the console cannot show it."""
        scenario = _first_scenario_with_steps()

        runnable = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        expected = sb_get_scenario_simulation_counts(
            console=E2E_CONSOLE, scenario_id=scenario['id'], include_disabled=True)

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
        # Post-split the reason is reachable only through a reported blocker,
        # which means only when the offline simulator's union count is a
        # genuine 0. An offline simulator that merely REDUCES an attack is
        # invisible to all three tools by design — that is SAF-35484's scope.
        runnable_blocked = sb_get_scenario_blocked_entities(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        offline = 'simulator_is_offline' in _blocker_codes(runnable_blocked)

        if not any(d > 0 for d in deltas) and not offline:
            pytest.skip(
                f"Console '{E2E_CONSOLE}' has no offline, disabled or unapproved simulator "
                f"that FULLY blocks anything: every step's runnable simulation_count equals "
                f"expected, and no reported blocker cites simulator_is_offline. Note this is "
                f"narrower than 'the console has no offline simulator' — one that only reduces "
                f"an attack's count is not reported by any of the three tools. The delta and "
                f"offline-reason assertions require the fully-blocking precondition; the "
                f"runnable <= expected ordering was asserted above and holds."
            )

        assert any(d > 0 for d in deltas), (
            "an offline simulator was reported as fully blocking, so a step must differ"
        )
        assert offline, "a positive delta must be explained by the offline reason"
        expected_blocked = sb_get_scenario_blocked_entities(
            console=E2E_CONSOLE, scenario_id=scenario['id'], include_disabled=True)
        assert 'simulator_is_offline' not in _blocker_codes(expected_blocked), (
            "expected counts score every simulator, so offline is never reported there"
        )

    @pytest.mark.parametrize("tool", SCENARIO_TOOLS)
    def test_step_less_scenario_yields_the_typed_error(self, tool):
        """T-31 — the guard fires before the request, identically on all three."""
        with pytest.raises(ValueError) as excinfo:
            tool(console=E2E_CONSOLE, scenario='{"steps": []}',
                 **_required_kwargs(tool))

        message = str(excinfo.value)
        assert 'steps' in message.lower()
        assert '400' in message or 'NOT_ALLOWED' in message

    def test_real_console_supplies_the_descriptions(self):
        """T-40 — the only test that can falsify the relay design."""
        scenario = _first_scenario_with_steps()

        result = sb_get_scenario_blocked_entities(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        catalog = result['constraint_catalog']
        referenced = _blocker_codes(result)

        if not referenced:
            pytest.skip(
                f"Scenario '{scenario['id']}' on console '{E2E_CONSOLE}' reported no "
                f"blocked entity, so no code reaches the catalog and there is nothing to "
                f"check. The relay assertions require at least one reported blocker — "
                f"note this is narrower than 'produced no conflicts', since a reducing "
                f"conflict is deliberately not reported by this tool."
            )

        # Unconditional: every referenced code has an entry, and no entry ever
        # echoes the code back as its own explanation.
        for code in referenced:
            assert code in catalog, f"blocker code {code} has no catalog entry"
            assert catalog[code]['description'] != code

        described = [c for c, e in catalog.items() if e['description']]
        if not described:
            pytest.skip(
                f"Console '{E2E_CONSOLE}' returned no constraintCatalog carrying a non-null "
                f"description — its orchestrator predates SAF-35568. The verbatim-relay "
                f"assertions require that precondition; the R11 degradation (blockers "
                f"surfaced, every description null, key present) was asserted instead and holds."
            )

        for code in described:
            assert isinstance(catalog[code]['description'], str)
            assert catalog[code]['description'].strip()

    def test_catalog_is_scoped_to_the_codes_its_blockers_cite(self):
        """T-40 — the catalog carries this answer's codes, not the whole vocabulary."""
        scenario = _first_scenario_with_steps()

        result = sb_get_scenario_blocked_entities(
            console=E2E_CONSOLE, scenario_id=scenario['id'])
        referenced = _blocker_codes(result)

        assert set(result['constraint_catalog']) == referenced
        assert len(result['constraint_catalog']) < 97, (
            "the full vocabulary is 97 codes; the catalog must be scoped to this answer"
        )

    def test_the_three_tools_agree_on_a_scenario_built_to_block(self):
        """T-48 — three answers from one scoring must not contradict each other.

        The block is constructed rather than discovered: an OS-constrained
        attack aimed at simulators of a different OS. Finding a console that
        happens to hold a blocked scenario would leave the assertion to luck.
        """
        from safebreach_mcp_config.config_functions import sb_get_console_simulators
        from safebreach_mcp_playbook.playbook_functions import sb_get_playbook_attacks

        try:
            simulators = sb_get_console_simulators(
                console=E2E_CONSOLE, status_filter='connected')['simulators']
        except Exception as e:
            pytest.skip(f"Could not list simulators on {E2E_CONSOLE}: {e}")

        # The API returns OS as a nested object and camelCase connectivity
        # flags. Reading a flat `os_type` finds nothing on ANY console, so the
        # skip below would fire forever while blaming the fleet.
        by_os = {}
        for simulator in simulators:
            os_type = ((simulator.get('OS') or {}).get('type') or '').upper()
            if os_type and simulator.get('isConnected'):
                by_os.setdefault(os_type, []).append(simulator['id'])
        if len(by_os) < 2:
            pytest.skip(
                f"Console '{E2E_CONSOLE}' has a single-OS connected fleet "
                f"({ {k: len(v) for k, v in by_os.items()} }), so no OS mismatch can be "
                f"constructed. A role mismatch would be the fallback; neither is available."
            )

        target_os, other_os = sorted(by_os, key=lambda k: -len(by_os[k]))[:2]
        try:
            attacks = sb_get_playbook_attacks(
                console=E2E_CONSOLE, target_platform_filter=target_os,
                page_number=0)['attacks_in_page']
        except Exception as e:
            pytest.skip(f"Could not list playbook attacks on {E2E_CONSOLE}: {e}")
        if not attacks:
            pytest.skip(f"No {target_os}-constrained attack found on '{E2E_CONSOLE}'.")

        blocked_attack = attacks[0]['id']
        # Every filter carries operator+name+values; the console rejects a
        # bare {"values": [...]} with a 400 schema error.
        body = json.dumps({"name": "", "steps": [{
            "attacksFilter": {"playbook": {"operator": "is", "name": "playbook",
                                           "values": [blocked_attack]}},
            "targetFilter": {"simulators": {"operator": "is", "name": "simulators",
                                            "values": by_os[other_os]}},
        }]})

        counts = sb_get_scenario_simulation_counts(console=E2E_CONSOLE, scenario=body)
        blocked = sb_get_scenario_blocked_entities(console=E2E_CONSOLE, scenario=body)
        blockers = sb_get_scenario_attack_blockers(
            console=E2E_CONSOLE, scenario=body, attack_ids=str(blocked_attack))

        # The three answers describe one scoring; they must not disagree.
        assert counts['returned_step_count'] == blocked['returned_step_count']
        assert blocked['verdict']['state'] in VERDICT_STATES

        disposition = blockers['dispositions'][0]['disposition']
        step = counts['steps'][0]
        if step['simulation_count'] == 0:
            # Two different zeros, and the orchestrator distinguishes them by
            # whether the attack reached the moves map at all:
            #   - map carries the id at 0  -> a move was generated and blocked
            #   - map is empty of the id   -> no move was ever generated for it
            # Only the first is what AC-9 calls inapplicable. Asserting
            # "blocked" for both would demand a claim the data cannot support.
            if str(blocked_attack) in step['attacks']:
                assert disposition in ('blocked', 'blocked_where_measured'), (
                    f"the attack is in the counts map at 0, so the blockers tool "
                    f"must not say {disposition!r}"
                )
                assert blocked['verdict']['state'] in ('blocked', 'clean_where_measured')
                for code in _blocker_codes(blocked):
                    assert code in blocked['constraint_catalog']
            else:
                # No move generated. All three tools must at least agree that
                # nothing runs — they must not disagree about the outcome.
                assert disposition == 'absent'
                assert not blocked['steps'][0]['zero_impact_attacks']
                assert blocked['verdict']['state'] in (
                    'clean', 'clean_where_measured', 'blocked')
        else:
            assert disposition == 'ran', (
                f"the counts tool reports simulations, so the blockers tool must not "
                f"say {disposition!r}"
            )
