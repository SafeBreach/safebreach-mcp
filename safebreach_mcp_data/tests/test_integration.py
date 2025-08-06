"""
Integration Tests for SafeBreach Data Functions

This module provides integration tests for the security control events functionality,
testing complete workflows and complex scenarios.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_data.data_functions import (
    sb_get_security_controls_events,
    sb_get_security_control_event_details,
    sb_get_test_simulations,
    sb_get_simulation_details,
    sb_get_test_drifts,
    security_control_events_cache,
    simulations_cache
)


class TestSecurityControlEventsIntegration:
    """Integration tests for security control events functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Clear caches before each test
        security_control_events_cache.clear()
        simulations_cache.clear()
    
    @pytest.fixture
    def mock_security_control_events_response(self):
        """Mock security control events API response."""
        return {
            "error": 0,
            "result": {
                "siemLogs": [
                    {
                        "id": "event-001",
                        "fields": {
                            "timestamp": "2025-07-17T23:36:55.000Z",
                            "vendor": "CrowdStrike",
                            "product": "CrowdStrike FDR",
                            "action": ["FileDeleteInfo"],
                            "sourceHosts": ["TEST-HOST-1", "172.31.17.101"],
                            "destHosts": [],
                            "status": "log_only",
                            "filePath": ["/path/to/file.exe"],
                            "fileHashes": ["abc123def456"],
                            "processName": ["process.exe"],
                            "processIds": [1234],
                            "sourcePorts": [80],
                            "destPorts": []
                        },
                        "rawLog": "{\"event_simpleName\":\"FileDeleteInfo\"}",
                        "originalFields": {"aid": "acb383cbca774d2c976ec87f6ba4ce0f"},
                        "parser": "CrowdStrike FDR",
                        "connectorName": "Splunk for FDR",
                        "connectorId": "connector-001",
                        "connectorType": "splunkrest",
                        "simulationId": 1048048516,
                        "planRunId": "1752744254468.59",
                        "moveId": 7169,
                        "stepRunId": "1752744254542.63",
                        "correlated": True,
                        "correlatedRules": ["SB Identifier"],
                        "dropRules": []
                    },
                    {
                        "id": "event-002",
                        "fields": {
                            "timestamp": "2025-07-17T23:33:31.000Z",
                            "vendor": "CrowdStrike",
                            "product": "CrowdStrike Falcon",
                            "action": "Prevention, process was blocked from execution.",
                            "sourceHosts": ["172.31.17.101", "TEST-HOST-1"],
                            "destHosts": [],
                            "status": "prevent",
                            "filePath": ["reg.exe"],
                            "fileHashes": ["def789ghi012"],
                            "alertId": "alert-123",
                            "alertName": "Credential Access via OS Credential Dumping",
                            "processName": ["reg.exe"],
                            "processIds": [5678],
                            "sourcePorts": [],
                            "destPorts": []
                        },
                        "rawLog": "{\"metadata\":{\"customerIDString\":\"88ce1bb60b9548acad68231f3ac5077b\"}}",
                        "originalFields": {"aid": "acb383cbca774d2c976ec87f6ba4ce0f"},
                        "parser": "CrowdStrike Falcon",
                        "connectorName": "Splunk for Falcon",
                        "connectorId": "connector-002",
                        "connectorType": "splunkrest",
                        "simulationId": 1048048516,
                        "planRunId": "1752744254468.59",
                        "moveId": 7169,
                        "stepRunId": "1752744254542.63",
                        "correlated": True,
                        "correlatedRules": ["SB Identifier"],
                        "dropRules": []
                    }
                ]
            }
        }
    
    @pytest.fixture
    def mock_simulation_response(self):
        """Mock simulation API response."""
        return [
            {
                "id": "sim-001",
                "planName": "Security Assessment",
                "planRunId": "1752744254468.59",
                "attackerSimulatorStartTime": 1640995200,
                "executionTime": 1640995300,
                "status": "missed",
                "moveId": 7169,
                "moveName": "Credential Dumping",
                "preventedBy": [],
                "reportedBy": [],
                "loggedBy": ["CrowdStrike FDR", "CrowdStrike Falcon"]
            }
        ]
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.post')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_full_workflow_simulation_to_security_events(self, mock_get, mock_post, mock_secret, mock_account_id, mock_base_url, mock_security_control_events_response, mock_simulation_response):
        """Test complete workflow from simulation to security control events."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        
        # Mock simulation API response (for POST requests to executionsHistoryResults)
        simulation_response = Mock()
        simulation_response.json.return_value = {"simulations": [mock_simulation_response[0]]}  # Wrap in simulations array
        simulation_response.status_code = 200
        simulation_response.raise_for_status.return_value = None
        
        # Mock security control events API response (for GET requests to eventLogs)
        security_events_response = Mock()
        security_events_response.json.return_value = mock_security_control_events_response
        security_events_response.status_code = 200
        security_events_response.raise_for_status.return_value = None
        
        # Configure mock_post for simulation details requests
        mock_post.return_value = simulation_response
        
        # Configure mock_get to return different responses based on URL
        def mock_get_side_effect(url, **kwargs):
            if 'eventLogs' in url:
                return security_events_response
            else:
                return Mock()
        
        mock_get.side_effect = mock_get_side_effect
        
        # Step 1: Get simulation details
        simulation_details = sb_get_simulation_details(
            "test-console", 
            "sim-001"
        )
        
        # Step 2: Get security control events for the simulation
        security_events = sb_get_security_controls_events(
            "test-console",
            "1752744254468.59",
            "sim-001"
        )
        
        # Step 3: Get detailed information for a specific security event
        event_details = sb_get_security_control_event_details(
            "test-console",
            "1752744254468.59",
            "sim-001",
            "event-001"
        )
        
        # Assertions
        assert "simulation_id" in simulation_details
        assert security_events["total_events"] == 2
        assert len(security_events["events_in_page"]) == 2
        assert event_details["event_id"] == "event-001"
        assert event_details["vendor"] == "CrowdStrike"
        assert event_details["product"] == "CrowdStrike FDR"
        
        # Verify API calls
        assert mock_post.call_count == 1  # One for simulation details
        assert mock_get.call_count == 1  # One for security events (event details uses cache)
        mock_secret.assert_called_with("test-console")
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_events_filtering_workflow(self, mock_get, mock_secret, mock_account_id, mock_base_url, mock_security_control_events_response):
        """Test filtering workflow for security control events."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = mock_security_control_events_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test 1: Get all events
        all_events = sb_get_security_controls_events("test-console", "test1", "sim1")
        
        # Test 2: Filter by vendor
        crowdstrike_events = sb_get_security_controls_events(
            "test-console", 
            "test1", 
            "sim1",
            vendor_name_filter="CrowdStrike"
        )
        
        # Test 3: Filter by product
        fdr_events = sb_get_security_controls_events(
            "test-console", 
            "test1", 
            "sim1",
            product_name_filter="FDR"
        )
        
        # Test 4: Filter by action
        prevention_events = sb_get_security_controls_events(
            "test-console", 
            "test1", 
            "sim1",
            security_action_filter="Prevention"
        )
        
        # Test 5: Filter by source host
        host_events = sb_get_security_controls_events(
            "test-console", 
            "test1", 
            "sim1",
            source_host_filter="TEST-HOST-1"
        )
        
        # Test 6: Combined filters
        combined_events = sb_get_security_controls_events(
            "test-console", 
            "test1", 
            "sim1",
            vendor_name_filter="CrowdStrike",
            product_name_filter="Falcon",
            security_action_filter="Prevention"
        )
        
        # Assertions
        assert all_events["total_events"] == 2
        assert crowdstrike_events["total_events"] == 2
        assert fdr_events["total_events"] == 1
        assert prevention_events["total_events"] == 1
        assert host_events["total_events"] == 2
        assert combined_events["total_events"] == 1
        
        # Verify filters were applied
        assert crowdstrike_events["applied_filters"]["vendor_name_filter"] == "CrowdStrike"
        assert fdr_events["applied_filters"]["product_name_filter"] == "FDR"
        assert prevention_events["applied_filters"]["security_action_filter"] == "Prevention"
        assert host_events["applied_filters"]["source_host_filter"] == "TEST-HOST-1"
        assert combined_events["applied_filters"]["vendor_name_filter"] == "CrowdStrike"
        assert combined_events["applied_filters"]["product_name_filter"] == "Falcon"
        assert combined_events["applied_filters"]["security_action_filter"] == "Prevention"
        
        # Should only call API once due to caching
        assert mock_get.call_count == 1
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_event_details_verbosity_levels(self, mock_get, mock_secret, mock_account_id, mock_base_url, mock_security_control_events_response):
        """Test different verbosity levels for security control event details."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = mock_security_control_events_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test different verbosity levels
        minimal_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001", verbosity_level="minimal"
        )
        
        standard_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001", verbosity_level="standard"
        )
        
        detailed_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001", verbosity_level="detailed"
        )
        
        full_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001", verbosity_level="full"
        )
        
        # Assertions
        # Minimal should have fewer fields than standard
        assert len(minimal_details) < len(standard_details)
        
        # Standard should have basic fields
        assert "event_id" in standard_details
        assert "vendor" in standard_details
        assert "product" in standard_details
        assert "action" in standard_details
        
        # Detailed should have more fields than standard
        assert len(detailed_details) > len(standard_details)
        assert "file_path" in detailed_details
        assert "raw_log_preview" in detailed_details
        
        # Full should have all fields including raw log
        assert len(full_details) >= len(detailed_details)
        assert "raw_log" in full_details
        assert "original_fields" in full_details
        
        # All should have metadata
        assert "_metadata" in minimal_details
        assert "_metadata" in standard_details
        assert "_metadata" in detailed_details
        assert "_metadata" in full_details
        
        # Verify verbosity levels in metadata
        assert minimal_details["_metadata"]["verbosity_level"] == "minimal"
        assert standard_details["_metadata"]["verbosity_level"] == "standard"
        assert detailed_details["_metadata"]["verbosity_level"] == "detailed"
        assert full_details["_metadata"]["verbosity_level"] == "full"
        
        # Should only call API once due to caching
        assert mock_get.call_count == 1
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_events_pagination_workflow(self, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test pagination workflow for security control events."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        
        # Create large dataset (25 events)
        large_dataset = []
        for i in range(25):
            event = {
                "id": f"event-{i:03d}",
                "fields": {
                    "timestamp": "2025-07-17T23:36:55.000Z",
                    "vendor": "TestVendor",
                    "product": f"TestProduct-{i % 3}",  # Vary products for filtering
                    "action": ["TestAction"],
                    "sourceHosts": [f"TestHost-{i % 2}"],  # Vary hosts for filtering
                    "destHosts": [],
                    "status": "test"
                },
                "connectorName": f"TestConnector-{i % 2}",
                "simulationId": 12345,
                "planRunId": "test1",
                "moveId": i
            }
            large_dataset.append(event)
        
        large_response = {
            "error": 0,
            "result": {
                "siemLogs": large_dataset
            }
        }
        
        mock_response = Mock()
        mock_response.json.return_value = large_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Test pagination
        page_0 = sb_get_security_controls_events("test-console", "test1", "sim1", page_number=0)
        page_1 = sb_get_security_controls_events("test-console", "test1", "sim1", page_number=1)
        page_2 = sb_get_security_controls_events("test-console", "test1", "sim1", page_number=2)
        
        # Test pagination with filter
        filtered_page_0 = sb_get_security_controls_events(
            "test-console", "test1", "sim1", 
            page_number=0,
            product_name_filter="TestProduct-0"
        )
        
        # Assertions
        assert page_0["page_number"] == 0
        assert page_0["total_events"] == 25
        assert page_0["total_pages"] == 3  # 25 / 10 = 2.5, ceil = 3
        assert len(page_0["events_in_page"]) == 10
        
        assert page_1["page_number"] == 1
        assert len(page_1["events_in_page"]) == 10
        
        assert page_2["page_number"] == 2
        assert len(page_2["events_in_page"]) == 5  # Last page has remainder
        
        # Filtered results should be smaller
        assert filtered_page_0["total_events"] < 25
        assert filtered_page_0["applied_filters"]["product_name_filter"] == "TestProduct-0"
        
        # Should only call API once due to caching
        assert mock_get.call_count == 1
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_events_cache_behavior(self, mock_get, mock_secret, mock_account_id, mock_base_url, mock_security_control_events_response):
        """Test cache behavior for security control events."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        mock_response = Mock()
        mock_response.json.return_value = mock_security_control_events_response
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # First call - should hit API
        result1 = sb_get_security_controls_events("test-console", "test1", "sim1")
        
        # Second call - should use cache
        result2 = sb_get_security_controls_events("test-console", "test1", "sim1")
        
        # Get event details - should use same cache
        event_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001"
        )
        
        # Different simulation - should hit API again
        result3 = sb_get_security_controls_events("test-console", "test1", "sim2")
        
        # Assertions
        assert result1["total_events"] == 2
        assert result2["total_events"] == 2
        assert result1 == result2  # Should be identical due to cache
        assert event_details["event_id"] == "event-001"
        assert result3["total_events"] == 2  # Would be different if real API
        
        # Should call API twice (once for sim1, once for sim2)
        assert mock_get.call_count == 2
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_events_error_handling_workflow(self, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test error handling in security control events workflow."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        
        # Test API error
        mock_get.side_effect = Exception("API connection failed")
        
        # Test getting events with error - should now raise exception
        with pytest.raises(Exception) as exc_info:
            sb_get_security_controls_events("test-console", "test1", "sim1")
        assert "API connection failed" in str(exc_info.value)
        
        # Test getting event details with error - should also raise exception
        with pytest.raises(Exception) as exc_info:
            sb_get_security_control_event_details(
                "test-console", "test1", "sim1", "event-001"
            )
        assert "API connection failed" in str(exc_info.value)
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    def test_security_control_events_empty_response_handling(self, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test handling of empty security control events response."""
        # Setup mocks
        mock_secret.return_value = "test-token"
        
        # Mock empty response
        empty_response = Mock()
        empty_response.json.return_value = {"error": 0, "result": {"siemLogs": []}}
        empty_response.raise_for_status.return_value = None
        mock_get.return_value = empty_response
        
        # Test getting events with empty response
        result = sb_get_security_controls_events("test-console", "test1", "sim1")
        
        # Test getting event details with empty response
        event_details = sb_get_security_control_event_details(
            "test-console", "test1", "sim1", "event-001"
        )
        
        # Assertions
        assert result["total_events"] == 0
        assert len(result["events_in_page"]) == 0
        assert result["total_pages"] == 0
        assert result["applied_filters"] == {}
        
        assert "error" in event_details
        assert "not found" in event_details["error"]
        assert event_details["event_id"] == "event-001"


class TestFindingsIntegration:
    """Integration tests for findings functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Clear caches before each test
        from safebreach_mcp_data.data_functions import findings_cache
        findings_cache.clear()
    
    @pytest.fixture
    def mock_findings_response(self):
        """Mock findings API response with diverse data."""
        return {
            "findings": [
                {
                    "planRunId": "1752050602228.12",
                    "timestamp": "2025-07-09T08:45:56.943Z",
                    "type": "openPorts",
                    "source": "RTI3HY8F",
                    "severity": 2,
                    "attributes": {
                        "ports": [135, 139, 445, 3389, 5985, 5986],
                        "hostname": "RTI3HY8F",
                        "internalIp": "200.200.200.200"
                    }
                },
                {
                    "planRunId": "1752050602228.12", 
                    "timestamp": "2025-07-09T08:50:07.023Z",
                    "type": "CredentialHarvestingMemory",
                    "source": "RC-A-W11-XDR01",
                    "severity": 4,
                    "attributes": {
                        "hostname": "RC-A-W11-XDR01",
                        "password": "$PAM:TEST_VAULT:secret/test/credentials/ef1c2582-5ac7-4385-97f7-7e646d54319b",
                        "obfuscatedPassword": "doI*******"
                    }
                },
                {
                    "planRunId": "1752050602228.12",
                    "timestamp": "2025-07-09T08:50:00.271Z",
                    "type": "UsersCollection",
                    "source": "Local (rc-a-w11-xdr01)",
                    "severity": 3,
                    "attributes": {
                        "hostname": "rc-a-w11-xdr01",
                        "username": "Administrator"
                    }
                },
                {
                    "planRunId": "1752050602228.12",
                    "timestamp": "2025-07-09T08:45:56.955Z",
                    "type": "ConnectedAgents",
                    "source": "6J2JFZ4H",
                    "severity": 5,
                    "attributes": {
                        "nodeId": "909930e6-7997-4ca6-9a0d-7dccb539a752",
                        "hostname": "6J2JFZ4H"
                    }
                },
                {
                    "planRunId": "1752050602228.12",
                    "timestamp": "2025-07-09T08:50:07.219Z",
                    "type": "CredentialHarvestingMemory",
                    "source": "RC-A-W11-XDR01",
                    "severity": 4,
                    "attributes": {
                        "hostname": "RC-A-W11-XDR01",
                        "password": "$PAM:TEST_VAULT:secret/test/credentials/86b79c2f-2a50-4001-a12b-ba24ce2ff577",
                        "obfuscatedPassword": "doI*******"
                    }
                }
            ]
        }
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_full_workflow_findings_retrieval(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url, mock_findings_response):
        """Test complete workflow from findings counts to details."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        
        mock_response = Mock()
        mock_response.json.return_value = mock_findings_response
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_counts, sb_get_test_findings_details
        
        # Step 1: Get findings counts
        counts_result = sb_get_test_findings_counts("test-console", "1752050602228.12")
        
        # Verify that the correct API endpoint was called
        expected_url = "https://test.com/api/data/v1/propagateSummary/1752050602228.12/findings/"
        mock_requests.get.assert_called_with(
            expected_url,
            headers={"Content-Type": "application/json", "x-apitoken": "test-api-token"},
            timeout=120
        )
        
        # Verify counts result
        assert counts_result["console"] == "test-console"
        assert counts_result["test_id"] == "1752050602228.12"
        assert counts_result["total_findings"] == 5
        assert counts_result["total_types"] == 4
        
        # Check specific counts
        findings_counts = {fc["type"]: fc["count"] for fc in counts_result["findings_counts"]}
        assert findings_counts["CredentialHarvestingMemory"] == 2
        assert findings_counts["openPorts"] == 1
        assert findings_counts["UsersCollection"] == 1
        assert findings_counts["ConnectedAgents"] == 1
        
        # Step 2: Get findings details
        details_result = sb_get_test_findings_details("test-console", "1752050602228.12")
        
        # Verify details result
        assert details_result["console"] == "test-console"
        assert details_result["test_id"] == "1752050602228.12"
        assert details_result["total_findings"] == 5
        assert details_result["total_pages"] == 1
        assert len(details_result["findings_in_page"]) == 5
        
        # Check that findings are sorted by timestamp (newest first)
        timestamps = [f["timestamp"] for f in details_result["findings_in_page"]]
        assert timestamps == sorted(timestamps, reverse=True)
        
        # Step 3: Filter by specific type
        filtered_counts = sb_get_test_findings_counts(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="CredentialHarvestingMemory"
        )
        
        assert filtered_counts["total_findings"] == 2
        assert filtered_counts["total_types"] == 1
        assert filtered_counts["applied_filters"]["attribute_filter"] == "CredentialHarvestingMemory"
        
        # Verify API was called only once due to caching
        assert mock_requests.get.call_count == 1
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_filtering_workflow(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url, mock_findings_response):
        """Test comprehensive filtering scenarios."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        
        mock_response = Mock()
        mock_response.json.return_value = mock_findings_response
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_details
        
        # Test filtering by hostname
        hostname_filtered = sb_get_test_findings_details(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="RTI3HY8F"
        )
        
        assert hostname_filtered["total_findings"] == 1
        assert hostname_filtered["findings_in_page"][0]["type"] == "openPorts"
        assert hostname_filtered["applied_filters"]["attribute_filter"] == "RTI3HY8F"
        
        # Test filtering by IP address
        ip_filtered = sb_get_test_findings_details(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="200.200.200.200"
        )
        
        assert ip_filtered["total_findings"] == 1
        assert ip_filtered["findings_in_page"][0]["attributes"]["internalIp"] == "200.200.200.200"
        
        # Test filtering by severity (will match findings with severity 4 and other places with "4")
        severity_filtered = sb_get_test_findings_details(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="4"
        )
        
        # Should find at least 2 (the credential harvesting findings with severity 4)
        assert severity_filtered["total_findings"] >= 2
        
        # Test filtering by port number
        port_filtered = sb_get_test_findings_details(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="3389"
        )
        
        assert port_filtered["total_findings"] == 1
        assert 3389 in port_filtered["findings_in_page"][0]["attributes"]["ports"]
        
        # Test case insensitive filtering
        case_filtered = sb_get_test_findings_details(
            "test-console", 
            "1752050602228.12", 
            attribute_filter="CREDENTIAL"
        )
        
        assert case_filtered["total_findings"] == 2
        assert all("Credential" in f["type"] for f in case_filtered["findings_in_page"])
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_pagination_workflow(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url):
        """Test findings pagination with large dataset."""
        # Setup mocks for large dataset
        mock_get_secret.return_value = "test-api-token"
        
        # Create 25 findings to test pagination (PAGE_SIZE = 10)
        large_findings = []
        for i in range(25):
            large_findings.append({
                "planRunId": "test",
                "timestamp": f"2025-07-09T08:45:{i:02d}.000Z",
                "type": f"TestType{i}",
                "source": f"TestSource{i}",
                "severity": (i % 5) + 1,
                "attributes": {
                    "hostname": f"host-{i}",
                    "testId": i
                }
            })
        
        mock_response = Mock()
        mock_response.json.return_value = {"findings": large_findings}
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_details
        
        # Test first page
        page_0 = sb_get_test_findings_details("test-console", "test-id", page_number=0)
        assert page_0["page_number"] == 0
        assert page_0["total_pages"] == 3
        assert page_0["total_findings"] == 25
        assert len(page_0["findings_in_page"]) == 10
        assert "hint_to_agent" in page_0
        
        # Test middle page
        page_1 = sb_get_test_findings_details("test-console", "test-id", page_number=1)
        assert page_1["page_number"] == 1
        assert len(page_1["findings_in_page"]) == 10
        assert "hint_to_agent" in page_1
        
        # Test last page
        page_2 = sb_get_test_findings_details("test-console", "test-id", page_number=2)
        assert page_2["page_number"] == 2
        assert len(page_2["findings_in_page"]) == 5  # Remaining findings
        assert "hint_to_agent" not in page_2  # No next page
        
        # Test pagination with filtering
        filtered_page = sb_get_test_findings_details(
            "test-console", 
            "test-id", 
            page_number=0,
            attribute_filter="TestType1"  # Should match TestType1, TestType10-19
        )
        
        assert filtered_page["total_findings"] == 11  # TestType1, TestType10-19
        assert filtered_page["total_pages"] == 2
        assert len(filtered_page["findings_in_page"]) == 10
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_cache_behavior(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url, mock_findings_response):
        """Test findings cache behavior across multiple calls."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        
        mock_response = Mock()
        mock_response.json.return_value = mock_findings_response
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_counts, sb_get_test_findings_details
        
        # Multiple calls should use cache
        counts1 = sb_get_test_findings_counts("test-console", "test-id")
        details1 = sb_get_test_findings_details("test-console", "test-id")
        counts2 = sb_get_test_findings_counts("test-console", "test-id", attribute_filter="openPorts")
        details2 = sb_get_test_findings_details("test-console", "test-id", attribute_filter="credential")
        
        # API should only be called once
        assert mock_requests.get.call_count == 1
        
        # Results should be consistent
        assert counts1["total_findings"] == 5
        assert details1["total_findings"] == 5
        assert counts2["total_findings"] == 1
        assert details2["total_findings"] == 2
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_error_handling_workflow(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url):
        """Test error handling in findings workflow."""
        # Setup mocks for API error
        mock_get_secret.return_value = "test-api-token"
        mock_requests.get.side_effect = Exception("API Connection Failed")
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_counts, sb_get_test_findings_details
        
        # Test error handling in counts - should now raise exception
        with pytest.raises(Exception) as exc_info:
            sb_get_test_findings_counts("test-console", "test-id")
        assert "API Connection Failed" in str(exc_info.value)
        
        # Test error handling in details - should now raise exception
        with pytest.raises(Exception) as exc_info:
            sb_get_test_findings_details("test-console", "test-id")
        assert "API Connection Failed" in str(exc_info.value)
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_empty_response_handling(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url):
        """Test handling of empty findings response."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        
        empty_response = Mock()
        empty_response.json.return_value = {"findings": []}
        empty_response.raise_for_status.return_value = None
        mock_requests.get.return_value = empty_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_counts, sb_get_test_findings_details
        
        # Test empty response in counts
        counts_result = sb_get_test_findings_counts("test-console", "test-id")
        assert counts_result["total_findings"] == 0
        assert counts_result["total_types"] == 0
        assert len(counts_result["findings_counts"]) == 0
        assert counts_result["applied_filters"] == {}
        
        # Test empty response in details
        details_result = sb_get_test_findings_details("test-console", "test-id")
        assert details_result["total_findings"] == 0
        assert details_result["total_pages"] == 0
        assert len(details_result["findings_in_page"]) == 0
        assert details_result["applied_filters"] == {}
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://test.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='123')
    @patch('safebreach_mcp_data.data_functions.requests')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    def test_findings_comprehensive_attributes_search(self, mock_get_secret, mock_requests, mock_account_id, mock_base_url, mock_findings_response):
        """Test comprehensive attribute search across all finding fields."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        
        mock_response = Mock()
        mock_response.json.return_value = mock_findings_response
        mock_response.raise_for_status.return_value = None
        mock_requests.get.return_value = mock_response
        
        from safebreach_mcp_data.data_functions import sb_get_test_findings_details
        
        test_cases = [
            # Search by type
            ("openPorts", 1),
            # Search by source
            ("6J2JFZ4H", 1),
            # Search by hostname in attributes
            ("RTI3HY8F", 1),
            # Search by IP in attributes
            ("200.200.200.200", 1),
            # Search by username in attributes
            ("Administrator", 1),
            # Search by nodeId in attributes
            ("909930e6-7997-4ca6-9a0d-7dccb539a752", 1),
            # Search by partial password (obfuscated)
            ("doI", 2),
            # Case insensitive search (matches CredentialHarvestingMemory type)
            ("CREDENTIAL", 2),
            # Partial search
            ("RC-A", 3),
            # Port number search in array
            ("445", 1),
            # Non-existent search
            ("nonexistent", 0)
        ]
        
        for search_term, expected_count in test_cases:
            result = sb_get_test_findings_details(
                "test-console", 
                "1752050602228.12", 
                attribute_filter=search_term
            )
            
            assert result["total_findings"] == expected_count, f"Failed for search term: {search_term}"
            if expected_count > 0:
                assert result["applied_filters"]["attribute_filter"] == search_term
                assert len(result["findings_in_page"]) == expected_count
    
    def test_findings_real_world_data_handling(self):
        """Test findings with real-world data issues like None timestamps."""
        # Create realistic findings data that includes common API issues
        realistic_findings = [
            {
                "planRunId": "test-123",
                "timestamp": "2025-07-10T12:00:00.000Z",
                "type": "openPorts", 
                "source": "host1",
                "severity": 2,
                "attributes": {"hostname": "host1", "ports": [80, 443]}
            },
            {
                "planRunId": "test-123",
                "timestamp": None,  # Real API sometimes returns None timestamps
                "type": "credentials",
                "source": "host2", 
                "severity": 4,
                "attributes": {"hostname": "host2", "username": "admin"}
            },
            {
                "planRunId": "test-123",
                # Missing timestamp field entirely (another real scenario)
                "type": "services",
                "source": "host3",
                "severity": 3,
                "attributes": {"hostname": "host3", "service": "ssh"}
            }
        ]
        
        # Test that our functions can handle this data without crashing
        from safebreach_mcp_data.data_functions import _apply_findings_filters
        
        # Test filtering - should not crash on None/missing timestamps
        filtered = _apply_findings_filters(realistic_findings, "host2")
        assert len(filtered) == 1
        assert filtered[0]["source"] == "host2"
        
        # The timestamp sorting is tested in the unit tests
        # This integration test focuses on overall data compatibility


class TestDriftAnalysisIntegration:
    """Integration tests for drift analysis functionality."""
    
    def setup_method(self):
        """Setup for each test method."""
        # Clear caches before each test
        from safebreach_mcp_data.data_functions import tests_cache
        security_control_events_cache.clear()
        simulations_cache.clear()
        tests_cache.clear()
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://integration-console.safebreach.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='1234567890')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    @patch('safebreach_mcp_data.data_functions.requests.post')
    def test_drift_analysis_complete_workflow(self, mock_post, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test complete drift analysis workflow with realistic data."""
        # Mock secret retrieval
        mock_secret.return_value = "test-api-token"
        
        # Mock test details API call (for current test)
        current_test_response = Mock()
        current_test_response.json.return_value = {
            "planRunId": "test-current-123",
            "planName": "Weekly Security Assessment",
            "startTime": 1640998800000,  # API returns milliseconds
            "endTime": 1641003600000,
            "status": "completed"
        }
        current_test_response.raise_for_status.return_value = None
        
        # Mock tests history API call (to find baseline test)
        history_response = Mock()
        history_response.json.return_value = {
            "error": 0,
            "result": {
                "testsInPage": [
                    {
                        "planRunId": "test-baseline-456",
                        "planName": "Weekly Security Assessment",
                        "startTime": 1640908800,  # Start time in seconds
                        "endTime": 1640912400,    # End time in seconds
                        "status": "completed"
                    }
                ],
                "totalTests": 1
            }
        }
        history_response.raise_for_status.return_value = None
        
        # Mock simulations API calls (baseline simulations)
        # The _get_all_simulations_from_cache_or_api function expects response_data.get("simulations", [])
        baseline_simulations_response = Mock()
        baseline_simulations_response.json.return_value = {
            "simulations": [
                {
                    "id": "sim-baseline-001",
                    "finalStatus": "missed",
                    "originalExecutionId": "track-001",
                    "moveId": "attack-001",
                    "executionTime": 1640909000
                },
                {
                    "id": "sim-baseline-002", 
                    "finalStatus": "prevented",
                    "originalExecutionId": "track-002",
                    "moveId": "attack-002",
                    "executionTime": 1640909100
                },
                {
                    "id": "sim-baseline-003",
                    "finalStatus": "logged",
                    "originalExecutionId": "track-003",
                    "moveId": "attack-003",
                    "executionTime": 1640909200
                }
            ]
        }
        baseline_simulations_response.raise_for_status.return_value = None
        
        # Mock simulations API calls (current simulations)
        current_simulations_response = Mock()
        current_simulations_response.json.return_value = {
            "simulations": [
                {
                    "id": "sim-current-001",
                    "finalStatus": "logged",  # Changed from missed -> positive drift
                    "originalExecutionId": "track-001",
                    "moveId": "attack-001",
                    "executionTime": 1640999000
                },
                {
                    "id": "sim-current-002",
                    "finalStatus": "prevented",  # Same status -> no drift
                    "originalExecutionId": "track-002",
                    "moveId": "attack-002",
                    "executionTime": 1640999100
                },
                {
                    "id": "sim-current-004",
                    "finalStatus": "stopped",  # New simulation -> exclusive to current
                    "originalExecutionId": "track-004",
                    "moveId": "attack-004",
                    "executionTime": 1640999300
                }
                # track-003 missing -> exclusive to baseline
            ]
        }
        current_simulations_response.raise_for_status.return_value = None
        
        # Configure mock responses based on URL
        def mock_response_selector(*args, **kwargs):
            url = args[0]
            if 'testsummaries' in url and 'test-current-123' in url:
                return current_test_response
            elif 'testsummaries' in url:  # for tests history call
                # Return raw array for tests history API
                tests_list_response = Mock()
                tests_list_response.json.return_value = [
                    {
                        "planRunId": "test-baseline-456",
                        "planName": "Weekly Security Assessment",
                        "startTime": 1640908800000,  # API returns milliseconds
                        "endTime": 1640912400000,
                        "status": "completed"
                    }
                ]
                tests_list_response.raise_for_status.return_value = None
                return tests_list_response
            return Mock()
        
        def mock_post_response_selector(*args, **kwargs):
            request_data = kwargs.get('json', {})
            run_id = request_data.get('runId', '')
            if run_id == 'test-baseline-456':
                return baseline_simulations_response
            elif run_id == 'test-current-123':
                return current_simulations_response
            # Fallback check with string matching if runId not found
            if 'test-baseline-456' in str(request_data):
                return baseline_simulations_response
            elif 'test-current-123' in str(request_data):
                return current_simulations_response
            return Mock()
        
        mock_get.side_effect = mock_response_selector
        mock_post.side_effect = mock_post_response_selector
        
        # Execute drift analysis
        result = sb_get_test_drifts('integration-console', 'test-current-123')
        
        # Verify comprehensive results
        assert isinstance(result, dict)
        assert 'total_drifts' in result
        assert result['total_drifts'] == 3  # 1 status drift + 1 exclusive baseline + 1 exclusive current
        
        # Verify exclusive simulations (now in metadata)
        metadata = result['_metadata'] 
        assert len(metadata['simulations_exclusive_to_baseline']) == 1  # sim-baseline-003 only in baseline
        assert len(metadata['simulations_exclusive_to_current']) == 1   # sim-current-004 only in current
        
        # Verify status drifts (now grouped by drift type)
        assert 'drifts' in result
        assert len(result['drifts']) == 1
        assert 'missed-logged' in result['drifts']
        
        drift_group = result['drifts']['missed-logged']
        assert drift_group['drift_type'] == 'missed-logged'
        assert drift_group['security_impact'] == 'positive'
        assert len(drift_group['drifted_simulations']) == 1
        
        drifted_sim = drift_group['drifted_simulations'][0]
        assert drifted_sim['drift_tracking_code'] == 'track-001'
        assert drifted_sim['former_simulation_id'] == 'sim-baseline-001'
        assert drifted_sim['current_simulation_id'] == 'sim-current-001'
        
        # Verify metadata completeness
        metadata = result['_metadata']
        assert metadata['console'] == 'integration-console'
        assert metadata['test_name'] == 'Weekly Security Assessment'
        assert metadata['baseline_simulations_count'] == 3
        assert metadata['current_simulations_count'] == 3
        assert 'analyzed_at' in metadata
        
        # Verify API calls were made correctly
        assert mock_get.call_count >= 2  # test details + tests history
        assert mock_post.call_count >= 2  # baseline + current simulations
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://cache-console.safebreach.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='1234567890')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console')
    @patch('safebreach_mcp_data.data_functions.requests.get')
    @patch('safebreach_mcp_data.data_functions.requests.post')
    def test_drift_analysis_caching_behavior(self, mock_post, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test that drift analysis properly utilizes caching."""
        # Mock secret retrieval
        mock_secret.return_value = "test-api-token"
        
        # Mock test details
        test_details_response = Mock()
        test_details_response.json.return_value = {
            "planRunId": "test-cache-123",
            "planName": "Cache Test",
            "startTime": 1640998800000,
            "endTime": 1641003600000,
            "status": "completed"
        }
        test_details_response.raise_for_status.return_value = None
        
        # Mock tests history
        history_response = Mock()
        history_response.json.return_value = {
            "error": 0,
            "result": {
                "testsInPage": [
                    {
                        "planRunId": "test-baseline-cache-456",
                        "planName": "Cache Test",
                        "endTime": 1640912400,
                        "status": "completed"
                    }
                ],
                "totalTests": 1
            }
        }
        history_response.raise_for_status.return_value = None
        
        # Mock simulations (minimal for caching test) - fix response format
        simulations_response = Mock()
        simulations_response.json.return_value = {
            "simulations": [
                {
                    "id": "sim-001",
                    "finalStatus": "prevented",
                    "originalExecutionId": "track-001"
                }
            ]
        }
        simulations_response.raise_for_status.return_value = None
        
        # Fix tests history mock response format
        def mock_get_response_selector(*args, **kwargs):
            url = args[0]
            if 'testsummaries' in url and 'test-cache-123' in url:
                return test_details_response
            elif 'testsummaries' in url:  # for tests history call
                # Return raw array for tests history API
                tests_list_response = Mock()
                tests_list_response.json.return_value = [
                    {
                        "planRunId": "test-baseline-cache-456",
                        "planName": "Cache Test",
                        "startTime": 1640908800000,
                        "endTime": 1640912400000,
                        "status": "completed"
                    }
                ]
                tests_list_response.raise_for_status.return_value = None
                return tests_list_response
            return Mock()
        
        mock_get.side_effect = mock_get_response_selector
        mock_post.return_value = simulations_response
        
        # First call - should hit API
        result1 = sb_get_test_drifts('cache-console', 'test-cache-123')
        initial_post_calls = mock_post.call_count
        
        # Second call immediately - should use cache for simulations
        result2 = sb_get_test_drifts('cache-console', 'test-cache-123')
        
        # Verify results are identical (excluding timestamp which will differ)
        result1_copy = result1.copy()
        result2_copy = result2.copy()
        result1_copy['_metadata'] = {k: v for k, v in result1_copy['_metadata'].items() if k != 'analyzed_at'}
        result2_copy['_metadata'] = {k: v for k, v in result2_copy['_metadata'].items() if k != 'analyzed_at'}
        assert result1_copy == result2_copy
        
        # Verify simulations were cached (no additional POST calls for simulations)
        assert mock_post.call_count == initial_post_calls
        
        # Test details and history might be called again as they're not heavily cached
        # but simulations should be cached
    
    @patch('safebreach_mcp_data.data_functions.get_api_base_url', return_value='https://error-console.safebreach.com')
    @patch('safebreach_mcp_data.data_functions.get_api_account_id', return_value='1234567890')
    @patch('safebreach_mcp_data.data_functions.get_secret_for_console') 
    @patch('safebreach_mcp_data.data_functions.requests.get')
    @patch('safebreach_mcp_data.data_functions.requests.post')
    def test_drift_analysis_error_handling_integration(self, mock_post, mock_get, mock_secret, mock_account_id, mock_base_url):
        """Test drift analysis error handling in realistic scenarios."""
        # Mock secret retrieval
        mock_secret.return_value = "test-api-token"
        
        # Test API error during simulations retrieval
        test_details_response = Mock()
        test_details_response.json.return_value = {
            "planRunId": "test-error-123",
            "planName": "Error Test",
            "startTime": 1640998800000,
            "status": "completed"
        }
        test_details_response.raise_for_status.return_value = None
        
        # Fix tests history mock response format
        def mock_get_error_response_selector(*args, **kwargs):
            url = args[0]
            if 'testsummaries' in url and 'test-error-123' in url:
                return test_details_response
            elif 'testsummaries' in url:  # for tests history call
                # Return raw array for tests history API
                tests_list_response = Mock()
                tests_list_response.json.return_value = [
                    {
                        "planRunId": "test-baseline-error-456", 
                        "planName": "Error Test", 
                        "startTime": 1640908800000,
                        "endTime": 1640912400000,
                        "status": "completed"
                    }
                ]
                tests_list_response.raise_for_status.return_value = None
                return tests_list_response
            return Mock()
        
        # Simulate API error for simulations
        simulations_error_response = Mock()
        simulations_error_response.raise_for_status.side_effect = Exception("Simulations API timeout")
        
        mock_get.side_effect = mock_get_error_response_selector
        mock_post.return_value = simulations_error_response
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Simulations API timeout"):
            sb_get_test_drifts('error-console', 'test-error-123')