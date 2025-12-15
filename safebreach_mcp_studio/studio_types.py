"""
Data transformation functions for Studio MCP Server.

This module provides functions to transform SafeBreach Breach Studio API responses
into MCP-compatible formats.
"""

from typing import Dict, Any


def get_validation_response_mapping(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform validation API response to MCP format.

    Args:
        api_response: Raw API response from validation endpoint

    Returns:
        Transformed validation result with the following structure:
        {
            "is_valid": bool,           # Overall validation status
            "exit_code": int,           # Exit code from validator
            "validation_errors": list,  # List of validation errors
            "stderr": str,              # Standard error output
            "stdout": dict              # Standard output details
        }
    """
    data = api_response.get('data', {})

    # Extract validation errors from stdout
    stdout = data.get('stdout', {})
    validation_errors = []
    for file_path, errors in stdout.items():
        if errors:  # Only add non-empty error lists
            validation_errors.extend(errors)

    return {
        "is_valid": data.get('is_valid', False) or data.get('valid', False),
        "exit_code": data.get('exit_code', -1),
        "validation_errors": validation_errors,
        "stderr": data.get('stderr', ''),
        "stdout": stdout
    }


def get_draft_response_mapping(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform draft save API response to MCP format.

    Args:
        api_response: Raw API response from save draft endpoint

    Returns:
        Transformed draft metadata with the following structure:
        {
            "draft_id": int,                # ID of created draft
            "name": str,                    # Draft name
            "description": str,             # Draft description
            "status": str,                  # Always "draft"
            "timeout": int,                 # Execution timeout
            "creation_date": str,           # ISO datetime string
            "update_date": str,             # ISO datetime string
            "target_file_name": str,        # Always "target.py"
            "method_type": int,             # Always 5
            "origin": str                   # Always "BREACH_STUDIO"
        }
    """
    data = api_response.get('data', {})

    return {
        "draft_id": data.get('id', 0),
        "name": data.get('name', ''),
        "description": data.get('description', ''),
        "status": data.get('status', 'draft'),
        "timeout": data.get('timeout', 300),
        "creation_date": data.get('creationDate', ''),
        "update_date": data.get('updateDate', ''),
        "target_file_name": data.get('targetFileName', 'target.py'),
        "method_type": data.get('methodType', 5),
        "origin": data.get('origin', 'BREACH_STUDIO')
    }


def get_simulation_list_item_mapping(simulation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a single simulation item from the list API response to MCP format.

    Args:
        simulation: Single simulation object from API response

    Returns:
        Transformed simulation summary with key fields
    """
    return {
        "id": simulation.get('id', 0),
        "name": simulation.get('name', ''),
        "description": simulation.get('description', ''),
        "status": simulation.get('status', 'draft'),
        "method_type": simulation.get('methodType', 5),
        "timeout": simulation.get('timeout', 300),
        "creation_date": simulation.get('creationDate', ''),
        "update_date": simulation.get('updateDate', ''),
        "published_date": simulation.get('publishedDate'),
        "target_file_name": simulation.get('targetFileName', 'target.py'),
        "origin": simulation.get('origin', 'BREACH_STUDIO'),
        "user_created": simulation.get('userCreated'),
        "user_updated": simulation.get('userUpdated')
    }


def get_all_simulations_response_mapping(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform get all simulations API response to MCP format.

    Args:
        api_response: Raw API response from get all endpoint

    Returns:
        Transformed response with simulations list and metadata
    """
    data = api_response.get('data', [])

    simulations = [get_simulation_list_item_mapping(sim) for sim in data]

    # Separate draft and published simulations
    draft_simulations = [sim for sim in simulations if sim['status'] == 'draft']
    published_simulations = [sim for sim in simulations if sim['status'] == 'published']

    return {
        "simulations": simulations,
        "total_count": len(simulations),
        "draft_count": len(draft_simulations),
        "published_count": len(published_simulations)
    }


def get_execution_result_mapping(execution: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a single execution result from the execution history API to MCP format.

    Args:
        execution: Single execution result object from API response

    Returns:
        Transformed execution result with key fields including:
        - Basic execution info (id, status, timing)
        - Test/plan information
        - Simulator details (attacker/target)
        - Result details and security action
        - Parameters used
        - Labels (e.g., "Draft")
    """
    # Extract timing information
    start_time = execution.get('startTime', '')
    end_time = execution.get('endTime', '')
    execution_time = execution.get('executionTime', '')

    # Extract node/simulator information
    attacker_node = {
        "id": execution.get('attackerNodeId', ''),
        "name": execution.get('attackerNodeName', ''),
        "os_type": execution.get('attackerOSType', ''),
        "os_version": execution.get('attackerOSVersion', ''),
        "ip": execution.get('sourceIp', '')
    }

    target_node = {
        "id": execution.get('targetNodeId', ''),
        "name": execution.get('targetNodeName', ''),
        "os_type": execution.get('targetOSType', ''),
        "os_version": execution.get('targetOSVersion', ''),
        "ip": execution.get('destinationIp', '')
    }

    # Extract parameters
    params_obj = execution.get('paramsObj', {})
    params_str = execution.get('paramsStr', [])
    parameters = execution.get('parameters', {})

    # Extract result information
    result_info = {
        "code": execution.get('resultCode', ''),
        "details": execution.get('resultDetails', '')
    }

    # Build clean result object
    return {
        "execution_id": execution.get('id', ''),
        "job_id": execution.get('jobId', ''),
        "original_execution_id": execution.get('originalExecutionId', ''),

        # Simulation identification
        "simulation_id": execution.get('moveId', 0),
        "simulation_name": execution.get('moveName', ''),
        "simulation_description": execution.get('moveDesc', ''),

        # Test/Plan information
        "test_name": execution.get('testName', ''),
        "plan_name": execution.get('planName', ''),
        "step_name": execution.get('stepName', ''),
        "plan_run_id": execution.get('planRunId', ''),
        "step_run_id": execution.get('stepRunId', ''),
        "run_id": execution.get('runId', ''),

        # Timing
        "start_time": start_time,
        "end_time": end_time,
        "execution_time": execution_time,
        "attacker_start_time": execution.get('attackerSimulatorStartTime', ''),
        "attacker_end_time": execution.get('attackerSimulatorEndTime', ''),
        "target_start_time": execution.get('targetSimulatorStartTime', ''),
        "target_end_time": execution.get('targetSimulatorEndTime', ''),

        # Status and results
        "status": execution.get('status', ''),  # SUCCESS, FAIL, etc.
        "final_status": execution.get('finalStatus', ''),  # missed, stopped, prevented, etc.
        "security_action": execution.get('securityAction', ''),  # not_logged, logged, prevented, etc.
        "result": result_info,

        # Nodes
        "attacker": attacker_node,
        "target": target_node,

        # Parameters
        "params_summary": params_str,
        "params_object": params_obj,
        "parameters_detailed": parameters,

        # Protocol and networking
        "protocol": execution.get('protocol', []),
        "attack_protocol": execution.get('attackProtocol', ''),
        "source_port": execution.get('sourcePort', []),

        # Classification
        "labels": execution.get('labels', []),
        "tags": execution.get('tags', []),
        "attack_types": execution.get('Attack_Type', []),
        "mitre_tactics": execution.get('MITRE_Tactic', []),

        # Additional metadata
        "package_name": execution.get('packageName', ''),
        "package_id": execution.get('packageId', 0),
        "method_id": execution.get('methodId', 0),
        "deployment_name": execution.get('deploymentName', []),
        "deployment_id": execution.get('deploymentId', []),

        # Event counts
        "simulation_events_count": len(execution.get('simulationEvents', [])),
        "attack_types_counter": execution.get('attackTypesCounter', 0),

        # Optional: Include full simulation events if needed (can be large)
        # "simulation_events": execution.get('simulationEvents', [])
    }
