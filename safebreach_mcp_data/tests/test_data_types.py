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
    full_security_control_events_mapping,
    get_full_simulation_logs_mapping,
    get_reduced_test_summary_mapping,
    _build_node_data,
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


class TestFullSimulationLogsDualScript:
    """Test suite for full simulation logs role-based mapping (host vs dual-script attacks)."""

    def _make_api_response(self, entries, attacker_node_id, target_node_id, **overrides):
        """Helper to build a mock API response."""
        base = {
            'id': '1477531',
            'runId': '1764165600525.2',
            'planRunId': '1764165600525.2',
            'status': 'SUCCESS',
            'finalStatus': 'logged',
            'startTime': '2025-11-26T14:00:35.809Z',
            'endTime': '2025-11-26T14:01:05.685Z',
            'executionTime': '2025-11-26T14:01:05.685Z',
            'securityAction': 'log_only',
            'moveId': 11318,
            'moveName': 'Write File to Disk',
            'moveDesc': 'Write a file to disk',
            'attackerNodeId': attacker_node_id,
            'attackerNodeName': 'attacker-sim',
            'attackerOSType': 'LINUX',
            'attackerOSPrettyName': 'Ubuntu 22.04',
            'targetNodeId': target_node_id,
            'targetNodeName': 'target-sim',
            'targetOSType': 'WINDOWS',
            'targetOSPrettyName': 'Windows Server 2022',
            'dataObj': {
                'data': [entries]
            },
        }
        base.update(overrides)
        return base

    def _make_entry(self, node_id, node_name='sim', logs='logs', steps=None, error='', output=''):
        """Helper to build a single data_array entry."""
        return {
            'id': node_id,
            'nodeNameInMove': node_name,
            'state': 'finished',
            'details': {
                'LOGS': logs,
                'SIMULATION_STEPS': steps or [],
                'DETAILS': 'Task finished',
                'ERROR': error,
                'OUTPUT': output,
                'STATUS': 'DONE',
                'CODE': 0,
                'SIMULATION_START_TIME': '2025-11-26T14:00:37.817Z',
                'SIMULATION_END_TIME': '2025-11-26T14:01:05.419Z',
                'STARTUP_DURATION': 1.291,
            }
        }

    def test_host_attack_target_only(self):
        """Host attack: target populated, attacker is None."""
        node_id = 'node-aaa'
        entry = self._make_entry(node_id, node_name='gold', logs='host logs here')
        api_response = self._make_api_response(
            [entry], attacker_node_id=node_id, target_node_id=node_id
        )

        result = get_full_simulation_logs_mapping(api_response)

        assert result['target'] is not None
        assert result['attacker'] is None
        assert result['target']['logs'] == 'host logs here'
        assert result['target']['node_id'] == node_id

    def test_dual_script_both_roles(self):
        """Dual-script attack: both attacker and target have distinct logs."""
        target_id = 'node-target'
        attacker_id = 'node-attacker'
        target_entry = self._make_entry(target_id, node_name='target', logs='target logs')
        attacker_entry = self._make_entry(attacker_id, node_name='attacker', logs='attacker logs')

        api_response = self._make_api_response(
            [target_entry, attacker_entry],
            attacker_node_id=attacker_id,
            target_node_id=target_id
        )

        result = get_full_simulation_logs_mapping(api_response)

        assert result['target'] is not None
        assert result['attacker'] is not None
        assert result['target']['logs'] == 'target logs'
        assert result['attacker']['logs'] == 'attacker logs'

    def test_role_mapping_by_node_id(self):
        """Correct role assignment by matching entry ID to attackerNodeId/targetNodeId."""
        target_id = 'node-tgt-111'
        attacker_id = 'node-atk-222'
        # Put attacker first in array to verify mapping uses ID, not position
        attacker_entry = self._make_entry(attacker_id, node_name='atk-sim', logs='atk-logs')
        target_entry = self._make_entry(target_id, node_name='tgt-sim', logs='tgt-logs')

        api_response = self._make_api_response(
            [attacker_entry, target_entry],
            attacker_node_id=attacker_id,
            target_node_id=target_id
        )

        result = get_full_simulation_logs_mapping(api_response)

        # Despite attacker being first in array, role mapping should be correct
        assert result['target']['node_id'] == target_id
        assert result['target']['logs'] == 'tgt-logs'
        assert result['attacker']['node_id'] == attacker_id
        assert result['attacker']['logs'] == 'atk-logs'

    def test_node_data_structure(self):
        """Each role section has all expected fields."""
        node_id = 'node-aaa'
        entry = self._make_entry(node_id, node_name='gold', logs='log data', error='some error', output='some output')
        api_response = self._make_api_response(
            [entry], attacker_node_id=node_id, target_node_id=node_id
        )

        result = get_full_simulation_logs_mapping(api_response)
        target = result['target']

        expected_fields = [
            'node_name', 'node_id', 'state', 'logs', 'simulation_steps',
            'details_summary', 'error', 'output', 'task_status', 'task_code',
            'os_type', 'os_version'
        ]
        for field in expected_fields:
            assert field in target, f"Missing field '{field}' in target node data"

        assert target['logs'] == 'log data'
        assert target['error'] == 'some error'
        assert target['output'] == 'some output'
        assert target['task_status'] == 'DONE'
        assert target['task_code'] == 0
        assert target['state'] == 'finished'

    def test_os_info_in_node_data(self):
        """OS type/version from top-level merged into node data."""
        target_id = 'node-tgt'
        attacker_id = 'node-atk'
        target_entry = self._make_entry(target_id, node_name='tgt')
        attacker_entry = self._make_entry(attacker_id, node_name='atk')

        api_response = self._make_api_response(
            [target_entry, attacker_entry],
            attacker_node_id=attacker_id,
            target_node_id=target_id,
            targetOSType='WINDOWS',
            targetOSPrettyName='Windows Server 2022',
            attackerOSType='LINUX',
            attackerOSPrettyName='Ubuntu 22.04',
        )

        result = get_full_simulation_logs_mapping(api_response)

        assert result['target']['os_type'] == 'WINDOWS'
        assert result['target']['os_version'] == 'Windows Server 2022'
        assert result['attacker']['os_type'] == 'LINUX'
        assert result['attacker']['os_version'] == 'Ubuntu 22.04'

    def test_build_node_data_helper(self):
        """Test _build_node_data extracts all expected fields from an entry."""
        entry = {
            'id': 'node-123',
            'nodeNameInMove': 'sim-node',
            'state': 'finished',
            'details': {
                'LOGS': 'detailed logs',
                'SIMULATION_STEPS': [{'step': 1}],
                'DETAILS': 'summary',
                'ERROR': 'err',
                'OUTPUT': 'out',
                'STATUS': 'DONE',
                'CODE': 0,
                'SIMULATION_START_TIME': '2025-01-01T00:00:00Z',
                'SIMULATION_END_TIME': '2025-01-01T00:01:00Z',
                'STARTUP_DURATION': 1.5,
            }
        }

        node = _build_node_data(entry)

        assert node['node_id'] == 'node-123'
        assert node['node_name'] == 'sim-node'
        assert node['state'] == 'finished'
        assert node['logs'] == 'detailed logs'
        assert node['simulation_steps'] == [{'step': 1}]
        assert node['details_summary'] == 'summary'
        assert node['error'] == 'err'
        assert node['output'] == 'out'
        assert node['task_status'] == 'DONE'
        assert node['task_code'] == 0


