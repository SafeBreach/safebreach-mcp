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
from safebreach_mcp_core.secret_utils import get_secret_for_console, get_auth_headers_for_console, check_rbac_response
from safebreach_mcp_core.token_context import get_cache_user_suffix
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from .config_types import (
    get_minimal_simulator_mapping,
    get_full_simulator_mapping,
    get_reduced_scenario_mapping,
    get_reduced_plan_mapping,
    get_scenario_detail_view,
    filter_scenarios_by_criteria,
    apply_scenario_ordering,
    paginate_scenarios,
    get_integration_catalog_entry,
    filter_integration_catalog,
    apply_integration_ordering,
    paginate_integration_list,
    get_minimal_installed_integration,
    filter_installed_integrations,
    get_installed_integration_detail_view,
    CATEGORY_TAXONOMY,
)


def _validate_category_filter(category_filter: Optional[str]) -> None:
    """Reject an unrecognized category_filter up front with the valid values (parity with the
    order_by/order_direction validation), rather than silently returning an empty result."""
    if category_filter is not None and \
            category_filter.lower() not in [c.lower() for c in CATEGORY_TAXONOMY]:
        raise ValueError(
            f"Invalid category_filter '{category_filter}'. "
            f"Valid categories are: {', '.join(CATEGORY_TAXONOMY)}"
        )


def _reject_removed_capability_flags(ti_only, vm_only) -> None:
    """The ti_only/vm_only flags were replaced by category_filter. Reject them explicitly with
    guidance, so an old caller gets a clear error instead of a silently-unfiltered result."""
    if ti_only is not None:
        raise ValueError(
            "The 'ti_only' filter was removed. Use category_filter='ti' instead. "
            f"Valid categories are: {', '.join(CATEGORY_TAXONOMY)}"
        )
    if vm_only is not None:
        raise ValueError(
            "The 'vm_only' filter was removed. Use category_filter='vulnerability_management' instead. "
            f"Valid categories are: {', '.join(CATEGORY_TAXONOMY)}"
        )

logger = logging.getLogger(__name__)

# Bounded cache: max 5 consoles, 1-hour TTL
simulators_cache = SafeBreachCache(name="simulators", maxsize=5, ttl=3600)

# Scenario caches
scenarios_cache = SafeBreachCache(name="scenarios", maxsize=5, ttl=1800)
categories_cache = SafeBreachCache(name="scenario_categories", maxsize=5, ttl=3600)
plans_cache = SafeBreachCache(name="plans", maxsize=5, ttl=1800)
users_cache = SafeBreachCache(name="users", maxsize=5, ttl=3600)
assets_cache = SafeBreachCache(name="assets", maxsize=5, ttl=3600)

# Integration-discovery caches (SAF-32798)
# Short 1-minute TTL: integrations change on demand (a user may install one and
# immediately expect Helm to reach it), so freshness is preferred over cache reuse.
integrations_catalog_cache = SafeBreachCache(name="integrations_catalog", maxsize=5, ttl=60)
installed_integrations_cache = SafeBreachCache(name="installed_integrations", maxsize=5, ttl=60)
siem_config_cache = SafeBreachCache(name="siem_config", maxsize=5, ttl=60)

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
    cache_key = f"simulators_{console}{get_cache_user_suffix()}"

    # Check cache first (only if caching is enabled)
    if is_caching_enabled("config"):
        cached = simulators_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved {len(cached)} simulators from cache for console '{console}'")
            return cached
    
    # Cache miss or expired - fetch from API using EXACT same pattern as original
    try:
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/nodes?details=true&deleted=false&assets=true&impersonatedUsers=true&includeProxies=false&deployments=false"

        headers = {"Content-Type": "application/json",
                    **get_auth_headers_for_console(console)}
        
        logger.info(f"Fetching simulators from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)
        
        try:
            response_data = response.json()
            api_data = response_data.get('data', [])
        except ValueError as e:
            logger.error("Failed to parse simulators response for console %s: %s", console, str(e))
            api_data = []
        
        # Fetch assets map for resolving asset IDs to names
        assets_map = _get_assets_map_from_cache_or_api(console)

        # Map the raw API data to our standardized format
        simulators = []
        for simulator in api_data:
            logger.info("Adding simulator %s to the return list", simulator['name'])
            simulators.append(get_minimal_simulator_mapping(simulator, assets_map=assets_map))

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
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)


        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/nodes/{simulator_id}"

        headers = {"Content-Type": "application/json",
                    **get_auth_headers_for_console(console)}

        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)
        
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


