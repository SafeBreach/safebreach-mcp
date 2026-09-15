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


class TestInputExclusivity:
    """Exactly one input names what to score."""

    def test_naming_none_names_all_three(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_simulation_counts(console='demo')
        message = str(excinfo.value)
        assert 'scenario' in message and 'scenario_id' in message and 'test_id' in message
        assert 'none was given' in message

    def test_naming_two_reports_both(self):
        with pytest.raises(ValueError) as excinfo:
            sb_get_scenario_simulation_counts(
                console='demo', scenario_id='7', test_id='1764165600525.2')
        message = str(excinfo.value)
        assert 'scenario_id' in message and 'test_id' in message

    def test_blank_string_counts_as_absent(self):
        """A blank scenario_id alongside a real test_id is not a second input."""
        result, post = _score([_step()], scenario=None, scenario_id='   ',
                              test_id='1764165600525.2')
        assert post.call_count == 1
        assert result['steps_returned'] == 1

    def test_step_less_scenario_never_reaches_the_api(self):
        with patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='no steps'):
                sb_get_scenario_simulation_counts(console='demo', scenario={'steps': []})
        requests_mock.post.assert_not_called()

    def test_invalid_scenario_json_is_rejected(self):
        with pytest.raises(ValueError, match='Invalid scenario JSON'):
            sb_get_scenario_simulation_counts(console='demo', scenario='{not json')


class TestPlanBody:
    """What gets posted for each input form."""

    def test_adhoc_scenario_is_posted_as_given(self):
        _, post = _score([_step()], scenario={'steps': [{'a': 1}]})
        body = post.call_args.kwargs['json']
        assert body['steps'] == [{'a': 1}]
        assert body['name'] == ''

    def test_integer_scenario_id_passes_through_without_a_lookup(self):
        with patch.object(studio_functions, '_fetch_all_scenarios') as scenarios:
            _, post = _score([_step()], scenario=None, scenario_id='42')
        scenarios.assert_not_called()
        assert post.call_args.kwargs['json'] == {'name': '', 'id': 42}

    def test_uuid_scenario_id_is_resolved_to_steps(self):
        saved = [{'id': 'abc-uuid', 'steps': [{'from_saved': True}]}]
        with patch.object(studio_functions, '_fetch_all_scenarios', return_value=saved):
            _, post = _score([_step()], scenario=None, scenario_id='abc-uuid')
        assert post.call_args.kwargs['json']['steps'] == [{'from_saved': True}]

    def test_unknown_uuid_raises_before_scoring(self):
        with patch.object(studio_functions, '_fetch_all_scenarios', return_value=[]), \
                patch.object(studio_functions, '_fetch_all_plans', return_value=[]), \
                patch.object(studio_functions, 'requests') as requests_mock:
            with pytest.raises(ValueError, match='not found'):
                sb_get_scenario_simulation_counts(console='demo', scenario_id='ghost-uuid')
        requests_mock.post.assert_not_called()

    def test_test_id_passes_through_as_test_id(self):
        _, post = _score([_step()], scenario=None, test_id='1764165600525.2')
        assert post.call_args.kwargs['json'] == {'name': '', 'testId': '1764165600525.2'}


class TestQueryParameters:
    """Every parameter is fixed; none is a tool parameter."""

    def test_parameters_are_fixed_and_booleans_are_json_spelled(self):
        _, post = _score([_step()])
        assert post.call_args.kwargs['params'] == {
            'limit': 500000,
            'includeDisabled': 'false',
            'getConstraints': 'false',
            'getAllConstraints': 'false',
            'useCache': 'true',
        }

    def test_constraints_are_never_requested(self):
        """This answer renders no conflicts, so it does not pay to compute them."""
        _, post = _score([_step()])
        params = post.call_args.kwargs['params']
        assert params['getConstraints'] == 'false'
        assert params['getAllConstraints'] == 'false'

    def test_one_call_per_scoring(self):
        _, post = _score([_step(), _step()])
        assert post.call_count == 1


