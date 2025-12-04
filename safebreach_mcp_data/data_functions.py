"""
SafeBreach Data Functions

This module provides functions for SafeBreach data operations,
specifically for test and simulation data management.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Iterable

import requests
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from .data_types import (
    get_reduced_test_summary_mapping,
    get_reduced_simulation_result_entity,
    get_full_simulation_result_entity,
    get_reduced_security_control_events_mapping,
    get_full_security_control_events_mapping
)
from .drifts_metadata import drift_types_mapping

logger = logging.getLogger(__name__)

# Global caches
tests_cache = {}
simulations_cache = {}
security_control_events_cache = {}

# Configuration constants
PAGE_SIZE = 10
CACHE_TTL = 3600  # 1 hour in seconds


def _normalize_numeric(value: Any) -> Optional[float]:
    """
    Normalize numeric values that may arrive as strings or other types.
    Returns None when the value cannot be interpreted as a number.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _get_timestamp_from_keys(test: Dict[str, Any], keys: Iterable[str], default: Optional[float] = None) -> Optional[float]:
    """
    Try to extract a numeric timestamp from the test entity using the provided keys.
    Returns the first successfully parsed value, or the supplied default.
    """
    for key in keys:
        value = _normalize_numeric(test.get(key))
        if value is not None:
            return value
    return default



def sb_get_tests_history(
    console: str = "default",
    page_number: int = 0,
    test_type: Optional[str] = None,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
    status_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    order_by: str = "end_time",
    order_direction: str = "desc"
) -> Dict[str, Any]:
    """
    Get filtered and paginated test history.
    
    Args:
        console: SafeBreach console name
        page_number: Page number (0-based)
        test_type: Filter by test type ('validate', 'propagate')
        start_date: Start date filter (Unix timestamp)
        end_date: End date filter (Unix timestamp)
        status_filter: Filter by status ('completed', 'canceled', 'failed', 'running')
        name_filter: Filter by test name (partial match)
        order_by: Field to order by ('end_time', 'start_time', 'name', 'duration')
        order_direction: Order direction ('desc', 'asc')
        
    Returns:
        Dict containing filtered tests, pagination info, and applied filters
    """
    # Validate critical parameters first (page_number should be checked before optional sorting parameters)
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    # Validate test_type parameter
    if test_type is not None:
        valid_test_types = ['validate', 'propagate']
        if test_type.lower() not in valid_test_types:
            raise ValueError(f"Invalid test_type parameter '{test_type}'. Valid values are: {', '.join(valid_test_types)}")
    
    # Validate order_by parameter
    valid_order_by = ['end_time', 'start_time', 'name', 'duration']
    if order_by not in valid_order_by:
        raise ValueError(f"Invalid order_by parameter '{order_by}'. Valid values are: {', '.join(valid_order_by)}")
    
    # Validate order_direction parameter
    valid_order_direction = ['asc', 'desc']
    if order_direction not in valid_order_direction:
        raise ValueError(f"Invalid order_direction parameter '{order_direction}'. Valid values are: {', '.join(valid_order_direction)}")
    
    # Validate date range - start_date should be before end_date
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError(f"Invalid date range: start_date ({start_date}) must be before or equal to end_date ({end_date})")
    
    try:
        # Get all tests from cache or API
        normalized_status = status_filter.lower() if isinstance(status_filter, str) else None
        use_cache = normalized_status != 'running'  # Don't use cache when running tests are requested
        all_tests = _get_all_tests_from_cache_or_api(console, use_cache=use_cache)
        
        # Apply filters
        filtered_tests = _apply_filters(
            all_tests,
            test_type=test_type,
            start_date=start_date,
            end_date=end_date,
            status_filter=status_filter,
            name_filter=name_filter
        )
        
        # Apply ordering
        ordered_tests = _apply_ordering(
            filtered_tests,
            order_by=order_by,
            order_direction=order_direction
        )
        
        # Calculate pagination info
        total_tests = len(ordered_tests)
        total_pages = (total_tests + PAGE_SIZE - 1) // PAGE_SIZE
        
        # Validate page overflow
        if total_pages > 0 and page_number >= total_pages:
            raise ValueError(f"Invalid page_number parameter '{page_number}'. Available pages range from 0 to {total_pages - 1} (total {total_pages} pages)")
        
        # Apply pagination
        start_index = page_number * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        page_tests = ordered_tests[start_index:end_index]
        
        # Track applied filters
        applied_filters = {}
        if test_type:
            applied_filters['test_type'] = test_type
        if start_date:
            applied_filters['start_date'] = start_date
        if end_date:
            applied_filters['end_date'] = end_date
        if status_filter:
            applied_filters['status_filter'] = status_filter
        if name_filter:
            applied_filters['name_filter'] = name_filter
        if order_by != "end_time":
            applied_filters['order_by'] = order_by
        if order_direction != "desc":
            applied_filters['order_direction'] = order_direction
        
        return {
            "page_number": page_number,
            "total_pages": total_pages,
            "total_tests": total_tests,
            "tests_in_page": page_tests,
            "applied_filters": applied_filters,
            "hint_to_agent": f"You can scan next page by specifying page_number={page_number + 1}" if page_number + 1 < total_pages else None
        }
        
    except Exception as e:
        logger.error("Error getting test history for console '%s': %s", console, str(e))
        raise


