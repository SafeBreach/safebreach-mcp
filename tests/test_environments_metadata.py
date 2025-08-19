"""
Tests for SafeBreach MCP Environments Metadata

This test suite covers the environment configuration loading functionality
including the new SAFEBREACH_LOCAL_ENV environment variable support.
"""

import os
import json
import unittest
from unittest.mock import patch, mock_open
import tempfile

class TestEnvironmentsMetadata(unittest.TestCase):
    """Test suite for environments metadata functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing environment variables that might affect tests
        self.env_vars_to_clean = [
            'SAFEBREACH_ENVS_FILE',
            'SAFEBREACH_LOCAL_ENV',
            'test_console_apitoken',
            'my_local_console_apitoken'
        ]
        
        self.original_env_vars = {}
        for var in self.env_vars_to_clean:
            self.original_env_vars[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment variables
        for var, original_value in self.original_env_vars.items():
            if original_value is not None:
                os.environ[var] = original_value
            elif var in os.environ:
                del os.environ[var]
        
        # Clear modules cache to ensure fresh imports in each test
        import sys
        modules_to_clear = [
            'safebreach_mcp_core.environments_metadata'
        ]
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]
    
    def test_default_environments_loading(self):
        """Test that default environments are loaded correctly."""
        from safebreach_mcp_core.environments_metadata import safebreach_envs, get_environment_by_name
        
        # Verify default environments exist
        self.assertIn("demo-console", safebreach_envs)
        self.assertIn("example-console", safebreach_envs)
        
        # Test get_environment_by_name function
        demo_env = get_environment_by_name("demo-console")
        self.assertEqual(demo_env["url"], "demo.safebreach.com")
        self.assertEqual(demo_env["account"], "1234567890")
        self.assertEqual(demo_env["secret_config"]["provider"], "env_var")
    
    def test_get_environment_by_name_not_found(self):
        """Test that get_environment_by_name raises error for unknown environment."""
        from safebreach_mcp_core.environments_metadata import get_environment_by_name
        
        with self.assertRaises(ValueError) as context:
            get_environment_by_name("non-existent-console")
        
        self.assertIn("Environment 'non-existent-console' not found", str(context.exception))
    
    def test_safebreach_envs_file_loading(self):
        """Test loading environments from SAFEBREACH_ENVS_FILE."""
        # Create a temporary JSON file
        test_envs = {
            "file-test-console": {
                "url": "file-test.safebreach.com",
                "account": "1111111111",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "file-test-console-apitoken"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(test_envs, temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Set environment variable to point to temp file
            os.environ['SAFEBREACH_ENVS_FILE'] = temp_file_path
            
            # Force reload of module to pick up new environment variables
            import importlib
            import safebreach_mcp_core.environments_metadata
            importlib.reload(safebreach_mcp_core.environments_metadata)
            
            # Import after reload (this triggers the file loading)
            from safebreach_mcp_core.environments_metadata import safebreach_envs, get_environment_by_name
            
            # Verify the environment was loaded
            self.assertIn("file-test-console", safebreach_envs)
            
            file_env = get_environment_by_name("file-test-console")
            self.assertEqual(file_env["url"], "file-test.safebreach.com")
            self.assertEqual(file_env["account"], "1111111111")
            
        finally:
            # Clean up temp file
            os.unlink(temp_file_path)
    
    def test_safebreach_local_env_loading(self):
        """Test loading environments from SAFEBREACH_LOCAL_ENV environment variable."""
        # Define test environment configuration
        local_env_config = {
            "local-test-console": {
                "url": "local-test.safebreach.com",
                "account": "2222222222",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "local-test-console-apitoken"
                }
            },
            "advanced-local-console": {
                "url": "advanced.safebreach.com", 
                "account": "3333333333",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "advanced-local-console-apitoken"
                },
                "mcp_servers": {
                    "config": {
                        "url": "http://localhost:8000",
                        "base_path": "/api/config"
                    },
                    "data": {
                        "url": "http://localhost:8001",
                        "base_path": "/api/data"
                    },
                    "playbook": {
                        "url": "http://localhost:8003",
                        "base_path": "/api/playbook"
                    }
                }
            }
        }
        
        # Set environment variable with JSON configuration
        os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_env_config)
        
        # Force reload of module to pick up new environment variables
        import importlib
        import safebreach_mcp_core.environments_metadata
        importlib.reload(safebreach_mcp_core.environments_metadata)
        
        # Import after reload (this triggers the environment loading)
        from safebreach_mcp_core.environments_metadata import safebreach_envs, get_environment_by_name
        
        # Verify the environments were loaded
        self.assertIn("local-test-console", safebreach_envs)
        self.assertIn("advanced-local-console", safebreach_envs)
        
        # Test basic environment
        local_env = get_environment_by_name("local-test-console")
        self.assertEqual(local_env["url"], "local-test.safebreach.com")
        self.assertEqual(local_env["account"], "2222222222")
        self.assertEqual(local_env["secret_config"]["provider"], "env_var")
        
        # Test advanced environment with MCP server URLs
        advanced_env = get_environment_by_name("advanced-local-console")
        self.assertEqual(advanced_env["url"], "advanced.safebreach.com")
        self.assertEqual(advanced_env["account"], "3333333333")
        self.assertIn("mcp_servers", advanced_env)
        
        # Verify MCP server configuration
        mcp_servers = advanced_env["mcp_servers"]
        self.assertEqual(mcp_servers["config"]["url"], "http://localhost:8000")
        self.assertEqual(mcp_servers["config"]["base_path"], "/api/config")
        self.assertEqual(mcp_servers["data"]["url"], "http://localhost:8001")
        self.assertEqual(mcp_servers["data"]["base_path"], "/api/data")
        self.assertEqual(mcp_servers["playbook"]["url"], "http://localhost:8003")
        self.assertEqual(mcp_servers["playbook"]["base_path"], "/api/playbook")
    
    def test_safebreach_local_env_invalid_json(self):
        """Test that invalid JSON in SAFEBREACH_LOCAL_ENV raises proper error."""
        # Set invalid JSON
        os.environ['SAFEBREACH_LOCAL_ENV'] = '{"invalid": json}'
        
        # Import should raise ValueError
        with self.assertRaises(ValueError) as context:
            from safebreach_mcp_core.environments_metadata import safebreach_envs
        
        self.assertIn("Invalid JSON in SAFEBREACH_LOCAL_ENV", str(context.exception))
    
    def test_combined_environment_loading(self):
        """Test that both SAFEBREACH_ENVS_FILE and SAFEBREACH_LOCAL_ENV can work together."""
        # Create environments for file loading
        file_envs = {
            "file-env": {
                "url": "file.safebreach.com",
                "account": "4444444444",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "file-env-apitoken"
                }
            }
        }
        
        # Create environments for local env loading
        local_envs = {
            "local-env": {
                "url": "local.safebreach.com",
                "account": "5555555555",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "local-env-apitoken"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(file_envs, temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Set both environment variables
            os.environ['SAFEBREACH_ENVS_FILE'] = temp_file_path
            os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_envs)
            
            # Force reload of module to pick up new environment variables
            import importlib
            import safebreach_mcp_core.environments_metadata
            importlib.reload(safebreach_mcp_core.environments_metadata)
            
            # Import after reload
            from safebreach_mcp_core.environments_metadata import safebreach_envs, get_environment_by_name
            
            # Verify both environments are available
            self.assertIn("file-env", safebreach_envs)
            self.assertIn("local-env", safebreach_envs)
            
            # Verify they load correctly
            file_env = get_environment_by_name("file-env")
            self.assertEqual(file_env["url"], "file.safebreach.com")
            
            local_env = get_environment_by_name("local-env")
            self.assertEqual(local_env["url"], "local.safebreach.com")
            
        finally:
            os.unlink(temp_file_path)
    
    def test_local_env_overrides_file_env(self):
        """Test that SAFEBREACH_LOCAL_ENV can override environments from SAFEBREACH_ENVS_FILE."""
        # Environment defined in both file and local env with different values
        common_env_name = "override-test-console"
        
        file_envs = {
            common_env_name: {
                "url": "file-version.safebreach.com",
                "account": "1111111111",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "override-test-console-apitoken"
                }
            }
        }
        
        local_envs = {
            common_env_name: {
                "url": "local-version.safebreach.com",
                "account": "2222222222",
                "secret_config": {
                    "provider": "aws_ssm",
                    "parameter_name": "override-test-console-apitoken"
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(file_envs, temp_file)
            temp_file_path = temp_file.name
        
        try:
            # Set both environment variables
            os.environ['SAFEBREACH_ENVS_FILE'] = temp_file_path
            os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_envs)
            
            # Force reload of module to pick up new environment variables
            import importlib
            import safebreach_mcp_core.environments_metadata
            importlib.reload(safebreach_mcp_core.environments_metadata)
            
            # Import after reload
            from safebreach_mcp_core.environments_metadata import safebreach_envs, get_environment_by_name
            
            # Verify local env overrode file env
            override_env = get_environment_by_name(common_env_name)
            self.assertEqual(override_env["url"], "local-version.safebreach.com")
            self.assertEqual(override_env["account"], "2222222222")
            self.assertEqual(override_env["secret_config"]["provider"], "aws_ssm")
            
        finally:
            os.unlink(temp_file_path)
    
    def test_per_service_urls_functionality(self):
        """Test that per-service URLs work correctly in get_api_base_url function."""
        # Test configuration with per-service URLs
        local_envs = {
            "microservices-console": {
                "url": "default.safebreach.com",
                "urls": {
                    "config": "config-api.safebreach.com",
                    "data": "data-api.safebreach.com",
                    "playbook": "playbook-api.safebreach.com"
                },
                "account": "1234567890",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "microservices_console_apitoken"
                }
            }
        }
        
        # Set environment variable with per-service URLs
        os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_envs)
        
        # Force reload of module to pick up new environment variables
        import importlib
        import safebreach_mcp_core.environments_metadata
        importlib.reload(safebreach_mcp_core.environments_metadata)
        
        # Import after reload
        from safebreach_mcp_core.environments_metadata import get_api_base_url
        
        # Test service-specific URLs are used
        self.assertEqual(get_api_base_url("microservices-console", "config"), "https://config-api.safebreach.com")
        self.assertEqual(get_api_base_url("microservices-console", "data"), "https://data-api.safebreach.com")
        self.assertEqual(get_api_base_url("microservices-console", "playbook"), "https://playbook-api.safebreach.com")
        
        # Test fallback to default URL for services without specific URLs
        self.assertEqual(get_api_base_url("microservices-console", "siem"), "https://default.safebreach.com")
    
    def test_per_service_urls_with_http_protocol(self):
        """Test that per-service URLs preserve HTTP/HTTPS protocols."""
        # Test configuration with HTTP URLs (should not be modified)
        local_envs = {
            "http-console": {
                "url": "default.safebreach.com",
                "urls": {
                    "config": "http://config.local:8080",
                    "data": "https://data.secure.com",
                    "playbook": "plain-playbook.com"  # Should get https:// prefix
                },
                "account": "1234567890",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "http_console_apitoken"
                }
            }
        }
        
        # Set environment variable
        os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_envs)
        
        # Force reload
        import importlib
        import safebreach_mcp_core.environments_metadata
        importlib.reload(safebreach_mcp_core.environments_metadata)
        
        from safebreach_mcp_core.environments_metadata import get_api_base_url
        
        # Test HTTP URLs are preserved
        self.assertEqual(get_api_base_url("http-console", "config"), "http://config.local:8080")
        self.assertEqual(get_api_base_url("http-console", "data"), "https://data.secure.com")
        # Test plain URLs get https:// prefix
        self.assertEqual(get_api_base_url("http-console", "playbook"), "https://plain-playbook.com")
    
    def test_per_service_urls_priority_over_default(self):
        """Test that per-service URLs take priority over default URL."""
        # Configuration where service URL differs from default
        local_envs = {
            "priority-console": {
                "url": "should-not-be-used.com",
                "urls": {
                    "config": "priority-config.com"
                },
                "account": "1234567890",
                "secret_config": {
                    "provider": "env_var",
                    "parameter_name": "priority_console_apitoken"
                }
            }
        }
        
        os.environ['SAFEBREACH_LOCAL_ENV'] = json.dumps(local_envs)
        
        import importlib
        import safebreach_mcp_core.environments_metadata
        importlib.reload(safebreach_mcp_core.environments_metadata)
        
        from safebreach_mcp_core.environments_metadata import get_api_base_url
        
        # Service with specific URL should use specific URL
        self.assertEqual(get_api_base_url("priority-console", "config"), "https://priority-config.com")
        # Service without specific URL should fall back to default
        self.assertEqual(get_api_base_url("priority-console", "data"), "https://should-not-be-used.com")


if __name__ == "__main__":
    unittest.main()