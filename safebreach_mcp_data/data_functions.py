"""
SafeBreach Data Functions

This module provides functions for SafeBreach data operations,
specifically for test and simulation data management.
"""

import copy
import logging
import time
from typing import Dict, List, Optional, Any, Iterable

import requests
from safebreach_mcp_core.cache_config import is_caching_enabled
from safebreach_mcp_core.safebreach_cache import SafeBreachCache
from safebreach_mcp_core.secret_utils import get_secret_for_console
from safebreach_mcp_core.environments_metadata import get_api_base_url, get_api_account_id
from safebreach_mcp_core.suggestions import get_suggestions_for_collection
from safebreach_mcp_core.datetime_utils import convert_epoch_to_datetime
from .data_types import (
    get_reduced_test_summary_mapping,
    get_reduced_simulation_result_entity,
    get_full_simulation_result_entity,
    get_reduced_security_control_events_mapping,
    get_full_security_control_events_mapping,
    group_and_enrich_drift_records,
    get_reduced_peer_benchmark_response,
)
from .drifts_metadata import drift_types_mapping

logger = logging.getLogger(__name__)

# Bounded caches with TTL (SafeBreachCache wraps cachetools.TTLCache)
tests_cache = SafeBreachCache(name="tests", maxsize=5, ttl=1800)
simulations_cache = SafeBreachCache(name="simulations", maxsize=3, ttl=600)
security_control_events_cache = SafeBreachCache(name="security_control_events", maxsize=3, ttl=600)
simulation_drifts_cache = SafeBreachCache(name="simulation_drifts", maxsize=3, ttl=600)
peer_benchmark_cache = SafeBreachCache(name="peer_benchmark", maxsize=3, ttl=600)

# Configuration constants
PAGE_SIZE = 10


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

    # Check cache first (only if caching is enabled)
    if use_cache and is_caching_enabled("data"):
        cached = tests_cache.get(cache_key)
        if cached is not None:
            logger.info("Retrieved %d tests from cache for console '%s'", len(cached), console)
            return cached
    
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

        # Cache the result so subsequent calls can reuse it (only if caching is enabled)
        if is_caching_enabled("data"):
            tests_cache.set(cache_key, tests)
        
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


def sb_get_test_details(test_id: str, console: str = "default",
                        include_drift_count: bool = False) -> Dict[str, Any]:
    """
    Returns the details of a specific test executed on a given SafeBreach management console.
    Always includes simulation status counts (free from the API).
    Optionally includes drift count (requires fetching simulations page-by-page).

    Uses the list endpoint (/testsummaries?size=1000) via cache, which returns richer data
    (including findingsCount and compromisedHosts for Propagate tests) compared to the
    single-test endpoint (/testsummaries/{test_id}) which omits those fields.
    Falls back to the single-test endpoint if the test is not found in the list.
    """
    # Validate required parameters
    if not test_id or not test_id.strip():
        raise ValueError("test_id parameter is required and cannot be empty")

    # Validate boolean parameter - handle None gracefully
    if include_drift_count is None:
        include_drift_count = False
    elif not isinstance(include_drift_count, bool):
        raise ValueError(f"Invalid include_drift_count parameter '{include_drift_count}'. Must be a boolean value (True/False)")

    try:
        # Try the list endpoint first (via cache) — it includes findingsCount/compromisedHosts
        return_details = _find_test_in_cached_list(test_id, console)

        if return_details is None:
            # Fallback: single-test endpoint (missing findingsCount/compromisedHosts)
            logger.info("Test '%s' not found in cached list, falling back to single-test endpoint", test_id)
            return_details = _fetch_single_test(test_id, console)

        if include_drift_count:
            drift_count = _count_drifted_simulations(test_id, console)
            return_details['simulations_statistics'].append({
                "explanation": (
                    "Simulations that completed with different results compared to "
                    "previous executions with exact same parameters"
                ),
                "drifted_count": drift_count
            })

        return return_details

    except Exception as e:
        logger.error("Error getting test details for test '%s' from console '%s': %s", test_id, console, str(e))
        raise


def _find_test_in_cached_list(test_id: str, console: str) -> Optional[Dict[str, Any]]:
    """
    Look up a test by ID from the cached test list (list endpoint).
    Returns the mapped test dict if found, None otherwise.
    The list endpoint includes fields like findingsCount/compromisedHosts
    that the single-test endpoint omits.
    """
    try:
        all_tests = _get_all_tests_from_cache_or_api(console)
        for test in all_tests:
            if test.get('test_id') == test_id:
                # Return a deep copy so callers can mutate without affecting the cache
                return copy.deepcopy(test)
    except Exception as e:
        logger.warning("Failed to search cached test list for '%s': %s", test_id, e)
    return None


def _fetch_single_test(test_id: str, console: str) -> Dict[str, Any]:
    """
    Fetch a single test from the /testsummaries/{test_id} endpoint.
    This endpoint omits findingsCount/compromisedHosts but works for any test ID.
    """
    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)

    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}"
    headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

    response = requests.get(api_url, headers=headers, timeout=120)
    response.raise_for_status()

    test_summary = response.json()

    if not test_summary or not isinstance(test_summary, dict):
        raise ValueError(f"Invalid test response for test_id '{test_id}': response is empty or not a dictionary")

    if 'planRunId' not in test_summary:
        raise ValueError(f"Invalid test_id '{test_id}': test does not exist or response is missing essential identifier (planRunId)")

    return get_reduced_test_summary_mapping(test_summary)


