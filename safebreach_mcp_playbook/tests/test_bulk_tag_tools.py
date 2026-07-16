"""
Tests for the BULK playbook attack tag tools (SAF-29870, Phase H, req 4).

Bulk add/remove/rename across many attacks/tags, wired to the configuration bulk endpoint
`/content/v3/accounts/{accountId}/moves/tags`, with guardrail caps (NFR) + partial-failure reporting.
"""

from types import SimpleNamespace

import pytest
import requests
from unittest.mock import patch, MagicMock

from safebreach_mcp_playbook.playbook_functions import (
    sb_bulk_add_playbook_attack_tags,
    sb_bulk_remove_playbook_attack_tags,
    sb_bulk_rename_playbook_attack_tag,
    clear_playbook_cache,
    MAX_BULK_ATTACK_IDS,
    MAX_BULK_TAG_VALUES,
)
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer

MOD = "safebreach_mcp_playbook.playbook_functions"
BASE_URL = "https://test.safebreach.com"
ACCOUNT = "1234567890"
BULK_URL = f"{BASE_URL}/api/content/v3/accounts/{ACCOUNT}/moves/tags"


def _resp(json_value):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = json_value
    return r


@pytest.fixture(autouse=True)
def _auth_ctx():
    from safebreach_mcp_core.token_context import _user_auth_artifacts
    token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
    yield
    _user_auth_artifacts.reset(token)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_playbook_cache()
    yield
    clear_playbook_cache()


@pytest.fixture
def infra():
    with patch(f"{MOD}.rate_limiter") as rate_limiter, \
         patch(f"{MOD}.get_caller_identity", return_value="test-caller") as caller, \
         patch(f"{MOD}.get_api_base_url", return_value=BASE_URL), \
         patch(f"{MOD}.get_api_account_id", return_value=ACCOUNT):
        yield SimpleNamespace(rate_limiter=rate_limiter, caller=caller)


# =========================================================================== #
# bulk add (POST body {moveIds, values})
# =========================================================================== #
class TestBulkAdd:
    def test_url_and_body(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_resp([])) as post:
            sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1027,2048", tag_values="prod,critical")
        assert post.call_args.args[0] == BULK_URL
        assert post.call_args.kwargs["json"] == {"moveIds": [1027, 2048], "values": ["prod", "critical"]}
        assert post.call_args.kwargs["timeout"] == 120

    def test_accepts_lists_too(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_resp([])) as post:
            sb_bulk_add_playbook_attack_tags(console="c", attack_ids=[1, 2, 3], tag_values=["a"])
        assert post.call_args.kwargs["json"] == {"moveIds": [1, 2, 3], "values": ["a"]}

    def test_gate_ordering(self, infra):
        order = []
        infra.rate_limiter.check_limit.side_effect = lambda *a: order.append("check_limit")
        infra.rate_limiter.record_action.side_effect = lambda *a: order.append("record_action")

        def _post(*a, **k):
            order.append("api_call")
            return _resp([])

        with patch(f"{MOD}.requests.post", side_effect=_post):
            sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1", tag_values="x")
        assert order == ["check_limit", "api_call", "record_action"]
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "bulk_add_playbook_attack_tags")

    def test_cap_attack_ids_guardrail(self, infra):
        too_many = ",".join(str(i) for i in range(MAX_BULK_ATTACK_IDS + 1))
        with patch(f"{MOD}.requests.post") as post:
            with pytest.raises(ValueError):
                sb_bulk_add_playbook_attack_tags(console="c", attack_ids=too_many, tag_values="x")
        post.assert_not_called()
        infra.rate_limiter.check_limit.assert_not_called()

    def test_cap_tag_values_guardrail(self, infra):
        too_many = ",".join(f"t{i}" for i in range(MAX_BULK_TAG_VALUES + 1))
        with patch(f"{MOD}.requests.post") as post:
            with pytest.raises(ValueError):
                sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1", tag_values=too_many)
        post.assert_not_called()

    @pytest.mark.parametrize("ids,vals", [("", "x"), ("1", ""), (None, "x"), ("1", None), ("abc", "x")])
    def test_invalid_inputs_raise_before_network(self, infra, ids, vals):
        with patch(f"{MOD}.requests.post") as post:
            with pytest.raises(ValueError):
                sb_bulk_add_playbook_attack_tags(console="c", attack_ids=ids, tag_values=vals)
        post.assert_not_called()

    def test_cache_cleared_on_success(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_resp([])), \
             patch(f"{MOD}.clear_playbook_cache") as clear:
            sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1", tag_values="x")
        clear.assert_called_once()

    def test_partial_failure_surfaced(self, infra):
        results = [{"moveId": 1, "tag": "x"},
                   {"moveId": 2, "status": "rejected", "reason": "Move 2 not found"}]
        with patch(f"{MOD}.requests.post", return_value=_resp(results)):
            r = sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1,2", tag_values="x")
        assert r["succeeded"] == 1
        assert r["failed_count"] == 1
        assert r["failures"][0]["moveId"] == 2
        assert r["action"] == "bulk_added"

    def test_record_action_not_called_on_failure(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_resp([])), \
             patch(f"{MOD}.check_rbac_response", side_effect=PermissionError("403")):
            with pytest.raises(PermissionError):
                sb_bulk_add_playbook_attack_tags(console="c", attack_ids="1", tag_values="x")
        infra.rate_limiter.record_action.assert_not_called()


