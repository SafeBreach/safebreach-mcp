"""Gate integration tests — verify rate limiting gates on write tools."""

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_studio.studio_functions import (
    sb_manage_test,
    sb_run_scenario,
    sb_save_studio_attack_draft,
    sb_update_studio_attack_draft,
    sb_run_studio_attack,
    sb_set_studio_attack_status,
)
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
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="RUNNING")
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
        _mock_state,
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
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="RUNNING")
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
        _mock_state,
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
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="RUNNING")
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
        _mock_state,
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

    # --- SAF-31111: Quick-returns skip rate limiting ---

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="CANCELED")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_account_id",
        return_value="1234567890",
    )
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_base_url",
        return_value="https://test.safebreach.com",
    )
    def test_quick_return_does_not_trigger_rate_limiting(
        self,
        _mock_base_url,
        _mock_account_id,
        _mock_state,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        """Quick-return for already-canceled test does NOT call rate limiter."""
        result = sb_manage_test(
            test_id="test123", action="cancel", console="test"
        )

        assert result.get('was_already') is True
        mock_rate_limiter.check_limit.assert_not_called()
        mock_rate_limiter.record_action.assert_not_called()

    # --- SAF-29972: Delete rate limiting ---

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions._fetch_storage_stats", return_value=None)
    @patch("safebreach_mcp_studio.studio_functions.requests.delete")
    @patch("safebreach_mcp_studio.studio_functions._fetch_test_summary")
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="CANCELED")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_account_id",
        return_value="1234567890",
    )
    @patch(
        "safebreach_mcp_studio.studio_functions.get_api_base_url",
        return_value="https://test.safebreach.com",
    )
    def test_delete_rate_limit_check_before_delete(
        self,
        _mock_base_url,
        _mock_account_id,
        _mock_state,
        mock_summary,
        mock_del,
        _mock_stats,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        """Delete execute calls check_limit before DELETE API."""
        mock_summary.return_value = {
            "originalPlan": {"name": "T"}, "status": "CANCELED",
            "finalStatus": {}, "startTime": 0, "endTime": 0,
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_del.return_value = mock_response

        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        def delete_side_effect(*args, **kwargs):
            call_order.append("api_call")
            return mock_response
        mock_del.side_effect = delete_side_effect

        sb_manage_test(
            test_id="t1", action="delete", console="test",
            reason="cleanup", dry_run=False
        )

        assert call_order == ["check_limit", "api_call", "record_action"]

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch(
        "safebreach_mcp_studio.studio_functions.get_caller_identity",
        return_value="test-caller",
    )
    @patch("safebreach_mcp_studio.studio_functions._fetch_test_storage_info", return_value=None)
    @patch("safebreach_mcp_studio.studio_functions._fetch_test_summary")
    @patch("safebreach_mcp_studio.studio_functions._get_test_state", return_value="CANCELED")
    def test_delete_dry_run_skips_rate_limit(
        self,
        _mock_state,
        mock_summary,
        _mock_storage,
        _mock_get_identity,
        mock_rate_limiter,
    ):
        """Delete dry-run does NOT call rate limiter."""
        mock_summary.return_value = {
            "originalPlan": {"name": "T"}, "status": "CANCELED",
            "finalStatus": {}, "startTime": 0, "endTime": 0,
        }

        result = sb_manage_test(
            test_id="t1", action="delete", console="test",
            reason="cleanup", dry_run=True
        )

        assert result['status'] == "dry_run"
        mock_rate_limiter.check_limit.assert_not_called()
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
    """Verify run_scenario gates: check_limit before queue POST, skip on evaluate."""

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
    def test_evaluate_does_not_call_gates(
        self, _mock_base_url, _mock_account_id,
        mock_get, _mock_stats, _mock_identity, mock_rate_limiter,
    ):
        """evaluate=True returns prediction without calling check_limit or record_action."""
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = [MOCK_OOB_SCENARIO]
        mock_get_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_get_resp

        result = sb_run_scenario(
            scenario_id="3b8eade5-9285-43b8-b3e7-6350420983a5",
            console="test",
            evaluate=True,
        )
        assert result["status"] == "evaluating"
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


# ---------------------------------------------------------------------------
# Shared mock response helpers
# ---------------------------------------------------------------------------
MOCK_DRAFT_API_RESPONSE = {
    "id": 10000001,
    "name": "Test Attack",
    "status": "draft",
    "methodType": 5,
    "class": "python",
    "description": "test",
    "timeout": 300,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}

MOCK_QUEUE_API_RESPONSE = {
    "data": {
        "planRunId": "1776488350786.15",
        "name": "Studio Attack Test",
        "steps": [{"stepRunId": "step-run-1"}],
    }
}


def _mock_success_response(json_value=None, status_code=200):
    """Create a mock HTTP response that looks successful."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_value if json_value is not None else {}
    return resp


# ---------------------------------------------------------------------------
# save_studio_attack_draft
# ---------------------------------------------------------------------------
class TestSaveStudioAttackDraftRateLimitingGate:
    """Verify gates on save_studio_attack_draft: check before POST, record after cache."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_check_limit_before_post(
        self, _mock_base_url, _mock_account_id,
        mock_post, _mock_identity, mock_rate_limiter,
    ):
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        def post_side_effect(*args, **kwargs):
            call_order.append("api_call")
            return _mock_success_response(MOCK_DRAFT_API_RESPONSE)

        mock_post.side_effect = post_side_effect

        sb_save_studio_attack_draft(
            name="Test Attack", python_code="print('hello')", console="test",
        )

        assert call_order == ["check_limit", "api_call", "record_action"]
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "save_studio_attack_draft"
        )
        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "save_studio_attack_draft"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_record_action_not_called_on_api_failure(
        self, _mock_base_url, _mock_account_id,
        mock_post, _mock_identity, mock_rate_limiter,
    ):
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("POST failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_save_studio_attack_draft(
                name="Test Attack", python_code="print('hello')", console="test",
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()


# ---------------------------------------------------------------------------
# update_studio_attack_draft
# ---------------------------------------------------------------------------
class TestUpdateStudioAttackDraftRateLimitingGate:
    """Verify gates on update_studio_attack_draft: check before PUT, record after cache."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.put")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_check_limit_before_put(
        self, _mock_base_url, _mock_account_id,
        mock_put, _mock_identity, mock_rate_limiter,
    ):
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        def put_side_effect(*args, **kwargs):
            call_order.append("api_call")
            return _mock_success_response(MOCK_DRAFT_API_RESPONSE)

        mock_put.side_effect = put_side_effect

        sb_update_studio_attack_draft(
            attack_id=10000001, name="Updated Attack",
            python_code="print('updated')", console="test",
        )

        assert call_order == ["check_limit", "api_call", "record_action"]
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "update_studio_attack_draft"
        )
        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "update_studio_attack_draft"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.put")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_record_action_not_called_on_api_failure(
        self, _mock_base_url, _mock_account_id,
        mock_put, _mock_identity, mock_rate_limiter,
    ):
        import requests as req
        mock_put.side_effect = req.exceptions.RequestException("PUT failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_update_studio_attack_draft(
                attack_id=10000001, name="Updated Attack",
                python_code="print('updated')", console="test",
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()


# ---------------------------------------------------------------------------
# run_studio_attack
# ---------------------------------------------------------------------------
class TestRunStudioAttackRateLimitingGate:
    """Verify gates on run_studio_attack: check before queue POST, record after response."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_check_limit_before_queue_post(
        self, _mock_base_url, _mock_account_id,
        mock_post, _mock_identity, mock_rate_limiter,
    ):
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        def post_side_effect(*args, **kwargs):
            call_order.append("api_call")
            return _mock_success_response(MOCK_QUEUE_API_RESPONSE)

        mock_post.side_effect = post_side_effect

        sb_run_studio_attack(
            attack_id=10000001, console="test",
            target_simulator_ids=["sim-uuid-1"],
        )

        assert call_order == ["check_limit", "api_call", "record_action"]
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "run_studio_attack"
        )
        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "run_studio_attack"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.post")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_record_action_not_called_on_api_failure(
        self, _mock_base_url, _mock_account_id,
        mock_post, _mock_identity, mock_rate_limiter,
    ):
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("Queue failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_run_studio_attack(
                attack_id=10000001, console="test",
                target_simulator_ids=["sim-uuid-1"],
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()


# ---------------------------------------------------------------------------
# set_studio_attack_status
# ---------------------------------------------------------------------------
MOCK_ALL_ATTACKS_RESPONSE = {
    "data": [
        {
            "id": 10000001,
            "name": "Test Attack",
            "status": "draft",
            "methodType": 5,
            "timeout": 300,
            "description": "test",
            "parameters": [],
            "tags": [],
        }
    ]
}

MOCK_TARGET_SOURCE_RESPONSE = {
    "data": {"filename": "target.py", "content": "print('hello')"}
}


class TestSetStudioAttackStatusRateLimitingGate:
    """Verify gates: check AFTER pre-check GET, before PUT. Record after cache invalidate."""

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.put")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_check_limit_after_precheck_before_put(
        self, _mock_base_url, _mock_account_id,
        mock_get, mock_put, _mock_identity, mock_rate_limiter,
    ):
        call_order = []
        mock_rate_limiter.check_limit.side_effect = (
            lambda *a, **kw: call_order.append("check_limit")
        )
        mock_rate_limiter.record_action.side_effect = (
            lambda *a, **kw: call_order.append("record_action")
        )

        # GET calls: first = list attacks (pre-check), second = target source
        def get_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "customMethods?" in url:
                call_order.append("precheck_get")
                return _mock_success_response(MOCK_ALL_ATTACKS_RESPONSE)
            elif "/files/target" in url:
                call_order.append("source_get")
                return _mock_success_response(MOCK_TARGET_SOURCE_RESPONSE)
            return _mock_success_response()

        mock_get.side_effect = get_side_effect

        def put_side_effect(*args, **kwargs):
            call_order.append("put_call")
            return _mock_success_response()

        mock_put.side_effect = put_side_effect

        sb_set_studio_attack_status(
            attack_id=10000001, new_status="published", console="test",
        )

        # Pre-check GETs happen BEFORE check_limit; PUT happens AFTER check_limit
        assert call_order.index("precheck_get") < call_order.index("check_limit")
        assert call_order.index("check_limit") < call_order.index("put_call")
        assert call_order.index("put_call") < call_order.index("record_action")
        mock_rate_limiter.check_limit.assert_called_once_with(
            "test-caller", "set_studio_attack_status"
        )
        mock_rate_limiter.record_action.assert_called_once_with(
            "test-caller", "set_studio_attack_status"
        )

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_gates_not_called_on_precheck_failure(
        self, _mock_base_url, _mock_account_id,
        mock_get, _mock_identity, mock_rate_limiter,
    ):
        """Pre-check GET fails → neither check_limit nor record_action called."""
        import requests as req
        mock_get.side_effect = req.exceptions.RequestException("List failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_set_studio_attack_status(
                attack_id=10000001, new_status="published", console="test",
            )

        mock_rate_limiter.check_limit.assert_not_called()
        mock_rate_limiter.record_action.assert_not_called()

    @patch("safebreach_mcp_studio.studio_functions.rate_limiter")
    @patch("safebreach_mcp_studio.studio_functions.get_caller_identity",
           return_value="test-caller")
    @patch("safebreach_mcp_studio.studio_functions.requests.put")
    @patch("safebreach_mcp_studio.studio_functions.requests.get")
    @patch("safebreach_mcp_studio.studio_functions.get_api_account_id",
           return_value="1234567890")
    @patch("safebreach_mcp_studio.studio_functions.get_api_base_url",
           return_value="https://test.safebreach.com")
    def test_record_action_not_called_on_put_failure(
        self, _mock_base_url, _mock_account_id,
        mock_get, mock_put, _mock_identity, mock_rate_limiter,
    ):
        """PUT fails → check_limit was called, record_action NOT called."""
        import requests as req

        # GET calls succeed (pre-check + source fetch)
        def get_side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "customMethods?" in url:
                return _mock_success_response(MOCK_ALL_ATTACKS_RESPONSE)
            elif "/files/target" in url:
                return _mock_success_response(MOCK_TARGET_SOURCE_RESPONSE)
            return _mock_success_response()

        mock_get.side_effect = get_side_effect
        mock_put.side_effect = req.exceptions.RequestException("PUT failed")

        with pytest.raises(req.exceptions.RequestException):
            sb_set_studio_attack_status(
                attack_id=10000001, new_status="published", console="test",
            )

        mock_rate_limiter.check_limit.assert_called_once()
        mock_rate_limiter.record_action.assert_not_called()
