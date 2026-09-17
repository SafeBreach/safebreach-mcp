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

    def test_T_1_naming_none_names_all_three(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_blocked_entities(console='demo')
        message = str(excinfo.value)
        assert 'scenario' in message and 'scenario_id' in message and 'test_id' in message

    def test_T_1_naming_two_reports_both(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_blocked_entities(
                console='demo', scenario_id='7', test_id='1764165600525.2')
        assert 'scenario_id' in str(excinfo.value) and 'test_id' in str(excinfo.value)

    def test_T_1_blank_string_counts_as_absent(self):
        _, post = _report([_step()], scenario=None, scenario_id='   ',
                          test_id='1764165600525.2')
        assert post.call_count == 1

    def test_T_13_a_non_numeric_scenario_id_is_refused_before_scoring(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='numeric id'):
                sb_get_scenario_blocked_entities(
                    console='demo', scenario_id='3b8eade5-9285-43b8-b3e7-6350420983a5')
        requests_mock.post.assert_not_called()

    def test_T_2_step_less_scenario_never_reaches_the_api(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='no steps'):
                sb_get_scenario_blocked_entities(console='demo', scenario={'steps': []})
        requests_mock.post.assert_not_called()

    def test_T_3_body_shapes_match_the_sibling(self):
        _, post = _report([_step()], scenario=None, scenario_id='4821')
        assert post.call_args.kwargs['json'] == {'name': '', 'id': 4821}
        _, post = _report([_step()], scenario=None, test_id='1764165600525.2')
        assert post.call_args.kwargs['json'] == {'name': '', 'testId': '1764165600525.2'}

    def test_T_27_an_all_blank_attack_filter_is_rejected(self):
        with pytest.raises(ValueError, match='named no attack'):
            sb_get_scenario_blocked_entities(
                console='demo', scenario={'steps': [{}]}, attack_ids=' , , ')


class TestQueryParameters:
    """Constraints are the answer here, so this tool pays for them."""

    def test_T_17_both_constraint_flags_are_on(self):
        _, post = _report([_step()])
        assert post.call_args.kwargs['params'] == {
            'limit': 500000,
            'includeDisabled': 'false',
            'getConstraints': 'true',
            'getAllConstraints': 'true',
            'useCache': 'true',
        }

    def test_T_17_the_sibling_tool_still_asks_for_no_constraints(self):
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

    def test_T_8_one_call_per_report(self):
        _, post = _report([_step(), _step()])
        assert post.call_count == 1

    def test_T_8_no_playbook_or_config_request_is_made(self):
        with patch.object(studio_functions, '_build_attack_name_map') as names:
            _report([_step()])
        names.assert_not_called()


class TestThreeStates:
    """Blocked, excluded and not-computed are three different facts."""

    def test_T_18_a_simulator_scored_zero_is_blocked(self):
        result, _ = _report([_step(
            simulators={'sim-a': 7, 'sim-b': 0},
            constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        step = result['steps'][0]
        assert step['blocked_simulators_total'] == 1
        assert step['blocked_simulators'][0]['simulator_ids'] == ['sim-b']
        assert step['excluded_simulators_total'] == 0

    def test_T_18_a_simulator_absent_from_scoring_is_excluded_not_blocked(self):
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

    def test_T_18_a_null_count_is_never_called_blocked(self):
        result, _ = _report([_step(simulators={'sim-a': None, 'sim-b': 0})])
        step = result['steps'][0]
        assert step['blocked_simulators_total'] == 1
        assert 'sim-a' not in str(step['blocked_simulators'])

    def test_T_18_an_attack_scored_zero_is_blocked_and_a_null_one_is_not(self):
        result, _ = _report([_step(moves={'1000': 0, '2000': None, '3000': 5})])
        step = result['steps'][0]
        assert [e['attack_id'] for e in step['blocked_attacks']] == ['1000']
        assert step['blocked_attacks_total'] == 1

    def test_T_23_a_blocked_simulator_with_no_constraint_is_still_reported(self):
        result, _ = _report([_step(simulators={'sim-b': 0})])
        step = result['steps'][0]
        assert step['blocked_simulators_unexplained'] == ['sim-b']
        assert 'no constraint reported' in _format_scenario_blocked_entities(result)


class TestVerdict:
    """Decided by whether counts were computed, never by list emptiness."""

    def test_T_19_limit_reached_is_not_evaluated_not_clean(self):
        result, _ = _report([_step(count=None, limit_reached=True,
                                   moves={'1': None}, simulators={})])
        assert result['verdict']['state'] == 'not_evaluated'
        text = _format_scenario_blocked_entities(result)
        assert 'not a clean result' in text

    def test_T_19_a_scenario_with_nothing_blocked_is_clean(self):
        result, _ = _report([_step()])
        assert result['verdict']['state'] == 'clean'

    def test_T_19_a_partly_scored_scenario_says_so(self):
        result, _ = _report([_step(moves={'1000': 0}, simulators={'sim-b': 0}),
                             _step(count=None, limit_reached=True)])
        verdict = result['verdict']
        assert verdict['state'] == 'partially_evaluated'
        assert verdict['steps_scored'] == 1
        assert 'unscored steps were not examined' in verdict['summary']

    def test_T_19_counts_are_over_distinct_entities_scenario_wide(self):
        """One attack blocked in three steps is one attack."""
        blocked = _step(moves={'1000': 0}, simulators={'sim-b': 0})
        result, _ = _report([blocked, dict(blocked), dict(blocked)])
        assert result['verdict']['blocked_attack_count'] == 1
        assert result['verdict']['blocked_simulator_count'] == 1

    def test_T_19_a_sentinel_step_without_side_subkeys_does_not_raise(self):
        result, _ = _report([_step(count=None, limit_reached=True,
                                   moves={'1': None}, simulators={}, constraints={})])
        assert _format_scenario_blocked_entities(result)


class TestAttackDispositions:
    """Naming attacks narrows what is listed, never what is claimed."""

    def test_T_20_ran_outranks_blocked_regardless_of_step_order(self):
        zero = _step(moves={'1000': 0})
        ran = _step(moves={'1000': 240})
        for steps in ([zero, ran], [ran, zero]):
            result, _ = _report(steps, attack_ids='1000')
            asked = result['steps'][0]['asked_about']['1000']
            assert asked == {'state': 'ran', 'count': 240}

    def test_T_20_the_four_dispositions_are_distinct(self):
        result, _ = _report([_step(moves={'ran': 5, 'blocked': 0, 'unmeasured': None})],
                            attack_ids='ran,blocked,unmeasured,absent')
        asked = result['steps'][0]['asked_about']
        assert {k: v['state'] for k, v in asked.items()} == {
            'ran': 'ran', 'blocked': 'blocked',
            'unmeasured': 'not_computed', 'absent': 'absent',
        }

    def test_T_19_naming_ids_does_not_change_the_verdict(self):
        steps = [_step(moves={'1000': 0, '2000': 0}, simulators={'sim-b': 0})]
        plain, _ = _report(steps, )
        scoped, _ = _report(steps, attack_ids='1000')
        assert plain['verdict'] == scoped['verdict']
        assert 'the verdict above is NOT' in _format_scenario_blocked_entities(scoped)

    def test_T_27_named_ids_are_answered_on_an_unscored_step(self):
        result, _ = _report([_step(count=None, limit_reached=True, moves={'1': None})],
                            attack_ids='1000')
        assert 'Asked about: #1000' in _format_scenario_blocked_entities(result)


class TestConstraintDetail:
    """Only `reason` is guaranteed; the rest is relayed where present."""

    def test_T_23_a_bare_reason_renders(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        assert '`incompatible_os`' in _format_scenario_blocked_entities(result)

    def test_T_23_validator_detail_is_relayed(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': [
                {'reason': 'incompatible_os', 'required': 'WINDOWS', 'actual': 'LINUX'}]}}))])
        text = _format_scenario_blocked_entities(result)
        assert 'required: WINDOWS' in text and 'actual: LINUX' in text

    def test_T_23_list_detail_is_rendered_readably(self):
        result, _ = _report([_step(
            moves={'1000': 0},
            constraints=_target({'sim-b': {'1000': [
                {'reason': 'port_in_use', 'values': [445, 139]}]}}))])
        assert 'values: 445, 139' in _format_scenario_blocked_entities(result)

    def test_T_23_both_sides_are_distinguished(self):
        constraints = _target({'sim-b': {'1000': ['incompatible_os']}})
        constraints['attackerConstraints'] = {
            'sim-b': {'1000': [{'reason': 'port_in_use'}]}}
        result, _ = _report([_step(moves={'1000': 0}, simulators={'sim-b': 0},
                                   constraints=constraints)])
        text = _format_scenario_blocked_entities(result)
        assert '(target' in text and '(attacker' in text


