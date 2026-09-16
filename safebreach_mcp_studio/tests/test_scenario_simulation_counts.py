"""Tests for get_scenario_simulation_counts."""

import pytest
from unittest.mock import patch, MagicMock

import safebreach_mcp_studio.studio_functions as studio_functions
from safebreach_mcp_studio.studio_functions import (
    SIMULATOR_LISTING_CAP,
    is_computed_count,
    sb_get_scenario_simulation_counts,
)
from safebreach_mcp_studio.studio_server import _format_scenario_simulation_counts


def _step(count=10, attackers=None, targets=None, limit_reached=False, moves=None):
    return {
        'simulationCount': count,
        'isLimitReached': limit_reached,
        'attackerSimulators': {} if attackers is None else attackers,
        'targetSimulators': {} if targets is None else targets,
        'moves': {'1': 5} if moves is None else moves,
    }


def _score(steps, **kwargs):
    """Call the tool against a canned statistics payload; return result and the POST."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'data': {'steps': steps}}
    with patch.object(studio_functions, 'requests') as requests_mock, \
            patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
            patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
            patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
            patch.object(studio_functions, 'check_rbac_response'):
        requests_mock.post.return_value = response
        kwargs.setdefault('scenario', {'steps': [{}]})
        result = sb_get_scenario_simulation_counts(console='demo', **kwargs)
    return result, requests_mock.post


def _rows(result, step=0):
    """The step's per-simulator breakdown, keyed by simulator id."""
    return {row['simulator_id']: row
            for row in result['steps'][step]['simulator_rows']}


def _row_ids(result, step=0):
    """The breakdown in the order it is rendered."""
    return [row['simulator_id'] for row in result['steps'][step]['simulator_rows']]


