"""
Tests for the data "simulation results by tags" retrieval tool (SAF-29870, Phase C).

Covers:
- `sb_get_simulation_results_by_tags` business function (Lucene `labels:` query construction,
  pagination, mapping, validation)
- the `get_simulation_results_by_tags` async MCP tool wrapper (dict, readOnlyHint=True)
"""

import asyncio

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_data.data_functions import (
    sb_get_simulation_results_by_tags,
    simulations_cache,
)


def _resp(rows):
    """Build a mock requests response whose .json() returns {'simulations': rows}."""
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status.return_value = None
    r.json.return_value = {"simulations": rows}
    return r


def _raw_row(sim_id, labels=None):
    return {
        "id": sim_id,
        "planName": "Test Plan",
        "planRunId": "run-1",
        "finalStatus": "missed",
        "moveId": 1027,
        "moveName": "DNS queries",
        "labels": labels or ["PRODUCTION"],
    }


class TestGetSimulationResultsByTags:
    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        simulations_cache.clear()

    def teardown_method(self):
        simulations_cache.clear()

    # ---- query construction ------------------------------------------------ #
    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_single_tag_query_construction(self, mock_post, *_):
        mock_post.side_effect = [_resp([_raw_row("sim1")]), _resp([])]
        sb_get_simulation_results_by_tags(console="default", tags="production")

        url = mock_post.call_args_list[0].args[0]
        body = mock_post.call_args_list[0].kwargs["json"]
        headers = mock_post.call_args_list[0].kwargs["headers"]
        assert "/accounts/123/executionsHistoryResults" in url
        assert "labels:PRODUCTION" in body["query"]
        assert body["query"].startswith("!labels:Ignore AND (!labels:Draft)")
        assert body["pageSize"] == 100
        assert body["sortBy"] == "executionTime"
        assert body["orderBy"] == "desc"
        assert headers["x-apitoken"] == "test-token"
        assert mock_post.call_args_list[0].kwargs["timeout"] == 120

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_multi_tag_or_query(self, mock_post, *_):
        mock_post.side_effect = [_resp([_raw_row("sim1")]), _resp([])]
        sb_get_simulation_results_by_tags(tags="prod,staging")
        query = mock_post.call_args_list[0].kwargs["json"]["query"]
        assert "(labels:PROD OR labels:STAGING)" in query
        # the tag clause is AND-joined to the guard, not OR at top level
        assert query.startswith("!labels:Ignore AND (!labels:Draft) AND ")

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_case_normalization_uppercases_tags(self, mock_post, *_):
        for value in ("Production", "PRODUCTION"):
            mock_post.reset_mock()
            mock_post.side_effect = [_resp([_raw_row("sim1")]), _resp([])]
            sb_get_simulation_results_by_tags(tags=value)
            assert "labels:PRODUCTION" in mock_post.call_args_list[0].kwargs["json"]["query"]

    # ---- result shape / mapping ------------------------------------------- #
    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_result_mapping_and_shape(self, mock_post, *_):
        mock_post.side_effect = [_resp([_raw_row("sim1"), _raw_row("sim2")]), _resp([])]
        result = sb_get_simulation_results_by_tags(tags="production")
        assert result["total_simulations"] == 2
        assert result["simulations_in_page"][0]["simulation_id"] == "sim1"
        for key in ("page_number", "total_pages", "simulations_in_page", "applied_filters"):
            assert key in result
        assert result["applied_filters"]["tags"] == "production"

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_no_match_returns_empty(self, mock_post, *_):
        mock_post.side_effect = [_resp([])]
        result = sb_get_simulation_results_by_tags(tags="production")
        assert result["total_simulations"] == 0
        assert result["simulations_in_page"] == []

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_pagination(self, mock_post, *_):
        page1 = [_raw_row(f"sim{i}") for i in range(12)]
        mock_post.side_effect = [_resp(page1), _resp([])]
        result = sb_get_simulation_results_by_tags(tags="production", page_number=0)
        assert len(result["simulations_in_page"]) == 10
        assert result["total_pages"] == 2
        assert "page_number=1" in (result["hint_to_agent"] or "")

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_multipage_fetch_aggregates(self, mock_post, *_):
        full_page = [_raw_row(f"sim{i}") for i in range(100)]
        mock_post.side_effect = [_resp(full_page), _resp([_raw_row("tail1"), _raw_row("tail2")]), _resp([])]
        result = sb_get_simulation_results_by_tags(tags="production")
        assert result["total_simulations"] == 102
        assert mock_post.call_count == 2  # 2nd page returned <100 rows → loop stops

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_rbac_checked(self, mock_post, _base, _acct, mock_rbac):
        mock_post.side_effect = [_resp([_raw_row("sim1")]), _resp([])]
        sb_get_simulation_results_by_tags(tags="production")
        assert mock_rbac.called

    # ---- validation -------------------------------------------------------- #
    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_empty_tags_raises_before_network(self, mock_post):
        with pytest.raises(ValueError):
            sb_get_simulation_results_by_tags(tags="")
        mock_post.assert_not_called()

    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_whitespace_only_tags_raises(self, mock_post):
        with pytest.raises(ValueError):
            sb_get_simulation_results_by_tags(tags="  , ")
        mock_post.assert_not_called()

    @patch("safebreach_mcp_data.data_functions.requests.post")
    def test_negative_page_raises(self, mock_post):
        with pytest.raises(ValueError):
            sb_get_simulation_results_by_tags(tags="production", page_number=-1)


class TestSimulationResultsByTagsToolWrapper:
    def _fn(self):
        from safebreach_mcp_data.data_server import data_server
        return data_server.mcp._tool_manager._tools["get_simulation_results_by_tags"].fn

    def test_tool_registered(self):
        from safebreach_mcp_data.data_server import data_server
        names = [t.name for t in asyncio.run(data_server.mcp.list_tools())]
        assert "get_simulation_results_by_tags" in names

    def test_tool_read_only(self):
        from safebreach_mcp_data.data_server import data_server
        tool = data_server.mcp._tool_manager._tools["get_simulation_results_by_tags"]
        assert tool.annotations.readOnlyHint is True

    @patch("safebreach_mcp_data.data_server.sb_get_simulation_results_by_tags")
    def test_wrapper_delegates(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(tags="prod", console="c", page_number=2))
        kwargs = mock_sb.call_args.kwargs
        assert kwargs["tags"] == "prod"
        assert kwargs["console"] == "c"
        assert kwargs["page_number"] == 2

    @patch("safebreach_mcp_data.data_server.sb_get_simulation_results_by_tags")
    def test_wrapper_console_default(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(tags="prod"))
        assert mock_sb.call_args.kwargs["console"] == "default"

    @patch("safebreach_mcp_data.data_server.sb_get_simulation_results_by_tags")
    def test_return_value_pass_through(self, mock_sb):
        sentinel = {"simulations_in_page": [{"simulation_id": "x"}], "total_simulations": 1}
        mock_sb.return_value = sentinel
        out = asyncio.run(self._fn()(tags="prod"))
        assert out is sentinel
