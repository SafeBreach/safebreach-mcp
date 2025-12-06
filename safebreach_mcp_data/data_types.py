"""
SafeBreach Data Types

This module provides data type mappings and transformations for SafeBreach data,
specifically for test and simulation entities.
"""

from typing import Dict, Any, List
from safebreach_mcp_data.drifts_metadata import drift_types_mapping

# Test summary mapping
reduced_test_summary_mapping = {
    'name': 'planName',
    'test_id': 'planRunId',
    'start_time': 'startTime',
    'end_time': 'endTime',
    'duration': 'duration',
    'status': 'status'
}

# Simulation result mappings
reduced_simulation_results_mapping = {
    'simulation_id': 'id',
    'test_name': 'planName',
    'test_id': 'planRunId',
    'start_time': 'attackerSimulatorStartTime',
    'end_time': 'executionTime',
    'status': 'finalStatus',
    'playbook_attack_id': 'moveId',
    'playbook_attack_name': 'moveName',
    'drift_tracking_code': 'originalExecutionId',
}

full_simulation_results_mapping = {
    **reduced_simulation_results_mapping,
    'prevented_by_security_control': 'preventedBy',
    'reported_by_security_control': 'reportedBy',
    'logged_by_security_control': 'loggedBy',
    'attacker_host_name': 'attackerNodeName',
    'attacker_OS_type': 'attackerOSType',
    'security_control_action': 'securityAction',
    'attack_bypassed_security_control': 'finalStatus',
    'result_details': 'resultDetails',
    'attack_plan': 'moveDesc',
    'attacker_node_id': 'attackerNodeId',
    'attacker_node_name': 'attackerNodeName',
    'attacker_node_os_build': 'attackerNodeOSBuild',
    'attacker_os_pretty_name': 'attackerOSPrettyName',
    'target_node_id': 'targetNodeId',
    'target_node_name': 'targetNodeName',
    'target_node_os_build': 'targetNodeOSBuild',
    'target_os_pretty_name': 'targetOSPrettyName',
}


def map_reduced_entity(entity, mapping):
    """
    Maps the keys of the entity to the new keys defined in the mapping.
    EXACT copy from original safebreach_types.py
    """
    return {new_key: entity[old_key] for new_key, old_key in mapping.items() if old_key in entity}


def map_entity(full_entity, mapping):
    """
    Maps the internally facing attributes of a Safebreach entity to externally facing attributes.
    EXACT copy from original safebreach_types.py
    """
    for external_attribute,internal_attribute in mapping.items():
        if internal_attribute in full_entity:
            full_entity[external_attribute] = full_entity[internal_attribute]
            del full_entity[internal_attribute]

    return full_entity


def get_reduced_test_summary_mapping(test_summary_entity):
    """
    Returns a reduced test summary entity with only the relevant fields.
    EXACT copy from original safebreach_types.py
    """
    reduced_test_summary_entity = map_reduced_entity(test_summary_entity, reduced_test_summary_mapping)
    system_tags = test_summary_entity.get('systemTags', [])
    reduced_test_summary_entity['test_type'] = "Breach And Attack Simulation (aka BAS aks Validate)" if "ALM" not in system_tags else "Automated Lateral Movement (aka ALM aka Propagate)"
    return reduced_test_summary_entity


def get_reduced_simulation_result_entity(simulation_result_entity):
    """
    Returns a reduced simulation result entity with only the relevant fields.
    EXACT copy from original safebreach_types.py
    """
    reduced_entity_to_return = map_reduced_entity(simulation_result_entity, reduced_simulation_results_mapping)
    reduced_entity_to_return['is_drifted'] = 'driftType' in simulation_result_entity

    if reduced_entity_to_return['is_drifted'] and simulation_result_entity['driftType'] == 'no_drift':
        reduced_entity_to_return['is_drifted'] = False

    return reduced_entity_to_return


