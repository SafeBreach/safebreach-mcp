# SAF-28331 Summary: Add Security Control Drift API to MCP

**Status**: Unblocked - Ready for Implementation

---

## What This Ticket Addresses

SAF-28331 exposes SafeBreach's **v2 Drift by Security Control** API endpoint through the MCP Data Server.
This enables LLM clients and automation workflows to analyze drift patterns for a specific security
control—tracking which capabilities (prevention, reporting, logging, alerting) changed over time.

**Context**: SAF-28330 (completed) exposed result-level and status-level drifts via
`/api/data/v1/.../drift/simulationStatus`. SAF-28331 adds a **new v2 endpoint** with a fundamentally
different data model: boolean status flags per capability instead of a single `finalStatus` string.

---

## API Details (Corrected)

### Endpoint

`POST /api/data/v2/accounts/{accountId}/drift/securityControl`

### Request Body

```json
{
  "securityControl": "Microsoft Defender for Endpoint",
  "windowStart": "2025-10-12T11:01:14.931Z",
  "windowEnd": "2025-10-13T13:20:50.099Z",
  "earliestSearchTime": "2025-10-10T00:00:00.000Z",
  "maxOutsideWindowExecutions": 0,
  "driftType": "Improvement",
  "fromStatus": {
    "logged": false,
    "reported": true,
    "prevented": false,
    "alerted": true
  },
  "toStatus": {
    "logged": false,
    "reported": true,
    "prevented": true,
    "alerted": true
  },
  "containsTransition": true,
  "startsAndEndsWithTransition": false
}
```

### Response

```json
[
  {
    "trackingId": "abc123def456...",
    "from": {
      "simulationId": 820344,
      "executionTime": "2025-10-12T11:01:14.931Z",
      "prevented": false,
      "reported": true,
      "logged": false,
      "alerted": true
    },
    "to": {
      "simulationId": 838191,
      "executionTime": "2025-10-13T13:20:50.099Z",
      "prevented": true,
      "reported": true,
      "logged": false,
      "alerted": true
    },
    "driftType": "Improvement"
  }
]
```

### Key Differences from Existing Drift APIs (v1/simulationStatus)

| Aspect | v1 simulationStatus (SAF-28330) | v2 securityControl (SAF-28331) |
|--------|------|------|
| Endpoint | `/v1/.../drift/simulationStatus` | `/v2/.../drift/securityControl` |
| Status model | Single `finalStatus` string | Boolean flags per capability |
| Status fields | `finalStatus`, `status` | `prevented`, `reported`, `logged`, `alerted` |
| Attack info | `attackId`, `attackTypes` present | Not present in response |
| `fromStatus`/`toStatus` | String params (`fromFinalStatus`) | Object params with boolean fields |
| Transition modes | Not supported | `containsTransition` / `startsAndEndsWithTransition` |
| Security control | Not a parameter | Required `securityControl` param |

---

## Key Features

### 1. Two-Phase Analysis Pattern (Summary -> Drill-Down)

**Phase 1: Summary View**
- Query with filters and grouping preference
- Returns grouped record counts organized by selected dimension
- Use case: "Show me drift summary for 'Microsoft Defender' in the last 7 days"

**Phase 2: Drill-Down View**
- Specify a group key to paginate detailed records within that group
- Includes full tracking IDs, simulation IDs, timestamps, and boolean status details
- Use case: "Show me the records where prevention was gained"

### 2. Flexible Grouping (Two Dimensions)

- **`group_by='transition'`**: Group by boolean status transition
  (e.g., `{P:F,R:T,L:F,A:T}->{P:T,R:T,L:F,A:T}` = gained prevention)
- **`group_by='drift_type'`**: Group by Improvement/Regression

Note: `group_by='attack_id'` is NOT supported since the v2 response doesn't include attack info.

### 3. Transition Matching Modes (API-Level Booleans)

Two mutually exclusive boolean API parameters:
- **`containsTransition=true`**: Match if the status sequence contains the from->to transition
  **at least once** during the window
- **`startsAndEndsWithTransition=true`**: Match only if the **first** and **last** statuses
  equal the from/to transition

Validation: exactly one must be true.

### 4. Boolean Status Filters

