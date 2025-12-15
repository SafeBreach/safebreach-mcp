"""
Business logic functions for Studio MCP Server.

This module provides the core functionality for validating custom Python simulation
code and saving simulations as drafts in SafeBreach Breach Studio.
"""

import re
import time
import json
import logging
import requests
from typing import Dict, Any

from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from .studio_types import (
    get_validation_response_mapping,
    get_draft_response_mapping,
    get_all_simulations_response_mapping
)

# Configure logging
logger = logging.getLogger(__name__)

# Cache for draft metadata (1-hour TTL)
studio_draft_cache = {}
CACHE_TTL = 3600  # 1 hour in seconds

# Required main function signature pattern
# Use negative lookbehind to ensure 'def' is not preceded by word characters (e.g., 'async')
MAIN_FUNCTION_PATTERN = (
    r'(?<!\w)def\s+main\s*\(\s*system_data\s*,\s*asset\s*,\s*proxy\s*,\s*'
    r'\*args\s*,\s*\*\*kwargs\s*\)\s*:'
)

# Valid OS constraint values
VALID_OS_CONSTRAINTS = {"All", "WINDOWS", "LINUX", "MAC"}

# Valid parameter types (excluding BINARY for now - will be added in future iteration)
VALID_PARAMETER_TYPES = {"NOT_CLASSIFIED", "PORT", "URI", "PROTOCOL"}

# Valid protocol values for PROTOCOL parameter type
VALID_PROTOCOLS = {
    "BGP", "BITS", "BOOTP", "DHCP", "DNS", "DROPBOX", "DTLS", "FTP",
    "HTTP", "HTTPS", "ICMP", "IMAP", "IP", "IPSEC", "IRC", "KERBEROS",
    "LDAP", "LLMNR", "mDNS", "MGCP", "MYSQL", "NBNS", "NNTP", "NTP",
    "POP3", "RADIUS", "RDP", "RPC", "SCTP", "SIP", "SMB", "SMTP",
    "SNMP", "SSH", "SSL", "SSDP", "STUN", "SYSLOG", "TCP", "TCPv6",
    "TDS", "TELNET", "TFTP", "TLS", "UDP", "UTP", "VNC", "WEBSOCKET",
    "WHOIS", "XMLRPC", "XMPP", "YMSG"
}


def _validate_os_constraint(os_constraint: str) -> None:
    """
    Validate that the OS constraint value is one of the allowed values.

    Args:
        os_constraint: OS constraint value to validate

    Raises:
        ValueError: If os_constraint is not one of the valid values
    """
    if os_constraint not in VALID_OS_CONSTRAINTS:
        raise ValueError(
            f"os_constraint must be one of {VALID_OS_CONSTRAINTS}, got: '{os_constraint}'"
        )


