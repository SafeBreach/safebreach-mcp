# SAF-28582: Full Simulation Logs Error - Context

## Ticket Information

- **ID**: SAF-28582
- **Title**: [safebreach-mcp] On staging: error when getting full simulation logs
- **Type**: Bug
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Priority**: Medium
- **Created**: Feb 24, 2026
- **Sprint**: Saf sprint 83
- **Time Estimate**: 3h

**Link**: https://safebreach.atlassian.net/browse/SAF-28582

## Current Phase

Phase 6: PRD Created

## Problem Statement

During pressure testing on staging (2026-02-24 ~12:53 UTC), the Data MCP server logged an error when attempting to retrieve full simulation logs:

```
2026-02-24 12:53:06,641 - safebreach_mcp_data.data_functions - ERROR - Error getting full simulation logs for simulation '3213805', test '1771853252399.2' from console 'default': Response missing dataObj.data structure
```

### Root Cause

1. **Cache-before-validation bug**: The response is cached BEFORE the mapping/validation step, so bad responses get cached and fail on subsequent lookups until TTL expires
2. **Unhandled empty data**: When `dataObj.data` is empty, the code raises ValueError instead of handling it gracefully
3. **Why empty?**: The API returns HTTP 200 but the execution log entries for simulation 3213805 under test 1771853252399.2 are not present in the response body

### Affected Code Paths

- `safebreach_mcp_data/data_functions.py:1656-1722` - `sb_get_full_simulation_logs()`
- `safebreach_mcp_data/data_functions.py:1725-1760` - `_get_full_simulation_logs_from_cache_or_api()` (caches before validation)
- `safebreach_mcp_data/data_types.py:466-471` - `get_full_simulation_logs_mapping()` (raises ValueError)
- `safebreach_mcp_data/data_functions.py:1763-1797` - `_fetch_full_simulation_logs_from_api()` (GET endpoint)

## Investigation Scope

**Repository**: /Users/yossiattas/Public/safebreach-mcp

**Focus Areas**:
1. Data server caching architecture and TTL mechanism
2. Full simulation logs data transformation and validation
3. Error handling patterns in other similar functions
4. API response structure assumptions and edge cases

## Investigation Findings

### 1. Cache-Before-Validation Bug (CRITICAL)
**Location:** `safebreach_mcp_data/data_functions.py:1725-1760` (`_get_full_simulation_logs_from_cache_or_api()`)

Raw API response is cached at lines 1756-1758 **BEFORE** structural validation occurs. When API returns `{"dataObj": {"data": [[]]}}` (empty nested arrays), this invalid data gets cached with 300-second TTL.

**Code snippet:**
```python
data = _fetch_full_simulation_logs_from_api(simulation_id, test_id, console)
# ↓ No validation between fetch and cache ↓
if is_caching_enabled("data"):
    full_simulation_logs_cache.set(cache_key, data)  # CACHES INVALID RESPONSE
    logger.info("Cached full simulation logs: %s", cache_key)
return data
```

### 2. Insufficient Validation Logic (HIGH)
**Location:** `safebreach_mcp_data/data_types.py:470-471` (`get_full_simulation_logs_mapping()`)

Validation check `if not data_array or not data_array[0]:` may not catch empty nested arrays correctly. For `data_array = [[]]`:
- `not data_array` = False (outer array is non-empty)
- `not data_array[0]` = True (inner array is empty)
- Result: Code should catch, but if there's an issue with the logic or downstream processing at line 473+, it may fail

**Code snippet:**
```python
data_array = data_obj.get('data', [[]])
if not data_array or not data_array[0]:
    raise ValueError("Response missing dataObj.data structure")  # ← Should catch [[]]
entries = data_array[0]  # Becomes []
# Line 497+: Code tries to access entries[0] → potential IndexError
```

### 3. Pattern Inconsistency with Other Functions (MEDIUM)
Unlike all other data server functions (`_get_all_findings_from_cache_or_api`, `_get_all_tests_from_cache_or_api`, etc.):
- **Others:** Cache transformed/extracted data (e.g., `findings_data = data.get('findings', [])` then cache)
- **Full simulation logs:** Caches raw API response, then validates during transformation
- **Impact:** This is the ONLY function mixing cache and validate operations

### 4. Cache Configuration (HIGH)
**Location:** `safebreach_mcp_data/data_functions.py:1652-1653`

Cache parameters:
- **Maxsize:** 2 entries (very restrictive)
- **TTL:** 300 seconds (5 minutes)
- **Control:** Enabled via `SB_MCP_CACHE_DATA=true`

**Impact:** Invalid data served to all callers for 300 seconds after first bad API response.

### 5. Error Handling (MEDIUM)
**Location:** `safebreach_mcp_data/data_functions.py:1656-1722` (`sb_get_full_simulation_logs()`)

ValueError from transformation is caught and logged but:
- Cached invalid data is NOT invalidated
- Function raises exception instead of returning graceful error
- No retry mechanism or fallback

### 6. Legitimate Empty Cases
Investigation confirmed there ARE valid scenarios where API returns empty `dataObj.data`:
- Logs still being collected by API
- Logs pruned/archived due to retention policies
- Simulation failed before log collection
- API returning partial results during high load

**Current behavior:** Treats all empty data as errors. Should gracefully handle and return meaningful message.

## E2E Verification Results (TDD - RCA Confirmation)

All 4 E2E tests passed against staging.safebreach.com via SSH tunnel:

| Test | Result | What It Confirms |
|------|--------|------------------|
| `test_raw_api_response_has_empty_data` | PASS | API returns HTTP 200 with `dataObj.data = [[]]`, status `INTERNAL_FAIL` |
| `test_mapping_raises_value_error_on_empty_data` | PASS | `get_full_simulation_logs_mapping()` raises `ValueError("Response missing dataObj.data structure")` |
| `test_sb_get_full_simulation_logs_raises_on_empty_data` | PASS | Full function chain propagates the ValueError |
| `test_cache_before_validation_bug` | PASS | Invalid response is cached before validation, causing repeated failures for 300s |

**Key Discovery**: Simulation 3213805 has status `INTERNAL_FAIL` — this is a legitimate API response where the simulation ran but failed internally, producing no execution logs.

**E2E test file**: `safebreach_mcp_data/tests/test_e2e_saf28582.py` (temporary, to be removed before merge)

## Brainstorming Results

**Selected Approach**: Approach A — Validate-Then-Cache (aligns with all other data functions)

User decisions:
- Primary fix: Cache-before-validation pattern
- Follow pattern of other data functions (cache after transformation)
- Handle empty logs gracefully with status message (not error)

## Proposed Solution

_(to be populated after approval phase)_

## Status Log

- **2026-02-24 15:20**: Context file created, preparing for investigation