Status transitions are defined as objects with four boolean capability flags:
- `prevented`: Whether the security control prevented the attack
- `reported`: Whether the security control reported the attack
- `logged`: Whether the security control logged the attack
- `alerted`: Whether the security control alerted on the attack

---

## Unblocking: Execution History Suggestions Helper

The ticket was blocked because the LLM agent had no way to discover valid `securityControl` values.

**Solution**: A shared helper in `safebreach_mcp_core/` that fetches from the
`GET /api/data/v1/accounts/{accountId}/executionsHistorySuggestions` endpoint.

**Endpoint details**:
- Returns `{ "completion": { ... 60+ collections ... } }`
- Each collection is an array of `{"key": "name", "doc_count": N}`
- The `security_product` collection provides valid security control names
  (e.g., "Microsoft Defender for Endpoint", "CrowdStrike Falcon")

**Design**:
- Location: `safebreach_mcp_core/suggestions.py` (shared across all servers)
- Generic interface: accepts console name + collection name, returns list of values
- Cacheable (suggestions change infrequently)
- Any MCP server can import and use it for input validation or discovery

**Usage in SAF-28331**:
- Before calling the v2 drift API, validate `security_control` against known values
- Or provide hints in error messages when an invalid control name is supplied

---

## Implementation Plan

### 1. Data Types Layer (`data_types.py`)

New payload builder for the v2 security control drift API:

```python
def build_security_control_drift_payload(
    security_control: str,
    window_start: int,          # epoch ms
    window_end: int,            # epoch ms
    contains_transition: bool,
    starts_and_ends_with_transition: bool,
    from_prevented: bool | None = None,
    from_reported: bool | None = None,
    from_logged: bool | None = None,
    from_alerted: bool | None = None,
    to_prevented: bool | None = None,
    to_reported: bool | None = None,
    to_logged: bool | None = None,
    to_alerted: bool | None = None,
    drift_type: str | None = None,
    earliest_search_time: int | None = None,
    max_outside_window_executions: int | None = None,
) -> dict
```

Maps to API payload:
```json
{
  "securityControl": "string",
  "windowStart": "ISO-8601",
  "windowEnd": "ISO-8601",
  "containsTransition": true,
  "startsAndEndsWithTransition": false,
  "fromStatus": { "prevented": false, "reported": true, "logged": false, "alerted": true },
  "toStatus": { "prevented": true, "reported": true, "logged": false, "alerted": true },
  "driftType": "Improvement",
  "earliestSearchTime": "ISO-8601",
  "maxOutsideWindowExecutions": 0
}
```

New response transformation for boolean status records:

```python
def map_security_control_drift_record(record: dict) -> dict:
    """Transform a raw v2 drift record into agent-friendly format.

    Converts boolean status flags into readable status strings and
    generates a human-readable transition description.
    """
```

### 2. Functions Layer (`data_functions.py`)

**Primary Function** (single entry point, two-phase via `group_key` presence):

1. **`sb_get_security_control_drifts()`**
   - Validates inputs (transition mode mutual exclusivity, boolean params)
   - Calls `POST /api/data/v2/accounts/{accountId}/drift/securityControl`
   - If no `group_key`: groups records and returns summary
   - If `group_key`: paginates records within that group and returns drill-down

**Helper Functions**:
- `_validate_security_control_drift_params()`: Validate mutual exclusivity of
  containsTransition/startsAndEndsWithTransition, validate boolean status params
- `_build_status_transition_key()`: Generate transition key from boolean flags
  (e.g., `"P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T"`)
- `_describe_status_transition()`: Generate human-readable description
  (e.g., "Gained prevention capability")
- `_fetch_and_cache_security_control_drifts()`: API call with caching

### 3. Server Layer (`data_server.py`)

**MCP Tool Registration**:

```python
@self.mcp.tool(
    name="get_security_control_drifts",
    description="""Analyze capability transitions for a specific security control over time.
    Shows how a control's prevented/reported/logged/alerted capabilities changed.

    USE THIS WHEN: You need to understand how a specific security control's capabilities
    changed over time (e.g., gained/lost prevention, started alerting).

    DON'T USE FOR:
      - Overall blocked/not-blocked posture (use get_simulation_result_drifts)
      - Security control final status overview (use get_simulation_status_drifts)
      - Comparing two specific test runs (use get_test_drifts)
    """
)
async def get_security_control_drifts(
    console: str,
    security_control: str,             # Required - scopes to specific control
    window_start: str | int,           # ISO-8601 or epoch
    window_end: str | int,             # ISO-8601 or epoch
    transition_matching_mode: str,     # "contains" or "starts_and_ends" (REQUIRED)
    from_prevented: bool | None = None,
    from_reported: bool | None = None,
    from_logged: bool | None = None,
    from_alerted: bool | None = None,
    to_prevented: bool | None = None,
    to_reported: bool | None = None,
    to_logged: bool | None = None,
    to_alerted: bool | None = None,
    drift_type: str | None = None,     # improvement|regression
    earliest_search_time: str | int | None = None,
    max_outside_window_executions: int | None = None,
    group_by: str = "transition",      # transition|drift_type
    group_key: str | None = None,      # For drill-down
    page_number: int = 0,
) -> dict
```

### 4. Response Structures

**Summary Phase Response** (group_key is None):
```json
{
  "security_control": "Microsoft Defender for Endpoint",
  "grouped_by": "transition",
  "groups": {
    "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T": {
      "count": 5,
      "description": "Gained prevention capability while maintaining reporting and alerting",
      "drift_types": {"Improvement": 5}
    },
    "P:T,R:T,L:T,A:T->P:F,R:T,L:T,A:T": {
      "count": 3,
      "description": "Lost prevention capability",
      "drift_types": {"Regression": 3}
    }
  },
  "total_records": 8,
  "applied_filters": {
    "securityControl": "Microsoft Defender for Endpoint",
    "windowStart": "2025-10-12T11:01:14.931Z",
    "windowEnd": "2025-10-13T13:20:50.099Z",
    "transitionMatchingMode": "contains"
  },
  "hint_to_agent": "Drill-down using group_key='P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T' for details."
}
```

**Drill-Down Phase Response** (group_key provided):
```json
{
  "security_control": "Microsoft Defender for Endpoint",
  "group_key": "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T",
  "description": "Gained prevention capability while maintaining reporting and alerting",
  "records": [
    {
      "trackingId": "abc123def456...",
      "from": {
        "simulationId": 820344,
        "executionTime": "2025-10-12T11:01:14.931Z",
        "prevented": false,
        "reported": true,
        "logged": false,
        "alerted": true
      },
      "to": {
        "simulationId": 838191,
        "executionTime": "2025-10-13T13:20:50.099Z",
        "prevented": true,
        "reported": true,
        "logged": false,
        "alerted": true
      },
      "driftType": "Improvement"
    }
  ],
  "page_number": 0,
  "total_pages": 1,
  "records_in_page": 5,
  "total_records_in_group": 5,
  "hint_to_agent": null
}
```

### 5. Testing Strategy

**Unit Tests** (`test_security_control_drifts.py`):
- Payload builder: boolean status object construction, timestamp conversion
- Validation: transition mode mutual exclusivity, at least one boolean specified
- Grouping: transition key generation from boolean combos, drift_type grouping
- Pagination: page boundaries, hints
- Response mapping: boolean flags to readable descriptions
- Mock API responses matching v2 format

**E2E Tests** (requires real SafeBreach environment):
- End-to-end with actual v2 API
- Filter combinations with real security controls
- Both transition matching modes

### 6. Caching

- Reuse existing `simulation_drifts_cache` (maxsize=3, ttl=600s)
- Cache key includes: console, security_control, window_start, window_end, transition_mode,
  all from/to booleans, drift_type
- Controlled by `is_caching_enabled("data")`

---

## Example User Queries (via MCP)

### Query 1: Overview of regressions for a control
*"Show me all regressions for 'Microsoft Defender for Endpoint' in the last 7 days."*

```
Tool Call:
  console: "prod"
  security_control: "Microsoft Defender for Endpoint"
  window_start: "2026-02-28T00:00:00Z"
  window_end: "2026-03-07T00:00:00Z"
  transition_matching_mode: "contains"
  drift_type: "regression"
  group_by: "transition"

Response: Summary grouped by boolean status transitions
```

### Query 2: Specific status transition
*"Find tracking IDs where the control stopped preventing attacks but kept alerting."*

