# Ticket Summary: SAF-29727

## Overview
**Mode**: Improving existing ticket  
**Project**: SAF (SafeBreach platform)  
**Repositories**: safebreach-mcp (MCP codebase), data (backend API - reference PR #2799)

---

## Current State

**Original Ticket Summary**: Add attack filters to drift tools in SafeBreach MCP

**Original Issues Identified**:
- Ticket requested support for attack-related filters (attackId, attackType, attackName) in drift tools
- Scope was ambiguous: which drift tools specifically? How should the filters integrate?
- No clarity on what data is available from the backend APIs

---

## Investigation Summary

### SafeBreach MCP Codebase

The investigation identified **3 drift tools** in `safebreach_mcp_data/`:

1. **`get_simulation_result_drifts()`** (data_server.py:351-381)
   - Time-window-based drift analysis for result status transitions (FAIL/SUCCESS)
   - Currently supports `attack_id` filtering (partial implementation)
   - Missing: `attack_type` and `attack_name` exposure in tool signature

2. **`get_simulation_status_drifts()`** (data_server.py:425-455)
   - Time-window-based drift analysis for security control status transitions
   - Currently supports `attack_id` filtering (partial implementation)
   - Missing: `attack_type` and `attack_name` exposure in tool signature

3. **`sb_get_security_control_drifts()`** (data_server.py)
   - Capability transitions for specific security controls
   - Missing: No attack filtering support at all

### Critical Finding: Partial Implementation Gap

**Current implementation status:**
- ✅ **`attack_id`** - Fully implemented end-to-end:
  - `build_drift_api_payload()` in data_types.py correctly maps to API camelCase
  - Drift functions accept `attack_id` parameter
  - **BUT** not exposed in MCP tool signatures for result/status drift tools
  
- ⚠️ **`attack_type`** - Partially implemented:
  - `build_drift_api_payload()` in data_types.py correctly maps to API camelCase
  - Drift functions accept `attack_type` parameter
  - **NOT exposed** in any MCP tool signatures
  
- ❌ **`attack_name`** - Not available in current API:
  - Backend API returns `attackTypes` (array of strings like "Legitimate Channel Exfiltration")
  - No single `attackName` field exists
  - Response parser already extracts and returns `attackTypes` in `attack_summary` field

**Backend context**: Per reference PR https://bitbucket.org/safebreach/data/pull-requests/2799, need to verify if backend API has been enhanced to support `attackName` filtering.

### Response Format

Attack data is already extracted and available in drift responses:
- `attack_summary` field contains: `attackId`, `attack_types` (array), and `count`
- Grouped by attack ID with counts of drifts per attack
- Sorted for consistent ordering

### Test Coverage

Existing tests in `test_drift_tools.py`:
- ✅ `test_build_payload_attack_filters()` - Validates `attack_id` and `attack_type` mapping
- ✅ `test_attack_summary_includes_attack_types()` - Validates attack_types extraction
- ❌ Missing: Tests for `attack_type` parameter flowing through MCP tool layer
- ❌ Missing: Tests for `security_control_drifts` (new tool addition)

---

## Problem Analysis

### Problem Description

The ticket requires adding attack-related filters to SafeBreach MCP drift tools to allow consumers to query drifts by attack properties without additional processing. Investigation reveals the backend implementation is **partially complete**:

- Core filtering logic exists in data_functions.py and data_types.py
- Filters are NOT exposed in MCP tool signatures (data_server.py)
- Attack data is already being extracted from responses but only `attack_id` is currently filterable via MCP tools
- `attack_type` filtering is implemented but hidden; `attack_name` availability depends on backend API enhancements

### Scope
Apply attack filtering across ALL three drift tools: `get_simulation_result_drifts`, `get_simulation_status_drifts`, and `sb_get_security_control_drifts`.

### Impact Assessment

**Affected Components**:
- **data_server.py** (lines 351-381, 425-455): MCP tool parameter registration
- **data_functions.py** (lines 2127-2280): Drift computation functions (minimal changes needed)
- **test_drift_tools.py**: Test coverage for new parameters

**User Impact**:
- Enables natural-language queries like "Show me drifts for CrowdStrike against attack X last 7 days"
- Reduces need for post-processing to filter by attack properties
- Supports both time-window-based and test-run-based drift analysis

### Risks & Edge Cases

- **API field availability**: Backend API must support `attackType` and optionally `attackName` filters
- **Test completeness**: Need to verify all three drift tools handle attack filtering correctly
- **Response consistency**: Ensure attack data is returned consistently across all three tools
- **Performance**: Filtering by attack properties should not degrade performance for large drift datasets

---

## Proposed Ticket Content

### Summary (Title)
**Add attack filters to all SafeBreach MCP drift tools**

### Description

As an MCP drift tools consumer, I want to filter drift analysis results by attack properties (attackId, attackType, attackName) so that I can query drift data without additional post-processing or external lookups.

#### Background

SafeBreach drift analysis tools (`get_simulation_result_drifts`, `get_simulation_status_drifts`, `sb_get_security_control_drifts`) help identify when simulations produce different results between test runs. Currently, these tools support basic filtering (time windows, status, etc.) but lack attack-specific filtering, requiring consumers to manually filter drift results by attack properties.

#### Technical Context

- Attack filtering logic is partially implemented: `build_drift_api_payload()` in data_types.py already maps attack parameters (`attackId`, `attackType`, `attackName`) to API camelCase format
- Drift analysis functions in data_functions.py already accept attack filter parameters but these are not exposed in MCP tool signatures (data_server.py)
- Attack data (`attackId`, `attackTypes`) is already extracted from API responses and returned in the `attack_summary` field
- Backend implementation details in https://bitbucket.org/safebreach/data/pull-requests/2799 may require verification for `attackName` support

#### Problem Description

Three drift tools currently lack attack filtering in their MCP tool signatures:
1. `get_simulation_result_drifts()` - Supports time-window drift analysis for result status transitions (FAIL/SUCCESS)
2. `get_simulation_status_drifts()` - Supports time-window drift analysis for security control status transitions (prevented/stopped/detected/logged/missed/inconsistent)
3. `sb_get_security_control_drifts()` - Analyzes capability transitions for specific security controls

While `attack_id` filtering is partially implemented (in data_functions), `attack_type` filtering is completely hidden, and `attack_name` availability is unclear.

#### Affected Areas
- **safebreach_mcp_data/data_server.py**: Tool registration for all three drift tools (missing attack filter parameters)
- **safebreach_mcp_data/data_types.py**: API payload building (already correct, no changes needed)
- **safebreach_mcp_data/data_functions.py**: Drift computation (minimal changes if any)
- **safebreach_mcp_data/tests/test_drift_tools.py**: Test coverage for attack filter parameter exposure

### Acceptance Criteria

- [ ] **`get_simulation_result_drifts` tool supports attack filtering:**
  - [ ] Accepts `attack_id` parameter (integer, optional)
  - [ ] Accepts `attack_type` parameter (string, optional)
  - [ ] Accepts `attack_name` parameter if backend API supports it
  - [ ] Parameters are passed correctly to the underlying API
  - [ ] Drift responses include attack information when filters are applied

- [ ] **`get_simulation_status_drifts` tool supports attack filtering:**
  - [ ] Accepts `attack_id` parameter (integer, optional)
  - [ ] Accepts `attack_type` parameter (string, optional)
  - [ ] Accepts `attack_name` parameter if backend API supports it
  - [ ] Parameters are passed correctly to the underlying API
  - [ ] Drift responses include attack information when filters are applied

- [ ] **`sb_get_security_control_drifts` tool supports attack filtering:**
  - [ ] Accepts `attack_id` parameter (integer, optional)
  - [ ] Accepts `attack_type` parameter (string, optional)
  - [ ] Accepts `attack_name` parameter if backend API supports it
  - [ ] Parameters are passed correctly to the underlying API
  - [ ] Drift responses include attack information when filters are applied

- [ ] **Implementation completeness:**
  - [ ] All attack filter parameters integrated into data_server.py tool definitions
  - [ ] API payload building correctly maps parameters to backend API format
  - [ ] Response parsing extracts and returns attack information

- [ ] **Test coverage:**
  - [ ] Tests validate `attack_type` parameter flows through MCP tool layer for all three tools
  - [ ] Tests validate `attack_name` parameter flows through MCP tool layer (if API supports it)
  - [ ] Tests validate drift responses include attack summary when filters are applied
  - [ ] Tests cover edge cases (no drifts matching filters, multiple attacks, etc.)

- [ ] **Documentation:**
  - [ ] Tool descriptions updated to document new attack filter parameters
  - [ ] Parameter documentation clarifies what data is available (`attackName` availability based on backend API support)

- [ ] **Product review:**
  - [ ] User can query drifts using natural language like "Show me drifts for CrowdStrike against attack X last 7 days"
  - [ ] Attack filtering works across all three drift tools consistently

---

## Key Decisions

1. **Scope**: Attack filtering should be added to ALL three drift tools (result drifts, status drifts, and security control drifts), not just the two mentioned in the original description
2. **Backward compatibility**: NOT required — tool signatures can be modified freely
3. **Attack name field**: Should verify backend API support; if unavailable, document that `attackTypes` (array) is the alternative
4. **Response format**: No changes needed — attack data already included in `attack_summary` field

---

## Implementation Notes

- **No backward compatibility concerns** — can modify all tool signatures
- **Minimal backend changes** — core filtering logic already exists in data_types.py and data_functions.py
- **Main work**: Exposing missing parameters in data_server.py and adding comprehensive test coverage
- **Verification needed**: Check backend API implementation (PR #2799) for `attackType` and `attackName` support details