class TestNullIsNotZero:
    """A count that was never taken is not a count of nothing."""

    def test_is_computed_count_rejects_none_and_bools(self):
        assert is_computed_count(0) is True
        assert is_computed_count(7) is True
        assert is_computed_count(None) is False
        # True is an int in Python; a stray flag must not read as the number 1.
        assert is_computed_count(True) is False
        assert is_computed_count(False) is False

    def test_limit_reached_step_is_not_computed(self):
        result, _ = _score([_step(count=None, limit_reached=True)])
        step = result['steps'][0]
        assert step['counts_computed'] is False
        assert step['simulation_count'] is None
        assert step['is_limit_reached'] is True

    def test_total_is_not_computed_when_no_step_was_scored(self):
        result, _ = _score([_step(count=None, limit_reached=True)])
        assert result['total_simulations'] is None
        text = _format_scenario_simulation_counts(result)
        assert 'not computed' in text
        assert 'Total simulations:** 0' not in text

    def test_partial_total_says_how_many_steps_it_covers(self):
        result, _ = _score([_step(count=40), _step(count=None, limit_reached=True)])
        assert result['total_simulations'] == 40
        assert result['steps_scored'] == 1
        assert 'across the 1 step(s) that were scored' in \
            _format_scenario_simulation_counts(result)

    def test_unmeasured_simulator_is_listed_apart_from_measured_zeros(self):
        result, _ = _score([_step(attackers={'sim-a': None, 'sim-b': 0, 'sim-c': 3})])
        step = result['steps'][0]
        assert step['attacker_simulators'] == {'sim-c': 3}
        assert step['attacker_simulators_unmeasured'] == ['sim-a']
        assert 'Not computed as attackers: sim-a' in \
            _format_scenario_simulation_counts(result)

    def test_truncated_reply_is_reported_against_the_submitted_steps(self):
        result, _ = _score([_step()], scenario={'steps': [{}, {}, {}]})
        assert result['steps_submitted'] == 3
        assert result['steps_returned'] == 1
        assert result['steps_truncated'] is True
        assert 'stopped evaluating early' in _format_scenario_simulation_counts(result)

    def test_no_truncation_claim_when_the_step_count_is_unknowable(self):
        """A passthrough body is resolved server-side, so nothing here knows its length."""
        result, _ = _score([_step()], scenario=None, test_id='1764165600525.2')
        assert result['steps_submitted'] is None
        assert result['steps_truncated'] is False


class TestMovesAreDropped:
    """The attack map is the other question, and the largest field in the payload."""

    def test_moves_never_reach_the_projection(self):
        result, _ = _score([_step(moves={str(i): 1 for i in range(2000)})])
        assert all('moves' not in step for step in result['steps'])
        assert 'moves' not in result

    def test_no_playbook_request_is_made(self):
        with patch.object(studio_functions, '_build_attack_name_map') as names:
            _score([_step()])
        names.assert_not_called()


class TestContributingSimulators:
    """Which simulators produce the simulations, ranked."""

    def test_measured_zeros_are_not_contributors(self):
        result, _ = _score([_step(attackers={'sim-a': 0, 'sim-b': 4})])
        assert result['steps'][0]['attacker_simulators'] == {'sim-b': 4}

    def test_contributors_are_ranked_by_contribution(self):
        result, _ = _score([_step(attackers={'low': 1, 'high': 9, 'mid': 5})])
        assert list(result['steps'][0]['attacker_simulators']) == ['high', 'mid', 'low']

    def test_coverage_denominator_is_the_offered_fleet(self):
        result, _ = _score([_step(targets={'a': 3, 'b': 0, 'c': 0})])
        step = result['steps'][0]
        assert step['target_simulators_total'] == 3
        assert len(step['target_simulators']) == 1
        assert '1 of 3 target simulators' in _format_scenario_simulation_counts(result)


class TestListingCap:
    """Past the cap the listing is dropped whole, never sampled."""

    def test_listing_survives_at_the_cap(self):
        fleet = {f'sim-{i:03d}': 1 for i in range(SIMULATOR_LISTING_CAP)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        assert result['steps'][0]['listing_omitted'] is False
        text = _format_scenario_simulation_counts(result)
        assert 'Contributing attackers:' in text
        assert 'listing omitted' not in text

    def test_listing_is_dropped_past_the_cap(self):
        fleet = {f'sim-{i:03d}': 1 for i in range(SIMULATOR_LISTING_CAP + 1)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        assert result['steps'][0]['listing_omitted'] is True
        text = _format_scenario_simulation_counts(result)
        assert 'Per-simulator listing omitted' in text
        assert 'Contributing attackers:' not in text

    def test_the_trigger_is_the_fleet_offered_not_the_fleet_contributing(self):
        """500 offered of which 3 produce is still a 500-entry answer to "which ones"."""
        fleet = {f'sim-{i:03d}': (1 if i < 3 else 0) for i in range(500)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)])
        step = result['steps'][0]
        assert len(step['attacker_simulators']) == 3
        assert step['listing_omitted'] is True

    def test_capping_never_touches_the_counts(self):
        fleet = {f'sim-{i:03d}': 2 for i in range(500)}
        result, _ = _score([_step(count=1000, attackers=fleet, targets=fleet)])
        text = _format_scenario_simulation_counts(result)
        assert result['total_simulations'] == 1000
        assert '500 of 500 target simulators' in text
        assert '500 of 500 attacker simulators' in text

    def test_dropping_the_listing_keeps_the_answer_small(self):
        fleet = {f'{i:08d}-0000-0000-0000-0000000000ce': 500 - i for i in range(500)}
        result, _ = _score([_step(count=125250, attackers=fleet, targets=fleet)])
        assert len(_format_scenario_simulation_counts(result)) < 1500


