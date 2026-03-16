"""
Tests for ISO 8601 timestamp normalization in Data Server tool wrappers (SAF-28875).

Verifies that all 10 timestamp parameters across 4 tool wrappers accept both
ISO 8601 strings and epoch integers, normalizing before dispatch to backend functions.
"""

import asyncio
import pytest
from unittest.mock import patch
from safebreach_mcp_data.data_server import SafeBreachDataServer


@pytest.fixture
def server():
    """Create a fresh data server instance for testing."""
    return SafeBreachDataServer()


class TestGetTestsHistoryTimestampNormalization:
    """Test ISO 8601 normalization for get_tests_history wrapper."""

    def test_iso_start_date_normalized(self, server):
        """ISO string start_date is normalized to epoch ms before dispatch."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_tests_history"
        ) as mock_fn:
            mock_fn.return_value = {"tests": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_tests_history"]
            asyncio.run(tool.fn(console="demo", start_date="2024-01-01T00:00:00Z"))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["start_date"], int)
            assert kwargs["start_date"] > 10**12  # epoch ms

    def test_iso_end_date_normalized(self, server):
        """ISO string end_date is normalized to epoch ms before dispatch."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_tests_history"
        ) as mock_fn:
            mock_fn.return_value = {"tests": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_tests_history"]
            asyncio.run(tool.fn(console="demo", end_date="2024-06-15T23:59:59Z"))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["end_date"], int)
            assert kwargs["end_date"] > 10**12

    def test_epoch_int_passthrough(self, server):
        """Epoch integer start_date passes through unchanged."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_tests_history"
        ) as mock_fn:
            mock_fn.return_value = {"tests": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_tests_history"]
            asyncio.run(tool.fn(console="demo", start_date=1640995200000))
            _, kwargs = mock_fn.call_args
            assert kwargs["start_date"] == 1640995200000

    def test_none_passthrough(self, server):
        """None start_date passes through as None."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_tests_history"
        ) as mock_fn:
            mock_fn.return_value = {"tests": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_tests_history"]
            asyncio.run(tool.fn(console="demo", start_date=None))
            _, kwargs = mock_fn.call_args
            assert kwargs["start_date"] is None


class TestGetTestSimulationsTimestampNormalization:
    """Test ISO 8601 normalization for get_test_simulations wrapper."""

    def test_iso_start_time_normalized(self, server):
        """ISO string start_time is normalized to epoch ms."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_test_simulations"
        ) as mock_fn:
            mock_fn.return_value = {"simulations": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_test_simulations"]
            asyncio.run(tool.fn(
                test_id="test1", console="demo",
                start_time="2024-03-01T00:00:00Z"
            ))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["start_time"], int)
            assert kwargs["start_time"] > 10**12

    def test_iso_end_time_normalized(self, server):
        """ISO string end_time is normalized to epoch ms."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_test_simulations"
        ) as mock_fn:
            mock_fn.return_value = {"simulations": [], "total_count": 0}
            tool = server.mcp._tool_manager._tools["get_test_simulations"]
            asyncio.run(tool.fn(
                test_id="test1", console="demo",
                end_time="2024-03-02T00:00:00Z"
            ))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["end_time"], int)
            assert kwargs["end_time"] > 10**12


class TestGetSimulationResultDriftsTimestampNormalization:
    """Test ISO 8601 normalization for get_simulation_result_drifts wrapper."""

    def test_iso_window_start_end_normalized(self, server):
        """ISO strings for window_start/window_end are normalized to epoch ms."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_simulation_result_drifts"
        ) as mock_fn:
            mock_fn.return_value = {"drift_groups": [], "total_drifts": 0}
            tool = server.mcp._tool_manager._tools["get_simulation_result_drifts"]
            asyncio.run(tool.fn(
                console="demo",
                window_start="2024-03-01T00:00:00Z",
                window_end="2024-03-02T00:00:00Z"
            ))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["window_start"], int)
            assert isinstance(kwargs["window_end"], int)
            assert kwargs["window_start"] > 10**12
            assert kwargs["window_end"] > kwargs["window_start"]

    def test_iso_look_back_time_normalized(self, server):
        """ISO string look_back_time is normalized to epoch ms."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_simulation_result_drifts"
        ) as mock_fn:
            mock_fn.return_value = {"drift_groups": [], "total_drifts": 0}
            tool = server.mcp._tool_manager._tools["get_simulation_result_drifts"]
            asyncio.run(tool.fn(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                look_back_time="2024-02-20T00:00:00Z"
            ))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["look_back_time"], int)
            assert kwargs["look_back_time"] > 10**12

    def test_invalid_window_start_raises_error(self, server):
        """Invalid string for required window_start raises ValueError."""
        tool = server.mcp._tool_manager._tools["get_simulation_result_drifts"]
        with pytest.raises(ValueError, match="window_start"):
            asyncio.run(tool.fn(
                console="demo",
                window_start="not-a-date",
                window_end=1709337600000
            ))


class TestGetSimulationStatusDriftsTimestampNormalization:
    """Test ISO 8601 normalization for get_simulation_status_drifts wrapper."""

    def test_iso_window_start_end_normalized(self, server):
        """ISO strings for window_start/window_end are normalized to epoch ms."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_simulation_status_drifts"
        ) as mock_fn:
            mock_fn.return_value = {"drift_groups": [], "total_drifts": 0}
            tool = server.mcp._tool_manager._tools["get_simulation_status_drifts"]
            asyncio.run(tool.fn(
                console="demo",
                window_start="2024-03-01T00:00:00Z",
                window_end="2024-03-02T00:00:00Z"
            ))
            _, kwargs = mock_fn.call_args
            assert isinstance(kwargs["window_start"], int)
            assert isinstance(kwargs["window_end"], int)
            assert kwargs["window_start"] > 10**12

    def test_invalid_window_end_raises_error(self, server):
        """Invalid string for required window_end raises ValueError."""
        tool = server.mcp._tool_manager._tools["get_simulation_status_drifts"]
        with pytest.raises(ValueError, match="window_end"):
            asyncio.run(tool.fn(
                console="demo",
                window_start=1709251200000,
                window_end="not-a-date"
            ))

    def test_epoch_int_passthrough(self, server):
        """Epoch integer window params pass through correctly."""
        with patch(
            "safebreach_mcp_data.data_server.sb_get_simulation_status_drifts"
        ) as mock_fn:
            mock_fn.return_value = {"drift_groups": [], "total_drifts": 0}
            tool = server.mcp._tool_manager._tools["get_simulation_status_drifts"]
            asyncio.run(tool.fn(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000
            ))
            _, kwargs = mock_fn.call_args
            assert kwargs["window_start"] == 1709251200000
            assert kwargs["window_end"] == 1709337600000