def _validate_and_build_parameters(parameters: list) -> str:
    """
    Validate and build the parameters JSON string for the API.

    This function takes a simplified parameter structure and converts it to the full
    API format required by SafeBreach Breach Studio.

    Args:
        parameters: List of parameter dictionaries with simplified structure:
            [
                {
                    "name": "filename",                    # Required
                    "value": "c:\\temp\\test.txt",          # Required (can be single value or list)
                    "display_name": "File name",           # Optional (defaults to name)
                    "description": "File path",            # Optional (defaults to "")
                    "type": "NOT_CLASSIFIED"               # Optional (defaults to "NOT_CLASSIFIED")
                                                           # Valid types: NOT_CLASSIFIED, PORT, URI, PROTOCOL
                                                           # PROTOCOL type validates value against 52 protocols
                },
                {
                    "name": "paths",                       # Multi-value parameter example
                    "value": ["c:\\temp\\file1.txt", "c:\\temp\\file2.txt"],
                    "type": "NOT_CLASSIFIED"
                },
                ...
            ]

    Returns:
        JSON string with full parameter structure for the API

    Raises:
        ValueError: If parameters structure is invalid or contains invalid types

    Example:
        >>> params = [{"name": "port", "value": 8080, "type": "PORT"}]
        >>> result = _validate_and_build_parameters(params)
        >>> # Returns JSON with full structure including id, source, values array, etc.
    """
    if not isinstance(parameters, list):
        raise ValueError("parameters must be a list")

    if not parameters:  # Empty list is valid
        return "[]"

    built_parameters = []

    for idx, param in enumerate(parameters):
        if not isinstance(param, dict):
            raise ValueError(f"Parameter at index {idx} must be a dictionary")

        # Validate required fields
        if "name" not in param:
            raise ValueError(f"Parameter at index {idx} missing required field: 'name'")
        if "value" not in param:
            raise ValueError(f"Parameter at index {idx} missing required field: 'value'")

        name = param["name"]
        value = param["value"]
        param_type = param.get("type", "NOT_CLASSIFIED")
        display_name = param.get("display_name", name)
        description = param.get("description", "")

        # Normalize value to list format for consistent handling
        if not isinstance(value, list):
            value_list = [value]
        else:
            value_list = value

        # Validate parameter type
        if param_type not in VALID_PARAMETER_TYPES:
            raise ValueError(
                f"Parameter '{name}' has invalid type '{param_type}'. "
                f"Valid types are: {VALID_PARAMETER_TYPES}"
            )

        # Validate and process each value
        processed_values = []
        for val_idx, val in enumerate(value_list, start=1):
            # Validate protocol value if parameter type is PROTOCOL
            if param_type == "PROTOCOL":
                val_str = str(val)
                # Case-insensitive lookup in VALID_PROTOCOLS
                matched_protocol = None
                for valid_protocol in VALID_PROTOCOLS:
                    if val_str.upper() == valid_protocol.upper():
                        matched_protocol = valid_protocol
                        break

                if matched_protocol is None:
                    raise ValueError(
                        f"Parameter '{name}' has invalid protocol value '{val}'. "
                        f"Valid protocols are: {sorted(VALID_PROTOCOLS)}"
                    )
                # Use the canonical case from VALID_PROTOCOLS
                val = matched_protocol

            # Build value entry
            processed_values.append({
                "id": val_idx,
                "value": val,
                "displayValue": str(val)
            })

        # Build the full parameter structure
        built_param = {
            "id": idx,
            "name": name,
            "type": param_type,
            "source": "PARAM",
            "values": processed_values,
            "isCustom": True,
            "description": description,
            "displayName": display_name
        }

        built_parameters.append(built_param)

    return json.dumps(built_parameters)