class TestCatalog:
    """Meanings come from the console or not at all."""

    def test_T_21_descriptions_are_relayed_verbatim(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))],
            catalog={'incompatible_os': {'description': 'Needs another OS.'}})
        assert result['catalog_supplied'] is True
        assert 'Needs another OS.' in _format_scenario_blocked_entities(result)

    def test_T_21_an_absent_catalog_says_so_and_invents_nothing(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))])
        assert result['catalog_supplied'] is False
        text = _format_scenario_blocked_entities(result)
        assert 'supplied no descriptions' in text
        assert 'not described by this console' in text

    def test_T_21_an_undescribed_code_is_not_given_a_meaning(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['brand_new_code']}}))],
            catalog={'brand_new_code': {}})
        assert result['constraint_catalog']['brand_new_code'] == {}
        assert 'not described by this console' in _format_scenario_blocked_entities(result)

    def test_T_21_the_catalog_is_narrowed_to_codes_actually_cited(self):
        result, _ = _report(
            [_step(moves={'1000': 0},
                   constraints=_target({'sim-b': {'1000': ['incompatible_os']}}))],
            catalog={'incompatible_os': {'description': 'x'},
                     'unrelated_code': {'description': 'y'}})
        assert list(result['constraint_catalog']) == ['incompatible_os']


