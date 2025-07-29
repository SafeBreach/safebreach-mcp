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
from .data_functions import (
    sb_get_tests_history,
    sb_get_test_details,
    sb_get_test_simulations,
    sb_get_test_simulation_details,
    sb_get_security_controls_events,
    sb_get_security_control_event_details,
    sb_get_test_findings_counts,
    sb_get_test_findings_details
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
Parameters: console (required), page_number (default 0), test_type ('validate'/'propagate'/None), start_date (Unix timestamp), end_date (Unix timestamp), 
status_filter ('completed'/'canceled'/'failed'/None), name_filter (partial name match), order_by ('endTime'/'startTime'/'name'/'duration'), order_direction ('desc'/'asc')"""
        )
        async def get_tests_history_tool(
            console: str,
            page_number: int = 0,
            test_type: Optional[str] = None,
            start_date: Optional[int] = None,
            end_date: Optional[int] = None,
            status_filter: Optional[str] = None,
            name_filter: Optional[str] = None,
            order_by: str = "endTime",
            order_direction: str = "desc"
        ) -> dict:
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
            description="Returns the full details for a specific test by id executed on a given Safebreach management console. Optionally includes detailed simulation statistics."
        )
        async def get_test_details_tool(
            console: str,
            test_id: str,
            include_simulations_statistics: bool = False
        ) -> dict:
            return sb_get_test_details(console, test_id, include_simulations_statistics)
        
        @self.mcp.tool(
            name="get_test_simulations",
            description="""Returns a filtered and paged listing of simulations executed in the context of a specific test by id on a given Safebreach management console.
Supports filtering by status, time windows, playbook attack ID, and playbook attack name patterns. Results are ordered by execution time (newest first) by default.
Parameters: console (required), test_id (required), page_number (default 0), status_filter (simulation status), start_time (Unix timestamp), end_time (Unix timestamp), 
playbook_attack_id_filter (exact match), playbook_attack_name_filter (partial name match)"""
        )
        async def get_test_simulations_tool(
            console: str,
            test_id: str,
            page_number: int = 0,
            status_filter: Optional[str] = None,
            start_time: Optional[int] = None,
            end_time: Optional[int] = None,
            playbook_attack_id_filter: Optional[str] = None,
            playbook_attack_name_filter: Optional[str] = None
        ) -> dict:
            return sb_get_test_simulations(
                console=console,
                test_id=test_id,
                page_number=page_number,
                status_filter=status_filter,
                start_time=start_time,
                end_time=end_time,
                playbook_attack_id_filter=playbook_attack_id_filter,
                playbook_attack_name_filter=playbook_attack_name_filter
            )
        
        @self.mcp.tool(
            name="get_test_simulation_details",
            description="""Returns the full details of a specific simulation by id in the context of a specific test by id on a given Safebreach management console.
Supports optional extensions for detailed analysis: MITRE ATT&CK techniques, full attack logs by host, and simulation execution logs.
Parameters: console (required), test_id (required), simulation_id (required), include_mitre_techniques (bool, default False), 
include_full_attack_logs (bool, default False), include_simulation_logs (bool, default False)"""
        )
        async def get_test_simulation_details_tool(
            console: str,
            test_id: str,
            simulation_id: str,
            include_mitre_techniques: bool = False,
            include_full_attack_logs: bool = False,
            include_simulation_logs: bool = False
        ) -> dict:
            return sb_get_test_simulation_details(
                console,
                test_id,
                simulation_id,
                include_mitre_techniques=include_mitre_techniques,
                include_full_attack_logs=include_full_attack_logs,
                include_simulation_logs=include_simulation_logs
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
            console: str,
            test_id: str,
            simulation_id: str,
            page_number: int = 0,
            product_name_filter: Optional[str] = None,
            vendor_name_filter: Optional[str] = None,
            security_action_filter: Optional[str] = None,
            connector_name_filter: Optional[str] = None,
            source_host_filter: Optional[str] = None,
            destination_host_filter: Optional[str] = None
        ) -> dict:
            return sb_get_security_controls_events(
                console=console,
                test_id=test_id,
                simulation_id=simulation_id,
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
            console: str,
            test_id: str,
            simulation_id: str,
            event_id: str,
            verbosity_level: str = "standard"
        ) -> dict:
            return sb_get_security_control_event_details(
                console=console,
                test_id=test_id,
                simulation_id=simulation_id,
                event_id=event_id,
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
            console: str,
            test_id: str,
            attribute_filter: Optional[str] = None
        ) -> dict:
            return sb_get_test_findings_counts(
                console=console,
                test_id=test_id,
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
            console: str,
            test_id: str,
            page_number: int = 0,
            attribute_filter: Optional[str] = None
        ) -> dict:
            return sb_get_test_findings_details(
                console=console,
                test_id=test_id,
                page_number=page_number,
                attribute_filter=attribute_filter
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