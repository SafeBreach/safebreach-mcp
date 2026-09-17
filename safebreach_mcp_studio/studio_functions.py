"""
Business logic functions for Studio MCP Server.

This module provides the core functionality for validating custom Python attack
code and managing attack drafts in SafeBreach Breach Studio.
"""

import re
import ast
import json
import logging
import requests
from typing import Dict, Any, Optional

from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.safebreach_cache import SafeBreachCache
from safebreach_mcp_core.secret_utils import get_secret_for_console, get_auth_headers_for_console, check_rbac_response
from safebreach_mcp_core.token_context import get_cache_user_suffix
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from safebreach_mcp_core.rate_limiter import rate_limiter, get_caller_identity
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

# Bounded cache for draft metadata: max 5 drafts, 30-minute TTL
studio_draft_cache = SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)

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


# ---------------------------------------------------------------------------
# Shared helpers — queue submission and DAG generation (SAF-31295)
# ---------------------------------------------------------------------------


def _build_linear_dag(steps):
    """
    Build a linear sequential DAG from a list of steps.

    Generates actions (multiAttack + wait) and edges for sequential execution:
    step1 → wait(0s) → step2 → wait(0s) → step3 → ...

    Steps missing a 'uuid' field get one auto-generated (mutated in place).

    Args:
        steps: List of step dicts (each should have a 'uuid' field)

    Returns:
        Tuple of (actions, edges) lists for the queue API payload
    """
    import uuid as uuid_module

    if not steps:
        return [], []

    # Auto-generate UUIDs for steps missing them
    for step in steps:
        if not step.get('uuid'):
            step['uuid'] = str(uuid_module.uuid4())

    actions = []
    edges = []

    # Create multiAttack actions (1-indexed)
    for i, step in enumerate(steps):
        actions.append({
            "id": i + 1,
            "type": "multiAttack",
            "data": {"uuid": step['uuid']},
        })

    # Create wait actions between consecutive steps
    for i in range(len(steps) - 1):
        actions.append({
            "id": 1001 + i,
            "type": "wait",
            "data": {"seconds": 0},
        })

    # Entry edge
    edges.append({"to": 1})

    # Chain edges: step_i → wait_i → step_{i+1}
    for i in range(len(steps) - 1):
        edges.append({"from": i + 1, "to": 1001 + i})
        edges.append({"from": 1001 + i, "to": i + 2})

    return actions, edges


def _submit_to_queue(payload, console, query_params=None):
    """
    Submit a plan payload to the orchestrator queue API.

    Handles URL construction, authentication, error logging, and RBAC checks.
    Callers are responsible for their own rate limiting gates.

    Args:
        payload: Complete JSON payload for the queue API
        console: SafeBreach console identifier
        query_params: Optional dict of query parameters. Defaults to
            {"enableFeedbackLoop": "true", "retrySimulations": "true"}

    Returns:
        Parsed JSON response from the queue API

    Raises:
        requests.exceptions.HTTPError: On HTTP 4xx/5xx responses
        requests.exceptions.RequestException: On network errors
        PermissionError: On 403 RBAC failures
    """
    if query_params is None:
        query_params = {
            "enableFeedbackLoop": "true",
            "retrySimulations": "true",
        }

    base_url = get_api_base_url(console, 'orchestrator')
    account_id = get_api_account_id(console)
    headers = {
        "Content-Type": "application/json",
        **get_auth_headers_for_console(console),
    }

    api_url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue"
    logger.info(f"Calling queue API: {api_url}")

    try:
        response = requests.post(
            api_url, headers=headers, params=query_params,
            json=payload, timeout=120,
        )
        if response.status_code >= 400:
            logger.error(
                f"Queue API error {response.status_code}: {response.text}"
            )
        check_rbac_response(response)
        api_response = response.json()
        logger.info("Queue API call successful")
        return api_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Queue API call failed: {e}")
        raise


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
    check_rbac_response(response)
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

    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}
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

    # Rate limiting gate — check before mutating
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "save_studio_attack_draft")

    # Get authentication and base URL
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

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
        check_rbac_response(response)
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

    # Cache the result (only if caching is enabled)
    if is_caching_enabled("studio"):
        cache_key = f"studio_draft_{console}_{result['draft_id']}{get_cache_user_suffix()}"
        studio_draft_cache.set(cache_key, result)
        logger.debug(f"Cached draft with key: {cache_key}")

    # Rate limiting gate — record after successful save
    rate_limiter.record_action(caller_id, "save_studio_attack_draft")

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
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

    # Call get all attacks API
    api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all"
    logger.info(f"Calling get all attacks API: {api_url}")

    try:
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)
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

    # Rate limiting gate — check before mutating
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "update_studio_attack_draft")

    # Get authentication and base URL
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

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
        check_rbac_response(response)
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

    # Update cache with new values (only if caching is enabled)
    if is_caching_enabled("studio"):
        cache_key = f"studio_draft_{console}_{result['draft_id']}{get_cache_user_suffix()}"
        studio_draft_cache.set(cache_key, result)
        logger.debug(f"Updated cache with key: {cache_key}")

    # Rate limiting gate — record after successful update
    rate_limiter.record_action(caller_id, "update_studio_attack_draft")

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
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

    # Fetch target source code (always required)
    target_api_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods/{attack_id}/files/target"
    logger.info(f"Calling get target source API: {target_api_url}")

    try:
        response = requests.get(target_api_url, headers=headers, timeout=120)
        check_rbac_response(response)
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


def _find_attack_by_id(attack_id: int, console: str = "default") -> Dict[str, Any]:
    """
    Fetch a single Studio attack's full record by ID from the content-manager
    custom-methods list.

    Args:
        attack_id: The playbook/custom-method ID of the attack.
        console: SafeBreach console identifier.

    Returns:
        The attack dict (includes status, name, methodType, parameters, tags, etc.).

    Raises:
        ValueError: If no attack with the given ID is found on the console.
        requests.exceptions.RequestException: Propagated if the list API call fails.
    """
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

    list_url = f"{base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all"
    logger.info(f"Looking up attack {attack_id} via: {list_url}")

    response = requests.get(list_url, headers=headers, timeout=120)
    check_rbac_response(response)
    api_response = response.json()
    # API may return {"data": [...]} wrapper or a raw list
    all_attacks = api_response.get("data", api_response) if isinstance(api_response, dict) else api_response

    for attack in all_attacks:
        if attack.get("id") == attack_id:
            return attack

    raise ValueError(f"Attack with ID {attack_id} not found on console '{console}'")


def _get_attack_status_by_id(attack_id: int, console: str = "default") -> tuple:
    """
    Fetch a single Studio attack's current publication status by ID.

    Thin wrapper over _find_attack_by_id for callers that only need the status.

    Args:
        attack_id: The playbook/custom-method ID of the attack.
        console: SafeBreach console identifier.

    Returns:
        Tuple (status, name) where status is lowercase ("draft" | "published").

    Raises:
        ValueError: If no attack with the given ID is found on the console.
        requests.exceptions.RequestException: Propagated if the list API call fails.
    """
    attack = _find_attack_by_id(attack_id, console)
    return attack.get("status", "").lower(), attack.get("name", "Unknown")


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

    # Rate limiting gate — check before mutating
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "run_studio_attack")

    # Resolve the attack's publication status so the queued test's draft flag matches it.
    # PUBLISHED -> draft=False so the run is discoverable in Test Results (SAF-31468);
    # DRAFT -> draft=True (Studio-only) with a warning. A failed lookup (not a "not found")
    # degrades to published so a transient read error does not hide a legitimate run.
    status_unconfirmed = False
    try:
        attack_status, _attack_name = _get_attack_status_by_id(attack_id, console)
        is_draft = (attack_status == "draft")
    except ValueError:
        # Attack genuinely not found — surface a clear error and do not queue.
        raise
    except Exception as e:
        logger.warning(
            f"Could not resolve publication status for attack {attack_id} "
            f"({e}); proceeding as published (draft=False)."
        )
        is_draft = False
        status_unconfirmed = True

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
            "draft": is_draft
        }
    }

    # Submit to queue API (studio attacks use retrySimulations=false)
    api_response = _submit_to_queue(
        payload, console,
        query_params={"enableFeedbackLoop": "true", "retrySimulations": "false"},
    )

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
        'draft': is_draft,
    }

    # Surface visibility guidance to the agent.
    if is_draft:
        result['hint_to_agent'] = (
            "This attack is in DRAFT, so the run was queued as a draft and is visible "
            "only in Breach Studio — it will NOT appear in the Test Results page. "
            "Publish the attack (set_studio_attack_status) before running to make the "
            "run discoverable in Test Results."
        )
    elif status_unconfirmed:
        result['hint_to_agent'] = (
            "The attack's publication status could not be confirmed, so the run was "
            "queued as published (draft=False). If the attack is actually a draft, its "
            "results may not appear as expected."
        )

    # Rate limiting gate — record after successful queue
    rate_limiter.record_action(caller_id, "run_studio_attack")

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
    base_url = get_api_base_url(console, 'data')  # Use data URL for execution history API
    account_id = get_api_account_id(console)

    headers = {
        "Content-Type": "application/json",
        **get_auth_headers_for_console(console)
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
        check_rbac_response(response)

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

        # Fetch test-level overview (SAF-30717)
        test_overview = None
        if total_found > 0:
            resolved_test_id = test_id if test_id else transformed_executions[0].get('test_id')
            if resolved_test_id:
                try:
                    summary_url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{resolved_test_id}"
                    summary_response = requests.get(summary_url, headers=headers, timeout=120)
                    check_rbac_response(summary_response)
                    summary_data = summary_response.json()

                    # SAF-32018: test_overview is a coarse status-tracker for this custom
                    # attack's run, so we keep the cheap test-level finalStatus aggregate here.
                    # For a RUNNING test this aggregate lags the live per-simulation results;
                    # the non-terminal hint below routes the agent to get_test_details (which
                    # returns live counts for running tests) for the exact numbers.
                    final_status = summary_data.get('finalStatus', {})
                    simulation_status_counts = [
                        {"status": status, "count": final_status.get(status, 0)}
                        for status in ['missed', 'stopped', 'prevented', 'detected',
                                       'logged', 'no-result', 'inconsistent']
                    ]
                    total_simulations = sum(entry['count'] for entry in simulation_status_counts)

                    test_overview = {
                        # Normalize casing: the summary API returns an uppercase status
                        # (e.g. "COMPLETED"), but the documented/unit-tested contract is
                        # lowercase (running/completed/canceled/failed/queued).
                        'status': (summary_data.get('status') or '').lower(),
                        'start_time': summary_data.get('startTime'),
                        'end_time': summary_data.get('endTime'),
                        'duration': summary_data.get('duration'),
                        'simulation_status_counts': simulation_status_counts,
                        'total_simulations': total_simulations,
                    }

                    terminal_statuses = {'completed', 'canceled', 'failed'}
                    test_status = (test_overview['status'] or '').lower()
                    if test_status not in terminal_statuses:
                        test_overview['hint_to_agent'] = (
                            f"Test is still {test_overview['status']} "
                            f"({total_found} of {total_simulations} simulations completed so far). "
                            f"These simulation_status_counts come from a periodically-updated "
                            f"summary and may lag the live results while the test runs. For exact "
                            f"live counts, call get_test_details(test_id='{resolved_test_id}', "
                            f"console='{console}') on the Data Server (it returns live counts for "
                            f"running tests), or get_simulations with a status_filter. "
                            f"Poll this tool again in ~30 seconds for updated totals."
                        )
                except Exception as e:
                    logger.warning(f"Failed to fetch test summary for test_id '{resolved_test_id}': {e}")
                    test_overview = None

        result = {
            'executions': transformed_executions,
            'returned_count': len(transformed_executions),
            'total_found': total_found,
            'attack_id': attack_id,
            'console': console,
            'has_more': total_found > len(transformed_executions),
            'test_overview': test_overview,
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
    if not is_caching_enabled("studio"):
        logger.debug(f"Caching disabled, cache miss for key: {cache_key}")
        return None

    cached = studio_draft_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Cache hit for key: {cache_key}")
        return cached

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

    # Get authentication and base URL (reused below for source fetch + PUT update)
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)
    headers = {**get_auth_headers_for_console(console)}

    # Pre-check: fetch the attack's current record via the shared helper. This supplies
    # the current status/name plus the fields (methodType, parameters, tags, constraints)
    # needed to rebuild the PUT payload below.
    current_attack = _find_attack_by_id(attack_id, console)
    attack_name = current_attack.get("name", "Unknown")
    current_status = current_attack.get("status", "").lower()

    # Check if already in target status
    if current_status == new_status:
        raise ValueError(
            f"Attack {attack_id} ('{attack_name}') is already {new_status}"
        )

    old_status = current_status

    # Rate limiting gate — check AFTER pre-check reads, before mutating PUT
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "set_studio_attack_status")

    # Fetch source code files needed for the PUT payload
    # Target file (always required)
    target_url = (
        f"{base_url}/api/content/v1/accounts/{account_id}"
        f"/customMethods/{attack_id}/files/target"
    )
    logger.info(f"Fetching target source for status update: {target_url}")

    try:
        target_response = requests.get(target_url, headers=headers, timeout=120)
        check_rbac_response(target_response)
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
        check_rbac_response(response)
        logger.info(f"Attack {attack_id} status successfully changed to '{new_status}'")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to change attack {attack_id} status to '{new_status}': {e}")
        raise

    # Invalidate cache if present
    cache_key = f"studio_draft_{console}_{attack_id}{get_cache_user_suffix()}"
    if studio_draft_cache.delete(cache_key):
        logger.debug(f"Invalidated cache for key: {cache_key}")

    # Rate limiting gate — record after successful status change
    rate_limiter.record_action(caller_id, "set_studio_attack_status")

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


