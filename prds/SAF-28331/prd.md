# PRD: SAF-28331 — Security Control Drift API

**Ticket**: SAF-28331
**Branch**: `SAF-28331-drift-by-security-control`
**Author**: Yossi Attas
**Status**: Ready for Implementation
**Last Updated**: 2026-03-12

---

## Phase Status Tracking

| Phase | Name | Status | Completed | Commit | Notes |
|-------|------|--------|-----------|--------|-------|
| 1 | Shared Suggestions Helper | ✅ Complete | 2026-03-12 | — | `safebreach_mcp_core/suggestions.py` |
| 2 | Payload Builder & Grouping | ✅ Complete | 2026-03-12 | — | `data_types.py` |
| 3 | Business Logic | ✅ Complete | 2026-03-12 | — | `data_functions.py` |
| 4 | MCP Tool Registration | ✅ Complete | 2026-03-12 | — | `data_server.py` |
| 5 | E2E Tests | ✅ Complete | 2026-03-12 | — | Automated against `pentest01` |

---

## Overview

Expose the SafeBreach v2 Drift by Security Control API (`POST /api/data/v2/accounts/{accountId}/drift/securityControl`)
as an MCP tool in the Data Server. This complements the existing result-level and status-level drift tools (SAF-28330)
by adding a **security-control-scoped** drift dimension with a **boolean capability model** (prevented, reported,
logged, alerted) instead of a single `finalStatus` string.

### Relationship to Existing Drift Tools

| Tool | View | API | Status Model |
|------|------|-----|-------------|
| `get_simulation_result_drifts` | Posture (FAIL/SUCCESS) | v1/drift/simulationStatus | String `status` |
| `get_simulation_status_drifts` | Control (finalStatus) | v1/drift/simulationStatus | String `finalStatus` |
| **`get_security_control_drifts`** | **Security Control** | **v2/drift/securityControl** | **Boolean flags** |

---

## Implementation Phases

### Phase 1: Shared Suggestions Helper (`safebreach_mcp_core/suggestions.py`)

**Goal**: Create a generic, cached helper for fetching execution history suggestions that any MCP server can use.

#### 1.1 New File: `safebreach_mcp_core/suggestions.py`

**API**: `GET /api/data/v1/accounts/{accountId}/executionsHistorySuggestions`

**Response structure**:
```json
{
  "completion": {
    "security_product": [{"key": "Microsoft Defender for Endpoint", "doc_count": 500}, ...],
    "security_controls": [{"key": "Endpoint", "doc_count": 300}, ...],
    "...": "60+ other collections"
  }
}
```

**Function signature**:
```python
def get_suggestions_for_collection(
    console: str,
    collection_name: str,
) -> list[str]:
    """Fetch valid values for a specific data-plane collection.

    Returns a list of string keys from the executionsHistorySuggestions API
    for the requested collection. Results are cached with TTL.

    Args:
        console: SafeBreach console name
        collection_name: Name of the collection (e.g., "security_product")

    Returns:
        List of valid string values for the collection

    Raises:
        ValueError: If collection_name not found in API response
    """
```

**Caching**:
- New `SafeBreachCache` instance: `suggestions_cache = SafeBreachCache(name="suggestions", maxsize=10, ttl=1800)`
- Cache key: `f"{console}_{collection_name}"`
- Controlled by `is_caching_enabled("data")` (same as other data caches)
- Suggestions change infrequently — 30min TTL is appropriate

**HTTP pattern** (match existing):
```python
apitoken = get_secret_for_console(console)
base_url = get_api_base_url(console, 'data')
account_id = get_api_account_id(console)
api_url = f"{base_url}/api/data/v1/accounts/{account_id}/executionsHistorySuggestions"
headers = {"Content-Type": "application/json", "x-apitoken": apitoken}
response = requests.get(api_url, headers=headers, timeout=120)
response.raise_for_status()
```