def clear_plans_cache():
    """Clear the plans cache (for testing)."""
    plans_cache.clear()


def _get_all_plans_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all custom plans (user-created scenarios) from cache or API.

    Plans live at /api/config/v2/accounts/{account_id}/plans?details=true and have
    a different schema than OOB scenarios.

    Args:
        console: SafeBreach console name

    Returns:
        List of full plan dictionaries
    """
    cache_key = f"plans_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = plans_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved {len(cached)} plans from cache for console '{console}'")
            return cached

    try:
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/config/v2/accounts/{account_id}/plans?details=true"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        logger.info(f"Fetching custom plans from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)

        response_data = response.json()
        # Plans API wraps the list in {"data": [...]}
        plans = response_data.get("data", []) if isinstance(response_data, dict) else response_data

        if is_caching_enabled("config"):
            plans_cache.set(cache_key, plans)

        logger.info(f"Retrieved {len(plans)} custom plans from API for console '{console}'")
        return plans

    except Exception as e:
        logger.error(f"Error fetching plans from API for console '{console}': {str(e)}")
        raise


def _get_users_map_from_cache_or_api(console: str) -> Dict[int, str]:
    """
    Get user ID to name mapping from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        Dict mapping user ID (int) to user name (str)
    """
    cache_key = f"users_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = users_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved users from cache for console '{console}'")
            return cached

    try:
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/users?details=false&deleted=true"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        logger.info(f"Fetching users from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)

        response_data = response.json()
        users_list = response_data.get("data", []) if isinstance(response_data, dict) else response_data
        users_map = {u["id"]: u.get("name", u.get("email", "Unknown")) for u in users_list}

        if is_caching_enabled("config"):
            users_cache.set(cache_key, users_map)

        logger.info(f"Retrieved {len(users_map)} users from API for console '{console}'")
        return users_map

    except Exception as e:
        logger.error(f"Error fetching users from API for console '{console}': {str(e)}")
        return {}  # Non-fatal — return empty map, plans will show userId instead


def _get_assets_map_from_cache_or_api(console: str) -> Dict[int, Dict[str, str]]:
    """
    Get asset ID to {name, type} mapping from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        Dict mapping asset ID (int) to {name, type} dict
    """
    cache_key = f"assets_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = assets_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved assets from cache for console '{console}'")
            return cached

    try:
        base_url = get_api_base_url(console, 'config')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/config/v1/accounts/{account_id}/assets"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        logger.info(f"Fetching assets from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)

        response_data = response.json()
        assets_list = response_data.get("data", []) if isinstance(response_data, dict) else response_data
        assets_map = {
            a["id"]: {"name": a.get("name", ""), "type": a.get("type", "")}
            for a in assets_list if isinstance(a, dict) and "id" in a
        }

        if is_caching_enabled("config"):
            assets_cache.set(cache_key, assets_map)

        logger.info(f"Retrieved {len(assets_map)} assets from API for console '{console}'")
        return assets_map

    except Exception as e:
        logger.error(f"Error fetching assets from API for console '{console}': {str(e)}")
        return {}


def _get_all_scenarios_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """
    Get all scenarios from cache or API.

    Args:
        console: SafeBreach console name

    Returns:
        List of full scenario dictionaries
    """
    cache_key = f"scenarios_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = scenarios_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved {len(cached)} scenarios from cache for console '{console}'")
            return cached

    try:
        base_url = get_api_base_url(console, 'playbook')

        api_url = f"{base_url}/api/content-manager/vLatest/scenarios"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        logger.info(f"Fetching scenarios from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)

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
    cache_key = f"categories_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = categories_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved categories from cache for console '{console}'")
            return cached

    try:
        base_url = get_api_base_url(console, 'playbook')

        api_url = f"{base_url}/api/content-manager/vLatest/scenarioCategories"
        headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

        logger.info(f"Fetching scenario categories from API for console '{console}'")
        response = requests.get(api_url, headers=headers, timeout=120)
        check_rbac_response(response)

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
        # Determine which sources to fetch based on creator_filter
        fetch_oob = creator_filter is None or creator_filter.lower() == 'safebreach'
        fetch_custom = creator_filter is None or creator_filter.lower() == 'custom'

        reduced = []

        if fetch_oob:
            all_scenarios = _get_all_scenarios_from_cache_or_api(console)
            categories_map = _get_categories_map_from_cache_or_api(console)
            reduced.extend(
                get_reduced_scenario_mapping(s, categories_map) for s in all_scenarios
            )

        if fetch_custom:
            all_plans = _get_all_plans_from_cache_or_api(console)
            users_map = _get_users_map_from_cache_or_api(console)
            reduced.extend(get_reduced_plan_mapping(p, users_map) for p in all_plans)

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
        paginated = paginate_scenarios(
            ordered,
            page_number=page_number,
            page_size=PAGE_SIZE,
            ready_to_run_filter_applied=ready_to_run_filter is not None,
        )

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

    Searches both OOB scenarios (UUID IDs) and custom plans (integer IDs).
    Returns the full raw payload with source_type='oob'|'custom' added, plus
    resolved category_names for OOB scenarios.
    """
    if scenario_id is None or (isinstance(scenario_id, str) and not scenario_id.strip()):
        raise ValueError("scenario_id parameter is required and cannot be empty")

    # Normalize to string for unified comparison (UUIDs and integer plan IDs)
    scenario_id = str(scenario_id).strip()

    # Try OOB scenarios first (UUID string IDs)
    all_scenarios = _get_all_scenarios_from_cache_or_api(console)
    categories_map = _get_categories_map_from_cache_or_api(console)

    for scenario in all_scenarios:
        if str(scenario.get("id")) == scenario_id:
            return get_scenario_detail_view(scenario, categories_map, source_type="oob")

    # Fall back to custom plans (integer IDs, stringified for comparison)
    all_plans = _get_all_plans_from_cache_or_api(console)
    users_map = _get_users_map_from_cache_or_api(console)
    for plan in all_plans:
        if str(plan.get("id")) == scenario_id:
            return get_scenario_detail_view(plan, categories_map, source_type="custom",
                                            users_map=users_map)

    raise ValueError(f"Scenario with ID '{scenario_id}' not found")