def _get_all_tests_from_cache_or_api(console: str = "default", use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Get all tests from cache or API.
    
    Args:
        console: SafeBreach console name
        use_cache: Whether to use cached results when available
        
    Returns:
        List of test dictionaries
    """
    cache_key = f"tests_{console}"
    current_time = time.time()
    
    # Check cache first
    if use_cache and cache_key in tests_cache:
        data, timestamp = tests_cache[cache_key]
        if current_time - timestamp < CACHE_TTL:
            logger.info("Retrieved %d tests from cache for console '%s'", len(data), console)
            return data
    
    # Cache miss or expired - fetch from API using EXACT same pattern as original
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)
        
        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries?size=1000&includeArchived=false"
        
        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}
        
        logger.info("Fetching tests from API for console '%s'", console)
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()

        try:
            tests_summaries = response.json()
        except ValueError as e:
            logger.error("Failed to parse tests history response for console %s: %s", console, str(e))
            tests_summaries = []
        
        # Map the raw API data to our standardized format - same pattern as original
        tests = []
        for test_summary in tests_summaries:
            logger.info("Adding test %s to the return list", test_summary['planName'])
            tests.append(get_reduced_test_summary_mapping(test_summary))
        
        # Cache the result so subsequent calls can reuse it
        tests_cache[cache_key] = (tests, current_time)
        
        logger.info("Retrieved %d tests from API for console '%s'", len(tests), console)
        return tests
        
    except Exception as e:
        logger.error("Error fetching tests from API for console '%s': %s", console, str(e))
        raise


def _apply_filters(
    tests: List[Dict[str, Any]],
    test_type: Optional[str] = None,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
    status_filter: Optional[str] = None,
    name_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Apply filters to test list.
    
    Args:
        tests: List of test dictionaries
        test_type: Filter by test type
        start_date: Start date filter
        end_date: End date filter
        status_filter: Status filter
        name_filter: Name filter
        
    Returns:
        Filtered list of tests
    """
    filtered = tests
    
    # Apply test type filter
    if test_type:
        if test_type.lower() == 'validate':
            # BAS tests - without "ALM" in systemTags
            filtered = [t for t in filtered if 'ALM' not in t['test_type']]
        elif test_type.lower() == 'propagate':
            # ALM tests - with "ALM" in systemTags
            filtered = [t for t in filtered if 'ALM' in t['test_type']]
    
    # Apply date filters
    if start_date:
        filtered = [
            t for t in filtered
            if (
                (timestamp := _get_timestamp_from_keys(t, ('end_time', 'start_time'))) is not None
                and timestamp >= start_date
            )
        ]
    if end_date:
        filtered = [
            t for t in filtered
            if (
                (timestamp := _get_timestamp_from_keys(t, ('end_time', 'start_time'))) is not None
                and timestamp <= end_date
            )
        ]
    
    # Apply status filter
    if status_filter:
        filtered = [t for t in filtered 
                   if t.get('status', '').lower() == status_filter.lower()]
    
    # Apply name filter
    if name_filter:
        filtered = [t for t in filtered 
                   if name_filter.lower() in t.get('name', '').lower()]
    
    return filtered


def _apply_ordering(
    tests: List[Dict[str, Any]],
    order_by: str = "end_time",
    order_direction: str = "desc"
) -> List[Dict[str, Any]]:
    """
    Apply ordering to test list.
    
    Args:
        tests: List of test dictionaries
        order_by: Field to order by
        order_direction: Order direction
        
    Returns:
        Ordered list of tests
    """
    reverse = order_direction.lower() == 'desc'

    def get_sort_key(test):
        if order_by == 'end_time':
            value = _get_timestamp_from_keys(test, ('end_time', 'start_time'), default=float('-inf'))
            return value
        elif order_by == 'start_time':
            value = _get_timestamp_from_keys(test, ('start_time', 'end_time'), default=float('-inf'))
            return value
        elif order_by == 'name':
            return test.get('name', '').lower()
        elif order_by == 'duration':
            numeric_value = _normalize_numeric(test.get('duration'))
            return numeric_value if numeric_value is not None else float('-inf')
        else:
            value = _get_timestamp_from_keys(test, ('end_time', 'start_time'), default=float('-inf'))
            return value  # Default to end_time
    
    return sorted(tests, key=get_sort_key, reverse=reverse)


def _find_previous_test_by_name(
    test_name: str,
    before_start_time: float,
    console: str = "default"
) -> Optional[Dict[str, Any]]:
    """
    Fallback helper to locate the most recent test matching ``test_name`` that ended before ``before_start_time``.
    This bypasses pagination constraints of ``sb_get_tests_history``.
    """
    try:
        all_tests = _get_all_tests_from_cache_or_api(console, use_cache=False)
    except Exception as exc:
        logger.error("Failed to fetch tests for fallback baseline search on %s: %s", console, exc)
        return None

    matching_tests: List[Dict[str, Any]] = []
    for test in all_tests:
        if not isinstance(test.get('name'), str):
            continue
        if test_name.lower() not in test['name'].lower():
            continue

        timestamp = _get_timestamp_from_keys(test, ('end_time', 'start_time'))
        if timestamp is None or timestamp > before_start_time:
            continue

        matching_tests.append(test)

    if not matching_tests:
        return None

    matching_tests.sort(
        key=lambda t: _get_timestamp_from_keys(t, ('end_time', 'start_time'), default=float('-inf')),
        reverse=True
    )
    return matching_tests[0]


def sb_get_test_details(test_id: str, console: str = "default", include_simulations_statistics: bool = False) -> Dict[str, Any]:
    """
    Returns the details of a specific test executed on a given SafeBreach management console.
    """
    # Validate required parameters
    if not test_id or not test_id.strip():
        raise ValueError("test_id parameter is required and cannot be empty")
    
    # Validate boolean parameter - handle None gracefully
    if include_simulations_statistics is None:
        include_simulations_statistics = False
    elif not isinstance(include_simulations_statistics, bool):
        raise ValueError(f"Invalid include_simulations_statistics parameter '{include_simulations_statistics}'. Must be a boolean value (True/False)")
    
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"

        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}

        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        
        test_summary = response.json()
        
        # Validate that we got a meaningful test response
        # Check for essential fields that should be present in a valid test
        if not test_summary or not isinstance(test_summary, dict):
            raise ValueError(f"Invalid test response for test_id '{test_id}': response is empty or not a dictionary")
        
        # Check for key identifiers that indicate this is a real test
        # Only check for planRunId as the essential field - planName may be optional
        if 'planRunId' not in test_summary:
            raise ValueError(f"Invalid test_id '{test_id}': test does not exist or response is missing essential identifier (planRunId)")
        
        return_details = get_reduced_test_summary_mapping(test_summary)
               
        if include_simulations_statistics:
            return_details['simulations_statistics'] = _get_simulation_statistics(test_id, test_summary, console)

        return return_details
        
    except Exception as e:
        logger.error("Error getting test details for test '%s' from console '%s': %s", test_id, console, str(e))
        raise


def _get_simulation_statistics(test_id: str, test_summary: Dict[str, Any], console: str = "default") -> List[Dict[str, Any]]:
    """
    Get simulation statistics for a test.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID
        test_summary: Test summary information

    Returns:
        Dict containing simulation statistics
    """
    try:
        # To coung drifts - get all simulations for the test
        all_simulations = _get_all_simulations_from_cache_or_api(test_id, console)
        drifts = 0
        for sim in all_simulations:
            is_drift = sim.get('is_drifted', False)
            if is_drift:
                if isinstance(is_drift, str):
                    # this is for debugging purposes, this should never happen
                    logging.error("Simulation %s has unexpected drift type: %s", sim.get('id', 'unknown'), is_drift)
                    continue

                drifts += 1

        # Get finalStatus safely, default to empty dict if not present
        final_status = test_summary.get('finalStatus', {})
        stats = [{
                    "status": "missed",
                    "explanation": (
                        "Simulations that were not stopped and were also not detected by any deployed security control "
                        "(No logs, no blocking, no alerting)"
                    ),
                    "count": final_status.get('missed', 0)
                },
                {
                    "status": "stopped",
                    "explanation": (
                        "Simulations where the attack was not successful but not logged nor detected by a security control"
                    ),
                    "count": final_status.get('stopped', 0)
                },
                {
                    "status": "prevented",
                    "explanation": (
                        "Simulations where the attack was evidently prevented as well as reportedby a security control"
                    ),
                    "count": final_status.get('prevented', 0)
                },
                {
                    "status": "reported",
                    "explanation": (
                        "Simulations where the attack was not stopped but detected and reported by a security control"
                    ),
                    "count": final_status.get('reported', 0)
                },
                {
                    "status": "logged",
                    "explanation": (
                        "Simulations where the attack was not stopped yet logged by a security control"
                    ),
                    "count": final_status.get('logged', 0)
                },
                {
                    "status": "no-result",
                    "explanation": (
                        "Simulations that could not be completed due to technical issues"
                    ),
                    "count": final_status.get('no-result', 0)
                },
                {
                    "explanation": (
                        "Simulations that completed with different results compared to previous executions with exact same parameters"
                    ),
                    "drifted_count": drifts
                }
            ]
        
        return stats
        
    except Exception as e:  # pylint: disable=broad-exception-caught  # Graceful error handling for statistics
        logger.error("Error getting simulation statistics for test '%s': %s", test_id, str(e))
        return [{"error": f"Failed to get simulation statistics: {str(e)}"}]


