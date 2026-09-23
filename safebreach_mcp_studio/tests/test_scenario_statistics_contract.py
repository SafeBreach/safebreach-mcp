"""Contract tests for the two scenario-statistics tools (SAF-35508).

T-30 lives here: a dead or slow console must fail loudly rather than answer zero.

T-29 lives here too: both tools are driven from `plan/statistics` responses recorded
verbatim from a live console (`fixtures/plan_statistics_*.json`, each with its
provenance). Hand-built fixtures elsewhere encode our reading of the orchestrator; these
encode what it actually sent, so a renamed field fails a test instead of silently
emptying the answer. If the contract moves, re-capture — never hand-edit a recording.
"""

import copy
import json
from pathlib import Path

import pytest
import requests as real_requests
from unittest.mock import patch, MagicMock

import safebreach_mcp_studio.studio_functions as studio_functions
from safebreach_mcp_studio.studio_functions import (
    STATISTICS_TIMEOUT_SECONDS,
    sb_get_scenario_blocked_entities,
    sb_get_scenario_simulation_counts,
)

TOOLS = (sb_get_scenario_simulation_counts, sb_get_scenario_blocked_entities)


def _drive(tool, *, post_side_effect=None, post_return=None):
    """Run a tool against a transport-level stub and return whatever escapes."""
    with patch.object(studio_functions, 'requests') as requests_mock, \
            patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
            patch.object(studio_functions, 'get_api_account_id', return_value='1111'), \
            patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}), \
            patch.object(studio_functions, 'check_rbac_response'):
        requests_mock.exceptions = real_requests.exceptions
        if post_side_effect is not None:
            requests_mock.post.side_effect = post_side_effect
        else:
            requests_mock.post.return_value = post_return
        return tool(console='demo', scenario={'steps': [{}]}), requests_mock.post


class TestTransportFailuresAreLoud:
    """An infrastructure failure is never dressed up as a measured result."""

    @pytest.mark.parametrize('tool', TOOLS)
    def test_T_30_a_connection_error_propagates(self, tool):
        with pytest.raises(real_requests.exceptions.ConnectionError):
            _drive(tool, post_side_effect=real_requests.exceptions.ConnectionError('no route'))

    @pytest.mark.parametrize('tool', TOOLS)
    def test_T_30_a_timeout_propagates(self, tool):
        with pytest.raises(real_requests.exceptions.Timeout):
            _drive(tool, post_side_effect=real_requests.exceptions.Timeout('too slow'))

    @pytest.mark.parametrize('tool', TOOLS)
    def test_T_30_a_non_json_body_raises_rather_than_scoring_zero(self, tool):
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError('Expecting value: line 1 column 1')
        with pytest.raises(ValueError):
            _drive(tool, post_return=response)


class TestAnAbsentDataKeyIsNotZero:
    """A reply carrying no data reports nothing scored — never a scenario that produces nothing."""

    @pytest.mark.parametrize('body', [{}, {'data': None}])
    def test_T_30_counts_report_no_step_rather_than_a_zero_total(self, body):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = body
        result, _ = _drive(sb_get_scenario_simulation_counts, post_return=response)
        assert result['steps_returned'] == 0
        assert result['total_simulations'] is None

    @pytest.mark.parametrize('body', [{}, {'data': None}])
    def test_T_30_blocked_does_not_call_an_unscored_scenario_clean(self, body):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = body
        result, _ = _drive(sb_get_scenario_blocked_entities, post_return=response)
        assert result['verdict']['state'] != 'clean'


class TestTheRequestCarriesItsTimeout:
    """A hung console must not hang the caller forever."""

    @pytest.mark.parametrize('tool', TOOLS)
    def test_T_30_the_configured_timeout_is_passed_to_the_call(self, tool):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'data': {'steps': []}}
        _, post = _drive(tool, post_return=response)
        assert post.call_args.kwargs['timeout'] == STATISTICS_TIMEOUT_SECONDS

    def test_T_30_the_configured_timeout_is_a_positive_number(self):
        assert isinstance(STATISTICS_TIMEOUT_SECONDS, (int, float))
        assert STATISTICS_TIMEOUT_SECONDS > 0


# ---------------------------------------------------------------------------
# T-29 — a renamed orchestrator field breaks a test, not the answer
# ---------------------------------------------------------------------------
#
# Driven by responses recorded VERBATIM from a live console (see each fixture's
# `provenance`). Every expectation below is computed from the recorded payload's own
# field names, never from a shape we wrote down, so the tools are checked against what
# the orchestrator actually sends.

FIXTURES = Path(__file__).parent / 'fixtures'
RECORDED = {'counts': sb_get_scenario_simulation_counts, 'blocked': sb_get_scenario_blocked_entities}
SIDES = ('attackerConstraints', 'targetConstraints')


def _recorded(name):
    return json.loads((FIXTURES / f'plan_statistics_{name}.json').read_text())


def _replay(name, payload=None):
    """Run a tool against its recorded response, served as a real requests.Response."""
    fixture = _recorded(name)
    response = real_requests.models.Response()
    response.status_code = fixture['provenance']['status']
    response._content = json.dumps(fixture['response'] if payload is None else payload).encode()
    with patch.object(studio_functions.requests, 'post', return_value=response) as post, \
            patch.object(studio_functions, 'get_api_base_url', return_value='https://console'), \
            patch.object(studio_functions, 'get_api_account_id', return_value='3475543660'), \
            patch.object(studio_functions, 'get_auth_headers_for_console', return_value={}):
        result = RECORDED[name](console='demo', scenario=copy.deepcopy(fixture['provenance']['request']['body']))
    return result, post, fixture