def _count_drifted_simulations(test_id: str, console: str = "default") -> int:
    """
    Count drifted simulations for a test using streaming page-by-page counting.
    Each page is counted and discarded — memory stays at O(page_size) regardless of total simulations.

    Args:
        test_id: Test ID
        console: SafeBreach console name

    Returns:
        Number of drifted simulations
    """
    try:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, 'data')
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

        drifts = 0
        page = 1
        page_size = 100

        while True:
            data = {
                "runId": f"{test_id}",
                "query": f"!labels:Ignore AND (!labels:Draft) AND (runId:{test_id})",
                "page": page,
                "pageSize": page_size,
                "orderBy": "desc",
                "sortBy": "executionTime"
            }

            response = requests.post(api_url, headers=headers, json=data, timeout=120)
            response.raise_for_status()

            try:
                response_data = response.json()
                page_simulations = response_data.get("simulations", [])
            except ValueError:
                break

            if not page_simulations:
                break

            # Count drifts in this page, then discard the page
            for sim in page_simulations:
                drift_type = sim.get('driftType')
                if drift_type and drift_type != 'no_drift':
                    drifts += 1

            if len(page_simulations) < page_size:
                break

            page += 1

        return drifts

    except Exception as e:  # pylint: disable=broad-exception-caught  # Graceful error handling for drift counting
        logger.error("Error counting drifted simulations for test '%s': %s", test_id, str(e))
        return 0


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

    # Check cache first (only if caching is enabled)
    if is_caching_enabled("data"):
        cached = simulations_cache.get(cache_key)
        if cached is not None:
            logger.info("Retrieved %d simulations from cache for test '%s'", len(cached), test_id)
            return cached
    
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

        # Cache the result (only if caching is enabled)
        if is_caching_enabled("data"):
            simulations_cache.set(cache_key, simulations)
        
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

    # Check cache first (only if caching is enabled)
    if is_caching_enabled("data"):
        cached = security_control_events_cache.get(cache_key)
        if cached is not None:
            logger.info("Using cached security control events for %s:%s:%s", console, test_id, simulation_id)
            return cached
    
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

        # Cache the result (only if caching is enabled)
        if is_caching_enabled("data"):
            security_control_events_cache.set(cache_key, security_events)
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


# Bounded cache for findings
findings_cache = SafeBreachCache(name="findings", maxsize=3, ttl=600)


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

    # Check if we have valid cached data (only if caching is enabled)
    if is_caching_enabled("data"):
        cached = findings_cache.get(cache_key)
        if cached is not None:
            logger.info("Using cached findings data for %s", cache_key)
            return cached
    
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

        # Cache the data (only if caching is enabled)
        if is_caching_enabled("data"):
            findings_cache.set(cache_key, findings_data)
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


