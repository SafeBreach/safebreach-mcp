# SAF-28331 Preparation Context

**Ticket ID**: SAF-28331
**Title**: Add Security Control Drift API to MCP
**Status**: Phase 3: Context Created
**Mode**: Improve Existing Ticket
**Repo**: /Users/yossiattas/Public/safebreach-mcp

---

## Ticket Summary

**Type**: Story
**Status**: To Do
**Assignee**: Yossi Attas (you)
**Reporter**: Shahaf Raviv
**Priority**: Medium
**Created**: Feb 16, 2026

### Current Description

As a SafeBreach MCP consumer (LLM client, automation workflow, or AI assistant user), expose the v2 Drift by Security Control API endpoint so users can query tracking IDs with status transitions matching drift patterns within a time window, scoped by security control.

**Key Requirements**:
- MCP tool exposure of v2 Drift by Security Control endpoint
- Time window filters (windowStart, windowEnd in ISO-8601 UTC)
- Context controls (earliestSearchTime, maxOutsideWindowExecutions)
- Transition filters (fromStatus, toStatus)
- Transition matching modes (containsTransition vs startsAndEndsWithTransition) - mutually exclusive
- Optional drift type filter
- All timestamps in ISO-8601 UTC format

**Definition of Done**:
- API available as MCP tool with all filters mapped correctly
- Functional tests validate each filter
- Example prompts documented
- Product review approval

---

## Investigation Findings

**Status**: Phase 4 Complete

### 1. Existing Drift Implementation (Data Server)

**Existing drift tools** already in place:
- **`get_test_drifts`** (data_functions.py:1466-1651): Compares two specific test runs, finds status drifts with drift tracking codes
- **`get_simulation_result_drifts`** (data_server.py:303-372): Time-window-based posture view (FAIL/SUCCESS transitions)
- **`get_simulation_status_drifts`** (data_server.py:374-445): Time-window-based control view (prevented/stopped/detected/logged/missed/inconsistent transitions)

**Drift metadata reference** (`drifts_metadata.py`): Maps 273 drift patterns with security_impact and descriptions

### 2. Data Server Architecture (Three-Tier Stack)

```
data_server.py (MCP tool registration)
       ↓
data_functions.py (business logic & API calls)
       ↓
data_types.py (data transformations)
```

Key modules:
- **data_server.py** (lines 34-446): `@self.mcp.tool()` decorators, timestamp normalization, delegation pattern
- **data_functions.py** (lines 1-2275): Core business logic, caching (SafeBreachCache), helper functions
- **data_types.py** (lines 1-754): Payload builders, field mapping, grouping enrichment

### 3. API Client Integration

**HTTP Pattern**:
- GET requests: `requests.get()`
- POST requests: `requests.post()` with `json=data` parameter
- Headers: `Content-Type: application/json`, `x-apitoken`
- Timeout: 120 seconds standard
- Error handling: `response.raise_for_status()`

**Drift API endpoint**: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`

**Response structure**: Array of drift records with:
```
trackingId, attackId, attackTypes,
from: { simulationId, executionTime, finalStatus, status, loggedBy, reportedBy, alertedBy, preventedBy },
to: { ... same structure ... },
driftType: "Improvement|Regression|NotApplicable"
```

### 4. Tool Exposure Patterns

**Registration pattern** (data_server.py):
```python
@self.mcp.tool(name="...", description="...")
async def tool_name(param1: Type, param2: Type = None) -> dict:
    param = normalize_timestamp(param) if param else None  # Handle ISO-8601 and epochs
    return sb_function_name(param1, param2)
