"""Tests for get_scenario_blocked_entities."""

import pytest
from unittest.mock import patch, MagicMock

import safebreach_mcp_studio.studio_functions as studio_functions
from safebreach_mcp_studio.studio_functions import (
    BLOCKED_ATTACKS_CAP,
    CONSTRAINT_NODES_CAP,
    sb_get_scenario_blocked_entities,
)
from safebreach_mcp_studio.studio_server import _format_scenario_blocked_entities


def _step(count=8, moves=None, simulators=None, constraints=None, limit_reached=False):
    return {
        'simulationCount': count,
        'isLimitReached': limit_reached,
        'moves': {'1000': 7} if moves is None else moves,
        'simulators': {'sim-a': 7} if simulators is None else simulators,
        'simulatorConstraints': {} if constraints is None else constraints,
    }


def _target(reasons_by_simulator):
    """A targetConstraints block: {simulator: {move: [reason, ...]}}."""
    return {'targetConstraints': {
        simulator: {move: [{'reason': r} if isinstance(r, str) else r for r in reasons]
                    for move, reasons in by_move.items()}
        for simulator, by_move in reasons_by_simulator.items()
    }}


def _report(steps, catalog=None, **kwargs):
    """Call the tool against a canned statistics payload; return result and the POST."""
    data = {'steps': steps}
    if catalog is not None:
        data['constraintCatalog'] = catalog
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'data': data}
    with patch.object(studio_functions, 'requests') as requests_mock, \
            patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
            patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
            patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
            patch.object(studio_functions, 'check_rbac_response'):
        requests_mock.post.return_value = response
        kwargs.setdefault('scenario', {'steps': [{}]})
        result = sb_get_scenario_blocked_entities(console='demo', **kwargs)
    return result, requests_mock.post


