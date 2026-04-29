"""
Tests for SafeBreach Config Functions

This module tests the config functions that handle simulator operations.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_config.config_functions import (
    sb_get_console_simulators,
    sb_get_simulator_details,
    _get_all_simulators_from_cache_or_api,
    _apply_simulator_filters,
    _apply_simulator_ordering,
    simulators_cache,
    sb_get_scenarios,
    sb_get_scenario_details,
    _get_all_scenarios_from_cache_or_api,
    _get_categories_map_from_cache_or_api,
    _get_all_plans_from_cache_or_api,
    scenarios_cache,
    categories_cache,
    plans_cache,
    clear_scenarios_cache,
    clear_categories_cache,
    clear_plans_cache,
)
from safebreach_mcp_core.token_context import get_cache_user_suffix

class TestConfigFunctions:
    """Test suite for config functions."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)
    
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
    
    @patch('safebreach_mcp_config.config_functions._get_assets_map_from_cache_or_api', return_value={})
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_from_cache_or_api_success(self, mock_get, mock_account_id, mock_base_url, mock_assets, mock_api_response):
        """Test successful retrieval of simulators from API."""
        # Setup mocks
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
    
    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_from_cache(self, mock_get, mock_cache_enabled, mock_simulator_data):
        """Test retrieval of simulators from cache when caching is enabled."""
        # Setup cache
        cache_key = f"simulators_test-console{get_cache_user_suffix()}"
        simulators_cache.set(cache_key, mock_simulator_data)

        # Test
        result = _get_all_simulators_from_cache_or_api("test-console")

        # Assertions
        assert len(result) == 2
        assert result[0]["id"] == "sim1"

        # Verify API was NOT called
        mock_get.assert_not_called()
    
    @patch('safebreach_mcp_config.config_functions._get_assets_map_from_cache_or_api', return_value={})
    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_get_all_simulators_cache_miss_fetches_api(self, mock_get, mock_account_id, mock_base_url, mock_cache_enabled, mock_assets, mock_api_response):
        """Test that cache miss (expired or empty) falls through to API fetch."""
        # Cache is empty (simulates expired/missing entry - TTLCache handles expiry internally)

        # Setup mocks
        mock_response = Mock()
        mock_response.json.return_value = mock_api_response
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test
        result = _get_all_simulators_from_cache_or_api("test-console")

        # Assertions
        assert len(result) == 2

        # Verify API was called due to cache miss
        mock_get.assert_called_once()
    
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
    
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_sb_get_simulator_details_success(self, mock_get, mock_account_id, mock_base_url):
        """Test successful simulator details retrieval."""
        # Setup mocks
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
        
        result = sb_get_simulator_details("sim1", "test-console")
        
        assert "id" in result
        assert result["id"] == "sim1"
        mock_get.assert_called_once()
    
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_sb_get_simulator_details_error(self, mock_get, mock_account_id, mock_base_url):
        """Test error handling in simulator details retrieval."""
        mock_get.side_effect = Exception("API Error")
        
        # The function should now raise an exception
        with pytest.raises(Exception) as exc_info:
            sb_get_simulator_details("sim1", "test-console")
        
        assert "API Error" in str(exc_info.value)
    
    def test_unknown_console_validation(self):
        """Test that unknown console names return proper error messages."""
        # Test sb_get_console_simulators with unknown console
        result = sb_get_console_simulators(console="unknown_console")
        
        # Should return error, not empty results
        assert "error" in result
        assert result["console"] == "unknown_console"
        assert "not found" in result["error"] or "No URL configured" in result["error"]

    def test_unknown_console_validation_simulator_details(self):
        """Test unknown console validation in sb_get_simulator_details."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details(simulator_id="sim123", console="unknown_console")
        assert "not found" in str(exc_info.value) or "No URL configured" in str(exc_info.value)
    
    def test_sb_get_simulator_details_empty_simulator_id(self):
        """Test validation for empty simulator_id parameter."""
        # Test empty string
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details("", "test-console")
        assert "simulator_id parameter is required and cannot be empty" in str(exc_info.value)
        
        # Test whitespace-only string
        with pytest.raises(ValueError) as exc_info:
            sb_get_simulator_details("   ", "test-console")
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


# --- Scenario Function Tests ---

MOCK_SCENARIO_DATA = [
    {
        "id": "aaa-111-222-333",
        "name": "CISA Alert Akira Ransomware",
        "description": "A known threat scenario",
        "createdBy": "SafeBreach",
        "recommended": True,
        "categories": [2],
        "tags": ["ransomware"],
        "createdAt": "2025-11-14T00:00:00.000Z",
        "updatedAt": "2026-01-22T00:00:00.000Z",
        "steps": [
            {
                "name": "Network Infiltration",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {},
                "attackerFilter": {},
                "attacksFilter": {"playbook": {"values": [11503, 11505]}}
            }
        ],
        "order": None, "actions": None, "edges": None, "phases": {}
    },
    {
        "id": "bbb-444-555-666",
        "name": "KongTuke Threat Group",
        "description": None,
        "createdBy": "SafeBreach",
        "recommended": False,
        "categories": [3],
        "tags": None,
        "createdAt": "2026-02-10T00:00:00.000Z",
        "updatedAt": "2026-02-10T00:00:00.000Z",
        "steps": [
            {
                "name": "Infection",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {},
                "attackerFilter": {},
                "attacksFilter": {}
            },
            {
                "name": "Lateral",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {},
                "attackerFilter": {},
                "attacksFilter": {}
            }
        ],
        "order": None, "actions": None, "edges": None, "phases": {}
    },
]

MOCK_CATEGORIES_DATA = [
    {"id": 2, "name": "Known Threats Series", "description": "Known threats", "icon": "flag", "order": 1},
    {"id": 3, "name": "Threat Groups", "description": "Threat groups", "icon": "users", "order": 2},
    {"id": 4, "name": "Baseline Scenarios", "description": "Baselines", "icon": "crosshairs", "order": 3},
]


class TestGetAllScenariosFromCacheOrApi:
    """Test _get_all_scenarios_from_cache_or_api function."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        clear_scenarios_cache()
        clear_categories_cache()

    def teardown_method(self):
        clear_scenarios_cache()
        clear_categories_cache()

    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_api_call_success(self, mock_get, mock_base_url):
        mock_response = Mock()
        mock_response.json.return_value = MOCK_SCENARIO_DATA
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = _get_all_scenarios_from_cache_or_api("test-console")

        assert len(result) == 2
        assert result[0]["id"] == "aaa-111-222-333"
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0] if mock_get.call_args[0] else mock_get.call_args[1].get('url', '')
        assert '/api/content-manager/vLatest/scenarios' in str(mock_get.call_args)

    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_cache_hit(self, mock_get, mock_cache_enabled):
        scenarios_cache.set(f"scenarios_test-console{get_cache_user_suffix()}", MOCK_SCENARIO_DATA)

        result = _get_all_scenarios_from_cache_or_api("test-console")

        assert len(result) == 2
        mock_get.assert_not_called()

    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_cache_miss_fetches_api(self, mock_get, mock_base_url, mock_cache_enabled):
        mock_response = Mock()
        mock_response.json.return_value = MOCK_SCENARIO_DATA
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = _get_all_scenarios_from_cache_or_api("test-console")

        assert len(result) == 2
        mock_get.assert_called_once()

    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_api_error_propagates(self, mock_get, mock_base_url):
        mock_get.side_effect = Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            _get_all_scenarios_from_cache_or_api("test-console")