def sb_get_test_simulations(
    test_id: str,
    console: str = "default",
    page_number: int = 0,
    status_filter: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    playbook_attack_id_filter: Optional[str] = None,
    playbook_attack_name_filter: Optional[str] = None,
    drifted_only: bool = False
) -> Dict[str, Any]:
    """
    Get filtered and paginated simulations for a test.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID
        page_number: Page number (0-based)
        status_filter: Filter by simulation status
        start_time: Start time filter (Unix timestamp)
        end_time: End time filter (Unix timestamp)
        playbook_attack_id_filter: Filter by playbook attack ID
        playbook_attack_name_filter: Filter by playbook attack name
        drifted_only: Filter to include only drifted simulations
        
    Returns:
        Dict containing filtered simulations, pagination info, and applied filters
    """
    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    # Validate time range - start_time should be before end_time
    if start_time is not None and end_time is not None and start_time > end_time:
        raise ValueError(f"Invalid time range: start_time ({start_time}) must be before or equal to end_time ({end_time})")
    
    # Validate boolean parameter - handle None gracefully
    if drifted_only is None:
        drifted_only = False
    elif not isinstance(drifted_only, bool):
        raise ValueError(f"Invalid drifted_only parameter '{drifted_only}'. Must be a boolean value (True/False)")
    
    try:
        # Get all simulations from cache or API
        all_simulations = _get_all_simulations_from_cache_or_api(test_id, console)
        
        # Apply filters
        filtered_simulations = _apply_simulation_filters(
            all_simulations,
            status_filter=status_filter,
            start_time=start_time,
            end_time=end_time,
            playbook_attack_id_filter=playbook_attack_id_filter,
            playbook_attack_name_filter=playbook_attack_name_filter,
            drifted_only=drifted_only
        )
        
        # Apply pagination
        start_index = page_number * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        page_simulations = filtered_simulations[start_index:end_index]
        
        # Calculate pagination info
        total_simulations = len(filtered_simulations)
        total_pages = (total_simulations + PAGE_SIZE - 1) // PAGE_SIZE
        
        # Track applied filters
        applied_filters = {}
        if status_filter:
            applied_filters['status_filter'] = status_filter
        if start_time:
            applied_filters['start_time'] = start_time
        if end_time:
            applied_filters['end_time'] = end_time
        if playbook_attack_id_filter:
            applied_filters['playbook_attack_id_filter'] = playbook_attack_id_filter
        if playbook_attack_name_filter:
            applied_filters['playbook_attack_name_filter'] = playbook_attack_name_filter
        if drifted_only:
            applied_filters['drifted_only'] = drifted_only
        
        return {
            "page_number": page_number,
            "total_pages": total_pages,
            "total_simulations": total_simulations,
            "simulations_in_page": page_simulations,
            "applied_filters": applied_filters,
            "hint_to_agent": f"You can scan next page by specifying page_number={page_number + 1}" if page_number + 1 < total_pages else None
        }
        
    except Exception as e:
        logger.error("Error getting simulations for test '%s' from console '%s': %s", test_id, console, str(e))
        raise