def get_full_simulation_result_entity(simulation_result_entity, include_mitre_techniques=False, include_basic_attack_logs=False, include_drift_info=False):
    """
    Returns a full simulation result entity with optional extensions.
    
    Args:
        simulation_result_entity: Raw simulation result data from SafeBreach API
        include_mitre_techniques: Include MITRE ATT&CK technique details
        include_basic_attack_logs: Include basic attack logs by host from simulation events
        
    Returns:
        Dict with full simulation result data and optional extensions
    """
    # Use map_reduced_entity with full mapping to get all fields
    full_simulation_result_entity = map_reduced_entity(simulation_result_entity, full_simulation_results_mapping)
    
    if include_drift_info:
        # We're seeing cases where the simulation result entity does not have the 'driftType' key
        # and other cases where it has the 'driftType' key but its value is 'no_drift'.
        full_simulation_result_entity['is_drifted'] = 'driftType' in simulation_result_entity
        if full_simulation_result_entity['is_drifted'] and simulation_result_entity['driftType'] == 'no_drift':
            full_simulation_result_entity['is_drifted'] = False

        if full_simulation_result_entity['is_drifted']:
            # If the simulation result entity has a drift, we add drift info
            # to the full simulation result entity. 
            drift_info = drift_types_mapping.get(simulation_result_entity['driftType'].lower(),
                                                 {
                                                     'type_of_drift': 'unknown',
                                                     'security_impact': 'unknown',
                                                     'description': f'No description available for {simulation_result_entity['driftType']}',
                                                     'hint_to_llm': 'consider using the drift_tracking_code to correlate with other simulation results to understand the drift'})     
            drift_info['drift_tracking_code'] = simulation_result_entity['originalExecutionId']
            full_simulation_result_entity['drift_info'] = drift_info

    else:
        if simulation_result_entity.get('lastStatusChangeDate', '') != simulation_result_entity.get('executionTime', ''):
            # This simulation did not drift, but it had a status change in the past.
            full_simulation_result_entity['drift_info'] = {
                'last_drift_date': simulation_result_entity.get('lastStatusChangeDate'),      # Most recent drift date
            }

    if include_mitre_techniques:
        mitre_techniques = []
        for technique in simulation_result_entity.get('MITRE_Technique', []):
            mitre_techniques.append({
                'id': technique.get('value'),
                'display_name': technique.get('displayName'),
                'url': technique.get('url')
            })
        full_simulation_result_entity['mitre_techniques'] = mitre_techniques

    if include_basic_attack_logs:
        # Basic attack logs are stored in the simulationEvents field
        simulation_events = simulation_result_entity.get('simulationEvents', [])
        
        # Group events by nodeId (host)
        events_by_host = {}
        for event in simulation_events:
            if isinstance(event, dict):
                node_id = event.get('nodeId', 'unknown')
                if node_id not in events_by_host:
                    events_by_host[node_id] = []
                events_by_host[node_id].append(event)
        
        # Transform grouped events into the expected format
        logs_by_host = []
        for node_id, host_events in events_by_host.items():
            host_object = {
                'host_info': {
                    'node_id': node_id,
                    'event_count': len(host_events)
                },
                'host_logs': host_events  # Include all simulation events for this host
            }
            logs_by_host.append(host_object)
        
        full_simulation_result_entity['basic_attack_logs_by_hosts'] = logs_by_host

    return full_simulation_result_entity


# Security control events mappings
reduced_security_control_events_mapping = {
    'event_id': 'id',
    'timestamp': 'fields.timestamp',
    'vendor': 'fields.vendor',
    'product': 'fields.product',
    'action': 'fields.action',
    'source_hosts': 'fields.sourceHosts',
    'destination_hosts': 'fields.destHosts',
    'status': 'fields.status',
    'connector_name': 'connectorName',
    'simulation_id': 'simulationId',
    'test_id': 'planRunId',
    'move_id': 'moveId'
}

