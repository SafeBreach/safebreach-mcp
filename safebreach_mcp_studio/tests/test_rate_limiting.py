"""Gate integration tests — verify manage_test calls check_limit/record_action correctly."""

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_studio.studio_functions import sb_manage_test
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