def _get_all_simulations_from_cache_or_api(test_id: str, console: str = "default") -> List[Dict[str, Any]]:
    """
    Get all simulations from cache or API.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID
        
    Returns:
        List of simulation dictionaries
    """
    cache_key = f"simulations_{console}_{test_id}"
    current_time = time.time()
    
    # Check cache first
    if cache_key in simulations_cache:
        data, timestamp = simulations_cache[cache_key]
        if current_time - timestamp < CACHE_TTL:
            logger.info("Retrieved %d simulations from cache for test '%s'", len(data), test_id)
            return data
    
    # Cache miss or expired - proceed to fetch from API with proper pagination
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)
        
        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"
        
        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}
        
        # Fetch all pages of simulations
        all_simulations_results = []
        page = 1
        page_size = 100
        
        logger.info("Fetching simulations from API for test '%s' from console '%s'", test_id, console)
        
        while True:
            data = {
                "runId": f"{test_id}",
                "query": f"!labels:Ignore AND (!labels:Draft) AND (runId:{test_id})",
                "page": page,
                "pageSize": page_size,
                "orderBy": "desc",
                "sortBy": "executionTime"
            }
            
            logger.info("Fetching page %d for test '%s' from console '%s'", page, test_id, console)
            response = requests.post(api_url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            
            try:
                response_data = response.json()
                page_simulations = response_data.get("simulations", [])
            except ValueError as e:
                logger.error("Failed to parse simulations response for test %s in console %s on page %d: %s", test_id, console, page, str(e))
                break
            
            # If no simulations returned, we've reached the end
            if not page_simulations:
                logger.info("No more simulations found on page %d for test '%s'", page, test_id)
                break
            
            # Add simulations from this page
            all_simulations_results.extend(page_simulations)
            logger.info("Added %d simulations from page %d for test '%s'", len(page_simulations), page, test_id)
            
            # If we got fewer simulations than page_size, we've reached the end
            if len(page_simulations) < page_size:
                logger.info("Reached last page %d for test '%s' (got %d < %d simulations)", page, test_id, len(page_simulations), page_size)
                break
            
            # Move to next page
            page += 1
        
        # Transform simulations using existing mapping - same pattern as original
        simulations = []
        for simulation_result in all_simulations_results:
            logger.info("Adding simulation %s to the return list", simulation_result['id'])
            simulations.append(get_reduced_simulation_result_entity(simulation_result))
        
        # Cache the result
        simulations_cache[cache_key] = (simulations, current_time)
        
        logger.info("Retrieved %d simulations total from %d pages for test '%s'", len(simulations), page - 1, test_id)
        return simulations
        
    except Exception as e:
        logger.error("Error fetching simulations from API for test '%s': %s", test_id, str(e))
        raise


def _apply_simulation_filters(
    simulations: List[Dict[str, Any]],
    status_filter: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    playbook_attack_id_filter: Optional[str] = None,
    playbook_attack_name_filter: Optional[str] = None,
    drifted_only: bool = False
) -> List[Dict[str, Any]]:
    """
    Apply filters to simulation list.
    
    Args:
        simulations: List of simulation dictionaries
        status_filter: Status filter
        start_time: Start time filter
        end_time: End time filter
        playbook_attack_id_filter: Playbook attack ID filter
        playbook_attack_name_filter: Playbook attack name filter
        drifted_only: Filter to include only drifted simulations
        
    Returns:
        Filtered list of simulations
    """
    filtered = simulations
    
    # Apply status filter
    if status_filter:
        filtered = [s for s in filtered 
                   if s.get('status', '').lower() == status_filter.lower()]
    
    # Apply time filters with safe type conversion
    if start_time:
        filtered = [s for s in filtered 
                   if _safe_time_compare(s, start_time, lambda x, y: x >= y)]
    if end_time:
        filtered = [s for s in filtered 
                   if _safe_time_compare(s, end_time, lambda x, y: x <= y)]
    
    # Apply playbook attack ID filter
    if playbook_attack_id_filter:
        filtered = [s for s in filtered 
                   if s.get('playbookAttackId') == playbook_attack_id_filter]
    
    # Apply playbook attack name filter
    if playbook_attack_name_filter:
        filtered = [s for s in filtered 
                   if playbook_attack_name_filter.lower() in s.get('playbookAttackName', '').lower()]
    
    # Apply drift filter
    if drifted_only:
        filtered = [s for s in filtered 
                   if s.get('is_drifted', False) is True]
    
    return filtered


def _safe_time_compare(simulation: Dict[str, Any], compare_time: int, operator) -> bool:
    """
    Safely compare simulation time with safe type conversion.
    
    Args:
        simulation: Simulation dictionary
        compare_time: Time to compare against
        operator: Comparison operator function
        
    Returns:
        Boolean comparison result
    """
    end_time_val = simulation.get('end_time', 0)
    if isinstance(end_time_val, str):
        try:
            end_time_val = int(end_time_val)
        except (ValueError, TypeError):
            end_time_val = 0
    return operator(end_time_val, compare_time)


def sb_get_simulation_details(
    simulation_id: str,
    console: str = "default",
    include_mitre_techniques: bool = False,
    include_basic_attack_logs: bool = False,
    include_drift_info: bool = False
) -> Dict[str, Any]:
    """
    Get detailed information for a specific simulation.
    
    Args:
        console: SafeBreach console name
        simulation_id: Simulation ID
        include_mitre_techniques: Include MITRE ATT&CK techniques
        include_basic_attack_logs: Include basic attack logs from simulation events
        include_drift_info: Include drift analysis information
        
    Returns:
        Dict containing simulation details
    """
    try:
        logger.info("Getting api key for console %s", console)
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"
        
        headers = {"Content-Type": "application/json",
                    "x-apitoken": apitoken}
        
        data = {
            "runId": "*",
            "query": f"id:{simulation_id}",
            "page": 1,
            "pageSize": 100,
            "orderBy": "desc",
            "sortBy": "executionTime"
        }
        
        logger.info("Fetching simulation '%s' from console '%s'", simulation_id, console)
        response = requests.post(api_url, headers=headers, json=data, timeout=120)
        if response.status_code != 200:
            logger.error("Failed to fetch simulation details for simulation ID %s: %s", simulation_id, response.text)
            return {"error": "Failed to fetch simulation details", "status_code": response.status_code}
        
        simulation_result = response.json()
        return_details = get_full_simulation_result_entity(
            simulation_result['simulations'][0],
            include_mitre_techniques=include_mitre_techniques,
            include_basic_attack_logs=include_basic_attack_logs,
            include_drift_info=include_drift_info
        )
        
        if include_drift_info and return_details.get('is_drifted', False):
            # Get the previous run ID of the most recent simulation with the same parameters such attack_playbook_id, simulators etc
            drift_code = return_details['drift_info']['drift_tracking_code']
            data = {
                "runId": "*",
                "query": f'originalExecutionId:("{drift_code}") AND !id:{simulation_id}',
                "page": 1,
                "pageSize": 200,
                "orderBy": "desc",
                "sortBy": "executionTime"
            }
            logger.info("Searching for simulations with drift_tracking_code = '%s' from console = '%s'", drift_code, console)
            response = requests.post(api_url, headers=headers, json=data, timeout=120)
            if response.status_code != 200:
                logger.error("Failed to fetch previous simulations with drift_tracking_code = %s: %s", drift_code, response.text)
                return_details['drift_info']['previous_simulation_id'] = "Failed to fetch previous simulations with same drift_tracking_code"
            else:
                previous_simulations = response.json().get('simulations', [])
                if previous_simulations:
                    for sim in previous_simulations:
                        if sim['executionTime'] < return_details['end_time']:
                            # We found the most recent previous simulation with the same drift_tracking_code
                            logger.info("Found previous simulation with ID %s for drift_tracking_code %s", sim.get('id', 'Unknown'), drift_code)
                            return_details['drift_info']['previous_simulation_id'] = sim.get('id', 'Unknown')
                            return_details['drift_info']['previous_test_id'] = sim.get('planRunId', 'Unknown')
                            break
                else:
                    return_details['drift_info']['previous_simulation_id'] = "No previous simulation found with same drift_tracking_code"

        return return_details
        
    except Exception as e:
        logger.error("Error getting simulation details for ID '%s': %s", simulation_id, str(e))
        raise


def _get_all_security_control_events_from_cache_or_api(test_id: str, simulation_id: str, console: str = "default") -> List[Dict[str, Any]]:
    """
    Get all security control events from cache or API.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)
        simulation_id: Simulation ID
        
    Returns:
        List of security control events
    """
    cache_key = f"{console}:{test_id}:{simulation_id}"
    current_time = time.time()
    
    # Check cache first
    if cache_key in security_control_events_cache:
        cache_entry = security_control_events_cache[cache_key]
        if current_time - cache_entry['timestamp'] < CACHE_TTL:
            logger.info("Using cached security control events for %s:%s:%s", console, test_id, simulation_id)
            return cache_entry['data']
    
    # Fetch from API
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'siem')
        account_id = get_api_account_id(console)
        
        # Use the SIEM API endpoint for security control events
        api_url = f"{base_url}/api/siem/v1/accounts/{account_id}/eventLogs?planRunId={test_id}&simulationId={simulation_id}"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}
        
        logger.info("Fetching security control events from API for %s:%s:%s", console, test_id, simulation_id)
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        
        response_data = response.json()
        
        # Extract siemLogs from the response
        security_events = []
        if 'result' in response_data and 'siemLogs' in response_data['result']:
            security_events = response_data['result']['siemLogs']
        
        # Cache the result
        security_control_events_cache[cache_key] = {
            'data': security_events,
            'timestamp': current_time
        }
        
        logger.info("Cached %d security control events for %s:%s:%s", len(security_events), console, test_id, simulation_id)
        return security_events
        
    except Exception as e:
        logger.error("Error fetching security control events from API for %s:%s:%s: %s", console, test_id, simulation_id, str(e))
        raise