# =========================================================================== #
# bulk remove (DELETE query moveIds|values pipe-delimited)
# =========================================================================== #
class TestBulkRemove:
    def test_url_and_pipe_query(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_resp([])) as delete:
            sb_bulk_remove_playbook_attack_tags(console="c", attack_ids="1027,2048", tag_values="prod,dev")
        assert delete.call_args.args[0] == BULK_URL
        assert delete.call_args.kwargs["params"] == {"moveIds": "1027|2048", "values": "prod|dev"}

    def test_gate_and_action_name(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_resp([])):
            sb_bulk_remove_playbook_attack_tags(console="c", attack_ids="1", tag_values="x")
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "bulk_remove_playbook_attack_tags")

    def test_cap_guardrail(self, infra):
        too_many = ",".join(str(i) for i in range(MAX_BULK_ATTACK_IDS + 1))
        with patch(f"{MOD}.requests.delete") as delete:
            with pytest.raises(ValueError):
                sb_bulk_remove_playbook_attack_tags(console="c", attack_ids=too_many, tag_values="x")
        delete.assert_not_called()


# =========================================================================== #
# bulk rename (PUT body {moveIds, oldValue, newValue})
# =========================================================================== #
class TestBulkRename:
    def test_url_and_body(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_resp([])) as put:
            sb_bulk_rename_playbook_attack_tag(console="c", attack_ids="1,2", old_value="old", new_value="new")
        assert put.call_args.args[0] == BULK_URL
        assert put.call_args.kwargs["json"] == {"moveIds": [1, 2], "oldValue": "old", "newValue": "new"}

    def test_noop_rename_raises(self, infra):
        with patch(f"{MOD}.requests.put") as put:
            with pytest.raises(ValueError):
                sb_bulk_rename_playbook_attack_tag(console="c", attack_ids="1", old_value="same", new_value="same")
        put.assert_not_called()

    @pytest.mark.parametrize("old,new", [("", "n"), ("o", ""), (None, "n")])
    def test_empty_values_raise(self, infra, old, new):
        with patch(f"{MOD}.requests.put") as put:
            with pytest.raises(ValueError):
                sb_bulk_rename_playbook_attack_tag(console="c", attack_ids="1", old_value=old, new_value=new)
        put.assert_not_called()

    def test_gate_action_name(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_resp([])):
            sb_bulk_rename_playbook_attack_tag(console="c", attack_ids="1", old_value="a", new_value="b")
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "bulk_rename_playbook_attack_tag")


# =========================================================================== #
# server wrappers — annotations + delegation
# =========================================================================== #
class TestBulkWrappers:
    def _tool(self, name):
        server = SafeBreachPlaybookServer()
        return server.mcp._tool_manager._tools[name]

    @pytest.mark.parametrize("name,destructive", [
        ("bulk_add_playbook_attack_tags", False),
        ("bulk_remove_playbook_attack_tags", True),
        ("bulk_rename_playbook_attack_tag", False),
    ])
    def test_registered_write_annotations(self, name, destructive):
        tool = self._tool(name)
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is destructive

    @patch("safebreach_mcp_playbook.playbook_server.sb_bulk_add_playbook_attack_tags")
    def test_add_wrapper_delegates(self, mock_sb):
        mock_sb.return_value = {"attack_ids": [1, 2], "succeeded": 2, "failed_count": 0, "hint_to_agent": "ok"}
        tool = self._tool("bulk_add_playbook_attack_tags")
        out = tool.fn(console="c", attack_ids="1,2", tag_values="x")
        assert mock_sb.call_args.kwargs["attack_ids"] == "1,2"
        assert mock_sb.call_args.kwargs["tag_values"] == "x"
        assert isinstance(out, str)

    @patch("safebreach_mcp_playbook.playbook_server.sb_bulk_add_playbook_attack_tags")
    def test_wrapper_error_path(self, mock_sb):
        mock_sb.side_effect = ValueError("too many")
        tool = self._tool("bulk_add_playbook_attack_tags")
        out = tool.fn(console="c", attack_ids="1", tag_values="x")
        assert isinstance(out, str)
        assert out.startswith("Error")
