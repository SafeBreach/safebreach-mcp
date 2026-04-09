# Ticket Context: SAF-29727

## Status
Phase 3: Context Initialized

## Mode
Improving

## Original Ticket
- **Summary**: Add attack filters to drift tools in SafeBreach MCP
- **Description**: 
  - As an MCP Drift tools consumer, want MCP Drift tools to support new attack-related filters and fields
  - Support filters: attackId, attackType, attackName (Security Control API); attackName (Simulation Status API - attackId and attackType already exist)
  - Pass filters correctly to underlying APIs
  - Include in response: attackId, attackType, attackName
  - Keep behavior unchanged when no filters are used
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Reporter**: Shahaf Raviv
- **Priority**: Medium
- **Type**: Story
- **Created**: Apr 6, 2026

## Task Scope
Add drift filtering by attacks — implement attack-related filters (attackId, attackType, attackName) to the SafeBreach MCP drift tools, allowing consumers to query drift data without additional processing or lookups.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp (main MCP codebase)
- Context: https://bitbucket.org/safebreach/data/pull-requests/2799 (backend API implementation details)

## Investigation Findings

### Drift Tools Scope
Four main drift analysis functions found in `safebreach_mcp_data/data_functions.py`:
1. `sb_get_test_drifts()` - Compares two test runs with same name
2. `sb_get_simulation_result_drifts()` - Time-window-based drift for result transitions (FAIL/SUCCESS)
3. `sb_get_simulation_status_drifts()` - Time-window-based drift for security control status (prevented/stopped/logged/detected/missed/inconsistent)
4. `sb_get_security_control_drifts()` - Capability transitions for specific security controls

### Critical Gap: Partial Implementation

**Current state:**
- ✅ `attack_id` filtering fully implemented end-to-end (data_types → data_functions → MCP tool)
- ⚠️ `attack_type` filtering implemented in data_types.py and data_functions.py BUT **NOT EXPOSED in MCP tool signatures** in data_server.py
- ❌ `attack_name` does NOT exist in API responses (only `attackTypes` array; no single name field)

### Implementation Details

**In `data_types.py` - `build_drift_api_payload()` (lines 618-665):**
- Correctly maps `attack_id` → `"attackId"` (int)
- Correctly maps `attack_type` → `"attackType"` (string)
- Both included in payload only if non-None

**In `data_server.py` - MCP Tool Registration:**
- `get_simulation_result_drifts_tool()`: Has `attack_id` parameter (line 358), **missing `attack_type`**
- `get_simulation_status_drifts_tool()`: Has `attack_id` parameter (line 432), **missing `attack_type`**

**In responses - `_group_and_paginate_drifts()` (lines 2085-2100):**
- Already extracts `attackId` and `attackTypes` from drift records
- Returns in `attack_summary` field with attack counts and types

### Test Coverage
- Tests exist for `attack_id` parameter mapping and extraction (test_drift_tools.py)
- Tests missing for `attack_type` parameter exposure in MCP tools
- No tests needed for `attack_name` (API field doesn't exist)

### Key Files
- `safebreach_mcp_data/data_functions.py` - Core drift functions with attack filter parameters
- `safebreach_mcp_data/data_types.py` - API payload building and response parsing
- `safebreach_mcp_data/data_server.py` - **MCP tool registration (missing `attack_type` parameter)**
- `safebreach_mcp_data/tests/test_drift_tools.py` - Test coverage

## Problem Analysis

### Scope Clarification
Add `attackId`, `attackType`, and `attackName` filtering to ALL three drift tools:
1. `get_simulation_result_drifts()` - Add filters to existing tool
2. `get_simulation_status_drifts()` - Add filters to existing tool  
3. `sb_get_security_control_drifts()` - Add filters to this tool as well

Filters should be added to the extent the backend APIs support them (per API documentation/implementation).

### Implementation Approach
**No backward compatibility required** — can modify tool signatures freely.

**For each drift tool:**
- Add `attack_id` parameter (already works in drift functions, needs exposure in data_server.py)
- Add `attack_type` parameter (implemented in data_types.py/data_functions.py, needs exposure in data_server.py)
- Add `attack_name` parameter (verify API support; investigation found no `attackName` field, only `attackTypes` array)
- Route through existing `build_drift_api_payload()` function
- Ensure response includes attack information when available

### Key Implementation Points
- `attack_id` and `attack_type` are already implemented in backend — just need MCP tool parameter exposure
- API payload building in `data_types.py` already supports these filters correctly
- Response parsing already extracts and returns attack data in `attack_summary` field
- Need to verify `attackName` support with backend implementation (PR context: https://bitbucket.org/safebreach/data/pull-requests/2799)

### Required Changes
1. **data_server.py**: Add missing parameters to all three drift tool definitions
2. **Test coverage**: Add tests validating `attack_type` and `attack_name` parameters flow through MCP layer
3. **Documentation**: Update tool descriptions to include new attack filter parameters

## Proposed Improvements
(Phase 6)