# Bounded cache for full simulation logs
full_simulation_logs_cache = SafeBreachCache(name="full_simulation_logs", maxsize=2, ttl=300)


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
        # Get already-transformed data from cache or API
        result = _get_full_simulation_logs_from_cache_or_api(simulation_id, test_id, console)
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
    Get full simulation logs from cache or API (validate-then-cache pattern).

    Fetches raw data from API, transforms it via get_full_simulation_logs_mapping(),
    then caches the transformed result. This ensures only validated data is cached,
    matching the pattern used by all other data server cache functions.

    Args:
        simulation_id: Simulation ID
        test_id: Test ID / planRunId
        console: SafeBreach console name

    Returns:
        Transformed simulation logs dictionary (already mapped)
    """
    cache_key = f"full_simulation_logs_{console}_{simulation_id}_{test_id}"

    # Check cache first (only if caching is enabled)
    if is_caching_enabled("data"):
        cached = full_simulation_logs_cache.get(cache_key)
        if cached is not None:
            logger.info("Retrieved full simulation logs from cache: %s", cache_key)
            return cached

    # Cache miss or expired - fetch from API
    logger.info("Fetching full simulation logs from API for simulation '%s', test '%s' from console '%s'",
                simulation_id, test_id, console)
    raw_data = _fetch_full_simulation_logs_from_api(simulation_id, test_id, console)

    # Transform BEFORE caching (validate-then-cache pattern)
    from .data_types import get_full_simulation_logs_mapping
    transformed = get_full_simulation_logs_mapping(raw_data)

    # Cache the transformed result (only if caching is enabled)
    if is_caching_enabled("data"):
        full_simulation_logs_cache.set(cache_key, transformed)
        logger.info("Cached transformed full simulation logs: %s", cache_key)

    return transformed


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


# ---------------------------------------------------------------------------
# Simulation drift functions (SAF-28330)
# ---------------------------------------------------------------------------

def _fetch_and_cache_simulation_drifts(
    console: str,
    payload: Dict[str, Any],
    cache_key: str,
    api_path: Optional[str] = None,
) -> tuple:
    """Fetch simulation drift records from the API, with optional caching.

    Args:
        console: SafeBreach console name
        payload: POST body for the drift API (built by build_drift_api_payload)
        cache_key: Key for the simulation_drifts_cache
        api_path: Custom API path (default: v1 simulationStatus endpoint)

    Returns:
        Tuple of (records list, elapsed_seconds float)

    Raises:
        ValueError: On 400 (validation) or 401 (auth) responses
        requests.exceptions.Timeout: On request timeout
    """
    # Check cache first
    if is_caching_enabled("data"):
        cached = simulation_drifts_cache.get(cache_key)
        if cached is not None:
            logger.info("Retrieved simulation drifts from cache: %s", cache_key)
            return cached, 0.0

    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)

    if api_path is None:
        api_path = f"/api/data/v1/accounts/{account_id}/drift/simulationStatus"
    api_url = f"{base_url}{api_path}"
    headers = {
        "Content-Type": "application/json",
        "x-apitoken": apitoken,
    }

    logger.info("Fetching simulation drifts from API for console '%s'", console)
    import time as _time
    t0 = _time.monotonic()
    response = requests.post(api_url, headers=headers, json=payload, timeout=120)
    elapsed = _time.monotonic() - t0

    if response.status_code == 400:
        raise ValueError(f"400 Bad Request from drift API: {response.text}")
    if response.status_code == 401:
        raise ValueError(f"Authentication failed (401) for console '{console}'")

    response.raise_for_status()
    records = response.json()

    logger.info(
        "Drift API returned %d records in %.1fs (%.1f MB) for console '%s'",
        len(records), elapsed, len(response.content) / 1024 / 1024, console,
    )
    if elapsed > 30:
        logger.warning(
            "Drift API response was slow (%.1fs). Consider narrowing the time window.",
            elapsed,
        )

    # Cache the result
    if is_caching_enabled("data"):
        simulation_drifts_cache.set(cache_key, records)
        logger.info("Cached %d simulation drift records: %s", len(records), cache_key)

    return records, elapsed


def _list_attack_types(console: str) -> Dict[str, Any]:
    """Return available attack_type values for a console via suggestions API."""
    from safebreach_mcp_core.suggestions import _fetch_suggestions_entries
    entries = _fetch_suggestions_entries(console, "attack_type")
    attack_types = [
        {"name": e["key"], "occurrences": e.get("doc_count", 0)}
        for e in entries
    ]
    attack_types.sort(key=lambda a: a["occurrences"], reverse=True)
    return {
        "attack_types": attack_types,
        "total": len(attack_types),
        "hint_to_agent": (
            "Valid attack_type values for this console (case-sensitive exact match). "
            "Pass one of these as attack_type to filter drifts. "
            "Note: attack_name is case-insensitive, but attack_type is NOT."
        ),
    }


def _validate_attack_type(console: str, attack_type: Optional[str]) -> None:
    """Validate attack_type against known values. Raises ValueError with valid options."""
    if attack_type is None or attack_type == "__list__":
        return
    from safebreach_mcp_core.suggestions import get_suggestions_for_collection
    try:
        valid_types = get_suggestions_for_collection(console, "attack_type")
    except Exception:
        return  # If suggestions API fails, skip validation and let the drift API handle it
    if valid_types and attack_type not in valid_types:
        raise ValueError(
            f"Invalid attack_type '{attack_type}' (case-sensitive exact match). "
            f"Valid values on this console: {valid_types}. "
            f"Use attack_type='__list__' to discover available values."
        )


_REMOVABLE_FILTERS = {
    "from_status", "to_status", "from_final_status", "to_final_status",
    "drift_type", "attack_id", "attack_type",
}


def _build_zero_results_hint(
    applied_filters: Dict[str, Any],
    elapsed_seconds: float,
) -> str:
    """Build a smart hint_to_agent when the drift API returns 0 results.

    The hint is context-aware based on which filters are active and how long
    the API call took (a proxy for dataset size).
    """
    parts: list = []

    # 1. Identify removable filters the user applied
    active = [k for k in applied_filters if k in _REMOVABLE_FILTERS]

    if active:
        names = ", ".join(active)
        parts.append(
            f"No drifts matched the current filters. "
            f"Try removing {names} to check if any drifts exist in this time window, then narrow down."
        )
    elif elapsed_seconds < 30:
        parts.append(
            "No drifts found. The API responded quickly, suggesting a small dataset. "
            "Consider extending look_back_time — attacks that run infrequently (e.g., monthly) "
            "may have baselines outside the current range. Try doubling it (14 days) or set to 30 days."
        )
    else:
        parts.append(
            f"No drifts found despite a large dataset (API took {elapsed_seconds:.0f}s). "
            "Extending the search would be slow. Consider: (a) trying a different or narrower time window, "
            "(b) filtering by attack_id or attack_type to focus the search."
        )

    # Always include cross-tool reference
    parts.append(
        "Alternatively, use get_test_drifts with a specific test ID "
        "for a targeted run-to-run comparison."
    )

    return " ".join(parts)


def _group_and_paginate_drifts(
    records: List[Dict[str, Any]],
    page_number: int,
    drift_key: Optional[str],
    applied_filters: Dict[str, Any],
    elapsed_seconds: float = 0.0,
    group_by: str = "final_status",
) -> Dict[str, Any]:
    """Group drift records and return summary or paginated drill-down.

    Two modes:
    - **Summary** (drift_key=None): Returns grouped counts without individual records.
    - **Drill-down** (drift_key set): Returns paginated records for a specific group.

    Args:
        records: Raw drift records from the API
        page_number: 0-based page number (used in drill-down mode)
        drift_key: If set, drill into this group; if None, return summary
        applied_filters: Dict of filters that were applied (for response metadata)
        elapsed_seconds: API call elapsed time in seconds (used for zero-results hints)
        group_by: Grouping mode — ``"final_status"`` or ``"result_status"``

    Returns:
        Dict with grouped summary or paginated drill-down data

    Raises:
        ValueError: On invalid drift_key or out-of-range page_number
    """
    groups = group_and_enrich_drift_records(records, group_by=group_by)

    if drift_key is None:
        # Summary mode: return groups without individual records
        summary_groups = []
        for group in groups:
            summary_groups.append({
                "drift_key": group["drift_key"],
                "count": group["count"],
                "security_impact": group["security_impact"],
                "description": group["description"],
                "hint_to_llm": group["hint_to_llm"],
            })

        if len(records) == 0:
            hint = _build_zero_results_hint(applied_filters, elapsed_seconds)
        else:
            hint = (
                "To see individual drift records, call this tool again with "
                "drift_key set to one of the drift_key values above (e.g. drift_key='prevented-logged')."
            )

        return {
            "total_drifts": len(records),
            "total_groups": len(groups),
            "drift_groups": summary_groups,
            "applied_filters": applied_filters,
            "hint_to_agent": hint,
        }

    # Drill-down mode: find the requested group
    target_group = None
    available_keys = []
    for group in groups:
        available_keys.append(group["drift_key"])
        if group["drift_key"] == drift_key:
            target_group = group

    if target_group is None:
        raise ValueError(
            f"Invalid drift_key '{drift_key}'. "
            f"Available keys: {', '.join(available_keys)}"
        )

    # Paginate the drifts within the group
    all_drifts = target_group["drifts"]
    total_in_group = len(all_drifts)
    total_pages = (total_in_group + PAGE_SIZE - 1) // PAGE_SIZE if total_in_group > 0 else 1

    if page_number >= total_pages or page_number < 0:
        raise ValueError(
            f"Page {page_number} out of range. "
            f"Available pages: 0 to {total_pages - 1}"
        )

    start_index = page_number * PAGE_SIZE
    end_index = start_index + PAGE_SIZE
    page_drifts = all_drifts[start_index:end_index]

    hint_parts = []
    if page_number + 1 < total_pages:
        hint_parts.append(
            f"Next page: call with drift_key='{drift_key}', page_number={page_number + 1}"
        )
    if group_by == "result_status":
        hint_parts.append(
            "For finer security-control-level breakdown, use get_simulation_status_drifts."
        )
    hint_parts.append(
        "To investigate a specific drift, call get_simulation_details with the "
        "simulationId from the 'from' or 'to' object. The response includes the "
        "planRunId (test ID) for tracing back to get_test_details."
    )

    result = {
        "drift_key": drift_key,
        "security_impact": target_group["security_impact"],
        "description": target_group["description"],
        "page_number": page_number,
        "total_pages": total_pages,
        "total_drifts_in_group": total_in_group,
        "drifts_in_page": page_drifts,
        "applied_filters": applied_filters,
        "hint_to_agent": " | ".join(hint_parts),
    }

    # Add final_status_breakdown for result_status grouping (coarse → fine-grained bridge)
    if group_by == "result_status":
        breakdown: Dict[str, int] = {}
        for d in all_drifts:
            fs_key = (
                f"{d.get('from', {}).get('finalStatus', 'unknown')}-"
                f"{d.get('to', {}).get('finalStatus', 'unknown')}"
            ).lower()
            breakdown[fs_key] = breakdown.get(fs_key, 0) + 1
        result["final_status_breakdown"] = breakdown

    # Attack-level sub-grouping (Phase 11) — computed from full group
    attack_counts: Dict[int, Dict[str, Any]] = {}
    for d in all_drifts:
        aid = d.get("attackId")
        if aid is not None:
            if aid not in attack_counts:
                attack_counts[aid] = {
                    "attack_id": aid,
                    "attack_name": d.get("attackName"),
                    "attack_types": d.get("attackTypes", []),
                    "count": 0,
                }
            attack_counts[aid]["count"] += 1
    result["attack_summary"] = sorted(
        attack_counts.values(), key=lambda x: x["count"], reverse=True
    )

    return result


# ---------------------------------------------------------------------------
# Public entry-point functions (SAF-28330)
# ---------------------------------------------------------------------------

_VALID_RESULT_STATUSES = {"FAIL", "SUCCESS"}
_VALID_FINAL_STATUSES = {"prevented", "stopped", "detected", "logged", "missed", "inconsistent"}
_VALID_DRIFT_TYPES = {"improvement", "regression", "not_applicable"}


def _validate_drift_type(drift_type: Optional[str]) -> None:
    """Validate drift_type parameter if provided."""
    if drift_type is not None and drift_type.lower() not in _VALID_DRIFT_TYPES:
        raise ValueError(
            f"Invalid drift_type '{drift_type}'. "
            f"Valid values: {', '.join(sorted(_VALID_DRIFT_TYPES))}"
        )


def _build_applied_filters(**kwargs: Any) -> Dict[str, Any]:
    """Build applied_filters dict from non-None keyword arguments."""
    return {k: v for k, v in kwargs.items() if v is not None}


def sb_get_simulation_result_drifts(
    console: str,
    window_start: int,
    window_end: int,
    drift_type: Optional[str] = None,
    attack_id: Optional[int] = None,
    attack_type: Optional[str] = None,
    attack_name: Optional[str] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    drift_key: Optional[str] = None,
    page_number: int = 0,
    look_back_time: Optional[int] = None,
) -> Dict[str, Any]:
    """Get simulation result drifts (blocked/not-blocked transitions) over a time window.

    Args:
        console: SafeBreach console name
        window_start: Start of time window (epoch milliseconds)
        window_end: End of time window (epoch milliseconds)
        drift_type: Filter by drift type (improvement/regression/not_applicable)
        attack_id: Filter by playbook attack ID
        attack_type: Filter by attack type
        from_status: Filter by original result status (FAIL or SUCCESS)
        to_status: Filter by new result status (FAIL or SUCCESS)
        drift_key: Drill into a specific group (e.g. "fail-success")
        page_number: Page number for drill-down mode (0-based)
        look_back_time: How far back (epoch ms) to search for baseline simulations.
            Defaults to 7 days before window_start.

    Returns:
        Summary (no drift_key), paginated drill-down (with drift_key),
        or attack type list (attack_type="__list__")
    """
    if attack_type == "__list__":
        return _list_attack_types(console)
    _validate_attack_type(console, attack_type)

    # Validate result-mode specific params
    if from_status is not None and from_status.upper() not in _VALID_RESULT_STATUSES:
        raise ValueError(
            f"Invalid from_status '{from_status}'. Valid values: {', '.join(sorted(_VALID_RESULT_STATUSES))}"
        )
    if to_status is not None and to_status.upper() not in _VALID_RESULT_STATUSES:
        raise ValueError(
            f"Invalid to_status '{to_status}'. Valid values: {', '.join(sorted(_VALID_RESULT_STATUSES))}"
        )
    _validate_drift_type(drift_type)

    from .data_types import build_drift_api_payload

    payload = build_drift_api_payload(
        window_start=window_start,
        window_end=window_end,
        drift_type=drift_type,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
        from_status=from_status,
        to_status=to_status,
        look_back_time=look_back_time,
    )

    cache_key = (
        f"result_drifts_{console}_{window_start}_{window_end}"
        f"_{drift_type}_{attack_id}_{attack_type}_{attack_name}_{from_status}_{to_status}"
        f"_{look_back_time}"
    )

    records, elapsed_seconds = _fetch_and_cache_simulation_drifts(console, payload, cache_key)

    applied_filters = _build_applied_filters(
        drift_type=drift_type,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
        from_status=from_status,
        to_status=to_status,
    )

    return _group_and_paginate_drifts(
        records, page_number, drift_key, applied_filters, elapsed_seconds,
        group_by="result_status",
    )


def sb_get_simulation_status_drifts(
    console: str,
    window_start: int,
    window_end: int,
    drift_type: Optional[str] = None,
    attack_id: Optional[int] = None,
    attack_type: Optional[str] = None,
    attack_name: Optional[str] = None,
    from_final_status: Optional[str] = None,
    to_final_status: Optional[str] = None,
    drift_key: Optional[str] = None,
    page_number: int = 0,
    look_back_time: Optional[int] = None,
) -> Dict[str, Any]:
    """Get simulation status drifts (security control final status transitions) over a time window.

    Args:
        console: SafeBreach console name
        window_start: Start of time window (epoch milliseconds)
        window_end: End of time window (epoch milliseconds)
        drift_type: Filter by drift type (improvement/regression/not_applicable)
        attack_id: Filter by playbook attack ID
        attack_type: Filter by attack type
        from_final_status: Filter by original final status
        to_final_status: Filter by new final status
        drift_key: Drill into a specific group (e.g. "prevented-logged")
        page_number: Page number for drill-down mode (0-based)
        look_back_time: How far back (epoch ms) to search for baseline simulations.
            Defaults to 7 days before window_start.

    Returns:
        Summary (no drift_key), paginated drill-down (with drift_key),
        or attack type list (attack_type="__list__")
    """
    if attack_type == "__list__":
        return _list_attack_types(console)
    _validate_attack_type(console, attack_type)

    # Validate final-status specific params
    if from_final_status is not None and from_final_status.lower() not in _VALID_FINAL_STATUSES:
        raise ValueError(
            f"Invalid from_final_status '{from_final_status}'. "
            f"Valid values: {', '.join(sorted(_VALID_FINAL_STATUSES))}"
        )
    if to_final_status is not None and to_final_status.lower() not in _VALID_FINAL_STATUSES:
        raise ValueError(
            f"Invalid to_final_status '{to_final_status}'. "
            f"Valid values: {', '.join(sorted(_VALID_FINAL_STATUSES))}"
        )
    _validate_drift_type(drift_type)

    from .data_types import build_drift_api_payload

    payload = build_drift_api_payload(
        window_start=window_start,
        window_end=window_end,
        drift_type=drift_type,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
        from_final_status=from_final_status,
        to_final_status=to_final_status,
        look_back_time=look_back_time,
    )

    cache_key = (
        f"status_drifts_{console}_{window_start}_{window_end}"
        f"_{drift_type}_{attack_id}_{attack_type}_{attack_name}_{from_final_status}_{to_final_status}"
        f"_{look_back_time}"
    )

    records, elapsed_seconds = _fetch_and_cache_simulation_drifts(console, payload, cache_key)

    applied_filters = _build_applied_filters(
        drift_type=drift_type,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
        from_final_status=from_final_status,
        to_final_status=to_final_status,
    )

    return _group_and_paginate_drifts(records, page_number, drift_key, applied_filters, elapsed_seconds)


# ---------------------------------------------------------------------------
# Security control drift functions (SAF-28331)
# ---------------------------------------------------------------------------

_VALID_TRANSITION_MODES = {"contains", "starts_and_ends"}

_SC_REMOVABLE_FILTERS = {
    "drift_type", "from_prevented", "from_reported", "from_logged", "from_alerted",
    "to_prevented", "to_reported", "to_logged", "to_alerted",
}


def _build_sc_zero_results_hint(
    applied_filters: Dict[str, Any],
    elapsed_seconds: float,
    console: str = "",
    security_control: str = "",
) -> str:
    """Build a smart hint_to_agent when the v2 drift API returns 0 results."""
    parts: list = []

    active = [k for k in applied_filters if k in _SC_REMOVABLE_FILTERS]

    if active:
        names = ", ".join(active)
        parts.append(
            f"No drifts matched the current filters. "
            f"Try removing {names} to check if any drifts exist in this time window."
        )
    elif elapsed_seconds < 30:
        parts.append(
            "No drifts found. Consider extending the time window or "
            "checking that the security control name is correct."
        )
    else:
        parts.append(
            f"No drifts found despite a large dataset (API took {elapsed_seconds:.0f}s). "
            "Consider narrowing the time window."
        )

    # Fetch known security product names to help the agent pick a valid one.
    # The suggestions API may include noisy entries (usernames, instance types),
    # but the agent can identify real products from the list.
    if console:
        try:
            suggestions = get_suggestions_for_collection(console, "security_product")
            if suggestions:
                parts.append(
                    f"Known security products on this console: {suggestions}."
                )
        except Exception:
            pass  # Don't let hint building fail the request

    parts.append(
        "Alternatively, use get_test_drifts with a specific test ID "
        "for a targeted run-to-run comparison."
    )

    return " ".join(parts)


def _group_and_paginate_sc_drifts(
    records: List[Dict[str, Any]],
    security_control: str,
    page_number: int,
    drift_key: Optional[str],
    applied_filters: Dict[str, Any],
    elapsed_seconds: float = 0.0,
    group_by: str = "transition",
    console: str = "",
) -> Dict[str, Any]:
    """Group v2 security control drift records and return summary or drill-down.

    Two modes:
    - **Summary** (drift_key=None): grouped counts.
    - **Drill-down** (drift_key set): paginated records for a specific group.
    """
    from .data_types import group_sc_drift_records

    groups = group_sc_drift_records(records, group_by=group_by)

    if drift_key is None:
        # Summary mode
        summary_groups = []
        for group in groups:
            summary_groups.append({
                "drift_key": group["drift_key"],
                "count": group["count"],
                "description": group["description"],
            })

        if len(records) == 0:
            hint = _build_sc_zero_results_hint(
                applied_filters, elapsed_seconds,
                console=console, security_control=security_control,
            )
        else:
            hint = (
                "To see individual drift records, call this tool again with "
                "drift_key set to one of the drift_key values above."
            )

        return {
            "security_control": security_control,
            "grouped_by": group_by,
            "total_drifts": len(records),
            "total_groups": len(groups),
            "drift_groups": summary_groups,
            "applied_filters": applied_filters,
            "hint_to_agent": hint,
        }

    # Drill-down mode
    target_group = None
    available_keys = []
    for group in groups:
        available_keys.append(group["drift_key"])
        if group["drift_key"] == drift_key:
            target_group = group

    if target_group is None:
        raise ValueError(
            f"Invalid drift_key '{drift_key}'. "
            f"Available keys: {', '.join(available_keys)}"
        )

    all_drifts = target_group["drifts"]
    total_in_group = len(all_drifts)
    total_pages = (total_in_group + PAGE_SIZE - 1) // PAGE_SIZE if total_in_group > 0 else 1

    if page_number >= total_pages or page_number < 0:
        raise ValueError(
            f"Page {page_number} out of range. "
            f"Available pages: 0 to {total_pages - 1}"
        )

    start_index = page_number * PAGE_SIZE
    end_index = start_index + PAGE_SIZE
    page_drifts = all_drifts[start_index:end_index]

    hint_parts = []
    if page_number + 1 < total_pages:
        hint_parts.append(
            f"Next page: call with drift_key='{drift_key}', page_number={page_number + 1}"
        )
    hint_parts.append(
        "To investigate a specific drift, call get_simulation_details with the "
        "simulationId from the 'from' or 'to' object."
    )

    return {
        "security_control": security_control,
        "drift_key": drift_key,
        "description": target_group["description"],
        "page_number": page_number,
        "total_pages": total_pages,
        "total_drifts_in_group": total_in_group,
        "drifts_in_page": page_drifts,
        "applied_filters": applied_filters,
        "hint_to_agent": " | ".join(hint_parts),
    }


def sb_get_security_control_drifts(
    console: str,
    security_control: str,
    window_start: int,
    window_end: int,
    transition_matching_mode: str,
    from_prevented: Optional[bool] = None,
    from_reported: Optional[bool] = None,
    from_logged: Optional[bool] = None,
    from_alerted: Optional[bool] = None,
    to_prevented: Optional[bool] = None,
    to_reported: Optional[bool] = None,
    to_logged: Optional[bool] = None,
    to_alerted: Optional[bool] = None,
    drift_type: Optional[str] = None,
    earliest_search_time: Optional[int] = None,
    max_outside_window_executions: Optional[int] = None,
    attack_id: Optional[int] = None,
    attack_type: Optional[str] = None,
    attack_name: Optional[str] = None,
    group_by: str = "transition",
    drift_key: Optional[str] = None,
    page_number: int = 0,
) -> Dict[str, Any]:
    """Get security control capability drifts over a time window.

    Calls the v2 drift/securityControl API and groups results by boolean
    capability transitions (prevented/reported/logged/alerted).

    Pass ``security_control="__list__"`` to enumerate available security
    control names on the console instead of querying drifts.

    Args:
        console: SafeBreach console name
        security_control: Security control name, or "__list__" to enumerate
        window_start: Start of time window (epoch milliseconds)
        window_end: End of time window (epoch milliseconds)
        transition_matching_mode: "contains" or "starts_and_ends"
        from_prevented..to_alerted: Boolean capability filters
        drift_type: Filter by drift type (improvement/regression/not_applicable)
        earliest_search_time: Baseline lookback (epoch ms, default 7d before window_start)
        max_outside_window_executions: Max executions outside window
        attack_id: Filter by playbook attack ID
        attack_type: Filter by attack type
        attack_name: Filter by attack name
        group_by: "transition" (default) or "drift_type"
        drift_key: Drill into a specific group
        page_number: Page number for drill-down (0-based)

    Returns:
        Summary (no drift_key), paginated drill-down (with drift_key),
        or security control list (security_control="__list__")
    """
    # 0. Discovery mode: list available security controls
    if security_control == "__list__":
        from safebreach_mcp_core.suggestions import _fetch_suggestions_entries
        entries = _fetch_suggestions_entries(console, "security_product")
        controls = [
            {"name": e["key"], "simulations": e.get("doc_count", 0)}
            for e in entries
        ]
        controls.sort(key=lambda c: c["simulations"], reverse=True)
        return {
            "security_controls": controls,
            "total": len(controls),
            "hint_to_agent": (
                "These are security product names from execution history, "
                "sorted by simulation count. Some entries may be noisy "
                "(usernames, instance types). "
                "Pass one of these names as security_control to query drifts."
            ),
        }

    # 0b. Discovery mode: list available attack types
    if attack_type == "__list__":
        return _list_attack_types(console)
    _validate_attack_type(console, attack_type)

    # 1. Validate transition_matching_mode
    if transition_matching_mode not in _VALID_TRANSITION_MODES:
        raise ValueError(
            f"Invalid transition_matching_mode '{transition_matching_mode}'. "
            f"Valid values: {', '.join(sorted(_VALID_TRANSITION_MODES))}"
        )

    # 2. Validate drift_type
    _validate_drift_type(drift_type)

    # 3. Map transition mode to API booleans
    contains_transition = transition_matching_mode == "contains"
    starts_and_ends_with_transition = transition_matching_mode == "starts_and_ends"

    # 5. Build payload
    from .data_types import build_security_control_drift_payload
    payload = build_security_control_drift_payload(
        security_control=security_control,
        window_start=window_start,
        window_end=window_end,
        contains_transition=contains_transition,
        starts_and_ends_with_transition=starts_and_ends_with_transition,
        from_prevented=from_prevented,
        from_reported=from_reported,
        from_logged=from_logged,
        from_alerted=from_alerted,
        to_prevented=to_prevented,
        to_reported=to_reported,
        to_logged=to_logged,
        to_alerted=to_alerted,
        drift_type=drift_type,
        earliest_search_time=earliest_search_time,
        max_outside_window_executions=max_outside_window_executions,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
    )

    # 6. Build cache key
    cache_key = (
        f"sc_drifts_{console}_{security_control}_{window_start}_{window_end}"
        f"_{transition_matching_mode}_{from_prevented}_{from_reported}"
        f"_{from_logged}_{from_alerted}_{to_prevented}_{to_reported}"
        f"_{to_logged}_{to_alerted}_{drift_type}_{earliest_search_time}"
        f"_{max_outside_window_executions}_{attack_id}_{attack_type}_{attack_name}"
    )

    # 7. Fetch via shared helper with v2 api_path
    account_id = get_api_account_id(console)
    api_path = f"/api/data/v2/accounts/{account_id}/drift/securityControl"
    records, elapsed_seconds = _fetch_and_cache_simulation_drifts(
        console, payload, cache_key, api_path=api_path,
    )

    # 8. Build applied filters and group/paginate
    applied_filters = _build_applied_filters(
        drift_type=drift_type,
        attack_id=attack_id,
        attack_type=attack_type,
        attack_name=attack_name,
        from_prevented=from_prevented,
        from_reported=from_reported,
        from_logged=from_logged,
        from_alerted=from_alerted,
        to_prevented=to_prevented,
        to_reported=to_reported,
        to_logged=to_logged,
        to_alerted=to_alerted,
    )

    return _group_and_paginate_sc_drifts(
        records, security_control, page_number, drift_key,
        applied_filters, elapsed_seconds, group_by=group_by,
        console=console,
    )


def sb_get_simulation_lineage(
    console: str,
    tracking_code: str,
    page_number: int = 0,
) -> Dict[str, Any]:
    """Return all simulations sharing a drift tracking code across test runs.

    Queries the SafeBreach API with ``runId: "*"`` to search across every test
    run, transforms results via :func:`get_reduced_simulation_result_entity`,
    computes per-simulation ``is_drifted`` by comparing to the chronological
    predecessor, and returns a paginated response ordered oldest-first.
    """
    if not tracking_code or not tracking_code.strip():
        raise ValueError("tracking_code must be a non-empty string")

    cache_key = f"lineage_{console}_{tracking_code}"
    all_simulations = None

    # Check cache
    if is_caching_enabled("data"):
        cached = simulations_cache.get(cache_key)
        if cached is not None:
            logger.info("Lineage cache hit for tracking_code '%s'", tracking_code)
            all_simulations = cached

    # Fetch from API if not cached
    if all_simulations is None:
        apitoken = get_secret_for_console(console)
        base_url = get_api_base_url(console, "data")
        account_id = get_api_account_id(console)

        api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistoryResults"
        headers = {"Content-Type": "application/json", "x-apitoken": apitoken}

        all_raw: List[Dict[str, Any]] = []
        page = 1
        page_size = 100

        while True:
            data = {
                "runId": "*",
                "query": f'originalExecutionId:("{tracking_code}")',
                "page": page,
                "pageSize": page_size,
                "orderBy": "asc",
                "sortBy": "executionTime",
            }

            response = requests.post(api_url, headers=headers, json=data, timeout=120)

            if response.status_code == 401:
                raise ValueError(
                    f"Authentication failed (401) for console '{console}'. "
                    "Check that the API token is valid."
                )
            response.raise_for_status()

            response_data = response.json()
            page_sims = response_data.get("simulations", [])
            if not page_sims:
                break

            all_raw.extend(page_sims)
            if len(page_sims) < page_size:
                break
            page += 1

        # Transform via existing mapper
        all_simulations = [
            get_reduced_simulation_result_entity(s) for s in all_raw
        ]

        # Compute is_drifted by comparing to chronological predecessor
        for i, sim in enumerate(all_simulations):
            if i == 0:
                sim["is_drifted"] = False
            else:
                sim["is_drifted"] = sim["status"] != all_simulations[i - 1]["status"]

        # Cache the transformed list
        if is_caching_enabled("data"):
            simulations_cache.set(cache_key, all_simulations)

    # Metadata
    total_simulations = len(all_simulations)
    status_summary: Dict[str, int] = {}
    for sim in all_simulations:
        s = sim.get("status", "unknown")
        status_summary[s] = status_summary.get(s, 0) + 1

    test_runs_spanned = len({s["test_id"] for s in all_simulations}) if all_simulations else 0
    first_seen = all_simulations[0]["end_time"] if all_simulations else None
    last_seen = all_simulations[-1]["end_time"] if all_simulations else None

    # MCP pagination
    total_pages = (total_simulations + PAGE_SIZE - 1) // PAGE_SIZE if total_simulations > 0 else 0
    start_idx = page_number * PAGE_SIZE
    page_sims = all_simulations[start_idx : start_idx + PAGE_SIZE]

    # Hint
    if total_simulations == 0:
        hint = (
            "No simulations found for this tracking code. "
            "The tracking code may be invalid or the simulations may have aged out."
        )
    else:
        hint = (
            f"Showing page {page_number} of {total_pages}. "
            "Use get_simulation_details for full details on any simulation."
        )

    return {
        "tracking_code": tracking_code,
        "total_simulations": total_simulations,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "status_summary": status_summary,
        "test_runs_spanned": test_runs_spanned,
        "page_number": page_number,
        "total_pages": total_pages,
        "simulations": page_sims,
        "hint_to_agent": hint,
    }


# ------------------------------------------------------------------
# Peer benchmark score (SAF-29415) — POST /api/data/v1/accounts/{id}/score
# ------------------------------------------------------------------
# Hint fragments composed when the backend response indicates partial or
# missing data. Strings are tuned for natural-language reasoning by the
# LLM consumer and to the substring assertions in the unit tests.
_PEER_BENCHMARK_204_HINT = (
    "No executions in the requested window, or all matched attacks were "
    "custom (peer benchmark excludes custom attack IDs >= 10,000,000)."
)
_PEER_BENCHMARK_NULL_CUSTOMER_HINT = "No customer executions in this window."
_PEER_BENCHMARK_NULL_PEER_HINT = (
    "No all-peers data for this window "
    "(possibly frozen snapshot on staging/private-dev)."
)
_PEER_BENCHMARK_EMPTY_INDUSTRY_HINT = (
    "No customer-industry data for this window "
    "(possibly frozen snapshot on staging/private-dev)."
)


def sb_get_peer_benchmark_score(
    console: str,
    start_date: int,
    end_date: int,
    include_test_ids_filter: Optional[str] = None,
    exclude_test_ids_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch the peer benchmark score for the given window via the SafeBreach
    Data API and return the MCP-shaped response.

    Wraps ``POST /api/data/v1/accounts/{account_id}/score`` (delivered in
    SAF-27621). Validates inputs at the MCP boundary, caches per-(console,
    window, sorted filters), converts epoch dates to ISO 8601 UTC for the
    request body, handles HTTP 204 explicitly, composes a ``hint_to_agent``
    when scores are null/empty, and runs the response through the Phase 1
    transform helper.

    Args:
        console: SafeBreach console name (resolved via environments_metadata).
        start_date: Epoch milliseconds for the start of the window.
        end_date: Epoch milliseconds for the end of the window.
        include_test_ids_filter: Comma-separated planRunIds to restrict
            scoring to. Mutually exclusive with ``exclude_test_ids_filter``.
        exclude_test_ids_filter: Comma-separated planRunIds to exclude.

    Returns:
        Dict with snake_case keys per ``peer_benchmark_rename_mapping``.
        ``customer_score`` and ``all_peers_score`` may be None;
        ``customer_industry_scores`` may be []. ``hint_to_agent`` is
        included when any of those conditions hold or when the backend
        returns HTTP 204.

    Raises:
        ValueError: When both filters are non-empty, or when
            ``start_date >= end_date``.
        requests.HTTPError: Propagated from the backend on non-2xx
            responses other than 204.
    """
    inc = (
        [v.strip() for v in include_test_ids_filter.split(",") if v.strip()]
        if include_test_ids_filter else []
    )
    exc = (
        [v.strip() for v in exclude_test_ids_filter.split(",") if v.strip()]
        if exclude_test_ids_filter else []
    )

    if inc and exc:
        raise ValueError(
            "Cannot provide both include_test_ids_filter and "
            "exclude_test_ids_filter. Omit both to include all tests."
        )

    if start_date >= end_date:
        raise ValueError("start_date must be before end_date.")

    cache_key = (
        f"peer_benchmark_{console}_{start_date}_{end_date}_"
        f"{','.join(sorted(inc))}_{','.join(sorted(exc))}"
    )
    if is_caching_enabled("data"):
        cached = peer_benchmark_cache.get(cache_key)
        if cached is not None:
            logger.info(
                "Retrieved peer benchmark score from cache for console '%s'",
                console,
            )
            return cached

    apitoken = get_secret_for_console(console)
    base_url = get_api_base_url(console, 'data')
    account_id = get_api_account_id(console)
    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/score"

    iso_start = convert_epoch_to_datetime(start_date)["iso_datetime"]
    iso_end = convert_epoch_to_datetime(end_date)["iso_datetime"]

    body: Dict[str, Any] = {"startDate": iso_start, "endDate": iso_end}
    if inc:
        body["includeTestIds"] = inc
    if exc:
        body["excludeTestIds"] = exc

    headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}

    logger.info(
        "Fetching peer benchmark score for console '%s' "
        "(start=%s, end=%s, include=%d, exclude=%d)",
        console, iso_start, iso_end, len(inc), len(exc),
    )
    response = requests.post(api_url, headers=headers, json=body, timeout=120)

    if response.status_code == 204:
        result = {
            "start_date": iso_start,
            "end_date": iso_end,
            "customer_score": None,
            "all_peers_score": None,
            "customer_industry_scores": [],
            "hint_to_agent": _PEER_BENCHMARK_204_HINT,
        }
        if is_caching_enabled("data"):
            peer_benchmark_cache.set(cache_key, result)
        return result

    try:
        response.raise_for_status()
    except requests.HTTPError:
        # Log without the API token — only console, URL, and status code.
        logger.error(
            "Peer benchmark API request failed for console '%s' "
            "(URL: %s, status: %s)",
            console, api_url, response.status_code,
        )
        raise

    backend_json = response.json()

    hint_fragments = []
    if backend_json.get("customerScore") is None:
        hint_fragments.append(_PEER_BENCHMARK_NULL_CUSTOMER_HINT)
    if backend_json.get("peerScore") is None:
        hint_fragments.append(_PEER_BENCHMARK_NULL_PEER_HINT)
    if not backend_json.get("industryScores"):
        hint_fragments.append(_PEER_BENCHMARK_EMPTY_INDUSTRY_HINT)
    hint = "; ".join(hint_fragments) if hint_fragments else None

    result = get_reduced_peer_benchmark_response(backend_json, hint=hint)

    if is_caching_enabled("data"):
        peer_benchmark_cache.set(cache_key, result)

    return result
