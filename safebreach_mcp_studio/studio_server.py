"""
SafeBreach MCP Studio Server

This server handles Breach Studio operations for SafeBreach MCP, including
validation of custom Python attack code and managing attack drafts.
"""

import sys
import os
import logging
from typing import Optional

# Add parent directory to path to import core components
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safebreach_mcp_core import SafeBreachMCPBase
from .studio_functions import (
    sb_validate_studio_code,
    sb_save_studio_attack_draft,
    sb_get_all_studio_attacks,
    sb_update_studio_attack_draft,
    sb_get_studio_attack_source,
    sb_run_studio_attack,
    sb_get_studio_attack_latest_result
)

logger = logging.getLogger(__name__)


class SafeBreachStudioServer(SafeBreachMCPBase):
    """SafeBreach MCP Studio Server for Breach Studio operations."""

    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Studio Server",
            description="Handles Breach Studio code validation and attack draft management"
        )

        # Register MCP tools
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tools for Studio operations."""

        @self.mcp.tool(
            name="validate_studio_code",
            description="""Validates custom Python attack code against SafeBreach Breach Studio requirements.

This tool checks if the Python code contains the required main function signature
'def main(system_data, asset, proxy, *args, **kwargs):' and validates the code
syntax against the SafeBreach Breach Studio API.

Parameters:
- python_code (required): The Python code content as a string to validate
- console (optional): SafeBreach console identifier (default: "default")

Returns validation result with:
- is_valid: Overall validation status (bool)
- has_main_function: Whether required main() signature exists (bool)
- exit_code: Exit code from validator (int)
- validation_errors: List of validation errors
- target_validation: Target-specific API validation results
- attacker_validation: Attacker-specific API validation results (None for host)
- lint_warnings: SB011/SB012 lint warnings for parameters
- stderr: Standard error output
- stdout: Standard output details

Example:
validate_studio_code(python_code="def main(system_data, asset, proxy, *args, **kwargs):\\n    pass", console="demo")
validate_studio_code(python_code=target_code, attacker_code=attacker_code, attack_type="exfil", console="demo")"""
        )
        def validate_studio_code(
            python_code: str,
            console: str = "default",
            attack_type: str = "host",
            attacker_code: str = None,
            target_os: str = "All",
            attacker_os: str = "All",
            parameters: list = None,
        ) -> str:
            """Validate custom Python attack code."""
            try:
                result = sb_validate_studio_code(
                    python_code, console,
                    attack_type=attack_type,
                    attacker_code=attacker_code,
                    target_os=target_os,
                    attacker_os=attacker_os,
                    parameters=parameters,
                )

                # Format response
                response_parts = [
                    "## Python Code Validation Result",
                    "",
                    f"**Attack Type:** {attack_type}",
                    f"**Overall Status:** {'VALID' if result.get('is_valid') else 'INVALID'}",
                    f"**Exit Code:** {result.get('exit_code', -1)}",
                    f"**Has Required main() Function:** {'Yes' if result.get('has_main_function') else 'No'}",
                    ""
                ]

                # Add validation errors if any
                validation_errors = result.get('validation_errors', [])
                if validation_errors:
                    response_parts.extend([
                        "## Validation Errors",
                        ""
                    ])
                    for idx, error in enumerate(validation_errors, 1):
                        response_parts.append(f"{idx}. {error}")
                    response_parts.append("")
                else:
                    response_parts.extend([
                        "**Validation Errors:** None",
                        ""
                    ])

                # Add lint warnings if any
                lint_warnings = result.get('lint_warnings', [])
                if lint_warnings:
                    response_parts.extend([
                        "## Lint Warnings",
                        ""
                    ])
                    for warning in lint_warnings:
                        response_parts.append(f"- [{warning['code']}] {warning['message']}")
                    response_parts.append("")

                # Add attacker validation info for dual-script
                attacker_validation = result.get('attacker_validation')
                if attacker_validation:
                    response_parts.extend([
                        "## Attacker Script Validation",
                        "",
                        f"**Valid:** {'Yes' if attacker_validation.get('is_valid') else 'No'}",
                        ""
                    ])

                # Add stderr if present
                stderr = result.get('stderr', '')
                if stderr:
                    response_parts.extend([
                        "## Standard Error Output",
                        "",
                        f"```\n{stderr}\n```",
                        ""
                    ])

                # Add recommendation
                if result.get('is_valid') and result.get('has_main_function'):
                    response_parts.append("**Code is valid and ready to be saved as a draft.**")
                elif result.get('is_valid') and not result.get('has_main_function'):
                    response_parts.append("**Code syntax is valid but missing required main() function signature.**")
                    response_parts.append("   Required: `def main(system_data, asset, proxy, *args, **kwargs):`")
                else:
                    response_parts.append("**Code has validation errors. Please fix them before saving as draft.**")

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Validation error: {e}")
                return f"Validation Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in validate_studio_code: {e}")
                return f"Error validating code: {str(e)}"

        @self.mcp.tool(
            name="save_studio_attack_draft",
            description="""Saves a custom Python attack as a draft in SafeBreach Breach Studio.