# =====================================================================
# Scenario Execution (SAF-29967)
# =====================================================================


def _has_real_filter_criteria(filter_dict):
    """
    Check if a filter dict has at least one key with non-empty values.

    A filter like {"os": {"operator": "is", "values": ["WINDOWS"]}} qualifies.
    A filter like {"simulators": {"operator": "is", "values": []}} does NOT.
    An empty dict or None does NOT qualify.
    """
    if not filter_dict:
        return False
    for value in filter_dict.values():
        if isinstance(value, dict):
            vals = value.get('values', [])
            if vals:
                return True
        elif value:
            return True
    return False


def compute_scenario_readiness(scenario):
    """
    Determine if a scenario is ready to run.

    A scenario is ready when ALL steps have BOTH targetFilter AND attackerFilter
    with at least one key containing non-empty values arrays.

    Returns bool. Named differently from config_types' compute_is_ready_to_run
    because this will evolve in future slices to return diagnostic info.
    """
    steps = scenario.get('steps', [])
    if not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        target = step.get('targetFilter', {})
        attacker = step.get('attackerFilter', {})
        if not _has_real_filter_criteria(target) or not _has_real_filter_criteria(attacker):
            return False
    return True


def diagnose_scenario_readiness(scenario):
    """
    Diagnose scenario readiness with detailed per-step analysis.

    Returns a dict with:
    - ready: bool
    - total_steps: int
    - missing_steps: list of dicts with step_number, step_name, missing_filters, attacksFilter
    """
    steps = scenario.get('steps', [])
    if not steps:
        return {'ready': False, 'total_steps': 0, 'missing_steps': []}

    missing_steps = []
    for i, step in enumerate(steps):
        target = step.get('targetFilter', {})
        attacker = step.get('attackerFilter', {})
        missing_filters = []
        if not _has_real_filter_criteria(target):
            missing_filters.append('targetFilter')
        if not _has_real_filter_criteria(attacker):
            missing_filters.append('attackerFilter')
        if missing_filters:
            recommendation = _get_step_filter_recommendation(step)
            missing_steps.append({
                'step_number': i + 1,
                'step_name': step.get('name', f'Step {i + 1}'),
                'missing_filters': missing_filters,
                'attacksFilter': step.get('attacksFilter', {}),
                'recommendation': recommendation,
            })

    return {
        'ready': len(missing_steps) == 0,
        'total_steps': len(steps),
        'missing_steps': missing_steps,
    }


def _apply_step_overrides(scenario, overrides):
    """
    Apply per-step filter overrides to a scenario's steps.

    Args:
        scenario: Scenario dict (modified in-place)
        overrides: Dict mapping step number strings (1-indexed) to filter overrides.
            Each value is a dict with optional 'targetFilter' and/or 'attackerFilter'.

    Raises:
        ValueError: If a step number is out of range
    """
    steps = scenario.get('steps', [])
    for step_num_str, override in overrides.items():
        step_num = int(step_num_str)
        if step_num < 1 or step_num > len(steps):
            raise ValueError(
                f"Invalid step {step_num} in step_overrides — "
                f"scenario has {len(steps)} steps (1-indexed)"
            )
        step = steps[step_num - 1]
        if 'targetFilter' in override:
            step['targetFilter'] = override['targetFilter']
        if 'attackerFilter' in override:
            step['attackerFilter'] = override['attackerFilter']


# Attack phase → recommended filter mapping
ATTACK_PHASE_RECOMMENDATIONS = {
    0: {
        'phase_name': 'exfiltration',
        'attackerFilter': 'role=isExfiltration',
        'targetFilter': 'os (endpoint OS)',
        'description': 'Data exfiltration — attacker needs isExfiltration role',
    },
    1: {
        'phase_name': 'infiltration (network)',
        'attackerFilter': 'role=isInfiltration',
        'targetFilter': 'os (endpoint OS)',
        'description': 'Network infiltration — attacker needs isInfiltration role',
    },
    2: {
        'phase_name': 'infiltration (network)',
        'attackerFilter': 'role=isInfiltration',
        'targetFilter': 'os (endpoint OS)',
        'description': 'Network infiltration — attacker needs isInfiltration role',
    },
    5: {
        'phase_name': 'host-level',
        'attackerFilter': 'os (same as target)',
        'targetFilter': 'os (endpoint OS)',
        'description': 'Host-level execution — attacker and target are the same machine',
    },
}


# Attack types that indicate network/infiltration (need isInfiltration role)
INFILTRATION_ATTACK_TYPES = {
    'Malware Transfer', 'Hidden Malware Transfer', 'Web Shell Transfer',
    'Exploit Transfer', 'Exploit Kit Infection', 'Remote Exploitation',
    'Brute Force', 'Remote Control', 'Outbound C&C Communication',
    'Malicious Domain Resolution', 'Real C2 Communication', 'URL Navigation',
}

# Attack types that indicate exfiltration (need isExfiltration role)
EXFILTRATION_ATTACK_TYPES = {
    'Covert Channel Exfiltration', 'Legitimate Channel Exfiltration',
}

# MITRE tactics that indicate host-level execution
HOST_LEVEL_TACTICS = {
    'Execution', 'Persistence', 'Privilege Escalation', 'Defense Evasion',
    'Discovery', 'Collection', 'Impact', 'Credential Access',
}

# MITRE tactics that indicate network activity
NETWORK_TACTICS = {
    'Initial Access', 'Command And Control', 'Lateral Movement',
}


def _get_step_filter_recommendation(step):
    """Generate filter recommendations based on a step's attack phase, type, and MITRE tactic.

    Uses attack phase first, then falls back to attack type inference,
    then MITRE tactic, then step name heuristics.
    """
    attacks_filter = step.get('attacksFilter', {})
    phase_values = attacks_filter.get('attackPhase', {}).get('values', [])
    attack_types = attacks_filter.get('attackType', {}).get('values', [])
    tags = attacks_filter.get('tags', {})
    mitre_tactics = tags.get('mitre_tactic', {}).get('values', []) if isinstance(tags, dict) else []
    step_name = step.get('name', '').lower()

    phase = phase_values[0] if phase_values else None

    # Try attack phase first
    if phase is not None and phase in ATTACK_PHASE_RECOMMENDATIONS:
        rec = ATTACK_PHASE_RECOMMENDATIONS[phase]
        return {
            'phase': phase,
            'phase_name': rec['phase_name'],
            'recommended_attackerFilter': rec['attackerFilter'],
            'recommended_targetFilter': rec['targetFilter'],
            'description': rec['description'],
            'attack_types': attack_types,
        }

    # Fallback: infer from attack types
    attack_type_set = set(attack_types)
    if attack_type_set & EXFILTRATION_ATTACK_TYPES:
        return {
            'phase': None,
            'phase_name': 'exfiltration (inferred from attack types)',
            'recommended_attackerFilter': 'role=isExfiltration',
            'recommended_targetFilter': 'os (endpoint OS)',
            'description': 'Exfiltration attacks detected — attacker needs isExfiltration role',
            'attack_types': attack_types,
        }
    if attack_type_set & INFILTRATION_ATTACK_TYPES:
        return {
            'phase': None,
            'phase_name': 'infiltration (inferred from attack types)',
            'recommended_attackerFilter': 'role=isInfiltration',
            'recommended_targetFilter': 'os (endpoint OS)',
            'description': 'Network attacks detected — attacker needs isInfiltration role',
            'attack_types': attack_types,
        }

    # Fallback: infer from MITRE tactics
    tactic_set = set(mitre_tactics)
    if tactic_set & {'Exfiltration'}:
        return {
            'phase': None,
            'phase_name': 'exfiltration (MITRE tactic)',
            'recommended_attackerFilter': 'role=isExfiltration',
            'recommended_targetFilter': 'os (endpoint OS)',
            'description': 'Exfiltration tactic — attacker needs isExfiltration role',
            'attack_types': attack_types,
        }
    if tactic_set & NETWORK_TACTICS:
        return {
            'phase': None,
            'phase_name': f'network ({", ".join(tactic_set & NETWORK_TACTICS)})',
            'recommended_attackerFilter': 'role=isInfiltration',
            'recommended_targetFilter': 'os (endpoint OS)',
            'description': 'Network tactic — attacker needs isInfiltration role',
            'attack_types': attack_types,
        }
    if tactic_set & HOST_LEVEL_TACTICS:
        return {
            'phase': None,
            'phase_name': f'host-level ({", ".join(tactic_set & HOST_LEVEL_TACTICS)})',
            'recommended_attackerFilter': 'os (same as target)',
            'recommended_targetFilter': 'os (endpoint OS)',
            'description': 'Host-level tactic — attacker and target on same machine',
            'attack_types': attack_types,
        }

    # Last resort: step name heuristics
    if any(x in step_name for x in ['exfil', 'data collection']):
        phase_name = 'exfiltration (from step name)'
        atk_rec = 'role=isExfiltration'
    elif any(x in step_name for x in ['network', 'infiltration', 'c&c', 'command and control',
                                       'initial access', 'lateral']):
        phase_name = 'infiltration (from step name)'
        atk_rec = 'role=isInfiltration'
    else:
        phase_name = 'host-level (default)'
        atk_rec = 'os (same as target)'

    return {
        'phase': None,
        'phase_name': phase_name,
        'recommended_attackerFilter': atk_rec,
        'recommended_targetFilter': 'os (endpoint OS)',
        'description': f'Inferred from step name — use targeted filter',
        'attack_types': attack_types,
    }


def _fetch_all_scenarios(console):
    """
    Fetch all OOB scenarios from the content-manager API.

    Args:
        console: SafeBreach console name

    Returns:
        List of full scenario dictionaries
    """
    base_url = get_api_base_url(console, 'playbook')

    api_url = f"{base_url}/api/content-manager/vLatest/scenarios"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    logger.info(f"Fetching scenarios from content-manager API for console '{console}'")
    response = requests.get(api_url, headers=headers, timeout=120)
    try:
        check_rbac_response(response)
    except requests.exceptions.HTTPError:
        body = getattr(response, 'text', '')
        logger.error(f"Scenario fetch error {response.status_code}: {body}")
        raise ValueError(
            f"Scenario fetch error ({response.status_code}): {body}"
        )

    scenarios = response.json()
    logger.info(f"Retrieved {len(scenarios)} scenarios for console '{console}'")
    return scenarios


def _fetch_all_plans(console):
    """
    Fetch all custom plans from the config API.

    Args:
        console: SafeBreach console name

    Returns:
        List of full plan dictionaries
    """
    base_url = get_api_base_url(console, 'config')
    account_id = get_api_account_id(console)

    api_url = f"{base_url}/api/config/v2/accounts/{account_id}/plans?details=true"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    logger.info(f"Fetching custom plans from API for console '{console}'")
    response = requests.get(api_url, headers=headers, timeout=120)
    try:
        check_rbac_response(response)
    except requests.exceptions.HTTPError:
        body = getattr(response, 'text', '')
        logger.error(f"Plan fetch error {response.status_code}: {body}")
        raise ValueError(
            f"Plan fetch error ({response.status_code}): {body}"
        )

    response_data = response.json()
    plans = response_data.get("data", []) if isinstance(response_data, dict) else response_data

    logger.info(f"Retrieved {len(plans)} custom plans for console '{console}'")
    return plans