class TestFullSimulationLogsEmptyData:
    """Test suite for graceful handling of empty dataObj.data in full simulation logs (SAF-28582).

    When the API returns HTTP 200 with empty execution logs (dataObj.data = [[]]),
    the mapping should return a valid response with logs_available=False instead
    of raising ValueError.
    """

    def _make_empty_api_response(self, **overrides):
        """Helper to build a mock API response with empty dataObj.data."""
        base = {
            'id': 3213805,
            'runId': '1771853252399.2',
            'planRunId': '1771853252399.2',
            'status': 'INTERNAL_FAIL',
            'finalStatus': 'stopped',
            'startTime': '2026-02-24T12:52:00.000Z',
            'endTime': '2026-02-24T12:53:06.000Z',
            'executionTime': '2026-02-24T12:53:06.000Z',
            'securityAction': '',
            'moveId': 10042,
            'moveName': "Email 'Azure token collector' Bash script as a ZIP attachment",
            'moveDesc': 'Test email-based attack delivery',
            'protocol': 'SMTP',
            'approach': 'Social Engineering',
            'opponent': 'attacker',
            'noiseLevel': 'low',
            'impact': 'medium',
            'attackerNodeId': 'node-atk-1',
            'targetNodeId': 'node-tgt-1',
            'dataObj': {'data': [[]]},
        }
        base.update(overrides)
        return base

    def test_empty_data_array_returns_graceful_response(self):
        """Input: {"dataObj": {"data": [[]]}} -> Returns dict with logs_available=False."""
        api_response = self._make_empty_api_response()

        result = get_full_simulation_logs_mapping(api_response)

        assert isinstance(result, dict)
        assert result['logs_available'] is False
        assert isinstance(result['logs_status'], str)
        assert len(result['logs_status']) > 0

    def test_missing_data_obj_returns_graceful_response(self):
        """Input: {} (no dataObj at all) -> Returns dict with logs_available=False."""
        api_response = {'id': 999, 'planRunId': 'test-1', 'status': 'FAIL'}

        result = get_full_simulation_logs_mapping(api_response)

        assert isinstance(result, dict)
        assert result['logs_available'] is False

    def test_missing_data_key_returns_graceful_response(self):
        """Input: {"dataObj": {}} (dataObj present but no data key) -> Returns dict with logs_available=False."""
        api_response = self._make_empty_api_response()
        api_response['dataObj'] = {}

        result = get_full_simulation_logs_mapping(api_response)

        assert isinstance(result, dict)
        assert result['logs_available'] is False

    def test_empty_data_preserves_metadata(self):
        """Verify simulation_id, test_id, status, attack_info are populated from API fields."""
        api_response = self._make_empty_api_response()

        result = get_full_simulation_logs_mapping(api_response)

        assert result['simulation_id'] == '3213805'
        assert result['test_id'] == '1771853252399.2'
        assert result['status']['overall'] == 'INTERNAL_FAIL'
        assert result['status']['final_status'] == 'stopped'
        assert result['attack_info']['move_id'] == 10042
        assert result['attack_info']['move_name'] == "Email 'Azure token collector' Bash script as a ZIP attachment"
        assert 'execution_times' in result

    def test_empty_data_sets_target_and_attacker_none(self):
        """Verify target=None and attacker=None when logs are empty."""
        api_response = self._make_empty_api_response()

        result = get_full_simulation_logs_mapping(api_response)

        assert result['target'] is None
        assert result['attacker'] is None

    def test_normal_response_has_logs_available_true(self):
        """Verify that normal (non-empty) responses include logs_available=True."""
        node_id = 'node-aaa'
        entry = {
            'id': node_id,
            'nodeNameInMove': 'sim-node',
            'state': 'finished',
            'details': {
                'LOGS': 'detailed logs',
                'SIMULATION_STEPS': [],
                'DETAILS': 'summary',
                'ERROR': '',
                'OUTPUT': '',
                'STATUS': 'DONE',
                'CODE': 0,
                'SIMULATION_START_TIME': '',
                'SIMULATION_END_TIME': '',
                'STARTUP_DURATION': 0.0,
            }
        }
        api_response = {
            'id': '1477531',
            'runId': '1764165600525.2',
            'planRunId': '1764165600525.2',
            'status': 'SUCCESS',
            'finalStatus': 'logged',
            'startTime': '',
            'endTime': '',
            'executionTime': '',
            'securityAction': 'log_only',
            'moveId': 11318,
            'moveName': 'Write File',
            'moveDesc': '',
            'attackerNodeId': node_id,
            'targetNodeId': node_id,
            'dataObj': {'data': [[entry]]},
        }

        result = get_full_simulation_logs_mapping(api_response)

        assert result['logs_available'] is True
        assert result['logs_status'] is None


