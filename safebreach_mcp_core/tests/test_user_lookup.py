"""Tests for safebreach_mcp_core.user_lookup — cached user ID → name resolution."""

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_core.user_lookup import get_user_name, _fetch_users_map, users_cache
from safebreach_mcp_core.token_context import _user_auth_artifacts


@pytest.fixture(autouse=True)
def set_auth_and_clear_cache():
    token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
    users_cache.clear()
    yield
    _user_auth_artifacts.reset(token)
    users_cache.clear()


class TestFetchUsersMap:
    """Tests for _fetch_users_map — config API user list."""

    @patch('safebreach_mcp_core.user_lookup.requests.get')
    @patch('safebreach_mcp_core.user_lookup.get_api_account_id')
    @patch('safebreach_mcp_core.user_lookup.get_api_base_url')
    def test_fetch_users_map_success(self, mock_base_url, mock_account_id, mock_get):
        """Returns {user_id: user_name} dict from config API."""
        mock_base_url.return_value = "https://test.safebreach.com"
        mock_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"id": 100001, "name": "sbadmin", "email": "admin@sb.com"},
                {"id": 100002, "name": "Yossi", "email": "yossi@sb.com"},
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = _fetch_users_map("test")

        assert result == {100001: "sbadmin", 100002: "Yossi"}
        assert "users" in mock_get.call_args[0][0]
        assert "deleted=true" in mock_get.call_args[0][0]

    @patch('safebreach_mcp_core.user_lookup.requests.get')
    @patch('safebreach_mcp_core.user_lookup.get_api_account_id')
    @patch('safebreach_mcp_core.user_lookup.get_api_base_url')
    def test_fetch_users_map_api_error_returns_empty(
        self, mock_base_url, mock_account_id, mock_get
    ):
        """Returns empty dict on API error (e.g., 403)."""
        mock_base_url.return_value = "https://test.safebreach.com"
        mock_account_id.return_value = "1234567890"

        mock_get.side_effect = Exception("403 Forbidden")

        result = _fetch_users_map("test")

        assert result == {}

    @patch('safebreach_mcp_core.user_lookup.requests.get')
    @patch('safebreach_mcp_core.user_lookup.get_api_account_id')
    @patch('safebreach_mcp_core.user_lookup.get_api_base_url')
    def test_fetch_users_map_cached(self, mock_base_url, mock_account_id, mock_get):
        """Second call uses cache, no API call."""
        mock_base_url.return_value = "https://test.safebreach.com"
        mock_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"id": 100001, "name": "sbadmin"}]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result1 = _fetch_users_map("test")
        result2 = _fetch_users_map("test")

        assert result1 == result2
        mock_get.assert_called_once()  # Only one API call


class TestGetUserName:
    """Tests for get_user_name — resolve ID to name."""

    @patch('safebreach_mcp_core.user_lookup._fetch_users_map')
    def test_get_user_name_found(self, mock_fetch):
        """Returns username when user ID exists in lookup."""
        mock_fetch.return_value = {100001: "sbadmin", 100002: "Yossi"}

        assert get_user_name(100001, "test") == "sbadmin"
        assert get_user_name(100002, "test") == "Yossi"

    @patch('safebreach_mcp_core.user_lookup._fetch_users_map')
    def test_get_user_name_not_found(self, mock_fetch):
        """Returns None when user ID not in lookup."""
        mock_fetch.return_value = {100001: "sbadmin"}

        assert get_user_name(999999, "test") is None

    @patch('safebreach_mcp_core.user_lookup._fetch_users_map')
    def test_get_user_name_none_id(self, mock_fetch):
        """Returns None when user ID is None."""
        mock_fetch.return_value = {100001: "sbadmin"}

        assert get_user_name(None, "test") is None