def _apply_security_control_events_filters(
    events: List[Dict[str, Any]],
    product_name_filter: Optional[str] = None,
    vendor_name_filter: Optional[str] = None,
    security_action_filter: Optional[str] = None,
    connector_name_filter: Optional[str] = None,
    source_host_filter: Optional[str] = None,
    destination_host_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Apply filters to security control events.
    
    Args:
        events: List of security control events
        product_name_filter: Filter by product name (partial match)
        vendor_name_filter: Filter by vendor name (partial match)
        security_action_filter: Filter by security action (partial match)
        connector_name_filter: Filter by connector name (partial match)
        source_host_filter: Filter by source host (partial match)
        destination_host_filter: Filter by destination host (partial match)
        
    Returns:
        List of filtered events
    """
    filtered_events = events
    
    # Apply product name filter
    if product_name_filter:
        filtered_events = [
            event for event in filtered_events
            if product_name_filter.lower() in event.get('fields', {}).get('product', '').lower()
        ]
    
    # Apply vendor name filter
    if vendor_name_filter:
        filtered_events = [
            event for event in filtered_events
            if vendor_name_filter.lower() in event.get('fields', {}).get('vendor', '').lower()
        ]
    
    # Apply security action filter
    if security_action_filter:
        filtered_events = [
            event for event in filtered_events
            if any(security_action_filter.lower() in str(action).lower() 
                   for action in (event.get('fields', {}).get('action', []) if isinstance(event.get('fields', {}).get('action'), list) 
                                 else [event.get('fields', {}).get('action', '')]))
        ]
    
    # Apply connector name filter
    if connector_name_filter:
        filtered_events = [
            event for event in filtered_events
            if connector_name_filter.lower() in event.get('connectorName', '').lower()
        ]
    
    # Apply source host filter
    if source_host_filter:
        filtered_events = [
            event for event in filtered_events
            if any(source_host_filter.lower() in str(host).lower() 
                   for host in event.get('fields', {}).get('sourceHosts', []))
        ]
    
    # Apply destination host filter
    if destination_host_filter:
        filtered_events = [
            event for event in filtered_events
            if any(destination_host_filter.lower() in str(host).lower() 
                   for host in event.get('fields', {}).get('destHosts', []))
        ]
    
    return filtered_events


def sb_get_security_controls_events(
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
) -> Dict[str, Any]:
    """
    Get filtered and paginated security control events for a specific test and simulation.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)
        simulation_id: Simulation ID
        page_number: Page number (0-based)
        product_name_filter: Filter by security control product name (partial match)
        vendor_name_filter: Filter by vendor name (partial match)
        security_action_filter: Filter by security action (partial match)
        connector_name_filter: Filter by SafeBreach integration name (partial match)
        source_host_filter: Filter by source host (partial match)
        destination_host_filter: Filter by destination host (partial match)
        
    Returns:
        Dict containing filtered events, pagination info, and applied filters
    """
    # Validate required parameters
    if not test_id or not test_id.strip():
        raise ValueError("test_id parameter is required and cannot be empty")
    if not simulation_id or not simulation_id.strip():
        raise ValueError("simulation_id parameter is required and cannot be empty")
    
    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    try:
        # Get all security control events from cache or API
        all_events = _get_all_security_control_events_from_cache_or_api(test_id, simulation_id, console)
        
        # Apply filters
        filtered_events = _apply_security_control_events_filters(
            all_events,
            product_name_filter=product_name_filter,
            vendor_name_filter=vendor_name_filter,
            security_action_filter=security_action_filter,
            connector_name_filter=connector_name_filter,
            source_host_filter=source_host_filter,
            destination_host_filter=destination_host_filter
        )
        
        # Apply pagination
        start_index = page_number * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        page_events = filtered_events[start_index:end_index]
        
        # Transform events to reduced format
        reduced_events = []
        for event in page_events:
            reduced_event = get_reduced_security_control_events_mapping(event)
            reduced_events.append(reduced_event)
        
        # Calculate pagination info
        total_events = len(filtered_events)
        total_pages = (total_events + PAGE_SIZE - 1) // PAGE_SIZE
        
        # Track applied filters
        applied_filters = {}
        if product_name_filter:
            applied_filters['product_name_filter'] = product_name_filter
        if vendor_name_filter:
            applied_filters['vendor_name_filter'] = vendor_name_filter
        if security_action_filter:
            applied_filters['security_action_filter'] = security_action_filter
        if connector_name_filter:
            applied_filters['connector_name_filter'] = connector_name_filter
        if source_host_filter:
            applied_filters['source_host_filter'] = source_host_filter
        if destination_host_filter:
            applied_filters['destination_host_filter'] = destination_host_filter
        
        return {
            "page_number": page_number,
            "total_pages": total_pages,
            "total_events": total_events,
            "events_in_page": reduced_events,
            "applied_filters": applied_filters,
            "hint_to_agent": f"Retrieved {len(reduced_events)} security control events for test {test_id} and simulation {simulation_id}. " +
                           (f"You can scan next page by calling with page_number={page_number + 1}" if page_number + 1 < total_pages else "This is the last page.")
        }
        
    except Exception as e:
        logger.error("Error getting security control events for %s:%s:%s: %s", console, test_id, simulation_id, str(e))
        raise


def sb_get_security_control_event_details(
    test_id: str,
    simulation_id: str,
    event_id: str,
    console: str = "default",
    verbosity_level: str = "standard"
) -> Dict[str, Any]:
    """
    Get detailed information for a specific security control event.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)
        simulation_id: Simulation ID
        event_id: Security control event ID
        verbosity_level: Level of detail ("minimal", "standard", "detailed", "full")
        
    Returns:
        Dict containing detailed security control event information
    """
    # Validate required parameters first
    if not console or not console.strip():
        raise ValueError("Invalid console parameter '{}'. Console name is required and cannot be empty".format(console))
    
    if not test_id or not test_id.strip():
        raise ValueError("Invalid test_id parameter '{}'. Test ID is required and cannot be empty".format(test_id))
    
    if not simulation_id or not simulation_id.strip():
        raise ValueError("Invalid simulation_id parameter '{}'. Simulation ID is required and cannot be empty".format(simulation_id))
    
    if not event_id or not event_id.strip():
        raise ValueError("Invalid event_id parameter '{}'. Event ID is required and cannot be empty".format(event_id))
    
    # Validate verbosity_level parameter
    if verbosity_level is None:
        verbosity_level = "standard"  # Default to standard if None is passed
    
    valid_verbosity_levels = ['minimal', 'standard', 'detailed', 'full']
    if verbosity_level not in valid_verbosity_levels:
        raise ValueError(f"Invalid verbosity_level parameter '{verbosity_level}'. Valid values are: {', '.join(valid_verbosity_levels)}")
    
    try:
        # Get all security control events from cache or API
        all_events = _get_all_security_control_events_from_cache_or_api(test_id, simulation_id, console)
        
        # Find the specific event
        target_event = None
        for event in all_events:
            if event.get('id') == event_id:
                target_event = event
                break
        
        if not target_event:
            return {
                "error": f"Security control event with ID '{event_id}' not found",
                "console": console,
                "test_id": test_id,
                "simulation_id": simulation_id,
                "event_id": event_id
            }
        
        # Transform event based on verbosity level
        detailed_event = get_full_security_control_events_mapping(target_event, verbosity_level)
        
        # Add metadata
        detailed_event['_metadata'] = {
            'console': console,
            'test_id': test_id,
            'simulation_id': simulation_id,
            'event_id': event_id,
            'verbosity_level': verbosity_level,
            'retrieved_at': time.time()
        }
        
        return detailed_event
        
    except Exception as e:
        logger.error("Error getting security control event details for %s:%s:%s:%s: %s", console, test_id, simulation_id, event_id, str(e))
        raise


# Global cache for findings
findings_cache = {}


def _get_all_findings_from_cache_or_api(test_id: str, console: str = "default") -> List[Dict[str, Any]]:
    """
    Get all findings from cache or SafeBreach API.
    
    Findings are retrieved using the propagateSummary API endpoint which returns
    ALL findings for the test across all simulations.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)
        
    Returns:
        List of findings data for the entire test
    """
    cache_key = f"{console}:{test_id}"
    current_time = time.time()
    
    # Check if we have valid cached data
    if (cache_key in findings_cache and
        current_time - findings_cache[cache_key]['timestamp'] < CACHE_TTL):
        logger.info("Using cached findings data for %s", cache_key)
        return findings_cache[cache_key]['data']
    
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        
        # Use the propagateSummary API endpoint for findings
        api_url = f"{base_url}/api/data/v1/propagateSummary/{test_id}/findings/"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}
        
        logger.info("Fetching findings from API for %s:%s", console, test_id)
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        findings_data = data.get('findings', [])
        
        # Cache the data
        findings_cache[cache_key] = {
            'data': findings_data,
            'timestamp': current_time
        }
        
        logger.info("Cached %d findings for %s", len(findings_data), cache_key)
        return findings_data
        
    except Exception as e:
        logger.error("Error fetching findings data for %s:%s: %s", console, test_id, str(e))
        raise


def _apply_findings_filters(
    findings: List[Dict[str, Any]],
    attribute_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Apply filters to findings list.
    
    Args:
        findings: List of findings to filter
        attribute_filter: Filter by any attribute (partial match, case-insensitive)
        
    Returns:
        Filtered list of findings
    """
    filtered_findings = findings
    
    # Apply attribute filter - search across all attributes
    if attribute_filter:
        filter_lower = attribute_filter.lower()
        filtered_findings = []
        
        for finding in findings:
            # Search in direct attributes
            match_found = False
            
            # Check top-level fields
            for key, value in finding.items():
                if key == 'attributes':  # Skip nested attributes for now
                    continue
                if str(value).lower().find(filter_lower) != -1:
                    match_found = True
                    break
            
            # Check nested attributes
            if not match_found and 'attributes' in finding:
                attributes = finding['attributes']
                if isinstance(attributes, dict):
                    for key, value in attributes.items():
                        # Handle different value types
                        if isinstance(value, list):
                            # Search in list items (e.g., ports)
                            for item in value:
                                if str(item).lower().find(filter_lower) != -1:
                                    match_found = True
                                    break
                        else:
                            # Search in simple values
                            if str(value).lower().find(filter_lower) != -1:
                                match_found = True
                                break
                        
                        if match_found:
                            break
            
            if match_found:
                filtered_findings.append(finding)
    
    return filtered_findings