```

**Docstring convention**: Each tool includes "USE THIS WHEN" / "DON'T USE FOR" sections with cross-references

### 5. Pagination & Filtering Patterns

**Pagination** (PAGE_SIZE = 10):
- Local pagination with `page_number` and `total_pages`
- Response includes `hint_to_agent` for scanning next page
- Applied filters tracked in response metadata

**Filter validation** (constants):
- `_VALID_RESULT_STATUSES = {"FAIL", "SUCCESS"}`
- `_VALID_FINAL_STATUSES = {"prevented", "stopped", "detected", "logged", "missed", "inconsistent"}`
- `_VALID_DRIFT_TYPES = {"improvement", "regression", "not_applicable"}`
- Validation raises ValueError with helpful message on invalid input

### 6. Caching Infrastructure

**SafeBreachCache instances** (lines 30-34):
- `simulation_drifts_cache = SafeBreachCache(name="simulation_drifts", maxsize=3, ttl=600)`
- Cache key pattern: `f"{console}_{window_start}_{window_end}_{drift_type}_{attack_id}..."`
- Controlled by `is_caching_enabled("data")` function

### 7. Test Patterns

**Test file**: `safebreach_mcp_data/tests/test_drift_tools.py`
- Fixtures for sample drift records
- Mock data with realistic structure
- Both unit tests and E2E tests (`@pytest.mark.e2e`)
- Payload builder tests separate from integration tests

### 8. Key Difference from SAF-28330

**Existing drift tools** (SAF-28330):
- Result-level: Group by FAIL/SUCCESS (posture view)
- Status-level: Group by prevented/stopped/detected/logged/missed/inconsistent (control view)

**SAF-28331 requirements** (NEW):
- Security control-scoped drift analysis
- **Transition matching modes** (containsTransition vs startsAndEndsWithTransition) — MUTUALLY EXCLUSIVE
  - `containsTransition`: Match if sequence contains fromStatus → toStatus **at least once**
  - `startsAndEndsWithTransition`: Match only if **first** and **last** statuses equal the transition
- This is a NEW filtering dimension beyond result/status drifts

---

## Brainstorming Results

**Status**: Phase 5 Complete

### Design Decisions

1. **Security Control Scoping**: Optional parameter
   - If not specified, returns all controls
   - If specified, filters to that control only

2. **Transition Matching Modes**: Required enum selector (NOT optional boolean flags)
   - `containsTransition`: Match if sequence contains fromFinalStatus → toFinalStatus **at least once**
   - `startsAndEndsWithTransition`: Match only if **first** and **last** statuses equal the transition
   - Mutual exclusivity enforced at tool level

3. **Response Strategy**: Two-Phase Grouped (Summary → Drill-Down)
   - **Phase 1 (Summary)**: Return grouped counts with applied filters
   - **Phase 2 (Drill-Down)**: Return paginated records within a specific group
   - Follows existing SAF-28330 pattern for consistency

4. **Grouping Flexibility**: Three grouping modes
   - `group_by='transition'`: Group by fromFinalStatus-toFinalStatus (e.g., 'prevented-detected')
   - `group_by='drift_type'`: Group by Improvement/Regression/NotApplicable
   - `group_by='attack_id'`: Group by attackId for attack-focused analysis
   - Caller controls which grouping dimension to use

5. **Complementary Tool**: New tool alongside existing result/status drifts
   - Not replacing get_simulation_result_drifts or get_simulation_status_drifts
   - Provides security control-scoped analysis as new dimension

### Implementation Approach (Chosen: Approach B with Flexible Grouping)

Two-phase pattern matching existing Data Server tools:

**Tool Signature**:
```python
async def get_security_control_drifts(
    console: str,
    security_control: str = None,  # Optional
    window_start: str | int,       # ISO-8601 or epoch
    window_end: str | int,         # ISO-8601 or epoch
    transition_matching_mode: str,  # "contains" or "starts_and_ends" (REQUIRED, enum)
    from_final_status: str = None,  # prevented|stopped|detected|logged|missed|inconsistent
    to_final_status: str = None,    # prevented|stopped|detected|logged|missed|inconsistent
    drift_type: str = None,         # improvement|regression|not_applicable
    earliest_search_time: str | int = None,
    max_outside_window_executions: int = None,
    group_by: str = "transition",   # Default grouping: transition|drift_type|attack_id
    group_key: str = None,          # For drill-down (phase 2): specifies which group to paginate
    page_number: int = 0,
) -> dict
```

**Phase 1 (Summary) Response**:
```python
{
    "grouped_by": "transition",  # Or "drift_type" or "attack_id"
    "groups": {
        "prevented-detected": {"count": 12, "security_impact": "negative"},
        "detected-prevented": {"count": 3, "security_impact": "positive"},
        ...
    },
    "total_records": 47,
    "applied_filters": {"securityControl": "X", "driftType": "Regression", ...},
    "hint_to_agent": "Drill-down using group_key='prevented-detected' for details"
}
```

**Phase 2 (Drill-Down) Response**:
```python
{
    "group_key": "prevented-detected",
    "records": [
        {
            "trackingId": "...",
            "attackId": 1263,
            "attackTypes": ["..."],
            "from": {...},
            "to": {...},
            "driftType": "Regression"
        },
        ...
    ],
    "page_number": 0,
    "total_pages": 2,
    "records_in_page": 10,
    "total_records_in_group": 12,
    "applied_filters": {...},
    "hint_to_agent": "Page 1 of 2. Get next page with page_number=1"
}
```

---

## Notes

- You're currently on branch `SAF-28331-drift-by-security-control`
- No comments on the ticket yet
- This is an API exposure story, not a UI/UX story