class TestTestSummaryMapping:
    """Tests for get_reduced_test_summary_mapping including inline stats and propagate findings."""

    def test_always_includes_simulation_statistics(self):
        """Test that simulations_statistics is always present even without requesting it."""
        entity = {
            "planName": "Test Plan",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": [],
            "finalStatus": {"missed": 3, "stopped": 1, "prevented": 5, "detected": 2, "logged": 0, "no-result": 1, "inconsistent": 0}
        }
        result = get_reduced_test_summary_mapping(entity)
        assert "simulations_statistics" in result
        stats = result["simulations_statistics"]
        assert len(stats) == 7
        assert next(s for s in stats if s["status"] == "missed")["count"] == 3
        assert next(s for s in stats if s["status"] == "prevented")["count"] == 5
        assert next(s for s in stats if s["status"] == "detected")["count"] == 2

    def test_missing_final_status_defaults_to_zero(self):
        """Test that missing finalStatus defaults all counts to 0."""
        entity = {
            "planName": "Test",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": []
        }
        result = get_reduced_test_summary_mapping(entity)
        stats = result["simulations_statistics"]
        for stat in stats:
            assert stat["count"] == 0

    def test_propagate_test_includes_findings(self):
        """Test that Propagate (ALM) tests include findings_count and compromised_hosts."""
        entity = {
            "planName": "Propagate Test",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": ["ALM"],
            "finalStatus": {},
            "findingsCount": 42,
            "compromisedHosts": 7
        }
        result = get_reduced_test_summary_mapping(entity)
        assert result["findings_count"] == 42
        assert result["compromised_hosts"] == 7
        assert "Propagate" in result["test_type"]

    def test_validate_test_excludes_findings(self):
        """Test that Validate (BAS) tests do not include findings fields."""
        entity = {
            "planName": "Validate Test",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": [],
            "finalStatus": {},
            "findingsCount": 10,
            "compromisedHosts": 3
        }
        result = get_reduced_test_summary_mapping(entity)
        assert "findings_count" not in result
        assert "compromised_hosts" not in result
        assert "Validate" in result["test_type"]

    def test_propagate_test_missing_findings_fields(self):
        """Test graceful handling when ALM test is missing findings fields in API response."""
        entity = {
            "planName": "Propagate Test",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": ["ALM"],
            "finalStatus": {}
        }
        result = get_reduced_test_summary_mapping(entity)
        assert "findings_count" not in result
        assert "compromised_hosts" not in result
        assert "Propagate" in result["test_type"]

    def test_propagate_test_zero_findings(self):
        """Test that zero findings are still included (not omitted)."""
        entity = {
            "planName": "Propagate Test",
            "planRunId": "run1",
            "startTime": 1000,
            "endTime": 2000,
            "duration": 1000,
            "status": "completed",
            "systemTags": ["ALM"],
            "finalStatus": {},
            "findingsCount": 0,
            "compromisedHosts": 0
        }
        result = get_reduced_test_summary_mapping(entity)
        assert result["findings_count"] == 0
        assert result["compromised_hosts"] == 0