**Tests** (TDD — write first): `safebreach_mcp_core/tests/test_suggestions.py`
- Write all 8 tests before implementing `suggestions.py`
- See [Test Strategy: Phase 1](#phase-1--suggestions-helper-tdd) for full test list

#### 1.2 Update `safebreach_mcp_core/__init__.py`

Export the new `get_suggestions_for_collection` function so other servers can import it directly.

---

### Phase 2: Payload Builder (`data_types.py`)

**Goal**: Add v2-specific payload builder and response transformation functions.

#### 2.1 New Function: `build_security_control_drift_payload()`

Builds the POST body for the v2 security control drift API. Key difference from `build_drift_api_payload()`:
the v1 builder uses string `fromStatus`/`toStatus`, while v2 uses **object** `fromStatus`/`toStatus` with boolean
capability flags.

```python
def build_security_control_drift_payload(
    security_control: str,
    window_start: int,              # epoch ms
    window_end: int,                # epoch ms
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
) -> dict:
```

**Output payload**:
```json
{
  "securityControl": "Microsoft Defender for Endpoint",
  "windowStart": "2025-10-12T11:01:14.000Z",
  "windowEnd": "2025-10-13T13:20:50.000Z",
  "earliestSearchTime": "2025-10-05T11:01:14.000Z",
  "containsTransition": true,
  "startsAndEndsWithTransition": false,
  "fromStatus": {"prevented": false, "reported": true, "logged": false, "alerted": true},
  "toStatus": {"prevented": true, "reported": true, "logged": false, "alerted": true},
  "driftType": "Improvement",
  "maxOutsideWindowExecutions": 0
}
```

**Rules**:
- Reuse existing `_epoch_ms_to_iso()` helper for timestamp conversion
- Reuse existing `_LOOK_BACK_DEFAULT_MS` for default `earliestSearchTime`
- Reuse existing `_DRIFT_TYPE_MAP` for drift_type normalization
- `fromStatus`/`toStatus` objects: only include boolean keys that are not None (partial specification)
- `fromStatus`/`toStatus` omitted entirely if all 4 booleans for that side are None

#### 2.2 New Function: `build_sc_drift_transition_key()`

Generates a compact transition key from boolean flags in a v2 drift record.

```python
def build_sc_drift_transition_key(record: dict) -> str:
    """Build transition key from v2 boolean status flags.

    Format: 'P:T,R:F,L:F,A:T->P:T,R:T,L:F,A:T'
    Where P=prevented, R=reported, L=logged, A=alerted, T=true, F=false

    Args:
        record: Raw v2 drift record with 'from' and 'to' objects containing boolean flags

    Returns:
        Compact transition key string
    """
```

#### 2.3 New Function: `group_sc_drift_records()`

Groups v2 drift records by transition key or drift type.

```python
def group_sc_drift_records(
    records: list[dict],
    group_by: str = "transition",
) -> list[dict]:
    """Group v2 security control drift records.

    Args:
        records: Raw v2 drift records from the API
        group_by: "transition" (boolean flag combos) or "drift_type" (Improvement/Regression)

    Returns:
        List of group dicts sorted by count descending, each containing:
        - drift_key: Group identifier
        - count: Number of records in group
        - description: Human-readable description of the transition
        - drifts: List of records in this group
    """
```

**Grouping modes**:
- `"transition"`: Uses `build_sc_drift_transition_key()` to group by boolean flag combos
- `"drift_type"`: Groups by `driftType` field (Improvement / Regression / NotApplicable)

**Description generation** (for transition mode):
- Compare `from` and `to` boolean flags to produce human-readable descriptions
- Example: `"Gained prevention capability"` when `from.prevented=false, to.prevented=true`
- Example: `"Lost prevention, gained logging"` for multi-flag changes

**Tests** (TDD — write first): New test classes in `test_drift_tools.py`
- Write all 22 tests before implementing the functions
- See [Test Strategy: Phase 2](#phase-2--payload-builder--grouping-tdd) for full test list

---

### Phase 3: Business Logic (`data_functions.py`)

**Goal**: Add the orchestrator function and refactor shared helpers for v2 reuse.

#### 3.1 Refactor: `_fetch_and_cache_simulation_drifts()`

Currently hardcodes `api/data/v1/accounts/{account_id}/drift/simulationStatus`. Refactor to accept the
API path as a parameter so the v2 endpoint can reuse the same fetch-and-cache logic.

**Before**:
```python
def _fetch_and_cache_simulation_drifts(console, payload, cache_key):
    ...
    api_url = f"{base_url}/api/data/v1/accounts/{account_id}/drift/simulationStatus"
    ...
```

**After**:
```python
def _fetch_and_cache_simulation_drifts(console, payload, cache_key, api_path=None):
    ...
    if api_path is None:
        api_path = f"/api/data/v1/accounts/{account_id}/drift/simulationStatus"
    api_url = f"{base_url}{api_path}"
    ...
```

**Backward compatible**: existing callers pass no `api_path` and get the v1 default.

#### 3.2 New Constant: `_VALID_TRANSITION_MODES`

```python
_VALID_TRANSITION_MODES = {"contains", "starts_and_ends"}
```

#### 3.3 New Function: `sb_get_security_control_drifts()`

Primary entry point — single function, two-phase via `drift_key` presence (matching existing pattern).

```python
def sb_get_security_control_drifts(
    console: str,
    security_control: str,
    window_start: int,
    window_end: int,
    transition_matching_mode: str,       # "contains" or "starts_and_ends"
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
    group_by: str = "transition",
    drift_key: str | None = None,
    page_number: int = 0,
) -> dict:
```

**Logic flow**:
1. **Validate** `transition_matching_mode` against `_VALID_TRANSITION_MODES`
2. **Validate** `drift_type` via existing `_validate_drift_type()`
3. **Validate** `security_control` via suggestions helper:
   - Call `get_suggestions_for_collection(console, "security_product")`
   - If `security_control` not in list, raise `ValueError` with the list of valid values
4. **Map** `transition_matching_mode`:
   - `"contains"` → `contains_transition=True, starts_and_ends_with_transition=False`
   - `"starts_and_ends"` → `contains_transition=False, starts_and_ends_with_transition=True`
5. **Build payload** via `build_security_control_drift_payload()`
6. **Build cache key**: `f"sc_drifts_{console}_{security_control}_{window_start}_{window_end}_..."`
7. **Fetch** via `_fetch_and_cache_simulation_drifts()` with v2 api_path:
   `f"/api/data/v2/accounts/{account_id}/drift/securityControl"`
8. **Group and paginate** using new `_group_and_paginate_sc_drifts()` helper

#### 3.4 New Function: `_group_and_paginate_sc_drifts()`

Similar to existing `_group_and_paginate_drifts()` but adapted for v2 boolean status model.

**Summary mode** (drift_key=None):
```python
{
    "security_control": "Microsoft Defender for Endpoint",
    "grouped_by": "transition",
    "total_drifts": 47,
    "total_groups": 5,
    "drift_groups": [
        {
            "drift_key": "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T",
            "count": 12,
            "description": "Gained prevention capability",
        },
        ...
    ],
    "applied_filters": {...},
    "hint_to_agent": "To see individual drift records, call this tool again with drift_key=..."
}
```

**Drill-down mode** (drift_key set):
```python
{
    "security_control": "Microsoft Defender for Endpoint",
    "drift_key": "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T",
    "description": "Gained prevention capability",
    "page_number": 0,
    "total_pages": 2,
    "total_drifts_in_group": 12,
    "drifts_in_page": [...],
    "applied_filters": {...},
    "hint_to_agent": "Next page: call with drift_key='...', page_number=1 | ..."
}
```

**Zero-results hint**: Reuse pattern from `_build_zero_results_hint()` but adapt the removable filters and
cross-tool references for the v2 context.

**Drill-down hint**: Include:
- Next page reference (if more pages)
- Cross-tool reference to `get_simulation_details` for investigation

Note: No `attack_summary` in drill-down (v2 response doesn't include `attackId`).
No `final_status_breakdown` (v2 uses boolean flags, not finalStatus strings).

**Tests** (TDD — write first): New test classes in `test_drift_tools.py`
- Write all 17 tests before implementing the functions
- See [Test Strategy: Phase 3](#phase-3--business-logic-tdd) for full test list

---

### Phase 4: MCP Tool Registration (`data_server.py`)

**Goal**: Register the new MCP tool with proper documentation and timestamp normalization.

#### 4.1 New Tool: `get_security_control_drifts`

```python
@self.mcp.tool(
    name="get_security_control_drifts",
    description="""Analyze capability transitions for a specific security control over time. \
Shows how a control's prevented/reported/logged/alerted capabilities changed within a time window.

TWO-PHASE USAGE:
  1. Call WITHOUT drift_key to get a grouped summary of all capability transitions with counts. \
Use this to understand the overall drift landscape for a security control.
  2. Call WITH drift_key='<key>' (e.g., 'P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T') and page_number \
to paginate through individual records in that group.

USE THIS WHEN: You need to understand how a specific security control's capabilities changed over \
time — e.g., did it gain/lose prevention? Did it start/stop alerting? Did detection degrade?

DON'T USE FOR:
  - Overall blocked/not-blocked posture view (use get_simulation_result_drifts).
  - Security control final status transitions like prevented->logged (use get_simulation_status_drifts).
  - Comparing two specific test runs (use get_test_drifts).

Parameters:
  console (required): SafeBreach console name.
  security_control (required): Security control name (e.g., 'Microsoft Defender for Endpoint'). \
Must match a known security product. If invalid, the error will list valid values.
  window_start (required): epoch ms/seconds or ISO 8601 string (e.g., '2026-03-01T00:00:00Z').
  window_end (required): epoch ms/seconds or ISO 8601 string.
  transition_matching_mode (required): How to match transitions. \
'contains' = sequence includes from->to at least once. \
'starts_and_ends' = first AND last statuses must equal from/to.
  from_prevented, from_reported, from_logged, from_alerted: \
Boolean filters for origin capability state. Omit to match any.
  to_prevented, to_reported, to_logged, to_alerted: \
Boolean filters for destination capability state. Omit to match any.
  drift_type: Filter by drift classification. Valid: 'improvement', 'regression', 'not_applicable'.
  earliest_search_time: How far back to search for baseline simulations. \
Epoch ms/seconds or ISO 8601 string. Defaults to 7 days before window_start.
  max_outside_window_executions: Max executions outside window to consider (integer).
  group_by: How to group results. 'transition' (default) groups by boolean capability changes. \
'drift_type' groups by Improvement/Regression.
  drift_key: Drill-down key from summary. Omit for grouped summary.
  page_number: Page number for drill-down mode (default 0, 10 records per page).
WARNING: This endpoint has no server-side pagination. Large time windows on busy consoles can be slow. \
Start with a narrow window (1-2 days) and widen only if needed."""
)
async def get_security_control_drifts_tool(
    console: str,
    security_control: str,
    window_start: str | int = None,
    window_end: str | int = None,
    transition_matching_mode: str = None,
    from_prevented: bool | None = None,
    from_reported: bool | None = None,
    from_logged: bool | None = None,
    from_alerted: bool | None = None,
    to_prevented: bool | None = None,
    to_reported: bool | None = None,
    to_logged: bool | None = None,
    to_alerted: bool | None = None,
    drift_type: str | None = None,
    earliest_search_time: str | int | None = None,
    max_outside_window_executions: int | None = None,
    group_by: str = "transition",
    drift_key: str | None = None,
    page_number: int = 0,
) -> dict:
    # Normalize timestamps (match existing pattern)
    window_start = normalize_timestamp(window_start)
    if window_start is None:
        raise ValueError("window_start: invalid or missing timestamp value")
    window_end = normalize_timestamp(window_end)
    if window_end is None:
        raise ValueError("window_end: invalid or missing timestamp value")
    if transition_matching_mode is None:
        raise ValueError(
            "transition_matching_mode is required. "
            "Valid values: 'contains', 'starts_and_ends'"
        )
    earliest_search_time = (
        normalize_timestamp(earliest_search_time)
        if earliest_search_time is not None else None
    )

    return sb_get_security_control_drifts(
        console=console,
        security_control=security_control,
        window_start=window_start,
        window_end=window_end,
        transition_matching_mode=transition_matching_mode,
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
        group_by=group_by,
        drift_key=drift_key,
        page_number=page_number,
    )
```

**Tests** (code-first — write after implementation): New test class in `test_drift_tools.py`
- Write 8 regression tests after the tool code is implemented
- See [Test Strategy: Phase 4](#phase-4--mcp-tool-registration-code-first) for full test list

---

### Phase 5: E2E Tests

**Goal**: Validate against the real `pentest01` environment using the automated E2E framework.

**Execution**: VS Code launch config `Run All E2E Tests (Default Console)` which runs
`.vscode/run_e2e_with_env.py` with `E2E_CONSOLE=pentest01`. Sources `.vscode/set_env.sh` for
API tokens automatically — zero manual setup, zero mocks.

**New E2E tests** in `test_drift_tools.py` (or separate file):
- Summary query for a known security control
- Drill-down into a transition group
- Both transition matching modes
- Filter by drift_type
- Boolean status filters (from/to)
- Invalid security control name → helpful error with valid values

**Decorators**: `@skip_e2e` + `@pytest.mark.e2e`

---

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/suggestions.py` | **CREATE** | Shared suggestions helper with caching |
| `safebreach_mcp_core/__init__.py` | EDIT | Export `get_suggestions_for_collection` |
| `safebreach_mcp_core/tests/test_suggestions.py` | **CREATE** | Unit tests for suggestions helper |
| `safebreach_mcp_data/data_types.py` | EDIT | Add `build_security_control_drift_payload`, `build_sc_drift_transition_key`, `group_sc_drift_records` |
| `safebreach_mcp_data/data_functions.py` | EDIT | Refactor `_fetch_and_cache_simulation_drifts` (add `api_path` param), add `sb_get_security_control_drifts`, `_group_and_paginate_sc_drifts` |
| `safebreach_mcp_data/data_server.py` | EDIT | Register `get_security_control_drifts` tool |
| `safebreach_mcp_data/tests/test_drift_tools.py` | EDIT | Add v2 test classes for all phases |

---

## Test Strategy

### Methodology

**TDD (test-first) for Phases 1–3**: These phases implement pure functions and I/O-with-mocks where
the contracts are fully defined upfront. Write failing tests first, then implement to make them pass.
This matches how SAF-28330 drift tests were built (see `test_drift_tools.py` Phase 1–3 structure).

**Code-first for Phase 4**: The MCP tool layer is a thin async wrapper (timestamp normalization +
delegation). Tests here are regression guards, not design drivers — write them after the tool code.

**Automated E2E for Phase 5**: Runs against `pentest01` via `.vscode/run_e2e_with_env.py` with
`E2E_CONSOLE=pentest01`. Zero mocks, zero manual setup. Sources `.vscode/set_env.sh` for API tokens
automatically. Written after unit tests pass to validate real API integration.

### Phase 1 — Suggestions Helper (TDD)

**File**: `safebreach_mcp_core/tests/test_suggestions.py`
**Approach**: Write all tests first. The contract is simple: console + collection → list of strings.

**Mock pattern** (same 4-mock stack as existing drift tests):
```python
@patch("safebreach_mcp_core.suggestions.requests.get")
@patch("safebreach_mcp_core.suggestions.get_secret_for_console", return_value="test-token")
@patch("safebreach_mcp_core.suggestions.get_api_base_url", return_value="https://demo.safebreach.com")
@patch("safebreach_mcp_core.suggestions.get_api_account_id", return_value="12345")
```

| Test | What it verifies |
|------|-----------------|
| `test_get_suggestions_success` | Calls API, parses response, returns `["key1", "key2"]` for valid collection |
| `test_get_suggestions_cache_hit` | Second call returns cached data; `requests.get` called only once |
| `test_get_suggestions_cache_miss_stores` | First call stores in cache; verify via `suggestions_cache.get()` |
| `test_get_suggestions_invalid_collection` | Unknown collection → `ValueError` listing available collection names |
| `test_get_suggestions_empty_collection` | Collection exists with `[]` entries → returns empty list |
| `test_get_suggestions_api_401` | 401 response → `ValueError` mentioning auth |
| `test_get_suggestions_api_timeout` | `requests.exceptions.Timeout` propagates |
| `test_get_suggestions_extracts_keys_only` | Items have `{"key": "...", "doc_count": N}` — only `key` values returned |

**~8 tests**, no manual sign-off.

### Phase 2 — Payload Builder & Grouping (TDD)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (new test classes)
**Approach**: Write all tests first. Pure functions with deterministic inputs/outputs — ideal TDD.
No mocks needed.

**2a. `TestBuildSecurityControlDriftPayload`**:

| Test | What it verifies |
|------|-----------------|
| `test_build_sc_payload_required_fields` | Output has `securityControl`, `windowStart`, `windowEnd`, `earliestSearchTime`, both transition booleans |
| `test_build_sc_payload_timestamps_converted` | Epoch ms → ISO-8601 UTC strings |
| `test_build_sc_payload_all_from_booleans` | `fromStatus: {prevented: T, reported: F, logged: T, alerted: F}` |
| `test_build_sc_payload_all_to_booleans` | Same for `toStatus` |
| `test_build_sc_payload_partial_from_booleans` | Only 2 of 4 → `fromStatus` has only those 2 keys |
| `test_build_sc_payload_no_from_booleans` | All None → no `fromStatus` key in payload |
| `test_build_sc_payload_no_to_booleans` | All None → no `toStatus` key in payload |
| `test_build_sc_payload_drift_type_mapping` | Parametrized: `"regression"` → `"Regression"`, etc. |
| `test_build_sc_payload_default_earliest_search_time` | None → 7 days before `window_start` |
| `test_build_sc_payload_explicit_earliest_search_time` | Explicit value overrides default |
| `test_build_sc_payload_max_outside_window` | Integer included as `maxOutsideWindowExecutions` |
| `test_build_sc_payload_max_outside_window_omitted` | None → key absent |

**2b. `TestBuildScDriftTransitionKey`**:

| Test | What it verifies |
|------|-----------------|
| `test_transition_key_all_true` | `P:T,R:T,L:T,A:T->P:T,R:T,L:T,A:T` |
| `test_transition_key_all_false` | `P:F,R:F,L:F,A:F->P:F,R:F,L:F,A:F` |
| `test_transition_key_mixed` | Specific combo produces correct compact key |
| `test_transition_key_single_change` | Only `prevented` flips — key reflects it |
| `test_transition_key_missing_field_defaults` | Missing `prevented` in `from` → defaults to `False` |

**2c. `TestGroupScDriftRecords`**:

| Test | What it verifies |
|------|-----------------|
| `test_group_by_transition_same_combo` | 3 identical boolean combos → 1 group, count=3 |
| `test_group_by_transition_different_combos` | Different combos → separate groups |
| `test_group_by_transition_sorted_by_count` | Groups sorted descending by count |
| `test_group_by_drift_type` | Groups by `driftType` (Improvement, Regression) |
| `test_group_by_drift_type_mixed` | 3 Improvement + 2 Regression → 2 groups |
| `test_group_empty_records` | `[]` → `[]` |
| `test_group_description_gained_prevention` | `from.prevented=false, to.prevented=true` → "gained prevention" |
| `test_group_description_lost_alerting` | `from.alerted=true, to.alerted=false` → "lost alerting" |
| `test_group_description_multi_change` | Multiple flags changed → description covers all |
| `test_group_preserves_original_records` | All original API fields intact in `drifts` list |

**~22 tests**, no manual sign-off.

### Phase 3 — Business Logic (TDD)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (new test classes)
**Approach**: Write tests first. Orchestrator tests need mocks for API + suggestions but follow
the exact `TestSbGetSimulationResultDrifts`/`TestSbGetSimulationStatusDrifts` pattern.

**3a. Refactor backward compatibility** (additions to existing `TestFetchAndCacheSimulationDrifts`):

| Test | What it verifies |
|------|-----------------|
| `test_fetch_v1_default_unchanged` | No `api_path` → URL contains `/v1/.../drift/simulationStatus` |
| `test_fetch_v2_custom_api_path` | `api_path="/api/data/v2/.../drift/securityControl"` → URL uses v2 |

**3b. `TestSbGetSecurityControlDrifts`**:

**Mock pattern** (5 patches):
```python
@patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
       return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
@patch("safebreach_mcp_data.data_functions.requests.post")
@patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
@patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
@patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
```

| Test | What it verifies |
|------|-----------------|
| `test_invalid_transition_mode` | `"invalid"` → `ValueError` listing `contains`, `starts_and_ends` |
| `test_invalid_drift_type` | `"unknown"` → `ValueError` (delegates to `_validate_drift_type`) |
| `test_invalid_security_control` | Not in suggestions → `ValueError` with list of valid names |
| `test_contains_mode_maps_correctly` | `"contains"` → payload has `containsTransition=true` |
| `test_starts_and_ends_mode_maps_correctly` | `"starts_and_ends"` → `startsAndEndsWithTransition=true` |
| `test_summary_mode` | No `drift_key` → response has `grouped_by`, `total_drifts`, `drift_groups` |
| `test_drill_down_mode` | `drift_key` set → `drifts_in_page`, `page_number`, `total_pages` |
| `test_drill_down_pagination` | 25 records → `total_pages=3`, page 0 has 10 records |
| `test_invalid_drift_key` | Unknown key → `ValueError` listing available keys |
| `test_out_of_range_page` | `page_number=99` → `ValueError` |
| `test_zero_results_hint` | 0 records → contextual `hint_to_agent` |
| `test_applied_filters` | Non-None filters appear in `applied_filters` dict |
| `test_cache_key_includes_all_params` | Key has console, security_control, timestamps, mode, booleans |
| `test_security_control_in_response` | Both summary and drill-down include `"security_control"` field |
| `test_no_attack_summary_in_drilldown` | Unlike v1, no `attack_summary` (v2 lacks `attackId`) |

**~17 tests**, no manual sign-off.

### Phase 4 — MCP Tool Registration (code-first)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (new test class)
**Approach**: Write tool code first, then add regression tests. The tool is a thin async wrapper
doing timestamp normalization + delegation — tests guard against regressions, not design.

| Test | What it verifies |
|------|-----------------|
| `test_tool_normalizes_iso_timestamp` | `"2026-03-01T00:00:00Z"` → epoch ms forwarded |
| `test_tool_normalizes_epoch_seconds` | `1709251200` → epoch ms |
| `test_tool_normalizes_epoch_ms` | `1709251200000` → passes through |
| `test_tool_missing_window_start` | `None` → `ValueError("window_start: invalid...")` |
| `test_tool_missing_window_end` | `None` → `ValueError("window_end: invalid...")` |
| `test_tool_missing_transition_mode` | `None` → `ValueError("transition_matching_mode is required...")` |
| `test_tool_normalizes_earliest_search_time` | ISO → epoch ms; `None` → passes as `None` |
| `test_tool_passes_all_params` | Mock `sb_get_security_control_drifts`, verify all 18 params forwarded |

**~8 tests**, low manual sign-off (docstring wording review only).

### Phase 5 — E2E Tests (automated, post-implementation)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (or separate file)
**Approach**: Written after all unit tests pass. Runs against `pentest01` via the automated
E2E framework (`.vscode/run_e2e_with_env.py`, `E2E_CONSOLE=pentest01`). Sources
`.vscode/set_env.sh` for API tokens automatically — zero mocks, zero manual setup.

**Decorators**: `@skip_e2e` + `@pytest.mark.e2e`

| Test | What it verifies |
|------|-----------------|
| `test_e2e_sc_drifts_summary` | Real API summary for known security control |
| `test_e2e_sc_drifts_drill_down` | Drill into first group from summary, verify paginated response |
| `test_e2e_sc_drifts_contains_mode` | `transition_matching_mode="contains"` returns valid results |
| `test_e2e_sc_drifts_starts_and_ends_mode` | `transition_matching_mode="starts_and_ends"` returns valid results |
| `test_e2e_sc_drifts_invalid_control` | Garbage name → `ValueError` listing real control names |
| `test_e2e_sc_drifts_with_drift_type_filter` | `drift_type="regression"` narrows results |

**~6 tests**, no manual sign-off.

### Test Summary

| Phase | # Tests | TDD? | Manual Sign-Off | Mock Complexity |
|-------|---------|------|-----------------|-----------------|
| 1. Suggestions helper | ~8 | **Yes** | None | 4-patch stack (requests.get) |
| 2. Payload/grouping | ~22 | **Yes** | None | None (pure functions) |
| 3. Business logic | ~17 | **Yes** | None | 5-patch stack (requests.post + suggestions) |
| 4. MCP tool | ~8 | No (code-first) | Low (docstring) | 1 patch (mock orchestrator) |
| 5. E2E | ~6 | No (post-impl) | None | None (real `pentest01` API) |
| **Total** | **~61** | | |

---

## Post-Implementation Refinements

### Refinement 1: `__list__` Discovery Mode

Added `security_control="__list__"` to enumerate available security controls with simulation counts.
Removed strict client-side validation (noisy `security_product` suggestions data includes usernames,
instance types). The v2 API returns `[]` for unknown controls, so soft guidance via zero-results hints
is preferred over hard validation errors.

**Response format**:
```python
{
    "security_controls": [
        {"name": "Microsoft Defender for Endpoint", "simulations": 500},
        {"name": "CrowdStrike Falcon", "simulations": 300},
    ],
    "total": 2,
    "hint_to_agent": "These are security product names from execution history..."
}
```

### Refinement 2: Drift Key Notation — Capability-List Format

**Problem**: The original `P:T,R:F,L:F,A:F->P:T,R:T,L:F,A:F` notation is cryptic and inconsistent
with the existing drift tools which use human-readable keys like `prevented-logged` and `fail-success`.

**Options analyzed**:
1. **Capability-list keys** — List active capabilities per side: `prevented->prevented,reported`
2. **Map to finalStatus names** — Reuse `prevented-logged` format. Loses boolean granularity.
3. **Group by drift_type only** — Use `regression`/`improvement`. Too coarse, loses transition detail.

**Selected: Option 1 (Capability-list keys)**. Preserves full boolean granularity (the unique value
of this tool) while being self-describing. The `->` arrow clearly separates from/to states.

**Format rules**:
- Each side lists comma-separated active (true) capability names: `prevented`, `reported`, `logged`, `alerted`
- `none` when all capabilities are false
- Arrow `->` separates from-state and to-state
- Examples:
  - `prevented->prevented,reported` — gained reporting
  - `prevented,reported,logged,alerted->none` — lost all capabilities
  - `none->prevented` — gained prevention from scratch
  - `prevented,reported->prevented,reported` — no change

**Files changed**: `data_types.py` (builder), `data_server.py` (docstring), `test_drift_tools.py` (assertions)

---

## Definition of Done

- [x] Suggestions helper created and tested
- [x] Payload builder handles all v2 params correctly
- [x] Transition key generation produces compact, readable keys
- [x] Grouping works for both transition and drift_type modes
- [x] Orchestrator validates all inputs with helpful errors
- [x] Security control validated against suggestions API
- [x] `_fetch_and_cache_simulation_drifts` refactored without breaking v1 callers
- [x] MCP tool registered with comprehensive docstring
- [x] All timestamp params accept ISO-8601 and epoch formats
- [x] Two-phase (summary/drill-down) pattern works correctly
- [x] Pagination with proper hints
- [x] Caching works with v2-specific cache keys
- [x] Zero-results smart hints adapted for v2 context
- [x] All unit tests passing
- [x] E2E tests passing
- [x] No breaking changes to existing drift tools
- [x] All cross-server tests passing (`716` tests)
- [x] `__list__` discovery mode with simulation counts
- [x] Capability-list drift key notation (replaces P:T/F notation)