def sb_validate_studio_code(python_code: str, console: str = "default") -> Dict[str, Any]:
    """
    Validate custom Python simulation code against Breach Studio requirements.

    This function checks if the provided Python code contains the required main function
    signature and validates it against the SafeBreach Breach Studio API.

    Args:
        python_code: The Python code content to validate
        console: SafeBreach console identifier (default: "default")

    Returns:
        Validation result dictionary containing:
        - is_valid: Overall validation status
        - exit_code: Exit code from validator
        - has_main_function: Whether required main() signature exists
        - validation_errors: List of validation errors
        - stderr: Standard error output
        - stdout: Standard output details

    Raises:
        ValueError: If python_code is empty or None
        requests.HTTPError: For API errors (401, 404, 500, etc.)
        Exception: For unexpected errors

    Example:
        >>> result = sb_validate_studio_code(code, "demo")
        >>> print(result['is_valid'])
        True
        >>> print(result['has_main_function'])
        True
    """
    # Validate input
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")

    logger.info(f"Validating Python code for console: {console}")

    # Check for required main function signature
    has_main_function = bool(re.search(MAIN_FUNCTION_PATTERN, python_code))
    logger.debug(f"Main function signature found: {has_main_function}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    # Note: Don't set Content-Type header - requests library will set it automatically
    # for multipart/form-data when files parameter is used
    headers = {"x-apitoken": apitoken}

    # Prepare multipart form data with Python file
    files = {
        'file': ('target.py', python_code, 'text/x-python-script')
    }

    # Required form data parameters for validation
    data = {
        'class': 'python'
    }

    # Call validation API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/validate"
    logger.info(f"Calling validation API: {api_url}")

    try:
        response = requests.put(api_url, headers=headers, data=data, files=files, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Validation API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Validation API call failed: {e}")
        raise

    # Transform response and add main function check
    result = get_validation_response_mapping(api_response)
    result['has_main_function'] = has_main_function

    logger.debug(f"Validation result: is_valid={result['is_valid']}, "
                 f"has_main_function={has_main_function}, "
                 f"exit_code={result['exit_code']}")

    return result


def sb_save_studio_draft(
    name: str,
    python_code: str,
    description: str = "",
    timeout: int = 300,
    os_constraint: str = "All",
    parameters: list = None,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Save a custom Python simulation as a draft in Breach Studio.

    This function submits the provided Python code and metadata to the SafeBreach
    Breach Studio API to create a new draft simulation.

    Args:
        name: Simulation name (e.g., "Port Scanner")
        python_code: The Python code content
        description: Simulation description (optional, default: "")
        timeout: Execution timeout in seconds (default: 300, min: 1)
        os_constraint: OS constraint for simulation execution (default: "All")
                      Valid values: "All" (no constraint), "WINDOWS", "LINUX", "MAC"
        parameters: Optional list of parameters accessible in system_data (default: None)
                   Each parameter is a dict with:
                   - name (required): Parameter name
                   - value (required): Parameter value (single value or list of values)
                   - type (optional): "NOT_CLASSIFIED", "PORT", "URI", or "PROTOCOL" (default: "NOT_CLASSIFIED")
                     * PROTOCOL type requires value to be one of 52 valid protocols (TCP, HTTP, SSH, etc.)
                   - display_name (optional): Display name (defaults to name)
                   - description (optional): Description (defaults to "")
                   Example single value: {"name": "port", "value": 8080}
                   Example multiple values: {"name": "paths", "value": ["file1.txt", "file2.txt"]}
        console: SafeBreach console identifier (default: "default")

    Returns:
        Draft metadata dictionary containing:
        - draft_id: ID of created draft
        - name: Draft name
        - description: Draft description
        - status: Always "draft"
        - timeout: Execution timeout
        - os_constraint: OS constraint applied
        - parameters_count: Number of parameters defined
        - creation_date: ISO datetime string
        - update_date: ISO datetime string
        - target_file_name: Always "target.py"
        - method_type: Always 5
        - origin: Always "BREACH_STUDIO"

    Raises:
        ValueError: If name or python_code is empty, timeout is less than 1,
                   os_constraint is invalid, or parameters are invalid
        requests.HTTPError: For API errors (401, 404, 500, etc.)
        Exception: For unexpected errors

    Example:
        >>> params = [{"name": "port", "value": 8080, "type": "PORT"}]
        >>> result = sb_save_studio_draft("My Attack", code, "Test", 300, "WINDOWS", params, "demo")
        >>> print(result['draft_id'])
        10000296
        >>> print(result['parameters_count'])
        1
    """
    # Validate inputs
    if not name or not name.strip():
        raise ValueError("name parameter is required and cannot be empty")
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")

    # Validate OS constraint
    _validate_os_constraint(os_constraint)

    # Validate and build parameters
    if parameters is None:
        parameters = []
    parameters_json = _validate_and_build_parameters(parameters)

    logger.info(f"Saving draft simulation '{name}' for console: {console} with OS constraint: {os_constraint}, parameters: {len(parameters)}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    # Note: Don't set Content-Type header - requests library will set it automatically
    # for multipart/form-data when files parameter is used
    headers = {"x-apitoken": apitoken}

    # Prepare multipart form data
    files = {
        'targetFile': ('target.py', python_code, 'text/x-python-script')
    }

    data = {
        'name': name,
        'timeout': str(timeout),
        'status': 'draft',
        'class': 'python',
        'description': description,
        'parameters': parameters_json,
        'tags': '[]',
        'methodType': '5',
        'targetFileName': 'target.py',
        'metaData': '{"targetFileName":"target.py"}'
    }

    # Add targetConstraints only if os_constraint is not "All"
    if os_constraint != "All":
        data['targetConstraints'] = f'{{"os":"{os_constraint}"}}'

    # Call save draft API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods"
    logger.info(f"Calling save draft API: {api_url}")

    try:
        response = requests.post(api_url, headers=headers, data=data, files=files, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Save draft API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Save draft API call failed: {e}")
        raise

    # Transform response
    result = get_draft_response_mapping(api_response)

    # Add os_constraint and parameters_count to result
    result['os_constraint'] = os_constraint
    result['parameters_count'] = len(parameters)

    # Cache the result (1-hour TTL)
    cache_key = f"studio_draft_{console}_{result['draft_id']}"
    studio_draft_cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }
    logger.debug(f"Cached draft with key: {cache_key}")

    logger.info(f"Successfully saved draft with ID: {result['draft_id']} with OS constraint: {os_constraint}, parameters: {len(parameters)}")

    return result


def sb_get_all_studio_simulations(
    console: str = "default",
    status_filter: str = "all",
    name_filter: str = None,
    user_id_filter: int = None
) -> Dict[str, Any]:
    """
    Get all Studio simulations (both draft and published) for a console.

    Args:
        console: SafeBreach console identifier (default: "default")
        status_filter: Filter by status - "all", "draft", or "published" (default: "all")
        name_filter: Filter by simulation name (case-insensitive partial match, optional)
        user_id_filter: Filter by user ID who created the simulation (optional)

    Returns:
        Dictionary containing:
        - simulations: List of all simulations
        - total_count: Total number of simulations
        - draft_count: Number of draft simulations
        - published_count: Number of published simulations

    Raises:
        ValueError: If status_filter is invalid
        Exception: For API errors

    Example:
        >>> result = sb_get_all_studio_simulations(console="demo", status_filter="draft")
        >>> print(f"Found {result['draft_count']} draft simulations")
        >>> result = sb_get_all_studio_simulations(console="demo", name_filter="MCP")
        >>> print(f"Found {result['total_count']} simulations with 'MCP' in name")
    """
    # Validate status_filter
    valid_statuses = ["all", "draft", "published"]
    if status_filter not in valid_statuses:
        raise ValueError(f"status_filter must be one of {valid_statuses}, got: {status_filter}")

    logger.info(f"Getting all Studio simulations for console: {console} (status={status_filter}, "
                f"name_filter={name_filter}, user_id_filter={user_id_filter})")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Call get all simulations API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all"
    logger.info(f"Calling get all simulations API: {api_url}")

    try:
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info(f"Get all simulations API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Get all simulations API call failed: {e}")
        raise

    # Transform response
    result = get_all_simulations_response_mapping(api_response)

    # Apply filters
    filtered_simulations = result['simulations']

    # Apply status filter if specified
    if status_filter != "all":
        filtered_simulations = [
            sim for sim in filtered_simulations
            if sim['status'] == status_filter
        ]

    # Apply name filter if specified (case-insensitive partial match)
    if name_filter:
        name_filter_lower = name_filter.lower()
        filtered_simulations = [
            sim for sim in filtered_simulations
            if name_filter_lower in sim['name'].lower()
        ]

    # Apply user ID filter if specified
    if user_id_filter is not None:
        filtered_simulations = [
            sim for sim in filtered_simulations
            if sim.get('user_created') == user_id_filter
        ]

    # Update result with filtered data
    result['simulations'] = filtered_simulations
    result['total_count'] = len(filtered_simulations)

    # Recalculate draft/published counts from filtered results
    result['draft_count'] = len([s for s in filtered_simulations if s['status'] == 'draft'])
    result['published_count'] = len([s for s in filtered_simulations if s['status'] == 'published'])

    logger.info(f"Successfully retrieved {result['total_count']} simulations "
                f"({result['draft_count']} drafts, {result['published_count']} published)")

    return result


def sb_update_studio_draft(
    draft_id: int,
    name: str,
    python_code: str,
    description: str = "",
    timeout: int = 300,
    os_constraint: str = "All",
    parameters: list = None,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Update an existing Studio draft simulation.

    Args:
        draft_id: ID of the draft to update (required)
        name: Updated simulation name (required)
        python_code: Updated Python code content (required)
        description: Updated simulation description (optional, default: "")
        timeout: Execution timeout in seconds (default: 300, min: 1)
        os_constraint: OS constraint for simulation execution (default: "All")
                      Valid values: "All" (no constraint), "WINDOWS", "LINUX", "MAC"
        parameters: Optional list of parameters accessible in system_data (default: None)
                   Each parameter is a dict with:
                   - name (required): Parameter name
                   - value (required): Parameter value (single value or list of values)
                   - type (optional): "NOT_CLASSIFIED", "PORT", "URI", or "PROTOCOL" (default: "NOT_CLASSIFIED")
                     * PROTOCOL type requires value to be one of 52 valid protocols (TCP, HTTP, SSH, etc.)
                   - display_name (optional): Display name (defaults to name)
                   - description (optional): Description (defaults to "")
                   Example single value: {"name": "port", "value": 8080}
                   Example multiple values: {"name": "paths", "value": ["file1.txt", "file2.txt"]}
        console: SafeBreach console identifier (default: "default")

    Returns:
        Updated draft metadata including draft_id, name, status, dates, os_constraint, parameters_count, etc.

    Raises:
        ValueError: If draft_id, name, python_code is invalid/empty, os_constraint is invalid,
                   or parameters are invalid
        Exception: For API errors

    Example:
        >>> params = [{"name": "port", "value": 8080, "type": "PORT"}]
        >>> result = sb_update_studio_draft(
        ...     draft_id=10000298,
        ...     name="Updated Simulation",
        ...     python_code=updated_code,
        ...     description="Updated description",
        ...     os_constraint="LINUX",
        ...     parameters=params,
        ...     console="demo"
        ... )
        >>> print(f"Updated draft {result['draft_id']} with {result['parameters_count']} parameters")
    """
    # Validate inputs
    if not draft_id or draft_id <= 0:
        raise ValueError("draft_id must be a positive integer")
    if not name or not name.strip():
        raise ValueError("name parameter is required and cannot be empty")
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")

    # Validate OS constraint
    _validate_os_constraint(os_constraint)

    # Validate and build parameters
    if parameters is None:
        parameters = []
    parameters_json = _validate_and_build_parameters(parameters)

    logger.info(f"Updating draft simulation {draft_id} '{name}' for console: {console} with OS constraint: {os_constraint}, parameters: {len(parameters)}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    # Note: Don't set Content-Type header - requests library will set it automatically
    # for multipart/form-data when files parameter is used
    headers = {"x-apitoken": apitoken}

    # Prepare multipart form data
    files = {
        'targetFile': ('target.py', python_code, 'text/x-python-script')
    }

    data = {
        'id': str(draft_id),
        'name': name,
        'timeout': str(timeout),
        'status': 'draft',
        'class': 'python',
        'description': description,
        'parameters': parameters_json,
        'tags': '[]',
        'methodType': '5',
        'targetFileName': 'target.py',
        'metaData': '{"targetFileName":"target.py"}'
    }

    # Add targetConstraints only if os_constraint is not "All"
    if os_constraint != "All":
        data['targetConstraints'] = f'{{"os":"{os_constraint}"}}'

    # Call update draft API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{draft_id}"
    logger.info(f"Calling update draft API: {api_url}")

    try:
        response = requests.put(api_url, headers=headers, data=data, files=files, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Update draft API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Update draft API call failed: {e}")
        raise

    # Transform response
    result = get_draft_response_mapping(api_response)

    # Add os_constraint and parameters_count to result
    result['os_constraint'] = os_constraint
    result['parameters_count'] = len(parameters)

    # Update cache with new values
    cache_key = f"studio_draft_{console}_{result['draft_id']}"
    studio_draft_cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }
    logger.debug(f"Updated cache with key: {cache_key}")

    logger.info(f"Successfully updated draft with ID: {result['draft_id']} with OS constraint: {os_constraint}, parameters: {len(parameters)}")

    return result


def sb_get_studio_simulation_source(
    simulation_id: int,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Get the target source code for a Studio simulation.

    Args:
        simulation_id: ID of the simulation (draft or published)
        console: SafeBreach console identifier (default: "default")

    Returns:
        Dictionary containing:
        - filename: Name of the source file (typically "target.py")
        - content: The Python source code as a string

    Raises:
        ValueError: If simulation_id is invalid
        Exception: For API errors

    Example:
        >>> result = sb_get_studio_simulation_source(simulation_id=10000298, console="demo")
        >>> print(result['filename'])
        'target.py'
        >>> print(result['content'][:100])
        '# Author: SafeBreach...'
    """
    # Validate inputs
    if not simulation_id or simulation_id <= 0:
        raise ValueError("simulation_id must be a positive integer")

    logger.info(f"Getting source code for simulation {simulation_id} on console: {console}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Call get source code API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{simulation_id}/files/target"
    logger.info(f"Calling get source code API: {api_url}")

    try:
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Get source code API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Get source code API call failed: {e}")
        raise

    # Extract data from response
    data = api_response.get('data', {})
    result = {
        'filename': data.get('filename', 'target.py'),
        'content': data.get('content', '')
    }

    logger.info(f"Successfully retrieved source code for simulation {simulation_id} "
                f"(filename: {result['filename']}, size: {len(result['content'])} bytes)")

    return result


def sb_run_studio_simulation(
    simulation_id: int,
    console: str = "default",
    simulator_ids: list = None,
    test_name: str = None
) -> Dict[str, Any]:
    """
    Run a Studio draft simulation on simulators.

    This function queues a Studio simulation for execution on either all connected
    simulators or specific simulator IDs.

    Args:
        simulation_id: ID of the draft simulation to execute
        console: SafeBreach console identifier (default: "default")
        simulator_ids: List of specific simulator UUIDs to run on (optional).
                      If None, runs on all connected simulators.
        test_name: Custom name for the test execution (optional).
                  Default: "Studio Simulation Test - {simulation_id}"

    Returns:
        Dictionary containing:
        - plan_run_id: ID of the test execution
        - step_run_id: ID of the step execution
        - test_name: Name of the test
        - simulation_id: ID of the simulation
        - simulator_count: Number of simulators targeted
        - priority: Execution priority
        - draft: Always True for draft simulations

    Raises:
        ValueError: If simulation_id is invalid or simulator_ids is empty list
        Exception: For API errors

    Example:
        >>> # Run on all connected simulators
        >>> result = sb_run_studio_simulation(simulation_id=10000298, console="demo")
        >>> print(result['plan_run_id'])
        '1764570357286.4'

        >>> # Run on specific simulators
        >>> result = sb_run_studio_simulation(
        ...     simulation_id=10000298,
        ...     console="demo",
        ...     simulator_ids=["3b6e04fb-828c-4017-84eb-0a898416f5ad", "82f32590-c51e-403a-9912-579af86fd3b9"]
        ... )
    """
    # Validate inputs
    if not simulation_id or simulation_id <= 0:
        raise ValueError("simulation_id must be a positive integer")

    if simulator_ids is not None and len(simulator_ids) == 0:
        raise ValueError("simulator_ids cannot be an empty list. Use None to run on all connected simulators")

    # Set default test name if not provided
    if not test_name:
        test_name = f"Studio Simulation Test - {simulation_id}"

    logger.info(f"Running simulation {simulation_id} on console: {console} "
                f"(simulators: {'all connected' if simulator_ids is None else len(simulator_ids)})")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')  # Use data URL for orchestration API
    account_id = get_api_account_id(console)
    headers = {
        "x-apitoken": apitoken,
        "Content-Type": "application/json"
    }

    # Build attacker and target filters
    if simulator_ids is None:
        # Run on all connected simulators
        attacker_filter = {
            "connection": {
                "operator": "is",
                "values": [True],
                "name": "connection"
            }
        }
        target_filter = {
            "connection": {
                "operator": "is",
                "values": [True],
                "name": "connection"
            }
        }
    else:
        # Run on specific simulators
        attacker_filter = {
            "simulators": {
                "operator": "is",
                "values": simulator_ids,
                "name": "simulators"
            }
        }
        target_filter = {
            "simulators": {
                "operator": "is",
                "values": simulator_ids,
                "name": "simulators"
            }
        }

    # Build request payload
    payload = {
        "plan": {
            "name": test_name,
            "steps": [{
                "attacksFilter": {
                    "playbook": {
                        "operator": "is",
                        "values": [simulation_id],
                        "name": "playbook"
                    }
                },
                "attackerFilter": attacker_filter,
                "targetFilter": target_filter,
                "systemFilter": {}
            }],
            "draft": True
        }
    }

    # Call run simulation API
    api_url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue"
    params = {
        "enableFeedbackLoop": "true",
        "retrySimulations": "false"
    }
    logger.info(f"Calling run simulation API: {api_url}")

    try:
        response = requests.post(api_url, headers=headers, params=params, json=payload, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Run simulation API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Run simulation API call failed: {e}")
        raise

    # Extract data from response
    data = api_response.get('data', {})
    steps = data.get('steps', [])
    step_data = steps[0] if steps else {}

    result = {
        'plan_run_id': data.get('planRunId', ''),
        'step_run_id': step_data.get('stepRunId', ''),
        'test_name': data.get('name', test_name),
        'simulation_id': simulation_id,
        'simulator_count': len(simulator_ids) if simulator_ids else 'all connected',
        'priority': data.get('priority', 'low'),
        'draft': data.get('draft', True),
        'ran_by': data.get('ranBy'),
        'retry_simulations': data.get('retrySimulations', False)
    }

    logger.info(f"Successfully queued simulation {simulation_id} for execution "
                f"(plan_run_id: {result['plan_run_id']}, step_run_id: {result['step_run_id']})")

    return result


def sb_get_studio_simulation_latest_result(
    simulation_id: int,
    console: str = "default",
    max_results: int = 1,
    page_size: int = 100
) -> Dict[str, Any]:
    """
    Retrieve the latest execution results for a Studio simulation by its playbook ID.

    This function queries the execution history to find the most recent runs of the specified
    Studio simulation, ordered by start time (newest first).

    Args:
        simulation_id: The playbook ID of the Studio simulation
        console: SafeBreach console identifier (default: "default")
        max_results: Maximum number of results to return (default: 1 for latest only)
        page_size: Number of results per page to request from API (default: 100)

    Returns:
        Dictionary containing:
        - executions: List of simulation execution results (most recent first)
        - total_found: Total number of executions found
        - simulation_id: The queried simulation ID
        - console: Console identifier

    Raises:
        ValueError: If simulation_id is invalid
        requests.HTTPError: If API request fails

    Example:
        # Get latest execution result
        result = sb_get_studio_simulation_latest_result(
            simulation_id=10000291,
            console="demo"
        )

        # Get last 5 execution results
        results = sb_get_studio_simulation_latest_result(
            simulation_id=10000291,
            console="demo",
            max_results=5
        )
    """
    # Validate inputs
    if not simulation_id or simulation_id <= 0:
        raise ValueError("simulation_id must be a positive integer")

    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    if page_size < 1 or page_size > 1000:
        raise ValueError("page_size must be between 1 and 1000")

    logger.info(f"Retrieving latest execution results for Studio simulation {simulation_id} from console '{console}'")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')  # Use data URL for execution history API
    account_id = get_api_account_id(console)

    headers = {
        "x-apitoken": apitoken,
        "Content-Type": "application/json"
    }

    # Build request payload with query for specific playbook ID
    payload = {
        "page": 1,
        "runId": "*",  # Wildcard for any run
        "pageSize": min(page_size, max_results),  # Only request what we need
        "query": f"Playbook_id:(\"{simulation_id}\")",  # Search for specific playbook ID
        "orderBy": "desc",  # Descending order (newest first)
        "sortBy": "startTime"  # Sort by start time
    }

    try:
        # Call execution history API
        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"

        logger.debug(f"Requesting execution history: POST {api_url}")
        logger.debug(f"Query payload: {payload}")

        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        api_response = response.json()

        # Extract simulations and total count
        simulations = api_response.get('simulations', [])
        total_found = api_response.get('total', 0)

        logger.info(f"Found {total_found} total executions for simulation {simulation_id}")

        # Limit to requested max_results
        limited_simulations = simulations[:max_results]

        # Transform each simulation to a cleaner format
        from .studio_types import get_execution_result_mapping
        transformed_executions = [
            get_execution_result_mapping(sim) for sim in limited_simulations
        ]

        result = {
            'executions': transformed_executions,
            'returned_count': len(transformed_executions),
            'total_found': total_found,
            'simulation_id': simulation_id,
            'console': console,
            'has_more': total_found > len(transformed_executions)
        }

        logger.info(f"Successfully retrieved {len(transformed_executions)} execution results for simulation {simulation_id}")

        return result

    except requests.HTTPError as e:
        error_msg = f"API error retrieving execution results for simulation {simulation_id}: {str(e)}"
        if e.response is not None:
            try:
                error_details = e.response.json()
                error_msg += f" - {error_details}"
            except:
                error_msg += f" - {e.response.text}"
        logger.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Error retrieving execution results for simulation {simulation_id} from console '{console}': {str(e)}"
        logger.error(error_msg)
        raise


def _get_draft_from_cache(cache_key: str) -> Dict[str, Any]:
    """
    Retrieve draft metadata from cache if available and not expired.

    Args:
        cache_key: Cache key for the draft

    Returns:
        Cached draft metadata or None if not found or expired
    """
    if cache_key in studio_draft_cache:
        cached_item = studio_draft_cache[cache_key]
        cache_age = time.time() - cached_item['timestamp']

        if cache_age < CACHE_TTL:
            logger.debug(f"Cache hit for key: {cache_key} (age: {cache_age:.1f}s)")
            return cached_item['data']
        else:
            # Cache expired, remove it
            logger.debug(f"Cache expired for key: {cache_key} (age: {cache_age:.1f}s)")
            del studio_draft_cache[cache_key]

    logger.debug(f"Cache miss for key: {cache_key}")
    return None
