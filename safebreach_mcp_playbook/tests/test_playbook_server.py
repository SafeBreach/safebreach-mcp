"""
Tests for SafeBreach Playbook Server

This module tests the FastMCP server implementation for playbook operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer, parse_external_config


class TestSafeBreachPlaybookServer:
    """Test the SafeBreachPlaybookServer class."""
    
    def test_server_initialization(self):
        """Test server initialization."""
        server = SafeBreachPlaybookServer()
        
        # Check that server was initialized correctly
        assert hasattr(server, 'mcp')
        assert server.mcp is not None
        
        # Check that tools were registered
        # We can't easily test tool registration without more complex mocking,
        # but we can at least verify the server was created
        assert isinstance(server, SafeBreachPlaybookServer)
    
    def test_server_has_mcp_attribute(self):
        """Test that server has the mcp attribute properly initialized."""
        server = SafeBreachPlaybookServer()
        assert hasattr(server, 'mcp')
        assert server.mcp is not None


class TestParseExternalConfig:
    """Test the parse_external_config function."""
    
    @patch.dict('os.environ', {}, clear=True)
    def test_parse_external_config_default(self):
        """Test parsing external config with default values."""
        result = parse_external_config('playbook')
        assert result is False
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_ALLOW_EXTERNAL': 'true'}, clear=True)
    def test_parse_external_config_global_flag(self):
        """Test parsing external config with global flag."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'true'}, clear=True)
    def test_parse_external_config_server_specific(self):
        """Test parsing external config with server-specific flag."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {
        'SAFEBREACH_MCP_ALLOW_EXTERNAL': 'false',
        'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'true'
    }, clear=True)
    def test_parse_external_config_server_overrides_global(self):
        """Test that server-specific flag works even when global is false."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'false'}, clear=True)
    def test_parse_external_config_explicit_false(self):
        """Test parsing external config with explicit false."""
        result = parse_external_config('playbook')
        assert result is False