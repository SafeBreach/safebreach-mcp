"""
Tests for SafeBreach Config Functions

This module tests the config functions that handle simulator operations.
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_config.config_functions import (
    sb_get_console_simulators,
    sb_get_simulator_details,
    _get_all_simulators_from_cache_or_api,
    _apply_simulator_filters,
    _apply_simulator_ordering,
    simulators_cache,
    CACHE_TTL
)

class TestConfigFunctions:
    """Test suite for config functions."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Clear cache before each test
        simulators_cache.clear()
    
    @pytest.fixture
    def mock_simulator_data(self):
        """Mock simulator data for testing."""
        return [
            {
                "id": "sim1",
                "name": "Test Simulator 1",
                "isConnected": True,
                "isEnabled": True,
                "version": "1.0.0",
                "labels": ["production", "web-server"],
                "ipAddresses": ["192.168.1.1"],
                "isCritical": True,
                "lastActivity": 1640995200,
                "deployment": {},
                "proxies": [],
                "externalIp": "192.168.1.1",
                "internalIp": "192.168.1.1",
                "nodeInfo": {
                    "MACHINE_INFO": {
                        "OS": {
                            "type": "Linux",
                            "version": "Ubuntu 20.04"
                        }
                    }
                }
            },
            {
                "id": "sim2",
                "name": "Test Simulator 2",
                "isConnected": False,
                "isEnabled": True,
                "version": "1.1.0",
                "labels": ["staging", "database"],
                "ipAddresses": ["192.168.1.2"],
                "isCritical": False,
                "lastActivity": 1640995300,
                "deployment": {},
                "proxies": [],
                "externalIp": "192.168.1.2",
                "internalIp": "192.168.1.2",
                "nodeInfo": {
                    "MACHINE_INFO": {
                        "OS": {
                            "type": "Windows",
                            "version": "Windows 10"
                        }
                    }
                }
            }
        ]
    
    @pytest.fixture
    def mock_api_response(self, mock_simulator_data):
        """Mock API response for simulators."""
        return {"data": mock_simulator_data}
    
    @patch('safebreach_mcp_config.config_functions.safebreach_envs', {'test-console': {'url': 'test.com', 'account': '123'}})
    @patch('safebreach_mcp_config.config_functions.get_secret_for_console')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_from_cache_or_api_success(self, mock_get, mock_secret, mock_api_response):
        """Test successful retrieval of simulators from API."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = mock_api_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test
        result = _get_all_simulators_from_cache_or_api("test-console")
        
        # Assertions
        assert len(result) == 2
        assert result[0]["id"] == "sim1"
        assert result[1]["id"] == "sim2"
        
        # Verify API was called
        mock_get.assert_called_once()
        mock_secret.assert_called_once_with("test-console")
    
    @patch('safebreach_mcp_config.config_functions.get_secret_for_console')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_from_cache(self, mock_get, mock_secret, mock_simulator_data):
        """Test retrieval of simulators from cache."""
        # Setup cache
        cache_key = "simulators_test-console"
        current_time = time.time()
        simulators_cache[cache_key] = (mock_simulator_data, current_time)
        
        # Test
        result = _get_all_simulators_from_cache_or_api("test-console")
        
        # Assertions
        assert len(result) == 2
        assert result[0]["id"] == "sim1"
        
        # Verify API was NOT called
        mock_get.assert_not_called()
        mock_secret.assert_not_called()
    
    @patch('safebreach_mcp_config.config_functions.safebreach_envs', {'test-console': {'url': 'test.com', 'account': '123'}})
    @patch('safebreach_mcp_config.config_functions.get_secret_for_console')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_cache_expired(self, mock_get, mock_secret, mock_simulator_data, mock_api_response):
        """Test cache expiration and API fallback."""
        # Setup expired cache
        cache_key = "simulators_test-console"
        old_time = time.time() - CACHE_TTL - 100
        simulators_cache[cache_key] = (mock_simulator_data, old_time)
        
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = mock_api_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test
        result = _get_all_simulators_from_cache_or_api("test-console")
        
        # Assertions
        assert len(result) == 2
        
        # Verify API was called due to cache expiration
        mock_get.assert_called_once()
        mock_secret.assert_called_once_with("test-console")
    
    def test_apply_simulator_filters_status(self, mock_simulator_data):
        """Test status filtering."""
        # Test connected filter
        connected = _apply_simulator_filters(mock_simulator_data, status_filter="connected")
        assert len(connected) == 1
        assert connected[0]["id"] == "sim1"
        
        # Test disconnected filter
        disconnected = _apply_simulator_filters(mock_simulator_data, status_filter="disconnected")
        assert len(disconnected) == 1
        assert disconnected[0]["id"] == "sim2"
        
        # Test enabled filter
        enabled = _apply_simulator_filters(mock_simulator_data, status_filter="enabled")
        assert len(enabled) == 2  # Both are enabled
        
        # Test disabled filter
        disabled = _apply_simulator_filters(mock_simulator_data, status_filter="disabled")
        assert len(disabled) == 0  # None are disabled
    
    def test_apply_simulator_filters_name(self, mock_simulator_data):
        """Test name filtering."""
        filtered = _apply_simulator_filters(mock_simulator_data, name_filter="1")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim1"
        
        filtered = _apply_simulator_filters(mock_simulator_data, name_filter="nonexistent")
        assert len(filtered) == 0
    
    def test_apply_simulator_filters_labels(self, mock_simulator_data):
        """Test label filtering."""
        filtered = _apply_simulator_filters(mock_simulator_data, label_filter="production")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim1"
        
        filtered = _apply_simulator_filters(mock_simulator_data, label_filter="server")
        assert len(filtered) == 1  # Matches "web-server"
        assert filtered[0]["id"] == "sim1"
    
    def test_apply_simulator_filters_os_type(self, mock_simulator_data):
        """Test OS type filtering."""
        # Transform data to match what the filter expects
        transformed_data = [
            {"id": "sim1", "OS": {"type": "Linux"}},
            {"id": "sim2", "OS": {"type": "Windows"}}
        ]
        
        filtered = _apply_simulator_filters(transformed_data, os_type_filter="Linux")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim1"
        
        filtered = _apply_simulator_filters(transformed_data, os_type_filter="Windows")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim2"
    
    def test_apply_simulator_filters_critical(self, mock_simulator_data):
        """Test critical filtering."""
        filtered = _apply_simulator_filters(mock_simulator_data, critical_only=True)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim1"
        
        filtered = _apply_simulator_filters(mock_simulator_data, critical_only=False)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "sim2"
    
    def test_apply_simulator_ordering(self, mock_simulator_data):
        """Test simulator ordering."""
        # Test ascending order by name (default)
        ordered = _apply_simulator_ordering(mock_simulator_data, order_by="name", order_direction="asc")
        assert ordered[0]["id"] == "sim1"  # "Test Simulator 1" comes first
        assert ordered[1]["id"] == "sim2"
        
        # Test descending order by name
        ordered = _apply_simulator_ordering(mock_simulator_data, order_by="name", order_direction="desc")
        assert ordered[0]["id"] == "sim2"  # "Test Simulator 2" comes first
        assert ordered[1]["id"] == "sim1"
        
        # Test order by version
        ordered = _apply_simulator_ordering(mock_simulator_data, order_by="version", order_direction="asc")
        assert ordered[0]["version"] == "1.0.0"
        assert ordered[1]["version"] == "1.1.0"
    
    @patch('safebreach_mcp_config.config_functions._get_all_simulators_from_cache_or_api')
    def test_sb_get_console_simulators_success(self, mock_get_all, mock_simulator_data):
        """Test successful console simulators retrieval."""
        mock_get_all.return_value = mock_simulator_data
        
        result = sb_get_console_simulators("test-console")
        
        assert "simulators" in result
        assert "total_simulators" in result
        assert "applied_filters" in result
        assert len(result["simulators"]) == 2
        assert result["total_simulators"] == 2
    
    @patch('safebreach_mcp_config.config_functions._get_all_simulators_from_cache_or_api')
    def test_sb_get_console_simulators_with_filters(self, mock_get_all, mock_simulator_data):
        """Test console simulators retrieval with filters."""
        mock_get_all.return_value = mock_simulator_data
        
        result = sb_get_console_simulators(
            "test-console",
            status_filter="connected",
            name_filter="1",
            critical_only=True
        )
        
        assert len(result["simulators"]) == 1
        assert result["simulators"][0]["id"] == "sim1"
        assert result["applied_filters"]["status_filter"] == "connected"
        assert result["applied_filters"]["name_filter"] == "1"
        assert result["applied_filters"]["critical_only"] is True
    
    @patch('safebreach_mcp_config.config_functions._get_all_simulators_from_cache_or_api')
    def test_sb_get_console_simulators_error(self, mock_get_all):
        """Test error handling in console simulators retrieval."""
        mock_get_all.side_effect = Exception("API Error")
        
        result = sb_get_console_simulators("test-console")
        
        assert "error" in result
        assert "API Error" in result["error"]
        assert result["console"] == "test-console"
    
    @patch('safebreach_mcp_config.config_functions.safebreach_envs', {'test-console': {'url': 'test.com', 'account': '123'}})
    @patch('safebreach_mcp_config.config_functions.get_secret_for_console')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_sb_get_simulator_details_success(self, mock_get, mock_secret):
        """Test successful simulator details retrieval."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "id": "sim1",
                "name": "Test Simulator",
                "isConnected": True,
                "isEnabled": True,
                "version": "1.0.0",
                "labels": ["test"],
                "ipAddresses": ["192.168.1.1"],
                "isCritical": False,
                "lastActivity": 1640995200,
                "deployment": {},
                "proxies": [],
                "externalIp": "192.168.1.1",
                "internalIp": "192.168.1.1",
                "nodeInfo": {
                    "MACHINE_INFO": {
                        "OS": {
                            "type": "Linux",
                            "version": "Ubuntu 20.04"
                        }
                    }
                }
            }
        }
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = sb_get_simulator_details("test-console", "sim1")
        
        assert "id" in result
        assert result["id"] == "sim1"
        mock_get.assert_called_once()
        mock_secret.assert_called_once_with("test-console")
    
    @patch('safebreach_mcp_config.config_functions.safebreach_envs', {'test-console': {'url': 'test.com', 'account': '123'}})
    @patch('safebreach_mcp_config.config_functions.get_secret_for_console')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_sb_get_simulator_details_error(self, mock_get, mock_secret):
        """Test error handling in simulator details retrieval."""
        mock_secret.return_value = "test-token"
        mock_get.side_effect = Exception("API Error")
        
        # The function should now raise an exception
        with pytest.raises(Exception) as exc_info:
            sb_get_simulator_details("test-console", "sim1")
        
        assert "API Error" in str(exc_info.value)
    
    def test_unknown_console_validation(self):
        """Test that unknown console names return proper error messages."""
        # Test sb_get_console_simulators with unknown console
        result = sb_get_console_simulators(console="unknown_console")
        
        # Should return error, not empty results
        assert "error" in result
        assert result["console"] == "unknown_console"
        assert "not found" in result["error"]
        assert "Available consoles:" in result["error"]
        
    def test_unknown_console_validation_simulator_details(self):
        """Test unknown console validation in sb_get_simulator_details."""
        # Test sb_get_simulator_details - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details(console="unknown_console", simulator_id="sim123")
        assert "not found" in str(exc_info.value)
    
    @patch('safebreach_mcp_config.config_functions.safebreach_envs')
    def test_secret_provider_failure_validation(self, mock_envs):
        """Test that secret provider failures return proper error messages."""
        from botocore.exceptions import ClientError
        
        # Mock environment with non-existent parameter
        mock_envs.__getitem__.return_value = {
            "url": "test.com",
            "account": "123", 
            "secret_config": {
                "provider": "aws_ssm",
                "parameter_name": "non-existent-config-param"
            }
        }
        mock_envs.__contains__.return_value = True
        mock_envs.keys.return_value = ["test-console"]
        
        # Mock ClientError for parameter not found
        with patch('safebreach_mcp_config.config_functions.get_secret_for_console') as mock_secret:
            mock_secret.side_effect = ClientError(
                error_response={'Error': {'Code': 'ParameterNotFound', 'Message': 'Parameter not found'}},
                operation_name='GetParameter'
            )
            
            # Test sb_get_console_simulators
            result = sb_get_console_simulators(console="test-console")
            assert "error" in result
            assert result.get("console") == "test-console"
            assert "ParameterNotFound" in result["error"]
            
            # Test sb_get_simulator_details - should raise ClientError
            with pytest.raises(ClientError) as exc_info:
                sb_get_simulator_details(console="test-console", simulator_id="sim123")
            assert "ParameterNotFound" in str(exc_info.value)
    
    def test_sb_get_simulator_details_empty_simulator_id(self):
        """Test validation for empty simulator_id parameter."""
        # Test empty string
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details("test-console", "")
        assert "simulator_id parameter is required and cannot be empty" in str(exc_info.value)
        
        # Test whitespace-only string
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details("test-console", "   ")
        assert "simulator_id parameter is required and cannot be empty" in str(exc_info.value)
    
    def test_sb_get_console_simulators_invalid_order_by(self):
        """Test validation for invalid order_by parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_console_simulators("test-console", order_by="invalid_field")
        assert "Invalid order_by parameter 'invalid_field'" in str(exc_info.value)
        assert "name, id, version, isConnected, isEnabled" in str(exc_info.value)
    
    def test_sb_get_console_simulators_invalid_order_direction(self):
        """Test validation for invalid order_direction parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_console_simulators("test-console", order_direction="invalid_direction")
        assert "Invalid order_direction parameter 'invalid_direction'" in str(exc_info.value)
        assert "asc, desc" in str(exc_info.value)
    
    def test_sb_get_console_simulators_invalid_status_filter(self):
        """Test validation for invalid status_filter parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_console_simulators("test-console", status_filter="invalid_status")
        assert "Invalid status_filter parameter 'invalid_status'" in str(exc_info.value)
        assert "connected, disconnected, enabled, disabled" in str(exc_info.value)
        
        # Test that valid values work with case insensitivity
        # This should NOT raise an error since validation is case-insensitive
        try:
            result = sb_get_console_simulators("Test-Console", status_filter="CONNECTED")
            # If we get here without validation error, case-insensitive validation is working
        except Exception as e:
            # Only acceptable exceptions are AWS/network related, not validation errors
            if "Invalid status_filter parameter" in str(e):
                pytest.fail("Case-insensitive validation should accept 'CONNECTED'")