```
Tool Call:
  console: "prod"
  security_control: "Microsoft Defender for Endpoint"
  window_start: "2026-02-28T00:00:00Z"
  window_end: "2026-03-07T00:00:00Z"
  transition_matching_mode: "contains"
  from_prevented: true
  to_prevented: false
  from_alerted: true
  to_alerted: true

Response: Matching records where prevention was lost but alerting maintained
```

### Query 3: Drill-down into a transition group
*"Show me the 5 records where prevention was gained."*

```
Tool Call:
  (same filters as Query 1, plus:)
  group_key: "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T"
  page_number: 0

Response: Paginated list of tracking IDs with full details
```

---

## Definition of Done

**Implementation**
- [ ] `safebreach_mcp_core/suggestions.py`: Generic shared helper for fetching execution history suggestions
- [ ] `data_types.py`: Payload builder for v2 security control drift API with boolean status objects
- [ ] `data_types.py`: Response transformation for boolean status records
- [ ] `data_functions.py`: Entry point function with summary/drill-down phases
- [ ] `data_functions.py`: Helper functions (validation, transition key, caching)
- [ ] `data_server.py`: MCP tool registration with documentation
- [ ] Timestamp normalization (ISO-8601 and epoch)
- [ ] Transition matching mode mutual exclusivity validation
- [ ] Boolean status object construction for `fromStatus`/`toStatus`
- [ ] `maxOutsideWindowExecutions` parameter support

**Testing**
- [ ] Unit tests for payload builders (boolean status objects)
- [ ] Unit tests for validation (transition modes, boolean params)
- [ ] Unit tests for grouping logic (transition keys, drift_type)
- [ ] Unit tests for pagination
- [ ] Unit tests for response transformation
- [ ] E2E tests with real SafeBreach API (`@pytest.mark.e2e`)

**Documentation**
- [ ] MCP tool docstring with "USE THIS WHEN / DON'T USE FOR" guidance
- [ ] Example queries in docstring
- [ ] Cross-references to related drift tools

**Code Quality**
- [ ] Follows Data Server three-tier architecture
- [ ] Reuses SafeBreachCache infrastructure
- [ ] Consistent error handling and logging
- [ ] Type hints throughout
- [ ] No breaking changes

---

## Acceptance Criteria

1. Tool `get_security_control_drifts` is available in Data Server
2. Calls `POST /api/data/v2/accounts/{accountId}/drift/securityControl` correctly
3. Two-phase usage (summary -> drill-down) works correctly
4. `group_by` controls organization (transition or drift_type)
5. Both `containsTransition` and `startsAndEndsWithTransition` modes work as specified
6. Boolean status filters (`from_prevented`, `to_prevented`, etc.) correctly build API payload
7. `securityControl` parameter properly scopes queries
8. `maxOutsideWindowExecutions` and `earliestSearchTime` parameters work
9. Drill-down pagination with proper hints
10. Caching works appropriately
11. Invalid inputs produce helpful error messages
12. Full test coverage (unit + E2E)

---

## Implementation Notes

### Design Rationale

**Why individual boolean params instead of a dict?**
- LLM agents interact more naturally with named boolean params
  (`from_prevented=true`) than JSON objects
- Allows partial specification (only specify booleans you care about)
- MCP tool params don't support nested objects well

**Why `group_by='attack_id'` is not supported?**
- The v2 securityControl endpoint doesn't return `attackId` in responses
- Only `trackingId`, `from`, `to`, and `driftType` are available

**Transition key format: `P:T,R:F,L:F,A:T->P:T,R:T,L:F,A:T`**
- Compact representation of boolean status combo
- P=prevented, R=reported, L=logged, A=alerted, T=true, F=false
- Arrow separates from->to states

### Gotchas & Edge Cases

1. **Mutual exclusivity**: `containsTransition` and `startsAndEndsWithTransition` cannot both be true
2. **Partial boolean specs**: If only some from/to booleans provided, only include those in the API
   `fromStatus`/`toStatus` objects
3. **No attack info**: Unlike v1 drift API, v2 doesn't return attackId/attackTypes
4. **Boolean combos**: 4 flags = 16 possible states per side = up to 256 unique transitions
5. **Empty results**: Provide smart hints (wrong control name? narrow time window? try other matching mode?)
