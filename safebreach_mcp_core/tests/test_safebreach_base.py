"""Tests for SafeBreachMCPBase — request_shutdown() method."""

from unittest.mock import MagicMock, patch


class TestRequestShutdown:

    @patch("safebreach_mcp_core.safebreach_base.SafeBreachAuth")
    def test_no_op_when_server_not_running(self, _mock_auth):
        from safebreach_mcp_core.safebreach_base import SafeBreachMCPBase

        base = SafeBreachMCPBase("test-server")
        assert base._uvicorn_server is None
        base.request_shutdown()  # should not raise
        assert base._uvicorn_server is None

    @patch("safebreach_mcp_core.safebreach_base.SafeBreachAuth")
    def test_sets_should_exit_when_server_running(self, _mock_auth):
        from safebreach_mcp_core.safebreach_base import SafeBreachMCPBase

        base = SafeBreachMCPBase("test-server")
        mock_server = MagicMock()
        mock_server.should_exit = False
        base._uvicorn_server = mock_server
        base.request_shutdown()
        assert mock_server.should_exit is True