class TestCaps:
    """Lists are capped; counts never are."""

    def test_T_24_the_attack_list_survives_at_the_cap(self):
        at = BLOCKED_ATTACKS_CAP
        result, _ = _report([_step(moves={f'atk-{i:03d}': 0 for i in range(at)})])
        step = result['steps'][0]
        assert len(step['blocked_attacks']) == at
        assert 'blocked_attack_codes' not in step

    def test_T_24_past_the_cap_no_partial_attack_list_is_returned(self):
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

    def test_T_25_tally_rows_carry_no_validator_detail(self):
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

    def test_T_26_the_catalog_covers_codes_cited_only_past_the_cap(self):
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

    def test_T_27_a_named_attack_carries_its_blockers_past_the_cap(self):
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

    def test_T_27_a_named_attack_that_ran_carries_no_blockers(self):
        """Constraints exist for the simulators that did not run it; they explain no failure."""
        result, _ = _report([_step(
            moves={'atk-000': 7},
            constraints=_target({'sim-b': {'atk-000': ['incompatible_os']}}))],
            attack_ids='atk-000')
        asked = result['steps'][0]['asked_about']['atk-000']
        assert asked['state'] == 'ran'
        assert 'blockers' not in asked

    def test_T_23_simulator_names_are_capped_but_the_group_count_is_exact(self):
        over = CONSTRAINT_NODES_CAP + 1
        simulators = {f'sim-{i}': 0 for i in range(over)}
        constraints = _target({f'sim-{i}': {'1000': ['incompatible_os']} for i in range(over)})
        result, _ = _report([_step(simulators=simulators, constraints=constraints)])
        group = result['steps'][0]['blocked_simulators'][0]
        assert len(group['simulator_ids']) == CONSTRAINT_NODES_CAP
        assert group['simulator_count'] == over
        assert 'and 1 more' in _format_scenario_blocked_entities(result)

    def test_T_23_blocked_simulators_are_grouped_by_code_not_listed_per_node(self):
        simulators = {f'sim-{i}': 0 for i in range(60)}
        constraints = _target({f'sim-{i}': {'1000': ['incompatible_os']} for i in range(60)})
        result, _ = _report([_step(simulators=simulators, constraints=constraints)])
        assert len(result['steps'][0]['blocked_simulators']) == 1
        assert result['steps'][0]['blocked_simulators_total'] == 60


