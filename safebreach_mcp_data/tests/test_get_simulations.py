"""
Tests for the merged `get_simulations` data tool (SAF-29870, Phase J).

`get_simulations` replaces `get_test_simulations` (per-test, client-side filters) and
`get_simulation_results_by_tags` (account-wide, tags-only). Every filter is pushed into the
`executionsHistoryResults` Lucene query, so the tool works account-wide (`test_id` omitted) OR scoped
to a test, in any filter combination.

These are UNIT tests against a mocked `requests.post`: they prove filters are pushed server-side by
asserting the exact Lucene `query` string built for each filter combination. Real-ES verification (that
ES honors `finalStatus.keyword`, the `moveName` wildcard on the analyzed text field, tag casing, and
enum spellings such as `no-result` vs `no_result`) is deferred to live E2E (Phase F).

Field → Lucene mapping asserted here:
  test scope   -> runId:<id>
  status       -> finalStatus.keyword:<value>
  attack id    -> moveId:<id>
  attack name  -> moveName:*<lowercased term>*   (wildcard substring)
  time window  -> executionTime:[<start> TO <end>]   (open-ended with *)
  drift        -> driftType:* AND NOT driftType:no_drift
  tags         -> labels:<UPPER>   (single) / (labels:A OR labels:B) (multi)
Pagination stays client-side over the server-filtered set (same model as the tools it replaces).
"""

import asyncio

import pytest
from unittest.mock import patch, MagicMock

from safebreach_mcp_data import data_functions as df
from safebreach_mcp_data.data_functions import simulations_cache


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


# One filtered page then an empty page ends the fetch loop.
def _one_page(rows):
    return [_resp(rows), _resp([])]


_GUARD = "!labels:Ignore AND (!labels:Draft)"


class _Base:
    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    @pytest.fixture(autouse=True)
    def no_running_test_probe(self):
        # SAF-32018 running-test hint probes the orchestrator; keep unit tests deterministic.
        with patch("safebreach_mcp_data.data_functions._is_test_non_terminal", return_value=False):
            yield

    def setup_method(self):
        simulations_cache.clear()

    def teardown_method(self):
        simulations_cache.clear()


def _q(mock_post, i=0):
    return mock_post.call_args_list[i].kwargs["json"]["query"]


def _body(mock_post, i=0):
    return mock_post.call_args_list[i].kwargs["json"]


