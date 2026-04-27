"""Tests for SAF-29865 tool-disable filtering.

The deny list is read from the `DISABLE_TOOL_LIST` env var at server start.
Listed tools are stripped from `tools/list` and rejected by `tools/call`
inside this server.

Scope: this layer is the operator's deploy-time pin — set the env var when
launching safebreach-mcp to permanently hide tools regardless of caller.
The SAF-29865 AI-actions gate (FF + consent) is enforced separately in the
mcp-proxy gateway by filtering tools/list responses and rejecting
tools/call requests at the proxy edge — see mcp-proxy's `gateway.py`."""

import asyncio

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp.exceptions import ToolError
from safebreach_mcp_core import safebreach_base as mod


def _make_tool(name: str):
    return SimpleNamespace(name=name)


def _build_base_with_tools(tools_by_name: dict):
    """Construct a SafeBreachMCPBase, attach a fake tool manager, install
    the filter. Caller monkeypatches `_DISABLE_TOOL_LIST` to drive scenarios."""
    with patch.object(mod, "SafeBreachAuth"):
        base = mod.SafeBreachMCPBase("test-server")

    fake_manager = MagicMock()
    fake_manager.list_tools.side_effect = lambda: list(tools_by_name.values())
    fake_manager.get_tool.side_effect = lambda name: tools_by_name.get(name)

    async def call_tool(name, arguments, context=None, convert_result=False):
        return {"executed": name}

    fake_manager.call_tool.side_effect = call_tool
    base.mcp._tool_manager = fake_manager

    async def _noop_app(scope, receive, send):
        pass

    base._install_disable_filtering(_noop_app)
    return base


class TestParseDisableToolList:
    """Pure parser — no env-var juggling needed."""

    def test_none_is_empty(self):
        assert mod._parse_disable_tool_list(None) == frozenset()

    def test_empty_string_is_empty(self):
        assert mod._parse_disable_tool_list('') == frozenset()

    def test_valid_json_array_is_parsed(self):
        assert mod._parse_disable_tool_list('["save_x","run_y"]') == frozenset({"save_x", "run_y"})

    def test_blank_names_are_stripped(self):
        assert mod._parse_disable_tool_list('["run_y",""]') == frozenset({"run_y"})

    def test_invalid_json_is_ignored(self):
        assert mod._parse_disable_tool_list('not-json') == frozenset()

    def test_non_array_json_is_ignored(self):
        assert mod._parse_disable_tool_list('{"save":"x"}') == frozenset()

    def test_non_string_elements_are_ignored(self):
        assert mod._parse_disable_tool_list('["ok", 42]') == frozenset()


class TestDenyList:
    """Listed tools are unreachable — hidden from list_tools, rejected by call_tool."""

    def test_listed_tool_hidden(self, monkeypatch):
        monkeypatch.setenv('DISABLE_TOOL_LIST', '["banned"]')
        base = _build_base_with_tools({
            "banned": _make_tool("banned"),
            "safe": _make_tool("safe"),
        })

        names = [t.name for t in base.mcp._tool_manager.list_tools()]
        assert names == ["safe"]

    def test_listed_tool_call_blocked(self, monkeypatch):
        monkeypatch.setenv('DISABLE_TOOL_LIST', '["banned"]')
        base = _build_base_with_tools({"banned": _make_tool("banned")})

        with pytest.raises(ToolError, match="disabled by the server administrator"):
            asyncio.run(base.mcp._tool_manager.call_tool("banned", {}))

    def test_empty_deny_list_is_passthrough(self, monkeypatch):
        monkeypatch.delenv('DISABLE_TOOL_LIST', raising=False)
        base = _build_base_with_tools({
            "writable": _make_tool("writable"),
            "safe": _make_tool("safe"),
        })

        names = sorted(t.name for t in base.mcp._tool_manager.list_tools())
        assert names == ["safe", "writable"]

    def test_unlisted_tool_call_passes(self, monkeypatch):
        monkeypatch.setenv('DISABLE_TOOL_LIST', '["banned"]')
        base = _build_base_with_tools({"safe": _make_tool("safe")})

        result = asyncio.run(base.mcp._tool_manager.call_tool("safe", {}))
        assert result == {"executed": "safe"}

    def test_deny_list_re_read_on_each_install(self, monkeypatch):
        """Each call to _install_disable_filtering re-reads the env var, so a
        server restart with a new value takes effect for the new instance."""
        monkeypatch.setenv('DISABLE_TOOL_LIST', '["banned"]')
        base = _build_base_with_tools({
            "banned": _make_tool("banned"),
            "safe": _make_tool("safe"),
        })
        assert [t.name for t in base.mcp._tool_manager.list_tools()] == ["safe"]

        # Operator updates the env var (mcp-proxy on FF flip), then restarts → new install.
        monkeypatch.setenv('DISABLE_TOOL_LIST', '[]')
        base2 = _build_base_with_tools({
            "banned": _make_tool("banned"),
            "safe": _make_tool("safe"),
        })
        assert sorted(t.name for t in base2.mcp._tool_manager.list_tools()) == ["banned", "safe"]
