"""
Tests for the playbook attack tag WRITE tools (SAF-29870, Phase B).

Three rate-limited write tools (the playbook server's first): add / remove / rename a custom tag
on a single playbook attack (move), calling the configuration service (`/content/v3`) through the
MCP gateway. Mirrors the studio write-tool pattern: validate → check_limit → mutate →
check_rbac_response → clear cache → record_action.
"""

from types import SimpleNamespace

import pytest
import requests
from unittest.mock import patch, MagicMock

from safebreach_mcp_playbook.playbook_functions import (
    sb_add_playbook_attack_tag,
    sb_remove_playbook_attack_tag,
    sb_rename_playbook_attack_tag,
    clear_playbook_cache,
)
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer

MOD = "safebreach_mcp_playbook.playbook_functions"
BASE_URL = "https://test.safebreach.com"
ACCOUNT = "1234567890"
EXPECTED_URL = f"{BASE_URL}/api/content/v3/accounts/{ACCOUNT}/moves/1027/tags"


def _ok_response(json_value=None):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = json_value if json_value is not None else {}
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
    """Patch the shared plumbing (rate limiter, base-url, account-id, caller-id)."""
    with patch(f"{MOD}.rate_limiter") as rate_limiter, \
         patch(f"{MOD}.get_caller_identity", return_value="test-caller") as caller, \
         patch(f"{MOD}.get_api_base_url", return_value=BASE_URL) as base_url, \
         patch(f"{MOD}.get_api_account_id", return_value=ACCOUNT) as account_id:
        yield SimpleNamespace(
            rate_limiter=rate_limiter, caller=caller, base_url=base_url, account_id=account_id
        )


# =========================================================================== #
# Tool 1 — sb_add_playbook_attack_tag (POST)
# =========================================================================== #
class TestAddPlaybookAttackTag:
    def test_url_method_body(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_ok_response()) as post:
            sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert post.call_args.args[0] == EXPECTED_URL
        assert post.call_args.kwargs["json"] == {"values": ["mytag"]}
        assert post.call_args.kwargs["timeout"] == 120
        assert post.call_args.kwargs["headers"]["Content-Type"] == "application/json"

    def test_gate_ordering(self, infra):
        order = []
        infra.rate_limiter.check_limit.side_effect = lambda *a: order.append("check_limit")
        infra.rate_limiter.record_action.side_effect = lambda *a: order.append("record_action")

        def _post(*a, **k):
            order.append("api_call")
            return _ok_response()

        with patch(f"{MOD}.requests.post", side_effect=_post):
            sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert order == ["check_limit", "api_call", "record_action"]
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "add_playbook_attack_tag")
        infra.rate_limiter.record_action.assert_called_once_with("test-caller", "add_playbook_attack_tag")

    def test_record_action_not_called_on_permission_error(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_ok_response()), \
             patch(f"{MOD}.check_rbac_response", side_effect=PermissionError("403")):
            with pytest.raises(PermissionError):
                sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        infra.rate_limiter.check_limit.assert_called_once()
        infra.rate_limiter.record_action.assert_not_called()

    def test_record_action_not_called_on_http_error(self, infra):
        bad = MagicMock()
        bad.status_code = 500
        bad.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        with patch(f"{MOD}.requests.post", return_value=bad):
            with pytest.raises(requests.exceptions.HTTPError):
                sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        infra.rate_limiter.record_action.assert_not_called()

    def test_cache_cleared_on_success_only(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_ok_response()), \
             patch(f"{MOD}.clear_playbook_cache") as clear:
            sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        clear.assert_called_once()

    def test_cache_not_cleared_on_failure(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_ok_response()), \
             patch(f"{MOD}.check_rbac_response", side_effect=PermissionError("403")), \
             patch(f"{MOD}.clear_playbook_cache") as clear:
            with pytest.raises(PermissionError):
                sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        clear.assert_not_called()

    def test_check_rbac_invoked(self, infra):
        resp = _ok_response()
        with patch(f"{MOD}.requests.post", return_value=resp), \
             patch(f"{MOD}.check_rbac_response") as rbac:
            sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        rbac.assert_called_once_with(resp)

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_empty_tag_raises_before_network(self, infra, bad):
        with patch(f"{MOD}.requests.post") as post:
            with pytest.raises(ValueError):
                sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value=bad)
        post.assert_not_called()
        infra.rate_limiter.check_limit.assert_not_called()

    def test_return_shape(self, infra):
        with patch(f"{MOD}.requests.post", return_value=_ok_response()):
            result = sb_add_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert result["attack_id"] == 1027
        assert result["tag_value"] == "mytag"
        assert result["action"] == "added"
        assert result["hint_to_agent"]


