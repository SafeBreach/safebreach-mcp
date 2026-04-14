"""
SafeBreach Config Functions

This module provides functions for SafeBreach configuration management,
specifically for simulator operations and infrastructure management.
"""

import requests
import logging
from typing import Dict, List, Optional, Any
from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.safebreach_cache import SafeBreachCache
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from .config_types import (
    get_minimal_simulator_mapping,
    get_full_simulator_mapping,
    get_reduced_scenario_mapping,
    filter_scenarios_by_criteria,
    apply_scenario_ordering,
    paginate_scenarios,
)

logger = logging.getLogger(__name__)

# Bounded cache: max 5 consoles, 1-hour TTL
simulators_cache = SafeBreachCache(name="simulators", maxsize=5, ttl=3600)

# Scenario caches
scenarios_cache = SafeBreachCache(name="scenarios", maxsize=5, ttl=1800)
categories_cache = SafeBreachCache(name="scenario_categories", maxsize=5, ttl=3600)

# Configuration constants
PAGE_SIZE = 10


def sb_get_console_simulators(
    console: str = "default",
    status_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    label_filter: Optional[str] = None,
    os_type_filter: Optional[str] = None,
    critical_only: Optional[bool] = None,
    order_by: str = "name",
    order_direction: str = "asc"
) -> Dict[str, Any]:
    """
    Get filtered list of Safebreach simulators for a given console.
    
    Args:
        console: SafeBreach console name
        status_filter: Filter by status ('connected', 'disconnected', 'enabled', 'disabled')
        name_filter: Filter by simulator name (partial match)
        label_filter: Filter by simulator labels (partial match)
        os_type_filter: Filter by OS type
        critical_only: Filter for critical simulators only
        order_by: Field to order by ('name', 'id', 'version', 'isConnected', 'isEnabled')
        order_direction: Order direction ('asc' or 'desc')
        
    Returns:
        Dict containing filtered simulators, total count, and applied filters
    """
    # Validate order_by parameter
    valid_order_by = ['name', 'id', 'version', 'isConnected', 'isEnabled']
    if order_by not in valid_order_by:
        raise ValueError(f"Invalid order_by parameter '{order_by}'. Valid values are: {', '.join(valid_order_by)}")
    
    # Validate order_direction parameter
    valid_order_direction = ['asc', 'desc']
    if order_direction not in valid_order_direction:
        raise ValueError(f"Invalid order_direction parameter '{order_direction}'. Valid values are: {', '.join(valid_order_direction)}")
    
    # Validate status_filter parameter
    if status_filter is not None:
        valid_status_filters = ['connected', 'disconnected', 'enabled', 'disabled']
        if status_filter.lower() not in valid_status_filters:
            raise ValueError(f"Invalid status_filter parameter '{status_filter}'. Valid values are: {', '.join(valid_status_filters)}")
    
    try:
        # Get all simulators from cache or API
        all_simulators = _get_all_simulators_from_cache_or_api(console)
        
        # Apply filters
        filtered_simulators = _apply_simulator_filters(
            all_simulators,
            status_filter=status_filter,
            name_filter=name_filter,
            label_filter=label_filter,
            os_type_filter=os_type_filter,
            critical_only=critical_only
        )
        
        # Apply ordering
        ordered_simulators = _apply_simulator_ordering(
            filtered_simulators,
            order_by=order_by,
            order_direction=order_direction
        )
        
        # Track applied filters
        applied_filters = {}
        if status_filter:
            applied_filters['status_filter'] = status_filter
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if label_filter:
            applied_filters['label_filter'] = label_filter
        if os_type_filter:
            applied_filters['os_type_filter'] = os_type_filter
        if critical_only is not None:
            applied_filters['critical_only'] = critical_only
        if order_by != "name":
            applied_filters['order_by'] = order_by
        if order_direction != "asc":
            applied_filters['order_direction'] = order_direction
        
        return {
            "simulators": ordered_simulators,
            "total_simulators": len(ordered_simulators),
            "applied_filters": applied_filters
        }
        
    except Exception as e:
        logger.error(f"Error getting simulators for console '{console}': {str(e)}")
        return {
            "error": f"Failed to get simulators: {str(e)}",
            "console": console
        }


