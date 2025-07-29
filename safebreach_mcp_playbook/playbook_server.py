"""
SafeBreach MCP Playbook Server

This server handles playbook attack operations for SafeBreach MCP.
"""

import sys
import os
import logging
from typing import Optional

# Add parent directory to path to import core components
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safebreach_mcp_core import SafeBreachMCPBase
from .playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details
)

logger = logging.getLogger(__name__)

class SafeBreachPlaybookServer(SafeBreachMCPBase):
    """SafeBreach MCP Playbook Server for playbook attack operations."""
    
    def __init__(self):
        super().__init__(
            server_name="SafeBreach MCP Playbook Server",
            description="Handles playbook attack operations"
        )
        
        # Register MCP tools
        self._register_tools()
    
    def _register_tools(self):
        """Register all MCP tools for playbook operations."""
        
        @self.mcp.tool(
            name="get_playbook_attacks",
            description="""Returns a filtered and paginated list of SafeBreach playbook attacks. 
Supports filtering by name, description, ID range, and date ranges. Results are paginated with 10 items per page.
Parameters: console (required), page_number (default 0), name_filter (partial match), description_filter (partial match), 
id_min (minimum ID), id_max (maximum ID), modified_date_start (ISO date), modified_date_end (ISO date), 
published_date_start (ISO date), published_date_end (ISO date)"""
        )
        def get_playbook_attacks(
            console: str,
            page_number: int = 0,
            name_filter: Optional[str] = None,
            description_filter: Optional[str] = None,
            id_min: Optional[int] = None,
            id_max: Optional[int] = None,
            modified_date_start: Optional[str] = None,
            modified_date_end: Optional[str] = None,
            published_date_start: Optional[str] = None,
            published_date_end: Optional[str] = None
        ) -> str:
            """Get filtered and paginated playbook attacks."""
            try:
                result = sb_get_playbook_attacks(
                    console=console,
                    page_number=page_number,
                    name_filter=name_filter,
                    description_filter=description_filter,
                    id_min=id_min,
                    id_max=id_max,
                    modified_date_start=modified_date_start,
                    modified_date_end=modified_date_end,
                    published_date_start=published_date_start,
                    published_date_end=published_date_end
                )
                
                if 'error' in result:
                    return f"Error: {result['error']}"
                
                attacks = result['attacks_in_page']
                total_attacks = result['total_attacks']
                page_number = result['page_number']
                total_pages = result['total_pages']
                applied_filters = result.get('applied_filters', {})
                
                # Format response
                response_parts = [
                    f"## Playbook Attacks - Page {page_number + 1} of {total_pages}",
                    f"**Total attacks matching filters: {total_attacks}**"
                ]
                
                if applied_filters:
                    filter_strs = []
                    for key, value in applied_filters.items():
                        filter_strs.append(f"{key}={value}")
                    response_parts.append(f"**Applied filters:** {', '.join(filter_strs)}")
                
                response_parts.append("")
                
                for attack in attacks:
                    response_parts.extend([
                        f"### {attack.get('name', 'Unknown')} (ID: {attack.get('id', 'Unknown')})",
                        f"**Description:** {attack.get('description', 'No description available')[:200]}{'...' if len(str(attack.get('description', ''))) > 200 else ''}",
                        f"**Modified:** {attack.get('modifiedDate', 'Unknown')}",
                        f"**Published:** {attack.get('publishedDate', 'Unknown')}",
                        ""
                    ])
                
                if result.get('hint_to_agent'):
                    response_parts.append(f"**Hint:** {result['hint_to_agent']}")
                
                return "\n".join(response_parts)
                
            except Exception as e:
                logger.error(f"Error in get_playbook_attacks: {e}")
                return f"Error getting playbook attacks: {str(e)}"
        
        @self.mcp.tool(
            name="get_playbook_attack_details",
            description="""Returns detailed information for a specific SafeBreach playbook attack by ID. 
Supports verbosity options to include additional details like fix suggestions, tags, and parameters.
Parameters: console (required), attack_id (required), include_fix_suggestions (default False), 
include_tags (default False), include_parameters (default False)"""
        )
        def get_playbook_attack_details(
            console: str,
            attack_id: int,
            include_fix_suggestions: bool = False,
            include_tags: bool = False,
            include_parameters: bool = False
        ) -> str:
            """Get detailed information for a specific playbook attack."""
            try:
                result = sb_get_playbook_attack_details(
                    console=console,
                    attack_id=attack_id,
                    include_fix_suggestions=include_fix_suggestions,
                    include_tags=include_tags,
                    include_parameters=include_parameters
                )
                
                # Format response
                response_parts = [
                    f"## {result.get('name', 'Unknown Attack')} (ID: {result.get('id', 'Unknown')})",
                    "",
                    f"**Description:**",
                    result.get('description', 'No description available'),
                    "",
                    f"**Modified Date:** {result.get('modifiedDate', 'Unknown')}",
                    f"**Published Date:** {result.get('publishedDate', 'Unknown')}"
                ]
                
                # Add optional fields based on verbosity
                if include_fix_suggestions and result.get('fix_suggestions'):
                    response_parts.extend([
                        "",
                        "## Fix Suggestions",
                        ""
                    ])
                    for idx, suggestion in enumerate(result['fix_suggestions'], 1):
                        response_parts.extend([
                            f"### {idx}. {suggestion.get('title', 'Untitled')}",
                            suggestion.get('content', 'No content available'),
                            ""
                        ])
                
                if include_tags and result.get('tags'):
                    tags = result['tags']
                    if isinstance(tags, list) and len(tags) > 0:
                        # Tags are now properly formatted strings from _transform_tags()
                        response_parts.extend([
                            "",
                            f"**Tags:** {', '.join(tags)}"
                        ])
                    elif tags:
                        response_parts.extend([
                            "",
                            f"**Tags:** {str(tags)}"
                        ])
                
                if include_parameters and result.get('params'):
                    response_parts.extend([
                        "",
                        "## Parameters",
                        ""
                    ])
                    params = result['params']
                    if isinstance(params, list):
                        for param in params:
                            if isinstance(param, dict):
                                response_parts.extend([
                                    f"**{param.get('displayName', param.get('name', 'Unknown'))}** ({param.get('type', 'Unknown')})",
                                    f"- Description: {param.get('description', 'No description')}",
                                    f"- Default values: {param.get('values', 'None')}",
                                    ""
                                ])
                    else:
                        response_parts.append(f"Parameters data: {str(params)}")
                
                return "\n".join(response_parts)
                
            except Exception as e:
                logger.error(f"Error in get_playbook_attack_details: {e}")
                return f"Error getting attack details: {str(e)}"


def parse_external_config(server_type: str) -> bool:
    """Parse external connection configuration for the server."""
    # Check global flag first
    global_external = os.environ.get('SAFEBREACH_MCP_ALLOW_EXTERNAL', 'false').lower() == 'true'
    
    # Check server-specific flag
    server_specific = os.environ.get(f'SAFEBREACH_MCP_{server_type.upper()}_EXTERNAL', 'false').lower() == 'true'
    
    return global_external or server_specific


async def main():
    """Main entry point for the playbook server."""
    logging.basicConfig(level=logging.INFO)
    
    # Parse external configuration
    allow_external = parse_external_config("playbook")
    custom_host = os.environ.get('SAFEBREACH_MCP_BIND_HOST', '127.0.0.1')
    
    # Create and run server
    playbook_server = SafeBreachPlaybookServer()
    await playbook_server.run_server(port=8003, host=custom_host, allow_external=allow_external)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())