This tool submits the provided Python code and metadata to create a new draft attack
that can later be published and used in SafeBreach tests.

Parameters:
- name (required): Attack name (e.g., "Port Scanner", "Credential Dumper")
- python_code (required): The Python code content as a string (target script)
- description (optional): Attack description (default: "")
- timeout (optional): Execution timeout in seconds (default: 300, minimum: 1)
- target_os (optional): OS constraint for target script (default: "All")
                        Valid values: "All", "WINDOWS", "LINUX", "MAC"
- attack_type (optional): Attack type (default: "host")
                         Valid values: "host" (single script), "exfil", "infil", "lateral" (dual-script)
- attacker_code (optional): Python code for attacker script (required for dual-script types)
- attacker_os (optional): OS constraint for attacker script (default: "All", dual-script only)
- parameters (optional): List of parameters accessible in system_data during execution
- console (optional): SafeBreach console identifier (default: "default")

Returns draft metadata including:
- draft_id, name, status, attack_type, creation_date, update_date, timeout, os_constraint, parameters_count

Example:
save_studio_attack_draft(name="Network Scanner", python_code=code, target_os="WINDOWS", console="demo")
save_studio_attack_draft(name="Exfil Attack", python_code=target_code, attacker_code=attacker_code, attack_type="exfil", console="demo")