# =========================================================================== #
# Tool 2 — sb_remove_playbook_attack_tag (DELETE)
# =========================================================================== #
class TestRemovePlaybookAttackTag:
    def test_url_method_query(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_ok_response()) as delete:
            sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert delete.call_args.args[0] == EXPECTED_URL
        assert delete.call_args.kwargs["params"] == {"values": "mytag"}
        assert "json" not in delete.call_args.kwargs or delete.call_args.kwargs["json"] is None
        assert delete.call_args.kwargs["timeout"] == 120

    def test_gate_ordering(self, infra):
        order = []
        infra.rate_limiter.check_limit.side_effect = lambda *a: order.append("check_limit")
        infra.rate_limiter.record_action.side_effect = lambda *a: order.append("record_action")

        def _delete(*a, **k):
            order.append("api_call")
            return _ok_response()

        with patch(f"{MOD}.requests.delete", side_effect=_delete):
            sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert order == ["check_limit", "api_call", "record_action"]
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "remove_playbook_attack_tag")
        infra.rate_limiter.record_action.assert_called_once_with("test-caller", "remove_playbook_attack_tag")

    def test_record_action_not_called_on_failure(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_ok_response()), \
             patch(f"{MOD}.check_rbac_response", side_effect=PermissionError("403")):
            with pytest.raises(PermissionError):
                sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        infra.rate_limiter.record_action.assert_not_called()

    def test_cache_cleared_on_success(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_ok_response()), \
             patch(f"{MOD}.clear_playbook_cache") as clear:
            sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        clear.assert_called_once()

    @pytest.mark.parametrize("bad", ["", "   ", None])
    def test_empty_tag_raises_before_network(self, infra, bad):
        with patch(f"{MOD}.requests.delete") as delete:
            with pytest.raises(ValueError):
                sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value=bad)
        delete.assert_not_called()
        infra.rate_limiter.check_limit.assert_not_called()

    def test_return_shape(self, infra):
        with patch(f"{MOD}.requests.delete", return_value=_ok_response()):
            result = sb_remove_playbook_attack_tag(console="c", attack_id=1027, tag_value="mytag")
        assert result["attack_id"] == 1027
        assert result["tag_value"] == "mytag"
        assert result["action"] == "removed"
        assert result["hint_to_agent"]