class TestInputsMatchTheSiblingTool:
    """The same plumbing, so the same rules — for free."""

    def test_naming_none_names_all_three(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_blocked_entities(console='demo')
        message = str(excinfo.value)
        assert 'scenario' in message and 'scenario_id' in message and 'test_id' in message

    def test_naming_two_reports_both(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_blocked_entities(
                console='demo', scenario_id='7', test_id='1764165600525.2')
        assert 'scenario_id' in str(excinfo.value) and 'test_id' in str(excinfo.value)

    def test_blank_string_counts_as_absent(self):
        _, post = _report([_step()], scenario=None, scenario_id='   ',
                          test_id='1764165600525.2')
        assert post.call_count == 1

    def test_a_non_numeric_scenario_id_is_refused_before_scoring(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='numeric id'):
                sb_get_scenario_blocked_entities(
                    console='demo', scenario_id='3b8eade5-9285-43b8-b3e7-6350420983a5')
        requests_mock.post.assert_not_called()

    def test_step_less_scenario_never_reaches_the_api(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='no steps'):
                sb_get_scenario_blocked_entities(console='demo', scenario={'steps': []})
        requests_mock.post.assert_not_called()

    def test_body_shapes_match_the_sibling(self):
        _, post = _report([_step()], scenario=None, scenario_id='4821')
        assert post.call_args.kwargs['json'] == {'name': '', 'id': 4821}
        _, post = _report([_step()], scenario=None, test_id='1764165600525.2')
        assert post.call_args.kwargs['json'] == {'name': '', 'testId': '1764165600525.2'}

    def test_an_all_blank_attack_filter_is_rejected(self):
        with pytest.raises(ValueError, match='named no attack'):
            sb_get_scenario_blocked_entities(
                console='demo', scenario={'steps': [{}]}, attack_ids=' , , ')


class TestQueryParameters:
    """Constraints are the answer here, so this tool pays for them."""

    def test_both_constraint_flags_are_on(self):
        _, post = _report([_step()])
        assert post.call_args.kwargs['params'] == {
            'limit': 500000,
            'includeDisabled': 'false',
            'getConstraints': 'true',
            'getAllConstraints': 'true',
            'useCache': 'true',
        }

    def test_the_sibling_tool_still_asks_for_no_constraints(self):
        """The shared fetch grew a parameter; the counts tool must not have moved."""
        from safebreach_mcp_studio.studio_functions import sb_get_scenario_simulation_counts
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'data': {'steps': []}}
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://c'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response'):
            requests_mock.post.return_value = response
            sb_get_scenario_simulation_counts(console='demo', scenario={'steps': [{}]})
        params = requests_mock.post.call_args.kwargs['params']
        assert params['getConstraints'] == 'false'
        assert params['getAllConstraints'] == 'false'

    def test_one_call_per_report(self):
        _, post = _report([_step(), _step()])
        assert post.call_count == 1

    def test_no_playbook_or_config_request_is_made(self):
        with patch.object(studio_functions, '_build_attack_name_map') as names:
            _report([_step()])
        names.assert_not_called()


class TestThreeStates:
    """Blocked, excluded and not-computed are three different facts."""

    def test_a_simulator_scored_zero_is_blocked(self):
        result, _ = _report([_step(
            simulators={'sim-a': 7, 'sim-b': 0},
            constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        step = result['steps'][0]
        assert step['blocked_simulators_total'] == 1
        assert step['blocked_simulators'][0]['simulator_ids'] == ['sim-b']
        assert step['excluded_simulators_total'] == 0

    def test_a_simulator_absent_from_scoring_is_excluded_not_blocked(self):
        """Offline nodes carry constraints but are never seeded into the count map."""
        result, _ = _report([_step(
            simulators={'sim-a': 7},
            constraints=_target({'sim-off': {'1000': ['simulator_is_offline']}}))])
        step = result['steps'][0]
        assert step['blocked_simulators_total'] == 0
        assert step['excluded_simulators_total'] == 1
        assert step['excluded_simulators'][0]['simulator_ids'] == ['sim-off']
        text = _format_scenario_blocked_entities(result)
        assert 'excluded from scoring' in text
        assert result['verdict']['blocked_simulator_count'] == 0

    def test_a_null_count_is_never_called_blocked(self):
        result, _ = _report([_step(simulators={'sim-a': None, 'sim-b': 0})])
        step = result['steps'][0]
        assert step['blocked_simulators_total'] == 1
        assert 'sim-a' not in str(step['blocked_simulators'])

    def test_an_attack_scored_zero_is_blocked_and_a_null_one_is_not(self):
        result, _ = _report([_step(moves={'1000': 0, '2000': None, '3000': 5})])
        step = result['steps'][0]
        assert [e['attack_id'] for e in step['blocked_attacks']] == ['1000']
        assert step['blocked_attacks_total'] == 1

    def test_a_blocked_simulator_with_no_constraint_is_still_reported(self):
        result, _ = _report([_step(simulators={'sim-b': 0})])
        step = result['steps'][0]
        assert step['blocked_simulators_unexplained'] == ['sim-b']
        assert 'no constraint reported' in _format_scenario_blocked_entities(result)


class TestVerdict:
    """Decided by whether counts were computed, never by list emptiness."""

    def test_limit_reached_is_not_evaluated_not_clean(self):
        result, _ = _report([_step(count=None, limit_reached=True,
                                   moves={'1': None}, simulators={})])
        assert result['verdict']['state'] == 'not_evaluated'
        text = _format_scenario_blocked_entities(result)
        assert 'not a clean result' in text

    def test_a_scenario_with_nothing_blocked_is_clean(self):
        result, _ = _report([_step()])
        assert result['verdict']['state'] == 'clean'

    def test_a_partly_scored_scenario_says_so(self):
        result, _ = _report([_step(moves={'1000': 0}, simulators={'sim-b': 0}),
                             _step(count=None, limit_reached=True)])
        verdict = result['verdict']
        assert verdict['state'] == 'partially_evaluated'
        assert verdict['steps_scored'] == 1
        assert 'unscored steps were not examined' in verdict['summary']

    def test_counts_are_over_distinct_entities_scenario_wide(self):
        """One attack blocked in three steps is one attack."""
        blocked = _step(moves={'1000': 0}, simulators={'sim-b': 0})
        result, _ = _report([blocked, dict(blocked), dict(blocked)])
        assert result['verdict']['blocked_attack_count'] == 1
        assert result['verdict']['blocked_simulator_count'] == 1

    def test_a_sentinel_step_without_side_subkeys_does_not_raise(self):
        result, _ = _report([_step(count=None, limit_reached=True,
                                   moves={'1': None}, simulators={}, constraints={})])
        assert _format_scenario_blocked_entities(result)


class TestAttackDispositions:
    """Naming attacks narrows what is listed, never what is claimed."""

    def test_ran_outranks_blocked_regardless_of_step_order(self):
        zero = _step(moves={'1000': 0})
        ran = _step(moves={'1000': 240})
        for steps in ([zero, ran], [ran, zero]):
            result, _ = _report(steps, attack_ids='1000')
            asked = result['steps'][0]['asked_about']['1000']
            assert asked == {'state': 'ran', 'count': 240}

    def test_the_four_dispositions_are_distinct(self):
        result, _ = _report([_step(moves={'ran': 5, 'blocked': 0, 'unmeasured': None})],
                            attack_ids='ran,blocked,unmeasured,absent')
        asked = result['steps'][0]['asked_about']
        assert {k: v['state'] for k, v in asked.items()} == {
            'ran': 'ran', 'blocked': 'blocked',
            'unmeasured': 'not_computed', 'absent': 'absent',
        }

    def test_naming_ids_does_not_change_the_verdict(self):
        steps = [_step(moves={'1000': 0, '2000': 0}, simulators={'sim-b': 0})]
        plain, _ = _report(steps, )
        scoped, _ = _report(steps, attack_ids='1000')
        assert plain['verdict'] == scoped['verdict']
        assert 'the verdict above is NOT' in _format_scenario_blocked_entities(scoped)

    def test_named_ids_are_answered_on_an_unscored_step(self):
        result, _ = _report([_step(count=None, limit_reached=True, moves={'1': None})],
                            attack_ids='1000')
        assert 'Asked about: #1000' in _format_scenario_blocked_entities(result)


class TestConstraintDetail:
    """Only `reason` is guaranteed; the rest is relayed where present."""

    def test_a_bare_reason_renders(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        assert '`incompatible_os`' in _format_scenario_blocked_entities(result)

    def test_validator_detail_is_relayed(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': [
                {'reason': 'incompatible_os', 'required': 'WINDOWS', 'actual': 'LINUX'}]}}))])
        text = _format_scenario_blocked_entities(result)
        assert 'required: WINDOWS' in text and 'actual: LINUX' in text

    def test_list_detail_is_rendered_readably(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': [
                {'reason': 'port_in_use', 'values': [445, 139]}]}}))])
        assert 'values: 445, 139' in _format_scenario_blocked_entities(result)

    def test_both_sides_are_distinguished(self):
        constraints = _target({'sim-b': {'1000': ['incompatible_os']}})
        constraints['attackerConstraints'] = {
            'sim-b': {'1000': [{'reason': 'port_in_use'}]}}
        result, _ = _report([_step(moves={'1000': 0}, simulators={'sim-b': 0},
                                   constraints=constraints)])
        text = _format_scenario_blocked_entities(result)
        assert '(target' in text and '(attacker' in text