# Each constraint has: description (human-readable) and fixable_via_overrides (bool)
CONSTRAINT_REASON_DESCRIPTIONS = {
    "incompatible_os": {
        "description": "Simulator OS doesn't match attack requirement",
        "fixable": True,
    },
    "incompatible_package": {
        "description": "Simulator role mismatch (e.g., requires infiltration/exfiltration)",
        "fixable": True,
    },
    "simulator_on_both_sides": {
        "description": "Network attack needs separate attacker and target simulators",
        "fixable": True,
    },
    "simulator_variant_is_not_root_user": {
        "description": "Attack requires root/admin execution privilege",
        "fixable": True,
    },
    "simulator_variant_is_root_user": {
        "description": "Attack requires non-root execution",
        "fixable": True,
    },
    "missing_required_advanced_actions": {
        "description": "Specific advanced action type not enabled on simulator",
        "fixable": False,
    },
    "simulator_failed_schema_validation": {
        "description": "Simulator missing required software/capability",
        "fixable": False,
    },
    "simulator_is_not_aws_attacker": {
        "description": "Requires AWS attacker role — check get_console_simulators for candidates",
        "fixable": True,
    },
    "simulator_is_not_aws_simulator": {
        "description": "Requires AWS simulator — check get_console_simulators for candidates",
        "fixable": True,
    },
    "simulator_is_not_mail_virtual_simulator": {
        "description": "Requires mailbox simulator — check get_console_simulators for candidates",
        "fixable": True,
    },
    "move_does_not_support_root_simulation_user": {
        "description": "Attack incompatible with root simulation user",
        "fixable": False,
    },
    "move_doesnt_requires_proxy_ignoring_proxy_variant": {
        "description": "Proxy configuration mismatch",
        "fixable": False,
    },
    "port_in_use": {
        "description": "Required port occupied on simulator",
        "fixable": False,
    },
    "simulator_didnt_pass_pre_execution_prerequisite_tests": {
        "description": "Pre-execution checks failed on simulator",
        "fixable": False,
    },
}


def _build_attack_name_map(console):
    """Build a move_id→name map from the playbook cache.

    Returns empty dict on failure (non-fatal — names are a cosmetic enhancement).
    """
    try:
        from safebreach_mcp_playbook.playbook_functions import _get_all_attacks_from_cache_or_api
        attacks = _get_all_attacks_from_cache_or_api(console)
        return {str(a['id']): a.get('name', '') for a in attacks if 'id' in a}
    except Exception as e:
        logger.warning(f"Failed to build attack name map: {e}")
        return {}


def _summarize_constraints(simulator_constraints, attack_names=None):
    """Summarize constraint failures into a per-attack breakdown.

    Returns a list of dicts: [{move_id, reasons: [{code, description, detail}]}]
    """
    # Merge target + attacker constraints per move
    move_reasons = {}
    for side in ['targetConstraints', 'attackerConstraints']:
        side_data = simulator_constraints.get(side, {})
        for sim_id, moves in side_data.items():
            for move_id, reasons in moves.items():
                if move_id not in move_reasons:
                    move_reasons[move_id] = {}
                for r in reasons:
                    code = r.get('reason', 'unknown')
                    # Use code as key to deduplicate across simulators
                    if code not in move_reasons[move_id]:
                        detail_parts = []
                        # Handle required/actual naming (e.g., incompatible_os)
                        if r.get('required') is not None and r.get('actual') is not None:
                            detail_parts.append(
                                f"requires {r['required']}, simulator has {r['actual']}"
                            )
                        # Handle expected/got naming (e.g., incompatible_package)
                        if r.get('expected') is not None:
                            detail_parts.append(f"expected: {r['expected']}")
                        if r.get('got') is not None and not r.get('expected'):
                            detail_parts.append(f"simulator has: {r['got']}")
                        # Include any free-form reason text
                        if r.get('reason_text'):
                            detail_parts.append(r['reason_text'])

                        move_reasons[move_id][code] = {
                            'code': code,
                            'description': CONSTRAINT_REASON_DESCRIPTIONS.get(code, {}).get('description', code),
                            'fixable': CONSTRAINT_REASON_DESCRIPTIONS.get(code, {}).get('fixable', True),
                            'detail': '; '.join(detail_parts) if detail_parts else None,
                        }

    result = []
    for move_id in sorted(move_reasons.keys()):
        entry = {
            'move_id': move_id,
            'reasons': list(move_reasons[move_id].values()),
        }
        if attack_names and move_id in attack_names:
            entry['attack_name'] = attack_names[move_id]
        result.append(entry)
    return result


def _summarize_constraints_aggregated(simulator_constraints, attack_names=None):
    """Aggregate constraint failures by reason code across all attacks.

    Used for partial-coverage steps where per-attack detail is too verbose.
    Returns a list of dicts: [{code, description, count, details: [{detail, attack_count}]}]
    """
    # First get per-attack breakdown
    per_attack = _summarize_constraints(simulator_constraints, attack_names=attack_names)

    # Aggregate by (code, detail) across attacks
    reason_groups = {}
    for attack in per_attack:
        for reason in attack['reasons']:
            code = reason['code']
            detail = reason.get('detail') or ''
            key = (code, detail)
            if key not in reason_groups:
                reason_groups[key] = {
                    'code': code,
                    'description': reason['description'],
                    'fixable': reason.get('fixable', True),
                    'detail': detail,
                    'attack_count': 0,
                    'move_ids': [],
                }
            reason_groups[key]['attack_count'] += 1
            reason_groups[key]['move_ids'].append(attack['move_id'])

    # Group by code, then sub-group by detail
    code_groups = {}
    for (code, detail), info in reason_groups.items():
        if code not in code_groups:
            code_groups[code] = {
                'code': code,
                'description': info['description'],
                'fixable': info.get('fixable', True),
                'total_attacks': 0,
                'sub_reasons': [],
            }
        code_groups[code]['total_attacks'] += info['attack_count']
        if detail:
            code_groups[code]['sub_reasons'].append({
                'detail': detail,
                'attack_count': info['attack_count'],
            })

    # Sort by total attacks descending
    return sorted(code_groups.values(), key=lambda x: -x['total_attacks'])


def _get_scenario_statistics(steps, console, include_constraints=False,
                             verbose_failures=False):
    """
    Predict per-step simulation counts using the plan statistics API.

    Args:
        steps: List of scenario step dicts (with filter fields)
        console: SafeBreach console name
        include_constraints: If True, include per-attack constraint failure reasons
            (adds latency — use only for evaluate)
        verbose_failures: If True, show per-attack constraints even for partial steps
            (default: aggregated summary for partial, per-attack for zero)

    Returns:
        List of per-step stat dicts with simulationCount, matched counts,
        resolved_attacks, and optionally constraint details.
    """
    logger.info(f"Calling statistics API for {len(steps)} steps on console '{console}'"
                f"{' (with constraints)' if include_constraints else ''}")
    # includeDisabled=True is this path's long-standing behaviour, kept as-is so
    # routing the call through the shared fetcher changes nothing on the wire. It
    # scores the whole fleet rather than the runnable part, so the prediction can
    # exceed what a run produces and offline nodes never surface as blockers.
    data = _fetch_scenario_statistics(
        console,
        {"name": "", "steps": steps},
        get_constraints=include_constraints,
        get_all_constraints=include_constraints,
        include_disabled=True,
    )
    step_stats = data.get('steps', [])

    # Build attack name map for evaluate (resolved attacks + constraint rendering)
    attack_names = _build_attack_name_map(console) if include_constraints else {}

    result = []
    for s in step_stats:
        sim_count = s.get('simulationCount', 0)
        target_sims = s.get('targetSimulators', {})
        attacker_sims = s.get('attackerSimulators', {})
        moves = s.get('moves', {})

        step_result = {
            'simulationCount': sim_count,
            'matchedTargetSimulators': sum(1 for v in target_sims.values() if v > 0),
            'matchedAttackerSimulators': sum(1 for v in attacker_sims.values() if v > 0),
            'matchedAttacks': sum(1 for v in moves.values() if v > 0),
            'totalTargetSimulators': len(target_sims),
            'totalAttackerSimulators': len(attacker_sims),
            'totalAttacks': len(moves),
        }

        # Resolved attacks: list of attacks with sim counts and names
        if include_constraints and moves:
            step_result['resolved_attacks'] = [
                {
                    'move_id': mid,
                    'name': attack_names.get(mid, ''),
                    'simulationCount': count,
                }
                for mid, count in sorted(moves.items(), key=lambda x: -x[1])
            ]

        # Add constraint diagnostics when there are unmatched attacks
        if include_constraints:
            unmatched = sum(1 for v in moves.values() if v == 0)
            constraints = s.get('simulatorConstraints', {})
            if constraints and unmatched > 0:
                if sim_count == 0 or verbose_failures:
                    # Per-attack detail: zero-sim steps OR verbose mode
                    step_result['constraint_summary'] = _summarize_constraints(
                        constraints, attack_names=attack_names
                    )
                else:
                    # Partial coverage default: aggregated summary
                    step_result['constraint_summary_aggregated'] = (
                        _summarize_constraints_aggregated(
                            constraints, attack_names=attack_names
                        )
                    )
                step_result['unmatched_attack_count'] = unmatched

        result.append(step_result)

    counts = [s['simulationCount'] for s in result]
    logger.info(f"Statistics: {counts} (total: {sum(counts)})")
    return result




# ---------------------------------------------------------------------------
# plan/statistics — how many simulations a scenario would produce
# ---------------------------------------------------------------------------

STATISTICS_TIMEOUT_SECONDS = 120
STATISTICS_LIMIT = 500000
SIMULATOR_LISTING_CAP = 20

COUNTS_HINT = (
    "These are runnable counts: offline, disabled and unapproved simulators are "
    "excluded. This tool reports what runs and how much; for why an attack or a "
    "simulator produces nothing, call get_scenario_blocked_entities. Nothing is "
    "cached here, so re-call after any change to the scenario."
)


def is_computed_count(value):
    """True when the console actually measured this count.

    ``None`` is what the orchestrator writes when it stops evaluating early, and
    it is not a zero — a count that was never taken says nothing about whether
    the entity runs. Bools are excluded deliberately: ``True`` is an ``int`` in
    Python, and a stray flag must never be read as the number 1.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _is_blank_input(value):
    """A blank string names nothing, so it counts as absent rather than as a choice."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return not value
    return False


def _sole_scenario_input(scenario, scenario_id, test_id):
    """The one input that names what to score, or an error naming all three."""
    given = [name for name, value in (('scenario', scenario),
                                      ('scenario_id', scenario_id),
                                      ('test_id', test_id))
             if not _is_blank_input(value)]
    if len(given) == 1:
        return given[0]
    detail = "none was given" if not given else f"these were given: {', '.join(given)}"
    raise ValueError(
        "Name exactly one of scenario, scenario_id or test_id — "
        f"{detail}."
    )


def _parse_scenario_argument(scenario):
    """An ad-hoc scenario, accepted either as JSON text or already parsed."""
    if isinstance(scenario, dict):
        return dict(scenario)
    try:
        parsed = json.loads(scenario)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Invalid scenario JSON: {e}")
    if not isinstance(parsed, dict):
        raise ValueError(
            "scenario must be a JSON object with a 'steps' list, "
            f"not {type(parsed).__name__}"
        )
    return parsed


def _statistics_plan_body(scenario, scenario_id, test_id):
    """The body to score, and how many steps it holds when that is knowable.

    The step count is returned alongside because the orchestrator truncates its
    reply when it stops evaluating early, and a reply shorter than the plan is
    only detectable against a step list this side holds. The two id forms are
    resolved server-side, so nothing here knows their length.
    """
    named = _sole_scenario_input(scenario, scenario_id, test_id)

    if named == 'test_id':
        return {'name': '', 'testId': str(test_id).strip()}, None

    if named == 'scenario_id':
        return {'name': '', 'id': _plan_id(scenario_id)}, None

    body = _parse_scenario_argument(scenario)
    steps = body.get('steps')
    _require_steps(steps, "The scenario given")
    body.setdefault('name', '')
    return body, len(steps)


def _plan_id(scenario_id):
    """A saved plan's numeric id, which the endpoint resolves for itself.

    An OOB scenario's UUID is refused rather than resolved here. The endpoint
    has no body field that accepts one, so honouring it would mean listing every
    scenario on the console to recover steps the caller can fetch directly — a
    second request this tool would otherwise never make.
    """
    resolved = str(scenario_id).strip()
    if not resolved.isdigit():
        raise ValueError(
            f"scenario_id must be a saved plan's numeric id, not '{resolved}'. "
            "For an OOB scenario, fetch its steps with get_scenario_details and "
            "pass them as 'scenario'."
        )
    return int(resolved)


