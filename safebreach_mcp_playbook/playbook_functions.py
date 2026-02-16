"""
SafeBreach Playbook Functions

This module provides functions for SafeBreach playbook operations,
specifically for accessing playbook attack data and details.
"""

import logging
import time
from typing import Dict, List, Optional, Any

import requests
from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url
from .playbook_types import (
    transform_reduced_playbook_attack,
    transform_full_playbook_attack,
    filter_attacks_by_criteria,
    paginate_attacks
)

logger = logging.getLogger(__name__)

# Global cache for playbook data
playbook_cache = {}

# Configuration constants
PAGE_SIZE = 10
CACHE_TTL = 3600  # 1 hour in seconds


def _get_all_attacks_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all attacks for a console from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        List of all attacks for the console

    Raises:
        ValueError: If console is not found or API call fails
    """

    # Check cache first (only if caching is enabled)
    cache_key = f"attacks_{console}"
    current_time = time.time()

    if (is_caching_enabled() and cache_key in playbook_cache and
        current_time - playbook_cache[cache_key]['timestamp'] < CACHE_TTL):
        logger.info("Cache hit for console %s playbook attacks", console)
        return playbook_cache[cache_key]['data']

    # Cache miss - fetch from API
    logger.info("Cache miss for console %s playbook attacks - fetching from API", console)

    try:
        # Get API token and environment info
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'playbook')

        # Make API call
        headers = {
            "x-apitoken": apitoken,
            "Content-Type": "application/json"
        }

        url = f"{base_url}/api/kb/vLatest/moves?details=true"
        logger.info(f"Making API call to {url}")
        response = requests.get(url, headers=headers, timeout=120)

        if response.status_code != 200:
            raise ValueError(f"API call failed with status {response.status_code}: {response.text}")

        response_data = response.json()

        if 'data' not in response_data:
            raise ValueError("API response missing 'data' field")

        attacks_data = response_data['data']

        # Cache the results (only if caching is enabled)
        if is_caching_enabled():
            playbook_cache[cache_key] = {
                'data': attacks_data,
                'timestamp': current_time
            }
            logger.info("Successfully cached %d attacks for console %s", len(attacks_data), console)
        return attacks_data

    except requests.RequestException as e:
        logger.error("Network error fetching playbook attacks for console %s: %s", console, e)
        raise ValueError(f"Failed to fetch playbook attacks: {str(e)}") from e
    except Exception as e:
        logger.error("Error fetching playbook attacks for console %s: %s", console, e)
        raise ValueError(f"Failed to fetch playbook attacks: {str(e)}") from e


def sb_get_playbook_attacks(
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
    mitre_tactic_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get filtered and paginated playbook attacks.

    Args:
        console: SafeBreach console name
        page_number: Page number (0-based)
        name_filter: Partial match on attack name (case-insensitive)
        description_filter: Partial match on attack description (case-insensitive)
        id_min: Minimum attack ID (inclusive)
        id_max: Maximum attack ID (inclusive)
        modified_date_start: Start date for modified date range (ISO format)
        modified_date_end: End date for modified date range (ISO format)
        published_date_start: Start date for published date range (ISO format)
        published_date_end: End date for published date range (ISO format)
        include_mitre_techniques: Whether to include MITRE ATT&CK data
        mitre_technique_filter: Comma-separated technique IDs/names (OR, case-insensitive partial)
        mitre_tactic_filter: Comma-separated tactic names (OR, case-insensitive partial)

    Returns:
        Dict containing paginated attacks and metadata

    Raises:
        ValueError: If console is not found or parameters are invalid
    """
    # Validate ID range - id_min should be less than or equal to id_max
    if id_min is not None and id_max is not None and id_min > id_max:
        raise ValueError(f"Invalid ID range: id_min ({id_min}) must be less than or equal to id_max ({id_max})")
    
    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    # Validate date ranges - start dates should be before end dates
    if modified_date_start is not None and modified_date_end is not None and modified_date_start > modified_date_end:
        raise ValueError(f"Invalid modified date range: modified_date_start ({modified_date_start}) must be before or equal to modified_date_end ({modified_date_end})")
    
    if published_date_start is not None and published_date_end is not None and published_date_start > published_date_end:
        raise ValueError(f"Invalid published date range: published_date_start ({published_date_start}) must be before or equal to published_date_end ({published_date_end})")
    
    try:
        # Get all attacks from cache or API
        all_attacks = _get_all_attacks_from_cache_or_api(console)

        # Auto-enable MITRE when filters need it
        needs_mitre = include_mitre_techniques or bool(mitre_technique_filter) or bool(mitre_tactic_filter)

        # Transform to reduced format
        reduced_attacks = [
            transform_reduced_playbook_attack(attack, include_mitre_techniques=needs_mitre)
            for attack in all_attacks
        ]

        # Apply filters
        filtered_attacks = filter_attacks_by_criteria(
            reduced_attacks,
            name_filter=name_filter,
            description_filter=description_filter,
            id_min=id_min,
            id_max=id_max,
            modified_date_start=modified_date_start,
            modified_date_end=modified_date_end,
            published_date_start=published_date_start,
            published_date_end=published_date_end,
            mitre_technique_filter=mitre_technique_filter,
            mitre_tactic_filter=mitre_tactic_filter
        )

        # Paginate results
        paginated_result = paginate_attacks(filtered_attacks, page_number, PAGE_SIZE)

        # Add applied filters info
        applied_filters = {}
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if description_filter:
            applied_filters['description_filter'] = description_filter
        if id_min is not None:
            applied_filters['id_min'] = id_min
        if id_max is not None:
            applied_filters['id_max'] = id_max
        if modified_date_start:
            applied_filters['modified_date_start'] = modified_date_start
        if modified_date_end:
            applied_filters['modified_date_end'] = modified_date_end
        if published_date_start:
            applied_filters['published_date_start'] = published_date_start
        if published_date_end:
            applied_filters['published_date_end'] = published_date_end
        if mitre_technique_filter:
            applied_filters['mitre_technique_filter'] = mitre_technique_filter
        if mitre_tactic_filter:
            applied_filters['mitre_tactic_filter'] = mitre_tactic_filter

        paginated_result['applied_filters'] = applied_filters

        return paginated_result

    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error in sb_get_playbook_attacks: %s", e)
        raise ValueError(f"Failed to get playbook attacks: {str(e)}") from e