# =========================================================================== #
# Tool 3 — sb_rename_playbook_attack_tag (PUT)
# =========================================================================== #
class TestRenamePlaybookAttackTag:
    def test_url_method_body(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_ok_response()) as put:
            sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="old", new_value="new")
        assert put.call_args.args[0] == EXPECTED_URL
        assert put.call_args.kwargs["json"] == {"oldValue": "old", "newValue": "new"}
        assert put.call_args.kwargs["timeout"] == 120
        assert put.call_args.kwargs["headers"]["Content-Type"] == "application/json"

    def test_gate_ordering(self, infra):
        order = []
        infra.rate_limiter.check_limit.side_effect = lambda *a: order.append("check_limit")
        infra.rate_limiter.record_action.side_effect = lambda *a: order.append("record_action")

        def _put(*a, **k):
            order.append("api_call")
            return _ok_response()

        with patch(f"{MOD}.requests.put", side_effect=_put):
            sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="old", new_value="new")
        assert order == ["check_limit", "api_call", "record_action"]
        infra.rate_limiter.check_limit.assert_called_once_with("test-caller", "rename_playbook_attack_tag")

    def test_record_action_not_called_on_failure(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_ok_response()), \
             patch(f"{MOD}.check_rbac_response", side_effect=PermissionError("403")):
            with pytest.raises(PermissionError):
                sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="old", new_value="new")
        infra.rate_limiter.record_action.assert_not_called()

    def test_cache_cleared_on_success(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_ok_response()), \
             patch(f"{MOD}.clear_playbook_cache") as clear:
            sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="old", new_value="new")
        clear.assert_called_once()

    @pytest.mark.parametrize("old,new", [("", "new"), ("old", ""), ("  ", "new"), (None, "new"), ("old", None)])
    def test_empty_values_raise_before_network(self, infra, old, new):
        with patch(f"{MOD}.requests.put") as put:
            with pytest.raises(ValueError):
                sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value=old, new_value=new)
        put.assert_not_called()
        infra.rate_limiter.check_limit.assert_not_called()

    def test_noop_rename_raises(self, infra):
        with patch(f"{MOD}.requests.put") as put:
            with pytest.raises(ValueError):
                sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="same", new_value="same")
        put.assert_not_called()

    def test_return_shape(self, infra):
        with patch(f"{MOD}.requests.put", return_value=_ok_response()):
            result = sb_rename_playbook_attack_tag(console="c", attack_id=1027, old_value="old", new_value="new")
        assert result["attack_id"] == 1027
        assert result["old_value"] == "old"
        assert result["new_value"] == "new"
        assert result["action"] == "renamed"
        assert result["hint_to_agent"]


# =========================================================================== #
# Server wrappers — annotations + delegation + error path
# =========================================================================== #
class TestWriteToolWrappers:
    def _tool(self, name):
        server = SafeBreachPlaybookServer()
        return server, server.mcp._tool_manager._tools[name]

    @pytest.mark.parametrize("name,expected_destructive", [
        ("add_playbook_attack_tag", False),
        ("remove_playbook_attack_tag", True),   # remove deletes data → destructive (matches manage_test)
        ("rename_playbook_attack_tag", False),  # update semantics, like update_studio_attack_draft
    ])
    def test_registered_and_write_annotations(self, name, expected_destructive):
        _, tool = self._tool(name)
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is expected_destructive

    @patch("safebreach_mcp_playbook.playbook_server.sb_add_playbook_attack_tag")
    def test_add_wrapper_delegates_and_markdown(self, mock_sb):
        mock_sb.return_value = {"attack_id": 1027, "tag_value": "mytag", "action": "added",
                                "hint_to_agent": "ok"}
        _, tool = self._tool("add_playbook_attack_tag")
        out = tool.fn(console="x", attack_id=1027, tag_value="mytag")
        assert mock_sb.call_args.kwargs["attack_id"] == 1027
        assert mock_sb.call_args.kwargs["tag_value"] == "mytag"
        assert isinstance(out, str)
        assert "mytag" in out

    @patch("safebreach_mcp_playbook.playbook_server.sb_rename_playbook_attack_tag")
    def test_rename_wrapper_delegates(self, mock_sb):
        mock_sb.return_value = {"attack_id": 1027, "old_value": "old", "new_value": "new",
                                "action": "renamed", "hint_to_agent": "ok"}
        _, tool = self._tool("rename_playbook_attack_tag")
        out = tool.fn(console="x", attack_id=1027, old_value="old", new_value="new")
        assert mock_sb.call_args.kwargs["old_value"] == "old"
        assert mock_sb.call_args.kwargs["new_value"] == "new"
        assert isinstance(out, str)

    @patch("safebreach_mcp_playbook.playbook_server.sb_add_playbook_attack_tag")
    def test_wrapper_error_path(self, mock_sb):
        mock_sb.side_effect = ValueError("bad")
        _, tool = self._tool("add_playbook_attack_tag")
        out = tool.fn(console="x", attack_id=1027, tag_value="mytag")
        assert isinstance(out, str)
        assert out.startswith("Error")