# --------------------------------------------------------------------------- #
# Query construction — one clause per filter
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsQueryConstruction(_Base):
    def test_within_test_scope_query(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(test_id="123")
        q = _q(mock_post)
        body = _body(mock_post)
        assert "/accounts/123/executionsHistoryResults" in mock_post.call_args_list[0].args[0]
        assert q.startswith(_GUARD)
        assert "runId:123" in q
        assert body["sortBy"] == "executionTime"
        assert body["orderBy"] == "desc"

    def test_account_wide_status_only(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(status_filter="missed")
        q = _q(mock_post)
        assert "finalStatus.keyword:missed" in q
        # account-wide → no runId clause
        assert "runId:" not in q

    def test_account_wide_attack_id_only(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(playbook_attack_id_filter="923")
        assert "moveId:923" in _q(mock_post)

    def test_account_wide_attack_name_wildcard(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(playbook_attack_name_filter="Trojan")
        q = _q(mock_post)
        # lowercased + leading/trailing wildcard to preserve substring semantics
        assert "moveName:*trojan*" in q

    def test_account_wide_time_window(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(start_time=1000, end_time=2000)
        assert "executionTime:[1000 TO 2000]" in _q(mock_post)

    def test_account_wide_start_time_only(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(start_time=1000)
        assert "executionTime:[1000 TO *]" in _q(mock_post)

    def test_account_wide_end_time_only(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(end_time=2000)
        assert "executionTime:[* TO 2000]" in _q(mock_post)

    def test_account_wide_drift_only(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(drifted_only=True)
        assert "driftType:* AND NOT driftType:no_drift" in _q(mock_post)

    def test_account_wide_single_tag(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(tags="production")
        assert "labels:PRODUCTION" in _q(mock_post)

    def test_account_wide_multi_tag_or(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(tags="prod,staging")
        q = _q(mock_post)
        assert "(labels:PROD OR labels:STAGING)" in q
        assert q.startswith(_GUARD + " AND ")


# --------------------------------------------------------------------------- #
# Filter combinations
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsFilterCombinations(_Base):
    def test_test_id_plus_tags(self, mock_post, *_):
        # by-tag search WITHIN a specific test
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(test_id="123", tags="prod")
        q = _q(mock_post)
        assert "runId:123" in q
        assert "labels:PROD" in q

    def test_status_plus_attack_name(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(status_filter="stopped", playbook_attack_name_filter="dns")
        q = _q(mock_post)
        assert "finalStatus.keyword:stopped" in q
        assert "moveName:*dns*" in q

    def test_all_filters_combined(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(
            test_id="123",
            status_filter="missed",
            playbook_attack_id_filter="923",
            playbook_attack_name_filter="trojan",
            start_time=1000,
            end_time=2000,
            drifted_only=True,
            tags="prod",
        )
        q = _q(mock_post)
        for clause in (
            "runId:123",
            "finalStatus.keyword:missed",
            "moveId:923",
            "moveName:*trojan*",
            "executionTime:[1000 TO 2000]",
            "driftType:* AND NOT driftType:no_drift",
            "labels:PROD",
        ):
            assert clause in q, f"missing clause: {clause}"


# --------------------------------------------------------------------------- #
# Require ≥1 filter when test_id is omitted (guard against whole-account dump)
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsRequireFilterGuard(_Base):
    def test_no_test_id_no_filters_raises(self, mock_post):
        with pytest.raises(ValueError):
            df.sb_get_simulations()
        mock_post.assert_not_called()

    def test_drifted_only_false_does_not_count_as_filter(self, mock_post):
        with pytest.raises(ValueError):
            df.sb_get_simulations(drifted_only=False)
        mock_post.assert_not_called()

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    def test_test_id_alone_is_allowed(self, _b, _a, _r, mock_post):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(test_id="123")  # no raise

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    def test_single_account_wide_filter_is_allowed(self, _b, _a, _r, mock_post):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(tags="prod")  # no raise

    @patch("safebreach_mcp_data.data_functions.check_rbac_response")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
    def test_drifted_only_true_counts_as_filter(self, _b, _a, _r, mock_post):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(drifted_only=True)  # no raise


# --------------------------------------------------------------------------- #
# Lucene special-char escaping of user-supplied values
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsLuceneEscaping(_Base):
    def test_escapes_special_chars_in_tag(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(tags="prod:v1")
        # colon escaped, value still uppercased
        assert r"labels:PROD\:V1" in _q(mock_post)

    def test_escapes_attack_name_but_keeps_builder_wildcards(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(playbook_attack_name_filter="a(b)c")
        q = _q(mock_post)
        # inner parens escaped; the builder's own surrounding * are NOT escaped
        assert r"moveName:*a\(b\)c*" in q

    def test_escapes_status_value(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(status_filter="odd:val")
        assert r"finalStatus.keyword:odd\:val" in _q(mock_post)


class TestLuceneEscapeHelper:
    def test_escapes_full_special_set(self):
        specials = ['+', '-', '&&', '||', '!', '(', ')', '{', '}',
                    '[', ']', '^', '"', '~', '*', '?', ':', '\\', '/']
        for ch in specials:
            out = df._lucene_escape(ch)
            # every character is backslash-prefixed (all chars in these tokens are special)
            assert out != ch
            assert out == ''.join('\\' + c for c in ch)

    def test_plain_value_unchanged(self):
        assert df._lucene_escape("hello") == "hello"


# --------------------------------------------------------------------------- #
# Pagination — client-side over the server-filtered set (same model as before)
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsPagination(_Base):
    def test_page_size_and_slice(self, mock_post, *_):
        mock_post.side_effect = [_resp([_raw_row(f"sim{i}") for i in range(12)]), _resp([])]
        result = df.sb_get_simulations(tags="production", page_number=0)
        assert len(result["simulations_in_page"]) == 10
        assert result["total_pages"] == 2
        assert result["total_simulations"] == 12
        assert "page_number=1" in (result["hint_to_agent"] or "")

    def test_multipage_fetch_aggregates(self, mock_post, *_):
        full = [_raw_row(f"sim{i}") for i in range(100)]
        mock_post.side_effect = [_resp(full), _resp([_raw_row("tail1")]), _resp([])]
        result = df.sb_get_simulations(tags="production")
        assert result["total_simulations"] == 101

    def test_negative_page_raises(self, mock_post, *_):
        with pytest.raises(ValueError):
            df.sb_get_simulations(tags="production", page_number=-1)
        mock_post.assert_not_called()


# --------------------------------------------------------------------------- #
# Result shape / mapping / validation (characterization of preserved behavior)
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsResultMapping(_Base):
    def test_result_shape_keys(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        result = df.sb_get_simulations(tags="production")
        for key in ("page_number", "total_pages", "total_simulations",
                    "simulations_in_page", "applied_filters", "hint_to_agent"):
            assert key in result

    def test_row_mapping_uses_reduced_entity(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        result = df.sb_get_simulations(tags="production")
        row = result["simulations_in_page"][0]
        assert row["simulation_id"] == "sim1"
        for key in ("status", "playbook_attack_id", "playbook_attack_name"):
            assert key in row

    def test_applied_filters_echoed(self, mock_post, *_):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        result = df.sb_get_simulations(test_id="123", status_filter="missed", tags="prod")
        af = result["applied_filters"]
        assert af.get("test_id") == "123"
        assert af.get("status_filter") == "missed"
        assert af.get("tags") == "prod"

    def test_rbac_checked(self, mock_post, _base, _acct, mock_rbac):
        mock_post.side_effect = _one_page([_raw_row("sim1")])
        df.sb_get_simulations(tags="production")
        assert mock_rbac.called

    def test_time_range_validation(self, mock_post, *_):
        with pytest.raises(ValueError):
            df.sb_get_simulations(test_id="1", start_time=2000, end_time=1000)
        mock_post.assert_not_called()

    def test_boolean_drifted_only_validation(self, mock_post, *_):
        with pytest.raises(ValueError):
            df.sb_get_simulations(test_id="1", drifted_only="nope")
        mock_post.assert_not_called()


# --------------------------------------------------------------------------- #
# SAF-32805 false-empty guard — preserved WITHIN a test only (option b)
# --------------------------------------------------------------------------- #
@patch("safebreach_mcp_data.data_functions.check_rbac_response")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="123")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://test.com")
@patch("safebreach_mcp_data.data_functions.requests.post")
class TestGetSimulationsFalseEmptyGuard(_Base):
    def test_within_test_zero_matches_but_test_has_sims_warns(self, mock_post, *_):
        # 1st (filtered) query → empty; 2nd (unfiltered, runId only) → the test has sims
        mock_post.side_effect = [
            _resp([]),                                   # filtered: 0 matches
            _resp([_raw_row("s1"), _raw_row("s2")]), _resp([]),   # unfiltered test population
        ]
        result = df.sb_get_simulations(test_id="123", status_filter="missed")
        assert result["total_simulations"] == 0
        hint = result["hint_to_agent"] or ""
        assert "0 of" in hint or "matched" in hint
        assert mock_post.call_count >= 2  # extra population query issued

    def test_account_wide_zero_matches_no_population_query(self, mock_post, *_):
        # account-wide (no test_id) → no second population query, generic empty hint
        mock_post.side_effect = [_resp([])]
        result = df.sb_get_simulations(tags="nope")
        assert result["total_simulations"] == 0
        assert mock_post.call_count == 1


# --------------------------------------------------------------------------- #
# Tool wrapper — renamed to get_simulations, old names gone
# --------------------------------------------------------------------------- #
class TestGetSimulationsToolWrapper:
    def _fn(self):
        from safebreach_mcp_data.data_server import data_server
        return data_server.mcp._tool_manager._tools["get_simulations"].fn

    def test_tool_registered(self):
        from safebreach_mcp_data.data_server import data_server
        names = [t.name for t in asyncio.run(data_server.mcp.list_tools())]
        assert "get_simulations" in names

    def test_old_tool_name_absent(self):
        from safebreach_mcp_data.data_server import data_server
        names = [t.name for t in asyncio.run(data_server.mcp.list_tools())]
        assert "get_test_simulations" not in names

    def test_deleted_by_tags_tool_absent(self):
        from safebreach_mcp_data.data_server import data_server
        names = [t.name for t in asyncio.run(data_server.mcp.list_tools())]
        assert "get_simulation_results_by_tags" not in names

    def test_tool_read_only(self):
        from safebreach_mcp_data.data_server import data_server
        tool = data_server.mcp._tool_manager._tools["get_simulations"]
        assert tool.annotations.readOnlyHint is True

    @patch("safebreach_mcp_data.data_server.sb_get_simulations")
    def test_wrapper_delegates(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(test_id="123", tags="prod", status_filter="missed",
                               console="c", page_number=2))
        kwargs = mock_sb.call_args.kwargs
        assert kwargs["test_id"] == "123"
        assert kwargs["tags"] == "prod"
        assert kwargs["status_filter"] == "missed"
        assert kwargs["console"] == "c"
        assert kwargs["page_number"] == 2

    @patch("safebreach_mcp_data.data_server.sb_get_simulations")
    def test_wrapper_optional_test_id_default_none(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(tags="prod"))
        assert mock_sb.call_args.kwargs.get("test_id") is None

    @patch("safebreach_mcp_data.data_server.sb_get_simulations")
    def test_wrapper_console_default(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(tags="prod"))
        assert mock_sb.call_args.kwargs["console"] == "default"

    @patch("safebreach_mcp_data.data_server.sb_get_simulations")
    def test_wrapper_timestamp_normalization(self, mock_sb):
        mock_sb.return_value = {"simulations_in_page": []}
        asyncio.run(self._fn()(test_id="1", start_time="2026-03-01T00:00:00Z"))
        # ISO normalized to epoch before delegation
        assert isinstance(mock_sb.call_args.kwargs["start_time"], int)

    @patch("safebreach_mcp_data.data_server.sb_get_simulations")
    def test_return_value_pass_through(self, mock_sb):
        sentinel = {"simulations_in_page": [{"simulation_id": "x"}], "total_simulations": 1}
        mock_sb.return_value = sentinel
        out = asyncio.run(self._fn()(tags="prod"))
        assert out is sentinel


# --------------------------------------------------------------------------- #
# Deleted symbols — the merge removes the duplicate tool + client-side filter
# --------------------------------------------------------------------------- #
class TestDeletedFunctionsGone:
    def test_sb_get_simulation_results_by_tags_removed(self):
        assert not hasattr(df, "sb_get_simulation_results_by_tags")

    def test_get_simulation_results_by_tags_from_api_removed(self):
        assert not hasattr(df, "_get_simulation_results_by_tags_from_api")

    def test_apply_simulation_filters_removed(self):
        assert not hasattr(df, "_apply_simulation_filters")

    def test_sb_get_test_simulations_removed(self):
        assert not hasattr(df, "sb_get_test_simulations")


# --------------------------------------------------------------------------- #
# Grep-guard — no dangling references to the old tool names in registered
# tool descriptions / hint strings (catches "missed a hint string" risk).
# --------------------------------------------------------------------------- #
class TestNoDanglingOldToolReferences:
    def test_registered_descriptions_have_no_old_names(self):
        from safebreach_mcp_data.data_server import data_server
        tools = asyncio.run(data_server.mcp.list_tools())
        blob = " ".join((t.description or "") for t in tools)
        assert "get_test_simulations" not in blob
        assert "get_simulation_results_by_tags" not in blob
