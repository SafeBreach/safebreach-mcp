"""
Business logic functions for Studio MCP Server.

This module provides the core functionality for validating custom Python attack
code and managing attack drafts in SafeBreach Breach Studio.
"""

import re
import ast
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
    get_all_attacks_response_mapping,
    paginate_studio_attacks,
    PAGE_SIZE
)
from .studio_templates import (
    get_target_template,
    get_attacker_template,
    get_parameters_template_json,
    get_attack_type_description,
    is_dual_script_type,
    TEMPLATE_VERSION,
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

# Valid attack types with their methodType codes
VALID_ATTACK_TYPES = {
    "host": 5, "exfil": 0, "infil": 2, "lateral": 1,
}

# Common aliases for attack types (maps alias → canonical key)
ATTACK_TYPE_ALIASES = {
    "exfiltration": "exfil",
    "infiltration": "infil",
    "lateral_movement": "lateral",
    "lateral-movement": "lateral",
    "host-level": "host",
    "host_level": "host",
}

# Attack types that require both target and attacker scripts
DUAL_SCRIPT_TYPES = {"exfil", "infil", "lateral"}

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


def _normalize_attack_type(attack_type: str) -> str:
    """
    Normalize attack_type to canonical lowercase key, accepting aliases.

    Case-insensitive matching: "Host" → "host", "EXFIL" → "exfil".
    Alias resolution: "exfiltration" → "exfil", "lateral_movement" → "lateral".

    Args:
        attack_type: Attack type string to normalize

    Returns:
        Canonical lowercase attack type key

    Raises:
        ValueError: If attack_type is not a valid type or alias
    """
    lowered = attack_type.lower()

    # Direct match against canonical keys
    if lowered in VALID_ATTACK_TYPES:
        return lowered

    # Check aliases
    if lowered in ATTACK_TYPE_ALIASES:
        return ATTACK_TYPE_ALIASES[lowered]

    valid_values = sorted(VALID_ATTACK_TYPES.keys())
    valid_aliases = sorted(ATTACK_TYPE_ALIASES.keys())
    raise ValueError(
        f"attack_type must be one of {valid_values}, got: '{attack_type}'. "
        f"Also accepts aliases: {valid_aliases}"
    )


def _validate_os_constraint(os_constraint: str) -> str:
    """
    Validate and normalize OS constraint to canonical case.

    Case-insensitive matching: "windows" → "WINDOWS", "all" → "All".

    Args:
        os_constraint: OS constraint value to validate

    Returns:
        Canonical case OS constraint value

    Raises:
        ValueError: If os_constraint is not one of the valid values
    """
    # Build case-insensitive lookup
    os_lookup = {v.lower(): v for v in VALID_OS_CONSTRAINTS}
    canonical = os_lookup.get(os_constraint.lower())

    if canonical is None:
        raise ValueError(
            f"os_constraint must be one of {VALID_OS_CONSTRAINTS}, got: '{os_constraint}'"
        )

    return canonical


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


def _lint_check_parameters(parameters: list) -> list:
    """
    Run SB011/SB012 lint checks on parameter definitions.

    Args:
        parameters: List of parameter dictionaries with 'name' field

    Returns:
        List of lint warning dictionaries with 'code', 'message', and 'parameter' fields
    """
    warnings = []

    # SB011: Check parameter names are valid Python identifiers
    for param in parameters:
        name = param.get("name", "")
        if name and not name.isidentifier():
            warnings.append({
                "code": "SB011",
                "message": f"Parameter name '{name}' is not a valid Python identifier. "
                          f"Use names like 'my_param' instead of '{name}'.",
                "parameter": name
            })

    # SB012: Check for duplicate parameter names (case-sensitive)
    seen_names = set()
    for param in parameters:
        name = param.get("name", "")
        if name in seen_names:
            warnings.append({
                "code": "SB012",
                "message": f"Duplicate parameter name '{name}'.",
                "parameter": name
            })
        seen_names.add(name)

    return warnings


def _validate_main_signature_ast(code: str, label: str) -> Dict[str, Any]:
    """
    AST-based validation of main function signature.

    Parses code and verifies that a function named 'main' exists with exactly
    the parameters: (system_data, asset, proxy, *args, **kwargs).

    Args:
        code: Python source code to validate
        label: Human-readable label for error messages (e.g., "target", "attacker")

    Returns:
        Dictionary with:
        - has_main_function: Whether a valid main() exists
        - signature_errors: List of signature error strings (empty if valid)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Syntax errors are handled separately; just report no main found
        return {"has_main_function": False, "signature_errors": []}

    # Find top-level 'def main(...)' (not async def)
    main_func = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_func = node
            break

    if main_func is None:
        return {"has_main_function": False, "signature_errors": []}

    # Validate signature
    errors = []
    args_node = main_func.args

    # Check positional args: exactly [system_data, asset, proxy]
    positional_names = [arg.arg for arg in args_node.args]
    expected_positional = ["system_data", "asset", "proxy"]
    if positional_names != expected_positional:
        errors.append(
            f"{label} main() positional parameters must be {expected_positional}, "
            f"got {positional_names}"
        )

    # Check *args
    if args_node.vararg is None:
        errors.append(f"{label} main() must have *args parameter")
    elif args_node.vararg.arg != "args":
        errors.append(
            f"{label} main() vararg must be named 'args', got '{args_node.vararg.arg}'"
        )

    # Check **kwargs
    if args_node.kwarg is None:
        errors.append(f"{label} main() must have **kwargs parameter")
    elif args_node.kwarg.arg != "kwargs":
        errors.append(
            f"{label} main() kwarg must be named 'kwargs', got '{args_node.kwarg.arg}'"
        )

    has_main = len(errors) == 0
    return {"has_main_function": has_main, "signature_errors": errors}


def _validate_code_locally(code: str, label: str) -> Dict[str, Any]:
    """
    Perform local validation checks on Python code (main function + syntax).

    Uses AST-based validation for main() signature verification and compile()
    for syntax checking.

    Args:
        code: Python source code to validate
        label: Human-readable label for error messages (e.g., "target", "attacker")

    Returns:
        Dictionary with 'has_main_function', 'syntax_error', and 'signature_errors' fields
    """
    # AST-based main function signature validation
    ast_result = _validate_main_signature_ast(code, label)
    has_main = ast_result["has_main_function"]
    signature_errors = ast_result["signature_errors"]

    syntax_error = None
    try:
        compile(code, f"<{label}>", "exec")
    except SyntaxError as e:
        syntax_error = f"{label} code syntax error at line {e.lineno}: {e.msg}"

    return {
        "has_main_function": has_main,
        "syntax_error": syntax_error,
        "signature_errors": signature_errors,
    }


def _call_validation_api(
    code: str,
    filename: str,
    api_url: str,
    headers: dict,
) -> Dict[str, Any]:
    """
    Call the SafeBreach validation API for a single code file.

    Args:
        code: Python source code to validate
        filename: Filename to use in the multipart upload
        api_url: Full API URL
        headers: Request headers

    Returns:
        Transformed validation result from API
    """
    files = {'file': (filename, code, 'text/x-python-script')}
    data = {'class': 'python'}

    response = requests.put(api_url, headers=headers, data=data, files=files, timeout=120)
    response.raise_for_status()
    api_response = response.json()
    return get_validation_response_mapping(api_response)


def sb_validate_studio_code(
    python_code: str,
    console: str = "default",
    attack_type: str = "host",
    attacker_code: str = None,
    target_os: str = "All",
    attacker_os: str = "All",
    parameters: list = None,
) -> Dict[str, Any]:
    """
    Validate custom Python attack code against Breach Studio requirements.

    Performs two-tier validation:
    - Tier 1 (local): attack type, main() signature, syntax check, SB011/SB012 lint
    - Tier 2 (API): backend code validation for target and attacker scripts

    Args:
        python_code: The target Python code content to validate
        console: SafeBreach console identifier (default: "default")
        attack_type: Attack type - "host", "exfil", "infil", or "lateral" (default: "host")
        attacker_code: Python code for attacker script (required for dual-script types)
        target_os: OS constraint for target script (default: "All")
        attacker_os: OS constraint for attacker script (default: "All", dual-script only)
        parameters: Optional list of parameter dicts to validate (SB011/SB012 lint)

    Returns:
        Validation result dictionary containing:
        - is_valid: Overall validation status (both tiers)
        - exit_code: Exit code from target validator
        - has_main_function: Whether target code has required main() signature
        - validation_errors: Combined list of validation errors
        - target_validation: Target-specific API validation results
        - attacker_validation: Attacker-specific API validation results (None for host)
        - lint_warnings: List of SB011/SB012 lint warnings
        - stderr: Standard error output from target validation
        - stdout: Standard output details from target validation

    Raises:
        ValueError: If inputs are invalid (empty code, bad attack_type, missing attacker_code)
        requests.HTTPError: For API errors (401, 404, 500, etc.)
    """
    # --- Tier 1: Local validation ---

    # Validate basic input
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")

    # Normalize and validate attack type
    attack_type = _normalize_attack_type(attack_type)

    # Validate and normalize OS constraints
    target_os = _validate_os_constraint(target_os)
    if attack_type in DUAL_SCRIPT_TYPES:
        attacker_os = _validate_os_constraint(attacker_os)

    # Validate dual-script requirement
    is_dual_script = attack_type in DUAL_SCRIPT_TYPES
    if is_dual_script and (not attacker_code or not attacker_code.strip()):
        raise ValueError(
            f"attacker_code is required for '{attack_type}' attack type (dual-script)"
        )

    logger.info(f"Validating {attack_type} attack code for console: {console}")

    # Local checks on target code
    target_local = _validate_code_locally(python_code, "target")
    has_main_function = target_local["has_main_function"]

    # Local checks on attacker code (dual-script only)
    attacker_local = None
    if is_dual_script:
        attacker_local = _validate_code_locally(attacker_code, "attacker")

    # Collect local errors (syntax + signature) as validation errors
    local_errors = []
    if target_local["syntax_error"]:
        local_errors.append(target_local["syntax_error"])
    local_errors.extend(target_local.get("signature_errors", []))
    if attacker_local and attacker_local["syntax_error"]:
        local_errors.append(attacker_local["syntax_error"])
    if attacker_local:
        local_errors.extend(attacker_local.get("signature_errors", []))

    # SB011/SB012 lint checks on parameters
    lint_warnings = []
    if parameters:
        _validate_and_build_parameters(parameters)  # structural validation
        lint_warnings = _lint_check_parameters(parameters)

    # --- Tier 2: API validation ---

    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/validate"

    logger.info(f"Calling validation API: {api_url}")

    try:
        # Validate target code
        target_validation = _call_validation_api(python_code, "target.py", api_url, headers)

        # Validate attacker code for dual-script types
        attacker_validation = None
        if is_dual_script:
            attacker_validation = _call_validation_api(attacker_code, "attacker.py", api_url, headers)

    except requests.exceptions.RequestException as e:
        logger.error(f"Validation API call failed: {e}")
        raise

    # --- Merge results ---

    # Combine validation errors from all sources
    all_errors = local_errors + target_validation.get('validation_errors', [])
    if attacker_validation:
        all_errors += attacker_validation.get('validation_errors', [])

    # Overall validity: no local errors AND target valid AND attacker valid (if applicable)
    is_valid = (
        not local_errors
        and target_validation.get('is_valid', False)
        and (attacker_validation is None or attacker_validation.get('is_valid', False))
    )

    result = {
        "is_valid": is_valid,
        "exit_code": target_validation.get('exit_code', -1),
        "has_main_function": has_main_function,
        "validation_errors": all_errors,
        "target_validation": target_validation,
        "attacker_validation": attacker_validation,
        "lint_warnings": lint_warnings,
        "stderr": target_validation.get('stderr', ''),
        "stdout": target_validation.get('stdout', {}),
    }

    logger.debug(f"Validation result: is_valid={is_valid}, "
                 f"has_main_function={has_main_function}, "
                 f"exit_code={result['exit_code']}")

    return result


def sb_save_studio_attack_draft(
    name: str,
    python_code: str,
    description: str = "",
    timeout: int = 300,
    target_os: str = "All",
    parameters: list = None,
    console: str = "default",
    attack_type: str = "host",
    attacker_code: str = None,
    attacker_os: str = "All",
) -> Dict[str, Any]:
    """
    Save a custom Python attack as a draft in Breach Studio.

    Args:
        name: Attack name (e.g., "Port Scanner")
        python_code: The target Python code content
        description: Attack description (optional, default: "")
        timeout: Execution timeout in seconds (default: 300, min: 1)
        target_os: OS constraint for target script (default: "All")
                   Valid values: "All", "WINDOWS", "LINUX", "MAC"
        parameters: Optional list of parameter dicts (default: None)
        console: SafeBreach console identifier (default: "default")
        attack_type: Attack type - "host", "exfil", "infil", or "lateral" (default: "host")
        attacker_code: Python code for attacker script (required for dual-script types)
        attacker_os: OS constraint for attacker script (default: "All", dual-script only)

    Returns:
        Draft metadata dictionary with draft_id, name, status, attack_type, etc.

    Raises:
        ValueError: If inputs are invalid
        requests.HTTPError: For API errors
    """
    # Validate inputs
    if not name or not name.strip():
        raise ValueError("name parameter is required and cannot be empty")
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")

    # Normalize and validate attack type
    attack_type = _normalize_attack_type(attack_type)

    # Validate and normalize OS constraints
    target_os = _validate_os_constraint(target_os)

    # Validate dual-script requirements
    is_dual_script = attack_type in DUAL_SCRIPT_TYPES
    if is_dual_script:
        if not attacker_code or not attacker_code.strip():
            raise ValueError(
                f"attacker_code is required for '{attack_type}' attack type (dual-script)"
            )
        attacker_os = _validate_os_constraint(attacker_os)

    # Validate and build parameters
    if parameters is None:
        parameters = []
    parameters_json = _validate_and_build_parameters(parameters)

    method_type = VALID_ATTACK_TYPES[attack_type]

    logger.info(f"Saving draft attack '{name}' (type={attack_type}) for console: {console}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Prepare multipart form data
    files = {
        'targetFile': ('target.py', python_code, 'text/x-python-script')
    }
    if is_dual_script:
        files['attackerFile'] = ('attacker.py', attacker_code, 'text/x-python-script')

    # Build metadata
    meta_data = {"targetFileName": "target.py"}
    if is_dual_script:
        meta_data["attackerFileName"] = "attacker.py"

    data = {
        'name': name,
        'timeout': str(timeout),
        'status': 'draft',
        'class': 'python',
        'description': description,
        'parameters': parameters_json,
        'tags': '[]',
        'methodType': str(method_type),
        'targetFileName': 'target.py',
        'metaData': json.dumps(meta_data)
    }

    # Add targetConstraints
    if target_os != "All":
        data['targetConstraints'] = json.dumps({"os": target_os})

    # Add attackerConstraints for dual-script
    if is_dual_script and attacker_os != "All":
        data['attackerConstraints'] = json.dumps({"os": attacker_os})

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

    # Add supplementary fields
    result['os_constraint'] = target_os
    result['parameters_count'] = len(parameters)

    # Cache the result (1-hour TTL)
    cache_key = f"studio_draft_{console}_{result['draft_id']}"
    studio_draft_cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }
    logger.debug(f"Cached draft with key: {cache_key}")

    logger.info(f"Successfully saved draft with ID: {result['draft_id']}")

    return result


def sb_get_all_studio_attacks(
    console: str = "default",
    status_filter: str = "all",
    name_filter: str = None,
    user_id_filter: int = None,
    page_number: int = 0,
) -> Dict[str, Any]:
    """
    Get all Studio attacks (both draft and published) for a console, with pagination.

    Args:
        console: SafeBreach console identifier (default: "default")
        status_filter: Filter by status - "all", "draft", or "published" (default: "all")
        name_filter: Filter by attack name (case-insensitive partial match, optional)
        user_id_filter: Filter by user ID who created the attack (optional)
        page_number: Zero-based page index (default: 0)

    Returns:
        Dictionary containing:
        - attacks_in_page: List of attacks for the current page
        - total_attacks: Total number of filtered attacks
        - page_number: Current page number
        - total_pages: Total number of pages
        - draft_count: Number of draft attacks (in filtered set)
        - published_count: Number of published attacks (in filtered set)
        - applied_filters: Dict of active filters
        - hint_to_agent: Navigation hint or None

    Raises:
        ValueError: If status_filter is invalid or page_number is negative
        Exception: For API errors
    """
    # Validate status_filter
    valid_statuses = ["all", "draft", "published"]
    if status_filter not in valid_statuses:
        raise ValueError(f"status_filter must be one of {valid_statuses}, got: {status_filter}")

    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")

    logger.info(f"Getting all Studio attacks for console: {console} (status={status_filter}, "
                f"name_filter={name_filter}, user_id_filter={user_id_filter}, page={page_number})")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Call get all attacks API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all"
    logger.info(f"Calling get all attacks API: {api_url}")

    try:
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Get all attacks API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Get all attacks API call failed: {e}")
        raise

    # Transform response
    result = get_all_attacks_response_mapping(api_response)

    # Apply filters
    filtered_attacks = result['attacks']

    # Apply status filter if specified
    if status_filter != "all":
        filtered_attacks = [
            a for a in filtered_attacks
            if a['status'] == status_filter
        ]

    # Apply name filter if specified (case-insensitive partial match)
    if name_filter:
        name_filter_lower = name_filter.lower()
        filtered_attacks = [
            a for a in filtered_attacks
            if name_filter_lower in a['name'].lower()
        ]

    # Apply user ID filter if specified
    if user_id_filter is not None:
        filtered_attacks = [
            a for a in filtered_attacks
            if a.get('user_created') == user_id_filter
        ]

    # Calculate draft/published counts from filtered results
    draft_count = len([a for a in filtered_attacks if a['status'] == 'draft'])
    published_count = len([a for a in filtered_attacks if a['status'] == 'published'])

    # Paginate the filtered results
    paginated = paginate_studio_attacks(filtered_attacks, page_number)

    # Add supplementary fields
    paginated['draft_count'] = draft_count
    paginated['published_count'] = published_count
    paginated['applied_filters'] = {
        'status_filter': status_filter if status_filter != "all" else None,
        'name_filter': name_filter,
        'user_filter': user_id_filter,
    }

    logger.info(f"Successfully retrieved {paginated['total_attacks']} attacks "
                f"({draft_count} drafts, {published_count} published), "
                f"page {page_number}/{paginated['total_pages']}")

    return paginated


def sb_update_studio_attack_draft(
    attack_id: int,
    name: str,
    python_code: str,
    description: str = "",
    timeout: int = 300,
    target_os: str = "All",
    parameters: list = None,
    console: str = "default",
    attack_type: str = "host",
    attacker_code: str = None,
    attacker_os: str = "All",
) -> Dict[str, Any]:
    """
    Update an existing Studio draft attack.

    Args:
        attack_id: ID of the draft attack to update (required)
        name: Updated attack name (required)
        python_code: Updated target Python code content (required)
        description: Updated attack description (optional, default: "")
        timeout: Execution timeout in seconds (default: 300, min: 1)
        target_os: OS constraint for target script (default: "All")
                   Valid values: "All", "WINDOWS", "LINUX", "MAC"
        parameters: Optional list of parameter dicts (default: None)
        console: SafeBreach console identifier (default: "default")
        attack_type: Attack type - "host", "exfil", "infil", or "lateral" (default: "host")
        attacker_code: Python code for attacker script (required for dual-script types)
        attacker_os: OS constraint for attacker script (default: "All", dual-script only)

    Returns:
        Updated draft metadata including draft_id, name, status, attack_type, dates, etc.

    Raises:
        ValueError: If inputs are invalid
        requests.HTTPError: For API errors
    """
    # Validate inputs
    if not attack_id or attack_id <= 0:
        raise ValueError("attack_id must be a positive integer")
    if not name or not name.strip():
        raise ValueError("name parameter is required and cannot be empty")
    if not python_code or not python_code.strip():
        raise ValueError("python_code parameter is required and cannot be empty")
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")

    # Normalize and validate attack type
    attack_type = _normalize_attack_type(attack_type)

    # Validate and normalize OS constraints
    target_os = _validate_os_constraint(target_os)

    # Validate dual-script requirements
    is_dual_script = attack_type in DUAL_SCRIPT_TYPES
    if is_dual_script:
        if not attacker_code or not attacker_code.strip():
            raise ValueError(
                f"attacker_code is required for '{attack_type}' attack type (dual-script)"
            )
        attacker_os = _validate_os_constraint(attacker_os)

    # Validate and build parameters
    if parameters is None:
        parameters = []
    parameters_json = _validate_and_build_parameters(parameters)

    method_type = VALID_ATTACK_TYPES[attack_type]

    logger.info(f"Updating draft attack {attack_id} '{name}' (type={attack_type}) for console: {console}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Prepare multipart form data
    files = {
        'targetFile': ('target.py', python_code, 'text/x-python-script')
    }
    if is_dual_script:
        files['attackerFile'] = ('attacker.py', attacker_code, 'text/x-python-script')

    # Build metadata
    meta_data = {"targetFileName": "target.py"}
    if is_dual_script:
        meta_data["attackerFileName"] = "attacker.py"

    data = {
        'id': str(attack_id),
        'name': name,
        'timeout': str(timeout),
        'status': 'draft',
        'class': 'python',
        'description': description,
        'parameters': parameters_json,
        'tags': '[]',
        'methodType': str(method_type),
        'targetFileName': 'target.py',
        'metaData': json.dumps(meta_data)
    }

    # Add targetConstraints
    if target_os != "All":
        data['targetConstraints'] = json.dumps({"os": target_os})

    # Add attackerConstraints for dual-script
    if is_dual_script and attacker_os != "All":
        data['attackerConstraints'] = json.dumps({"os": attacker_os})

    # Call update draft API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}"
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

    # Add supplementary fields
    result['os_constraint'] = target_os
    result['parameters_count'] = len(parameters)

    # Update cache with new values
    cache_key = f"studio_draft_{console}_{result['draft_id']}"
    studio_draft_cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }
    logger.debug(f"Updated cache with key: {cache_key}")

    logger.info(f"Successfully updated draft with ID: {result['draft_id']}")

    return result


def sb_get_studio_attack_source(
    attack_id: int,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Get the source code for a Studio attack (target and optionally attacker).

    Args:
        attack_id: ID of the attack (draft or published)
        console: SafeBreach console identifier (default: "default")

    Returns:
        Dictionary containing:
        - attack_id: The attack ID
        - target: {"filename": "target.py", "content": "..."} — always present
        - attacker: {"filename": "attacker.py", "content": "..."} or None

    Raises:
        ValueError: If attack_id is invalid
        Exception: For API errors (target fetch)
    """
    # Validate inputs
    if not attack_id or attack_id <= 0:
        raise ValueError("attack_id must be a positive integer")

    logger.info(f"Getting source code for attack {attack_id} on console: {console}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Fetch target source code (always required)
    target_api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}/files/target"
    logger.info(f"Calling get target source API: {target_api_url}")

    try:
        response = requests.get(target_api_url, headers=headers, timeout=120)
        response.raise_for_status()
        target_response = response.json()
        logger.info("Get target source API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Get target source API call failed: {e}")
        raise

    target_data = target_response.get('data', {})
    target_result = {
        'filename': target_data.get('filename', 'target.py'),
        'content': target_data.get('content', '')
    }

    # Fetch attacker source code (may not exist for host attacks)
    attacker_result = None
    attacker_api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}/files/attacker"
    logger.info(f"Calling get attacker source API: {attacker_api_url}")

    try:
        attacker_response = requests.get(attacker_api_url, headers=headers, timeout=120)
        if attacker_response.status_code == 200:
            attacker_data = attacker_response.json().get('data', {})
            attacker_content = attacker_data.get('content', '')
            if attacker_content:
                attacker_result = {
                    'filename': attacker_data.get('filename', 'attacker.py'),
                    'content': attacker_content
                }
                logger.info("Get attacker source API call successful")
            else:
                logger.info("Attacker file exists but is empty — treating as host attack")
        elif attacker_response.status_code == 404:
            logger.info("No attacker file found (host attack)")
        else:
            logger.warning(f"Unexpected status {attacker_response.status_code} fetching attacker file")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch attacker source (non-fatal): {e}")

    result = {
        'attack_id': attack_id,
        'target': target_result,
        'attacker': attacker_result,
    }

    logger.info(f"Successfully retrieved source code for attack {attack_id} "
                f"(target: {len(target_result['content'])} bytes, "
                f"attacker: {len(attacker_result['content']) if attacker_result else 0} bytes)")

    return result


