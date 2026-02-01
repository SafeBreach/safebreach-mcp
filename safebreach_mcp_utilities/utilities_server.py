"""
SafeBreach MCP Utilities Server

This server handles utility functions for SafeBreach MCP,
specifically datetime conversion and other helper utilities.
"""

import sys
import os
import logging

# Add parent directory to path to import core components
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safebreach_mcp_core import SafeBreachMCPBase, convert_datetime_to_epoch, convert_epoch_to_datetime

logger = logging.getLogger(__name__)

class SafeBreachUtilitiesServer(SafeBreachMCPBase):
    """SafeBreach MCP Utilities Server for helper functions."""
    
    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Utilities Server",
            description="Handles datetime conversion and other utility functions"
        )
        
        # Register MCP tools
        self._register_tools()
    
    def _register_tools(self):
        """Register all MCP tools for utility operations."""
        
        @self.mcp.tool(
            name="convert_datetime_to_epoch",
            description="""Converts a datetime string in ISO format to Unix epoch timestamp in MILLISECONDS.
Returns timestamps in milliseconds format to match SafeBreach API expectations for date filtering parameters (start_date, end_date).
Supports various ISO datetime formats including timezone information.
Parameters: datetime_str (required, ISO format string like '2024-01-15T10:30:00Z' or '2024-01-15T10:30:00+00:00')"""
        )
        async def convert_datetime_to_epoch_tool(datetime_str: str) -> dict:
            return convert_datetime_to_epoch(datetime_str)

        @self.mcp.tool(
            name="convert_epoch_to_datetime",
            description="""Converts a Unix epoch timestamp to ISO format datetime string.
Accepts timestamps in both MILLISECONDS (SafeBreach API format) and seconds - auto-detects the format.
Supports optional timezone specification for the output format. Useful for interpreting epoch timestamps from SafeBreach API responses.
Parameters: epoch_timestamp (required, Unix timestamp as integer in milliseconds or seconds), timezone (optional, default 'UTC')"""
        )
        async def convert_epoch_to_datetime_tool(epoch_timestamp: int, timezone: str = "UTC") -> dict:
            return convert_epoch_to_datetime(epoch_timestamp, timezone)

def parse_external_config(server_type: str) -> bool:
    """Parse external connection configuration for specific server."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'
    
    return global_external or server_specific

# Create server instance
utilities_server = SafeBreachUtilitiesServer()

async def run_utilities_server():
    """Run the utilities server on port 8002."""
    # Check for external binding configuration
    allow_external = parse_external_config("utilities")
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    logger.info("Starting SafeBreach MCP Utilities Server...")
    if allow_external:
        logger.info("🌐 External connections enabled - server accessible from remote hosts")
    else:
        logger.info("🏠 Local connections only - server accessible from localhost")
    
    await utilities_server.run_server(port=8002, host=custom_host, allow_external=allow_external)

async def main():
    """Main entry point for the utilities server."""
    await run_utilities_server()

# Create legacy main function for backward compatibility
legacy_main = utilities_server.create_main_function(port=8002)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())