"""
Tests for SafeBreach MCP Server Manager API

This module tests the programmatic server management functionality.
"""

import os
import pytest
import tempfile
import time
import unittest
from unittest.mock import Mock, patch, MagicMock

from mcp_server_manager import (
    MCPServerManager, 
    ServerConfig, 
    ServerType, 
    ServerStatus, 
    ServerInstance
)


class TestServerConfig(unittest.TestCase):
    """Test suite for ServerConfig class."""
    
    def test_server_config_creation_basic(self):
        """Test basic server configuration creation."""
        config = ServerConfig(
            server_type=ServerType.DATA,
            port=8001
        )
        
        self.assertEqual(config.server_type, ServerType.DATA)
        self.assertEqual(config.port, 8001)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.base_url, "/")
        self.assertEqual(config.allow_external, False)
        self.assertIsNone(config.auth_token)
        self.assertEqual(config.environment_vars, {})
        self.assertEqual(config.custom_args, [])
    
    def test_server_config_creation_full(self):
        """Test full server configuration creation."""
        config = ServerConfig(
            server_type=ServerType.DATA,
            port=8001,
            host="0.0.0.0",
            base_url="/api/mcp",
            allow_external=True,
            auth_token="test-token-123",
            environment_vars={"TEST_VAR": "test-value"},
            custom_args=["--verbose"]
        )
        
        self.assertEqual(config.server_type, ServerType.DATA)
        self.assertEqual(config.port, 8001)
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.base_url, "/api/mcp")
        self.assertTrue(config.allow_external)
        self.assertEqual(config.auth_token, "test-token-123")
        self.assertEqual(config.environment_vars, {"TEST_VAR": "test-value"})
        self.assertEqual(config.custom_args, ["--verbose"])
    
    def test_server_config_string_server_type_conversion(self):
        """Test server configuration with string server type conversion."""
        config = ServerConfig(server_type="data", port=8001)
        self.assertEqual(config.server_type, ServerType.DATA)
        
        config = ServerConfig(server_type="config", port=8000)
        self.assertEqual(config.server_type, ServerType.CONFIG)
    
    def test_server_config_base_url_normalization(self):
        """Test base URL normalization in post-initialization."""
        # Test leading slash addition
        config = ServerConfig(server_type=ServerType.DATA, port=8001, base_url="api/mcp")
        self.assertEqual(config.base_url, "/api/mcp")
        
        # Test trailing slash removal
        config = ServerConfig(server_type=ServerType.DATA, port=8001, base_url="/api/mcp/")
        self.assertEqual(config.base_url, "/api/mcp")
        
        # Test empty string handling
        config = ServerConfig(server_type=ServerType.DATA, port=8001, base_url="")
        self.assertEqual(config.base_url, "/")
        
        # Test root URL preservation
        config = ServerConfig(server_type=ServerType.DATA, port=8001, base_url="/")
        self.assertEqual(config.base_url, "/")
    
    def test_server_config_port_validation(self):
        """Test port number validation in post-initialization."""
        # Valid port
        config = ServerConfig(server_type=ServerType.DATA, port=8001)
        self.assertEqual(config.port, 8001)
        
        # Invalid port - too low
        with self.assertRaises(ValueError) as cm:
            ServerConfig(server_type=ServerType.DATA, port=1000)
        self.assertIn("Port 1000 must be between 1024 and 65535", str(cm.exception))
        
        # Invalid port - too high
        with self.assertRaises(ValueError) as cm:
            ServerConfig(server_type=ServerType.DATA, port=70000)
        self.assertIn("Port 70000 must be between 1024 and 65535", str(cm.exception))


class TestServerInstance(unittest.TestCase):
    """Test suite for ServerInstance class."""
    
    def test_server_instance_creation(self):
        """Test server instance creation."""
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        instance = ServerInstance("test-instance", config)
        
        self.assertEqual(instance.instance_id, "test-instance")
        self.assertEqual(instance.config, config)
        self.assertIsNone(instance.process)
        self.assertEqual(instance.status, ServerStatus.STOPPED)
        self.assertIsNone(instance.start_time)
        self.assertIsNone(instance.stop_time)
        self.assertIsNone(instance.pid)
        self.assertIsNone(instance.env_file)
    
    def test_server_instance_with_process(self):
        """Test server instance with process information."""
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        mock_process = Mock()
        mock_process.pid = 12345
        
        instance = ServerInstance(
            "test-instance", 
            config, 
            process=mock_process,
            status=ServerStatus.RUNNING,
            start_time=time.time()
        )
        
        self.assertEqual(instance.pid, 12345)
        self.assertEqual(instance.status, ServerStatus.RUNNING)
        self.assertIsNotNone(instance.start_time)


