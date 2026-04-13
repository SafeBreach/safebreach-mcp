"""
Tests for SafeBreach Data Server tool wrappers (SAF-29415 Phase 3).

This file targets the thin MCP-tool wrappers registered on
``SafeBreachDataServer``. Wrappers are tested by reaching into FastMCP's
``_tool_manager._tools`` registry and invoking the underlying async
function directly via ``asyncio.run`` — this preserves the wrapper's
real exception types and dict return values, which the public
``call_tool`` API would otherwise wrap in ``ToolError`` / serialize to
``TextContent``.
"""

import asyncio

import pytest
from unittest.mock import patch


def _get_tool_fn(tool_name: str):
    """Return the underlying async function for a registered MCP tool."""
    # Deferred import to avoid module-level coupling and to ensure the
    # singleton ``data_server`` is fully constructed before lookup.
    from safebreach_mcp_data.data_server import data_server
    return data_server.mcp._tool_manager._tools[tool_name].fn


class TestPeerBenchmarkToolWrapper:
    """Wrapper-contract tests for the ``get_peer_benchmark_score`` MCP tool."""

    # ---- Test 1: registration --------------------------------------
    def test_tool_registered(self):
        """get_peer_benchmark_score appears in the registered tool list."""
        from safebreach_mcp_data.data_server import data_server
        tools = asyncio.run(data_server.mcp.list_tools())
        names = [tool.name for tool in tools]
        assert "get_peer_benchmark_score" in names

    # ---- Test 2: epoch input normalization -------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_epoch_input_normalization(self, mock_fn):
        """Epoch-seconds inputs are converted to epoch-ms before delegation."""
        mock_fn.return_value = {"score": 42}
        fn = _get_tool_fn("get_peer_benchmark_score")

        asyncio.run(fn(
            console="c",
            start_date=1700000000,
            end_date=1702592000,
        ))

        mock_fn.assert_called_once()
        kwargs = mock_fn.call_args.kwargs
        assert kwargs['start_date'] == 1700000000000
        assert kwargs['end_date'] == 1702592000000

    # ---- Test 3: ISO input normalization ---------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_iso_input_normalization(self, mock_fn):
        """ISO 8601 strings are normalized to epoch-ms before delegation."""
        mock_fn.return_value = {"score": 42}
        fn = _get_tool_fn("get_peer_benchmark_score")

        asyncio.run(fn(
            console="c",
            start_date="2026-03-01T00:00:00Z",
            end_date="2026-03-31T23:59:59Z",
        ))

        mock_fn.assert_called_once()
        kwargs = mock_fn.call_args.kwargs
        assert kwargs['start_date'] == 1772323200000
        assert kwargs['end_date'] == 1775001599000

    # ---- Test 4: missing start_date raises -------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_missing_start_date_raises(self, mock_fn):
        """start_date=None -> ValueError; business function never called."""
        fn = _get_tool_fn("get_peer_benchmark_score")

        with pytest.raises(ValueError, match="start_date and end_date are required"):
            asyncio.run(fn(
                console="c",
                start_date=None,
                end_date=1702592000,
            ))

        mock_fn.assert_not_called()

    # ---- Test 5: missing end_date raises ---------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_missing_end_date_raises(self, mock_fn):
        """end_date=None -> ValueError; business function never called."""
        fn = _get_tool_fn("get_peer_benchmark_score")

        with pytest.raises(ValueError, match="start_date and end_date are required"):
            asyncio.run(fn(
                console="c",
                start_date=1700000000,
                end_date=None,
            ))

        mock_fn.assert_not_called()

    # ---- Test 6: invalid start_date string raises ------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_invalid_start_date_string_raises(self, mock_fn):
        """Non-parseable date string -> ValueError; business fn never called."""
        fn = _get_tool_fn("get_peer_benchmark_score")

        with pytest.raises(ValueError, match="start_date and end_date are required"):
            asyncio.run(fn(
                console="c",
                start_date="not-a-date",
                end_date=1702592000,
            ))

        mock_fn.assert_not_called()

    # ---- Test 7: filters pass through unchanged --------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_filters_pass_through(self, mock_fn):
        """Filter strings are forwarded to the business function unchanged."""
        mock_fn.return_value = {}
        fn = _get_tool_fn("get_peer_benchmark_score")

        asyncio.run(fn(
            console="c",
            start_date=1700000000000,
            end_date=1702592000000,
            include_test_ids_filter="a,b",
            exclude_test_ids_filter=None,
        ))

        kwargs = mock_fn.call_args.kwargs
        assert kwargs['include_test_ids_filter'] == "a,b"
        assert kwargs['exclude_test_ids_filter'] is None

    # ---- Test 8: console default -----------------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_console_default(self, mock_fn):
        """Omitting console -> business function called with console='default'."""
        mock_fn.return_value = {}
        fn = _get_tool_fn("get_peer_benchmark_score")

        asyncio.run(fn(
            start_date=1700000000000,
            end_date=1702592000000,
        ))

        kwargs = mock_fn.call_args.kwargs
        assert kwargs['console'] == "default"

    # ---- Test 9: return value pass-through -------------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_return_value_pass_through(self, mock_fn):
        """Wrapper returns the business function's exact dict (identity)."""
        sentinel = {"customer_score": 85, "_sentinel": True}
        mock_fn.return_value = sentinel
        fn = _get_tool_fn("get_peer_benchmark_score")

        result = asyncio.run(fn(
            console="c",
            start_date=1700000000000,
            end_date=1702592000000,
        ))

        assert result is sentinel  # identity check, not equality

    # ---- Test 10: business ValueError propagates -------------------
    @patch('safebreach_mcp_data.data_server.sb_get_peer_benchmark_score')
    def test_business_function_valueerror_propagates(self, mock_fn):
        """ValueError from the business function propagates unchanged."""
        mock_fn.side_effect = ValueError("both filters cannot be used together")
        fn = _get_tool_fn("get_peer_benchmark_score")

        with pytest.raises(ValueError, match="both filters cannot be used together"):
            asyncio.run(fn(
                console="c",
                start_date=1700000000000,
                end_date=1702592000000,
                include_test_ids_filter="a",
                exclude_test_ids_filter="b",
            ))