# =============================================================================
# Integration-discovery tools (SAF-32798)
# =============================================================================

def clear_integrations_catalog_cache():
    """Clear the integrations catalog cache (for testing)."""
    integrations_catalog_cache.clear()


def _get_integrations_catalog_from_cache_or_api(console: str) -> Dict[str, Any]:
    """Fetch the connector-type catalog (keyed by type) from cache or the SIEM API.

    Source: GET /api/siem/v1/accounts/{account}/config/integrations, whose response is
    wrapped in the SIEM envelope {"error": 0, "result": {<type>: <def>, ...}}.
    Reused by get_integrations, get_installed_integrations (category enrichment) and
    get_installed_integration (redaction schema + category enrichment).
    """
    cache_key = f"integrations_catalog_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = integrations_catalog_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved integrations catalog from cache for console '{console}'")
            return cached

    base_url = get_api_base_url(console, 'siem')
    account_id = get_api_account_id(console)
    api_url = f"{base_url}/api/siem/v1/accounts/{account_id}/config/integrations"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    logger.info(f"Fetching integrations catalog from API for console '{console}'")
    response = requests.get(api_url, headers=headers, timeout=120)
    check_rbac_response(response)

    payload = response.json()
    catalog = payload.get("result", payload) if isinstance(payload, dict) else payload
    if not isinstance(catalog, dict):
        catalog = {}

    if is_caching_enabled("config"):
        integrations_catalog_cache.set(cache_key, catalog)

    logger.info(f"Retrieved {len(catalog)} connector types from API for console '{console}'")
    return catalog