class TestMCPServerManager(unittest.TestCase):
    """Test suite for MCPServerManager class."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = MCPServerManager()
    
    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, 'manager'):
            self.manager.stop_all_servers()
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        self.assertIsInstance(self.manager.instances, dict)
        self.assertIsInstance(self.manager.port_registry, dict)
        self.assertEqual(len(self.manager.instances), 0)
        self.assertEqual(len(self.manager.port_registry), 0)
    
    def test_get_server_command_individual_servers(self):
        """Test server command generation for individual servers."""
        # Test config server
        config = ServerConfig(server_type=ServerType.CONFIG, port=8000)
        cmd = self.manager._get_server_command(config)
        expected = ["uv", "run", "-m", "safebreach_mcp_config.config_server"]
        self.assertEqual(cmd, expected)
        
        # Test data server
        config = ServerConfig(server_type=ServerType.DATA, port=8001)
        cmd = self.manager._get_server_command(config)
        expected = ["uv", "run", "-m", "safebreach_mcp_data.data_server"]
        self.assertEqual(cmd, expected)
        
        # Test utilities server
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        cmd = self.manager._get_server_command(config)
        expected = ["uv", "run", "-m", "safebreach_mcp_utilities.utilities_server"]
        self.assertEqual(cmd, expected)
        
        # Test playbook server
        config = ServerConfig(server_type=ServerType.PLAYBOOK, port=8003)
        cmd = self.manager._get_server_command(config)
        expected = ["uv", "run", "-m", "safebreach_mcp_playbook.playbook_server"]
        self.assertEqual(cmd, expected)
    
    def test_get_server_command_all_servers_basic(self):
        """Test server command generation for multi-server launcher with basic config."""
        config = ServerConfig(server_type=ServerType.ALL, port=8000)
        cmd = self.manager._get_server_command(config)
        
        expected = ["uv", "run", "python", "start_all_servers.py"]
        self.assertEqual(cmd, expected)
    
    def test_get_server_command_all_servers_full_config(self):
        """Test server command generation for multi-server launcher with full config."""
        config = ServerConfig(
            server_type=ServerType.ALL,
            port=8000,
            host="0.0.0.0",
            base_url="/api/mcp",
            allow_external=True,
            custom_args=["--verbose"]
        )
        cmd = self.manager._get_server_command(config)
        
        expected = [
            "uv", "run", "python", "start_all_servers.py",
            "--external", "--host", "0.0.0.0", "--base-url", "/api/mcp",
            "--verbose"
        ]
        self.assertEqual(cmd, expected)
    
    def test_prepare_environment_basic(self):
        """Test environment variable preparation with basic configuration."""
        config = ServerConfig(server_type=ServerType.DATA, port=8001)
        
        with patch.dict(os.environ, {"EXISTING_VAR": "existing_value"}, clear=True):
            env = self.manager._prepare_environment(config)
            
            # Should inherit existing environment
            self.assertEqual(env["EXISTING_VAR"], "existing_value")
            
            # Should not add MCP-specific vars for basic config
            self.assertNotIn('SAFEBREACH_MCP_BASE_URL', env)
            self.assertNotIn('SAFEBREACH_MCP_ALLOW_EXTERNAL', env)
    
    def test_prepare_environment_full_config(self):
        """Test environment variable preparation with full configuration."""
        config = ServerConfig(
            server_type=ServerType.DATA,
            port=8001,
            base_url="/api/mcp",
            allow_external=True,
            auth_token="test-token",
            environment_vars={"CUSTOM_VAR": "custom-value"}
        )
        
        env = self.manager._prepare_environment(config)
        
        self.assertEqual(env['SAFEBREACH_MCP_BASE_URL'], "/api/mcp")
        self.assertEqual(env['SAFEBREACH_MCP_ALLOW_EXTERNAL'], 'true')
        self.assertEqual(env['SAFEBREACH_MCP_AUTH_TOKEN'], "test-token")
        self.assertEqual(env['SAFEBREACH_MCP_DATA_EXTERNAL'], 'true')
        self.assertEqual(env['CUSTOM_VAR'], "custom-value")
    
    def test_prepare_environment_external_without_token(self):
        """Test environment preparation with external access but no token."""
        config = ServerConfig(
            server_type=ServerType.CONFIG,
            port=8000,
            allow_external=True
        )
        
        with patch('mcp_server_manager.logger') as mock_logger:
            env = self.manager._prepare_environment(config)
            
            self.assertEqual(env['SAFEBREACH_MCP_ALLOW_EXTERNAL'], 'true')
            self.assertEqual(env['SAFEBREACH_MCP_CONFIG_EXTERNAL'], 'true')
            mock_logger.warning.assert_called_once()
            self.assertIn("no auth token provided", mock_logger.warning.call_args[0][0])
    
    def test_create_temp_env_file(self):
        """Test temporary environment file creation."""
        env_vars = {
            "VAR1": "value1",
            "VAR2": "value2",
            "VAR3": "value with spaces"
        }
        
        env_file = self.manager._create_temp_env_file(env_vars)
        
        try:
            self.assertTrue(os.path.exists(env_file))
            self.assertTrue(env_file.endswith('.env'))
            
            with open(env_file, 'r') as f:
                content = f.read()
                self.assertIn("VAR1=value1", content)
                self.assertIn("VAR2=value2", content)
                self.assertIn("VAR3=value with spaces", content)
        finally:
            # Clean up
            if os.path.exists(env_file):
                os.unlink(env_file)
    
    def test_check_port_availability_available(self):
        """Test port availability checking for available port."""
        result = self.manager._check_port_availability(8001, "test-instance")
        self.assertTrue(result)
    
    def test_check_port_availability_same_instance(self):
        """Test port availability checking for same instance."""
        # Register a port
        self.manager.port_registry[8001] = "test-instance"
        
        # Same instance - should be available
        result = self.manager._check_port_availability(8001, "test-instance")
        self.assertTrue(result)
    
    def test_check_port_availability_different_instance(self):
        """Test port availability checking for different instance."""
        # Register a port
        self.manager.port_registry[8001] = "existing-instance"
        
        # Different instance - should not be available
        with patch('mcp_server_manager.logger') as mock_logger:
            result = self.manager._check_port_availability(8001, "new-instance")
            self.assertFalse(result)
            mock_logger.error.assert_called_once()
            self.assertIn("Port 8001 is already in use", mock_logger.error.call_args[0][0])
    
    @patch('subprocess.Popen')
    @patch('mcp_server_manager.MCPServerManager._create_temp_env_file')
    def test_start_server_success(self, mock_create_env_file, mock_popen):
        """Test successful server startup."""
        # Mock environment file creation
        mock_create_env_file.return_value = "/tmp/test.env"
        
        # Mock successful process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process
        
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        
        with patch('time.sleep'):  # Speed up the test
            result = self.manager.start_server("test-instance", config)
        
        self.assertTrue(result)
        self.assertIn("test-instance", self.manager.instances)
        self.assertIn(8002, self.manager.port_registry)
        
        instance = self.manager.instances["test-instance"]
        self.assertEqual(instance.status, ServerStatus.RUNNING)
        self.assertEqual(instance.pid, 12345)
        self.assertEqual(instance.env_file, "/tmp/test.env")
    
    @patch('subprocess.Popen')
    @patch('mcp_server_manager.MCPServerManager._create_temp_env_file')
    def test_start_server_failure(self, mock_create_env_file, mock_popen):
        """Test failed server startup."""
        # Mock environment file creation
        mock_create_env_file.return_value = "/tmp/test.env"
        
        # Mock failed process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Process failed
        mock_process.communicate.return_value = ("stdout output", "stderr output")
        mock_popen.return_value = mock_process
        
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        
        with patch('time.sleep'):  # Speed up the test
            with patch('mcp_server_manager.logger') as mock_logger:
                result = self.manager.start_server("test-instance", config)
        
        self.assertFalse(result)
        self.assertNotIn("test-instance", self.manager.instances)
        self.assertNotIn(8002, self.manager.port_registry)
        
        # Verify error logging
        mock_logger.error.assert_called()
        self.assertIn("failed to start", mock_logger.error.call_args_list[0][0][0])
    
    def test_start_server_duplicate_instance(self):
        """Test starting server with duplicate instance ID."""
        # Create a mock instance
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        instance = ServerInstance("test-instance", config)
        self.manager.instances["test-instance"] = instance
        
        # Try to start with same instance ID
        with patch('mcp_server_manager.logger') as mock_logger:
            result = self.manager.start_server("test-instance", config)
        
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
        self.assertIn("already exists", mock_logger.error.call_args[0][0])
    
    def test_start_server_port_conflict(self):
        """Test starting server with conflicting port."""
        # Register a port to different instance
        self.manager.port_registry[8002] = "other-instance"
        
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        result = self.manager.start_server("test-instance", config)
        
        self.assertFalse(result)
    
    def test_stop_server_not_found(self):
        """Test stopping non-existent server."""
        with patch('mcp_server_manager.logger') as mock_logger:
            result = self.manager.stop_server("non-existent")
        
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
        self.assertIn("not found", mock_logger.error.call_args[0][0])
    
    def test_stop_server_already_stopped(self):
        """Test stopping server that's already stopped."""
        # Create stopped instance
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        instance = ServerInstance("test-instance", config, status=ServerStatus.STOPPED)
        self.manager.instances["test-instance"] = instance
        
        with patch('mcp_server_manager.logger') as mock_logger:
            result = self.manager.stop_server("test-instance")
        
        self.assertTrue(result)
        mock_logger.info.assert_called_once()
        self.assertIn("already stopped", mock_logger.info.call_args[0][0])
    
    def test_get_server_status_not_found(self):
        """Test getting status of non-existent server."""
        status = self.manager.get_server_status("non-existent")
        self.assertIsNone(status)
    
    def test_get_server_info_not_found(self):
        """Test getting info of non-existent server."""
        info = self.manager.get_server_info("non-existent")
        self.assertIsNone(info)
    
    def test_get_server_info_success(self):
        """Test getting server information for existing server."""
        # Create mock instance
        config = ServerConfig(
            server_type=ServerType.DATA,
            port=8001,
            host="127.0.0.1",
            base_url="/api/mcp"
        )
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Running
        
        instance = ServerInstance(
            "test-instance", 
            config, 
            process=mock_process,
            status=ServerStatus.RUNNING,
            start_time=time.time(),
            pid=12345
        )
        self.manager.instances["test-instance"] = instance
        
        info = self.manager.get_server_info("test-instance")
        
        self.assertIsNotNone(info)
        self.assertEqual(info["instance_id"], "test-instance")
        self.assertEqual(info["server_type"], "data")
        self.assertEqual(info["port"], 8001)
        self.assertEqual(info["host"], "127.0.0.1")
        self.assertEqual(info["base_url"], "/api/mcp")
        self.assertEqual(info["status"], "running")
        self.assertEqual(info["pid"], 12345)
        self.assertEqual(info["endpoint"], "http://127.0.0.1:8001/api/mcp/sse")
        self.assertIsNotNone(info["uptime"])
    
    def test_get_server_info_root_url(self):
        """Test getting server information with root URL."""
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        instance = ServerInstance("test-instance", config)
        self.manager.instances["test-instance"] = instance
        
        info = self.manager.get_server_info("test-instance")
        
        self.assertEqual(info["endpoint"], "http://127.0.0.1:8002/sse")
    
    def test_list_servers_empty(self):
        """Test listing servers when none exist."""
        servers = self.manager.list_servers()
        self.assertEqual(servers, [])
    
    def test_list_servers_with_instances(self):
        """Test listing servers with existing instances."""
        # Create mock instances
        configs = [
            ServerConfig(server_type=ServerType.CONFIG, port=8000),
            ServerConfig(server_type=ServerType.DATA, port=8001),
        ]
        
        for i, config in enumerate(configs):
            instance = ServerInstance(f"instance-{i}", config)
            self.manager.instances[f"instance-{i}"] = instance
        
        servers = self.manager.list_servers()
        
        self.assertEqual(len(servers), 2)
        self.assertEqual(servers[0]["instance_id"], "instance-0")
        self.assertEqual(servers[1]["instance_id"], "instance-1")
    
    def test_cleanup_instance(self):
        """Test instance cleanup functionality."""
        # Create instance with temporary file
        config = ServerConfig(server_type=ServerType.UTILITIES, port=8002)
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.close()
        
        instance = ServerInstance(
            "test-instance", 
            config, 
            env_file=temp_file.name
        )
        self.manager.instances["test-instance"] = instance
        self.manager.port_registry[8002] = "test-instance"
        
        # Verify instance exists
        self.assertIn("test-instance", self.manager.instances)
        self.assertIn(8002, self.manager.port_registry)
        self.assertTrue(os.path.exists(temp_file.name))
        
        # Clean up instance
        self.manager._cleanup_instance("test-instance")
        
        # Verify cleanup
        self.assertNotIn("test-instance", self.manager.instances)
        self.assertNotIn(8002, self.manager.port_registry)
        self.assertFalse(os.path.exists(temp_file.name))
    
    def test_cleanup_instance_not_found(self):
        """Test cleanup of non-existent instance."""
        # Should not raise error
        self.manager._cleanup_instance("non-existent")
    
    def test_stop_all_servers_empty(self):
        """Test stopping all servers when none exist."""
        with patch('mcp_server_manager.logger') as mock_logger:
            result = self.manager.stop_all_servers()
        
        self.assertTrue(result)
        mock_logger.info.assert_any_call("Stopping all server instances...")
        mock_logger.info.assert_any_call("All servers stopped")


if __name__ == "__main__":
    unittest.main()