class TestGetCategoriesMapFromCacheOrApi:
    """Test _get_categories_map_from_cache_or_api function."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        clear_scenarios_cache()
        clear_categories_cache()

    def teardown_method(self):
        clear_scenarios_cache()
        clear_categories_cache()

    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_returns_id_to_name_map(self, mock_get, mock_base_url):
        mock_response = Mock()
        mock_response.json.return_value = MOCK_CATEGORIES_DATA
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = _get_categories_map_from_cache_or_api("test-console")

        assert isinstance(result, dict)
        assert result[2] == "Known Threats Series"
        assert result[3] == "Threat Groups"
        assert result[4] == "Baseline Scenarios"

    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_cache_hit(self, mock_get, mock_cache_enabled):
        categories_cache.set(f"categories_test-console{get_cache_user_suffix()}", {2: "Known Threats Series"})

        result = _get_categories_map_from_cache_or_api("test-console")

        assert result[2] == "Known Threats Series"
        mock_get.assert_not_called()

    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_api_error_propagates(self, mock_get, mock_base_url):
        mock_get.side_effect = Exception("API unreachable")

        with pytest.raises(Exception, match="API unreachable"):
            _get_categories_map_from_cache_or_api("test-console")


class TestSbGetScenarios:
    """Test sb_get_scenarios orchestration function."""

    def setup_method(self):
        clear_scenarios_cache()
        clear_categories_cache()
        clear_plans_cache()

    def teardown_method(self):
        clear_scenarios_cache()
        clear_categories_cache()
        clear_plans_cache()

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_full_orchestration(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series", 3: "Threat Groups"}

        result = sb_get_scenarios("test-console")

        assert "page_number" in result
        assert "total_pages" in result
        assert "total_scenarios" in result
        assert "scenarios_in_page" in result
        assert result["total_scenarios"] == 2
        assert result["page_number"] == 0

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_pagination_with_large_dataset(self, mock_scenarios, mock_categories, mock_plans):
        large_list = [
            {
                "id": f"scenario-{i}", "name": f"Scenario {i}",
                "description": None, "createdBy": "SafeBreach",
                "recommended": False, "categories": [2], "tags": None,
                "createdAt": "2025-01-01T00:00:00.000Z",
                "updatedAt": "2025-01-01T00:00:00.000Z",
                "steps": [], "order": None, "actions": None, "edges": None, "phases": {}
            }
            for i in range(25)
        ]
        mock_scenarios.return_value = large_list
        mock_categories.return_value = {2: "Known Threats Series"}

        result = sb_get_scenarios("test-console", page_number=0)

        assert result["total_scenarios"] == 25
        assert result["total_pages"] == 3
        assert len(result["scenarios_in_page"]) == 10
        assert result["hint_to_agent"] is not None

    def test_invalid_order_by(self):
        with pytest.raises(ValueError, match="Invalid order_by"):
            sb_get_scenarios("test-console", order_by="invalid_field")

    def test_invalid_creator_filter(self):
        with pytest.raises(ValueError, match="Invalid creator_filter"):
            sb_get_scenarios("test-console", creator_filter="invalid")

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_api_failure_returns_error_dict(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.side_effect = Exception("API timeout")

        result = sb_get_scenarios("test-console")

        assert "error" in result
        assert "API timeout" in result["error"]
        assert result["console"] == "test-console"

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_applied_filters_metadata(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series", 3: "Threat Groups"}

        result = sb_get_scenarios(
            "test-console",
            name_filter="Akira",
            creator_filter="safebreach",
        )

        assert "applied_filters" in result
        assert result["applied_filters"]["name_filter"] == "Akira"
        assert result["applied_filters"]["creator_filter"] == "safebreach"

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_merges_oob_and_custom(self, mock_scenarios, mock_categories, mock_plans):
        """No filter should return both OOB scenarios and custom plans."""
        mock_scenarios.return_value = MOCK_SCENARIO_DATA  # 2 OOB
        mock_categories.return_value = {2: "Known Threats Series", 3: "Threat Groups"}
        mock_plans.return_value = [
            {
                "id": 100, "name": "Custom Plan A",
                "description": None, "tags": [], "userId": 1,
                "originalScenarioId": None, "steps": [],
                "createdAt": "2026-01-01T00:00:00.000Z",
                "updatedAt": "2026-01-01T00:00:00.000Z",
            }
        ]

        result = sb_get_scenarios("test-console")

        assert result["total_scenarios"] == 3  # 2 OOB + 1 custom
        source_types = {s["source_type"] for s in result["scenarios_in_page"]}
        assert source_types == {"oob", "custom"}

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_creator_filter_custom_only_fetches_plans(self, mock_scenarios, mock_categories, mock_plans):
        """creator_filter='custom' should skip fetching OOB scenarios."""
        mock_plans.return_value = [
            {
                "id": 100, "name": "Custom Plan A",
                "description": None, "tags": [], "userId": 1,
                "originalScenarioId": None, "steps": [],
                "createdAt": "2026-01-01T00:00:00.000Z",
                "updatedAt": "2026-01-01T00:00:00.000Z",
            }
        ]

        result = sb_get_scenarios("test-console", creator_filter="custom")

        assert result["total_scenarios"] == 1
        assert result["scenarios_in_page"][0]["source_type"] == "custom"
        mock_scenarios.assert_not_called()
        mock_plans.assert_called_once()

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_creator_filter_safebreach_only_fetches_scenarios(self, mock_scenarios, mock_categories, mock_plans):
        """creator_filter='safebreach' should skip fetching custom plans."""
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series", 3: "Threat Groups"}

        result = sb_get_scenarios("test-console", creator_filter="safebreach")

        assert result["total_scenarios"] == 2
        assert all(s["source_type"] == "oob" for s in result["scenarios_in_page"])
        mock_plans.assert_not_called()


class TestGetAllPlansFromCacheOrApi:
    """Test _get_all_plans_from_cache_or_api function."""

    @pytest.fixture(autouse=True)
    def set_auth_context(self):
        from safebreach_mcp_core.token_context import _user_auth_artifacts
        token = _user_auth_artifacts.set({"x-apitoken": "test-token"})
        yield
        _user_auth_artifacts.reset(token)

    def setup_method(self):
        clear_plans_cache()

    def teardown_method(self):
        clear_plans_cache()

    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123456')
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_api_call_success_unwraps_data(self, mock_get, mock_base_url, mock_account):
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": 1, "name": "Plan 1"}]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = _get_all_plans_from_cache_or_api("test-console")

        assert len(result) == 1
        assert result[0]["id"] == 1
        # Verify URL contains the plans path with account_id
        call_args = str(mock_get.call_args)
        assert '/api/config/v2/accounts/123456/plans' in call_args

    @patch('safebreach_mcp_config.config_functions.is_caching_enabled', return_value=True)
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_cache_hit_skips_api(self, mock_get, mock_cache_enabled):
        plans_cache.set(f"plans_test-console{get_cache_user_suffix()}", [{"id": 99, "name": "Cached"}])

        result = _get_all_plans_from_cache_or_api("test-console")

        assert result[0]["id"] == 99
        mock_get.assert_not_called()

    @patch('safebreach_mcp_config.config_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_config.config_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_config.config_functions.requests.get')
    def test_api_error_propagates(self, mock_get, mock_base_url, mock_account):
        mock_get.side_effect = Exception("API unreachable")

        with pytest.raises(Exception, match="API unreachable"):
            _get_all_plans_from_cache_or_api("test-console")


class TestSbGetScenarioDetails:
    """Test sb_get_scenario_details function."""

    def setup_method(self):
        clear_scenarios_cache()
        clear_categories_cache()
        clear_plans_cache()

    def teardown_method(self):
        clear_scenarios_cache()
        clear_categories_cache()
        clear_plans_cache()

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_returns_simplified_view(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series", 3: "Threat Groups"}

        result = sb_get_scenario_details("aaa-111-222-333", "test-console")

        assert result["id"] == "aaa-111-222-333"
        assert isinstance(result["id"], str)
        assert result["source_type"] == "oob"
        assert result["name"] == "CISA Alert Akira Ransomware"
        assert "steps" in result
        assert result["category_names"] == ["Known Threats Series"]
        assert result["step_count"] == 1
        assert result["is_ready_to_run"] is False
        assert isinstance(result["tags"], list)
        # Simplified: no raw execution mechanics
        assert "actions" not in result
        assert "edges" not in result
        assert "phases" not in result
        # Steps are simplified
        assert result["steps"][0]["name"] == "Network Infiltration"
        assert "attack_selection" in result["steps"][0]

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api', return_value=[])
    def test_finds_custom_plan_by_integer_id(self, mock_scenarios, mock_categories, mock_plans):
        mock_categories.return_value = {}
        mock_plans.return_value = [
            {"id": 119, "name": "Custom Plan", "steps": [], "userId": 1}
        ]

        result = sb_get_scenario_details("119", "test-console")

        assert result["id"] == "119"
        assert isinstance(result["id"], str)
        assert result["source_type"] == "custom"
        assert result["category_names"] == []
        assert result["steps"] == []

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_not_found_raises_value_error(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series"}

        with pytest.raises(ValueError, match="not found"):
            sb_get_scenario_details("nonexistent-id", "test-console")

    def test_empty_scenario_id_raises_value_error(self):
        with pytest.raises(ValueError, match="scenario_id"):
            sb_get_scenario_details("", "test-console")

    @patch('safebreach_mcp_config.config_functions._get_all_plans_from_cache_or_api', return_value=[])
    @patch('safebreach_mcp_config.config_functions._get_categories_map_from_cache_or_api')
    @patch('safebreach_mcp_config.config_functions._get_all_scenarios_from_cache_or_api')
    def test_has_simplified_step_format(self, mock_scenarios, mock_categories, mock_plans):
        mock_scenarios.return_value = MOCK_SCENARIO_DATA
        mock_categories.return_value = {2: "Known Threats Series"}

        result = sb_get_scenario_details("aaa-111-222-333", "test-console")

        assert result["source_type"] == "oob"
        assert "has_wait_steps" in result
        for step in result["steps"]:
            assert "name" in step
            assert "attack_selection" in step
            assert "target_criteria" in step
            assert "attacker_criteria" in step