def sb_get_integrations(
    console: str = "default",
    page_number: int = 0,
    name_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    vendor_filter: Optional[str] = None,
    order_by: str = "name",
    order_direction: str = "asc",
    ti_only: Optional[bool] = None,
    vm_only: Optional[bool] = None,
) -> Dict[str, Any]:
    """Get the filtered, paginated catalog of available connector *types*.

    Returns the menu of connector types that could be installed (no account data, no secrets).
    `category_filter` matches the derived `categories` membership (see derive_categories).
    `ti_only`/`vm_only` are removed and rejected — use `category_filter` instead.
    """
    _reject_removed_capability_flags(ti_only, vm_only)
    _validate_category_filter(category_filter)
    valid_order_by = ['name', 'type', 'category', 'vendor']
    if order_by not in valid_order_by:
        raise ValueError(
            f"Invalid order_by parameter '{order_by}'. Valid values are: {', '.join(valid_order_by)}"
        )
    valid_order_direction = ['asc', 'desc']
    if order_direction not in valid_order_direction:
        raise ValueError(
            f"Invalid order_direction parameter '{order_direction}'. "
            f"Valid values are: {', '.join(valid_order_direction)}"
        )
    if page_number < 0:
        raise ValueError(f"page_number must be >= 0, got {page_number}")

    try:
        catalog = _get_integrations_catalog_from_cache_or_api(console)
        entries = [get_integration_catalog_entry(type_key, raw, catalog) for type_key, raw in catalog.items()]

        filtered = filter_integration_catalog(
            entries,
            name_filter=name_filter,
            category_filter=category_filter,
            vendor_filter=vendor_filter,
        )
        ordered = apply_integration_ordering(filtered, order_by=order_by, order_direction=order_direction)
        paginated = paginate_integration_list(ordered, page_number, PAGE_SIZE, 'integrations')

        applied_filters: Dict[str, Any] = {}
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if category_filter:
            applied_filters['category_filter'] = category_filter
        if vendor_filter:
            applied_filters['vendor_filter'] = vendor_filter
        # Always record the effective ordering so a response self-documents how it was sorted.
        applied_filters['order_by'] = order_by
        applied_filters['order_direction'] = order_direction

        paginated['applied_filters'] = applied_filters
        return paginated

    except Exception as e:
        logger.error(f"Error getting integrations for console '{console}': {str(e)}")
        return {
            "error": f"Failed to get integrations: {str(e)}",
            "console": console,
        }


def clear_installed_integrations_cache():
    """Clear the installed-integrations cache (for testing)."""
    installed_integrations_cache.clear()


def _get_installed_integrations_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """Fetch the installed connectors from cache or the SIEM API.

    Source: GET /api/siem/v1/accounts/{account}/config/integrations/installed, whose
    response is wrapped in the SIEM envelope {"error": 0, "result": [<connector>, ...]}.
    The live API already returns a slim id/type/name/enabled per connector.
    """
    cache_key = f"installed_integrations_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = installed_integrations_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved installed integrations from cache for console '{console}'")
            return cached

    base_url = get_api_base_url(console, 'siem')
    account_id = get_api_account_id(console)
    api_url = f"{base_url}/api/siem/v1/accounts/{account_id}/config/integrations/installed"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    logger.info(f"Fetching installed integrations from API for console '{console}'")
    response = requests.get(api_url, headers=headers, timeout=120)
    check_rbac_response(response)

    payload = response.json()
    installed = payload.get("result", payload) if isinstance(payload, dict) else payload
    if not isinstance(installed, list):
        installed = []

    if is_caching_enabled("config"):
        installed_integrations_cache.set(cache_key, installed)

    logger.info(f"Retrieved {len(installed)} installed integrations from API for console '{console}'")
    return installed


def sb_get_installed_integrations(
    console: str = "default",
    page_number: int = 0,
    name_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    enabled_filter: Optional[bool] = None,
    category_filter: Optional[str] = None,
    order_by: str = "name",
    order_direction: str = "asc",
    ti_only: Optional[bool] = None,
    vm_only: Optional[bool] = None,
) -> Dict[str, Any]:
    """Get the filtered, paginated list of INSTALLED integration connectors (slim, no secrets).

    Each connector is enriched with its `category` (raw label) and derived `categories`
    membership, joined from the catalog by type. `category_filter` matches the derived
    membership — e.g. `category_filter='ti'` lists installed TI feeds (replacing the former
    get_ti_integrations tool), `category_filter='vulnerability_management'` lists installed
    VM connectors. `ti_only`/`vm_only` are removed and rejected — use `category_filter`.
    """
    _reject_removed_capability_flags(ti_only, vm_only)
    _validate_category_filter(category_filter)
    valid_order_by = ['name', 'type', 'id', 'enabled', 'category']
    if order_by not in valid_order_by:
        raise ValueError(
            f"Invalid order_by parameter '{order_by}'. Valid values are: {', '.join(valid_order_by)}"
        )
    valid_order_direction = ['asc', 'desc']
    if order_direction not in valid_order_direction:
        raise ValueError(
            f"Invalid order_direction parameter '{order_direction}'. "
            f"Valid values are: {', '.join(valid_order_direction)}"
        )
    if page_number < 0:
        raise ValueError(f"page_number must be >= 0, got {page_number}")

    try:
        raw_installed = _get_installed_integrations_from_cache_or_api(console)
        catalog = _get_integrations_catalog_from_cache_or_api(console)
        entries = [get_minimal_installed_integration(c, catalog) for c in raw_installed]

        filtered = filter_installed_integrations(
            entries,
            name_filter=name_filter,
            type_filter=type_filter,
            enabled_filter=enabled_filter,
            category_filter=category_filter,
        )
        ordered = apply_integration_ordering(filtered, order_by=order_by, order_direction=order_direction)
        paginated = paginate_integration_list(ordered, page_number, PAGE_SIZE, 'installed_integrations')

        applied_filters: Dict[str, Any] = {}
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if type_filter:
            applied_filters['type_filter'] = type_filter
        if enabled_filter is not None:
            applied_filters['enabled_filter'] = enabled_filter
        if category_filter:
            applied_filters['category_filter'] = category_filter
        # Always record the effective ordering so a response self-documents how it was sorted.
        applied_filters['order_by'] = order_by
        applied_filters['order_direction'] = order_direction

        paginated['applied_filters'] = applied_filters
        return paginated

    except Exception as e:
        logger.error(f"Error getting installed integrations for console '{console}': {str(e)}")
        return {
            "error": f"Failed to get installed integrations: {str(e)}",
            "console": console,
        }