def _require_steps(steps, subject):
    """Refuse a step-less scenario here rather than spending a request on a 400."""
    if not steps:
        raise ValueError(
            f"{subject} has no steps, so there is nothing to score. "
            "A scenario needs at least one step."
        )


def _fetch_scenario_statistics(console, body, get_constraints=False,
                           get_all_constraints=False, include_disabled=False):
    """Score one plan body against the fleet as it stands.

    The single place this repo calls the statistics endpoint. Every parameter
    but the three flags is fixed, and the constraint pair follows the question
    being asked: constraints are the whole answer to what will not run, and dead
    weight to how much will. They are never free — a single ordinary step
    measured 38,531 of them. Both default off so a caller that does not ask for
    them cannot be made to pay.

    ``include_disabled`` widens scoring from the enabled fleet to the whole one.
    It defaults off, which is both the runnable figure and the endpoint's own
    default. On, the orchestrator also empties its offline-node set, so a fleet
    scored that way can never report ``simulator_is_offline`` as a blocker.

    ``get_all_constraints`` decides how many reasons a simulator records, not how
    they are grouped. Off, validators run as a chain over survivors and a
    simulator keeps only the first reason that eliminated it; on, every validator
    runs against the full node set and it accumulates every reason it fails.

    Booleans are sent as their JSON spelling; the endpoint reads them as strings,
    and ``"True"`` would quietly ask a different question.
    """
    base_url = get_api_base_url(console, 'orchestrator')
    account_id = get_api_account_id(console)
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}
    api_url = f"{base_url}/api/orch/v1/accounts/{account_id}/plan/statistics"
    params = {
        'limit': STATISTICS_LIMIT,
        'includeDisabled': 'true' if include_disabled else 'false',
        'getConstraints': 'true' if get_constraints else 'false',
        'getAllConstraints': 'true' if get_all_constraints else 'false',
        'useCache': 'true',
    }

    logger.info(f"Scoring plan statistics on console '{console}'")
    response = requests.post(api_url, headers=headers, params=params, json=body,
                             timeout=STATISTICS_TIMEOUT_SECONDS)
    try:
        check_rbac_response(response)
    except requests.exceptions.HTTPError:
        detail = getattr(response, 'text', '')
        logger.error(f"Statistics API error {response.status_code}: {detail}")
        raise ValueError(f"Statistics API error ({response.status_code}): {detail}")

    return response.json().get('data', {}) or {}


def _normalize_statistics_steps(payload):
    """The counts exactly as the console reported them, and nothing derived.

    This is where ``moves`` is dropped. The endpoint always sends it and offers
    no parameter to suppress it, so this is the earliest point this side
    controls; on a real step it is a couple of thousand attack ids and the
    largest field in the payload. Counting attacks is the other question, and
    carrying the map through three layers to discard it at the fourth is work
    done for nothing.
    """
    steps = []
    for index, step in enumerate(payload.get('steps') or []):
        count = step.get('simulationCount')
        steps.append({
            'step_index': index,
            'simulation_count': count,
            'counts_computed': is_computed_count(count),
            'is_limit_reached': bool(step.get('isLimitReached')),
            'attacker_simulators': dict(step.get('attackerSimulators') or {}),
            'target_simulators': dict(step.get('targetSimulators') or {}),
        })
    return steps


def _shape_statistics_step(step):
    """One step's answer: the count, and what each simulator would produce in each role.

    The raw role maps are kept whole. Both the default per-simulator breakdown
    and the named-id answers are read from them through the same disposition
    vocabulary, so a simulator measured at exactly zero stays distinguishable
    from one the step never offered in that role.
    """
    offered = set(step['attacker_simulators']) | set(step['target_simulators'])
    return {
        'step_index': step['step_index'],
        'simulation_count': step['simulation_count'],
        'counts_computed': step['counts_computed'],
        'is_limit_reached': step['is_limit_reached'],
        'attacker_simulators_offered': step['attacker_simulators'],
        'target_simulators_offered': step['target_simulators'],
        'simulators_offered': len(offered),
        # The trigger is the fleet the step offers, not how much of it produces:
        # 500 offered of which 3 produce is still a 500-row breakdown.
        'listing_omitted': len(offered) > SIMULATOR_LISTING_CAP,
    }


def _simulator_rows(step):
    """What every simulator in this step would produce, in both roles at once.

    One row per simulator rather than a list per role: the caller is choosing
    which machines to attack from and which to attack, and that decision reads
    a machine's two numbers together. A simulator offered in only one role is
    stated as such in the other, which is the fact that makes it a target-only
    or attacker-only candidate.

    Ranked by total contribution so the strongest candidates lead. Simulators
    measured at zero are kept: "produces nothing here" is the most actionable
    thing this answer can say about a machine.
    """
    offered = sorted(set(step['attacker_simulators_offered'])
                     | set(step['target_simulators_offered']), key=str)
    rows = [
        {
            'simulator_id': simulator_id,
            'attacker': _simulator_disposition(step, 'attacker_simulators', simulator_id),
            'target': _simulator_disposition(step, 'target_simulators', simulator_id),
        }
        for simulator_id in offered
    ]
    rows.sort(key=lambda row: (-((row['attacker']['count'] or 0)
                                 + (row['target']['count'] or 0)),
                               str(row['simulator_id'])))
    return rows


def _parse_id_list(raw, field, subject, fallback):
    """The ids to answer for individually, in the order they were named.

    Parsed before anything else a tool does, so a malformed filter costs no
    request against a 120-second timeout.
    """
    if _is_blank_input(raw):
        return []
    if isinstance(raw, (list, tuple)):
        tokens = [str(token).strip() for token in raw]
    else:
        tokens = [token.strip() for token in str(raw).split(',')]
    named, seen = [], set()
    for token in tokens:
        if not token:
            continue
        if token not in seen:
            seen.add(token)
            named.append(token)
    if not named:
        raise ValueError(f"{field} was given but named no {subject}. {fallback}")
    return named


def _simulator_disposition(step, role, simulator_id):
    """What this step says about one named simulator in one role.

    Four answers, none readable as another. Absence from the map is not a zero:
    the step never offered this simulator in this role, which is a different
    fact from offering it and measuring nothing.
    """
    mapping = step[f'{role}_offered']
    if simulator_id not in mapping:
        return {'state': 'not_in_step', 'count': None}
    count = mapping[simulator_id]
    if not is_computed_count(count):
        return {'state': 'not_computed', 'count': None}
    if count == 0:
        return {'state': 'measured_zero', 'count': 0}
    return {'state': 'contributes', 'count': count}


def _project_simulation_counts(steps, named_simulator_ids, steps_submitted):
    """"How many simulations, and which simulators produce them?" — nothing else.

    Three data fields per step and three structural ones. The structural keys
    are what make the numbers honest: without them a missing count reads as a
    zero, which would report a scenario nobody scored as a scenario that runs
    nothing.
    """
    projected = []
    for step in steps:
        view = {
            'step_index': step['step_index'],
            'simulation_count': step['simulation_count'],
            'counts_computed': step['counts_computed'],
            'is_limit_reached': step['is_limit_reached'],
            'listing_omitted': step['listing_omitted'],
            'simulators_offered': step['simulators_offered'],
        }
        # Absent rather than empty past the cap: an empty list would read as a
        # step whose simulators were looked at and found to produce nothing.
        if not step['listing_omitted']:
            view['simulator_rows'] = _simulator_rows(step)
        if named_simulator_ids:
            view['asked_about'] = {
                simulator_id: {
                    role: _simulator_disposition(step, role, simulator_id)
                    for role in ('attacker_simulators', 'target_simulators')
                }
                for simulator_id in named_simulator_ids
            }
        projected.append(view)

    computed = [s['simulation_count'] for s in projected if s['counts_computed']]
    return {
        'counts_mode': 'runnable',
        'steps': projected,
        'steps_returned': len(projected),
        'steps_submitted': steps_submitted,
        # A reply shorter than the plan means evaluation stopped early. Only
        # knowable when this side held the step list; the passthrough forms are
        # resolved server-side, so `steps_submitted` is None and no claim is made.
        'steps_truncated': bool(steps_submitted is not None
                                and len(projected) < steps_submitted),
        'total_simulations': sum(computed) if computed else None,
        'steps_scored': len(computed),
        'asked_about': list(named_simulator_ids),
        'hint_to_agent': COUNTS_HINT,
    }


def sb_get_scenario_simulation_counts(
    console: str = "default",
    scenario=None,
    scenario_id: str = None,
    test_id: str = None,
    simulator_ids: str = None,
) -> Dict[str, Any]:
    """How many simulations a scenario would produce, and which simulators produce them.

    Scores a scenario against the fleet as it stands without running it, and
    changes nothing. Constraints are never evaluated: this answer renders none,
    and asking for them is the single most expensive thing this endpoint can be
    asked to do. Every input form costs exactly one request - nothing here
    resolves an id by listing the console.

    Args:
        console: SafeBreach console identifier
        scenario: An ad-hoc scenario body, as JSON text or a parsed dict
        scenario_id: A saved plan's numeric id, resolved by the endpoint itself
        test_id: A planRunId, scoring whatever scenario that run executed
        simulator_ids: Comma-separated simulators to answer for individually

    Returns:
        Per-step simulation counts with the contributing simulators in each role.

    Raises:
        ValueError: If not exactly one input names what to score, if
            scenario_id is not numeric, if the scenario has no steps, or if
            the statistics API rejects the body.
    """
    named_simulator_ids = _parse_id_list(
        simulator_ids, 'simulator_ids', 'simulator',
        "Leave it out to list the step's own simulators.")
    body, steps_submitted = _statistics_plan_body(scenario, scenario_id, test_id)
    payload = _fetch_scenario_statistics(console, body)
    steps = [_shape_statistics_step(step)
             for step in _normalize_statistics_steps(payload)]
    return _project_simulation_counts(steps, named_simulator_ids, steps_submitted)



# ---------------------------------------------------------------------------
# plan/statistics — what in a scenario will not run, and why
# ---------------------------------------------------------------------------

BLOCKED_ATTACKS_CAP = 50
CONSTRAINT_NODES_CAP = 3

SIDE_KEYS = (('attackerConstraints', 'attacker'), ('targetConstraints', 'target'))

# Only `reason` is guaranteed on a constraint leaf. These are the fields the
# validators attach alongside it, relayed where present and never invented.
DETAIL_FIELDS = ('values', 'expected', 'actual', 'got', 'required', 'schemaErrors', 'value')

BLOCKED_HINT = (
    "Reports only what will not run at all — an attack or simulator the console scored "
    "at exactly zero. An entity that runs on fewer simulators than were offered is "
    "reduced, not blocked, and is deliberately not listed. Nothing is removed from the "
    "scenario; acting on this report belongs to whoever holds the configuration. For how "
    "many simulations the scenario produces, call get_scenario_simulation_counts. Nothing "
    "is cached here, so re-call after any change to the scenario."
)

# The unscoped hint's "reduced, not blocked" clause is false under a simulator scope —
# an attack that ran elsewhere but produced nothing here is exactly that, and is listed.
# Leaving the clause in place would have the answer contradict its own footnote.
BLOCKED_HINT_SCOPED = (
    "Scoped to the named simulator(s): the per-step list is what produced nothing ON "
    "them, so it includes attacks that ran elsewhere in the scenario and excludes "
    "scenario-wide zeros recorded against other machines. It is therefore NOT a subset "
    "of the unscoped list — call without simulator_ids for what runs nowhere at all. "
    "The verdict and every total stay scenario-wide and count only scenario-wide zeros. "
    "Nothing is removed from the scenario; acting on this report belongs to whoever holds "
    "the configuration. For how many simulations the scenario produces, call "
    "get_scenario_simulation_counts. Nothing is cached here, so re-call after any change."
)


def _normalize_blocked_steps(payload):
    """The counts and the constraints exactly as the console reported them.

    ``moves`` is kept here, unlike the counts path that drops it: a blocked
    attack *is* that map reading zero, and it is also what tells a block apart
    from a reduction. ``simulators`` is the attacker-union-target map, which is
    the only sound denominator for a blocked simulator.
    """
    steps = []
    for index, step in enumerate(payload.get('steps') or []):
        count = step.get('simulationCount')
        steps.append({
            'step_index': index,
            'simulation_count': count,
            'counts_computed': is_computed_count(count),
            'is_limit_reached': bool(step.get('isLimitReached')),
            'moves': {str(k): v for k, v in (step.get('moves') or {}).items()},
            'simulators': dict(step.get('simulators') or {}),
            'constraints': step.get('simulatorConstraints') or {},
        })
    return steps