full_security_control_events_mapping = {
    **reduced_security_control_events_mapping,
    'file_path': 'fields.filePath',
    'file_hashes': 'fields.fileHashes',
    'process_name': 'fields.processName',
    'process_ids': 'fields.processIds',
    'source_ports': 'fields.sourcePorts',
    'destination_ports': 'fields.destPorts',
    'alert_id': 'fields.alertId',
    'alert_name': 'fields.alertName',
    'parser': 'parser',
    'connector_id': 'connectorId',
    'connector_type': 'connectorType',
    'correlated': 'correlated',
    'correlation_rules': 'correlatedRules',
    'drop_rules': 'dropRules',
    'step_run_id': 'stepRunId'
}


def get_nested_value(data, path, default=None):
    """
    Get a nested value from a dictionary using dot notation.
    
    Args:
        data: The dictionary to search
        path: The dot-separated path (e.g., 'fields.vendor')
        default: Default value if path not found
    
    Returns:
        The value at the path or default
    """
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def map_security_control_event(event_entity, mapping):
    """
    Maps security control event with support for nested field access.
    
    Args:
        event_entity: Raw security control event data from SafeBreach API
        mapping: Dictionary mapping new keys to old keys (with dot notation support)
    
    Returns:
        Dict with mapped fields
    """
    mapped_entity = {}
    
    for new_key, old_key in mapping.items():
        if '.' in old_key:
            # Handle nested field access
            value = get_nested_value(event_entity, old_key)
        else:
            # Handle direct field access
            value = event_entity.get(old_key)
        
        if value is not None:
            mapped_entity[new_key] = value
    
    return mapped_entity


def get_reduced_security_control_events_mapping(security_control_event_entity):
    """
    Returns a reduced security control event entity with only the relevant fields.
    
    Args:
        security_control_event_entity: Raw security control event data from SafeBreach API
    
    Returns:
        Dict with reduced security control event data
    """
    return map_security_control_event(security_control_event_entity, reduced_security_control_events_mapping)


def get_full_security_control_events_mapping(security_control_event_entity, verbosity_level="standard"):
    """
    Returns a full security control event entity with optional verbosity levels.
    
    Args:
        security_control_event_entity: Raw security control event data from SafeBreach API
        verbosity_level: Level of detail ("minimal", "standard", "detailed", "full")
    
    Returns:
        Dict with security control event data based on verbosity level
    """
    if verbosity_level == "minimal":
        # Return only essential fields for basic correlation
        minimal_mapping = {
            'event_id': 'id',
            'timestamp': 'fields.timestamp',
            'vendor': 'fields.vendor',
            'product': 'fields.product',
            'action': 'fields.action',
            'status': 'fields.status',
            'simulation_id': 'simulationId',
            'test_id': 'planRunId'
        }
        return map_security_control_event(security_control_event_entity, minimal_mapping)
    
    elif verbosity_level == "standard":
        # Return standard fields for typical SecOps analysis
        return map_security_control_event(security_control_event_entity, reduced_security_control_events_mapping)
    
    elif verbosity_level == "detailed":
        # Return detailed fields for thorough investigation
        detailed_mapping = {
            **full_security_control_events_mapping,
            'original_fields': 'originalFields',
            'raw_log_preview': 'rawLog'
        }
        result = map_security_control_event(security_control_event_entity, detailed_mapping)
        
        # Truncate raw log for readability (first 1000 chars)
        if 'raw_log_preview' in result and isinstance(result['raw_log_preview'], str):
            if len(result['raw_log_preview']) > 1000:
                result['raw_log_preview'] = result['raw_log_preview'][:1000] + "... [truncated]"
        
        return result
    
    elif verbosity_level == "full":
        # Return complete data for comprehensive analysis
        result = map_security_control_event(security_control_event_entity, full_security_control_events_mapping)
        
        # Add raw log and original fields
        if 'rawLog' in security_control_event_entity:
            result['raw_log'] = security_control_event_entity['rawLog']
        
        if 'originalFields' in security_control_event_entity:
            result['original_fields'] = security_control_event_entity['originalFields']
        
        return result
    
    else:
        # Default to standard level
        return map_security_control_event(security_control_event_entity, reduced_security_control_events_mapping)