class TestApiErrors:
    """Failures surface as typed errors."""

    def test_T_10_http_error_becomes_a_value_error(self):
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

    def test_T_11_registered_as_read_only(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        tools = SafeBreachStudioServer().mcp._tool_manager._tools
        assert 'get_scenario_blocked_entities' in tools
        annotations = tools['get_scenario_blocked_entities'].annotations
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False

    def test_T_11_the_two_tools_route_to_each_other(self):
        from safebreach_mcp_studio.studio_functions import BLOCKED_HINT, COUNTS_HINT
        assert 'get_scenario_blocked_entities' in COUNTS_HINT
        assert 'get_scenario_simulation_counts' in BLOCKED_HINT


class TestReportingChangesNothing:
    """The tool is a report: it never edits the scenario and never blocks a save."""

    def test_T_22_the_submitted_scenario_is_unchanged_after_scoring(self):
        import copy
        body = {'steps': [{'name': 'step one'}, {'name': 'step two'}]}
        before = copy.deepcopy(body)
        _report([_step(), _step()], scenario=body)
        assert body == before

    def test_T_22_nothing_but_the_statistics_endpoint_is_contacted(self):
        _, post = _report([_step()])
        assert post.call_count == 1
        url = post.call_args[0][0] if post.call_args[0] else post.call_args.kwargs['url']
        assert url.endswith('/plan/statistics')

    def test_T_22_no_save_or_update_verb_is_ever_issued(self):
        """A report must not reach for a mutating verb, whatever the payload says."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'data': {'steps': [_step()]}}
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response'):
            requests_mock.post.return_value = response
            sb_get_scenario_blocked_entities(console='demo', scenario={'steps': [{}]})
        assert requests_mock.put.call_count == 0
        assert requests_mock.patch.call_count == 0
        assert requests_mock.delete.call_count == 0


class TestRegisteredToolBoundary:
    """An agent sees a message naming the tool, never a traceback."""

    def _registered(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        return SafeBreachStudioServer().mcp._tool_manager._tools[
            'get_scenario_blocked_entities'].fn

    def test_T_28_a_refused_input_comes_back_as_text(self):
        answer = self._registered()(console='demo')
        assert isinstance(answer, str)
        assert 'Scenario Blocked Entities Error' in answer
        assert 'scenario' in answer and 'test_id' in answer

    def test_T_28_an_api_failure_carries_its_cause_into_the_text(self):
        import requests as real_requests
        response = MagicMock()
        response.status_code = 503
        response.text = 'upstream exploded'
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response',
                             side_effect=real_requests.exceptions.HTTPError()):
            requests_mock.post.return_value = response
            requests_mock.exceptions = real_requests.exceptions
            answer = self._registered()(console='demo', scenario='{"steps": [{}]}')
        assert isinstance(answer, str)
        assert 'upstream exploded' in answer

    def test_T_28_an_rbac_refusal_is_not_reported_as_a_clean_scenario(self):
        import requests as real_requests
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'data': {'steps': []}}
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response',
                             side_effect=PermissionError('role may not read this account')):
            requests_mock.post.return_value = response
            requests_mock.exceptions = real_requests.exceptions
            answer = self._registered()(console='demo', scenario='{"steps": [{}]}')
        assert 'Permission Error' in answer
        assert 'role may not read this account' in answer
        assert 'clean' not in answer.lower()


# ---------------------------------------------------------------------------
# Phase 6 — simulator_ids scopes the blocked-attack list
# ---------------------------------------------------------------------------

def _scoped_step(**overrides):
    """Three blocked attacks spread across two simulators that were both scored.

    '1000' is cited only on sim-b, '1002' only on sim-c, and '1001' on both but
    under a different code each side — which is what makes "only the codes cited
    on that simulator" falsifiable rather than incidentally true.
    """
    step = _step(
        count=0,
        moves={'1000': 0, '1001': 0, '1002': 0},
        simulators={'sim-b': 0, 'sim-c': 0},
        constraints=_target({
            'sim-b': {'1000': ['incompatible_os'], '1001': ['incompatible_os']},
            'sim-c': {'1001': ['port_in_use'], '1002': ['port_in_use']},
        }),
    )
    step.update(overrides)
    return step


def _listed_ids(step):
    return [entry['attack_id'] for entry in step['blocked_attacks']]


class TestSimulatorScoping:
    """What will not run on THIS machine, rather than what will not run anywhere."""

    def test_T_38_only_attacks_blocked_on_the_named_simulator_are_listed(self):
        result, _ = _report([_scoped_step()], simulator_ids='sim-b')
        step = result['steps'][0]
        assert _listed_ids(step) == ['1000', '1001']
        assert step['blocked_attacks_listed'] == 2
        assert step['blocked_attacks_total'] == 3

    def test_T_38_a_line_shows_only_the_codes_cited_on_that_simulator(self):
        result, _ = _report([_scoped_step()], simulator_ids='sim-b')
        entries = result['steps'][0]['blocked_attacks']
        shared = next(e for e in entries if e['attack_id'] == '1001')
        assert [b['code'] for b in shared['blockers']] == ['incompatible_os']
        # Scoped to the attack lines, not the whole narration: sim-c is scored 0,
        # so the scenario-wide blocked-simulator section cites port_in_use for an
        # unrelated and entirely correct reason.
        assert all(b['code'] != 'port_in_use'
                   for entry in entries for b in entry['blockers'])

    def test_T_38_naming_two_simulators_returns_the_union(self):
        result, _ = _report([_scoped_step()], simulator_ids='sim-b,sim-c')
        assert _listed_ids(result['steps'][0]) == ['1000', '1001', '1002']


class TestPerSimulatorBlocks:
    """Scoping asks "what does not run HERE" — not "which scenario-wide zeros touch here"."""

    @staticmethod
    def _field_step():
        """A real console payload's shape: one scenario-wide zero, one per-simulator zero.

        '5328' scores 0 everywhere and is constrained on the target. '98' scores 2 —
        it RAN — but produced nothing on the attacker it is constrained against. The
        second is the case that distinguishes a per-simulator answer from a narrowed
        scenario-wide one.
        """
        step = _step(
            count=24,
            moves={'98': 2, '5328': 0, '7071': 22},
            simulators={'sim-att': 1, 'sim-other': 1, 'sim-tgt': 24},
            constraints={
                'targetConstraints': {'sim-tgt': {'5328': [
                    {'reason': 'simulator_variant_is_root_user'},
                    {'reason': 'move_does_not_support_root_simulation_user'}]}},
                'attackerConstraints': {'sim-att': {'98': [
                    {'reason': 'move_doesnt_requires_proxy_ignoring_proxy_variant'}]}},
            },
        )
        return [step]

    def test_T_45_an_attack_that_ran_elsewhere_is_listed_where_it_produced_nothing(self):
        result, _ = _report(self._field_step(), simulator_ids='sim-att')
        step = result['steps'][0]
        assert _listed_ids(step) == ['98']
        assert [b['code'] for b in step['blocked_attacks'][0]['blockers']] == [
            'move_doesnt_requires_proxy_ignoring_proxy_variant']

    def test_T_45_the_scenario_wide_zero_is_not_listed_where_it_is_uncited(self):
        result, _ = _report(self._field_step(), simulator_ids='sim-att')
        assert '5328' not in _listed_ids(result['steps'][0])

    def test_T_45_scoping_to_the_target_lists_only_what_is_blocked_there(self):
        result, _ = _report(self._field_step(), simulator_ids='sim-tgt')
        assert _listed_ids(result['steps'][0]) == ['5328']

    def test_T_45_the_scenario_wide_total_still_counts_only_scenario_wide_zeros(self):
        result, _ = _report(self._field_step(), simulator_ids='sim-att')
        step = result['steps'][0]
        # 98 is listed HERE but ran, so it is not a scenario-wide block. The totals
        # and verdict must keep saying so — the filter changes the question asked of
        # a step, never the scenario-level claim.
        assert step['blocked_attacks_total'] == 1
        assert step['blocked_attacks_listed'] == 1
        assert result['verdict'] == _report(self._field_step())[0]['verdict']

    def test_T_45_a_simulator_with_nothing_recorded_against_it_lists_nothing(self):
        result, _ = _report(self._field_step(), simulator_ids='sim-other')
        step = result['steps'][0]
        assert step['blocked_attacks'] == []
        assert step['asked_about_simulators']['sim-other']['state'] == 'ran'


class TestScopingChangesOnlyTheListing:
    """Naming ids narrows what is listed — never what is claimed."""

    def test_T_39_the_verdict_and_every_total_survive_scoping(self):
        plain, _ = _report([_scoped_step()])
        scoped, _ = _report([_scoped_step()], simulator_ids='sim-b')
        assert plain['verdict'] == scoped['verdict']
        for key in ('blocked_attacks_total', 'blocked_simulators_total',
                    'excluded_simulators_total'):
            assert plain['steps'][0][key] == scoped['steps'][0][key]

    def test_T_39_both_simulator_sections_are_unchanged_by_scoping(self):
        plain, _ = _report([_scoped_step()])
        scoped, _ = _report([_scoped_step()], simulator_ids='sim-b')
        for key in ('blocked_simulators', 'blocked_simulators_unexplained',
                    'excluded_simulators'):
            assert plain['steps'][0][key] == scoped['steps'][0][key]

    def test_T_39_the_scoped_list_discloses_its_omission_as_a_ratio(self):
        result, _ = _report([_scoped_step()], simulator_ids='sim-b')
        assert '2 of 3' in _format_scenario_blocked_entities(result)


class TestExcludedSimulatorShortCircuit:
    """A switched-off machine is not an incompatibility with every attack."""

    @staticmethod
    def _with_offline():
        """sim-off carries simulator_is_offline on every move and was never scored."""
        return _step(
            count=0,
            moves={'1000': 0, '1001': 0, '1002': 0},
            simulators={'sim-b': 0},
            constraints=_target({
                'sim-b': {'1000': ['incompatible_os']},
                'sim-off': {move: ['simulator_is_offline']
                            for move in ('1000', '1001', '1002')},
            }),
        )

    def test_T_40_an_excluded_simulator_gets_no_scoped_attack_list(self):
        result, _ = _report([self._with_offline()], simulator_ids='sim-off')
        step = result['steps'][0]
        assert 'blocked_attacks' not in step
        assert 'blocked_attack_codes' not in step

    def test_T_40_the_withheld_list_states_its_reason(self):
        result, _ = _report([self._with_offline()], simulator_ids='sim-off')
        assert result['steps'][0]['blocked_attacks_withheld'] == ['sim-off']
        narrated = _format_scenario_blocked_entities(result)
        # A distinctive phrase, not "excluded from scoring" — that is the existing
        # section heading and renders whenever anything is excluded, so asserting
        # it would pass with no short-circuit implemented at all.
        assert 'list withheld' in narrated
        assert 'sim-off' in narrated

    def test_T_40_the_named_simulator_is_answered_excluded_never_blocked(self):
        result, _ = _report([self._with_offline()], simulator_ids='sim-off')
        answer = result['steps'][0]['asked_about_simulators']['sim-off']
        assert answer['state'] == 'excluded'

    def test_T_40_the_verdict_and_totals_are_untouched_by_the_short_circuit(self):
        plain, _ = _report([self._with_offline()])
        scoped, _ = _report([self._with_offline()], simulator_ids='sim-off')
        assert plain['verdict'] == scoped['verdict']
        assert (plain['steps'][0]['blocked_attacks_total']
                == scoped['steps'][0]['blocked_attacks_total'] == 3)

    def test_T_40_a_genuinely_blocked_simulator_still_gets_its_scoped_list(self):
        result, _ = _report([self._with_offline()], simulator_ids='sim-b')
        step = result['steps'][0]
        assert 'blocked_attacks_withheld' not in step
        assert _listed_ids(step) == ['1000']

    def test_T_40_naming_one_excluded_and_one_scored_still_lists_the_scored_one(self):
        result, _ = _report([self._with_offline()], simulator_ids='sim-off,sim-b')
        step = result['steps'][0]
        assert 'blocked_attacks_withheld' not in step
        assert _listed_ids(step) == ['1000']
        assert step['asked_about_simulators']['sim-off']['state'] == 'excluded'


class TestNamedSimulatorAnswers:
    """Silence never stands in for an answer."""

    @staticmethod
    def _mixed_steps():
        scored = _step(
            count=4,
            moves={'1000': 0},
            simulators={'sim-ran': 4, 'sim-zero': 0},
            constraints=_target({'sim-zero': {'1000': ['incompatible_os']}}),
        )
        unscored = _step(
            count=None,
            moves={'1000': None},
            simulators={'sim-unmeasured': None},
            constraints=_target({'sim-off': {'1000': ['simulator_is_offline']}}),
        )
        return [scored, unscored]

    def test_T_41_every_named_simulator_gets_exactly_one_state(self):
        named = 'sim-ran,sim-zero,sim-unmeasured,sim-off,sim-nowhere'
        result, _ = _report(self._mixed_steps(), simulator_ids=named)
        assert result['asked_about_simulators'] == named.split(',')
        states = {sid: answer['state']
                  for sid, answer in result['steps'][0]['asked_about_simulators'].items()}
        assert set(states) == set(named.split(','))
        assert states['sim-ran'] == 'ran'
        assert states['sim-zero'] == 'blocked'
        assert states['sim-off'] == 'excluded'
        assert states['sim-nowhere'] == 'absent'

    def test_T_41_an_unmeasured_simulator_is_not_computed_never_zero(self):
        result, _ = _report(self._mixed_steps(), simulator_ids='sim-unmeasured')
        answer = result['steps'][0]['asked_about_simulators']['sim-unmeasured']
        assert answer['state'] == 'not_computed'
        assert answer['count'] is None

    def test_T_41_an_empty_scoped_list_still_answers_the_named_simulator(self):
        result, _ = _report([_scoped_step()], simulator_ids='sim-nowhere')
        step = result['steps'][0]
        assert step['blocked_attacks_listed'] == 0
        assert step['blocked_attacks_total'] == 3
        narrated = _format_scenario_blocked_entities(result)
        assert '0 of 3' in narrated
        assert 'sim-nowhere' in narrated


class TestScopedCapAndComposition:
    """The cap follows the scoped list, and the two filters are independent axes."""

    @staticmethod
    def _over_cap(cited_on_b):
        """Every attack blocked; only `cited_on_b` of them cite sim-b."""
        blocked = [str(2000 + i) for i in range(BLOCKED_ATTACKS_CAP + 10)]
        return _step(
            count=0,
            moves={attack: 0 for attack in blocked},
            simulators={'sim-b': 0, 'sim-c': 0},
            constraints=_target({
                'sim-b': {attack: ['incompatible_os'] for attack in blocked[:cited_on_b]},
                'sim-c': {attack: ['port_in_use'] for attack in blocked},
            }),
        )

    def test_T_42_scoping_under_the_cap_earns_the_per_attack_list_back(self):
        result, _ = _report([self._over_cap(3)], simulator_ids='sim-b')
        step = result['steps'][0]
        assert 'blocked_attacks' in step
        assert 'blocked_attack_codes' not in step
        assert step['blocked_attacks_listed'] == 3
        assert step['blocked_attacks_total'] == BLOCKED_ATTACKS_CAP + 10

    def test_T_42_a_scoped_set_still_over_the_cap_is_summarised(self):
        result, _ = _report([self._over_cap(BLOCKED_ATTACKS_CAP + 1)],
                            simulator_ids='sim-b')
        step = result['steps'][0]
        assert 'blocked_attacks' not in step
        tally = step['blocked_attack_codes']
        assert sum(row['attack_count'] for row in tally) == BLOCKED_ATTACKS_CAP + 1

    def test_T_42_the_two_filters_compose_without_narrowing_each_other(self):
        outside = str(2000 + BLOCKED_ATTACKS_CAP + 5)
        result, _ = _report([self._over_cap(3)],
                            simulator_ids='sim-b', attack_ids=outside)
        step = result['steps'][0]
        assert step['blocked_attacks_listed'] == 3
        assert _listed_ids(step) == ['2000', '2001', '2002']
        named = step['asked_about'][outside]
        assert named['state'] == 'blocked'
        assert [b['code'] for b in named['blockers']] == ['port_in_use']


class TestScopedCatalog:
    """The meanings track what the scoped answer actually shows."""

    @staticmethod
    def _steps():
        """port_in_use is cited only by an out-of-scope ATTACK, on no rendered simulator.

        sim-c must CONTRIBUTE, not score zero and not be excluded: either of those
        renders it in a scenario-wide simulator section, which legitimately puts
        port_in_use in the catalog and makes the absence assertion below fail
        against a perfectly correct implementation.

        Attack '1001' is the one that makes this guard anything: it IS listed (it
        cites sim-b) and it ALSO carries port_in_use from sim-c. Without that code
        being filtered out of the tally, the catalog would describe a code appearing
        nowhere in the rendered lines. A fixture whose out-of-scope code sits only on
        an unlisted attack cannot catch that — the listing filter alone removes it,
        and the tally filter could be deleted with every assertion still passing.
        """
        return [_step(
            count=5,
            moves={'1000': 0, '1001': 0, '1002': 0},
            simulators={'sim-b': 0, 'sim-c': 5},
            constraints=_target({
                'sim-b': {'1000': ['incompatible_os'], '1001': ['incompatible_os']},
                'sim-c': {'1001': ['port_in_use'], '1002': ['port_in_use']},
            }),
        )]

    def test_T_43_the_catalog_is_narrowed_to_codes_the_scoped_answer_shows(self):
        catalog = {'incompatible_os': {'description': 'OS mismatch.'},
                   'port_in_use': {'description': 'Port taken.'}}
        result, _ = _report(self._steps(), catalog=catalog, simulator_ids='sim-b')
        assert 'incompatible_os' in result['constraint_catalog']
        assert 'port_in_use' not in result['constraint_catalog']

    def test_T_43_the_catalog_covers_codes_dropped_at_the_scoped_cap(self):
        blocked = [str(3000 + i) for i in range(BLOCKED_ATTACKS_CAP + 1)]
        step = _step(
            count=0,
            moves={attack: 0 for attack in blocked},
            simulators={'sim-b': 0},
            constraints=_target({'sim-b': {
                **{attack: ['incompatible_os'] for attack in blocked[:-1]},
                blocked[-1]: ['rare_code'],
            }}),
        )
        catalog = {'incompatible_os': {'description': 'OS mismatch.'},
                   'rare_code': {'description': 'Seldom seen.'}}
        result, _ = _report([step], catalog=catalog, simulator_ids='sim-b')
        assert 'blocked_attacks' not in result['steps'][0]
        assert 'rare_code' in result['constraint_catalog']

    def test_T_43_a_scoped_report_without_a_catalog_invents_no_meaning(self):
        result, _ = _report(self._steps(), simulator_ids='sim-b')
        assert result['catalog_supplied'] is False
        assert 'incompatible_os' in _format_scenario_blocked_entities(result)
