"""Gate integration tests — verify rate limiting gates on write tools."""

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_studio.studio_functions import sb_manage_test, sb_run_scenario
from safebreach_mcp_core.token_context import _user_auth_artifacts


@pytest.fixture(autouse=True)
def set_auth_context():
    token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
    yield
    _user_auth_artifacts.reset(token)


class TestManageTestRateLimitingGate:
    """Verify rate limiting gates are called in the correct order around the API call."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions.requests.delete")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_account_id",
        return_value="1234567890",
    )
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_base_url",
        return_value="https://test.safebreach.com",
    )
    def test_check_limit_called_before_api_call(
        self,
        _mock_base_url,
        _mock_account_id,
        mock_delete,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {}

        def delete_side_effect(*args, **kwargs):
            call_order.append("api_call")
            return mock_response

        mock_delete.side_effect = delete_side_effect

        sb_manage_test(
            test_id="1776488350786.15", action="cancel", console="test"
        )

        assert call_order == ["check_limit", "api_call", "record_action"]
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "manage_test"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions.requests.delete")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_account_id",
        return_value="1234567890",
    )
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_base_url",
        return_value="https://test.safebreach.com",
    )
    def test_record_action_called_after_success(
        self,
        _mock_base_url,
        _mock_account_id,
        mock_delete,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {}
        mock_delete.return_value = mock_response

        sb_manage_test(
            test_id="1776488350786.15", action="cancel", console="test"
        )

        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "manage_test"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions.requests.delete")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_account_id",
        return_value="1234567890",
    )
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_base_url",
        return_value="https://test.safebreach.com",
    )
    def test_record_action_not_called_on_api_failure(
        self,
        _mock_base_url,
        _mock_account_id,
        mock_delete,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        import requests as req

        mock_delete.side_effect = req.exceptions.RequestException("API error")

        with pytest.raises(req.exceptions.RequestException):
            sb_manage_test(
                test_id="1776488350786.15", action="cancel", console="test"
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()


# ---------------------------------------------------------------------------
# Shared fixtures for run_scenario tests
# ---------------------------------------------------------------------------
MOCK_STATS = [
    {"simulationCount": 100, "matchedTargetSimulators": 3,
     "matchedAttackerSimulators": 2, "matchedAttacks": 5,
     "totalTargetSimulators": 10, "totalAttackerSimulators": 5, "totalAttacks": 8},
]

MOCK_OOB_SCENARIO = {
    "id": "3b8eade5-9285-43b8-b3e7-6350420983a5",
    "name": "Test Scenario",
    "steps": [{"name": "Step1", "uuid": "aaa", "attacksFilter": {},
               "targetFilter": {"os": {"operator": "is", "values": ["WINDOWS"], "name": "os"}},
               "attackerFilter": {"os": {"operator": "is", "values": ["LINUX"], "name": "os"}},
               "systemFilter": {}}],
    "actions": [], "edges": [], "systemTags": [],
}

MOCK_QUEUE_RESPONSE = {
    "data": {
        "planRunId": "1776488350786.15",
        "name": "Test Scenario",
        "steps": [{"stepRunId": "step-run-1"}],
    }
}


class TestRunScenarioRateLimitingGate:
    """Verify run_scenario gates: check_limit before queue POST, skip on dry_run."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions._get_scenario_statistics",
           return_value=MOCK_STATS)
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_check_limit_before_queue_post(
        self, _mock_base_url, _mock_account_id,
        mock_get, mock_post, _mock_stats, _mock_identity, mock_rate_limiter,
    ):
        """check_limit called before POST, record_action after success."""
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        # Mock GET (scenario fetch)
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [MOCK_OOB_SCENARIO]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        # Mock POST (queue)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = MOCK_QUEUE_RESPONSE
        mock_post_resp.raise_for_status.return_value = None

        def post_side_effect(*args, **kwargs):
            call_order.append("queue_post")
            return mock_post_resp

        mock_post.side_effect = post_side_effect

        result = sb_run_scenario(
            scenario_id="3b8eade5-9285-43b8-b3e7-6350420983a5",
            console="test",
        )
        assert result["status"] == "queued"
        assert call_order == ["check_limit", "queue_post", "record_action"]
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "run_scenario"
        )
        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "run_scenario"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions._get_scenario_statistics",
           return_value=MOCK_STATS)
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_dry_run_does_not_call_gates(
        self, _mock_base_url, _mock_account_id,
        mock_get, _mock_stats, _mock_identity, mock_rate_limiter,
    ):
        """dry_run=True returns prediction without calling check_limit or record_action."""
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [MOCK_OOB_SCENARIO]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        result = sb_run_scenario(
            scenario_id="3b8eade5-9285-43b8-b3e7-6350420983a5",
            console="test",
            dry_run=True,
        )
        assert result["status"] == "dry_run"
        mock_rate_limiter.check_limit.assert_not_called()
        mock_rate_limiter.record_action.assert_not_called()

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_not_ready_does_not_call_gates(
        self, _mock_base_url, _mock_account_id,
        mock_get, _mock_identity, mock_rate_limiter,
    ):
        """Not-ready diagnostic returns without calling gates."""
        not_ready_scenario = {
            **MOCK_OOB_SCENARIO,
            "steps": [{
                "name": "Incomplete",
                "uuid": "bbb",
                "attacksFilter": {},
                "targetFilter": {},
                "attackerFilter": {},
                "systemFilter": {},
            }],
        }
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [not_ready_scenario]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        result = sb_run_scenario(
            scenario_id="3b8eade5-9285-43b8-b3e7-6350420983a5",
            console="test",
        )
        assert result["status"] == "not_ready"
        mock_rate_limiter.check_limit.assert_not_called()
        mock_rate_limiter.record_action.assert_not_called()

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions._get_scenario_statistics",
           return_value=MOCK_STATS)
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_record_action_not_called_on_queue_failure(
        self, _mock_base_url, _mock_account_id,
        mock_get, mock_post, _mock_stats, _mock_identity, mock_rate_limiter,
    ):
        """Queue POST failure: check_limit called, record_action NOT called."""
        import requests as req

        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [MOCK_OOB_SCENARIO]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        mock_post.side_effect = req.exceptions.RequestException("Queue failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_run_scenario(
                scenario_id="3b8eade5-9285-43b8-b3e7-6350420983a5",
                console="test",
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()
