"""
Data transformation functions for Studio MCP Server.

This module provides functions to transform SafeBreach Breach Studio API responses
into MCP-compatible formats.
"""

from typing import Dict, Any, List


PAGE_SIZE = 10


def paginate_studio_attacks(
    attacks: List[Dict[str, Any]],
    page_number: int = 0,
    page_size: int = PAGE_SIZE
) -> Dict[str, Any]:
    """
    Paginate a list of studio attacks.

    Args:
        attacks: List of attack objects
        page_number: Page number (0-based)
        page_size: Number of items per page

    Returns:
        Dict containing paginated results and metadata
    """
    total_attacks = len(attacks)
    total_pages = (total_attacks + page_size - 1) // page_size if total_attacks > 0 else 0

    # Validate page number
    if page_number < 0 or (total_pages > 0 and page_number >= total_pages):
        return {
            'page_number': page_number,
            'total_pages': total_pages,
            'total_attacks': total_attacks,
            'attacks_in_page': [],
            'error': f'Invalid page_number {page_number}. Available pages range from 0 to {total_pages - 1} (total {total_pages} pages)'
        }

    # Calculate slice indices
    start_idx = page_number * page_size
    end_idx = min(start_idx + page_size, total_attacks)

    attacks_in_page = attacks[start_idx:end_idx]

    hint = None
    if page_number + 1 < total_pages:
        hint = f'You can scan next page by calling with page_number={page_number + 1}'
    elif total_pages > 0 and page_number == total_pages - 1:
        hint = 'This is the last page'

    return {
        'attacks_in_page': attacks_in_page,
        'total_attacks': total_attacks,
        'page_number': page_number,
        'total_pages': total_pages,
        'hint_to_agent': hint,
    }


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
            "method_type": int,             # Attack type method code
            "attack_type": str,             # Human-readable attack type
            "origin": str                   # Always "BREACH_STUDIO"
        }
    """
    data = api_response.get('data', {})

    # Reverse-map methodType to attack_type name
    method_type = data.get('methodType', 5)
    method_type_to_attack = {5: "host", 0: "exfil", 2: "infil", 1: "lateral"}
    attack_type = method_type_to_attack.get(method_type, "host")

    return {
        "draft_id": data.get('id', 0),
        "name": data.get('name', ''),
        "description": data.get('description', ''),
        "status": data.get('status', 'draft'),
        "timeout": data.get('timeout', 300),
        "creation_date": data.get('creationDate', ''),
        "update_date": data.get('updateDate', ''),
        "target_file_name": data.get('targetFileName', 'target.py'),
        "method_type": method_type,
        "attack_type": attack_type,
        "origin": data.get('origin', 'BREACH_STUDIO')
    }


def get_attack_list_item_mapping(attack: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a single attack item from the list API response to MCP format.

    Args:
        attack: Single attack object from API response

    Returns:
        Transformed attack summary with key fields
    """
    return {
        "id": attack.get('id', 0),
        "name": attack.get('name', ''),
        "description": attack.get('description', ''),
        "status": attack.get('status', 'draft'),
        "method_type": attack.get('methodType', 5),
        "timeout": attack.get('timeout', 300),
        "creation_date": attack.get('creationDate', ''),
        "update_date": attack.get('updateDate', ''),
        "published_date": attack.get('publishedDate'),
        "target_file_name": attack.get('targetFileName', 'target.py'),
        "origin": attack.get('origin', 'BREACH_STUDIO'),
        "user_created": attack.get('userCreated'),
        "user_updated": attack.get('userUpdated')
    }


def get_all_attacks_response_mapping(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform get all attacks API response to MCP format.

    Args:
        api_response: Raw API response from get all endpoint

    Returns:
        Transformed response with attacks list and metadata
    """
    data = api_response.get('data', [])

    attacks = [get_attack_list_item_mapping(item) for item in data]

    # Separate draft and published attacks
    draft_attacks = [a for a in attacks if a['status'] == 'draft']
    published_attacks = [a for a in attacks if a['status'] == 'published']

    return {
        "attacks": attacks,
        "total_attacks": len(attacks),
        "draft_count": len(draft_attacks),
        "published_count": len(published_attacks)
    }


def _parse_simulation_steps(simulation_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse simulationEvents into structured step list.

    Args:
        simulation_events: List of simulation event objects from API response

    Returns:
        List of structured step dictionaries
    """
    steps = []
    for event in simulation_events:
        steps.append({
            "step_name": event.get('action', ''),
            "timing": event.get('timestamp', ''),
            "status": event.get('type', ''),
            "node": event.get('nodeNameInMove', event.get('nodeId', '')),
            "details": event.get('details', ''),
        })
    return steps


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

    # Compute is_drifted from originalExecutionId
    original_exec_id = execution.get('originalExecutionId', '')
    exec_id = execution.get('id', '')
    is_drifted = bool(original_exec_id and exec_id and original_exec_id != exec_id)

    # Build clean result object
    return {
        "simulation_id": execution.get('id', ''),
        "job_id": execution.get('jobId', ''),
        "drift_tracking_code": original_exec_id,
        "is_drifted": is_drifted,

        # Attack identification
        "attack_id": execution.get('moveId', 0),
        "attack_name": execution.get('moveName', ''),
        "attack_description": execution.get('moveDesc', ''),

        # Test/Plan information
        "test_name": execution.get('testName', ''),
        "plan_name": execution.get('planName', ''),
        "step_name": execution.get('stepName', ''),
        "test_id": execution.get('planRunId', ''),
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
        "execution_status": execution.get('status', ''),  # SUCCESS, FAIL, etc.
        "status": execution.get('finalStatus', ''),  # missed, stopped, prevented, etc.
        "security_action": execution.get('securityAction', ''),
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

        # Enhanced debug fields (Phase 6)
        "simulation_steps": _parse_simulation_steps(execution.get('simulationEvents', [])),
        "logs": execution.get('logs', ''),
        "output": execution.get('output', ''),
    }