class TestInputExclusivity:
    """Exactly one input names what to score."""

    def test_T_1_naming_none_names_all_three(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_simulation_counts(console='demo')
        message = str(excinfo.value)
        assert 'scenario' in message and 'scenario_id' in message and 'test_id' in message
        assert 'none was given' in message

    def test_T_1_naming_two_reports_both(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_simulation_counts(
                console='demo', scenario_id='7', test_id='1764165600525.2')
        message = str(excinfo.value)
        assert 'scenario_id' in message and 'test_id' in message

    def test_T_1_blank_string_counts_as_absent(self):
        """A blank scenario_id alongside a real test_id is not a second input."""
        result, post = _score([_step()], scenario=None, scenario_id='   ',
                              test_id='1764165600525.2')
        assert post.call_count == 1
        assert result['steps_returned'] == 1

    def test_T_2_step_less_scenario_never_reaches_the_api(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='no steps'):
                sb_get_scenario_simulation_counts(console='demo', scenario={'steps': []})
        requests_mock.post.assert_not_called()

    def test_T_1_invalid_scenario_json_is_rejected(self):
        with pytest.raises(ValueError, match='Invalid scenario JSON'):
            sb_get_scenario_simulation_counts(console='demo', scenario='{not json')


class TestPlanBody:
    """What gets posted for each input form."""

    def test_T_3_adhoc_scenario_is_posted_as_given(self):
        _, post = _score([_step()], scenario={'steps': [{'a': 1}]})
        body = post.call_args.kwargs['json']
        assert body['steps'] == [{'a': 1}]
        assert body['name'] == ''

    def test_T_3_integer_scenario_id_passes_through_without_a_lookup(self):
        with patch.object(studio_functions, '_fetch_all_scenarios') as scenarios:
            _, post = _score([_step()], scenario=None, scenario_id='42')
        scenarios.assert_not_called()
        assert post.call_args.kwargs['json'] == {'name': '', 'id': 42}

    def test_T_13_a_non_numeric_scenario_id_is_refused_before_scoring(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError) as excinfo:
                sb_get_scenario_simulation_counts(
                    console='demo', scenario_id='3b8eade5-9285-43b8-b3e7-6350420983a5')
        requests_mock.post.assert_not_called()
        message = str(excinfo.value)
        assert 'numeric id' in message
        # The refusal names the way through, not just the way blocked.
        assert 'get_scenario_details' in message and 'scenario' in message

    def test_T_13_no_input_form_lists_the_console(self):
        """Every form costs exactly one request; none resolves an id by listing."""
        for kwargs in ({'scenario': {'steps': [{}]}},
                       {'scenario': None, 'scenario_id': '4821'},
                       {'scenario': None, 'test_id': '1764165600525.2'}):
            with patch.object(studio_functions, '_fetch_all_scenarios') as scenarios, \
                    patch.object(studio_functions, '_fetch_all_plans') as plans:
                _, post = _score([_step()], **kwargs)
            scenarios.assert_not_called()
            plans.assert_not_called()
            assert post.call_count == 1

    def test_T_3_test_id_passes_through_as_test_id(self):
        _, post = _score([_step()], scenario=None, test_id='1764165600525.2')
        assert post.call_args.kwargs['json'] == {'name': '', 'testId': '1764165600525.2'}


class TestQueryParameters:
    """Every parameter is fixed; none is a tool parameter."""

    def test_T_4_T_5_parameters_are_fixed_and_booleans_are_json_spelled(self):
        _, post = _score([_step()])
        assert post.call_args.kwargs['params'] == {
            'limit': 500000,
            'includeDisabled': 'false',
            'getConstraints': 'false',
            'getAllConstraints': 'false',
            'useCache': 'true',
        }

    def test_T_4_constraints_are_never_requested(self):
        """This answer renders no conflicts, so it does not pay to compute them."""
        _, post = _score([_step()])
        params = post.call_args.kwargs['params']
        assert params['getConstraints'] == 'false'
        assert params['getAllConstraints'] == 'false'

    def test_T_8_one_call_per_scoring(self):
        _, post = _score([_step(), _step()])
        assert post.call_count == 1


class TestNullIsNotZero:
    """A count that was never taken is not a count of nothing."""

    def test_T_7_is_computed_count_rejects_none_and_bools(self):
        assert is_computed_count(0) is True
        assert is_computed_count(7) is True
        assert is_computed_count(None) is False
        # True is an int in Python; a stray flag must not read as the number 1.
        assert is_computed_count(True) is False
        assert is_computed_count(False) is False

    def test_T_7_limit_reached_step_is_not_computed(self):
        result, _ = _score([_step(count=None, limit_reached=True)])
        step = result['steps'][0]
        assert step['counts_computed'] is False
        assert step['simulation_count'] is None
        assert step['is_limit_reached'] is True

    def test_T_6_total_is_not_computed_when_no_step_was_scored(self):
        result, _ = _score([_step(count=None, limit_reached=True)])
        assert result['total_simulations'] is None
        text = _format_scenario_simulation_counts(result)
        assert 'not computed' in text
        assert 'Total simulations:** 0' not in text

    def test_T_6_partial_total_says_how_many_steps_it_covers(self):
        result, _ = _score([_step(count=40), _step(count=None, limit_reached=True)])
        assert result['total_simulations'] == 40
        assert result['steps_scored'] == 1
        assert 'across the 1 step(s) that were scored' in \
            _format_scenario_simulation_counts(result)

    def test_T_7_unmeasured_is_distinguished_from_a_measured_zero(self):
        result, _ = _score([_step(attackers={'sim-a': None, 'sim-b': 0, 'sim-c': 3})])
        rows = _rows(result)
        assert rows['sim-a']['attacker']['state'] == 'not_computed'
        assert rows['sim-b']['attacker']['state'] == 'measured_zero'
        assert rows['sim-c']['attacker'] == {'state': 'contributes', 'count': 3}

    def test_T_7_truncated_reply_is_reported_against_the_submitted_steps(self):
        result, _ = _score([_step()], scenario={'steps': [{}, {}, {}]})
        assert result['steps_submitted'] == 3
        assert result['steps_returned'] == 1
        assert result['steps_truncated'] is True
        assert 'stopped evaluating early' in _format_scenario_simulation_counts(result)

    def test_T_7_no_truncation_claim_when_the_step_count_is_unknowable(self):
        """A passthrough body is resolved server-side, so nothing here knows its length."""
        result, _ = _score([_step()], scenario=None, test_id='1764165600525.2')
        assert result['steps_submitted'] is None
        assert result['steps_truncated'] is False


class TestMovesAreDropped:
    """The attack map is the other question, and the largest field in the payload."""

    def test_T_8_moves_never_reach_the_projection(self):
        result, _ = _score([_step(moves={str(i): 1 for i in range(2000)})])
        assert all('moves' not in step for step in result['steps'])
        assert 'moves' not in result

    def test_T_8_no_playbook_request_is_made(self):
        with patch.object(studio_functions, '_build_attack_name_map') as names:
            _score([_step()])
        names.assert_not_called()


class TestSimulatorBreakdown:
    """Every simulator the step offers, with both its role numbers."""

    def test_T_14_every_offered_simulator_gets_a_row_including_measured_zeros(self):
        """"Produces nothing here" is the most actionable thing to say about a machine."""
        result, _ = _score([_step(attackers={'sim-a': 0, 'sim-b': 4},
                                 targets={'sim-a': 0, 'sim-b': 4})])
        assert _row_ids(result) == ['sim-b', 'sim-a']
        assert _rows(result)['sim-a']['attacker']['state'] == 'measured_zero'

    def test_T_14_a_row_carries_both_roles_at_once(self):
        result, _ = _score([_step(attackers={'sim-a': 7}, targets={'sim-a': 2})])
        row = _rows(result)['sim-a']
        assert row['attacker'] == {'state': 'contributes', 'count': 7}
        assert row['target'] == {'state': 'contributes', 'count': 2}
        assert 'sim-a — attacker: 7, target: 2' in \
            _format_scenario_simulation_counts(result)

    def test_T_14_rows_are_ranked_by_total_contribution(self):
        result, _ = _score([_step(attackers={'low': 1, 'high': 5, 'mid': 2},
                                  targets={'low': 0, 'high': 4, 'mid': 4})])
        assert _row_ids(result) == ['high', 'mid', 'low']

    def test_T_14_a_simulator_offered_in_one_role_says_so_in_the_other(self):
        """The fact that makes a machine a target-only or attacker-only candidate."""
        result, _ = _score([_step(attackers={'win-1': 3}, targets={'lin-1': 2})])
        rows = _rows(result)
        assert rows['win-1']['target']['state'] == 'not_in_step'
        assert rows['lin-1']['attacker']['state'] == 'not_in_step'
        text = _format_scenario_simulation_counts(result)
        assert 'win-1 — attacker: 3, target: not in this step' in text
        assert 'lin-1 — attacker: not in this step, target: 2' in text

    def test_T_14_an_unmeasured_count_reads_as_not_computed_not_as_zero(self):
        result, _ = _score([_step(attackers={'sim-a': None}, targets={'sim-a': 0})])
        text = _format_scenario_simulation_counts(result)
        assert 'sim-a — attacker: not computed, target: 0 - measured' in text


class TestListingCap:
    """Past the cap the breakdown is dropped whole and the caller is told how to get it."""

    def test_T_15_breakdown_survives_at_the_cap(self):
        fleet = {f'sim-{i:03d}': 1 for i in range(SIMULATOR_LISTING_CAP)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        step = result['steps'][0]
        assert step['listing_omitted'] is False
        assert len(step['simulator_rows']) == SIMULATOR_LISTING_CAP
        assert 'breakdown omitted' not in _format_scenario_simulation_counts(result)

    def test_T_15_breakdown_is_dropped_past_the_cap(self):
        fleet = {f'sim-{i:03d}': 1 for i in range(SIMULATOR_LISTING_CAP + 1)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        step = result['steps'][0]
        assert step['listing_omitted'] is True
        # Absent, not empty: an empty list would read as "looked and found nothing".
        assert 'simulator_rows' not in step

    def test_T_15_the_omission_asks_for_a_narrower_filter_not_for_ids(self):
        """Naming ids cannot be the instruction: choosing is how you learn which ids."""
        fleet = {f'sim-{i:03d}': 1 for i in range(500)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        text = _format_scenario_simulation_counts(result)
        assert 'Narrow the step' in text and 'simulators filter' in text
        assert 'Name simulator_ids' not in text

    def test_T_15_the_trigger_is_the_union_of_both_role_maps(self):
        """Neither map alone passes the cap, but the breakdown would still be 30 rows."""
        attackers = {f'atk-{i:02d}': 1 for i in range(15)}
        targets = {f'tgt-{i:02d}': 1 for i in range(15)}
        result, _ = _score([_step(attackers=attackers, targets=targets)])
        step = result['steps'][0]
        assert step['simulators_offered'] == 30
        assert step['listing_omitted'] is True

    def test_T_15_the_trigger_is_the_fleet_offered_not_the_fleet_producing(self):
        """500 offered of which 3 produce is still a 500-row breakdown."""
        fleet = {f'sim-{i:03d}': (1 if i < 3 else 0) for i in range(500)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        assert result['steps'][0]['listing_omitted'] is True

    def test_T_15_capping_never_touches_the_simulation_count(self):
        fleet = {f'sim-{i:03d}': 2 for i in range(500)}
        result, _ = _score([_step(count=1000, attackers=fleet, targets=fleet)])
        assert result['total_simulations'] == 1000
        assert '1,000 simulations' in _format_scenario_simulation_counts(result)

    def test_T_15_dropping_the_breakdown_keeps_the_answer_small(self):
        fleet = {f'{i:08d}-0000-0000-0000-0000000000ce': 500 - i for i in range(500)}
        result, _ = _score([_step(count=125250, attackers=fleet, targets=fleet)])
        assert len(_format_scenario_simulation_counts(result)) < 1000


class TestNamedSimulators:
    """simulator_ids narrows what is listed, never what is counted."""

    def test_T_16_each_named_id_is_answered_in_both_roles(self):
        result, _ = _score(
            [_step(attackers={'sim-a': 7}, targets={'sim-a': 0})],
            simulator_ids='sim-a')
        asked = result['steps'][0]['asked_about']['sim-a']
        assert asked['attacker_simulators'] == {'state': 'contributes', 'count': 7}
        assert asked['target_simulators'] == {'state': 'measured_zero', 'count': 0}

    def test_T_16_the_four_dispositions_are_distinct(self):
        result, _ = _score(
            [_step(attackers={'runs': 3, 'zero': 0, 'unmeasured': None})],
            simulator_ids='runs,zero,unmeasured,absent')
        asked = result['steps'][0]['asked_about']
        states = {name: asked[name]['attacker_simulators']['state'] for name in asked}
        assert states == {
            'runs': 'contributes',
            'zero': 'measured_zero',
            'unmeasured': 'not_computed',
            'absent': 'not_in_step',
        }

    def test_T_16_named_ids_are_answered_past_the_cap(self):
        """The one way to get a per-simulator number once the breakdown is dropped."""
        fleet = {f'sim-{i:03d}': 500 - i for i in range(500)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)],
                           simulator_ids='sim-000,sim-499')
        text = _format_scenario_simulation_counts(result)
        assert result['steps'][0]['listing_omitted'] is True
        assert 'Asked about: sim-000 — attacker: 500, target: 500' in text
        assert 'Asked about: sim-499 — attacker: 1, target: 1' in text

    def test_T_16_naming_ids_does_not_change_the_counts(self):
        fleet = {'sim-a': 3, 'sim-b': 4}
        plain, _ = _score([_step(count=7, attackers=fleet, targets=fleet)])
        scoped, _ = _score([_step(count=7, attackers=fleet, targets=fleet)],
                           simulator_ids='sim-a')
        assert plain['total_simulations'] == scoped['total_simulations']
        assert plain['steps'][0]['simulators_offered'] == \
            scoped['steps'][0]['simulators_offered']
        assert 'the simulation counts are NOT' in \
            _format_scenario_simulation_counts(scoped)

    def test_T_16_named_ids_are_deduped_in_the_order_given(self):
        result, _ = _score([_step(attackers={'sim-a': 1})],
                           simulator_ids=' sim-b , sim-a , sim-b ')
        assert result['asked_about'] == ['sim-b', 'sim-a']

    def test_T_16_an_all_blank_filter_is_rejected(self):
        with pytest.raises(ValueError, match='named no simulator'):
            sb_get_scenario_simulation_counts(
                console='demo', scenario={'steps': [{}]}, simulator_ids=' , , ')

    def test_T_16_named_ids_are_answered_on_an_unscored_step(self):
        result, _ = _score([_step(count=None, limit_reached=True)],
                           simulator_ids='sim-a')
        text = _format_scenario_simulation_counts(result)
        assert 'not computed' in text
        assert 'Asked about: sim-a — attacker: not in this step' in text


class TestApiErrors:
    """Failures surface as typed errors rather than raw exceptions."""

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
                sb_get_scenario_simulation_counts(
                    console='demo', scenario={'steps': [{}]})

    def test_T_7_an_empty_reply_reports_no_step_rather_than_zero(self):
        result, _ = _score([])
        assert result['steps_returned'] == 0
        assert result['total_simulations'] is None
        assert 'no step was returned' in _format_scenario_simulation_counts(result)


class TestToolRegistration:
    """The tool is registered read-only."""

    def test_T_11_registered_as_read_only(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        server = SafeBreachStudioServer()
        tools = server.mcp._tool_manager._tools
        assert 'get_scenario_simulation_counts' in tools
        annotations = tools['get_scenario_simulation_counts'].annotations
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False


class TestRunnableDisclosure:
    """The answer says it is runnable, so a caller cannot read it as the expected figure."""

    def test_T_9_the_rendered_answer_declares_the_counts_runnable(self):
        result, _ = _score([_step(count=7)])
        rendered = _format_scenario_simulation_counts(result)
        assert 'runnable' in rendered.lower()
        assert 'offline, disabled and unapproved simulators are excluded' in rendered

    def test_T_9_the_result_carries_the_runnable_mode_and_hint(self):
        result, _ = _score([_step(count=7)])
        assert result['counts_mode'] == 'runnable'
        assert 'runnable counts' in studio_functions.COUNTS_HINT

    def test_T_9_the_tool_description_says_expected_cannot_be_derived(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        tools = SafeBreachStudioServer().mcp._tool_manager._tools
        description = tools['get_scenario_simulation_counts'].description
        assert 'runnable' in description
        assert 'cannot be derived' in description


class TestNoCachingMcpSide:
    """Every call re-measures, so an adjusted scenario is never answered from a stale number."""

    def _score_twice(self):
        """Score the same input twice against a stub whose answer changes between calls."""
        first, second = MagicMock(), MagicMock()
        first.status_code = second.status_code = 200
        first.json.return_value = {'data': {'steps': [_step(count=4)]}}
        second.json.return_value = {'data': {'steps': [_step(count=9)]}}
        with patch.object(studio_functions, 'requests') as requests_mock, \
                patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
                patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
                patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
                patch.object(studio_functions, 'check_rbac_response'):
            requests_mock.post.side_effect = [first, second]
            body = {'steps': [{}]}
            a = sb_get_scenario_simulation_counts(console='demo', scenario=body)
            b = sb_get_scenario_simulation_counts(console='demo', scenario=body)
        return a, b, requests_mock.post

    def test_T_12_a_repeated_call_issues_its_own_request(self):
        _, _, post = self._score_twice()
        assert post.call_count == 2

    def test_T_12_the_second_answer_reflects_the_changed_payload(self):
        first, second, _ = self._score_twice()
        assert first['steps'][0]['simulation_count'] == 4
        assert second['steps'][0]['simulation_count'] == 9

    def test_T_12_the_answer_tells_the_caller_nothing_is_cached(self):
        assert 'cached' in studio_functions.COUNTS_HINT.lower()


class TestRegisteredToolBoundary:
    """What an agent receives on failure is a message naming the tool, never a traceback."""

    def _registered(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        return SafeBreachStudioServer().mcp._tool_manager._tools[
            'get_scenario_simulation_counts'].fn

    def test_T_28_a_refused_input_comes_back_as_text(self):
        answer = self._registered()(console='demo')
        assert isinstance(answer, str)
        assert 'Scenario Simulation Counts Error' in answer
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
        assert 'Scenario Simulation Counts Error' in answer
        assert 'Statistics API error' in answer
        assert 'upstream exploded' in answer

    def test_T_28_an_rbac_refusal_is_distinguishable_from_an_empty_result(self):
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
        assert 'Scenario Simulation Counts' in answer