class TestNamedSimulators:
    """simulator_ids narrows what is listed, never what is counted."""

    def test_each_named_id_is_answered_in_both_roles(self):
        result, _ = _score(
            [_step(attackers={'sim-a': 7}, targets={'sim-a': 0})],
            simulator_ids='sim-a')
        asked = result['steps'][0]['asked_about']['sim-a']
        assert asked['attacker_simulators'] == {'state': 'contributes', 'count': 7}
        assert asked['target_simulators'] == {'state': 'measured_zero', 'count': 0}

    def test_the_four_dispositions_are_distinct(self):
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

    def test_named_ids_are_answered_past_the_cap(self):
        fleet = {f'sim-{i:03d}': 500 - i for i in range(500)}
        result, _ = _score([_step(attackers=fleet, targets=fleet)],
                           simulator_ids='sim-000,sim-499')
        text = _format_scenario_simulation_counts(result)
        assert result['steps'][0]['listing_omitted'] is True
        assert 'Asked about as attackers: sim-000 (500), sim-499 (1)' in text

    def test_a_measured_zero_is_reachable_only_by_naming_it(self):
        """It is in neither the contributors nor the unmeasured list, yet it counts."""
        result, _ = _score([_step(attackers={'sim-a': 0, 'sim-b': 4})],
                           simulator_ids='sim-a')
        step = result['steps'][0]
        assert 'sim-a' not in step['attacker_simulators']
        assert 'sim-a' not in step['attacker_simulators_unmeasured']
        assert step['asked_about']['sim-a']['attacker_simulators']['count'] == 0
        assert '0 - measured' in _format_scenario_simulation_counts(result)

    def test_naming_ids_does_not_change_the_counts_or_the_coverage(self):
        fleet = {'sim-a': 3, 'sim-b': 4}
        plain, _ = _score([_step(count=7, attackers=fleet, targets=fleet)])
        scoped, _ = _score([_step(count=7, attackers=fleet, targets=fleet)],
                           simulator_ids='sim-a')
        assert plain['total_simulations'] == scoped['total_simulations']
        for key in ('attacker_simulators_total', 'target_simulators_total'):
            assert plain['steps'][0][key] == scoped['steps'][0][key]
        assert 'the simulation counts and the coverage figures are NOT' in \
            _format_scenario_simulation_counts(scoped)

    def test_named_ids_are_deduped_in_the_order_given(self):
        result, _ = _score([_step(attackers={'sim-a': 1})],
                           simulator_ids=' sim-b , sim-a , sim-b ')
        assert result['asked_about'] == ['sim-b', 'sim-a']

    def test_an_all_blank_filter_is_rejected(self):
        with pytest.raises(ValueError, match='named no simulator'):
            sb_get_scenario_simulation_counts(
                console='demo', scenario={'steps': [{}]}, simulator_ids=' , , ')

    def test_named_ids_are_answered_on_an_unscored_step(self):
        result, _ = _score([_step(count=None, limit_reached=True)],
                           simulator_ids='sim-a')
        text = _format_scenario_simulation_counts(result)
        assert 'not computed' in text
        assert 'Asked about as attackers: sim-a (not in this step)' in text


class TestApiErrors:
    """Failures surface as typed errors rather than raw exceptions."""

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
                sb_get_scenario_simulation_counts(
                    console='demo', scenario={'steps': [{}]})

    def test_an_empty_reply_reports_no_step_rather_than_zero(self):
        result, _ = _score([])
        assert result['steps_returned'] == 0
        assert result['total_simulations'] is None
        assert 'no step was returned' in _format_scenario_simulation_counts(result)


class TestToolRegistration:
    """The tool is registered read-only."""

    def test_registered_as_read_only(self):
        from safebreach_mcp_studio.studio_server import SafeBreachStudioServer
        server = SafeBreachStudioServer()
        tools = server.mcp._tool_manager._tools
        assert 'get_scenario_simulation_counts' in tools
        annotations = tools['get_scenario_simulation_counts'].annotations
        assert annotations.readOnlyHint is True
        assert annotations.destructiveHint is False