def _get_all_simulators_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all simulators from cache or API.
    
    Args:
        console: SafeBreach console name
        
    Returns:
        List of simulator dictionaries
    """
    cache_key = f"simulators_{console}"

    # Check cache first (only if caching is enabled)
    if is_caching_enabled("config"):
        cached = simulators_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved {len(cached)} simulators from cache for console '{console}'")
            return cached
    
    # Cache miss or expired - fetch from API using EXACT same pattern as original
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/nodes?details=true&deleted=false&assets=false&impersonatedUsers=false&includeProxies=false&deployments=false"

        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}
        
        logger.info(f"Fetching simulators from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        
        try:
            response_data = response.json()
            api_data = response_data.get('data', [])
        except ValueError as e:
            logger.error("Failed to parse simulators response for console %s: %s", console, str(e))
            api_data = []
        
        # Map the raw API data to our standardized format - same pattern as original
        simulators = []
        for simulator in api_data:
            logger.info("Adding simulator %s to the return list", simulator['name'])
            simulators.append(get_minimal_simulator_mapping(simulator))

        # Cache the result (only if caching is enabled)
        if is_caching_enabled("config"):
            simulators_cache.set(cache_key, simulators)
        
        if len(simulators) == 0:
            logger.warning("Zero simulators found on the environment %s", console)
        
        logger.info(f"Retrieved {len(simulators)} simulators from API for console '{console}'")
        return simulators
        
    except Exception as e:
        logger.error(f"Error fetching simulators from API for console '{console}': {str(e)}")
        raise


def _apply_simulator_filters(
    simulators: List[Dict[str, Any]],
    status_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    label_filter: Optional[str] = None,
    os_type_filter: Optional[str] = None,
    critical_only: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """
    Apply filters to simulator list.
    
    Args:
        simulators: List of simulator dictionaries
        status_filter: Filter by status
        name_filter: Filter by name (partial match)
        label_filter: Filter by labels (partial match)
        os_type_filter: Filter by OS type
        critical_only: Filter for critical simulators only
        
    Returns:
        Filtered list of simulators
    """
    filtered = simulators
    
    # Apply status filter
    if status_filter:
        if status_filter.lower() == 'connected':
            filtered = [s for s in filtered if s.get('isConnected', False)]
        elif status_filter.lower() == 'disconnected':
            filtered = [s for s in filtered if not s.get('isConnected', False)]
        elif status_filter.lower() == 'enabled':
            filtered = [s for s in filtered if s.get('isEnabled', False)]
        elif status_filter.lower() == 'disabled':
            filtered = [s for s in filtered if not s.get('isEnabled', False)]
    
    # Apply name filter
    if name_filter:
        filtered = [s for s in filtered if name_filter.lower() in s.get('name', '').lower()]
    
    # Apply label filter
    if label_filter:
        filtered = [s for s in filtered 
                   if any(label_filter.lower() in label.lower() 
                         for label in s.get('labels', []))]
    
    # Apply OS type filter
    if os_type_filter:
        filtered = [s for s in filtered 
                   if s.get('OS', {}).get('type', '').lower() == os_type_filter.lower()]
    
    # Apply critical filter
    if critical_only is not None:
        filtered = [s for s in filtered 
                   if s.get('isCritical', False) == critical_only]
    
    return filtered


def _apply_simulator_ordering(
    simulators: List[Dict[str, Any]],
    order_by: str = "name",
    order_direction: str = "asc"
) -> List[Dict[str, Any]]:
    """
    Apply ordering to simulator list.
    
    Args:
        simulators: List of simulator dictionaries
        order_by: Field to order by
        order_direction: Order direction ('asc' or 'desc')
        
    Returns:
        Ordered list of simulators
    """
    reverse = order_direction.lower() == 'desc'
    
    # Define sort key functions
    def get_sort_key(sim):
        if order_by == 'name':
            return sim.get('name', '').lower()
        elif order_by == 'id':
            return sim.get('id', '')
        elif order_by == 'version':
            return sim.get('version', '')
        elif order_by == 'isConnected':
            return sim.get('isConnected', False)
        elif order_by == 'isEnabled':
            return sim.get('isEnabled', False)
        else:
            return sim.get('name', '').lower()  # Default to name
    
    return sorted(simulators, key=get_sort_key, reverse=reverse)


def sb_get_simulator_details(simulator_id: str, console: str = "default") -> Dict[str, Any]:
    """
    Returns the full details of a specific Safebreach simulator linked to a given Safebreach management console.
    """
    # Validate required parameters
    if not simulator_id or not simulator_id.strip():
        raise ValueError("simulator_id parameter is required and cannot be empty")
    
    try:
        logger.info("Getting api key for console %s", console)
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)


        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/nodes/{simulator_id}"

        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}

        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        
        try:
            response_data = response.json()
        except ValueError as e:
            logger.error("Failed to parse simulator details response for simulator ID %s: %s", simulator_id, str(e))
            raise
        
        if 'data' not in response_data:
            logger.error("Invalid response format for simulator ID %s: missing 'data' key", simulator_id)
            raise ValueError(f"Invalid response format: missing 'data' key")
        
        simulator = response_data['data']
        stripped_simulator = get_full_simulator_mapping(simulator)
        return stripped_simulator
        
    except Exception as e:
        logger.error(f"Error getting simulator details for ID '{simulator_id}' from console '{console}': {str(e)}")
        raise


# --- Scenario Functions ---


def clear_scenarios_cache():
    """Clear the scenarios cache (for testing)."""
    scenarios_cache.clear()


def clear_categories_cache():
    """Clear the categories cache (for testing)."""
    categories_cache.clear()


def _get_all_scenarios_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all scenarios from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        List of full scenario dictionaries
    """
    cache_key = f"scenarios_{console}"

    if is_caching_enabled("config"):
        cached = scenarios_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved {len(cached)} scenarios from cache for console '{console}'")
            return cached

    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'content-manager')

        api_url = f"{base_url}/api/content-manager/vLatest/scenarios"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

        logger.info(f"Fetching scenarios from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()

        scenarios = response.json()

        if is_caching_enabled("config"):
            scenarios_cache.set(cache_key, scenarios)

        logger.info(f"Retrieved {len(scenarios)} scenarios from API for console '{console}'")
        return scenarios

    except Exception as e:
        logger.error(f"Error fetching scenarios from API for console '{console}': {str(e)}")
        raise


def _get_categories_map_from_cache_or_api(console: str) -> Dict[int, str]:
    """
    Get category ID to name mapping from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        Dict mapping category ID (int) to category name (str)
    """
    cache_key = f"categories_{console}"

    if is_caching_enabled("config"):
        cached = categories_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved categories from cache for console '{console}'")
            return cached

    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'content-manager')

        api_url = f"{base_url}/api/content-manager/vLatest/scenarioCategories"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

        logger.info(f"Fetching scenario categories from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()

        categories_list = response.json()
        categories_map = {cat["id"]: cat["name"] for cat in categories_list}

        if is_caching_enabled("config"):
            categories_cache.set(cache_key, categories_map)

        logger.info(f"Retrieved {len(categories_map)} categories from API for console '{console}'")
        return categories_map

    except Exception as e:
        logger.error(f"Error fetching categories from API for console '{console}': {str(e)}")
        raise


def sb_get_scenarios(
    console: str = "default",
    page_number: int = 0,
    name_filter: Optional[str] = None,
    creator_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    recommended_filter: Optional[bool] = None,
    tag_filter: Optional[str] = None,
    ready_to_run_filter: Optional[bool] = None,
    order_by: str = "name",
    order_direction: str = "asc",
) -> Dict[str, Any]:
    """
    Get filtered and paginated list of scenarios for a given console.
    """
    valid_order_by = ['name', 'step_count', 'createdAt', 'updatedAt']
    if order_by not in valid_order_by:
        raise ValueError(
            f"Invalid order_by parameter '{order_by}'. "
            f"Valid values are: {', '.join(valid_order_by)}"
        )

    valid_order_direction = ['asc', 'desc']
    if order_direction not in valid_order_direction:
        raise ValueError(
            f"Invalid order_direction parameter '{order_direction}'. "
            f"Valid values are: {', '.join(valid_order_direction)}"
        )

    if creator_filter is not None:
        valid_creator_filters = ['safebreach', 'custom']
        if creator_filter.lower() not in valid_creator_filters:
            raise ValueError(
                f"Invalid creator_filter parameter '{creator_filter}'. "
                f"Valid values are: {', '.join(valid_creator_filters)}"
            )

    if page_number < 0:
        raise ValueError(f"page_number must be >= 0, got {page_number}")

    try:
        all_scenarios = _get_all_scenarios_from_cache_or_api(console)
        categories_map = _get_categories_map_from_cache_or_api(console)

        reduced = [
            get_reduced_scenario_mapping(s, categories_map) for s in all_scenarios
        ]

        filtered = filter_scenarios_by_criteria(
            reduced,
            name_filter=name_filter,
            creator_filter=creator_filter,
            category_filter=category_filter,
            recommended_filter=recommended_filter,
            tag_filter=tag_filter,
            ready_to_run_filter=ready_to_run_filter,
        )

        ordered = apply_scenario_ordering(filtered, order_by=order_by, order_direction=order_direction)
        paginated = paginate_scenarios(ordered, page_number=page_number, page_size=PAGE_SIZE)

        applied_filters = {}
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if creator_filter:
            applied_filters['creator_filter'] = creator_filter
        if category_filter:
            applied_filters['category_filter'] = category_filter
        if recommended_filter is not None:
            applied_filters['recommended_filter'] = recommended_filter
        if tag_filter:
            applied_filters['tag_filter'] = tag_filter
        if ready_to_run_filter is not None:
            applied_filters['ready_to_run_filter'] = ready_to_run_filter
        if order_by != "name":
            applied_filters['order_by'] = order_by
        if order_direction != "asc":
            applied_filters['order_direction'] = order_direction

        paginated['applied_filters'] = applied_filters
        return paginated

    except Exception as e:
        logger.error(f"Error getting scenarios for console '{console}': {str(e)}")
        return {
            "error": f"Failed to get scenarios: {str(e)}",
            "console": console,
        }


def sb_get_scenario_details(scenario_id: str, console: str = "default") -> Dict[str, Any]:
    """
    Get full details of a specific scenario by ID.
    """
    if not scenario_id or not scenario_id.strip():
        raise ValueError("scenario_id parameter is required and cannot be empty")

    all_scenarios = _get_all_scenarios_from_cache_or_api(console)
    categories_map = _get_categories_map_from_cache_or_api(console)

    for scenario in all_scenarios:
        if scenario.get("id") == scenario_id:
            result = dict(scenario)
            result["category_names"] = [
                categories_map[cat_id]
                for cat_id in scenario.get("categories", [])
                if cat_id in categories_map
            ]
            return result

    raise ValueError(f"Scenario with ID '{scenario_id}' not found")