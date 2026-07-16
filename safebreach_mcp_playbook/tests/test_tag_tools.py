"""
Tests for the playbook "by tags" retrieval tool (SAF-29870, Phase C).

Covers:
- `transform_reduced_playbook_attack(..., include_tags=True)` exposing a `tags` list
- `filter_attacks_by_criteria(..., tag_filter=...)` (comma-separated OR, case-insensitive EXACT)
- `sb_get_playbook_attacks_by_tags` business function
- the `get_playbook_attacks_by_tags` MCP tool wrapper (Markdown, readOnlyHint=True)
"""

import pytest
from unittest.mock import patch

from safebreach_mcp_playbook.playbook_functions import (
    sb_get_playbook_attacks_by_tags,
    sb_get_playbook_attack_tags,
    clear_playbook_cache,
)
from safebreach_mcp_playbook.playbook_types import (
    filter_attacks_by_criteria,
    transform_reduced_playbook_attack,
)
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer


# --------------------------------------------------------------------------- #
# Fixtures — raw API-shaped attacks (what _get_all_attacks_from_cache_or_api returns)
# --------------------------------------------------------------------------- #
def _custom_tags(*values):
    """Build a move `tags` array holding a custom-tag ('Tags') group with the given values."""
    return [{"id": 99, "name": "Tags",
             "values": [{"id": i + 1, "value": v, "sort": -1} for i, v in enumerate(values)]}]


@pytest.fixture
def raw_attacks_with_tags():
    return [
        # custom tags network, dns
        {"id": 1027, "name": "DNS queries of malicious URLs", "description": "dns test",
         "modifiedDate": "2024-10-07T07:28:05.000Z", "publishedDate": "2019-05-29T15:18:44.000Z",
         "tags": _custom_tags("network", "dns"), "content": {}},
        # custom tags file, http
        {"id": 2048, "name": "File transfer via HTTP", "description": "http test",
         "modifiedDate": "2024-01-15T10:30:00.000Z", "publishedDate": "2020-03-10T12:00:00.000Z",
         "tags": _custom_tags("file", "http"), "content": {}},
        # ONLY a classification (sector) group, NO custom tags — must never match a tag query
        {"id": 3099, "name": "Banking sector attack", "description": "classification only",
         "modifiedDate": "2024-02-20T09:00:00.000Z", "publishedDate": "2021-06-01T00:00:00.000Z",
         "tags": [{"id": 14, "name": "sector",
                   "values": [{"id": 1, "value": "Banking", "displayName": "Banking"}]}],
         "content": {}},
    ]


# --------------------------------------------------------------------------- #
# transform_reduced_playbook_attack — include_tags
# --------------------------------------------------------------------------- #
class TestReducedTransformIncludesTags:
    def test_default_transform_has_no_tags(self, raw_attacks_with_tags):
        reduced = transform_reduced_playbook_attack(raw_attacks_with_tags[0])
        assert "tags" not in reduced

    def test_include_tags_extracts_custom_values(self, raw_attacks_with_tags):
        reduced = transform_reduced_playbook_attack(raw_attacks_with_tags[0], include_tags=True)
        assert reduced["tags"] == ["network", "dns"]

    def test_include_tags_ignores_classification(self, raw_attacks_with_tags):
        # move 3099 has only a 'sector' classification group and no custom 'Tags' group
        reduced = transform_reduced_playbook_attack(raw_attacks_with_tags[2], include_tags=True)
        assert reduced["tags"] == []

    def test_include_tags_missing_tags_is_empty_list(self):
        reduced = transform_reduced_playbook_attack({"id": 1, "name": "x"}, include_tags=True)
        assert reduced["tags"] == []


# --------------------------------------------------------------------------- #
# filter_attacks_by_criteria — tag_filter
# --------------------------------------------------------------------------- #
class TestFilterAttacksByTags:
    @pytest.fixture
    def reduced(self):
        return [
            {"id": 1027, "name": "a", "tags": ["network", "dns"]},
            {"id": 2048, "name": "b", "tags": ["file", "http"]},
            {"id": 3099, "name": "c", "tags": ["sector:Banking"]},
            {"id": 4000, "name": "d", "tags": []},
        ]

    def test_none_passthrough(self, reduced):
        assert filter_attacks_by_criteria(reduced, tag_filter=None) == reduced

    def test_single_tag(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter="network")
        assert [a["id"] for a in out] == [1027]

    def test_multi_tag_or(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter="dns,http")
        assert {a["id"] for a in out} == {1027, 2048}

    def test_nested_tag_value(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter="sector:Banking")
        assert [a["id"] for a in out] == [3099]

    def test_case_insensitive(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter="NETWORK")
        assert [a["id"] for a in out] == [1027]

    def test_exact_match_not_substring(self, reduced):
        # "net" must NOT match "network" (tags are discrete tokens, exact match)
        out = filter_attacks_by_criteria(reduced, tag_filter="net")
        assert out == []

    def test_attack_without_tags_excluded(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter="network")
        assert all(a["id"] != 4000 for a in out)

    def test_whitespace_and_mixed_case_multi(self, reduced):
        out = filter_attacks_by_criteria(reduced, tag_filter=" Network , HTTP ")
        assert {a["id"] for a in out} == {1027, 2048}


