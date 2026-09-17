"""Contract tests for the two scenario-statistics tools (SAF-35508).

T-30 lives here: a dead or slow console must fail loudly rather than answer zero.

T-29 — the recorded real-console payload test — is deliberately NOT in this file. It
requires a response captured from a live console, and a hand-built fixture standing in
for one would re-assert the shapes we already assumed, which is the exact failure T-29
exists to catch. It stays unwritten until a console can be reached.
"""

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