def sb_get_test_findings_counts(
    test_id: str,
    console: str = "default",
    attribute_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get counts of findings by type for a specific test, with optional filtering.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)
        attribute_filter: Filter by any attribute (partial match, case-insensitive)
        
    Returns:
        Dict containing finding counts by type and metadata
    """
    try:
        # Get all findings from cache or API
        all_findings = _get_all_findings_from_cache_or_api(test_id, console)
        
        # Apply filters
        filtered_findings = _apply_findings_filters(
            all_findings,
            attribute_filter=attribute_filter
        )
        
        # Count findings by type
        type_counts = {}
        for finding in filtered_findings:
            finding_type = finding.get('type', 'Unknown')
            type_counts[finding_type] = type_counts.get(finding_type, 0) + 1
        
        # Sort by count (descending) then by type name
        sorted_counts = sorted(
            [{'type': t, 'count': c} for t, c in type_counts.items()],
            key=lambda x: (-x['count'], x['type'])
        )
        
        # Track applied filters
        applied_filters = {}
        if attribute_filter:
            applied_filters['attribute_filter'] = attribute_filter
        
        result = {
            'console': console,
            'test_id': test_id,
            'total_findings': len(filtered_findings),
            'total_types': len(type_counts),
            'findings_counts': sorted_counts,
            'applied_filters': applied_filters,
            'retrieved_at': time.time()
        }
        
        logger.info("Retrieved %d findings of %d types for %s:%s", len(filtered_findings), len(type_counts), console, test_id)
        return result
        
    except Exception as e:
        logger.error("Error getting test findings counts for %s:%s: %s", console, test_id, str(e))
        raise


def sb_get_test_findings_details(
    test_id: str,
    console: str = "default",
    page_number: int = 0,
    attribute_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get detailed findings for a specific test with filtering and pagination.
    
    Args:
        console: SafeBreach console name
        test_id: Test ID (planRunId)  
        page_number: Page number (0-based)
        attribute_filter: Filter by any attribute (partial match, case-insensitive)
        
    Returns:
        Dict containing filtered findings, pagination info, and applied filters
    """
    # Validate page_number parameter
    if page_number < 0:
        raise ValueError(f"Invalid page_number parameter '{page_number}'. Page number must be non-negative (0 or greater)")
    
    try:
        # Get all findings from cache or API
        all_findings = _get_all_findings_from_cache_or_api(test_id, console)
        
        # Apply filters
        filtered_findings = _apply_findings_filters(
            all_findings,
            attribute_filter=attribute_filter
        )
        
        # Sort by timestamp (most recent first) for consistent ordering
        # Handle None/invalid timestamps by treating them as empty strings (which sort last)
        def safe_timestamp_key(finding):
            timestamp = finding.get('timestamp')
            return timestamp if timestamp is not None else ''
        
        sorted_findings = sorted(
            filtered_findings,
            key=safe_timestamp_key,
            reverse=True
        )
        
        # Calculate pagination info
        total_findings = len(sorted_findings)
        total_pages = (total_findings + PAGE_SIZE - 1) // PAGE_SIZE
        
        # Validate page overflow
        if total_pages > 0 and page_number >= total_pages:
            raise ValueError(f"Invalid page_number parameter '{page_number}'. Available pages range from 0 to {total_pages - 1} (total {total_pages} pages)")
        
        # Apply pagination
        start_index = page_number * PAGE_SIZE
        end_index = start_index + PAGE_SIZE
        page_findings = sorted_findings[start_index:end_index]
        
        # Track applied filters
        applied_filters = {}
        if attribute_filter:
            applied_filters['attribute_filter'] = attribute_filter
        
        result = {
            'console': console,
            'test_id': test_id,
            'page_number': page_number,
            'total_pages': total_pages,
            'total_findings': total_findings,
            'findings_in_page': page_findings,
            'applied_filters': applied_filters,
            'retrieved_at': time.time()
        }
        
        # Add hint for pagination
        if page_number + 1 < total_pages:
            result['hint_to_agent'] = f"You can scan next page by calling with page_number={page_number + 1}. There are {total_pages} total pages."
        
        logger.info("Retrieved page %d of %d (%d findings) for %s:%s", page_number, total_pages, len(page_findings), console, test_id)
        return result
        
    except Exception as e:
        logger.error("Error getting test findings details for %s:%s: %s", console, test_id, str(e))
        raise


