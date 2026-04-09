# Ticket Context: SAF-29727

## Status
Phase 6: PRD Created

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
- /Users/yossiattas/projects/data (backend data repo - local)
- Context: https://bitbucket.org/safebreach/data/pull-requests/2799 (backend API - MERGED)

## Backend API Contract (from PR #2799 - MERGED)

### Security Control Drift API (`POST /drift/securityControl`)
New request params: `attackId` (int, exact), `attackName` (string, match_phrase), `attackType` (string, exact)
Response: `attackId`, `attackName`, `attackTypes` at top level of each drift pair

### Simulation Status Drift API (`POST /drift/simulationStatus`)
Already had: `attackId`, `attackType`
New: `attackName` (string, match_phrase)
Response: `attackId`, `attackName`, `attackTypes` at top level of each drift pair

### Field Mapping (API → ES)
- `attackId` → `moveId` (exact match filter)
- `attackName` → `moveName` (match_phrase filter)
- `attackType` → `Attack_Type.value.keyword` (exact match filter)
- Response `attackTypes` is flattened array from `Attack_Type[].value`

### CORRECTION from initial investigation
`attackName` IS available in the API (mapped to `moveName`).
Earlier finding that "`attackName` does not exist" was wrong.
Both APIs support all three attack filters.

## Investigation Findings

### Drift Tools Scope
Four main drift analysis functions found in `safebreach_mcp_data/data_functions.py`:
1. `sb_get_test_drifts()` - Compares two test runs with same name
2. `sb_get_simulation_result_drifts()` - Time-window-based drift for result transitions (FAIL/SUCCESS)
3. `sb_get_simulation_status_drifts()` - Time-window-based drift for security control status (prevented/stopped/logged/detected/missed/inconsistent)
4. `sb_get_security_control_drifts()` - Capability transitions for specific security controls

### Full Gap Analysis Per Tool

#### 1. `get_simulation_result_drifts` (v1 API: `/drift/simulationStatus`)
| Layer | attack_id | attack_type | attack_name |
|-------|-----------|-------------|-------------|
| data_types.py (build_drift_api_payload) | ✅ | ✅ | ❌ Missing |
| data_functions.py (sb_get_simulation_result_drifts) | ✅ | ✅ | ❌ Missing |
| data_server.py (MCP tool) | ✅ | ❌ Not exposed | ❌ Missing |

#### 2. `get_simulation_status_drifts` (v1 API: `/drift/simulationStatus`)
| Layer | attack_id | attack_type | attack_name |
|-------|-----------|-------------|-------------|
| data_types.py (build_drift_api_payload) | ✅ | ✅ | ❌ Missing |
| data_functions.py (sb_get_simulation_status_drifts) | ✅ | ✅ | ❌ Missing |
| data_server.py (MCP tool) | ✅ | ❌ Not exposed | ❌ Missing |

#### 3. `get_security_control_drifts` (v2 API: `/drift/securityControl`)
| Layer | attack_id | attack_type | attack_name |
|-------|-----------|-------------|-------------|
| data_types.py (build_security_control_drift_payload) | ❌ Missing | ❌ Missing | ❌ Missing |
| data_functions.py (sb_get_security_control_drifts) | ❌ Missing | ❌ Missing | ❌ Missing |
| data_server.py (MCP tool) | ❌ Missing | ❌ Missing | ❌ Missing |

#### Response Handling
- `attack_summary` extracts `attackId` and `attackTypes` but NOT `attackName`
- Need to add `attack_name` to attack_summary entries

### Key Files
- `safebreach_mcp_data/data_functions.py` - lines 2127 (result), 2205 (status), 2445 (SC)
- `safebreach_mcp_data/data_types.py` - lines 618 (build_drift_api_payload), 761 (build_sc_payload)
- `safebreach_mcp_data/data_server.py` - lines 351 (result tool), 425 (status tool), 504 (SC tool)
- `safebreach_mcp_data/tests/test_drift_tools.py` - existing attack filter tests

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

## Brainstorming Decisions

### Builder Strategy: Approach A (Separate Builders)
- Keep `build_drift_api_payload()` for result/status drifts — add `attack_name` param
- Keep `build_security_control_drift_payload()` for SC drifts — add all 3 attack params
- Rationale: preserves v1/v2 API separation, minimal diff, trivial duplication

### Implementation Phasing: Approach B (Tool-by-Tool, TDD, Elephant Carpaccio)
- Implement each tool fully before moving to the next
- Pure TDD: write tests first, then implement to pass
- Elephant carpaccio: thinnest possible vertical slices
- Order: result drifts → status drifts → security control drifts → response enrichment

## Proposed Improvements
(Phase 6)
