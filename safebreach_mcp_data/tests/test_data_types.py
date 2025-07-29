"""
Tests for SafeBreach Data Types

This module tests the data type mappings and transformations for security control events.
"""

import pytest
from safebreach_mcp_data.data_types import (
    get_nested_value,
    map_security_control_event,
    get_reduced_security_control_events_mapping,
    get_full_security_control_events_mapping,
    reduced_security_control_events_mapping,
    full_security_control_events_mapping
)


class TestDataTypes:
    """Test suite for data type mappings and transformations."""
    
    @pytest.fixture
    def mock_security_control_event(self):
        """Mock security control event data for testing."""
        return {
            "id": "8207d61e-d14b-5e1d-adcb-8ea461249001",
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
                "processIds": [1234, 5678],
                "sourcePorts": [80, 443],
                "destPorts": [8080],
                "alertId": "alert-123",
                "alertName": "Test Alert"
            },
            "rawLog": "{\"event_simpleName\":\"FileDeleteInfo\"}",
            "originalFields": {"aid": "acb383cbca774d2c976ec87f6ba4ce0f"},
            "parser": "CrowdStrike FDR",
            "connectorName": "Splunk for FDR",
            "connectorId": "t_LI23N26uTHxm_TVlZK3",
            "connectorType": "splunkrest",
            "simulationId": 1048048516,
            "planRunId": "1752744254468.59",
            "moveId": 7169,
            "stepRunId": "1752744254542.63",
            "correlated": True,
            "correlatedRules": ["SB Identifier"],
            "dropRules": []
        }
    
    def test_get_nested_value_success(self):
        """Test successful nested value retrieval."""
        data = {
            "level1": {
                "level2": {
                    "level3": "target_value"
                }
            }
        }
        
        result = get_nested_value(data, "level1.level2.level3")
        assert result == "target_value"
    
    def test_get_nested_value_missing_key(self):
        """Test nested value retrieval with missing key."""
        data = {
            "level1": {
                "level2": {
                    "level3": "target_value"
                }
            }
        }
        
        result = get_nested_value(data, "level1.level2.missing", default="default_value")
        assert result == "default_value"
    
    def test_get_nested_value_missing_intermediate_key(self):
        """Test nested value retrieval with missing intermediate key."""
        data = {
            "level1": {
                "level2": {
                    "level3": "target_value"
                }
            }
        }
        
        result = get_nested_value(data, "level1.missing.level3", default="default_value")
        assert result == "default_value"
    
    def test_get_nested_value_none_data(self):
        """Test nested value retrieval with None data."""
        result = get_nested_value(None, "level1.level2", default="default_value")
        assert result == "default_value"
    
    def test_get_nested_value_empty_path(self):
        """Test nested value retrieval with empty path."""
        data = {"key": "value"}
        result = get_nested_value(data, "", default="default_value")
        assert result == "default_value"
    
    def test_map_security_control_event_basic(self, mock_security_control_event):
        """Test basic security control event mapping."""
        mapping = {
            "event_id": "id",
            "vendor": "fields.vendor",
            "product": "fields.product"
        }
        
        result = map_security_control_event(mock_security_control_event, mapping)
        
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
    
    def test_map_security_control_event_missing_fields(self, mock_security_control_event):
        """Test security control event mapping with missing fields."""
        mapping = {
            "event_id": "id",
            "missing_field": "nonexistent.field",
            "vendor": "fields.vendor"
        }
        
        result = map_security_control_event(mock_security_control_event, mapping)
        
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert "missing_field" not in result
    
    def test_map_security_control_event_direct_and_nested(self, mock_security_control_event):
        """Test security control event mapping with both direct and nested fields."""
        mapping = {
            "event_id": "id",  # Direct field
            "vendor": "fields.vendor",  # Nested field
            "parser": "parser"  # Direct field
        }
        
        result = map_security_control_event(mock_security_control_event, mapping)
        
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["parser"] == "CrowdStrike FDR"
    
    def test_get_reduced_security_control_events_mapping(self, mock_security_control_event):
        """Test reduced security control events mapping."""
        result = get_reduced_security_control_events_mapping(mock_security_control_event)
        
        # Check that all expected fields are present
        assert "event_id" in result
        assert "timestamp" in result
        assert "vendor" in result
        assert "product" in result
        assert "action" in result
        assert "source_hosts" in result
        assert "destination_hosts" in result
        assert "status" in result
        assert "connector_name" in result
        assert "simulation_id" in result
        assert "test_id" in result
        assert "move_id" in result
        
        # Check values
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
        assert result["action"] == ["FileDeleteInfo"]
        assert result["source_hosts"] == ["TEST-HOST-1", "172.31.17.101"]
        assert result["destination_hosts"] == []
        assert result["status"] == "log_only"
        assert result["connector_name"] == "Splunk for FDR"
        assert result["simulation_id"] == 1048048516
        assert result["test_id"] == "1752744254468.59"
        assert result["move_id"] == 7169
    
    def test_get_full_security_control_events_mapping_minimal(self, mock_security_control_event):
        """Test full security control events mapping with minimal verbosity."""
        result = get_full_security_control_events_mapping(mock_security_control_event, "minimal")
        
        # Should only have essential fields
        expected_fields = ["event_id", "timestamp", "vendor", "product", "action", "status", "simulation_id", "test_id"]
        
        for field in expected_fields:
            assert field in result
        
        # Should not have detailed fields
        assert "file_path" not in result
        assert "raw_log" not in result
        assert "original_fields" not in result
        
        # Check values
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
    
    def test_get_full_security_control_events_mapping_standard(self, mock_security_control_event):
        """Test full security control events mapping with standard verbosity."""
        result = get_full_security_control_events_mapping(mock_security_control_event, "standard")
        
        # Should have all reduced mapping fields
        expected_fields = list(reduced_security_control_events_mapping.keys())
        
        for field in expected_fields:
            assert field in result
        
        # Check values
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
        assert result["action"] == ["FileDeleteInfo"]
        assert result["source_hosts"] == ["TEST-HOST-1", "172.31.17.101"]
    
    def test_get_full_security_control_events_mapping_detailed(self, mock_security_control_event):
        """Test full security control events mapping with detailed verbosity."""
        result = get_full_security_control_events_mapping(mock_security_control_event, "detailed")
        
        # Should have all full mapping fields plus preview fields
        expected_fields = list(full_security_control_events_mapping.keys()) + ["original_fields", "raw_log_preview"]
        
        for field in expected_fields:
            assert field in result
        
        # Check values
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
        assert result["file_path"] == ["/path/to/file.exe"]
        assert result["file_hashes"] == ["abc123def456"]
        assert result["raw_log_preview"] == "{\"event_simpleName\":\"FileDeleteInfo\"}"
        assert result["original_fields"] == {"aid": "acb383cbca774d2c976ec87f6ba4ce0f"}
    
    def test_get_full_security_control_events_mapping_detailed_truncated_log(self, mock_security_control_event):
        """Test full security control events mapping with detailed verbosity and truncated log."""
        # Create a long raw log
        long_log = "x" * 2000  # 2000 characters
        mock_security_control_event["rawLog"] = long_log
        
        result = get_full_security_control_events_mapping(mock_security_control_event, "detailed")
        
        # Should be truncated to 1000 characters + truncation message
        assert len(result["raw_log_preview"]) == 1000 + len("... [truncated]")
        assert result["raw_log_preview"].endswith("... [truncated]")
    
    def test_get_full_security_control_events_mapping_full(self, mock_security_control_event):
        """Test full security control events mapping with full verbosity."""
        result = get_full_security_control_events_mapping(mock_security_control_event, "full")
        
        # Should have all full mapping fields plus raw log and original fields
        expected_fields = list(full_security_control_events_mapping.keys()) + ["raw_log", "original_fields"]
        
        for field in expected_fields:
            assert field in result
        
        # Check values
        assert result["event_id"] == "8207d61e-d14b-5e1d-adcb-8ea461249001"
        assert result["vendor"] == "CrowdStrike"
        assert result["product"] == "CrowdStrike FDR"
        assert result["file_path"] == ["/path/to/file.exe"]
        assert result["file_hashes"] == ["abc123def456"]
        assert result["process_name"] == ["process.exe"]
        assert result["process_ids"] == [1234, 5678]
        assert result["source_ports"] == [80, 443]
        assert result["destination_ports"] == [8080]
        assert result["alert_id"] == "alert-123"
        assert result["alert_name"] == "Test Alert"
        assert result["raw_log"] == "{\"event_simpleName\":\"FileDeleteInfo\"}"
        assert result["original_fields"] == {"aid": "acb383cbca774d2c976ec87f6ba4ce0f"}
    
    def test_get_full_security_control_events_mapping_invalid_verbosity(self, mock_security_control_event):
        """Test full security control events mapping with invalid verbosity level."""
        result = get_full_security_control_events_mapping(mock_security_control_event, "invalid")
        
        # Should default to standard level
        expected_fields = list(reduced_security_control_events_mapping.keys())
        
        for field in expected_fields:
            assert field in result
        
        # Should not have detailed fields
        assert "raw_log" not in result
        assert "original_fields" not in result
    
    def test_get_full_security_control_events_mapping_missing_raw_log(self, mock_security_control_event):
        """Test full security control events mapping with missing raw log."""
        # Remove raw log
        del mock_security_control_event["rawLog"]
        
        result = get_full_security_control_events_mapping(mock_security_control_event, "full")
        
        # Should still work but without raw log
        assert "event_id" in result
        assert "vendor" in result
        assert "raw_log" not in result
    
    def test_get_full_security_control_events_mapping_missing_original_fields(self, mock_security_control_event):
        """Test full security control events mapping with missing original fields."""
        # Remove original fields
        del mock_security_control_event["originalFields"]
        
        result = get_full_security_control_events_mapping(mock_security_control_event, "full")
        
        # Should still work but without original fields
        assert "event_id" in result
        assert "vendor" in result
        assert "original_fields" not in result