def get_full_simulation_logs_mapping(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform SafeBreach API full simulation logs response to MCP tool format.

    Focuses on extracting detailed logs and structured execution information
    from the nested response structure. The primary feature is exposing the
    LOGS field (~40KB) that contains timestamped simulator execution logs.

    Args:
        api_response: Raw API response from executionsHistoryResults endpoint

    Returns:
        Transformed dictionary with organized full simulation logs data

    Raises:
        ValueError: If expected fields are missing from response
        IndexError: If dataObj structure is unexpected
    """
    # Extract nested details object
    data_obj = api_response.get('dataObj', {})
    data_array = data_obj.get('data', [[]])

    if not data_array or not data_array[0]:
        raise ValueError("Response missing dataObj.data structure")

    details_obj = data_array[0][0]
    details = details_obj.get('details', {})

    # Helper function to calculate duration
    def calculate_duration(start_time: str, end_time: str) -> float:
        """Calculate duration in seconds between two ISO timestamps."""
        if not start_time or not end_time:
            return 0.0
        try:
            from datetime import datetime
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            return (end - start).total_seconds()
        except (ValueError, AttributeError):
            return 0.0

    # Build transformed response
    return {
        # Core identification
        "simulation_id": str(api_response.get('id', '')),
        "test_id": api_response.get('planRunId', ''),
        "run_id": api_response.get('runId', ''),

        # Execution timing
        "execution_times": {
            "start_time": api_response.get('startTime', ''),
            "end_time": api_response.get('endTime', ''),
            "execution_time": api_response.get('executionTime', ''),
            "duration_seconds": calculate_duration(
                api_response.get('startTime', ''),
                api_response.get('endTime', '')
            ),
            "simulation_start": details.get('SIMULATION_START_TIME', ''),
            "simulation_end": details.get('SIMULATION_END_TIME', ''),
            "startup_duration": details.get('STARTUP_DURATION', 0.0)
        },

        # Execution status
        "status": {
            "overall": api_response.get('status', ''),
            "final_status": api_response.get('finalStatus', ''),
            "task_status": details.get('STATUS', ''),
            "task_code": details.get('CODE', 0),
            "security_action": api_response.get('securityAction', '')
        },

        # PRIMARY FEATURE: Detailed logs
        "logs": details.get('LOGS', ''),

        # Structured execution steps
        "simulation_steps": details.get('SIMULATION_STEPS', []),

        # Summary information
        "details_summary": details.get('DETAILS', ''),
        "error": details.get('ERROR', ''),
        "output": details.get('OUTPUT', ''),

        # Execution context
        "metadata": {
            "job_id": api_response.get('jobId', 0),
            "task_id": api_response.get('taskId', 0),
            "method_id": api_response.get('methodId', 0),
            "node_name_in_move": details_obj.get('nodeNameInMove', ''),
            "state": details_obj.get('state', ''),
            "node_id": details_obj.get('id', '')
        },

        # Attack information
        "attack_info": {
            "move_id": api_response.get('moveId', 0),
            "move_name": api_response.get('moveName', ''),
            "move_description": api_response.get('moveDesc', ''),
            "protocol": api_response.get('protocol', ''),
            "approach": api_response.get('approach', ''),
            "opponent": api_response.get('opponent', ''),
            "noise_level": api_response.get('noiseLevel', ''),
            "impact": api_response.get('impact', '')
        },

        # Host information
        "host_info": {
            "attacker_node_id": api_response.get('attackerNodeId', ''),
            "attacker_node_name": api_response.get('attackerNodeName', ''),
            "attacker_os_type": api_response.get('attackerOSType', ''),
            "attacker_os_version": api_response.get('attackerOSVersion', ''),
            "target_node_id": api_response.get('targetNodeId', ''),
            "target_node_name": api_response.get('targetNodeName', ''),
            "target_os_type": api_response.get('targetOSType', ''),
            "target_os_version": api_response.get('targetOSVersion', ''),
            "src_node_id": api_response.get('srcNodeId', ''),
            "dest_node_id": api_response.get('destNodeId', '')
        }
    }