def _constraint_leaves(constraints):
    """Every (side, simulator, move, code) pairing the console recorded.

    Both levels are read defensively: when evaluation stops early the sentinel
    step carries ``simulatorConstraints: {}`` with neither side sub-key, and the
    single-simulation rerun path creates them lazily.
    """
    for key, side in SIDE_KEYS:
        for simulator_id, by_move in (constraints.get(key) or {}).items():
            for move_id, leaves in (by_move or {}).items():
                for leaf in leaves or ():
                    code = (leaf or {}).get('reason')
                    if code:
                        yield side, simulator_id, str(move_id), code, leaf


def _leaf_detail(leaf):
    """What a validator attached beside the reason, where it attached anything."""
    return {field: leaf[field] for field in DETAIL_FIELDS
            if leaf.get(field) not in (None, [], {})}


def _shape_blocked_step(step):
    """Group the step's constraints by attack and by simulator in one pass.

    One traversal rather than two: ``getAllConstraints=true`` makes every
    validator run against the full node set, so the raw structure is large
    enough that walking it twice is the difference that matters.
    """
    by_attack, by_simulator = {}, {}
    for side, simulator_id, move_id, code, leaf in _constraint_leaves(step['constraints']):
        detail = _leaf_detail(leaf)

        codes = by_attack.setdefault(move_id, {})
        entry = codes.setdefault(code, {'sides': set(), 'simulators': set(), 'detail': {}})
        entry['sides'].add(side)
        entry['simulators'].add(simulator_id)
        entry['detail'] = entry['detail'] or detail

        codes = by_simulator.setdefault(simulator_id, {})
        entry = codes.setdefault(code, {'sides': set(), 'moves': set(), 'detail': {}})
        entry['sides'].add(side)
        entry['moves'].add(move_id)
        entry['detail'] = entry['detail'] or detail

    shaped = dict(step)
    shaped['by_attack'] = by_attack
    shaped['by_simulator'] = by_simulator
    return shaped


def _scored_zero(mapping):
    """Ids the console measured at exactly zero — never the ones it never measured."""
    return sorted(key for key, count in mapping.items()
                  if is_computed_count(count) and count == 0)


def _excluded_simulator_ids(step):
    """Simulators the console constrained but never scored.

    Offline, disabled and unapproved nodes are seeded into the constraint map —
    carrying ``simulator_is_offline`` on every move — but are never seeded into
    the count map under ``includeDisabled=false``. Absent is therefore a third
    state, and reporting it as blocked would call every switched-off machine
    incompatible.
    """
    return sorted(sid for sid in step['by_simulator'] if sid not in step['simulators'])


def _attack_blockers(step, attack_id, only_simulators=None):
    """The codes cited against one attack, worst-reach first.

    ``only_simulators`` narrows to the codes recorded against those machines,
    which is what turns a line from "why this runs nowhere" into "why this will
    not run HERE". ``simulator_count`` stays the code's full reach either way: it
    describes how far the constraint extends, and rescoping it to the named
    machines would silently answer a different question.
    """
    blockers = [
        {'code': code, 'side': sorted(entry['sides']),
         'simulator_count': len(entry['simulators']), 'detail': entry['detail']}
        for code, entry in step['by_attack'].get(attack_id, {}).items()
        if only_simulators is None or (entry['simulators'] & only_simulators)
    ]
    blockers.sort(key=lambda blocker: (-blocker['simulator_count'], blocker['code']))
    return blockers


def _attacks_blocked_on(step, simulator_ids):
    """Every attack the console recorded a constraint against on a named machine.

    Deliberately **independent of the attack's scenario-wide count**: an attack
    that ran elsewhere still produced nothing *here*, and "what will not run on
    this machine" is the question the filter asks. Conversely a scenario-wide zero
    citing none of the named machines is absent — it is not blocked *here*.

    So the scoped list is not a subset of the unscoped one; it answers a different
    question about a narrower subject. The scenario-wide totals and the verdict are
    what stay invariant, and they continue to count only scenario-wide zeros.
    """
    return sorted(attack_id for attack_id, codes in step['by_attack'].items()
                  if any(entry['simulators'] & simulator_ids
                         for entry in codes.values()))


def _blocked_simulator_disposition(steps, simulator_id):
    """What the whole scenario says about one named simulator.

    Precedence is ``ran`` > ``blocked`` > ``excluded`` > ``not_computed`` >
    ``absent``. Steps can offer different fleets, so one machine can be excluded
    in one step and scored zero in another: evidence of contribution outranks
    evidence of non-contribution, and appearing in any count map outranks being
    absent from all of them. Reporting a machine the console scored somewhere as
    switched-off would be the same false positive the three-state model exists to
    prevent, one level up.
    """
    ran, blocked, excluded, offered = None, False, False, False
    for step in steps:
        in_counts = simulator_id in step['simulators']
        if not in_counts and simulator_id not in step['by_simulator']:
            continue
        offered = True
        if not in_counts:
            # Constrained but never scored: switched off, not incompatible.
            excluded = True
            continue
        count = step['simulators'][simulator_id]
        if not is_computed_count(count):
            continue
        if count > 0:
            ran = count if ran is None else max(ran, count)
        else:
            blocked = True
    if ran is not None:
        return {'state': 'ran', 'count': ran}
    if blocked:
        return {'state': 'blocked', 'count': 0}
    if excluded:
        return {'state': 'excluded', 'count': None}
    if offered:
        return {'state': 'not_computed', 'count': None}
    return {'state': 'absent', 'count': None}


def _attack_code_tally(step, attack_ids, only_simulators=None):
    """How many blocked attacks each constraint code accounts for.

    Replaces the per-attack list once that list would be truncated. A tally
    accounts for every blocked attack where a fifty-of-sixty sample accounts for
    fifty, and it surfaces what a wall of near-identical lines buries — which
    reason is behind most of them.

    No validator detail is carried. A row stands for many attacks, and the
    detail fields belong to whichever leaf happened to be recorded first, so one
    ``required``/``actual`` pair would speak for attacks that need not share it.
    Detail stays on the per-attack lines below the cap, where it is exact.
    """
    tally = {}
    for attack_id in attack_ids:
        for code, entry in step['by_attack'].get(attack_id, {}).items():
            if only_simulators is not None and not (entry['simulators'] & only_simulators):
                continue
            row = tally.setdefault(code, {'code': code, 'sides': set(), 'attack_count': 0})
            row['sides'] |= entry['sides']
            row['attack_count'] += 1
    rows = [{'code': row['code'], 'side': sorted(row['sides']),
             'attack_count': row['attack_count']} for row in tally.values()]
    rows.sort(key=lambda row: (-row['attack_count'], row['code']))
    return rows


def _named_attack_answer(step, disposition, attack_id):
    """A named attack's scenario-wide verdict, plus why it runs nowhere.

    Blockers are attached only when the attack runs nowhere in the *whole*
    scenario and this step scored it at zero. Both halves matter. An attack that
    ran somewhere has constraints recorded against the simulators that did not
    run it, and hanging those off a line that reads "ran, 240 simulations" would
    offer an explanation for a failure that did not happen.

    This is what keeps ``attack_ids`` useful once the per-attack list is
    summarised away: it is the only remaining route to an exact reason.
    """
    answer = dict(disposition)
    count = step['moves'].get(attack_id)
    if disposition['state'] == 'blocked' and is_computed_count(count) and count == 0:
        answer['blockers'] = _attack_blockers(step, attack_id)
    return answer


def _simulator_groups(step, simulator_ids):
    """Blocked simulators reported per constraint code rather than per simulator.

    Sixty nodes eliminated by three codes is three lines, not sixty. Only the
    names are capped; the count in each group is exact.
    """
    groups, explained = {}, set()
    for simulator_id in simulator_ids:
        for code, entry in step['by_simulator'].get(simulator_id, {}).items():
            explained.add(simulator_id)
            key = (code, tuple(sorted(entry['sides'])))
            group = groups.setdefault(key, {
                'code': code, 'side': list(key[1]),
                'simulator_ids': [], 'detail': entry['detail'],
            })
            group['simulator_ids'].append(simulator_id)

    rendered = []
    for group in groups.values():
        names = sorted(group['simulator_ids'])
        group['simulator_count'] = len(names)
        group['simulator_ids'] = names[:CONSTRAINT_NODES_CAP]
        rendered.append(group)
    rendered.sort(key=lambda group: (-group['simulator_count'], group['code']))
    return rendered, sorted(set(simulator_ids) - explained)


def _attack_disposition(steps, attack_id):
    """What the whole scenario says about one named attack.

    Ran outranks blocked: an attack scored zero in one step and 240 in another
    ran, and the answer must not depend on which step the scenario lists first.
    """
    ran, blocked, offered = None, False, False
    for step in steps:
        if attack_id not in step['moves']:
            continue
        offered = True
        count = step['moves'][attack_id]
        if not is_computed_count(count):
            continue
        if count > 0:
            ran = count if ran is None else max(ran, count)
        else:
            blocked = True
    if ran is not None:
        return {'state': 'ran', 'count': ran}
    if blocked:
        return {'state': 'blocked', 'count': 0}
    if offered:
        return {'state': 'not_computed', 'count': None}
    return {'state': 'absent', 'count': None}


def _verdict_summary(state, attacks, simulators, scored, returned):
    """The verdict as a sentence, with the unscored steps never written off."""
    if state == 'not_evaluated':
        return ("No step was scored, so nothing can be said about what will run. "
                "This is not a clean result.")
    if state == 'partially_evaluated':
        return (f"{scored} of {returned} step(s) were scored. Across those, {attacks} "
                f"attack(s) and {simulators} simulator(s) contribute nothing; the "
                "unscored steps were not examined.")
    if state == 'blocked':
        return (f"{attacks} attack(s) and {simulators} simulator(s) contribute nothing "
                "in this scenario.")
    return "Every attack and simulator in this scenario contributes at least one simulation."


def _blocked_verdict(steps):
    """Decided by whether counts were computed, never by whether the lists are empty.

    A report that stopped early empties both lists by construction, so a verdict
    read off their length would call a scenario nobody scored a scenario with
    nothing wrong. Counts are over distinct entities scenario-wide: one attack
    blocked in three steps is one attack.
    """
    scored = [step for step in steps if step['counts_computed']]
    attacks, simulators = set(), set()
    for step in scored:
        attacks.update(_scored_zero(step['moves']))
        simulators.update(_scored_zero(step['simulators']))

    if not scored:
        state = 'not_evaluated'
    elif len(scored) < len(steps):
        state = 'partially_evaluated'
    elif attacks or simulators:
        state = 'blocked'
    else:
        state = 'clean'

    return {
        'state': state,
        'blocked_attack_count': len(attacks),
        'blocked_simulator_count': len(simulators),
        'steps_scored': len(scored),
        'steps_returned': len(steps),
        'summary': _verdict_summary(state, len(attacks), len(simulators),
                                    len(scored), len(steps)),
    }


def _cited_catalog(catalog, codes):
    """One entry per code this answer cites, relayed verbatim from the console.

    Narrowed to what was actually rendered, so a caller is never handed the
    whole vocabulary to explain a handful of blockers. Nothing here is authored
    on this side: a code the console did not describe stays undescribed.
    """
    supplied = catalog or {}
    return {code: dict(supplied.get(code) or {}) for code in sorted(codes)}