class TestCatalog:
    """Meanings come from the console or not at all."""

    def test_descriptions_are_relayed_verbatim(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))],
            catalog={'incompatible_os': {'description': 'Needs another OS.'}})
        assert result['catalog_supplied'] is True
        assert 'Needs another OS.' in _format_scenario_blocked_entities(result)

    def test_an_absent_catalog_says_so_and_invents_nothing(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        assert result['catalog_supplied'] is False
        text = _format_scenario_blocked_entities(result)
        assert 'supplied no descriptions' in text
        assert 'not described by this console' in text

    def test_an_undescribed_code_is_not_given_a_meaning(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['brand_new_code']}}))],
            catalog={'brand_new_code': {}})
        assert result['constraint_catalog']['brand_new_code'] == {}
        assert 'not described by this console' in _format_scenario_blocked_entities(result)

    def test_the_catalog_is_narrowed_to_codes_actually_cited(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))],
            catalog={'incompatible_os': {'description': 'x'},
                     'unrelated_code': {'description': 'y'}})
        assert list(result['constraint_catalog']) == ['incompatible_os']


class TestCaps:
    """Lists are capped; counts never are."""

    def test_the_attack_list_survives_at_the_cap(self):
        at = BLOCKED_ATTACKS_CAP
        result, _ = _report([_step(moves={f'atk-{i:03d}': 0 for i in range(at)})])
        step = result['steps'][0]
        assert len(step['blocked_attacks']) == at
        assert 'blocked_attack_codes' not in step

    def test_past_the_cap_no_partial_attack_list_is_returned(self):
        """A fifty-of-sixty sample accounts for fifty; the tally accounts for sixty."""
        over = BLOCKED_ATTACKS_CAP + 10
        result, _ = _report([_step(
            moves={f'atk-{i:03d}': 0 for i in range(over)},
            constraints=_target({'sim-b': {f'atk-{i:03d}': ['incompatible_os']
                                           for i in range(over)}}))])
        step = result['steps'][0]
        # Absent, not empty — empty would read as "looked and found nothing".
        assert 'blocked_attacks' not in step
        assert step['blocked_attacks_total'] == over
        assert result['verdict']['blocked_attack_count'] == over
        row = step['blocked_attack_codes'][0]
        assert row['attack_count'] == over, "the tally must cover every blocked attack"
        text = _format_scenario_blocked_entities(result)
        assert f'({over:,}), by constraint' in text
        assert 'per-attack detail omitted' in text
        assert 'Name attack_ids' in text

    def test_tally_rows_carry_no_validator_detail(self):
        """A row stands for many attacks; one leaf's values must not speak for all."""
        over = BLOCKED_ATTACKS_CAP + 1
        result, _ = _report([_step(
            moves={f'atk-{i:03d}': 0 for i in range(over)},
            constraints=_target({'sim-b': {f'atk-{i:03d}': [
                {'reason': 'incompatible_os', 'required': 'WINDOWS', 'actual': 'LINUX'}]
                for i in range(over)}}))])
        assert all('detail' not in row for row in result['steps'][0]['blocked_attack_codes'])
        # Scoped to the tally lines: the simulator sections legitimately carry
        # detail, because there a row is one simulator rather than many attacks.
        tally_lines = [line for line in _format_scenario_blocked_entities(result).splitlines()
                       if 'attack(s)' in line]
        assert tally_lines, "expected the tally to render"
        assert not any('required: WINDOWS' in line for line in tally_lines)

    def test_the_catalog_covers_codes_cited_only_past_the_cap(self):
        """Cited codes are collected before capping, not from the rendered rows."""
        over = BLOCKED_ATTACKS_CAP + 5
        blocked = {f'atk-{i:03d}': 0 for i in range(over)}
        constraints = _target({
            'sim-common': {f'atk-{i:03d}': ['incompatible_os'] for i in range(over - 1)},
            'sim-rare': {f'atk-{over - 1:03d}': ['only_the_last_one']},
        })
        result, _ = _report([_step(moves=blocked, constraints=constraints)],
                            catalog={'incompatible_os': {'description': 'x'},
                                     'only_the_last_one': {'description': 'rare'}})
        assert 'only_the_last_one' in result['constraint_catalog']
        assert 'rare' in _format_scenario_blocked_entities(result)

    def test_a_named_attack_carries_its_blockers_past_the_cap(self):
        """The list is gone, so attack_ids is the only route to an exact reason."""
        over = BLOCKED_ATTACKS_CAP + 5
        last = f'atk-{over - 1:03d}'
        result, _ = _report([_step(
            moves={f'atk-{i:03d}': 0 for i in range(over)},
            constraints=_target({'sim-b': {last: ['incompatible_os']}}))],
            attack_ids=last)
        asked = result['steps'][0]['asked_about'][last]
        assert asked['state'] == 'blocked'
        assert [b['code'] for b in asked['blockers']] == ['incompatible_os']
        assert f'Asked about: #{last} (blocked) — `incompatible_os`' in \
            _format_scenario_blocked_entities(result)

    def test_a_named_attack_that_ran_carries_no_blockers(self):
        """Constraints exist for the simulators that did not run it; they explain no failure."""
        result, _ = _report([_step(
            moves={'atk-000': 7},
            constraints=_target({'sim-b': {'atk-000': ['incompatible_os']}}))],
            attack_ids='atk-000')
        asked = result['steps'][0]['asked_about']['atk-000']
        assert asked['state'] == 'ran'
        assert 'blockers' not in asked

    def test_simulator_names_are_capped_but_the_group_count_is_exact(self):
        over = CONSTRAINT_NODES_CAP + 1
        simulators = {f'sim-{i}': 0 for i in range(over)}
        constraints = _target({f'sim-{i}': {'1000': ['incompatible_os']} for i in range(over)})
        result, _ = _report([_step(simulators=simulators, constraints=constraints)])
        group = result['steps'][0]['blocked_simulators'][0]
        assert len(group['simulator_ids']) == CONSTRAINT_NODES_CAP
        assert group['simulator_count'] == over
        assert 'and 1 more' in _format_scenario_blocked_entities(result)

    def test_blocked_simulators_are_grouped_by_code_not_listed_per_node(self):
        simulators = {f'sim-{i}': 0 for i in range(60)}
        constraints = _target({f'sim-{i}': {'1000': ['incompatible_os']} for i in range(60)})
        result, _ = _report([_step(simulators=simulators, constraints=constraints)])
        assert len(result['steps'][0]['blocked_simulators']) == 1
        assert result['steps'][0]['blocked_simulators_total'] == 60


class TestApiErrors:
    """Failures surface as typed errors."""

    def test_http_error_becomes_a_value_error(self):
        import requests as real_requests
        response = MagicMock()
        response.status_code = 400
        response.text = 'NOT_ALLOWED'
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://c'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response',
                             side_effect=real_requests.exceptions.HTTPError()):
            requests_mock.post.return_value = response
            requests_mock.exceptions = real_requests.exceptions
            with pytest.raises(ValueError, match='Statistics API error'):
                sb_get_scenario_blocked_entities(console='demo', scenario={'steps': [{}]})


class TestToolRegistration:
    """Registered read-only, alongside its sibling."""

    def test_registered_as_read_only(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        tools = SafeBreachStudioServer().mcp._tool_manager._tools
        assert 'get_scenario_blocked_entities' in tools
        annotations = tools['get_scenario_blocked_entities'].annotations
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

    def test_the_two_tools_route_to_each_other(self):
        from safebreach_mcp_studio.studio_functions import BLOCKED_HINT, COUNTS_HINT
        assert 'get_scenario_blocked_entities' in COUNTS_HINT
        assert 'get_scenario_simulation_counts' in BLOCKED_HINT
