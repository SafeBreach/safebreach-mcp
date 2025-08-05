"""
SafeBreach Config Functions

This module provides functions for SafeBreach configuration management,
specifically for simulator operations and infrastructure management.
"""

import requests
import logging
import time
from typing import Dict, List, Optional, Any
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import safebreach_envs
from .config_types import get_minimal_simulator_mapping, get_full_simulator_mapping

logger = logging.getLogger(__name__)

# Global cache for simulators
simulators_cache = {}

# Configuration constants
PAGE_SIZE = 10
CACHE_TTL = 3600  # 1 hour in seconds


def sb_get_console_simulators(
    console: str,
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
    current_time = time.time()
    
    # Check cache first
    if cache_key in simulators_cache:
        data, timestamp = simulators_cache[cache_key]
        if current_time - timestamp < CACHE_TTL:
            logger.info(f"Retrieved {len(data)} simulators from cache for console '{console}'")
            return data
    
    # Cache miss or expired - fetch from API using EXACT same pattern as original
    try:
        apitoken = get_secret_for_console(console)
        safebreach_env = safebreach_envs[console]
        
        api_url = f"https://{safebreach_env['url']}/api/config/v1/accounts/{safebreach_env['account']}/nodes?details=true&deleted=false&assets=false&impersonatedUsers=false&includeProxies=false&deployments=false"
        
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
        
        # Cache the result
        simulators_cache[cache_key] = (simulators, current_time)
        
        if len(simulators) == 0:
            logger.warning("Zero simulators found on the environment %s", safebreach_env)
        
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


def sb_get_simulator_details(console: str, simulator_id: str) -> Dict[str, Any]:
    """
    Returns the full details of a specific Safebreach simulator linked to a given Safebreach management console.
    """
    # Validate required parameters
    if not simulator_id or not simulator_id.strip():
        raise ValueError("simulator_id parameter is required and cannot be empty")
    
    try:
        apitoken = get_secret_for_console(console)
        safebreach_env = safebreach_envs[console]
        logger.info("Getting api key for console %s", console)

        api_url = f"https://{safebreach_env['url']}/api/config/v1/accounts/{safebreach_env['account']}/nodes/{simulator_id}"

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