def sb_get_test_drifts(test_id: str, console: str = "default") -> Dict[str, Any]:
    """
    Analyze drift between the given test and the most recent previous test with the same name.
    
    This function compares simulations between two test runs to identify:
    1. Simulations that exist only in the first test (baseline)
    2. Simulations that exist only in the second test (current)
    3. Simulations that exist in both tests but have different status values (drifted)
    
    Args:
        console: SafeBreach console name
        test_id: Test ID to analyze for drifts
        
    Returns:
        Dict containing drift analysis results with the following structure:
        {
            "total_drifts": int,  # Total number of drifts found
            "baseline_test_id": ["sim_id1", ...],  # Simulations exclusive to baseline test
            "current_test_id": ["sim_id2", ...],   # Simulations exclusive to current test
            "drifts": [  # Simulations with matching drift_tracking_code but different status
                {
                    "drift_tracking_code": str,
                    "drift_from": {"simulation_id": str, "status": str},
                    "drift_to": {"simulation_id": str, "status": str},
                    "drift_type": str,  # Key from drift_types_mapping
                    "security_impact": str,  # "positive", "negative", or "neutral"
                    "description": str
                }
            ]
        }
    """
    # Validate required parameters
    if not test_id or not test_id.strip():
        raise ValueError("test_id parameter is required and cannot be empty")
    
    try:
        # Step 1: Get details of the current test to find its name and start_time
        logger.info("Getting test details for test '%s' on console '%s'", test_id, console)
        current_test = sb_get_test_details(test_id, console)
        
        if not current_test or 'name' not in current_test:
            return {
                "error": f"Could not retrieve test details for test_id '{test_id}' or test lacks a name attribute",
                "console": console,
                "test_id": test_id
            }
        
        test_name = current_test['name']
        current_start_time = current_test.get('start_time')
        
        if not current_start_time:
            return {
                "error": f"Test '{test_id}' does not have a start_time attribute",
                "console": console,
                "test_id": test_id,
                "test_name": test_name
            }
        
        # Step 2: Find the most recent previous test with the same name
        logger.info("Searching for baseline test with name '%s' before start_time %s", test_name, current_start_time)
        baseline_tests = sb_get_tests_history(
            console=console,
            page_number=0,
            name_filter=test_name,
            end_date=current_start_time,  # include tests that ended exactly at the current start_time
            order_by="end_time",
            order_direction="desc"
        )
        
        baseline_entry = baseline_tests.get('tests_in_page', [])
        if baseline_entry:
            baseline_candidate = baseline_entry[0]
        else:
            baseline_candidate = _find_previous_test_by_name(
                test_name=test_name,
                before_start_time=current_start_time,
                console=console
            )

        if not baseline_candidate:
            return {
                "error": f"No previous test found with name '{test_name}' before the current test execution",
                "console": console,
                "test_id": test_id,
                "test_name": test_name,
                "current_start_time": current_start_time
            }
        
        baseline_test_id = baseline_candidate['test_id']
        logger.info("Found baseline test: '%s'", baseline_test_id)
        
        # Step 3: Get all simulations for both tests
        logger.info("Fetching all simulations for baseline test '%s'", baseline_test_id)
        baseline_simulations = _get_all_simulations_from_cache_or_api(baseline_test_id, console)
        
        logger.info("Fetching all simulations for current test '%s'", test_id)
        current_simulations = _get_all_simulations_from_cache_or_api(test_id, console)
        
        # Step 4: Group simulations by drift_tracking_code
        baseline_by_drift_code = {}
        for sim in baseline_simulations:
            drift_code = sim.get('drift_tracking_code')
            if drift_code:
                baseline_by_drift_code[drift_code] = sim
        
        current_by_drift_code = {}
        for sim in current_simulations:
            drift_code = sim.get('drift_tracking_code')
            if drift_code:
                current_by_drift_code[drift_code] = sim
        
        # Step 5: Analyze drift patterns
        baseline_only_codes = set(baseline_by_drift_code.keys()) - set(current_by_drift_code.keys())
        current_only_codes = set(current_by_drift_code.keys()) - set(baseline_by_drift_code.keys())
        shared_codes = set(baseline_by_drift_code.keys()) & set(current_by_drift_code.keys())
        
        # Simulations exclusive to baseline test
        baseline_only_sims = [baseline_by_drift_code[code]['simulation_id'] for code in baseline_only_codes]
        
        # Simulations exclusive to current test
        current_only_sims = [current_by_drift_code[code]['simulation_id'] for code in current_only_codes]
        
        # Analyze shared simulations for status drifts
        drifts_by_types = {}
        for drift_code in shared_codes:
            baseline_sim = baseline_by_drift_code[drift_code]
            current_sim = current_by_drift_code[drift_code]
            baseline_status = baseline_sim['status'].replace("-", "_").lower()
            current_status = current_sim['status'].replace("-", "_").lower()
            
            if baseline_status != current_status:
                # Found a drift - look up drift type
                drift_key = f"{baseline_status}-{current_status}"
                drift_info = drift_types_mapping.get(drift_key, {
                    "type_of_drift": f"from_{baseline_status}_to_{current_status}",
                    "security_impact": "unknown", 
                    "description": f"Status changed from {baseline_status} to {current_status}",
                    "hint_to_llm": "Review simulation logs and security control events for this drift pattern"
                })

                if drift_key not in drifts_by_types:
                    drifts_by_types[drift_key] = {
                        "drift_type": drift_key,
                        "security_impact": drift_info.get("security_impact", "unknown"),
                        "description": drift_info.get("description", f"Status changed from {baseline_status} to {current_status}"),
                        "drifted_simulations": []
                    }

                drifts_by_types[drift_key]["drifted_simulations"].append({
                    "drift_tracking_code": drift_code,
                    "former_simulation_id": baseline_sim['simulation_id'],
                    "current_simulation_id": current_sim['simulation_id'],
                })
        
        # Calculate total drifts
        status_drifts = 0
        for _, list_of_drifts in drifts_by_types.items():
            status_drifts += len(list_of_drifts["drifted_simulations"])

        total_drifts = len(baseline_only_sims) + len(current_only_sims) + status_drifts
        
        # Prepare result
        result = {
            "total_drifts": total_drifts,
            "drifts": drifts_by_types if drifts_by_types else {},
            "_metadata": {
                "console": console,
                "current_test_id": test_id,
                "baseline_test_id": baseline_test_id,
                "test_name": test_name,
                "baseline_simulations_count": len(baseline_simulations),
                "current_simulations_count": len(current_simulations),
                "shared_drift_codes": len(shared_codes),
                "simulations_exclusive_to_baseline": baseline_only_sims,
                "simulations_exclusive_to_current": current_only_sims,
                "status_drifts": status_drifts,
                "analyzed_at": time.time()
            }
        }
        
        logger.info("Drift analysis complete for test '%s': %d total drifts found", test_id, total_drifts)
        return result
        
    except Exception as e:
        logger.error("Error analyzing test drifts for %s:%s: %s", console, test_id, str(e))
        raise


