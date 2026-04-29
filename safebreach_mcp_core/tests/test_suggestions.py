"""
Tests for the execution history suggestions helper (SAF-28331 Phase 1).

TDD tests for safebreach_mcp_core/suggestions.py covering:
- Happy-path API call and response parsing
- Cache hit/miss behavior
- Invalid collection name handling
- Empty collection handling
- API error propagation (401, timeout)
- Key-only extraction (doc_count discarded)
"""

from unittest.mock import patch, MagicMock

import pytest
import requests as req

from safebreach_mcp_core.suggestions import (
    get_suggestions_for_collection,
    suggestions_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SUGGESTIONS_RESPONSE = {
    "completion": {
        "security_product": [
            {"key": "Microsoft Defender for Endpoint", "doc_count": 500},
            {"key": "CrowdStrike Falcon", "doc_count": 300},
        ],
        "security_controls": [
            {"key": "Endpoint", "doc_count": 200},
            {"key": "Network", "doc_count": 150},
        ],
        "attack_type": [
            {"key": "host", "doc_count": 1000},
        ],
    }
}


# ---------------------------------------------------------------------------
# Tests: get_suggestions_for_collection
# ---------------------------------------------------------------------------

class TestGetSuggestionsForCollection:
    """Tests for the shared suggestions helper."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        """Set up auth context for all tests (SAF-29974)."""
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        """Clear the suggestions cache before each test."""
        suggestions_cache.clear()

    # --- Happy path ---

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_success(self, mock_account, mock_url, mock_get):
        """Calls API, parses response, returns list of keys for valid collection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_SUGGESTIONS_RESPONSE
        mock_get.return_value = mock_response

        result = get_suggestions_for_collection("demo", "security_product")

        assert result == ["Microsoft Defender for Endpoint", "CrowdStrike Falcon"]
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "/api/data/v1/accounts/12345/executionsHistorySuggestions" in call_url
        call_headers = mock_get.call_args[1].get("headers", {})
        assert call_headers.get("x-apitoken") == "test-token"

    # --- Caching ---

    @patch("safebreach_mcp_core.suggestions.is_caching_enabled", return_value=True)
    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_cache_hit(self, mock_account, mock_url, mock_get, mock_cache_enabled):
        """Second call returns cached data; requests.get called only once."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_SUGGESTIONS_RESPONSE
        mock_get.return_value = mock_response

        result1 = get_suggestions_for_collection("demo", "security_product")
        result2 = get_suggestions_for_collection("demo", "security_product")

        assert result1 == ["Microsoft Defender for Endpoint", "CrowdStrike Falcon"]
        assert result2 == ["Microsoft Defender for Endpoint", "CrowdStrike Falcon"]
        assert mock_get.call_count == 1

    @patch("safebreach_mcp_core.suggestions.is_caching_enabled", return_value=True)
    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_cache_miss_stores(self, mock_account, mock_url, mock_get, mock_cache_enabled):
        """First call stores result in cache; verified via suggestions_cache.get()."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_SUGGESTIONS_RESPONSE
        mock_get.return_value = mock_response

        get_suggestions_for_collection("demo", "security_product")

        from safebreach_mcp_core.token_context import get_cache_user_suffix
        cached = suggestions_cache.get(f"demo_security_product{get_cache_user_suffix()}")
        assert cached is not None
        # Cache stores full entries (key + doc_count), not just keys
        assert [e["key"] for e in cached] == [
            "Microsoft Defender for Endpoint", "CrowdStrike Falcon",
        ]

    # --- Error handling ---

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_invalid_collection(self, mock_account, mock_url, mock_get):
        """Unknown collection raises ValueError listing available collection names."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_SUGGESTIONS_RESPONSE
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="security_product"):
            get_suggestions_for_collection("demo", "nonexistent_collection")

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_empty_collection(self, mock_account, mock_url, mock_get):
        """Collection exists with empty entries — returns empty list, no error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "completion": {
                "empty_collection": [],
                "security_product": [{"key": "A", "doc_count": 1}],
            }
        }
        mock_get.return_value = mock_response

        result = get_suggestions_for_collection("demo", "empty_collection")

        assert result == []

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_api_401(self, mock_account, mock_url, mock_get):
        """401 response raises ValueError mentioning authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="[Aa]uthenticat"):
            get_suggestions_for_collection("demo", "security_product")

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_api_timeout(self, mock_account, mock_url, mock_get):
        """Timeout is propagated."""
        mock_get.side_effect = req.exceptions.Timeout("timed out")

        with pytest.raises(req.exceptions.Timeout):
            get_suggestions_for_collection("demo", "security_product")

    # --- Key extraction ---

    @patch("safebreach_mcp_core.suggestions.requests.get")

    @patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
    def test_get_suggestions_extracts_keys_only(self, mock_account, mock_url, mock_get):
        """Only 'key' string values extracted; doc_count discarded."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "completion": {
                "test_col": [
                    {"key": "Alpha", "doc_count": 999},
                    {"key": "Beta", "doc_count": 1},
                    {"key": "Gamma", "doc_count": 42},
                ]
            }
        }
        mock_get.return_value = mock_response

        result = get_suggestions_for_collection("demo", "test_col")

        assert result == ["Alpha", "Beta", "Gamma"]
        assert all(isinstance(item, str) for item in result)

