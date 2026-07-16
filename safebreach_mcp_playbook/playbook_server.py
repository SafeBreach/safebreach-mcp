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

from mcp.types import ToolAnnotations
from safebreach_mcp_core import SafeBreachMCPBase
from .playbook_functions import (
    sb_get_playbook_attacks,
    sb_get_playbook_attack_details,
    sb_get_playbook_attacks_by_tags,
    sb_add_playbook_attack_tag,
    sb_remove_playbook_attack_tag,
    sb_rename_playbook_attack_tag
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
            annotations=ToolAnnotations(readOnlyHint=True),
            description="""Returns a filtered and paginated list of SafeBreach playbook attacks.
Supports filtering by name, description, ID range, date ranges, MITRE ATT&CK techniques/tactics, and platform.
Results are paginated with 10 items per page. Each attack includes attacker_platform and target_platform fields.
Parameters: console (required), page_number (default 0), name_filter (partial match), description_filter (partial match),
id_min (minimum ID), id_max (maximum ID), modified_date_start (ISO date), modified_date_end (ISO date),
published_date_start (ISO date), published_date_end (ISO date),
include_mitre_techniques (default False - include MITRE ATT&CK tactics/techniques/sub-techniques),
mitre_technique_filter (comma-separated technique IDs or names, OR logic, case-insensitive partial match),
mitre_tactic_filter (comma-separated tactic names or IDs like TA0006, OR logic, case-insensitive partial match),
attacker_platform_filter (comma-separated platform values e.g. WINDOWS,LINUX - OR logic, case-insensitive partial match.
  Strict: only attacks matching the specified platform(s) are returned.
  Add ANY to also include platform-agnostic attacks, e.g. WINDOWS,ANY),
target_platform_filter (comma-separated platform values e.g. WINDOWS,LINUX - OR logic, case-insensitive partial match.
  Strict: only attacks matching the specified platform(s) are returned.
  Add ANY to also include platform-agnostic attacks, e.g. WINDOWS,ANY).
Valid platform values: ANY, AWS, AZURE, DOCKER, GCP, LINUX, MAC, MAILBOX, WEBAPPLICATION, WINDOWS"""
        )
        def get_playbook_attacks(
            console: str = "default",
            page_number: int = 0,
            name_filter: Optional[str] = None,
            description_filter: Optional[str] = None,
            id_min: Optional[int] = None,
            id_max: Optional[int] = None,
            modified_date_start: Optional[str] = None,
            modified_date_end: Optional[str] = None,
            published_date_start: Optional[str] = None,
            published_date_end: Optional[str] = None,
            include_mitre_techniques: bool = False,
            mitre_technique_filter: Optional[str] = None,
            mitre_tactic_filter: Optional[str] = None,
            attacker_platform_filter: Optional[str] = None,
            target_platform_filter: Optional[str] = None
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
                    published_date_end=published_date_end,
                    include_mitre_techniques=include_mitre_techniques,
                    mitre_technique_filter=mitre_technique_filter,
                    mitre_tactic_filter=mitre_tactic_filter,
                    attacker_platform_filter=attacker_platform_filter,
                    target_platform_filter=target_platform_filter
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
                        f"**Published:** {attack.get('publishedDate', 'Unknown')}"
                    ])

                    # Render MITRE data if present
                    mitre_tactics = attack.get('mitre_tactics', [])
                    mitre_techniques = attack.get('mitre_techniques', [])
                    mitre_sub_techniques = attack.get('mitre_sub_techniques', [])

                    if mitre_tactics:
                        tactic_names = ', '.join(t.get('name', '') for t in mitre_tactics)
                        response_parts.append(f"**MITRE Tactics:** {tactic_names}")
                    if mitre_techniques:
                        tech_names = ', '.join(t.get('display_name', t.get('id', '')) for t in mitre_techniques)
                        response_parts.append(f"**MITRE Techniques:** {tech_names}")
                    if mitre_sub_techniques:
                        sub_names = ', '.join(t.get('display_name', t.get('id', '')) for t in mitre_sub_techniques)
                        response_parts.append(f"**MITRE Sub-Techniques:** {sub_names}")

                    # Render platform data
                    attacker_platform = attack.get('attacker_platform')
                    target_platform = attack.get('target_platform')
                    if attacker_platform:
                        response_parts.append(f"**Attacker Platform:** {attacker_platform}")
                    if target_platform:
                        response_parts.append(f"**Target Platform:** {target_platform}")

                    response_parts.append("")
                
                if result.get('hint_to_agent'):
                    response_parts.append(f"**Hint:** {result['hint_to_agent']}")
                
                return "\n".join(response_parts)
                
            except Exception as e:
                logger.error(f"Error in get_playbook_attacks: {e}")
                return f"Error getting playbook attacks: {str(e)}"
        
        @self.mcp.tool(
            name="get_playbook_attack_details",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="""Returns detailed information for a specific SafeBreach playbook attack by ID.
Supports verbosity options to include additional details like fix suggestions, tags, parameters, and MITRE ATT&CK data.
Parameters: console (required), attack_id (required), include_fix_suggestions (default False),
include_tags (default False), include_parameters (default False),
include_mitre_techniques (default False - include MITRE ATT&CK tactics, techniques, and sub-techniques with URLs)"""
        )
        def get_playbook_attack_details(
            attack_id: int,
            console: str = "default",
            include_fix_suggestions: bool = False,
            include_tags: bool = False,
            include_parameters: bool = False,
            include_mitre_techniques: bool = False
        ) -> str:
            """Get detailed information for a specific playbook attack."""
            try:
                result = sb_get_playbook_attack_details(
                    attack_id=attack_id,
                    console=console,
                    include_fix_suggestions=include_fix_suggestions,
                    include_tags=include_tags,
                    include_parameters=include_parameters,
                    include_mitre_techniques=include_mitre_techniques
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

                if include_mitre_techniques:
                    mitre_tactics = result.get('mitre_tactics', [])
                    mitre_techniques = result.get('mitre_techniques', [])
                    mitre_sub_techniques = result.get('mitre_sub_techniques', [])

                    if mitre_tactics or mitre_techniques or mitre_sub_techniques:
                        response_parts.extend(["", "## MITRE ATT&CK Mapping", ""])

                        if mitre_tactics:
                            response_parts.append("**Tactics:**")
                            for t in mitre_tactics:
                                response_parts.append(f"- {t.get('name', 'Unknown')}")

                        if mitre_techniques:
                            response_parts.append("**Techniques:**")
                            for t in mitre_techniques:
                                response_parts.append(
                                    f"- [{t.get('display_name', t.get('id', ''))}]({t.get('url', '')})"
                                )

                        if mitre_sub_techniques:
                            response_parts.append("**Sub-Techniques:**")
                            for t in mitre_sub_techniques:
                                response_parts.append(
                                    f"- [{t.get('display_name', t.get('id', ''))}]({t.get('url', '')})"
                                )

                return "\n".join(response_parts)

            except Exception as e:
                logger.error(f"Error in get_playbook_attack_details: {e}")
                return f"Error getting attack details: {str(e)}"

        @self.mcp.tool(
            name="get_playbook_attacks_by_tags",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="""Returns a filtered and paginated list of SafeBreach playbook attacks that carry any of the given custom tags.
Tag matching is case-insensitive and exact per tag token (a filter of "net" does NOT match a tag "network").
Parameters: console (required), tags (required, comma-separated tag values, OR logic), page_number (default 0).
Results are paginated with 10 items per page; each attack includes its normalized tags list."""
        )
        def get_playbook_attacks_by_tags(
            console: str = "default",
            tags: Optional[str] = None,
            page_number: int = 0
        ) -> str:
            """Get playbook attacks filtered by one or more custom tags."""
            try:
                result = sb_get_playbook_attacks_by_tags(
                    console=console,
                    tags=tags,
                    page_number=page_number
                )

                if 'error' in result:
                    return f"Error: {result['error']}"

                attacks = result['attacks_in_page']
                total_attacks = result['total_attacks']
                page_number = result['page_number']
                total_pages = result['total_pages']
                applied_filters = result.get('applied_filters', {})

                response_parts = [
                    f"## Playbook Attacks by Tags - Page {page_number + 1} of {total_pages}",
                    f"**Total attacks matching tags: {total_attacks}**"
                ]

                if applied_filters:
                    filter_strs = [f"{key}={value}" for key, value in applied_filters.items()]
                    response_parts.append(f"**Applied filters:** {', '.join(filter_strs)}")

                response_parts.append("")

                for attack in attacks:
                    response_parts.extend([
                        f"### {attack.get('name', 'Unknown')} (ID: {attack.get('id', 'Unknown')})",
                        f"**Tags:** {', '.join(attack.get('tags', []))}"
                    ])
                    description = str(attack.get('description', '') or '')
                    if description:
                        response_parts.append(
                            f"**Description:** {description[:200]}{'...' if len(description) > 200 else ''}"
                        )
                    response_parts.append("")

                if result.get('hint_to_agent'):
                    response_parts.append(f"**Hint:** {result['hint_to_agent']}")

                return "\n".join(response_parts)

            except Exception as e:
                logger.error(f"Error in get_playbook_attacks_by_tags: {e}")
                return f"Error getting playbook attacks by tags: {str(e)}"

        @self.mcp.tool(
            name="add_playbook_attack_tag",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            description="""Adds a custom tag to a single SafeBreach playbook attack.
This is a WRITE action (rate-limited, hidden unless AI-agent actions are enabled).
Parameters: console (required), attack_id (required, the playbook attack/move ID), tag_value (required, a single tag)."""
        )
        def add_playbook_attack_tag(console: str = "default", attack_id: int = None, tag_value: str = None) -> str:
            """Add a custom tag to a single playbook attack."""
            try:
                result = sb_add_playbook_attack_tag(console=console, attack_id=attack_id, tag_value=tag_value)
                return f"✅ Added tag '{result['tag_value']}' to playbook attack {result['attack_id']}."
            except Exception as e:
                logger.error(f"Error in add_playbook_attack_tag: {e}")
                return f"Error adding tag to playbook attack: {str(e)}"

        @self.mcp.tool(
            name="remove_playbook_attack_tag",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
            description="""Removes a custom tag from a single SafeBreach playbook attack.
This is a WRITE action (rate-limited, hidden unless AI-agent actions are enabled).
Parameters: console (required), attack_id (required, the playbook attack/move ID), tag_value (required, a single tag)."""
        )
        def remove_playbook_attack_tag(console: str = "default", attack_id: int = None, tag_value: str = None) -> str:
            """Remove a custom tag from a single playbook attack."""
            try:
                result = sb_remove_playbook_attack_tag(console=console, attack_id=attack_id, tag_value=tag_value)
                return f"✅ Removed tag '{result['tag_value']}' from playbook attack {result['attack_id']}."
            except Exception as e:
                logger.error(f"Error in remove_playbook_attack_tag: {e}")
                return f"Error removing tag from playbook attack: {str(e)}"

        @self.mcp.tool(
            name="rename_playbook_attack_tag",
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
            description="""Renames a custom tag on a single SafeBreach playbook attack.
This is a WRITE action (rate-limited, hidden unless AI-agent actions are enabled).
Parameters: console (required), attack_id (required, the playbook attack/move ID), old_value (required), new_value (required)."""
        )
        def rename_playbook_attack_tag(console: str = "default", attack_id: int = None,
                                       old_value: str = None, new_value: str = None) -> str:
            """Rename a custom tag on a single playbook attack."""
            try:
                result = sb_rename_playbook_attack_tag(
                    console=console, attack_id=attack_id, old_value=old_value, new_value=new_value
                )
                return (f"✅ Renamed tag '{result['old_value']}' to '{result['new_value']}' "
                        f"on playbook attack {result['attack_id']}.")
            except Exception as e:
                logger.error(f"Error in rename_playbook_attack_tag: {e}")
                return f"Error renaming tag on playbook attack: {str(e)}"


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