# Global cache for full simulation logs
full_simulation_logs_cache = {}


def sb_get_full_simulation_logs(
    simulation_id: str,
    test_id: str,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Get comprehensive execution logs for a specific simulation including detailed traces.

    This function retrieves the full simulation logs response from the SafeBreach API,
    with primary focus on exposing the detailed LOGS field that contains ~40KB of
    timestamped simulator execution logs for troubleshooting and forensic analysis.

    Args:
        simulation_id (str): Simulation ID - required (e.g., "1477531")
        test_id (str): Test ID / planRunId - required (e.g., "1764165600525.2")
        console (str): SafeBreach console name - defaults to "default"

    Returns:
        Dict containing:
            - simulation_id: Simulation identifier
            - test_id: Test plan run ID
            - execution_times: Start, end, execution timestamps and durations
            - status: Execution status and final outcome
            - logs: Full simulator logs (~40KB detailed text)
            - simulation_steps: Structured array of execution steps
            - details_summary: High-level execution summary
            - metadata: Execution context and configuration
            - attack_info: Move name, description, protocol, approach
            - host_info: Attacker and target node information

    Raises:
        ValueError: If simulation_id or test_id are empty/invalid
        requests.HTTPError: If API request fails
        KeyError: If response structure is unexpected

    Example:
        >>> details = sb_get_full_simulation_logs(
        ...     simulation_id="1477531",
        ...     test_id="1764165600525.2",
        ...     console="demo"
        ... )
        >>> print(f"Logs size: {len(details['logs'])} bytes")
        >>> print(f"Steps count: {len(details['simulation_steps'])}")
    """
    # Validate required parameters
    if not simulation_id or not simulation_id.strip():
        raise ValueError("simulation_id parameter is required and cannot be empty")

    if not test_id or not test_id.strip():
        raise ValueError("test_id parameter is required and cannot be empty")

    try:
        # Get data from cache or API
        api_response = _get_full_simulation_logs_from_cache_or_api(simulation_id, test_id, console)

        # Transform using data types mapping
        from .data_types import get_full_simulation_logs_mapping
        result = get_full_simulation_logs_mapping(api_response)

        return result

    except Exception as e:
        logger.error(
            "Error getting full simulation logs for simulation '%s', test '%s' from console '%s': %s",
            simulation_id, test_id, console, str(e)
        )
        raise


def _get_full_simulation_logs_from_cache_or_api(
    simulation_id: str,
    test_id: str,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Get full simulation logs from cache or API.

    Args:
        simulation_id: Simulation ID
        test_id: Test ID / planRunId
        console: SafeBreach console name

    Returns:
        Raw API response dictionary
    """
    cache_key = f"full_simulation_logs_{console}_{simulation_id}_{test_id}"
    current_time = time.time()

    # Check cache first
    if cache_key in full_simulation_logs_cache:
        data, timestamp = full_simulation_logs_cache[cache_key]
        if current_time - timestamp < CACHE_TTL:
            logger.info("Retrieved full simulation logs from cache: %s", cache_key)
            return data

    # Cache miss or expired - fetch from API
    logger.info("Fetching full simulation logs from API for simulation '%s', test '%s' from console '%s'",
                simulation_id, test_id, console)
    data = _fetch_full_simulation_logs_from_api(simulation_id, test_id, console)

    # Cache the result
    full_simulation_logs_cache[cache_key] = (data, current_time)
    logger.info("Cached full simulation logs: %s", cache_key)

    return data


def _fetch_full_simulation_logs_from_api(
    simulation_id: str,
    test_id: str,
    console: str = "default"
) -> Dict[str, Any]:
    """
    Fetch full simulation logs from SafeBreach API.

    Args:
        simulation_id: Simulation ID
        test_id: Test ID / planRunId
        console: SafeBreach console name

    Returns:
        Raw API response dictionary

    Raises:
        requests.HTTPError: If API request fails
        ValueError: If response is invalid
    """
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)

        # Build API URL with simulation_id as path parameter and runId as query parameter
        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults/{simulation_id}?runId={test_id}"

        headers = {
            "Content-Type": "application/json",
            "x-apitoken": apitoken
        }

        logger.info("GET request to: %s", api_url)
        response = requests.get(api_url, headers=headers, timeout=120)

        # Handle HTTP errors
        if response.status_code == 404:
            raise ValueError(
                f"Full simulation logs not found for simulation_id='{simulation_id}', test_id='{test_id}'"
            )
        elif response.status_code == 401:
            raise ValueError(f"Authentication failed for console '{console}'")

        response.raise_for_status()

        # Parse JSON response
        try:
            api_response = response.json()
        except ValueError as e:
            logger.error("Failed to parse full simulation logs response: %s", str(e))
            raise ValueError(f"Invalid JSON response from API: {str(e)}")

        logger.info("Successfully retrieved full simulation logs for simulation '%s'", simulation_id)
        return api_response

    except requests.exceptions.Timeout:
        logger.error("Timeout fetching full simulation logs for simulation '%s'", simulation_id)
        raise
    except requests.exceptions.RequestException as e:
        logger.error("Request error fetching full simulation logs for simulation '%s': %s", simulation_id, str(e))
        raise
    except Exception as e:
        logger.error("Unexpected error fetching full simulation logs: %s", str(e))
        raise