# --------------------------------------------------------------------------- #
# sb_get_playbook_attacks_by_tags
# --------------------------------------------------------------------------- #
class TestGetPlaybookAttacksByTags:
    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_single_tag_happy_path(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(console="default", tags="network")
        assert result["total_attacks"] == 1
        assert result["attacks_in_page"][0]["id"] == 1027
        assert "network" in result["attacks_in_page"][0]["tags"]
        assert result["applied_filters"]["tags"] == "network"

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_multi_tag_or_semantics(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(tags="dns,http")
        assert {a["id"] for a in result["attacks_in_page"]} == {1027, 2048}

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_classification_tag_not_matched(self, mock_get_all, raw_attacks_with_tags):
        # 'Banking' is a classification (sector) tag, not a custom tag → must not match
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(tags="Banking")
        assert result["total_attacks"] == 0

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_case_insensitivity(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(tags="NETWORK")
        assert [a["id"] for a in result["attacks_in_page"]] == [1027]

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_no_match_returns_empty(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(tags="nonexistent")
        assert result["total_attacks"] == 0
        assert result["attacks_in_page"] == []

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_tags_present_on_results(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        result = sb_get_playbook_attacks_by_tags(tags="dns,http,sector:Banking")
        for attack in result["attacks_in_page"]:
            assert isinstance(attack["tags"], list)

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_empty_tags_raises(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        with pytest.raises(ValueError):
            sb_get_playbook_attacks_by_tags(tags="")

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_whitespace_only_tags_raises(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        with pytest.raises(ValueError):
            sb_get_playbook_attacks_by_tags(tags="   ,  ")

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_negative_page_raises(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        with pytest.raises(ValueError):
            sb_get_playbook_attacks_by_tags(tags="network", page_number=-1)

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_pagination_shape(self, mock_get_all):
        mock_get_all.return_value = [
            {"id": i, "name": f"attack-{i}", "description": "d", "tags": _custom_tags("bulk"), "content": {}}
            for i in range(12)
        ]
        result = sb_get_playbook_attacks_by_tags(tags="bulk", page_number=0)
        assert result["total_attacks"] == 12
        assert len(result["attacks_in_page"]) == 10
        assert result["total_pages"] == 2
        assert "page_number=1" in (result["hint_to_agent"] or "")


# --------------------------------------------------------------------------- #
# get_playbook_attacks_by_tags MCP tool wrapper
# --------------------------------------------------------------------------- #
class TestGetPlaybookAttacksByTagsTool:
    def _fn(self, server):
        return server.mcp._tool_manager._tools["get_playbook_attacks_by_tags"].fn

    def test_tool_registered(self):
        server = SafeBreachPlaybookServer()
        assert "get_playbook_attacks_by_tags" in server.mcp._tool_manager._tools

    def test_tool_read_only_hint(self):
        server = SafeBreachPlaybookServer()
        tool = server.mcp._tool_manager._tools["get_playbook_attacks_by_tags"]
        assert tool.annotations.readOnlyHint is True

    @patch("safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks_by_tags")
    def test_wrapper_delegates_and_returns_markdown(self, mock_sb):
        mock_sb.return_value = {
            "attacks_in_page": [{"name": "DNS thing", "id": 1027, "tags": ["network"]}],
            "total_attacks": 1, "page_number": 0, "total_pages": 1,
            "applied_filters": {"tags": "network"}, "hint_to_agent": None,
        }
        server = SafeBreachPlaybookServer()
        out = self._fn(server)(tags="network")
        mock_sb.assert_called_once()
        assert mock_sb.call_args.kwargs["tags"] == "network"
        assert mock_sb.call_args.kwargs["console"] == "default"
        assert isinstance(out, str)
        assert "Playbook Attacks" in out
        assert "DNS thing" in out

    @patch("safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks_by_tags")
    def test_wrapper_error_dict_becomes_error_string(self, mock_sb):
        mock_sb.return_value = {"error": "boom"}
        server = SafeBreachPlaybookServer()
        out = self._fn(server)(tags="network")
        assert isinstance(out, str)
        assert out.startswith("Error")


# --------------------------------------------------------------------------- #
# get_playbook_attack_tags (Phase G — retrieve tags on a given attack, req 3)
# --------------------------------------------------------------------------- #
class TestGetPlaybookAttackTags:
    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        clear_playbook_cache()

    def teardown_method(self):
        clear_playbook_cache()

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_returns_custom_tags(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        r = sb_get_playbook_attack_tags(console="default", attack_id=1027)
        assert r["attack_id"] == 1027
        assert r["tags"] == ["network", "dns"]
        assert r["hint_to_agent"]

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_classification_only_returns_empty(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        r = sb_get_playbook_attack_tags(console="default", attack_id=3099)
        assert r["tags"] == []

    def test_missing_attack_id_raises(self):
        with pytest.raises(ValueError):
            sb_get_playbook_attack_tags(console="default", attack_id=None)

    @patch("safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api")
    def test_attack_not_found_raises(self, mock_get_all, raw_attacks_with_tags):
        mock_get_all.return_value = raw_attacks_with_tags
        with pytest.raises(ValueError):
            sb_get_playbook_attack_tags(console="default", attack_id=999999)

    def test_tool_registered_read_only(self):
        server = SafeBreachPlaybookServer()
        tool = server.mcp._tool_manager._tools["get_playbook_attack_tags"]
        assert tool.annotations.readOnlyHint is True

    @patch("safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_tags")
    def test_wrapper_delegates(self, mock_sb):
        mock_sb.return_value = {"attack_id": 1027, "tags": ["network"], "hint_to_agent": "ok"}
        server = SafeBreachPlaybookServer()
        out = server.mcp._tool_manager._tools["get_playbook_attack_tags"].fn(attack_id=1027)
        assert mock_sb.call_args.kwargs["attack_id"] == 1027
        assert isinstance(out, str)
        assert "network" in out
