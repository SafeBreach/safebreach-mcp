"""
SafeBreach MCP Data Server

This server handles test and simulation data operations for SafeBreach MCP.
"""

import sys
import os
import logging
from typing import Optional

# Add parent directory to path to import core components
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safebreach_mcp_core import SafeBreachMCPBase
from safebreach_mcp_core.datetime_utils import normalize_timestamp
from .data_functions import (
    sb_get_tests_history,
    sb_get_test_details,
    sb_get_test_simulations,
    sb_get_simulation_details,
    sb_get_security_controls_events,
    sb_get_security_control_event_details,
    sb_get_test_findings_counts,
    sb_get_test_findings_details,
    sb_get_test_drifts,
    sb_get_full_simulation_logs,
    sb_get_simulation_result_drifts,
    sb_get_simulation_status_drifts,
    sb_get_security_control_drifts,
    sb_get_simulation_lineage,
    sb_get_peer_benchmark_score,
)

logger = logging.getLogger(__name__)

class SafeBreachDataServer(SafeBreachMCPBase):
    """SafeBreach MCP Data Server for test and simulation data operations."""
    
    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Data Server",
            description="Handles test and simulation data operations"
        )
        
        # Register MCP tools
        self._register_tools()
    
    def _register_tools(self):
        """Register all MCP tools for data operations."""
        
        @self.mcp.tool(
            name="get_tests_history",
            description="""Returns a filtered and paged history listing of tests executed on a given Safebreach management console.
Supports filtering by test type (validate/propagate), time windows, status, and name patterns. Results are ordered by end time (newest first) by default.
Parameters: console (required), page_number (default 0), test_type ('validate'/'propagate'/None), \
start_date (epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'), \
end_date (epoch ms/seconds or ISO 8601 string),
status_filter ('completed'/'canceled'/'failed'/None), name_filter (partial name match), order_by ('end_time'/'start_time'/'name'/'duration'), order_direction ('desc'/'asc').
Accepts both epoch timestamps and ISO 8601 strings for date parameters."""
        )
        async def get_tests_history_tool(
            console: str = "default",
            page_number: int = 0,
            test_type: Optional[str] = None,
            start_date: Optional[str | int] = None,
            end_date: Optional[str | int] = None,
            status_filter: Optional[str] = None,
            name_filter: Optional[str] = None,
            order_by: str = "end_time",
            order_direction: str = "desc"
        ) -> dict:
            start_date = normalize_timestamp(start_date) if start_date is not None else None
            end_date = normalize_timestamp(end_date) if end_date is not None else None
            return sb_get_tests_history(
                console=console,
                page_number=page_number,
                test_type=test_type,
                start_date=start_date,
                end_date=end_date,
                status_filter=status_filter,
                name_filter=name_filter,
                order_by=order_by,
                order_direction=order_direction
            )
        
        @self.mcp.tool(
            name="get_test_details",
            description="""Returns the full details for a specific test by id executed on a given Safebreach management console.
Always includes simulation status counts (missed, stopped, prevented, detected, logged, no-result, inconsistent) at no extra cost.
Optionally includes drift count via include_drift_count parameter.
WARNING: include_drift_count=True may take a significant amount of time for large tests (proportional to the number of simulations) as it must scan all simulation pages. Only request drift count when specifically needed."""
        )
        async def get_test_details_tool(
            test_id: str,
            console: str = "default",
            include_drift_count: bool = False
        ) -> dict:
            return sb_get_test_details(test_id, console, include_drift_count)
        
        @self.mcp.tool(
            name="get_test_simulations",
            description="""Returns a filtered and paged listing of simulations executed in the context of a specific test by id on a given Safebreach management console.
Supports filtering by status, time windows, playbook attack ID, playbook attack name patterns, and drift analysis. Results are ordered by execution time (newest first) by default.
Each simulation includes a drift_tracking_code — a lineage identifier grouping all executions of the same \
attack configuration across test runs. Pass it to get_simulation_lineage to trace how results changed over time.
Parameters: console (required), test_id (required), page_number (default 0), status_filter (simulation status), \
start_time (epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'), \
end_time (epoch ms/seconds or ISO 8601 string),
playbook_attack_id_filter (exact match), playbook_attack_name_filter (partial name match), drifted_only (bool, default False, filter only drifted simulations).
Accepts both epoch timestamps and ISO 8601 strings for time parameters.
For broader drift analysis across a time window (not limited to a single test), see \
get_simulation_result_drifts and get_simulation_status_drifts."""
        )
        async def get_test_simulations_tool(
            test_id: str,
            console: str = "default",
            page_number: int = 0,
            status_filter: Optional[str] = None,
            start_time: Optional[str | int] = None,
            end_time: Optional[str | int] = None,
            playbook_attack_id_filter: Optional[str] = None,
            playbook_attack_name_filter: Optional[str] = None,
            drifted_only: bool = False
        ) -> dict:
            start_time = normalize_timestamp(start_time) if start_time is not None else None
            end_time = normalize_timestamp(end_time) if end_time is not None else None
            return sb_get_test_simulations(
                test_id=test_id,
                console=console,
                page_number=page_number,
                status_filter=status_filter,
                start_time=start_time,
                end_time=end_time,
                playbook_attack_id_filter=playbook_attack_id_filter,
                playbook_attack_name_filter=playbook_attack_name_filter,
                drifted_only=drifted_only
            )
        
        @self.mcp.tool(
            name="get_test_simulation_details",
            description="""Returns the full details of a specific simulation by id on a given Safebreach management console.
Supports optional extensions for detailed analysis: MITRE ATT&CK techniques, basic attack logs by host from simulation events, and drift analysis information.
When include_drift_info=True, returns drift_tracking_code for drifted simulations. Pass this code to \
get_simulation_lineage to see the full execution timeline across all test runs.
Parameters: console (required), simulation_id (required), include_mitre_techniques (bool, default False),
include_basic_attack_logs (bool, default False), include_drift_info (bool, default False).
Note: For comprehensive execution logs (~40KB), use get_full_simulation_logs tool instead.
For time-window-based drift trends, see get_simulation_result_drifts and get_simulation_status_drifts."""
        )
        async def get_test_simulation_details_tool(
            simulation_id: str,
            console: str = "default",
            include_mitre_techniques: bool = False,
            include_basic_attack_logs: bool = False,
            include_drift_info: bool = False
        ) -> dict:
            return sb_get_simulation_details(
                simulation_id,
                console,
                include_mitre_techniques=include_mitre_techniques,
                include_basic_attack_logs=include_basic_attack_logs,
                include_drift_info=include_drift_info
            )
        
        @self.mcp.tool(
            name="get_security_controls_events",
            description="""Returns a filtered and paginated list of security control events for a specific test and simulation.
These events represent the security controls (products) that SafeBreach was able to correlate to the malicious activity simulation.
Supports filtering by product name, vendor name, security action, connector name, source host, and destination host.
Parameters: console (required), test_id (required), simulation_id (required), page_number (default 0), 
product_name_filter (partial match), vendor_name_filter (partial match), security_action_filter (partial match), 
connector_name_filter (partial match), source_host_filter (partial match), destination_host_filter (partial match)"""
        )
        async def get_security_controls_events_tool(
            test_id: str,
            simulation_id: str,
            console: str = "default",
            page_number: int = 0,
            product_name_filter: Optional[str] = None,
            vendor_name_filter: Optional[str] = None,
            security_action_filter: Optional[str] = None,
            connector_name_filter: Optional[str] = None,
            source_host_filter: Optional[str] = None,
            destination_host_filter: Optional[str] = None
        ) -> dict:
            return sb_get_security_controls_events(
                test_id=test_id,
                simulation_id=simulation_id,
                console=console,
                page_number=page_number,
                product_name_filter=product_name_filter,
                vendor_name_filter=vendor_name_filter,
                security_action_filter=security_action_filter,
                connector_name_filter=connector_name_filter,
                source_host_filter=source_host_filter,
                destination_host_filter=destination_host_filter
            )
        
        @self.mcp.tool(
            name="get_security_control_event_details",
            description="""Returns detailed information for a specific security control event.
Provides comprehensive data to help SecOps engineers understand the causality between SafeBreach malicious activity simulation and the event emitted by the security control.
Supports different verbosity levels for context-aware information density.
Parameters: console (required), test_id (required), simulation_id (required), event_id (required), 
verbosity_level (default 'standard', options: 'minimal', 'standard', 'detailed', 'full')"""
        )
        async def get_security_control_event_details_tool(
            test_id: str,
            simulation_id: str,
            event_id: str,
            console: str = "default",
            verbosity_level: str = "standard"
        ) -> dict:
            return sb_get_security_control_event_details(
                test_id=test_id,
                simulation_id=simulation_id,
                event_id=event_id,
                console=console,
                verbosity_level=verbosity_level
            )
        
        @self.mcp.tool(
            name="get_test_findings_counts",
            description="""Returns counts of findings by type for a specific test, with optional filtering by any attribute.
            Findings are the main data points identified by SafeBreach Propagate tests in the customer's environment.
            This function provides a summary view showing how many findings of each type were identified.
            Parameters: console (required), test_id (required), attribute_filter (optional - filter by any finding attribute with partial match)"""
        )
        async def get_test_findings_counts_tool(
            test_id: str,
            console: str = "default",
            attribute_filter: Optional[str] = None
        ) -> dict:
            return sb_get_test_findings_counts(
                test_id=test_id,
                console=console,
                attribute_filter=attribute_filter
            )
        
        @self.mcp.tool(
            name="get_test_findings_details",
            description="""Returns detailed findings for a specific test with filtering and pagination by any attribute.
            Findings are the main data points identified by SafeBreach Propagate tests, similar to a Penetration Test report.
            This function provides the full details of findings with support for filtering by any attribute (type, source, severity, hostname, IP addresses, etc.).
            Parameters: console (required), test_id (required), page_number (default 0), attribute_filter (optional - filter by any finding attribute with partial match)"""
        )
        async def get_test_findings_details_tool(
            test_id: str,
            console: str = "default",
            page_number: int = 0,
            attribute_filter: Optional[str] = None
        ) -> dict:
            return sb_get_test_findings_details(
                test_id=test_id,
                console=console,
                page_number=page_number,
                attribute_filter=attribute_filter
            )
        
        @self.mcp.tool(
            name="get_test_drifts",
            description="""Analyzes drift between the given test and the most recent previous test with the same name.
            Compares simulation results to identify: (1) simulations exclusive to baseline test, (2) simulations exclusive to current test,
            (3) simulations with matching drift_tracking_code but different status values.
            Returns comprehensive drift analysis with security impact classification and detailed metadata for further investigation.
            Each drifted simulation includes a drift_tracking_code — use get_simulation_lineage to trace its full history across all test runs.
            Parameters: console (required), test_id (required - the test to analyze for drifts).
            Note: For time-window-based drift analysis across all tests (not comparing two specific test runs), \
use get_simulation_result_drifts or get_simulation_status_drifts instead."""
        )
        async def get_test_drifts_tool(
            test_id: str,
            console: str = "default"
        ) -> dict:
            return sb_get_test_drifts(
                test_id=test_id,
                console=console
            )

        @self.mcp.tool(
            name="get_full_simulation_logs",
            description="""Retrieves comprehensive low-level execution logs for a specific simulation (~40KB detailed traces per node).

IMPORTANT: Use this tool to diagnose why a simulation was stopped, failed, returned no-result, or produced unexpected results.
The logs contain granular execution traces NOT available in get_simulation_details or get_studio_attack_latest_result.
When a simulation status is "stopped" or "no-result", always retrieve these logs before concluding root cause.

Primary use cases: Deep troubleshooting, forensic analysis, step-by-step execution analysis, detailed log correlation. \
Use drift_tracking_code from the parent simulation to correlate logs across test runs via get_simulation_lineage.
Returns a role-based structure:
- 'target': Contains the target node's full execution data. Null when logs_available is False.
- 'attacker': Present for dual-script attacks (exfil, infil, lateral movement). Null for host-only attacks or when logs_available is False.
- 'logs_available' (bool): True when execution logs are present, False when the API returned empty data (e.g., INTERNAL_FAIL simulations).
- 'logs_status' (str or null): Null when logs are available. Contains an explanatory message when logs_available is False.
- Also includes: simulation_id, test_id, run_id, execution_times, status, attack_info (always present regardless of logs_available).
Each role section contains: node_name, node_id, os_type, os_version, state, logs, simulation_steps, details_summary, error, output, task_status, task_code.
Parameters: simulation_id (required - e.g., '1477531'), test_id (required - planRunId, e.g., '1764165600525.2'), console (required).
Note: Results are cached for 5 minutes. Use get_simulation_details with include_basic_attack_logs for summary-level logs only."""
        )
        async def get_full_simulation_logs_tool(
            simulation_id: str,
            test_id: str,
            console: str = "default"
        ) -> dict:
            return sb_get_full_simulation_logs(
                simulation_id=simulation_id,
                test_id=test_id,
                console=console
            )

        @self.mcp.tool(
            name="get_simulation_result_drifts",
            description="""Returns time-window-based simulation result drift analysis showing transitions between \
blocked (FAIL) and not-blocked (SUCCESS) states.

TWO-PHASE USAGE:
  1. Call WITHOUT drift_key to get a grouped summary of all drift types with counts per transition \
(e.g., fail-success, success-fail). Use this to understand the overall drift landscape.
  2. Call WITH drift_key='<key>' (e.g., 'fail-success') and page_number to paginate through individual \
records in that group.

USE THIS WHEN: You need to analyze how simulation RESULTS (blocked vs not-blocked) changed over a time period \
across all tests. This provides a security POSTURE view — did attacks that were previously blocked become \
unblocked, or vice versa? Each drill-down record includes drift_tracking_code — pass it to \
get_simulation_lineage for the full execution history of that simulation lineage.

DON'T USE FOR:
  - Comparing two specific test runs (use get_test_drifts instead).
  - Filtering drifted simulations within a single test (use get_test_simulations with drifted_only=True).
  - Getting drift details for a single simulation (use get_test_simulation_details with include_drift_info=True).
  - Analyzing security control final status transitions like prevented→logged (use get_simulation_status_drifts).

Parameters:
  console (required): SafeBreach console name.
  window_start (required): epoch ms/seconds or ISO 8601 string (e.g., '2026-03-01T00:00:00Z').
  window_end (required): epoch ms/seconds or ISO 8601 string.
  from_status: Filter by origin result status. Valid: 'FAIL' (blocked), 'SUCCESS' (not blocked).
  to_status: Filter by destination result status. Valid: 'FAIL', 'SUCCESS'.
  drift_type: Filter by drift classification. Valid: 'improvement', 'regression', 'not_applicable'.
  attack_id: Filter by specific playbook attack ID (integer).
  attack_type: Filter by attack type — CASE-SENSITIVE exact match (e.g., 'Suspicious File Creation'). \
Pass '__list__' to discover all valid attack type values on this console. \
Wrong case silently returns zero results, so always use '__list__' first or copy exact values from attack_summary.
  attack_name: Filter by attack name — case-insensitive phrase match (e.g., 'Upload File over SMB').
  drift_key: Drill-down key from summary (e.g., 'fail-success'). Omit for grouped summary.
  page_number: Page number for drill-down mode (default 0, 10 records per page).
  look_back_time: How far back to search for baseline (pre-drift) simulations. \
Accepts epoch ms/seconds or ISO 8601 string. \
Defaults to 7 days before window_start. Increase for attacks that run infrequently (e.g., monthly). \
Decrease for faster responses on busy consoles.
Accepts both epoch timestamps and ISO 8601 strings for all time parameters.
WARNING: This endpoint has no server-side pagination. Large time windows (7+ days) on busy consoles can take \
3+ minutes. Start with a narrow window (1-2 days) and widen only if needed."""
        )
        async def get_simulation_result_drifts_tool(
            console: str,
            window_start: str | int = None,
            window_end: str | int = None,
            from_status: Optional[str] = None,
            to_status: Optional[str] = None,
            drift_type: Optional[str] = None,
            attack_id: Optional[int] = None,
            attack_type: Optional[str] = None,
            attack_name: Optional[str] = None,
            drift_key: Optional[str] = None,
            page_number: int = 0,
            look_back_time: Optional[str | int] = None
        ) -> dict:
            if attack_type == "__list__":
                return sb_get_simulation_result_drifts(
                    console=console, window_start=0, window_end=0, attack_type="__list__")
            window_start = normalize_timestamp(window_start)
            if window_start is None:
                raise ValueError("window_start: invalid or missing timestamp value")
            window_end = normalize_timestamp(window_end)
            if window_end is None:
                raise ValueError("window_end: invalid or missing timestamp value")
            look_back_time = normalize_timestamp(look_back_time) if look_back_time is not None else None
            return sb_get_simulation_result_drifts(
                console=console,
                window_start=window_start,
                window_end=window_end,
                from_status=from_status,
                to_status=to_status,
                drift_type=drift_type,
                attack_id=attack_id,
                attack_type=attack_type,
                attack_name=attack_name,
                drift_key=drift_key,
                page_number=page_number,
                look_back_time=look_back_time
            )

        @self.mcp.tool(
            name="get_simulation_status_drifts",
            description="""Returns time-window-based simulation status drift analysis showing transitions between \
security control final statuses (prevented, stopped, detected, logged, missed, inconsistent).

TWO-PHASE USAGE:
  1. Call WITHOUT drift_key to get a grouped summary of all drift types with counts per transition \
(e.g., prevented-logged, detected-missed). Use this to understand the overall drift landscape.
  2. Call WITH drift_key='<key>' (e.g., 'prevented-logged') and page_number to paginate through individual \
records in that group.

USE THIS WHEN: You need to analyze how security CONTROLS responded differently over time. This provides a \
security CONTROL view — did the detection method change? Did prevention degrade to just detection? \
Did detection degrade to just logging? Each drill-down record includes drift_tracking_code — pass it to \
get_simulation_lineage for the full execution history of that simulation lineage.

DON'T USE FOR:
  - Comparing two specific test runs (use get_test_drifts instead).
  - Filtering drifted simulations within a single test (use get_test_simulations with drifted_only=True).
  - Getting drift details for a single simulation (use get_test_simulation_details with include_drift_info=True).
  - Analyzing blocked/not-blocked result transitions (use get_simulation_result_drifts).

Parameters:
  console (required): SafeBreach console name.
  window_start (required): epoch ms/seconds or ISO 8601 string (e.g., '2026-03-01T00:00:00Z').
  window_end (required): epoch ms/seconds or ISO 8601 string.
  from_final_status: Filter by origin final status. Valid: 'prevented', 'stopped', 'detected', 'logged', \
'missed', 'inconsistent'.
  to_final_status: Filter by destination final status. Valid: 'prevented', 'stopped', 'detected', 'logged', \
'missed', 'inconsistent'.
  drift_type: Filter by drift classification. Valid: 'improvement', 'regression', 'not_applicable'.
  attack_id: Filter by specific playbook attack ID (integer).
  attack_type: Filter by attack type — CASE-SENSITIVE exact match (e.g., 'Suspicious File Creation'). \
Pass '__list__' to discover all valid attack type values on this console. \
Wrong case silently returns zero results, so always use '__list__' first or copy exact values from attack_summary.
  attack_name: Filter by attack name — case-insensitive phrase match (e.g., 'Upload File over SMB').
  drift_key: Drill-down key from summary (e.g., 'prevented-logged'). Omit for grouped summary.
  page_number: Page number for drill-down mode (default 0, 10 records per page).
  look_back_time: How far back to search for baseline (pre-drift) simulations. \
Accepts epoch ms/seconds or ISO 8601 string. \
Defaults to 7 days before window_start. Increase for attacks that run infrequently (e.g., monthly). \
Decrease for faster responses on busy consoles.
Accepts both epoch timestamps and ISO 8601 strings for all time parameters.
WARNING: This endpoint has no server-side pagination. Large time windows (7+ days) on busy consoles can take \
3+ minutes. Start with a narrow window (1-2 days) and widen only if needed."""
        )
        async def get_simulation_status_drifts_tool(
            console: str,
            window_start: str | int = None,
            window_end: str | int = None,
            from_final_status: Optional[str] = None,
            to_final_status: Optional[str] = None,
            drift_type: Optional[str] = None,
            attack_id: Optional[int] = None,
            attack_type: Optional[str] = None,
            attack_name: Optional[str] = None,
            drift_key: Optional[str] = None,
            page_number: int = 0,
            look_back_time: Optional[str | int] = None
        ) -> dict:
            if attack_type == "__list__":
                return sb_get_simulation_status_drifts(
                    console=console, window_start=0, window_end=0, attack_type="__list__")
            window_start = normalize_timestamp(window_start)
            if window_start is None:
                raise ValueError("window_start: invalid or missing timestamp value")
            window_end = normalize_timestamp(window_end)
            if window_end is None:
                raise ValueError("window_end: invalid or missing timestamp value")
            look_back_time = normalize_timestamp(look_back_time) if look_back_time is not None else None
            return sb_get_simulation_status_drifts(
                console=console,
                window_start=window_start,
                window_end=window_end,
                from_final_status=from_final_status,
                to_final_status=to_final_status,
                drift_type=drift_type,
                attack_id=attack_id,
                attack_type=attack_type,
                attack_name=attack_name,
                drift_key=drift_key,
                page_number=page_number,
                look_back_time=look_back_time
            )

        @self.mcp.tool(
            name="get_security_control_drifts",
            description="""Analyze capability transitions for a specific security control over time. \
Shows how a control's prevented/reported/logged/alerted capabilities changed within a time window.

TWO-PHASE USAGE:
  1. Call WITHOUT drift_key to get a grouped summary of all capability transitions with counts. \
Use this to understand the overall drift landscape for a security control.
  2. Call WITH drift_key='<key>' (e.g., 'none->prevented' or 'reported,alerted->prevented,reported,alerted') and page_number \
to paginate through individual records in that group.

USE THIS WHEN: You need to understand how a specific security control's capabilities changed over \
time — e.g., did it gain/lose prevention? Did it start/stop alerting? Did detection degrade? \
Each drill-down record includes drift_tracking_code — pass it to get_simulation_lineage for the full \
execution history of that simulation lineage.

DON'T USE FOR:
  - Overall blocked/not-blocked posture view (use get_simulation_result_drifts).
  - Security control final status transitions like prevented->logged (use get_simulation_status_drifts).
  - Comparing two specific test runs (use get_test_drifts).

Parameters:
  console (required): SafeBreach console name.
  security_control (required): Security control name (e.g., 'Microsoft Defender for Endpoint'), \
or '__list__' to enumerate available security control names on the console. \
When '__list__' is passed, all other parameters are ignored and the response contains \
a list of known security product names filtered to those with significant simulation data.
  window_start (required): epoch ms/seconds or ISO 8601 string (e.g., '2026-03-01T00:00:00Z').
  window_end (required): epoch ms/seconds or ISO 8601 string.
  transition_matching_mode (required): How to match transitions. \
'contains' = sequence includes from->to at least once. \
'starts_and_ends' = first AND last statuses must equal from/to.
  from_prevented, from_reported, from_logged, from_alerted: \
Boolean filters for origin capability state. Omit to match any.
  to_prevented, to_reported, to_logged, to_alerted: \
Boolean filters for destination capability state. Omit to match any.
  drift_type: Filter by drift classification. Valid: 'improvement', 'regression', 'not_applicable'.
  earliest_search_time: How far back to search for baseline simulations. \
Epoch ms/seconds or ISO 8601 string. Defaults to 7 days before window_start.
  max_outside_window_executions: Max executions outside window to consider (integer).
  attack_id: Filter by specific playbook attack ID (integer).
  attack_type: Filter by attack type — CASE-SENSITIVE exact match (e.g., 'Suspicious File Creation'). \
Pass '__list__' to discover all valid attack type values on this console. \
Wrong case silently returns zero results, so always use '__list__' first or copy exact values from attack_summary.
  attack_name: Filter by attack name — case-insensitive phrase match (e.g., 'Upload File over SMB').
  group_by: How to group results. 'transition' (default) groups by boolean capability changes. \
'drift_type' groups by Improvement/Regression.
  drift_key: Drill-down key from summary. Omit for grouped summary.
  page_number: Page number for drill-down mode (default 0, 10 records per page).
WARNING: This endpoint has no server-side pagination. Large time windows on busy consoles can be slow. \
Start with a narrow window (1-2 days) and widen only if needed."""
        )
        async def get_security_control_drifts_tool(
            console: str,
            security_control: str,
            window_start: str | int = None,
            window_end: str | int = None,
            transition_matching_mode: str = None,
            from_prevented: bool | None = None,
            from_reported: bool | None = None,
            from_logged: bool | None = None,
            from_alerted: bool | None = None,
            to_prevented: bool | None = None,
            to_reported: bool | None = None,
            to_logged: bool | None = None,
            to_alerted: bool | None = None,
            drift_type: str | None = None,
            earliest_search_time: str | int | None = None,
            max_outside_window_executions: int | None = None,
            attack_id: int | None = None,
            attack_type: str | None = None,
            attack_name: str | None = None,
            group_by: str = "transition",
            drift_key: str | None = None,
            page_number: int = 0,
        ) -> dict:
            # Discovery mode: list available security controls
            if security_control == "__list__":
                return sb_get_security_control_drifts(
                    console=console,
                    security_control="__list__",
                    window_start=0,
                    window_end=0,
                    transition_matching_mode="contains",
                )

            # Discovery mode: list available attack types
            if attack_type == "__list__":
                return sb_get_security_control_drifts(
                    console=console,
                    security_control=security_control,
                    window_start=0,
                    window_end=0,
                    transition_matching_mode="contains",
                    attack_type="__list__",
                )

            window_start = normalize_timestamp(window_start)
            if window_start is None:
                raise ValueError("window_start: invalid or missing timestamp value")
            window_end = normalize_timestamp(window_end)
            if window_end is None:
                raise ValueError("window_end: invalid or missing timestamp value")
            if transition_matching_mode is None:
                raise ValueError(
                    "transition_matching_mode is required. "
                    "Valid values: 'contains', 'starts_and_ends'"
                )
            earliest_search_time = (
                normalize_timestamp(earliest_search_time)
                if earliest_search_time is not None else None
            )

            return sb_get_security_control_drifts(
                console=console,
                security_control=security_control,
                window_start=window_start,
                window_end=window_end,
                transition_matching_mode=transition_matching_mode,
                from_prevented=from_prevented,
                from_reported=from_reported,
                from_logged=from_logged,
                from_alerted=from_alerted,
                to_prevented=to_prevented,
                to_reported=to_reported,
                to_logged=to_logged,
                to_alerted=to_alerted,
                drift_type=drift_type,
                earliest_search_time=earliest_search_time,
                max_outside_window_executions=max_outside_window_executions,
                attack_id=attack_id,
                attack_type=attack_type,
                attack_name=attack_name,
                group_by=group_by,
                drift_key=drift_key,
                page_number=page_number,
            )

        @self.mcp.tool(
            name="get_simulation_lineage",
            description="""Returns the full chronological execution history (lineage) of a simulation across all \
test runs, identified by its drift_tracking_code.

The drift_tracking_code is a lineage identifier that groups all executions of the same attack \
configuration across test runs. Every simulation record returned by get_test_simulations, \
get_test_simulation_details (with include_drift_info=True), get_simulation_result_drifts, \
get_simulation_status_drifts, and get_security_control_drifts includes a drift_tracking_code field.

USE THIS WHEN: After discovering a drift or investigating a simulation, you want to see how its \
results changed over time across multiple test runs. Pass the drift_tracking_code from any \
simulation record to get the complete timeline.

RETURNS: Chronological list of all simulations sharing the tracking code, each with an is_drifted \
flag indicating whether its status differs from its predecessor. Also includes a status_summary \
(count per status), test_runs_spanned, first_seen, and last_seen timestamps.

CROSS-REFERENCES:
  - For individual simulation details, use get_test_simulation_details.
  - For time-window drift analysis, see get_simulation_result_drifts and get_simulation_status_drifts.
  - For security control capability transitions, see get_security_control_drifts.
  - For comparing two specific test runs, use get_test_drifts.

Parameters:
  console (required): SafeBreach console name.
  tracking_code (required): The drift_tracking_code value from any simulation or drift record.
  page_number (default 0): Page number for pagination (10 simulations per page)."""
        )
        async def get_simulation_lineage_tool(
            console: str,
            tracking_code: str,
            page_number: int = 0,
        ) -> dict:
            return sb_get_simulation_lineage(
                console=console,
                tracking_code=tracking_code,
                page_number=page_number,
            )

        @self.mcp.tool(
            name="get_peer_benchmark_score",
            description="""Returns the customer's security posture score compared to SafeBreach peers for a given time window.
Wraps POST /api/data/v1/accounts/{account_id}/score (SAF-27621).

Parameters:
  console (default 'default'): SafeBreach console name.
  start_date (required): epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'. Start of the scoring window.
  end_date (required): epoch ms/seconds or ISO 8601 string, e.g. '2026-03-01T00:00:00Z'. End of the scoring window.
  include_test_ids_filter: comma-separated planRunIds to restrict scoring to. \
Mutually exclusive with exclude_test_ids_filter.
  exclude_test_ids_filter: comma-separated planRunIds to exclude from scoring. \
Mutually exclusive with include_test_ids_filter.

Peers vs industry distinction: all_peers_score reflects the average across ALL SafeBreach customers regardless of \
industry (sourced from the backend's all_industries bucket). customer_industry_scores is an array scoped to the \
customer's OWN industry only — determined server-side from a Salesforce industry mapping and not overridable by the \
caller. In practice the array has 0 or 1 elements.

Response fields:
  peer_snapshot_month — the full-month peer snapshot used for comparison; peer and industry aggregation is always \
full-month even when the query window is shorter.
  peer_data_through_date — ETL freshness date; may be null when the gateway has no snapshot.
  custom_attacks_filtered_count — count of custom attacks (moveId >= 10_000_000) auto-excluded from the peer comparison.
  hint_to_agent — present when data is missing (e.g., no executions, no peer snapshot); guides the LLM's next step.

Score formula: score = 1.0 * blocked + 0.5 * detected.

HTTP 204 behavior: when the backend returns no-content (no executions in the window or all matched attacks are \
custom), this tool returns the empty-shape response with a hint_to_agent — the caller does NOT need to handle an \
exception."""
        )
        async def get_peer_benchmark_score_tool(
            console: str = "default",
            start_date: Optional[str | int] = None,
            end_date: Optional[str | int] = None,
            include_test_ids_filter: Optional[str] = None,
            exclude_test_ids_filter: Optional[str] = None,
        ) -> dict:
            start_date = normalize_timestamp(start_date) if start_date is not None else None
            end_date = normalize_timestamp(end_date) if end_date is not None else None
            if start_date is None or end_date is None:
                raise ValueError("start_date and end_date are required")
            return sb_get_peer_benchmark_score(
                console=console,
                start_date=start_date,
                end_date=end_date,
                include_test_ids_filter=include_test_ids_filter,
                exclude_test_ids_filter=exclude_test_ids_filter,
            )

def parse_external_config(server_type: str) -> bool:
    """Parse external connection configuration for specific server."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'
    
    return global_external or server_specific

# Create server instance
data_server = SafeBreachDataServer()

async def run_data_server():
    """Run the data server on port 8001."""
    # Check for external binding configuration
    allow_external = parse_external_config("data")
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    logger.info("Starting SafeBreach MCP Data Server...")
    if allow_external:
        logger.info("🌐 External connections enabled - server accessible from remote hosts")
    else:
        logger.info("🏠 Local connections only - server accessible from localhost")
    
    await data_server.run_server(port=8001, host=custom_host, allow_external=allow_external)

async def main():
    """Main entry point for the data server."""
    await run_data_server()

# Create legacy main function for backward compatibility
legacy_main = data_server.create_main_function(port=8001)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())