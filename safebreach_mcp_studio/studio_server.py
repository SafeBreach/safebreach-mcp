"""
SafeBreach MCP Studio Server

This server handles Breach Studio operations for SafeBreach MCP, including
validation of custom Python simulation code and saving simulations as drafts.
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
    sb_save_studio_draft,
    sb_get_all_studio_simulations,
    sb_update_studio_draft,
    sb_get_studio_simulation_source,
    sb_run_studio_simulation,
    sb_get_studio_simulation_latest_result
)

logger = logging.getLogger(__name__)


class SafeBreachStudioServer(SafeBreachMCPBase):
    """SafeBreach MCP Studio Server for Breach Studio operations."""

    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Studio Server",
            description="Handles Breach Studio code validation and draft management"
        )

        # Register MCP tools
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tools for Studio operations."""

        @self.mcp.tool(
            name="validate_studio_code",
            description="""Validates custom Python simulation code against SafeBreach Breach Studio requirements.

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
- stderr: Standard error output
- stdout: Standard output details

Example:
validate_studio_code(python_code="def main(system_data, asset, proxy, *args, **kwargs):\\n    pass", console="demo")"""
        )
        def validate_studio_code(
            python_code: str,
            console: str = "default"
        ) -> str:
            """Validate custom Python simulation code."""
            try:
                result = sb_validate_studio_code(python_code, console)

                # Format response
                response_parts = [
                    "## Python Code Validation Result",
                    "",
                    f"**Overall Status:** {'✅ Valid' if result.get('is_valid') else '❌ Invalid'}",
                    f"**Exit Code:** {result.get('exit_code', -1)}",
                    f"**Has Required main() Function:** {'✅ Yes' if result.get('has_main_function') else '❌ No'}",
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
                    response_parts.append("✅ **Code is valid and ready to be saved as a draft.**")
                elif result.get('is_valid') and not result.get('has_main_function'):
                    response_parts.append("⚠️ **Code syntax is valid but missing required main() function signature.**")
                    response_parts.append("   Required: `def main(system_data, asset, proxy, *args, **kwargs):`")
                else:
                    response_parts.append("❌ **Code has validation errors. Please fix them before saving as draft.**")

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Validation error: {e}")
                return f"Validation Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in validate_studio_code: {e}")
                return f"Error validating code: {str(e)}"

        @self.mcp.tool(
            name="save_studio_draft",
            description="""Saves a custom Python simulation as a draft in SafeBreach Breach Studio.

This tool submits the provided Python code and metadata to create a new draft simulation
that can later be published and used in SafeBreach tests.

Parameters:
- name (required): Simulation name (e.g., "Port Scanner", "Credential Dumper")
- python_code (required): The Python code content as a string
- description (optional): Simulation description (default: "")
- timeout (optional): Execution timeout in seconds (default: 300, minimum: 1)
- os_constraint (optional): OS constraint for simulation execution (default: "All")
                           Valid values: "All" (no OS constraint), "WINDOWS", "LINUX", "MAC"
                           - "All": Simulation can run on any operating system (default behavior)
                           - "WINDOWS": Simulation will only run on Windows simulators
                           - "LINUX": Simulation will only run on Linux simulators
                           - "MAC": Simulation will only run on macOS simulators
- parameters (optional): List of parameters accessible in system_data during execution (default: None)
                        Each parameter is a dict with:
                        - name (required): Parameter name for accessing in code
                        - value (required): Parameter value (single value or list for multiple values)
                        - type (optional): "NOT_CLASSIFIED", "PORT", "URI", or "PROTOCOL" (default: "NOT_CLASSIFIED")
                          * PROTOCOL type requires value to be one of 52 valid protocols (TCP, HTTP, SSH, HTTPS, etc.)
                        - display_name (optional): Display name in UI (defaults to name)
                        - description (optional): Parameter description (defaults to "")
                        Examples:
                          Single value: {"name": "port", "value": 8080, "type": "PORT"}
                          Multiple values: {"name": "paths", "value": ["c:\\temp\\file1.txt", "c:\\temp\\file2.txt"]}
                          Protocol: {"name": "proto", "value": "TCP", "type": "PROTOCOL"}
- console (optional): SafeBreach console identifier (default: "default")

Returns draft metadata including:
- draft_id: ID of the created draft (int)
- name: Draft name
- status: Always "draft"
- creation_date: ISO datetime string
- update_date: ISO datetime string
- timeout: Execution timeout
- os_constraint: OS constraint applied
- parameters_count: Number of parameters defined
- target_file_name: Always "target.py"

Example:
save_studio_draft(name="Network Scanner", python_code=code, description="Scans network ports", timeout=300, os_constraint="WINDOWS", parameters=[{"name": "port", "value": 8080, "type": "PORT"}], console="demo")

Note: It's recommended to validate the code using validate_studio_code before saving as draft."""
        )
        def save_studio_draft(
            name: str,
            python_code: str,
            description: str = "",
            timeout: int = 300,
            os_constraint: str = "All",
            parameters: list = None,
            console: str = "default"
        ) -> str:
            """Save a custom Python simulation as a draft."""
            try:
                result = sb_save_studio_draft(
                    name=name,
                    python_code=python_code,
                    description=description,
                    timeout=timeout,
                    os_constraint=os_constraint,
                    parameters=parameters,
                    console=console
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
                    f"**OS Constraint:** {result.get('os_constraint', 'All')}",
                    f"**Parameters:** {result.get('parameters_count', 0)} parameter(s)",
                    f"**Target File:** {result.get('target_file_name', 'target.py')}",
                    f"**Method Type:** {result.get('method_type', 5)}",
                    f"**Origin:** {result.get('origin', 'BREACH_STUDIO')}",
                    "",
                    f"**Created:** {result.get('creation_date', 'Unknown')}",
                    f"**Last Updated:** {result.get('update_date', 'Unknown')}",
                    "",
                    "✅ **Draft saved successfully and can now be published from SafeBreach console.**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Save draft error: {e}")
                return f"Save Draft Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in save_studio_draft: {e}")
                return f"Error saving draft: {str(e)}"

        @self.mcp.tool(
            name="get_all_studio_simulations",
            description="""Retrieves all Studio simulations (both draft and published) from SafeBreach Breach Studio.

This tool lists all custom Python simulations created in Breach Studio, with optional filtering by status, name, and creator.

Parameters:
- console (optional): SafeBreach console identifier (default: "default")
- status_filter (optional): Filter by status - "all", "draft", or "published" (default: "all")
- name_filter (optional): Filter by simulation name (case-insensitive partial match)
- user_id_filter (optional): Filter by user ID who created the simulation

Returns a summary including:
- simulations: List of all simulations with id, name, status, dates, creator, etc.
- total_count: Total number of simulations
- draft_count: Number of draft simulations
- published_count: Number of published simulations

Each simulation includes: id, name, description, status, method_type, timeout, creation_date, update_date, published_date, target_file_name, origin, user_created, user_updated

Example:
get_all_studio_simulations(console="demo", status_filter="draft")
get_all_studio_simulations(console="demo", name_filter="MCP")
get_all_studio_simulations(console="demo", user_id_filter=347729146100002)"""
        )
        def get_all_studio_simulations(
            console: str = "default",
            status_filter: str = "all",
            name_filter: str = None,
            user_id_filter: int = None
        ) -> str:
            """Get all Studio simulations."""
            try:
                result = sb_get_all_studio_simulations(
                    console=console,
                    status_filter=status_filter,
                    name_filter=name_filter,
                    user_id_filter=user_id_filter
                )

                # Format response
                response_parts = [
                    "## Studio Simulations",
                    "",
                    f"**Total Simulations:** {result.get('total_count', 0)}",
                    f"**Draft Simulations:** {result.get('draft_count', 0)}",
                    f"**Published Simulations:** {result.get('published_count', 0)}",
                    ""
                ]

                simulations = result.get('simulations', [])
                if simulations:
                    response_parts.append("### Simulations List")
                    response_parts.append("")
                    for sim in simulations[:10]:  # Show first 10
                        response_parts.append(f"**ID {sim.get('id')}**: {sim.get('name', 'Unnamed')}")
                        response_parts.append(f"- Status: {sim.get('status', 'unknown')}")
                        if sim.get('description'):
                            desc = sim.get('description', '')[:100]
                            response_parts.append(f"- Description: {desc}...")
                        response_parts.append(f"- Created: {sim.get('creation_date', 'Unknown')}")
                        if sim.get('user_created'):
                            response_parts.append(f"- Creator User ID: {sim.get('user_created')}")
                        response_parts.append("")

                    if len(simulations) > 10:
                        response_parts.append(f"... and {len(simulations) - 10} more simulations")
                        response_parts.append("")
                else:
                    response_parts.append("No simulations found.")
                    response_parts.append("")

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Get all simulations error: {e}")
                return f"Get All Simulations Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in get_all_studio_simulations: {e}")
                return f"Error retrieving simulations: {str(e)}"

        @self.mcp.tool(
            name="update_studio_draft",
            description="""Updates an existing Studio draft simulation in SafeBreach Breach Studio.

This tool allows you to modify an existing draft simulation's name, code, description, timeout, OS constraint, and parameters.
Note: Only draft simulations can be updated. Published simulations cannot be modified.

Parameters:
- draft_id (required): ID of the draft simulation to update
- name (required): Updated simulation name
- python_code (required): Updated Python code content as a string
- description (optional): Updated simulation description (default: "")
- timeout (optional): Execution timeout in seconds (default: 300, minimum: 1)
- os_constraint (optional): OS constraint for simulation execution (default: "All")
                           Valid values: "All" (no OS constraint), "WINDOWS", "LINUX", "MAC"
                           - "All": Simulation can run on any operating system (default behavior)
                           - "WINDOWS": Simulation will only run on Windows simulators
                           - "LINUX": Simulation will only run on Linux simulators
                           - "MAC": Simulation will only run on macOS simulators
- parameters (optional): List of parameters accessible in system_data during execution (default: None)
                        Each parameter is a dict with:
                        - name (required): Parameter name for accessing in code
                        - value (required): Parameter value (single value or list for multiple values)
                        - type (optional): "NOT_CLASSIFIED", "PORT", "URI", or "PROTOCOL" (default: "NOT_CLASSIFIED")
                          * PROTOCOL type requires value to be one of 52 valid protocols (TCP, HTTP, SSH, HTTPS, etc.)
                        - display_name (optional): Display name in UI (defaults to name)
                        - description (optional): Parameter description (defaults to "")
                        Examples:
                          Single value: {"name": "port", "value": 8080, "type": "PORT"}
                          Multiple values: {"name": "paths", "value": ["c:\\temp\\file1.txt", "c:\\temp\\file2.txt"]}
                          Protocol: {"name": "proto", "value": "TCP", "type": "PROTOCOL"}
- console (optional): SafeBreach console identifier (default: "default")

Returns updated draft metadata including:
- draft_id: ID of the updated draft
- name: Updated draft name
- status: Always "draft"
- creation_date: Original creation date
- update_date: New update timestamp
- timeout: Execution timeout
- os_constraint: OS constraint applied
- parameters_count: Number of parameters defined

Example:
update_studio_draft(draft_id=10000298, name="Updated Scanner", python_code=updated_code, description="Updated version", os_constraint="LINUX", parameters=[{"name": "port", "value": 443, "type": "PORT"}], console="demo")

Note: Use get_all_studio_simulations to find the draft_id of simulations you want to update."""
        )
        def update_studio_draft(
            draft_id: int,
            name: str,
            python_code: str,
            description: str = "",
            timeout: int = 300,
            os_constraint: str = "All",
            parameters: list = None,
            console: str = "default"
        ) -> str:
            """Update an existing Studio draft simulation."""
            try:
                result = sb_update_studio_draft(
                    draft_id=draft_id,
                    name=name,
                    python_code=python_code,
                    description=description,
                    timeout=timeout,
                    os_constraint=os_constraint,
                    parameters=parameters,
                    console=console
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
                    f"**OS Constraint:** {result.get('os_constraint', 'All')}",
                    f"**Parameters:** {result.get('parameters_count', 0)} parameter(s)",
                    f"**Target File:** {result.get('target_file_name', 'target.py')}",
                    "",
                    f"**Originally Created:** {result.get('creation_date', 'Unknown')}",
                    f"**Last Updated:** {result.get('update_date', 'Unknown')}",
                    "",
                    "✅ **Draft updated successfully and ready to be published from SafeBreach console.**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Update draft error: {e}")
                return f"Update Draft Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in update_studio_draft: {e}")
                return f"Error updating draft: {str(e)}"

        @self.mcp.tool(
            name="get_studio_simulation_source",
            description="""Retrieves the target Python source code for a Studio simulation.

This tool downloads the source code file (target.py) for a specific simulation, whether draft or published.

Parameters:
- simulation_id (required): ID of the simulation to get source code for
- console (optional): SafeBreach console identifier (default: "default")

Returns:
- filename: Name of the source file (typically "target.py")
- content: The complete Python source code as a string

Use cases:
- Review simulation code before publishing
- Download simulation code for local testing or modification
- Compare different versions of simulation code
- Learn from existing simulations by reviewing their implementation

Example:
get_studio_simulation_source(simulation_id=10000298, console="demo")"""
        )
        def get_studio_simulation_source(
            simulation_id: int,
            console: str = "default"
        ) -> str:
            """Get the source code for a Studio simulation."""
            try:
                result = sb_get_studio_simulation_source(
                    simulation_id=simulation_id,
                    console=console
                )

                # Format response
                content = result.get('content', '')
                filename = result.get('filename', 'target.py')

                response_parts = [
                    "## Simulation Source Code",
                    "",
                    f"**Simulation ID:** {simulation_id}",
                    f"**Filename:** {filename}",
                    f"**Size:** {len(content)} bytes",
                    f"**Lines:** {len(content.splitlines())} lines",
                    "",
                    "### Source Code",
                    "",
                    f"```python",
                    content,
                    "```"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Get source error: {e}")
                return f"Get Source Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in get_studio_simulation_source: {e}")
                return f"Error retrieving source code: {str(e)}"

        @self.mcp.tool(
            name="run_studio_simulation",
            description="""Runs a Studio draft simulation on SafeBreach simulators.

This tool queues a Studio simulation for execution on either all connected simulators
or specific simulator IDs. The simulation will be executed as a test and results can
be retrieved using the returned plan_run_id.

Parameters:
- simulation_id (required): ID of the draft simulation to execute
- console (optional): SafeBreach console identifier (default: "default")
- simulator_ids (optional): List of specific simulator UUIDs to run on.
                           If not provided, runs on all connected simulators.
- test_name (optional): Custom name for the test execution.
                       Default: "Studio Simulation Test - {simulation_id}"

Returns:
- plan_run_id: ID of the test execution (use this to retrieve results)
- step_run_id: ID of the step execution
- test_name: Name of the test
- simulation_id: ID of the simulation
- simulator_count: Number of simulators targeted
- priority: Execution priority (typically "low")
- draft: Always True for draft simulations

Use cases:
- Test a draft simulation before publishing
- Run simulations on specific test environments
- Execute custom attack scenarios on selected simulators
- Validate simulation behavior across different OS types

Example (all connected simulators):
run_studio_simulation(simulation_id=10000298, console="demo")

Example (specific simulators):
run_studio_simulation(
    simulation_id=10000298,
    console="demo",
    simulator_ids=["3b6e04fb-828c-4017-84eb-0a898416f5ad", "82f32590-c51e-403a-9912-579af86fd3b9"]
)

Note: After execution, use get_test_details with the returned plan_run_id to retrieve results."""
        )
        def run_studio_simulation(
            simulation_id: int,
            console: str = "default",
            simulator_ids: list = None,
            test_name: str = None
        ) -> str:
            """Run a Studio draft simulation on simulators."""
            try:
                result = sb_run_studio_simulation(
                    simulation_id=simulation_id,
                    console=console,
                    simulator_ids=simulator_ids,
                    test_name=test_name
                )

                # Format response
                response_parts = [
                    "## Simulation Execution Queued",
                    "",
                    f"**Test Name:** {result.get('test_name')}",
                    f"**Simulation ID:** {result.get('simulation_id')}",
                    f"**Plan Run ID:** `{result.get('plan_run_id')}` ✨",
                    f"**Step Run ID:** {result.get('step_run_id')}",
                    "",
                    f"**Target Simulators:** {result.get('simulator_count')}",
                    f"**Priority:** {result.get('priority')}",
                    f"**Draft Mode:** {result.get('draft')}",
                    "",
                    "### Next Steps",
                    "",
                    f"1. Wait for the simulation to complete execution",
                    f"2. Use `get_test_details` with plan_run_id `{result.get('plan_run_id')}` to retrieve results",
                    f"3. Use `get_test_simulations` to see detailed simulation results",
                    "",
                    "✅ **Simulation successfully queued for execution!**"
                ]

                return "\n".join(response_parts)

            except ValueError as e:
                logger.error(f"Run simulation error: {e}")
                return f"Run Simulation Error: {str(e)}"
            except Exception as e:
                logger.error(f"Error in run_studio_simulation: {e}")
                return f"Error running simulation: {str(e)}"

        @self.mcp.tool(
            name="get_studio_simulation_latest_result",
            description="""Retrieves the latest execution results for a Studio simulation by its playbook ID.

This tool queries the execution history to find the most recent runs of a specific Studio simulation,
ordered by start time (newest first). Useful for checking the results of recently executed simulations.

Parameters:
- simulation_id (required): The playbook ID of the Studio simulation
- console (optional): SafeBreach console identifier (default: "default")
- max_results (optional): Maximum number of results to return (default: 1 for latest only)

Returns detailed execution information including:
- Execution status (SUCCESS/FAIL) and final status (missed, stopped, prevented, etc.)
- Test/plan information and timing details
- Attacker and target simulator details
- Parameters used in the execution
- Result codes and security actions
- Labels (e.g., "Draft")

Example (get latest result):
get_studio_simulation_latest_result(simulation_id=10000291, console="demo")

Example (get last 5 results):
get_studio_simulation_latest_result(simulation_id=10000291, console="demo", max_results=5)"""
        )
        def get_studio_simulation_latest_result(
            simulation_id: int,
            console: str = "default",
            max_results: int = 1
        ) -> str:
            """Get the latest execution results for a Studio simulation."""
            try:
                result = sb_get_studio_simulation_latest_result(
                    simulation_id=simulation_id,
                    console=console,
                    max_results=max_results
                )

                # Check if any results found
                if result['total_found'] == 0:
                    return f"## No Execution Results Found\n\nNo execution history found for simulation ID {simulation_id} on console '{console}'."

                # Format response
                response_parts = [
                    "## Studio Simulation Execution Results",
                    "",
                    f"**Simulation ID:** {result['simulation_id']}",
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
                        f"**Execution ID:** {execution['execution_id']}",
                        f"**Job ID:** {execution['job_id']}",
                        "",
                        "#### Status",
                        f"- **Execution Status:** {execution['status']}",
                        f"- **Final Status:** {execution['final_status']}",
                        f"- **Security Action:** {execution['security_action']}",
                        "",
                        "#### Test Information",
                        f"- **Test Name:** {execution['test_name']}",
                        f"- **Plan Name:** {execution['plan_name']}",
                        f"- **Step Name:** {execution['step_name']}",
                        f"- **Plan Run ID:** {execution['plan_run_id']}",
                        "",
                        "#### Timing",
                        f"- **Start Time:** {execution['start_time']}",
                        f"- **End Time:** {execution['end_time']}",
                        "",
                        "#### Simulators",
                        f"- **Attacker:** {execution['attacker']['name']} ({execution['attacker']['os_type']} - {execution['attacker']['ip']})",
                        f"- **Target:** {execution['target']['name']} ({execution['target']['os_type']} - {execution['target']['ip']})",
                        "",
                        "#### Result Details",
                        f"- **Result Code:** {execution['result']['code']}",
                        f"- **Details:** {execution['result']['details']}",
                        "",
                        "#### Additional Info",
                        f"- **Labels:** {', '.join(execution['labels']) if execution['labels'] else 'None'}",
                        f"- **Parameters:** {len(execution['params_summary'])} parameter(s)",
                        f"- **Simulation Events:** {execution['simulation_events_count']} event(s)",
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
                logger.error(f"Error in get_studio_simulation_latest_result: {e}")
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
