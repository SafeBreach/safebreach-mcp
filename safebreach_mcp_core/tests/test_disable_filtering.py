"""Tests for SAF-29865 tool-disable filtering — two independent layers:

  Layer 1 (DISABLE_TOOL_LIST): server-wide absolute deny. Listed tools are
    always hidden / always rejected, regardless of header.

  Layer 2 (write-tool gate): triggered by `X-Disable-Tools: true` header.
    When the gate is closed, tools whose annotation `readOnlyHint != True`
    are hidden / rejected. Read-only tools always pass.

The two layers compose: a deny-listed tool is unreachable forever; a non-
deny-listed write tool becomes reachable iff the gate opens (mcp-proxy
opens it when the account FF + consent are both ON). breach-genie sees
the post-filtered catalog."""

import asyncio

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp.exceptions import ToolError
from safebreach_mcp_core import safebreach_base as mod


def _make_tool(name: str, read_only: bool = False):
    """A fake MCP tool with an `annotations.readOnlyHint`. Default is write."""
    return SimpleNamespace(name=name, annotations=SimpleNamespace(readOnlyHint=read_only))


def _make_unannotated_tool(name: str):
    """A tool without annotations — fails safe to 'write' under Layer 2."""
    return SimpleNamespace(name=name, annotations=None)


async def _noop_app(scope, receive, send):
    pass


def _build_base_with_tools(tools_by_name: dict):
    """Construct a SafeBreachMCPBase, attach a fake tool manager, install
    the filter, return the wrapped app + the base. Caller monkeypatches
    `_DISABLE_TOOL_LIST` and sets `_disable_tools_flag` to drive scenarios."""
    with patch.object(mod, "SafeBreachAuth"):
        base = mod.SafeBreachMCPBase("test-server")

    fake_manager = MagicMock()
    fake_manager.list_tools.side_effect = lambda: list(tools_by_name.values())
    fake_manager.get_tool.side_effect = lambda name: tools_by_name.get(name)

    async def call_tool(name, arguments, context=None, convert_result=False):
        return {"executed": name}

    fake_manager.call_tool.side_effect = call_tool
    base.mcp._tool_manager = fake_manager
    wrapped = base._install_disable_filtering(_noop_app)
    return base, wrapped


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