def clear_siem_config_cache():
    """Clear the SIEM full-config cache (for testing)."""
    siem_config_cache.clear()


def _get_siem_config_connectors_from_cache_or_api(console: str) -> List[Dict[str, Any]]:
    """Fetch the FULL connector configs from the SIEM config blob (cache or API).

    Source: GET /api/siem/v1/accounts/{account}/config → envelope {"error":0,"result":{...}}
    whose `result.connectors[]` holds the full per-connector config (with secrets as
    vault refs). Used by get_installed_integration since there is no single-connector GET.
    """
    cache_key = f"siem_config_connectors_{console}{get_cache_user_suffix()}"

    if is_caching_enabled("config"):
        cached = siem_config_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Retrieved SIEM config connectors from cache for console '{console}'")
            return cached

    base_url = get_api_base_url(console, 'siem')
    account_id = get_api_account_id(console)
    api_url = f"{base_url}/api/siem/v1/accounts/{account_id}/config"
    headers = {"Content-Type": "application/json", **get_auth_headers_for_console(console)}

    logger.info(f"Fetching SIEM config from API for console '{console}'")
    response = requests.get(api_url, headers=headers, timeout=120)
    check_rbac_response(response)

    payload = response.json()
    config = payload.get("result", payload) if isinstance(payload, dict) else payload
    connectors = config.get("connectors", []) if isinstance(config, dict) else []
    if not isinstance(connectors, list):
        connectors = []

    if is_caching_enabled("config"):
        siem_config_cache.set(cache_key, connectors)

    logger.info(f"Retrieved {len(connectors)} full connector configs from API for console '{console}'")
    return connectors


def sb_get_installed_integration(console: str = "default", integration_id: Optional[str] = None) -> Dict[str, Any]:
    """Get the full config of a single INSTALLED connector by id, with secrets redacted.

    There is no dedicated single-connector API, so the connector is located in the SIEM
    config blob (`/config`) and redacted in Python against the catalog's sensitive-field schema.
    """
    if integration_id is None or (isinstance(integration_id, str) and not integration_id.strip()):
        raise ValueError("integration_id parameter is required and cannot be empty")

    integration_id = str(integration_id).strip()

    try:
        connectors = _get_siem_config_connectors_from_cache_or_api(console)
        catalog = _get_integrations_catalog_from_cache_or_api(console)

        for connector in connectors:
            if str(connector.get("id")) == integration_id:
                detail = get_installed_integration_detail_view(connector, catalog)
                return {
                    "console": console,
                    "integration_id": integration_id,
                    "integration": detail["integration"],
                    "redacted_fields": detail["redacted_fields"],
                }

        return {
            "error": f"Installed integration with id '{integration_id}' not found",
            "console": console,
            "hint_to_agent": "Call get_installed_integrations to list valid connector ids.",
        }

    except Exception as e:
        logger.error(f"Error getting installed integration '{integration_id}' for console '{console}': {str(e)}")
        return {
            "error": f"Failed to get installed integration: {str(e)}",
            "console": console,
        }