def sb_run_studio_attack(
    attack_id: int,
    console: str = "default",
    target_simulator_ids: list = None,
    attacker_simulator_ids: list = None,
    all_connected: bool = False,
    test_name: str = None,
) -> Dict[str, Any]:
    """
    Run a Studio draft attack on simulators.

    Args:
        attack_id: ID of the draft attack to execute
        console: SafeBreach console identifier (default: "default")
        target_simulator_ids: List of target simulator UUIDs (for explicit selection)
        attacker_simulator_ids: List of attacker simulator UUIDs (network attacks only)
        all_connected: If True, run on all connected simulators (overrides simulator IDs)
        test_name: Custom name for the test execution (optional)

    Returns:
        Dictionary containing test_id, attack_id, test_name, status, etc.

    Raises:
        ValueError: If inputs are invalid
        Exception: For API errors
    """
    # Validate inputs
    if not attack_id or attack_id <= 0:
        raise ValueError("attack_id must be a positive integer")

    if not all_connected and target_simulator_ids is None:
        raise ValueError(
            "Either target_simulator_ids must be provided or all_connected must be True"
        )

    if not all_connected and target_simulator_ids is not None and len(target_simulator_ids) == 0:
        raise ValueError("target_simulator_ids cannot be an empty list")

    if not all_connected and attacker_simulator_ids is not None and len(attacker_simulator_ids) == 0:
        raise ValueError("attacker_simulator_ids cannot be an empty list")

    # Set default test name if not provided
    if not test_name:
        test_name = f"Studio Attack Test - {attack_id}"

    logger.info(f"Running attack {attack_id} on console: {console} "
                f"(all_connected={all_connected}, "
                f"targets={len(target_simulator_ids) if target_simulator_ids else 'N/A'}, "
                f"attackers={len(attacker_simulator_ids) if attacker_simulator_ids else 'N/A'})")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    headers = {
        "x-apitoken": apitoken,
        "Content-Type": "application/json"
    }

    # Build attacker and target filters
    if all_connected:
        connection_filter = {
            "connection": {
                "operator": "is",
                "values": [True],
                "name": "connection"
            }
        }
        attacker_filter = connection_filter
        target_filter = connection_filter
    else:
        # Target filter from target_simulator_ids
        target_filter = {
            "simulators": {
                "operator": "is",
                "values": target_simulator_ids,
                "name": "simulators"
            }
        }
        # Attacker filter: use attacker_simulator_ids if provided, else same as target
        # (host attacks: attacker=target, so use target IDs for both)
        attacker_ids = attacker_simulator_ids if attacker_simulator_ids else target_simulator_ids
        attacker_filter = {
            "simulators": {
                "operator": "is",
                "values": attacker_ids,
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
                        "values": [attack_id],
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

    # Call run attack API
    api_url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue"
    params = {
        "enableFeedbackLoop": "true",
        "retrySimulations": "false"
    }
    logger.info(f"Calling run attack API: {api_url}")

    try:
        response = requests.post(api_url, headers=headers, params=params, json=payload, timeout=120)
        response.raise_for_status()
        api_response = response.json()
        logger.info("Run attack API call successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"Run attack API call failed: {e}")
        raise

    # Extract data from response
    data = api_response.get('data', {})
    steps = data.get('steps', [])
    step_data = steps[0] if steps else {}

    result = {
        'test_id': data.get('planRunId', ''),
        'step_run_id': step_data.get('stepRunId', ''),
        'test_name': data.get('name', test_name),
        'attack_id': attack_id,
        'status': 'queued',
    }

    logger.info(f"Successfully queued attack {attack_id} for execution "
                f"(test_id: {result['test_id']}, step_run_id: {result['step_run_id']})")

    return result


def sb_get_studio_attack_latest_result(
    attack_id: int,
    console: str = "default",
    max_results: int = 1,
    page_size: int = 100,
    include_logs: bool = True,
    test_id: str = None,
) -> Dict[str, Any]:
    """
    Retrieve the latest execution results for a Studio attack by its playbook ID.

    This function queries the execution history to find the most recent runs of the specified
    Studio attack, ordered by start time (newest first).

    Args:
        attack_id: The playbook ID of the Studio attack
        console: SafeBreach console identifier (default: "default")
        max_results: Maximum number of results to return (default: 1 for latest only)
        page_size: Number of results per page to request from API (default: 100)
        include_logs: Whether to include simulation_steps, logs, and output fields (default: True)
        test_id: Optional test ID (planRunId) to filter results to a specific test run

    Returns:
        Dictionary containing:
        - executions: List of attack execution results (most recent first)
        - total_found: Total number of executions found
        - attack_id: The queried attack ID
        - console: Console identifier

    Raises:
        ValueError: If attack_id is invalid
        requests.HTTPError: If API request fails

    Example:
        # Get latest execution result
        result = sb_get_studio_attack_latest_result(
            attack_id=10000291,
            console="demo"
        )

        # Get last 5 execution results
        results = sb_get_studio_attack_latest_result(
            attack_id=10000291,
            console="demo",
            max_results=5
        )
    """
    # Validate inputs
    if not attack_id or attack_id <= 0:
        raise ValueError("attack_id must be a positive integer")

    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    if page_size < 1 or page_size > 1000:
        raise ValueError("page_size must be between 1 and 1000")

    logger.info(f"Retrieving latest execution results for Studio attack {attack_id} from console '{console}'")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')  # Use data URL for execution history API
    account_id = get_api_account_id(console)

    headers = {
        "x-apitoken": apitoken,
        "Content-Type": "application/json"
    }

    # Build query string for specific playbook ID, optionally filtered by test_id
    query = f"Playbook_id:(\"{attack_id}\")"
    if test_id:
        query += f" AND runId:{test_id}"

    # Build request payload
    payload = {
        "page": 1,
        "runId": "*",  # Wildcard for any run
        "pageSize": min(page_size, max_results),  # Only request what we need
        "query": query,
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

        logger.info(f"Found {total_found} total executions for attack {attack_id}")

        # Limit to requested max_results
        limited_simulations = simulations[:max_results]

        # Transform each simulation to a cleaner format
        from .studio_types import get_execution_result_mapping
        transformed_executions = [
            get_execution_result_mapping(sim) for sim in limited_simulations
        ]

        # Strip debug fields if include_logs is False
        if not include_logs:
            for exec_result in transformed_executions:
                exec_result.pop('simulation_steps', None)
                exec_result.pop('logs', None)
                exec_result.pop('output', None)

        result = {
            'executions': transformed_executions,
            'returned_count': len(transformed_executions),
            'total_found': total_found,
            'attack_id': attack_id,
            'console': console,
            'has_more': total_found > len(transformed_executions)
        }

        logger.info(f"Successfully retrieved {len(transformed_executions)} execution results for attack {attack_id}")

        return result

    except requests.HTTPError as e:
        error_msg = f"API error retrieving execution results for attack {attack_id}: {str(e)}"
        if e.response is not None:
            try:
                error_details = e.response.json()
                error_msg += f" - {error_details}"
            except:
                error_msg += f" - {e.response.text}"
        logger.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Error retrieving execution results for attack {attack_id} from console '{console}': {str(e)}"
        logger.error(error_msg)
        raise


def sb_get_studio_attack_boilerplate(
    attack_type: str = "host",
) -> Dict[str, Any]:
    """
    Get boilerplate code and parameters for a new custom attack.

    Returns ready-to-use template code, default parameters JSON, and metadata
    for the specified attack type. No API calls are made — all data is local.

    Args:
        attack_type: Attack type - "host", "exfil", "infil", or "lateral" (default: "host")

    Returns:
        Dictionary containing:
        - attack_type: The requested attack type
        - is_dual_script: Whether this type requires target + attacker scripts
        - description: Human-readable description of the attack type
        - target_code: Template Python code for target.py
        - attacker_code: Template Python code for attacker.py (None for host)
        - parameters_json: Default parameters.json content as formatted JSON string
        - files_needed: List of filenames needed (["target.py"] or ["target.py", "attacker.py"])
        - template_version: Version of the template set
        - next_steps: List of suggested next steps for the agent

    Raises:
        ValueError: If attack_type is not valid
    """
    attack_type = _normalize_attack_type(attack_type)

    dual_script = is_dual_script_type(attack_type)
    target_code = get_target_template(attack_type)
    attacker_code = get_attacker_template(attack_type) if dual_script else None
    parameters_json = get_parameters_template_json(attack_type)
    description = get_attack_type_description(attack_type)

    files_needed = ["target.py", "attacker.py"] if dual_script else ["target.py"]

    next_steps = [
        "Customize the target code to implement your attack logic",
    ]
    if dual_script:
        next_steps.append("Customize the attacker code for the network-side logic")
    next_steps.extend([
        "Modify parameters_json to define your attack parameters",
        "Use validate_studio_code to check your code before saving",
        "Use save_studio_attack_draft to save the attack to Breach Studio",
    ])

    logger.info(f"Returning boilerplate for attack type: {attack_type}")

    return {
        "attack_type": attack_type,
        "is_dual_script": dual_script,
        "description": description,
        "target_code": target_code,
        "attacker_code": attacker_code,
        "parameters_json": parameters_json,
        "files_needed": files_needed,
        "template_version": TEMPLATE_VERSION,
        "next_steps": next_steps,
    }


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


def sb_set_studio_attack_status(
    attack_id: int, new_status: str, console: str = "default"
) -> Dict[str, Any]:
    """
    Publish or unpublish a Studio attack (transition between DRAFT and PUBLISHED).

    Args:
        attack_id: ID of the attack to change status for (must be positive)
        new_status: Target status - "draft" or "published" (case-insensitive)
        console: SafeBreach console identifier (default: "default")

    Returns:
        Dictionary containing:
        - attack_id: The attack ID
        - attack_name: Name of the attack
        - old_status: Previous status
        - new_status: New status after transition
        - implications: Description of what the status change means

    Raises:
        ValueError: If attack_id is invalid, new_status is invalid, attack not found,
                    or attack is already in the target status
        Exception: For API errors
    """
    # Validate attack_id
    if not isinstance(attack_id, int) or attack_id <= 0:
        raise ValueError(f"attack_id must be a positive integer, got: {attack_id}")

    # Normalize and validate new_status
    new_status = new_status.lower().strip()
    valid_statuses = ["draft", "published"]
    if new_status not in valid_statuses:
        raise ValueError(
            f"new_status must be one of {valid_statuses}, got: '{new_status}'"
        )

    logger.info(f"Setting attack {attack_id} status to '{new_status}' on console: {console}")

    # Get authentication and base URL
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {"x-apitoken": apitoken}

    # Pre-check: get current status via list API
    list_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all"
    logger.info(f"Pre-checking attack status via: {list_url}")

    try:
        list_response = requests.get(list_url, headers=headers, timeout=120)
        list_response.raise_for_status()
        api_response = list_response.json()
        # API returns {"data": [...]} wrapper
        all_attacks = api_response.get("data", api_response) if isinstance(api_response, dict) else api_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to list attacks for pre-check: {e}")
        raise

    # Find the attack in the list
    current_attack = None
    for attack in all_attacks:
        if attack.get("id") == attack_id:
            current_attack = attack
            break

    if current_attack is None:
        raise ValueError(f"Attack with ID {attack_id} not found on console '{console}'")

    attack_name = current_attack.get("name", "Unknown")
    current_status = current_attack.get("status", "").lower()

    # Check if already in target status
    if current_status == new_status:
        raise ValueError(
            f"Attack {attack_id} ('{attack_name}') is already {new_status}"
        )

    old_status = current_status

    # Fetch source code files needed for the PUT payload
    # Target file (always required)
    target_url = (
        f"{base_url}/api/content/v1/accounts/{account_id}"
        f"/customMethods/{attack_id}/files/target"
    )
    logger.info(f"Fetching target source for status update: {target_url}")

    try:
        target_response = requests.get(target_url, headers=headers, timeout=120)
        target_response.raise_for_status()
        target_data = target_response.json().get('data', {})
        target_content = target_data.get('content', '')
        target_filename = target_data.get('filename', 'target.py')
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch target source for status update: {e}")
        raise

    # Attacker file (optional, for dual-script attack types)
    method_type = current_attack.get("methodType", 5)
    dual_script_method_types = {0, 1, 2}  # exfil, lateral, infil
    attacker_content = None
    attacker_filename = None

    if method_type in dual_script_method_types:
        attacker_url = (
            f"{base_url}/api/content/v1/accounts/{account_id}"
            f"/customMethods/{attack_id}/files/attacker"
        )
        logger.info(f"Fetching attacker source for dual-script attack: {attacker_url}")
        try:
            attacker_resp = requests.get(attacker_url, headers=headers, timeout=120)
            if attacker_resp.status_code == 200:
                attacker_data = attacker_resp.json().get('data', {})
                attacker_content = attacker_data.get('content', '')
                attacker_filename = attacker_data.get('filename', 'attacker.py')
                if attacker_content:
                    logger.info("Attacker source fetched successfully")
                else:
                    attacker_content = None
            else:
                logger.info(f"No attacker file found (status {attacker_resp.status_code})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch attacker source (non-fatal): {e}")

    # Build multipart form-data for PUT update (same format as sb_update_studio_attack_draft)
    files = {
        'targetFile': (target_filename, target_content, 'text/x-python-script')
    }
    if attacker_content:
        files['attackerFile'] = (attacker_filename, attacker_content, 'text/x-python-script')

    meta_data = {"targetFileName": target_filename}
    if attacker_content:
        meta_data["attackerFileName"] = attacker_filename

    # Extract parameters and tags — ensure they are JSON strings
    raw_params = current_attack.get('parameters', [])
    params_json = json.dumps(raw_params) if not isinstance(raw_params, str) else raw_params

    raw_tags = current_attack.get('tags', [])
    tags_json = json.dumps(raw_tags) if not isinstance(raw_tags, str) else raw_tags

    data = {
        'id': str(attack_id),
        'name': current_attack.get('name', ''),
        'timeout': str(current_attack.get('timeout', 300)),
        'status': new_status,
        'class': 'python',
        'description': current_attack.get('description', ''),
        'parameters': params_json,
        'tags': tags_json,
        'methodType': str(method_type),
        'targetFileName': target_filename,
        'metaData': json.dumps(meta_data)
    }

    # Add constraints if present
    target_constraints = current_attack.get('targetConstraints')
    if target_constraints:
        data['targetConstraints'] = (
            json.dumps(target_constraints)
            if isinstance(target_constraints, dict) else target_constraints
        )

    attacker_constraints = current_attack.get('attackerConstraints')
    if attacker_constraints:
        data['attackerConstraints'] = (
            json.dumps(attacker_constraints)
            if isinstance(attacker_constraints, dict) else attacker_constraints
        )

    # PUT update to change status (publish = set status to "published", unpublish = set to "draft")
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}"
    logger.info(f"Calling PUT update to set status to '{new_status}': {api_url}")

    try:
        response = requests.put(api_url, headers=headers, data=data, files=files, timeout=120)
        response.raise_for_status()
        logger.info(f"Attack {attack_id} status successfully changed to '{new_status}'")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to change attack {attack_id} status to '{new_status}': {e}")
        raise

    # Invalidate cache if present
    cache_key = f"studio_draft_{console}_{attack_id}"
    if cache_key in studio_draft_cache:
        del studio_draft_cache[cache_key]
        logger.debug(f"Invalidated cache for key: {cache_key}")

    # Build implications text
    if new_status == "published":
        implications = (
            "Attack is now read-only on the console and available in SafeBreach Playbook "
            "for use in production test scenarios."
        )
    else:
        implications = (
            "Attack is now editable and has been removed from SafeBreach Playbook. "
            "Use update_studio_attack_draft to make changes."
        )

    return {
        "attack_id": attack_id,
        "attack_name": attack_name,
        "old_status": old_status,
        "new_status": new_status,
        "implications": implications,
    }