def _zeros(mapping):
    return {key for key, count in (mapping or {}).items()
            if isinstance(count, int) and not isinstance(count, bool) and count == 0}


class TestRecordedLivePayload:
    """The tools against what a live orchestrator actually sent."""

    @pytest.mark.parametrize('name', sorted(RECORDED))
    def test_T_29_the_fixture_is_a_recording_with_provenance(self, name):
        provenance = _recorded(name)['provenance']
        assert provenance['console'] and provenance['captured_at'], "a recording must say where and when"
        assert provenance['status'] == 200

    @pytest.mark.parametrize('name', sorted(RECORDED))
    def test_T_29_the_tool_still_asks_the_recorded_question(self, name):
        """If the request drifts, the recording answers a different question and must be re-captured."""
        _, post, fixture = _replay(name)
        recorded = fixture['provenance']['request']
        assert post.call_args.args[0] == 'https://console' + recorded['path']
        assert post.call_args.kwargs['params'] == recorded['params']
        assert post.call_args.kwargs['json'] == recorded['body']

    def test_T_29_counts_reproduce_the_recorded_payload(self):
        result, _, fixture = _replay('counts')
        raw_steps = fixture['response']['data']['steps']
        assert len(result['steps']) == len(raw_steps) > 0
        assert result['total_simulations'] == sum(s['simulationCount'] for s in raw_steps) > 0

        for step, raw in zip(result['steps'], raw_steps):
            assert step['simulation_count'] == raw['simulationCount']
            # A live step omits isLimitReached when the limit was not reached.
            assert step['counts_computed'] is True and step['is_limit_reached'] is bool(raw.get('isLimitReached'))
            offered = set(raw['attackerSimulators']) | set(raw['targetSimulators'])
            assert step['simulators_offered'] == len(offered)
            rows = {row['simulator_id']: row for row in step['simulator_rows']}
            assert set(rows) == offered
            for role, key in (('attacker', 'attackerSimulators'), ('target', 'targetSimulators')):
                for simulator_id, count in raw[key].items():
                    answer = rows[simulator_id][role]
                    expected = 'measured_zero' if count == 0 else 'contributes'
                    assert answer['state'] == expected, (simulator_id, role, answer)
                    if count:
                        assert answer['count'] == count

    def test_T_29_blocked_reproduces_the_recorded_payload(self):
        result, _, fixture = _replay('blocked')
        data = fixture['response']['data']
        assert result['verdict']['state'] == 'blocked'

        for step, raw in zip(result['steps'], data['steps']):
            constrained = set().union(*(raw['simulatorConstraints'].get(side, {}) for side in SIDES))
            assert step['blocked_attacks_total'] == len(_zeros(raw['moves']))
            assert step['blocked_simulators_total'] == len(_zeros(raw['simulators']))
            assert step['excluded_simulators_total'] == len(constrained - set(raw['simulators']))

        recorded_codes = {leaf['reason']
                          for raw in data['steps'] for side in SIDES
                          for by_move in raw['simulatorConstraints'].get(side, {}).values()
                          for leaves in by_move.values() for leaf in leaves}
        cited = set(result['constraint_catalog'])
        assert cited and cited <= recorded_codes, "every cited code must be one the console recorded"
        assert cited <= set(data['constraintCatalog']), "and one its catalog describes"
        for code in cited:
            assert result['constraint_catalog'][code] == data['constraintCatalog'][code], "relayed verbatim"

        listed = [entry for step in result['steps'] for entry in step.get('blocked_attacks', [])]
        assert listed, "the recording blocks attacks, so the answer must name some"
        assert all(entry['blockers'] for entry in listed), "each blocked attack carries its recorded reasons"

    @pytest.mark.parametrize('name,path', [
        ('counts', ('steps', 'simulationCount')),
        ('counts', ('steps', 'attackerSimulators')),
        ('counts', ('steps', 'targetSimulators')),
        ('blocked', ('steps', 'simulationCount')),
        ('blocked', ('steps', 'moves')),
        ('blocked', ('steps', 'simulators')),
        ('blocked', ('steps', 'simulatorConstraints')),
        ('blocked', ('steps', 'simulatorConstraints', 'attackerConstraints')),
        ('blocked', ('steps', 'simulatorConstraints', 'targetConstraints')),
        ('blocked', ('constraintCatalog',)),
    ])
    def test_T_29_every_field_the_tools_read_is_load_bearing(self, name, path):
        """Renaming any one recorded field changes the answer — so a real rename cannot pass silently."""
        original, _, fixture = _replay(name)
        payload = copy.deepcopy(fixture['response'])

        def rename(node, keys):
            head, *rest = keys
            if head == 'steps':
                for step in node['steps']:
                    rename(step, rest)
            elif rest:
                rename(node[head], rest)
            elif head in node:
                node[f'{head}Renamed'] = node.pop(head)

        rename(payload['data'], list(path))
        renamed, _, _ = _replay(name, payload)
        assert json.dumps(renamed, sort_keys=True, default=str) != json.dumps(original, sort_keys=True, default=str), (
            f"renaming {'.'.join(path)} left the answer unchanged — the tool does not actually depend on it")
