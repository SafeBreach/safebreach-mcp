"""
Simplified Authentication Tests for SafeBreach MCP External Connections

This test suite covers authentication functionality without requiring actual server startup.
Focuses on unit testing the authentication components and configuration.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from safebreach_mcp_core.safebreach_base import SafeBreachMCPBase
from start_all_servers import MultiServerLauncher
from safebreach_mcp_config.config_server import SafeBreachConfigServer
from safebreach_mcp_data.data_server import SafeBreachDataServer
from safebreach_mcp_utilities.utilities_server import SafeBreachUtilitiesServer
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer


class TestAuthenticationSimple(unittest.TestCase):
    """Simple unit tests for authentication functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_auth_token = "test-auth-token-12345"
        
        # Mock SafeBreach API calls
        self.api_patcher = patch('safebreach_mcp_core.safebreach_auth.SafeBreachAuth.make_request')
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = {"data": [], "message": "test"}
    
    def tearDown(self):
        """Clean up test environment."""
        self.api_patcher.stop()
    
    def test_authentication_wrapper_creation(self):
        """Test that authentication wrapper can be created with valid token."""
        with patch.dict(os.environ, {'SAFEBREACH_MCP_AUTH_TOKEN': self.test_auth_token}):
            base_server = SafeBreachMCPBase("test-server")
            mock_app = MagicMock()
            
            # Should create wrapper without errors
            wrapper = base_server._create_authenticated_asgi_app(mock_app)
            self.assertIsNotNone(wrapper)
            self.assertTrue(callable(wrapper))
    
    def test_authentication_wrapper_missing_token(self):
        """Test that authentication wrapper fails without token."""
        with patch.dict(os.environ, {}, clear=True):
            base_server = SafeBreachMCPBase("test-server")
            mock_app = MagicMock()
            
            # Should raise ValueError for missing token
            with self.assertRaises(ValueError) as cm:
                base_server._create_authenticated_asgi_app(mock_app)
            
            self.assertIn("SAFEBREACH_MCP_AUTH_TOKEN", str(cm.exception))
    
    def test_multi_server_launcher_external_config(self):
        """Test that MultiServerLauncher handles external configuration correctly."""
        # Mock command-line arguments
        mock_args = type('Args', (), {
            'external': True,
            'external_config': False,
            'external_data': False,
            'external_utilities': False,
            'host': '127.0.0.1'
        })()
        
        launcher = MultiServerLauncher(mock_args)
        
        # Should enable external connections for all servers
        expected = {'config': True, 'data': True, 'utilities': True, 'playbook': True}
        self.assertEqual(launcher.external_config, expected)
    
    def test_multi_server_launcher_specific_external_config(self):
        """Test specific server external configuration."""
        mock_args = type('Args', (), {
            'external': False,
            'external_config': True,
            'external_data': False,
            'external_utilities': True,
            'host': '127.0.0.1'
        })()
        
        launcher = MultiServerLauncher(mock_args)
        
        # Should enable external only for specified servers
        expected = {'config': True, 'data': False, 'utilities': True, 'playbook': False}
        self.assertEqual(launcher.external_config, expected)
    
    def test_bind_host_determination(self):
        """Test bind host determination logic."""
        with patch.dict(os.environ, {'SAFEBREACH_MCP_AUTH_TOKEN': self.test_auth_token}):
            base_server = SafeBreachMCPBase("test-server")
            
            # External connections should bind to 0.0.0.0
            external_host = base_server._determine_bind_host("127.0.0.1", allow_external=True)
            self.assertEqual(external_host, "0.0.0.0")
            
            # Local connections should use provided host
            local_host = base_server._determine_bind_host("127.0.0.1", allow_external=False)
            self.assertEqual(local_host, "127.0.0.1")
    
    def test_server_instantiation_with_authentication(self):
        """Test that server classes can be instantiated properly."""
        with patch('safebreach_mcp_core.safebreach_auth.SafeBreachAuth.make_request'):
            # All server types should instantiate without errors
            config_server = SafeBreachConfigServer()
            self.assertIsInstance(config_server, SafeBreachMCPBase)
            
            data_server = SafeBreachDataServer()
            self.assertIsInstance(data_server, SafeBreachMCPBase)
            
            utilities_server = SafeBreachUtilitiesServer()
            self.assertIsInstance(utilities_server, SafeBreachMCPBase)
            
            playbook_server = SafeBreachPlaybookServer()
            self.assertIsInstance(playbook_server, SafeBreachMCPBase)
    
    def test_environment_external_config_parsing(self):
        """Test parsing of external connection configuration from environment."""
        # Test global external flag
        with patch.dict(os.environ, {'SAFEBREACH_MCP_ALLOW_EXTERNAL': 'true'}):
            from start_all_servers import parse_external_config
            config = parse_external_config()
            expected = {'config': True, 'data': True, 'utilities': True, 'playbook': True}
            self.assertEqual(config, expected)
        
        # Test server-specific flags
        with patch.dict(os.environ, {
            'SAFEBREACH_MCP_CONFIG_EXTERNAL': 'true',
            'SAFEBREACH_MCP_DATA_EXTERNAL': 'false',
            'SAFEBREACH_MCP_UTILITIES_EXTERNAL': 'true'
        }):
            config = parse_external_config()
            expected = {'config': True, 'data': False, 'utilities': True, 'playbook': False}
            self.assertEqual(config, expected)
    
    def test_security_warning_log_method(self):
        """Test that security warning logging method exists and works."""
        with patch.dict(os.environ, {'SAFEBREACH_MCP_AUTH_TOKEN': self.test_auth_token}):
            base_server = SafeBreachMCPBase("test-server")
            
            # Should not raise exception
            try:
                base_server._log_external_binding_warning(8000)
            except Exception as e:
                self.fail(f"Security warning logging failed: {e}")
    
    def test_authentication_token_validation(self):
        """Test authentication token validation in wrapper."""
        with patch.dict(os.environ, {'SAFEBREACH_MCP_AUTH_TOKEN': self.test_auth_token}):
            base_server = SafeBreachMCPBase("test-server")
            mock_app = MagicMock()
            
            wrapper = base_server._create_authenticated_asgi_app(mock_app)
            
            # The wrapper should contain the expected auth token
            # This is a basic structural test - actual ASGI testing would require more setup
            self.assertIsNotNone(wrapper)
            self.assertTrue(callable(wrapper))


if __name__ == '__main__':
    unittest.main(verbosity=2)