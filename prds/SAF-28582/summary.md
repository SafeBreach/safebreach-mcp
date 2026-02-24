# SAF-28582: Fix full simulation logs error for empty dataObj.data

## Summary

Fix two bugs in `get_full_simulation_logs` when the SafeBreach API returns HTTP 200 with empty execution logs (`dataObj.data = [[]]`):
1. **Cache-before-validation**: Invalid API response gets cached for 5 minutes before the code discovers it's empty, causing repeated failures
2. **Unhandled empty data**: Raises `ValueError` instead of returning a graceful response with empty logs

## Root Cause (E2E Verified)

The API returns HTTP 200 for simulation 3213805 with `status: INTERNAL_FAIL` and `dataObj.data = [[]]` (empty inner array). Note: `INTERNAL_FAIL` does not inherently mean empty logs — some internally-failed simulations may have partial logs. In this case the logs happen to be empty. The fix adds a safe check for empty `dataObj.data` regardless of simulation status.

## Approach: Validate-Then-Cache (Approach A)

Align `full_simulation_logs` with the pattern used by all other data functions — validate and transform BEFORE caching. Handle empty `dataObj.data` as a valid state, not an error.

## Changes Required

### 1. `safebreach_mcp_data/data_types.py` — `get_full_simulation_logs_mapping()`

**Current** (line 470-471):
```python
if not data_array or not data_array[0]:
    raise ValueError("Response missing dataObj.data structure")
```

**Fix**: Instead of raising, return a valid response with empty logs and a status message:
```python
if not data_array or not data_array[0]:
    return {
        "simulation_id": str(api_response.get('id', '')),
        "test_id": api_response.get('planRunId', ''),
        "run_id": api_response.get('runId', ''),
        "execution_times": { ... },
        "status": {
            "overall": api_response.get('status', ''),
            "final_status": api_response.get('finalStatus', ''),
            "security_action": api_response.get('securityAction', ''),
        },
        "attack_info": { ... },
        "target": None,
        "attacker": None,
        "logs_available": False,
        "logs_status": "No execution logs available for this simulation",
    }
```

### 2. `safebreach_mcp_data/data_functions.py` — `_get_full_simulation_logs_from_cache_or_api()`

**Current** (lines 1753-1758): Caches raw API response before transformation.

**Fix**: Move transformation inside the cache-or-API function, cache the transformed result (matching other data functions):
```python
def _get_full_simulation_logs_from_cache_or_api(simulation_id, test_id, console):
    cache_key = f"full_simulation_logs_{console}_{simulation_id}_{test_id}"

    if is_caching_enabled("data"):
        cached = full_simulation_logs_cache.get(cache_key)
        if cached is not None:
            return cached

    raw_data = _fetch_full_simulation_logs_from_api(simulation_id, test_id, console)

    # Transform BEFORE caching (validate-then-cache pattern)
    from .data_types import get_full_simulation_logs_mapping
    transformed = get_full_simulation_logs_mapping(raw_data)

    if is_caching_enabled("data"):
        full_simulation_logs_cache.set(cache_key, transformed)

    return transformed
```

### 3. `safebreach_mcp_data/data_functions.py` — `sb_get_full_simulation_logs()`

**Simplify**: Remove the transformation call since it now happens in the cache layer:
```python
def sb_get_full_simulation_logs(simulation_id, test_id, console="default"):
    # ... validation ...
    try:
        result = _get_full_simulation_logs_from_cache_or_api(simulation_id, test_id, console)
        return result  # Already transformed
    except Exception as e:
        logger.error(...)
        raise
```

### 4. `safebreach_mcp_data/data_server.py` — MCP tool handler

Update the MCP tool's response formatting to handle the `logs_available: False` case:
- When `logs_available` is False, return the status message and metadata without attempting to display empty target/attacker fields.

## Test Plan

### Unit Tests (permanent)
- [ ] Test `get_full_simulation_logs_mapping()` with empty `dataObj.data = [[]]` returns valid response with `logs_available: False`
- [ ] Test `get_full_simulation_logs_mapping()` with missing `dataObj` returns valid response with `logs_available: False`
- [ ] Test `_get_full_simulation_logs_from_cache_or_api()` caches transformed data (not raw response)
- [ ] Test that cache miss fetches from API, transforms, then caches
- [ ] Test that cache hit returns transformed data without API call
- [ ] Test that invalid API response is NOT cached
- [ ] Verify existing tests still pass (161 unit tests)

### E2E Tests (temporary — remove before merge)
- [x] `test_raw_api_response_has_empty_data` — API returns HTTP 200 with empty dataObj.data
- [x] `test_mapping_raises_value_error_on_empty_data` — Current code raises ValueError
- [x] `test_sb_get_full_simulation_logs_raises_on_empty_data` — Full error path confirmed
- [x] `test_cache_before_validation_bug` — Invalid response cached for 300s confirmed

### Post-Fix E2E Verification
- [ ] Re-run against staging: function returns graceful response instead of ValueError
- [ ] Verify caching works correctly with transformed data

## Acceptance Criteria

1. `get_full_simulation_logs` returns a valid response (not exception) when API returns empty execution logs
2. Response includes `logs_available: False` and `logs_status` message explaining why logs are missing
3. Response still includes all available metadata (simulation_id, test_id, status, attack_info)
4. Invalid API responses are NOT cached (validate-then-cache pattern)
5. Valid transformed responses ARE cached (matching other data function patterns)
6. All 161 existing unit tests continue to pass
7. Cross-server test suite (all servers) continues to pass