def _project_blocked_entities(steps, catalog, named_attack_ids, named_simulator_ids=()):
    """What will not run, and why — nothing about how much will.

    The verdict is computed first, over the unfiltered report, so narrowing what
    is shown can never narrow what is claimed. ``named_simulator_ids`` narrows
    only the per-step attack listing; the verdict, every total and both
    simulator-side sections stay scenario-wide, because those are the frame that
    tells a caller whether the machine they named is even in play.
    """
    verdict = _blocked_verdict(steps)
    dispositions = {attack_id: _attack_disposition(steps, attack_id)
                    for attack_id in named_attack_ids}
    simulator_answers = {simulator_id: _blocked_simulator_disposition(steps, simulator_id)
                         for simulator_id in named_simulator_ids}
    scope = set(named_simulator_ids)

    projected, cited = [], set()
    for step in steps:
        view = {
            'step_index': step['step_index'],
            'counts_computed': step['counts_computed'],
            'is_limit_reached': step['is_limit_reached'],
        }
        if step['counts_computed']:
            blocked_attacks = _scored_zero(step['moves'])
            view['blocked_attacks_total'] = len(blocked_attacks)

            # An excluded node is seeded into the constraint map against EVERY move,
            # so leaving one in the scope would drag the whole step into the listing
            # — including alongside a healthy machine that blocks one attack. They
            # are dropped from the match set first, and the list is withheld only
            # when that empties it. Either way the machine is reported as switched
            # off rather than as incompatible with everything.
            withheld = [simulator_id for simulator_id in named_simulator_ids
                        if simulator_id in _excluded_simulator_ids(step)]
            effective = scope - set(withheld)
            if scope and not effective:
                view['blocked_attacks_withheld'] = withheld
                listed, only = [], None
            elif scope:
                listed = _attacks_blocked_on(step, effective)
                only = effective
                # The denominator changes with the question: scoped, the honest
                # comparison is against the attacks this step holds, not against
                # the scenario-wide blocked count the list is no longer a subset of.
                view['attacks_in_step'] = len(step['moves'])
            else:
                listed, only = blocked_attacks, None

            if 'blocked_attacks_withheld' not in view:
                view['blocked_attacks_listed'] = len(listed)
                view['blocked_attacks_scoped'] = bool(scope)
                # The tally is built whether or not it is rendered: it is also where
                # the cited codes come from, and taking those from the rendered rows
                # instead would shrink the catalog exactly when it does the most work.
                tally = _attack_code_tally(step, listed, only_simulators=only)
                if len(listed) > BLOCKED_ATTACKS_CAP:
                    # Absent, not empty — an empty list would read as "looked and
                    # found nothing" rather than "summarised instead of listed".
                    view['blocked_attack_codes'] = tally
                else:
                    view['blocked_attacks'] = [
                        {'attack_id': attack_id,
                         'blockers': _attack_blockers(step, attack_id, only_simulators=only)}
                        for attack_id in listed
                    ]
                cited.update(row['code'] for row in tally)

            groups, unexplained = _simulator_groups(step, _scored_zero(step['simulators']))
            view['blocked_simulators'] = groups
            view['blocked_simulators_total'] = len(_scored_zero(step['simulators']))
            view['blocked_simulators_unexplained'] = unexplained

            excluded, _ = _simulator_groups(step, _excluded_simulator_ids(step))
            view['excluded_simulators'] = excluded
            view['excluded_simulators_total'] = len(_excluded_simulator_ids(step))

            for group in groups + excluded:
                cited.add(group['code'])
        if named_attack_ids:
            view['asked_about'] = {
                attack_id: _named_attack_answer(step, dispositions[attack_id], attack_id)
                for attack_id in named_attack_ids
            }
        if named_simulator_ids:
            # Scenario-wide, so identical on every step — carried per step anyway so
            # an empty scoped list is never read alone. Silence is the failure mode
            # here: a caller who names a healthy machine and sees nothing must not
            # conclude the scenario is clean.
            view['asked_about_simulators'] = dict(simulator_answers)
        projected.append(view)

    return {
        'verdict': verdict,
        'steps': projected,
        'asked_about': list(named_attack_ids),
        'asked_about_simulators': list(named_simulator_ids),
        'attacks_summarised': any('blocked_attack_codes' in view for view in projected),
        'constraint_catalog': _cited_catalog(catalog, cited),
        # None and {} are different facts: an older console supplies no catalog
        # at all, a current one can supply an empty one.
        'catalog_supplied': catalog is not None,
        'hint_to_agent': BLOCKED_HINT_SCOPED if named_simulator_ids else BLOCKED_HINT,
    }


def sb_get_scenario_blocked_entities(
    console: str = "default",
    scenario=None,
    scenario_id: str = None,
    test_id: str = None,
    attack_ids: str = None,
    simulator_ids: str = None,
) -> Dict[str, Any]:
    """What in a scenario will not run at all, and the constraints cited against it.

    Scores a scenario against the fleet as it stands without running it, and
    changes nothing. Reports every attack and simulator the console measured at
    exactly zero; an entity that merely runs on fewer simulators than were
    offered is reduced, not blocked, and is not listed.

    Constraints are requested here, which is the expensive half of this
    endpoint, and every reason is asked for rather than only the first — a
    simulator eliminated by several rules is worth more than its alphabetically
    earliest one. The caps and the per-code grouping are what keep that
    affordable.

    Args:
        console: SafeBreach console identifier
        scenario: An ad-hoc scenario body, as JSON text or a parsed dict
        scenario_id: A saved plan's numeric id, resolved by the endpoint itself
        test_id: A planRunId, scoring whatever scenario that run executed
        attack_ids: Comma-separated attacks to answer for individually
        simulator_ids: Comma-separated simulators to scope the blocked-attack
            listing to — only attacks blocked ON them are listed, each showing
            only the codes cited on them. Narrows what is listed, never what is
            counted.

    Returns:
        A scenario-wide verdict, and per step what contributes nothing and why.

    Raises:
        ValueError: If not exactly one input names what to score, if
            scenario_id is not numeric, if the scenario has no steps, or if
            the statistics API rejects the body.
    """
    named_attack_ids = _parse_id_list(
        attack_ids, 'attack_ids', 'attack',
        "Leave it out to report every blocked attack in the scenario.")
    named_simulator_ids = _parse_id_list(
        simulator_ids, 'simulator_ids', 'simulator',
        "Leave it out to report what is blocked anywhere in the scenario.")
    body, _ = _statistics_plan_body(scenario, scenario_id, test_id)
    payload = _fetch_scenario_statistics(console, body, get_constraints=True,
                                     get_all_constraints=True)
    steps = [_shape_blocked_step(step)
             for step in _normalize_blocked_steps(payload)]
    return _project_blocked_entities(steps, payload.get('constraintCatalog'),
                                     named_attack_ids, named_simulator_ids)

# ---------------------------------------------------------------------------
# quick_run — SAF-31295: Quick Run attack execution
# ---------------------------------------------------------------------------


def _validate_and_resolve_attack_ids(attack_ids_str, console):
    """
    Parse, validate, and resolve attack IDs against the playbook cache.

    Args:
        attack_ids_str: Comma-separated attack IDs string
        console: SafeBreach console identifier

    Returns:
        Tuple of (parsed_ids: list[int], name_map: dict[int, str])
        name_map maps attack ID → attack name (empty on cache failure)

    Raises:
        ValueError: If input is empty, contains non-integers, or IDs not in playbook
    """
    if not attack_ids_str or (isinstance(attack_ids_str, str)
                              and not attack_ids_str.strip()):
        raise ValueError("attack_ids is required and cannot be empty")

    # Parse comma-separated IDs
    raw_parts = attack_ids_str.split(",")
    parsed_ids = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue  # Skip empty segments (e.g., "8849,,217")
        try:
            parsed_ids.append(int(part))
        except ValueError:
            raise ValueError(
                f"invalid attack ID '{part}' — all IDs must be integers"
            )

    if not parsed_ids:
        raise ValueError("attack_ids is required and cannot be empty")

    # Validate against playbook cache
    name_map = {}
    try:
        from safebreach_mcp_playbook.playbook_functions import (
            _get_all_attacks_from_cache_or_api,
        )
        all_attacks = _get_all_attacks_from_cache_or_api(console)
        valid_ids = {a['id'] for a in all_attacks if 'id' in a}
        name_map = {
            a['id']: a.get('name', '') for a in all_attacks if 'id' in a
        }

        invalid_ids = [aid for aid in parsed_ids if aid not in valid_ids]
        if invalid_ids:
            raise ValueError(
                f"Attack IDs not found in playbook: {invalid_ids}"
            )
    except ValueError:
        raise  # Re-raise our own validation errors
    except Exception as e:
        # Playbook cache failure — degrade gracefully (no name resolution)
        logger.warning(f"Playbook cache unavailable: {e}")

    return parsed_ids, name_map


def _build_quick_run_steps(parsed_ids, name_map):
    """
    Construct one step per attack with default connection filters.

    Args:
        parsed_ids: List of validated attack IDs
        name_map: Dict mapping attack ID → name (may be empty)

    Returns:
        List of step dicts ready for the statistics/queue APIs
    """
    import uuid as uuid_module

    steps = []
    for attack_id in parsed_ids:
        attack_name = name_map.get(attack_id, f"Attack {attack_id}")
        steps.append({
            "uuid": str(uuid_module.uuid4()),
            "name": attack_name,
            "attacksFilter": {
                "playbook": {
                    "operator": "is",
                    "values": [attack_id],
                    "name": "playbook",
                }
            },
            "targetFilter": {
                "connection": {
                    "operator": "is",
                    "values": [True],
                    "name": "connection",
                }
            },
            "attackerFilter": {
                "connection": {
                    "operator": "is",
                    "values": [True],
                    "name": "connection",
                }
            },
            "systemFilter": {},
        })
    return steps


def _default_quick_run_name(steps):
    """
    Build the default Quick Run test name from the attacks being queued.

    Args:
        steps: Step dicts that will actually be queued

    Returns:
        Name following the Playbook UI convention ("Quick Run - <attack>")
    """
    names = [step.get("name") for step in steps if step.get("name")]
    if not names:
        return f"Quick Run ({len(steps)} attacks)"
    if len(names) == 1:
        return f"Quick Run - {names[0]}"
    return f"Quick Run - {names[0]} +{len(names) - 1} more"


def _apply_quick_run_overrides(steps, overrides, parsed_ids):
    """
    Apply per-attack simulator overrides to constructed steps.

    Each override maps an attack ID (string) to a dict with 'target' and
    optionally 'attacker' simulator UUID lists. If only 'target' is provided,
    attackerFilter is set to the same as targetFilter (host attack assumption).

    Args:
        steps: List of step dicts (modified in place)
        overrides: Dict mapping attack ID strings to override dicts
        parsed_ids: List of valid attack IDs (for validation)

    Raises:
        ValueError: If an override references an attack ID not in parsed_ids
    """
    parsed_ids_set = set(parsed_ids)
    # Build attack_id → step index mapping
    step_by_attack = {}
    for i, step in enumerate(steps):
        attack_id = step["attacksFilter"]["playbook"]["values"][0]
        step_by_attack[attack_id] = i

    for attack_id_str, override in overrides.items():
        attack_id = int(attack_id_str)
        if attack_id not in parsed_ids_set:
            raise ValueError(
                f"simulator_overrides references attack ID {attack_id} "
                f"which is not in attack_ids"
            )

        step_idx = step_by_attack[attack_id]
        step = steps[step_idx]

        target_uuids = override.get("target", [])
        attacker_uuids = override.get("attacker")

        # Build target filter
        target_filter = {
            "simulators": {
                "operator": "is",
                "values": target_uuids,
                "name": "simulators",
            }
        }
        step["targetFilter"] = target_filter

        # Build attacker filter — infer from target if not provided
        if attacker_uuids is not None:
            step["attackerFilter"] = {
                "simulators": {
                    "operator": "is",
                    "values": attacker_uuids,
                    "name": "simulators",
                }
            }
        else:
            step["attackerFilter"] = target_filter