class TestDenyListLayer:
    """Layer 1: DISABLE_TOOL_LIST is absolute — listed tools are unreachable
    regardless of any header / flag state."""

    def test_listed_tool_hidden_with_gate_closed(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({
            "banned": _make_tool("banned", read_only=False),
            "safe": _make_tool("safe", read_only=True),
        })
        mod._disable_tools_flag.set(True)

        names = [t.name for t in base.mcp._tool_manager.list_tools()]
        assert names == ["safe"]

    def test_listed_tool_hidden_with_gate_open(self, monkeypatch):
        """Even when the gate is open (FF + consent on), deny-listed tools stay hidden."""
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({
            "banned": _make_tool("banned", read_only=False),
            "writable": _make_tool("writable", read_only=False),
            "safe": _make_tool("safe", read_only=True),
        })
        mod._disable_tools_flag.set(False)

        names = sorted(t.name for t in base.mcp._tool_manager.list_tools())
        assert names == ["safe", "writable"]

    def test_listed_tool_call_blocked_with_gate_closed(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({"banned": _make_tool("banned")})
        mod._disable_tools_flag.set(True)

        with pytest.raises(ToolError, match="disabled by the server administrator"):
            asyncio.run(base.mcp._tool_manager.call_tool("banned", {}))

    def test_listed_tool_call_blocked_with_gate_open(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({"banned": _make_tool("banned")})
        mod._disable_tools_flag.set(False)

        with pytest.raises(ToolError, match="disabled by the server administrator"):
            asyncio.run(base.mcp._tool_manager.call_tool("banned", {}))


class TestWriteGateLayer:
    """Layer 2: write tools (`readOnlyHint != True`) are visible iff the gate
    is open. The gate is closed when X-Disable-Tools: true is on the request."""

    def test_gate_closed_hides_writes_keeps_reads(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({
            "writable": _make_tool("writable", read_only=False),
            "safe": _make_tool("safe", read_only=True),
        })
        mod._disable_tools_flag.set(True)

        names = [t.name for t in base.mcp._tool_manager.list_tools()]
        assert names == ["safe"]

    def test_gate_open_shows_writes_and_reads(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({
            "writable": _make_tool("writable", read_only=False),
            "safe": _make_tool("safe", read_only=True),
        })
        mod._disable_tools_flag.set(False)

        names = sorted(t.name for t in base.mcp._tool_manager.list_tools())
        assert names == ["safe", "writable"]

    def test_gate_closed_blocks_write_call(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({"writable": _make_tool("writable", read_only=False)})
        mod._disable_tools_flag.set(True)

        with pytest.raises(ToolError, match="AI actions are not enabled"):
            asyncio.run(base.mcp._tool_manager.call_tool("writable", {}))

    def test_gate_closed_allows_read_call(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({"safe": _make_tool("safe", read_only=True)})
        mod._disable_tools_flag.set(True)

        result = asyncio.run(base.mcp._tool_manager.call_tool("safe", {}))
        assert result == {"executed": "safe"}

    def test_gate_open_allows_write_call(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({"writable": _make_tool("writable", read_only=False)})
        mod._disable_tools_flag.set(False)

        result = asyncio.run(base.mcp._tool_manager.call_tool("writable", {}))
        assert result == {"executed": "writable"}

    def test_unannotated_tool_treated_as_write(self, monkeypatch):
        """A tool without annotations fails safe — gate hides it."""
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset())
        base, _ = _build_base_with_tools({"unknown": _make_unannotated_tool("unknown")})
        mod._disable_tools_flag.set(True)

        names = [t.name for t in base.mcp._tool_manager.list_tools()]
        assert names == []

        with pytest.raises(ToolError, match="AI actions are not enabled"):
            asyncio.run(base.mcp._tool_manager.call_tool("unknown", {}))


class TestLayerComposition:
    """Both layers active at once: deny list trumps the gate, gate trumps read."""

    def test_deny_list_plus_closed_gate_keeps_only_unlisted_reads(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({
            "banned": _make_tool("banned", read_only=True),   # listed → hidden even though read-only
            "writable": _make_tool("writable", read_only=False),  # not listed, write → hidden by gate
            "safe": _make_tool("safe", read_only=True),        # not listed, read → visible
        })
        mod._disable_tools_flag.set(True)

        names = [t.name for t in base.mcp._tool_manager.list_tools()]
        assert names == ["safe"]

    def test_deny_list_plus_open_gate_shows_all_unlisted(self, monkeypatch):
        monkeypatch.setattr(mod, '_DISABLE_TOOL_LIST', frozenset({"banned"}))
        base, _ = _build_base_with_tools({
            "banned": _make_tool("banned", read_only=False),
            "writable": _make_tool("writable", read_only=False),
            "safe": _make_tool("safe", read_only=True),
        })
        mod._disable_tools_flag.set(False)

        names = sorted(t.name for t in base.mcp._tool_manager.list_tools())
        assert names == ["safe", "writable"]


class TestDisableAwareAsgiMiddleware:
    """The ASGI wrap reads X-Disable-Tools per request into _disable_tools_flag."""

    def _run_middleware(self, headers):
        captured = {}

        async def downstream(scope, receive, send):
            captured["flag"] = mod._disable_tools_flag.get()

        with patch.object(mod, "SafeBreachAuth"):
            base = mod.SafeBreachMCPBase("test-server")
        base.mcp._tool_manager = MagicMock(
            list_tools=lambda: [], call_tool=lambda *a, **kw: None,
            get_tool=lambda n: None,
        )
        wrapped = base._install_disable_filtering(downstream)

        scope = {"type": "http", "headers": headers}
        asyncio.run(wrapped(scope, lambda: None, lambda m: None))
        return captured

    @pytest.mark.parametrize('raw,expected_flag', [
        (b"true",  True),
        (b"TRUE",  True),
        (b"false", False),
        (b"maybe", False),
        (b"",      False),
    ])
    def test_header_value_maps_to_flag(self, raw, expected_flag):
        captured = self._run_middleware([(b"x-disable-tools", raw)])
        assert captured["flag"] is expected_flag

    def test_missing_header_defaults_to_false(self):
        captured = self._run_middleware([])
        assert captured["flag"] is False

    def test_non_http_scope_passes_through(self):
        called = {"hit": False}

        async def downstream(scope, receive, send):
            called["hit"] = True

        with patch.object(mod, "SafeBreachAuth"):
            base = mod.SafeBreachMCPBase("test-server")
        base.mcp._tool_manager = MagicMock(
            list_tools=lambda: [], call_tool=lambda *a, **kw: None,
            get_tool=lambda n: None,
        )
        wrapped = base._install_disable_filtering(downstream)

        asyncio.run(wrapped({"type": "websocket"}, lambda: None, lambda m: None))
        assert called["hit"] is True