def sb_get_playbook_attack_details(
    attack_id: int,
    console: str = "default",
    include_fix_suggestions: bool = False,
    include_tags: bool = False,
    include_parameters: bool = False,
    include_mitre_techniques: bool = False
) -> Dict[str, Any]:
    """
    Get detailed information for a specific playbook attack.

    Args:
        console: SafeBreach console name
        attack_id: Attack ID to get details for
        include_fix_suggestions: Whether to include fix suggestions
        include_tags: Whether to include tags
        include_parameters: Whether to include parameters
        include_mitre_techniques: Whether to include MITRE ATT&CK data

    Returns:
        Dict containing detailed attack information

    Raises:
        ValueError: If console or attack is not found
    """
    try:
        # Get all attacks from cache or API
        all_attacks = _get_all_attacks_from_cache_or_api(console)

        # Find the specific attack
        attack_data = None
        for attack in all_attacks:
            if attack.get('id') == attack_id:
                attack_data = attack
                break

        if attack_data is None:
            # Get available IDs for error message
            available_ids = [str(attack.get('id', 'unknown')) for attack in all_attacks[:10]]
            if len(all_attacks) > 10:
                available_ids.append('...')
            raise ValueError(
                f"Attack with ID {attack_id} not found. "
                f"Available IDs include: {', '.join(available_ids)}"
            )

        # Transform to full format with verbosity options
        detailed_attack = transform_full_playbook_attack(
            attack_data,
            include_fix_suggestions=include_fix_suggestions,
            include_tags=include_tags,
            include_parameters=include_parameters,
            include_mitre_techniques=include_mitre_techniques
        )

        return detailed_attack

    except ValueError:
        raise
    except Exception as e:
        logger.error("Unexpected error in sb_get_playbook_attack_details: %s", e)
        raise ValueError(f"Failed to get attack details: {str(e)}") from e


def clear_playbook_cache():
    """Clear all playbook caches. Useful for testing."""
    playbook_cache.clear()
    logger.info("Playbook cache cleared")