def sb_quick_run(
    attack_ids: str,
    console: str = "default",
    test_name: str = None,
    all_connected: bool = False,
    simulator_overrides: str = None,
    evaluate: bool = True,
) -> Dict[str, Any]:
    """
    Construct and execute a Quick Run test from explicit playbook attack IDs.

    Creates one step per attack with default all-connected simulator filters.
    Supports per-attack simulator overrides and a global all_connected toggle.
    Defaults to evaluate=True — evaluates the test without queuing.

    Args:
        attack_ids: Comma-separated playbook attack IDs (integers)
        console: SafeBreach console identifier (default: "default")
        test_name: Custom test name (optional, auto-generated if not provided)
        all_connected: Global override — all connected simulators (default: False)
        simulator_overrides: JSON string for per-attack simulator targeting
        evaluate: If True (default), evaluate without queuing

    Returns:
        Dict with status='evaluating' (evaluation) or status='queued' (execution)

    Raises:
        ValueError: If attack_ids invalid, not found, or overrides malformed
    """
    # Fail-fast: parse JSON inputs before any API calls
    parsed_overrides = None
    if simulator_overrides is not None:
        try:
            parsed_overrides = json.loads(simulator_overrides)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid simulator_overrides JSON: {e}")

    # Phase 2: Input validation and step construction
    parsed_ids, name_map = _validate_and_resolve_attack_ids(attack_ids, console)
    steps = _build_quick_run_steps(parsed_ids, name_map)

    # Phase 3: Simulator overrides

    if parsed_overrides and not all_connected:
        _apply_quick_run_overrides(steps, parsed_overrides, parsed_ids)

    # Phase 4: Statistics pre-flight
    step_stats = _get_scenario_statistics(
        steps, console, include_constraints=evaluate
    )
    step_counts = [s.get('simulationCount', 0) for s in step_stats]
    total_predicted = sum(step_counts)
    empty_steps = [i + 1 for i, c in enumerate(step_counts) if c == 0]

    # Evaluate: return prediction without queuing
    if evaluate:
        # Build contextual hint based on results
        if total_predicted == 0:
            hint = (
                "All attacks produce 0 simulations. Check simulator availability "
                "with get_console_simulators, or try simulator_overrides with "
                "specific simulator UUIDs."
            )
        elif empty_steps:
            hint = (
                f"{len(empty_steps)} attack(s) will produce 0 simulations. "
                "You can proceed (they will be skipped), provide "
                "simulator_overrides for those attacks, or remove them. "
                "To execute, call again with evaluate=False."
            )
        elif total_predicted > 1000:
            hint = (
                f"High simulation count ({total_predicted:,}). Consider using "
                "simulator_overrides to target specific simulators and reduce "
                "the count. To execute as-is, call again with evaluate=False."
            )
        else:
            hint = "To execute, call again with evaluate=False."

        return {
            'status': 'evaluating',
            'attack_ids': parsed_ids,
            'steps': steps,
            'predicted_simulations': total_predicted,
            'predicted_per_step': step_counts,
            'step_stats': step_stats,
            'empty_steps': empty_steps,
            'step_count': len(steps),
            'hint_to_agent': hint,
        }

    # Execution validation
    if total_predicted == 0:
        raise ValueError(
            f"Quick Run would produce 0 simulations across all "
            f"{len(steps)} attacks. No matching simulators found."
        )

    # Filter out 0-sim steps for partial execution
    skipped_attacks = []
    if empty_steps:
        exec_steps = []
        for i, step in enumerate(steps):
            if step_counts[i] > 0:
                exec_steps.append(step)
            else:
                attack_id = step["attacksFilter"]["playbook"]["values"][0]
                skipped_attacks.append(attack_id)
        steps = exec_steps

    # Build DAG for remaining steps
    actions, edges = _build_linear_dag(steps)

    # Build queue payload
    effective_test_name = test_name or _default_quick_run_name(steps)
    payload = {
        "plan": {
            "name": effective_test_name,
            "steps": steps,
            "systemTags": [],
            "actions": actions,
            "edges": edges,
        }
    }

    # Rate limiting gates
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "quick_run")

    # Submit to queue
    api_response = _submit_to_queue(payload, console)

    # Record successful action
    rate_limiter.record_action(caller_id, "quick_run")

    # Extract response data
    data = api_response.get('data', {})
    resp_steps = data.get('steps', [])

    queued_hint = (
        f"Test queued. Use get_test_details with test_id "
        f"'{data.get('planRunId', '')}' to track execution progress. "
        f"Use manage_test to pause, resume, or cancel."
    )
    if skipped_attacks:
        queued_hint += (
            f" Note: {len(skipped_attacks)} attack(s) were skipped "
            f"(0 simulations): {skipped_attacks}."
        )

    result = {
        'status': 'queued',
        'test_id': data.get('planRunId', ''),
        'test_name': data.get('name', effective_test_name),
        'attack_ids': parsed_ids,
        'step_count': len(resp_steps),
        'step_run_ids': [s.get('stepRunId', '') for s in resp_steps],
        'predicted_simulations': total_predicted,
        'predicted_per_step': step_counts,
        'step_stats': step_stats,
        'empty_steps': empty_steps,
        'skipped_attacks': skipped_attacks,
        'hint_to_agent': queued_hint,
    }

    logger.info(
        f"Successfully queued Quick Run "
        f"(test_id: {result['test_id']}, attacks: {len(parsed_ids)}, "
        f"steps queued: {result['step_count']})"
    )

    return result


def sb_run_scenario(
    scenario_id: str,
    console: str = "default",
    test_name: str = None,
    allow_partial_steps: bool = False,
    step_overrides: str = None,
    evaluate: bool = False,
    verbose_failures: bool = False,
) -> Dict[str, Any]:
    """
    Run a scenario (OOB or custom plan) via the orchestrator queue API.

    Two-turn workflow for non-ready scenarios:
    1. Call without step_overrides → returns diagnostic if not ready
    2. Call with step_overrides (JSON string) → augments and runs

    Args:
        scenario_id: UUID (OOB) or integer string (custom plan)
        console: SafeBreach console identifier (default: "default")
        test_name: Custom name for the test (optional, defaults to scenario name)
        allow_partial_steps: If False (default), refuse if any step produces 0 simulations.
        step_overrides: JSON string mapping step numbers (1-indexed) to filter overrides.
            Example: '{"1": {"targetFilter": {"os": {"operator": "is", "values": ["WINDOWS"]}}}}'
        evaluate: If True, predict simulation counts without actually queuing the test.

    Returns:
        If ready (or made ready via overrides): dict with test_id, status='queued', etc.
        If not ready and no overrides: dict with status='not_ready', diagnostic info.

    Raises:
        ValueError: If scenario_id is invalid, not found, or step_overrides JSON is invalid
        Exception: For API errors
    """
    if not scenario_id or (isinstance(scenario_id, str) and not scenario_id.strip()):
        raise ValueError("scenario_id is required and cannot be empty")

    # Parse step_overrides JSON if provided
    parsed_overrides = None
    if step_overrides is not None:
        try:
            parsed_overrides = json.loads(step_overrides)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid step_overrides JSON: {e}")

    scenario_id = str(scenario_id).strip()

    # Lookup: try OOB scenarios first, then custom plans
    scenario = None
    is_custom_plan = False

    all_scenarios = _fetch_all_scenarios(console)
    for s in all_scenarios:
        if str(s.get('id')) == scenario_id:
            scenario = s
            break

    if scenario is None:
        all_plans = _fetch_all_plans(console)
        for p in all_plans:
            if str(p.get('id')) == scenario_id:
                scenario = p
                is_custom_plan = True
                break

    if scenario is None:
        raise ValueError(f"Scenario '{scenario_id}' not found")

    # Apply step overrides if provided (deep copy to avoid mutating cached data)
    import copy
    scenario = copy.deepcopy(scenario)
    if parsed_overrides:
        # Expand "default" key into all missing steps that lack explicit overrides
        default_override = parsed_overrides.pop('default', None)
        if default_override:
            pre_diag = diagnose_scenario_readiness(scenario)
            for step_info in pre_diag.get('missing_steps', []):
                step_num_str = str(step_info['step_number'])
                if step_num_str not in parsed_overrides:
                    parsed_overrides[step_num_str] = default_override
        _apply_step_overrides(scenario, parsed_overrides)

    # Check readiness — return diagnostic if not ready (two-turn workflow)
    diagnostic = diagnose_scenario_readiness(scenario)
    if not diagnostic['ready']:
        return {
            'status': 'not_ready',
            'scenario_id': scenario_id,
            'scenario_name': scenario.get('name', ''),
            'source_type': 'custom' if is_custom_plan else 'oob',
            'diagnostic': diagnostic,
        }

    # Statistics pre-flight: predict simulation counts per step
    # Include constraints for evaluate to diagnose zero-simulation steps
    step_stats = _get_scenario_statistics(scenario['steps'], console,
                                          include_constraints=evaluate,
                                          verbose_failures=verbose_failures)
    step_counts = [s['simulationCount'] for s in step_stats]
    total_predicted = sum(step_counts)
    empty_steps = [
        i + 1 for i, count in enumerate(step_counts) if count == 0
    ]

    # evaluate: return prediction without queuing (before validation — the point is to preview)
    if evaluate:
        logger.info(
            f"Evaluating test for scenario '{scenario.get('name')}' ({scenario_id}): "
            f"predicted {total_predicted} simulations, empty steps: {empty_steps}"
        )
        return {
            'status': 'evaluating',
            'scenario_id': scenario_id,
            'scenario_name': scenario.get('name', ''),
            'source_type': 'custom' if is_custom_plan else 'oob',
            'predicted_simulations': total_predicted,
            'predicted_per_step': step_counts,
            'step_stats': step_stats,
            'empty_steps': empty_steps,
            'step_count': len(scenario.get('steps', [])),
        }

    # Validate simulation counts (only for actual runs, not evaluate)
    if total_predicted == 0:
        step_names = [s.get('name', f'Step {i+1}') for i, s in enumerate(scenario['steps'])]
        raise ValueError(
            f"Scenario '{scenario.get('name', scenario_id)}' would produce 0 simulations "
            f"across all {len(step_counts)} steps. No matching simulators or attacks found. "
            f"Steps: {step_names}"
        )

    if empty_steps and not allow_partial_steps:
        step_details = []
        for idx in empty_steps:
            step_name = scenario['steps'][idx - 1].get('name', f'Step {idx}')
            step_details.append(f"Step {idx} ({step_name})")
        raise ValueError(
            f"Scenario '{scenario.get('name', scenario_id)}' has steps with 0 simulations: "
            f"{', '.join(step_details)}. "
            f"Set allow_partial_steps=True to run anyway with partial coverage, "
            f"or check simulator availability."
        )

    effective_test_name = test_name or scenario['name']

    logger.info(
        f"Running scenario '{scenario['name']}' ({scenario_id}) on console: {console} "
        f"(predicted: {total_predicted} simulations, empty steps: {empty_steps})"
    )

    # Build payload for queue API — different structure for OOB vs custom plans
    if is_custom_plan and not parsed_overrides:
        # Ready custom plans without overrides: just send planId
        payload = {
            "plan": {
                "name": effective_test_name,
                "planId": scenario['id'],
                "systemTags": scenario.get('systemTags') or []
            }
        }
    else:
        # OOB scenarios: relay full payload with steps + DAG
        # Content-manager API returns None for actions, edges, systemTags, and step
        # UUIDs. Queue API requires all of these — generate when missing.
        steps = scenario['steps']

        actions = scenario.get('actions')
        edges = scenario.get('edges')

        if not actions or not edges:
            actions, edges = _build_linear_dag(steps)
        else:
            # Ensure UUIDs exist even when actions/edges are provided
            import uuid as uuid_module
            for step in steps:
                if not step.get('uuid'):
                    step['uuid'] = str(uuid_module.uuid4())

        plan_body = {
            "name": effective_test_name,
            "steps": steps,
            "systemTags": scenario.get('systemTags') or [],
            "actions": actions,
            "edges": edges
        }

        # originalScenarioId only applies to OOB scenarios (content-manager UUID)
        if not is_custom_plan:
            plan_body["originalScenarioId"] = scenario['id']

        payload = {"plan": plan_body}

    # Rate limiting gate — check before queuing (after evaluate/not_ready early returns)
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "run_scenario")

    api_response = _submit_to_queue(payload, console)

    # Extract data from response
    data = api_response.get('data', {})
    steps = data.get('steps', [])

    result = {
        'test_id': data.get('planRunId', ''),
        'test_name': data.get('name', effective_test_name),
        'scenario_id': scenario_id,
        'scenario_name': scenario['name'],
        'source_type': 'custom' if is_custom_plan else 'oob',
        'step_count': len(steps),
        'step_run_ids': [s.get('stepRunId', '') for s in steps],
        'predicted_simulations': total_predicted,
        'predicted_per_step': step_counts,
        'step_stats': step_stats,
        'empty_steps': empty_steps,
        'status': 'queued',
    }

    # Rate limiting gate — record after successful queue
    rate_limiter.record_action(caller_id, "run_scenario")

    logger.info(
        f"Successfully queued scenario '{scenario['name']}' "
        f"(test_id: {result['test_id']}, steps: {result['step_count']})"
    )

    return result


# ---------------------------------------------------------------------------
# manage_test — SAF-29969: Test lifecycle management (pause/resume/cancel)
# ---------------------------------------------------------------------------


def _get_test_state(test_id: str, console: str) -> str:
    """
    Fetch the current state of a test by consulting the orchestrator queue
    first (real-time), falling back to the data API (eventually consistent).

    Args:
        test_id: Test execution ID (planRunId)
        console: SafeBreach console identifier

    Returns:
        Status string: "RUNNING", "PAUSED", "CANCELED", "COMPLETED", etc.

    Raises:
        requests.exceptions.RequestException: On API error
    """
    from safebreach_mcp_core.queue_state import get_orchestrator_test_state

    # Phase 1: orchestrator queue (real-time for active tests)
    orch_state = get_orchestrator_test_state(test_id, console)
    if orch_state is not None:
        return orch_state

    logger.info(
        "Test '%s' not found in orchestrator queue — "
        "falling back to data API", test_id
    )

    # Phase 2: data API (terminal / historical tests)
    data_base = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    url = f"{data_base}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    response = requests.get(url, headers=headers, timeout=30)
    check_rbac_response(response)
    return response.json().get('status', 'UNKNOWN')