Note: It's recommended to validate the code using validate_studio_code before saving as draft."""
        )
        def save_studio_attack_draft(
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
        ) -> str:
            """Save a custom Python attack as a draft."""
            try:
                result = sb_save_studio_attack_draft(
                    name=name,
                    python_code=python_code,
                    description=description,
                    timeout=timeout,
                    target_os=target_os,
                    parameters=parameters,
                    console=console,
                    attack_type=attack_type,
                    attacker_code=attacker_code,
                    attacker_os=attacker_os,
                )

                # Format response
                response_parts = [
                    "## Draft Saved Successfully",
                    "",
                    f"**Draft ID:** {result.get('draft_id', 'Unknown')}",
                    f"**Name:** {result.get('name', 'Unknown')}",
                    f"**Status:** {result.get('status', 'draft')}",
                    f"**Description:** {result.get('description', 'No description') or 'No description'}",
                    "",
                    f"**Timeout:** {result.get('timeout', 300)} seconds",
                    f"**Target OS:** {result.get('os_constraint', 'All')}",
                    f"**Parameters:** {result.get('parameters_count', 0)} parameter(s)",
                    f"**Target File:** {result.get('target_file_name', 'target.py')}",
                    f"**Method Type:** {result.get('method_type', 5)}",
                    f"**Origin:** {result.get('origin', 'BREACH_STUDIO')}",
                    "",
                    f"**Created:** {result.get('creation_date', 'Unknown')}",
                    f"**Last Updated:** {result.get('update_date', 'Unknown')}",
                    "",
                    "**Draft saved successfully and can now be published from SafeBreach console.**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Save draft error: {e}")
                return f"Save Draft Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in save_studio_attack_draft: {e}")
                return f"Error saving draft: {str(e)}"

        @self.mcp.tool(
            name="get_all_studio_attacks",
            description="""Retrieves Studio attacks (both draft and published) from SafeBreach Breach Studio.

Results are paginated with 10 items per page. Supports filtering by status, name, and creator.

Parameters:
- console (optional): SafeBreach console identifier (default: "default")
- page_number (optional): Page number, 0-based (default: 0)
- status_filter (optional): Filter by status - "all", "draft", or "published" (default: "all")
- name_filter (optional): Filter by attack name (case-insensitive partial match)
- user_id_filter (optional): Filter by user ID who created the attack

Returns paginated attacks with metadata including total_attacks, page_number, total_pages, draft_count, published_count.

Example:
get_all_studio_attacks(console="demo", page_number=0, status_filter="draft")"""
        )
        def get_all_studio_attacks(
            console: str = "default",
            page_number: int = 0,
            status_filter: str = "all",
            name_filter: str = None,
            user_id_filter: int = None,
        ) -> str:
            """Get all Studio attacks."""
            try:
                result = sb_get_all_studio_attacks(
                    console=console,
                    status_filter=status_filter,
                    name_filter=name_filter,
                    user_id_filter=user_id_filter,
                    page_number=page_number,
                )

                # Check for pagination error
                if 'error' in result:
                    return f"Pagination Error: {result['error']}"

                page_num = result.get('page_number', 0)
                total_pages = result.get('total_pages', 0)

                # Format response
                response_parts = [
                    f"## Studio Attacks - Page {page_num + 1} of {total_pages}" if total_pages > 0 else "## Studio Attacks",
                    "",
                    f"**Total Attacks:** {result.get('total_attacks', 0)}",
                    f"**Draft Attacks:** {result.get('draft_count', 0)}",
                    f"**Published Attacks:** {result.get('published_count', 0)}",
                    ""
                ]

                attacks = result.get('attacks_in_page', [])
                if attacks:
                    response_parts.append("### Attacks List")
                    response_parts.append("")
                    for attack in attacks:
                        response_parts.append(f"**ID {attack.get('id')}**: {attack.get('name', 'Unnamed')}")
                        response_parts.append(f"- Status: {attack.get('status', 'unknown')}")
                        if attack.get('description'):
                            desc = attack.get('description', '')[:100]
                            response_parts.append(f"- Description: {desc}...")
                        response_parts.append(f"- Created: {attack.get('creation_date', 'Unknown')}")
                        if attack.get('user_created'):
                            response_parts.append(f"- Creator User ID: {attack.get('user_created')}")
                        response_parts.append("")
                else:
                    response_parts.append("No attacks found.")
                    response_parts.append("")

                # Add hint
                hint = result.get('hint_to_agent')
                if hint:
                    response_parts.append(f"*{hint}*")
                    response_parts.append("")

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Get all attacks error: {e}")
                return f"Get All Attacks Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in get_all_studio_attacks: {e}")
                return f"Error retrieving attacks: {str(e)}"

        @self.mcp.tool(
            name="update_studio_attack_draft",
            description="""Updates an existing Studio draft attack in SafeBreach Breach Studio.

This tool allows you to modify an existing draft attack's name, code, description, timeout, OS constraint, and parameters.
Note: Only draft attacks can be updated. Published attacks cannot be modified.

Parameters:
- attack_id (required): ID of the draft attack to update
- name (required): Updated attack name
- python_code (required): Updated target Python code content as a string
- description (optional): Updated attack description (default: "")
- timeout (optional): Execution timeout in seconds (default: 300, minimum: 1)
- target_os (optional): OS constraint for target script (default: "All")
                        Valid values: "All", "WINDOWS", "LINUX", "MAC"
- attack_type (optional): Attack type (default: "host")
                         Valid values: "host", "exfil", "infil", "lateral"
- attacker_code (optional): Python code for attacker script (required for dual-script types)
- attacker_os (optional): OS constraint for attacker script (default: "All", dual-script only)
- parameters (optional): List of parameters accessible in system_data during execution
- console (optional): SafeBreach console identifier (default: "default")

Returns updated draft metadata including:
- draft_id, name, status, attack_type, creation_date, update_date, timeout, os_constraint, parameters_count

Example:
update_studio_attack_draft(attack_id=10000298, name="Updated Scanner", python_code=updated_code, target_os="LINUX", console="demo")
update_studio_attack_draft(attack_id=10000298, name="Updated Exfil", python_code=target_code, attacker_code=attacker_code, attack_type="exfil", console="demo")

Note: Use get_all_studio_attacks to find the attack_id of attacks you want to update."""
        )
        def update_studio_attack_draft(
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
        ) -> str:
            """Update an existing Studio draft attack."""
            try:
                result = sb_update_studio_attack_draft(
                    attack_id=attack_id,
                    name=name,
                    python_code=python_code,
                    description=description,
                    timeout=timeout,
                    target_os=target_os,
                    parameters=parameters,
                    console=console,
                    attack_type=attack_type,
                    attacker_code=attacker_code,
                    attacker_os=attacker_os,
                )

                # Format response
                response_parts = [
                    "## Draft Updated Successfully",
                    "",
                    f"**Draft ID:** {result.get('draft_id', 'Unknown')}",
                    f"**Name:** {result.get('name', 'Unknown')}",
                    f"**Status:** {result.get('status', 'draft')}",
                    f"**Description:** {result.get('description', 'No description') or 'No description'}",
                    "",
                    f"**Timeout:** {result.get('timeout', 300)} seconds",
                    f"**Target OS:** {result.get('os_constraint', 'All')}",
                    f"**Parameters:** {result.get('parameters_count', 0)} parameter(s)",
                    f"**Target File:** {result.get('target_file_name', 'target.py')}",
                    "",
                    f"**Originally Created:** {result.get('creation_date', 'Unknown')}",
                    f"**Last Updated:** {result.get('update_date', 'Unknown')}",
                    "",
                    "**Draft updated successfully and ready to be published from SafeBreach console.**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Update draft error: {e}")
                return f"Update Draft Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in update_studio_attack_draft: {e}")
                return f"Error updating draft: {str(e)}"

        @self.mcp.tool(
            name="get_studio_attack_source",
            description="""Retrieves the source code for a Studio attack (target and optionally attacker scripts).

This tool downloads the source code files for a specific attack, whether draft or published.
For dual-script attacks (exfil, infil, lateral), both target and attacker scripts are returned.

Parameters:
- attack_id (required): ID of the attack to get source code for
- console (optional): SafeBreach console identifier (default: "default")

Returns:
- attack_id: The attack ID
- target: {filename, content} — always present
- attacker: {filename, content} or None — present for dual-script attacks

Example:
get_studio_attack_source(attack_id=10000298, console="demo")"""
        )
        def get_studio_attack_source(
            attack_id: int,
            console: str = "default"
        ) -> str:
            """Get the source code for a Studio attack."""
            try:
                result = sb_get_studio_attack_source(
                    attack_id=attack_id,
                    console=console
                )

                # Format response
                target = result.get('target', {})
                attacker = result.get('attacker')
                target_content = target.get('content', '')
                target_filename = target.get('filename', 'target.py')

                response_parts = [
                    "## Attack Source Code",
                    "",
                    f"**Attack ID:** {attack_id}",
                    f"**Type:** {'Dual-script' if attacker else 'Host (single-script)'}",
                    "",
                    f"### Target Script ({target_filename})",
                    "",
                    f"**Size:** {len(target_content)} bytes | **Lines:** {len(target_content.splitlines())} lines",
                    "",
                    f"```python",
                    target_content,
                    "```"
                ]

                if attacker:
                    attacker_content = attacker.get('content', '')
                    attacker_filename = attacker.get('filename', 'attacker.py')
                    response_parts.extend([
                        "",
                        f"### Attacker Script ({attacker_filename})",
                        "",
                        f"**Size:** {len(attacker_content)} bytes | **Lines:** {len(attacker_content.splitlines())} lines",
                        "",
                        f"```python",
                        attacker_content,
                        "```"
                    ])

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Get source error: {e}")
                return f"Get Source Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in get_studio_attack_source: {e}")
                return f"Error retrieving source code: {str(e)}"

        @self.mcp.tool(
            name="run_studio_attack",
            description="""Runs a Studio draft attack on SafeBreach simulators.

Parameters:
- attack_id (required): ID of the draft attack to execute
- console (optional): SafeBreach console identifier (default: "default")
- target_simulator_ids (optional): List of target simulator UUIDs
- attacker_simulator_ids (optional): List of attacker simulator UUIDs (network attacks)
- all_connected (optional): Run on all connected simulators (default: False)
- test_name (optional): Custom name for the test execution

Either target_simulator_ids or all_connected=True must be provided.

Returns: test_id, attack_id, test_name, status

Example:
run_studio_attack(attack_id=10000298, all_connected=True, console="demo")
run_studio_attack(attack_id=10000298, target_simulator_ids=["uuid1", "uuid2"], console="demo")"""
        )
        def run_studio_attack(
            attack_id: int,
            console: str = "default",
            target_simulator_ids: list = None,
            attacker_simulator_ids: list = None,
            all_connected: bool = False,
            test_name: str = None,
        ) -> str:
            """Run a Studio draft attack on simulators."""
            try:
                result = sb_run_studio_attack(
                    attack_id=attack_id,
                    console=console,
                    target_simulator_ids=target_simulator_ids,
                    attacker_simulator_ids=attacker_simulator_ids,
                    all_connected=all_connected,
                    test_name=test_name,
                )

                # Format response
                response_parts = [
                    "## Attack Execution Queued",
                    "",
                    f"**Test Name:** {result.get('test_name')}",
                    f"**Attack ID:** {result.get('attack_id')}",
                    f"**Test ID:** `{result.get('test_id')}`",
                    f"**Step Run ID:** {result.get('step_run_id')}",
                    f"**Status:** {result.get('status')}",
                    "",
                    "### Next Steps",
                    "",
                    f"1. Wait for the attack to complete execution",
                    f"2. Use `get_test_details` with test_id `{result.get('test_id')}` to retrieve results",
                    f"3. Use `get_test_simulations` to see detailed simulation results",
                    "",
                    "**Attack successfully queued for execution!**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Run attack error: {e}")
                return f"Run Attack Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in run_studio_attack: {e}")
                return f"Error running attack: {str(e)}"

        @self.mcp.tool(
            name="get_studio_attack_latest_result",
            description="""Retrieves the latest execution results for a Studio attack by its playbook ID.

This tool queries the execution history to find the most recent runs of a specific Studio attack,
ordered by start time (newest first). Useful for checking the results of recently executed attacks.

Parameters:
- attack_id (required): The playbook ID of the Studio attack
- console (optional): SafeBreach console identifier (default: "default")
- max_results (optional): Maximum number of results to return (default: 1 for latest only)
- include_logs (optional): Include simulation_steps, logs, and output fields (default: True)

Returns detailed execution information including:
- Execution status and status (missed, stopped, prevented, etc.)
- Test/plan information and timing details
- Attacker and target simulator details
- Parameters used in the execution
- Result codes and security actions
- Simulation steps, logs, and output (when include_logs=True)
- Drift tracking (is_drifted, drift_tracking_code)

Example (get latest result):
get_studio_attack_latest_result(attack_id=10000291, console="demo")

Example (get last 5 results):
get_studio_attack_latest_result(attack_id=10000291, console="demo", max_results=5)

Example (without logs for compact output):
get_studio_attack_latest_result(attack_id=10000291, console="demo", include_logs=False)"""
        )
        def get_studio_attack_latest_result(
            attack_id: int,
            console: str = "default",
            max_results: int = 1,
            include_logs: bool = True
        ) -> str:
            """Get the latest execution results for a Studio attack."""
            try:
                result = sb_get_studio_attack_latest_result(
                    attack_id=attack_id,
                    console=console,
                    max_results=max_results,
                    include_logs=include_logs
                )

                # Check if any results found
                if result['total_found'] == 0:
                    return (f"## No Execution Results Found\n\n"
                            f"No execution history found for attack ID {attack_id} on console '{console}'.")

                # Format response
                response_parts = [
                    "## Studio Attack Execution Results",
                    "",
                    f"**Attack ID:** {result['attack_id']}",
                    f"**Console:** {result['console']}",
                    f"**Total Executions Found:** {result['total_found']}",
                    f"**Showing:** {result['returned_count']} result(s)",
                    ""
                ]

                # Add each execution result
                for idx, execution in enumerate(result['executions'], 1):
                    response_parts.extend([
                        f"### Execution #{idx}" if max_results > 1 else "### Latest Execution",
                        "",
                        f"**Simulation ID:** {execution['simulation_id']}",
                        f"**Job ID:** {execution['job_id']}",
                        "",
                        "#### Status",
                        f"- **Execution Status:** {execution['execution_status']}",
                        f"- **Status:** {execution['status']}",
                        f"- **Security Action:** {execution['security_action']}",
                        "",
                        "#### Test Information",
                        f"- **Test Name:** {execution['test_name']}",
                        f"- **Plan Name:** {execution['plan_name']}",
                        f"- **Step Name:** {execution['step_name']}",
                        f"- **Test ID:** {execution['test_id']}",
                        "",
                        "#### Timing",
                        f"- **Start Time:** {execution['start_time']}",
                        f"- **End Time:** {execution['end_time']}",
                        "",
                        "#### Simulators",
                        f"- **Attacker:** {execution['attacker']['name']} "
                        f"({execution['attacker']['os_type']} - {execution['attacker']['ip']})",
                        f"- **Target:** {execution['target']['name']} "
                        f"({execution['target']['os_type']} - {execution['target']['ip']})",
                        "",
                        "#### Result Details",
                        f"- **Result Code:** {execution['result']['code']}",
                        f"- **Details:** {execution['result']['details']}",
                        "",
                        "#### Drift Tracking",
                        f"- **Is Drifted:** {execution['is_drifted']}",
                        f"- **Drift Tracking Code:** {execution.get('drift_tracking_code', 'N/A')}",
                        "",
                        "#### Additional Info",
                        f"- **Labels:** {', '.join(execution['labels']) if execution['labels'] else 'None'}",
                        f"- **Parameters:** {len(execution['params_summary'])} parameter(s)",
                        f"- **Simulation Events:** {execution['simulation_events_count']} event(s)",
                        ""
                    ])

                    # Add logs/steps/output sections when include_logs is True
                    if include_logs:
                        # Simulation steps
                        steps = execution.get('simulation_steps', [])
                        if steps:
                            response_parts.extend(["#### Simulation Steps", ""])
                            for step in steps:
                                response_parts.append(
                                    f"- [{step.get('timing', '')}] **{step.get('step_name', '')}** "
                                    f"({step.get('status', '')}) on {step.get('node', '')} "
                                    f"- {step.get('details', '')}"
                                )
                            response_parts.append("")

                        # Logs
                        logs = execution.get('logs', '')
                        if logs:
                            response_parts.extend([
                                "#### Logs",
                                "```",
                                logs,
                                "```",
                                ""
                            ])

                        # Output
                        output = execution.get('output', '')
                        if output:
                            response_parts.extend([
                                "#### Output",
                                "```",
                                output,
                                "```",
                                ""
                            ])

                # Add note about more results if available
                if result['has_more']:
                    response_parts.extend([
                        "---",
                        "",
                        f"**Note:** {result['total_found'] - result['returned_count']} more execution(s) available. ",
                        f"Use `max_results={result['total_found']}` to retrieve all results.",
                        ""
                    ])

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Get latest result error: {e}")
                return f"Get Latest Result Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in get_studio_attack_latest_result: {e}")
                return f"Error retrieving execution results: {str(e)}"


def parse_external_config(server_type: str) -> bool:
    """Parse external connection configuration for the server."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'

    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'

    return global_external or server_specific


async def main():
    """Main entry point for the Studio server."""
    logging.basicConfig(level=logging.INFO)

    # Parse external configuration
    allow_external = parse_external_config("studio")
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')

    # Create and run server
    studio_server = SafeBreachStudioServer()
    await studio_server.run_server(port=8004, host=custom_host, allow_external=allow_external)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
