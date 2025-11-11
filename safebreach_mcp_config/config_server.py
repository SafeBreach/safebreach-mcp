"""
SafeBreach MCP Config Server

This server handles configuration management operations for SafeBreach MCP,
specifically simulator operations and infrastructure management.
"""

import sys
import os
import logging
from typing import Optional

# Add parent directory to path to import core components
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safebreach_mcp_core import SafeBreachMCPBase
from .config_functions import sb_get_console_simulators, sb_get_simulator_details

logger = logging.getLogger(__name__)

class SafeBreachConfigServer(SafeBreachMCPBase):
    """SafeBreach MCP Config Server for simulator operations."""
    
    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Config Server",
            description="Handles simulator operations and infrastructure management"
        )
        
        # Register MCP tools
        self._register_tools()
    
    def _register_tools(self):
        """Register all MCP tools for config operations."""
        
        @self.mcp.tool(
            name="get_console_simulators",
            description="""Returns a filtered list of Safebreach simulators linked to a given Safebreach management console.
Supports filtering by status, name, labels, OS type, and critical status. Results are ordered by name (ascending) by default.
Parameters: console (required), status_filter ('connected'/'disconnected'/'enabled'/'disabled'/None), name_filter (partial name match), 
label_filter (partial label match), os_type_filter (OS type match), critical_only (True/False/None), order_by ('name'/'id'/'version'/'isConnected'/'isEnabled'), order_direction ('asc'/'desc')"""
        )
        async def get_console_simulators_tool(
            console: str = "default",
            status_filter: Optional[str] = None,
            name_filter: Optional[str] = None,
            label_filter: Optional[str] = None,
            os_type_filter: Optional[str] = None,
            critical_only: Optional[bool] = None,
            order_by: str = "name",
            order_direction: str = "asc"
        ) -> dict:
            # In single-tenant mode, auto-resolve any unknown console name to SAFEBREACH_CONSOLE_NAME
            from safebreach_mcp_core.environments_metadata import get_console_name, safebreach_envs
            if not safebreach_envs:  # Single-tenant mode (no hardcoded environments)
                console_name = get_console_name()
                if console_name != 'default' and console not in safebreach_envs:
                    console = console_name
            return sb_get_console_simulators(
                console=console,
                status_filter=status_filter,
                name_filter=name_filter,
                label_filter=label_filter,
                os_type_filter=os_type_filter,
                critical_only=critical_only,
                order_by=order_by,
                order_direction=order_direction
            )
        
        @self.mcp.tool(
            name="get_simulator_details",
            description="Gets the full details of a specific Safebreach simulator and the host on which it is running"
        )
        async def get_simulator_details_tool(simulator_id: str, console: str = "default") -> dict:
            # In single-tenant mode, auto-resolve any unknown console name to SAFEBREACH_CONSOLE_NAME
            from safebreach_mcp_core.environments_metadata import get_console_name, safebreach_envs
            if not safebreach_envs:  # Single-tenant mode (no hardcoded environments)
                console_name = get_console_name()
                if console_name != 'default' and console not in safebreach_envs:
                    console = console_name
            return sb_get_simulator_details(simulator_id, console)

def parse_external_config(server_type: str) -> bool:
    """Parse external connection configuration for specific server."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'
    
    return global_external or server_specific

# Create server instance
config_server = SafeBreachConfigServer()

async def run_config_server():
    """Run the config server on port 8000."""
    # Check for external binding configuration
    allow_external = parse_external_config("config")
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    logger.info("Starting SafeBreach MCP Config Server...")
    if allow_external:
        logger.info("🌐 External connections enabled - server accessible from remote hosts")
    else:
        logger.info("🏠 Local connections only - server accessible from localhost")
    
    await config_server.run_server(port=8000, host=custom_host, allow_external=allow_external)

async def main():
    """Main entry point for the config server."""
    await run_config_server()

# Create legacy main function for backward compatibility
legacy_main = config_server.create_main_function(port=8000)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())