def _set_test_state(test_id: str, action: str, console: str) -> Dict[str, Any]:
    """
    Change a running test's state via the orchestrator API.

    Args:
        test_id: Test execution ID (planRunId), e.g. "1776488350786.15"
        action: Lifecycle action — "cancel", "pause", or "resume"
        console: SafeBreach console identifier

    Returns:
        Dict with test_id, action, and status="success"

    Raises:
        requests.exceptions.RequestException: On API error
    """
    base_url = get_api_base_url(console, 'orchestrator')
    account_id = get_api_account_id(console)
    auth_headers = get_auth_headers_for_console(console)

    try:
        if action == "cancel":
            url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}"
            headers = {**auth_headers}
            response = requests.delete(url, headers=headers, timeout=30)
        elif action in ("pause", "resume"):
            url = f"{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}/state"
            headers = {"Content-Type": "application/json", **auth_headers}
            response = requests.put(
                url, headers=headers, json={"status": action}, timeout=120
            )
        else:
            raise ValueError(
                f"Invalid action '{action}'. Valid actions: pause, resume, cancel"
            )

        check_rbac_response(response)
        logger.info(f"Test {test_id} {action} successful")
    except requests.exceptions.RequestException as e:
        logger.error(f"{action.capitalize()} test {test_id} failed: {e}")
        raise

    return {"test_id": test_id, "action": action, "status": "success"}


def _append_test_note(
    test_id: str, action: str, reason: str, console: str
) -> Dict[str, Any]:
    """
    Append a timestamped note to a test's comment field (best-effort).

    Reads existing comment via GET, concatenates new note, writes back via PUT.
    The data API comment field is NOT additive — must read-then-append.

    Args:
        test_id: Test execution ID (planRunId)
        action: Lifecycle action that was performed (pause/resume/cancel)
        reason: User-provided reason for the action
        console: SafeBreach console identifier

    Returns:
        Dict with note_status ("success" or "failed") and note text or error
    """
    try:
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)
        url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        # Step 1: Read existing comment
        response = requests.get(url, headers=headers, timeout=30)
        check_rbac_response(response)
        existing_comment = response.json().get('comment') or ""

        # Step 2: Format new note
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        new_note = f"[{timestamp} UTC] Test {action}: {reason}"

        # Step 3: Concatenate
        if existing_comment:
            combined = f"{existing_comment}\n{new_note}"
        else:
            combined = new_note

        # Step 4: Write back
        response = requests.put(
            url, headers=headers, json={"comment": combined}, timeout=30
        )
        check_rbac_response(response)

        logger.info(f"Note appended to test {test_id}: {new_note}")
        return {"note_status": "success", "note": new_note}

    except Exception as e:
        logger.warning(f"Failed to append note to test {test_id}: {e}")
        return {"note_status": "failed", "note_error": str(e)}


def _fetch_test_summary(test_id: str, console: str) -> Dict[str, Any]:
    """
    Fetch test summary from the data API.

    Args:
        test_id: Test execution ID (planRunId)
        console: SafeBreach console identifier

    Returns:
        Raw JSON dict from GET /testsummaries/{test_id}

    Raises:
        ValueError: If test is not found (404)
        requests.exceptions.RequestException: On other API errors
    """
    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    response = requests.get(url, headers=headers, timeout=30)
    try:
        check_rbac_response(response)
    except Exception:
        if hasattr(response, 'status_code') and response.status_code == 404:
            raise ValueError(f"Test '{test_id}' not found")
        raise

    return response.json()


def _fetch_test_storage_info(test_id: str, console: str) -> Optional[Dict[str, Any]]:
    """
    Fetch storage impact data for a test from the detailedTestSummaries API.
    Best-effort — returns None on any error.

    Args:
        test_id: Test execution ID (planRunId)
        console: SafeBreach console identifier

    Returns:
        Dict with space_freed_bytes, events_freed_bytes, current_usage_bytes,
        usage_limit_bytes — or None on error.
    """
    try:
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)
        url = (
            f"{base_url}/api/data/v1/accounts/{account_id}"
            f"/detailedTestSummaries?planRunIds={test_id}"
        )
        headers = {"accept": "application/json", **get_auth_headers_for_console(console)}

        response = requests.get(url, headers=headers, timeout=30)
        check_rbac_response(response)
        data = response.json()

        if not isinstance(data, list) or len(data) == 0:
            return None

        item = data[0]
        breakdown = item.get('testSizeBreakdown', {})
        return {
            "space_freed_bytes": breakdown.get('executionsHistorySize', 0),
            "events_freed_bytes": breakdown.get('integrationLogIndexSize', 0),
            "current_usage_bytes": item.get('historyIndexSizeInBytes', 0),
            "usage_limit_bytes": item.get('historyIndexLimitSizeInBytes', 0),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch storage info for test {test_id}: {e}")
        return None


def _fetch_storage_stats(console: str) -> Optional[Dict[str, Any]]:
    """
    Fetch platform-wide storage utilization stats. Best-effort.

    Args:
        console: SafeBreach console identifier

    Returns:
        Dict with tests_on_disk_bytes, tests_limit_bytes, tests_on_disk_count,
        tests_limit_count, last_cleanup_date, events_index_bytes — or None on error.
    """
    try:
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)
        url = f"{base_url}/api/data/v1/accounts/{account_id}/dbStorageStats"
        headers = {"accept": "application/json", **get_auth_headers_for_console(console)}

        response = requests.get(url, headers=headers, timeout=30)
        check_rbac_response(response)
        data = response.json()

        return {
            "tests_on_disk_bytes": data.get('executionsHistoryIndexSizeInBytes', 0),
            "tests_limit_bytes": data.get('executionsHistoryLimitSizeInBytes', 0),
            "tests_on_disk_count": data.get('executionsHistoryIndexCount', 0),
            "tests_limit_count": data.get('executionsHistoryLimitIndexesCount', 0),
            "last_cleanup_date": data.get('lastTestsCleanupDate'),
            "events_index_bytes": data.get('logHistoryIndexSizeInBytes', 0),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch storage stats for {console}: {e}")
        return None


def sb_delete_test(
    test_id: str,
    console: str,
    reason: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Delete a test from history (SAF-29972). Only terminal tests allowed.

    Args:
        test_id: Test execution ID (planRunId)
        console: SafeBreach console identifier
        reason: Mandatory reason for the deletion (audit trail)
        dry_run: If True (default), return preview without deleting

    Returns:
        Dict with test_id, action, status, and preview/deletion info
    """
    if not reason or not str(reason).strip():
        raise ValueError(
            "reason is required for delete — provide a justification "
            "for the permanent removal of this test."
        )

    # State pre-check — only terminal tests can be deleted
    current_state = _get_test_state(test_id, console).upper()
    terminal_states = {"CANCELED", "COMPLETED", "FAILED"}
    if current_state not in terminal_states:
        raise ValueError(
            f"Cannot delete a {current_state.lower()} test. "
            "Use manage_test with action='cancel' first, then delete."
        )

    # Fetch test summary for planName and preview data
    summary = _fetch_test_summary(test_id, console)
    plan_name = summary.get('originalPlan', {}).get('name', 'Unknown')
    final_status = summary.get('finalStatus', {})
    simulation_count = sum(final_status.values()) if final_status else 0

    preview = {
        "test_name": plan_name,
        "status": summary.get('status', current_state),
        "simulation_count": simulation_count,
        "start_time": summary.get('startTime'),
        "end_time": summary.get('endTime'),
    }

    if dry_run:
        # Enrich preview with storage savings (best-effort)
        storage_info = _fetch_test_storage_info(test_id, console)
        if storage_info is not None:
            preview['storage_savings'] = storage_info

        return {
            "test_id": test_id, "action": "delete", "status": "dry_run",
            "dry_run": True, "preview": preview,
            "hint_to_agent": (
                "This is a preview. To permanently delete this test, call "
                "manage_test again with dry_run=False. This action is irreversible."
            ),
        }

    # Execute delete — rate limit, DELETE API, storage stats
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "manage_test")

    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    delete_url = f"{base_url}/api/data/v1/accounts/{account_id}/tests/{test_id}"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    response = requests.delete(
        delete_url, headers=headers,
        json={"id": test_id, "planName": plan_name}, timeout=30
    )
    check_rbac_response(response)

    rate_limiter.record_action(caller_id, "manage_test")
    logger.info(f"Test {test_id} deleted. Reason: {reason}")

    # Post-delete storage stats (best-effort)
    storage_stats = _fetch_storage_stats(console)

    return {
        "test_id": test_id, "action": "delete", "status": "deleted",
        "deleted_test_name": plan_name, "reason": reason,
        "storage_stats": storage_stats,
        "hint_to_agent": (
            "Test permanently deleted. Use get_tests to see remaining tests."
        ),
    }


def sb_manage_test(
    test_id: str,
    action: str,
    console: str = "default",
    reason: str = None,
    dry_run: bool = None,
) -> Dict[str, Any]:
    """
    Manage a test's lifecycle — pause, resume, cancel, or delete.

    Args:
        test_id: Test execution ID (planRunId), e.g. "1776488350786.15"
        action: Lifecycle action — "pause", "resume", "cancel", or "delete"
        console: SafeBreach console identifier (default: "default")
        reason: Reason for the action. Required for delete, optional for others.
        dry_run: Only for delete — if True (default), preview without deleting.

    Returns:
        Dict with test_id, action, status, and optional note/preview info
    """
    if not test_id or not str(test_id).strip():
        raise ValueError("test_id is required and cannot be empty")

    valid_actions = ["pause", "resume", "cancel", "delete"]
    if action not in valid_actions:
        raise ValueError(
            f"Invalid action '{action}'. Valid actions: pause, resume, cancel, delete"
        )

    # Delete dispatches to dedicated function (SAF-29972)
    if action == "delete":
        if dry_run is None:
            dry_run = True
        return sb_delete_test(test_id, console, reason, dry_run)

    logger.info(f"Managing test {test_id}: action={action}, console={console}")

    # State pre-check — SAF-31111: validate transition before API call.
    # Uses orchestrator GET /queue (real-time) with data API fallback.
    current_state = _get_test_state(test_id, console).upper()
    terminal_states = {"CANCELED", "COMPLETED"}

    # Idempotent quick-returns and invalid transition checks
    if action == "cancel":
        if current_state in terminal_states:
            status_key = f"already_{current_state.lower()}"
            return {
                "test_id": test_id, "action": action, "status": status_key,
                "was_already": True, "current_state": current_state,
                "hint_to_agent": (
                    f"Test is already {current_state.lower()}. No action needed. "
                    "Use get_test_details to view results."
                ),
            }
    elif action == "pause":
        if current_state == "PAUSED":
            return {
                "test_id": test_id, "action": action, "status": "already_paused",
                "was_already": True, "current_state": current_state,
                "hint_to_agent": (
                    "Test is already paused. Use manage_test with action='resume' "
                    "to continue, or action='cancel' to abort."
                ),
            }
        if current_state in terminal_states:
            raise ValueError(
                f"Cannot pause a {current_state.lower()} test. "
                "The test has already finished."
            )
    elif action == "resume":
        if current_state == "RUNNING":
            return {
                "test_id": test_id, "action": action, "status": "already_running",
                "was_already": True, "current_state": current_state,
                "hint_to_agent": (
                    "Test is already running. Use get_test_details to monitor progress."
                ),
            }
        if current_state in terminal_states:
            raise ValueError(
                f"Cannot resume a {current_state.lower()} test. "
                "The test has already finished."
            )

    # Rate limiting gate — check before mutating
    caller_id = get_caller_identity()
    rate_limiter.check_limit(caller_id, "manage_test")

    result = _set_test_state(test_id, action, console)

    # Rate limiting gate — record after successful state change
    rate_limiter.record_action(caller_id, "manage_test")

    # Append a best-effort timestamped note. Failure does not block the lifecycle
    # action above (which already succeeded).
    #
    # KNOWN BACKEND ISSUE (TODO: investigate + fix server-side): the data API
    # `PUT /testsummaries/{id}` intermittently returns HTTP 500 when the note is
    # appended to a test whose summary was freshly created (right after queue) or is
    # mid-transition (e.g. just-canceled), most visibly under concurrent load. This is
    # a SafeBreach backend API bug — it must be root-caused and fixed in the API, and
    # deliberately should NOT be papered over with retries here or in the MCP E2E tests.
    if reason and reason.strip():
        note_result = _append_test_note(test_id, action, reason, console)
        result.update(note_result)

    hints = {
        "pause": (
            "Test is paused. Use manage_test with action='resume' to continue, "
            "or action='cancel' to abort. Use get_test_details to check current status."
        ),
        "resume": "Test resumed. Use get_test_details to monitor progress.",
        "cancel": (
            "Test cancelled. Partial results may be available via get_test_details."
        ),
    }
    result['hint_to_agent'] = hints.get(action, "")

    return result
