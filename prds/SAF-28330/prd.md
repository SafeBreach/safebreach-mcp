# PRD: Simulation Result and Status Drift Tools — SAF-28330

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Simulation Result and Status Drift Tools |
| **JIRA** | SAF-28330 |
| **Task Type** | Feature |
| **Purpose** | Enable time-window-based drift analysis via two new MCP tools |
| **Target Consumer** | AI agents (LLMs) consuming MCP tools for security posture analysis |
| **Key Benefits** | Time-window drift visibility, complementary to test-run-centric analysis, clear LLM tool selection |
| **Originating Request** | SAF-28330 — requested by Shahaf Raviv |

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-03-06 |
| **Owner** | Yossi Attas |
| **Current Phase** | All phases complete (1-12) |

---

## 2. Solution Description

### Chosen Solution: Shared Core with Validation Layer (Approach C)

Two specialized MCP tools split by the API's mutually exclusive filter modes, sharing a common internal
fetch/cache/paginate core but with distinct validation and parameter handling layers.

**Architecture:**
- `data_types.py` — `group_and_enrich_drift_records()` for grouping+enrichment,
  `build_drift_api_payload()` for request building
- `data_functions.py` — `_fetch_and_cache_simulation_drifts()` for API+cache,
  `_group_and_paginate_drifts()` for summary/drill-down response building,
  `sb_get_simulation_result_drifts()` and `sb_get_simulation_status_drifts()` as public entry points
- `data_server.py` — Two @mcp.tool() registrations with distinct docstrings and TWO-PHASE USAGE guidance

### Alternatives Considered

| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Approach A: Thin Wrappers | Single shared function, minimal wrappers | No clear validation layer, harder to test |
| Approach B: Fully Separate | Two independent implementations | Code duplication, inconsistency risk over time |
| Single unified tool | One tool with all filters | Mutually exclusive params confuse LLMs |
| Single tool + mode param | analysis_mode="result"\|"status" | Conditional params add complexity |

### Decision Rationale
Approach C provides clear separation of concerns (validation → fetch → paginate → enrich), each layer
testable independently, DRY where it matters (API call, caching, pagination), and distinct where it
matters (parameter validation, docstrings). Aligns with existing data server patterns.

---

## 3. Core Feature Components

### Component A: Drift Record Transformation (data_types.py)

**Purpose**: New functions to transform raw API drift records into enriched, grouped MCP-friendly format.

**Key Features**:
- `build_drift_api_payload(params)` — Constructs the POST request body for the drift API from MCP tool
  parameters. Handles epoch-to-ISO-8601 conversion for windowStart/windowEnd and look_back_time
  (→ earliestSearchTime), maps snake_case MCP params to camelCase API params, and validates filter
  combinations. When look_back_time is None, defaults to `window_start - 7 days`.
- `group_and_enrich_drift_records(records)` — Groups raw API records by their drift transition key
  (e.g., "prevented-logged"), enriches each group with metadata from `drifts_metadata.py`
  (security_impact, description, hint_to_llm). Enrichment appears once per group, not per record.
  Returns a list of drift group dicts, each containing the enrichment fields plus a `drifts` array
  of individual records (with full API detail: loggedBy, reportedBy, alertedBy, preventedBy arrays).

### Component B: Drift API Integration (data_functions.py)

**Purpose**: New business logic functions for fetching, caching, grouping, and paginating drift data.

**Key Features**:
- `_fetch_and_cache_simulation_drifts(console, payload, cache_key)` — Internal function that handles
  the HTTP POST to the drift API endpoint, caches the full response array, and returns raw records.
  Uses existing patterns: `get_api_base_url(console, 'data')`, `get_api_account_id(console)`,
  `get_secret_for_console(console)`, 120s timeout.
- `_group_and_paginate_drifts(records, page_number, drift_key, applied_filters)` — Internal function
  that groups records by drift transition type via `group_and_enrich_drift_records()`, then either:
  (a) if drift_key is None, returns the summary view (all groups with counts, no individual records),
  or (b) if drift_key is provided, paginates records within that specific group (PAGE_SIZE=10).
- `sb_get_simulation_result_drifts(...)` — Public function for result-mode drift analysis.
  Validates result-mode params (from_status, to_status must be FAIL/SUCCESS), builds payload via
  `build_drift_api_payload()`, delegates to shared core. Accepts optional drift_key for drill-down.
- `sb_get_simulation_status_drifts(...)` — Public function for final-status-mode drift analysis.
  Validates final-status params (from_final_status, to_final_status must be
  prevented/stopped/detected/logged/missed/inconsistent), builds payload, delegates to shared core.
  Accepts optional drift_key for drill-down.

### Component C: MCP Tool Registration (data_server.py)

**Purpose**: Expose both functions as MCP tools with comprehensive docstrings.

**Key Features**:
- `get_simulation_result_drifts` tool — Security posture lens with "USE THIS WHEN" / "DON'T USE FOR"
  guidance. Parameters: console, window_start, window_end, look_back_time (optional, defaults to
  7 days before window_start), drift_type, attack_id, attack_type, from_status, to_status,
  drift_key (optional, for drill-down into a specific group), page_number.
- `get_simulation_status_drifts` tool — Security control lens with distinct docstring guidance.
  Parameters: console, window_start, window_end, look_back_time (optional, defaults to 7 days
  before window_start), drift_type, attack_id, attack_type, from_final_status, to_final_status,
  drift_key (optional, for drill-down), page_number.
- **Two-phase response**: Without drift_key returns grouped summary (counts + enrichment per group).
  With drift_key returns paginated records for that specific group.
- Existing drift tool docstrings updated with cross-references to new tools.

---

## 4. API Endpoints and Integration

### Existing API to Consume

- **API Name**: Simulation Status Drift
- **URL**: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
- **Headers**: `Content-Type: application/json`, `x-apitoken: {apitoken}`
- **Request Payload**:
```json
{
  "windowStart": "2026-03-01T00:00:00.000Z",
  "windowEnd": "2026-03-04T00:00:00.000Z",
  "driftType": "Regression",
  "attackId": 1263,
  "attackType": "host",
  "fromStatus": "FAIL",
  "toStatus": "SUCCESS",
  "earliestSearchTime": "2026-02-01T00:00:00.000Z",
  "maxOutsideWindowExecutions": 10
}
```
- **Mutually Exclusive**: `fromStatus`/`toStatus` cannot be sent with `fromFinalStatus`/`toFinalStatus`
  (server returns 400)
- **Response Example** (single record from flat array):
```json
{
  "trackingId": "aabb0011ccdd2233eeff4455aabb6677",
  "attackId": 1263,
  "attackTypes": ["Legitimate Channel Exfiltration"],
  "from": {
    "simulationId": 3189641,
    "executionTime": "2026-02-28T15:55:22.037Z",
    "finalStatus": "logged",
    "status": "SUCCESS",
    "loggedBy": ["Microsoft Defender for Endpoint"],
    "reportedBy": [],
    "alertedBy": [],
    "preventedBy": []
  },
  "to": {
    "simulationId": 3286842,
    "executionTime": "2026-03-03T15:37:28.212Z",
    "finalStatus": "inconsistent",
    "status": "SUCCESS",
    "loggedBy": [],
    "reportedBy": [],
    "alertedBy": [],
    "preventedBy": ["system"]
  },
  "driftType": "NotApplicable"
}
```
- **Error Responses**:
  - 400: Mutual exclusion violation or >500K simulations in time window
  - 401: Invalid API token
  - Timeout: Large time windows may take >120s

---

## 6. Non-Functional Requirements

### Performance Requirements
- **Response Times**: API may return 10K+ records for 3-day windows; pagination keeps MCP response
  small (10 records per page)
- **500K Limit**: API rejects requests covering >500K simulations. Tool should return a clear error
  message guiding the user to narrow the time window.
- **Look-back Time**: The API's `earliestSearchTime` controls how far back the backend searches for
  baseline (pre-drift) simulations. Backend default is 30 days, which is excessive on high-load
  consoles. Exposed as `look_back_time` with a 7-day default (window_start - 7 days) for better
  performance. Users can increase for infrequently-run attacks or decrease for faster responses.
- **Caching**: Full API response cached (maxsize=3, TTL=600s) to avoid repeated large fetches during
  page navigation

### Technical Constraints
- **Epoch Input**: Tool accepts epoch timestamps in milliseconds (consistent with existing data server
  tools). Internally converts to ISO-8601 for the API.
- **Backward Compatibility**: No breaking changes to existing tools. Only additive: new functions,
  new cache, updated docstrings.
- **Existing Imports**: Must add new function imports to data_server.py and new type imports to
  data_functions.py.

---

## 7. Definition of Done

- [x] `get_simulation_result_drifts` tool exposed and functional with all filters
- [x] `get_simulation_status_drifts` tool exposed and functional with all filters
- [x] Two-phase response: summary mode (grouped counts) and drill-down mode (paginated records, PAGE_SIZE=10)
- [x] Epoch-to-ISO-8601 time conversion working correctly
- [x] Caching via SafeBreachCache (simulation_drifts, maxsize=3, TTL=600s)
- [x] Input validation: reject invalid status values, handle mutual exclusion
- [x] `look_back_time` parameter exposed with 7-day default, mapped to `earliestSearchTime` in API payload
- [x] Zero-results hint_to_agent with context-aware suggestions (filter relaxation, look_back_time extension, cross-tool)
- [x] Error handling: 400 (too many sims), 401 (auth), timeout with clear messages
- [x] Docstrings with "USE THIS WHEN" / "DON'T USE FOR" for LLM tool selection
- [x] Existing drift tool docstrings updated with cross-references
- [x] hint_to_agent in responses guiding to drill-down tools
- [x] Unit tests covering: all filter combos, pagination, errors, cache, enrichment
- [x] E2E smoke tests for basic API connectivity
- [x] Result drifts group by FAIL/SUCCESS (posture view), distinct from status drifts (Phase 9)
- [x] `driftType` field stripped from drift records to avoid LLM confusion (Phase 10)
- [x] `attack_summary` in drill-down responses for automatic pattern detection (Phase 11)
- [x] Test ID traceability hints in drill-down: simulationId → planRunId guidance (Phase 12)
- [x] Manual LLM tool selection tests signed off (Phase 7)

---

## 8. Testing Strategy

### Approach: TDD per Phase
Each implementation phase (1-4) includes its own unit tests written before the implementation code.
Tests are added incrementally to `safebreach_mcp_data/tests/test_drift_tools.py` as each phase
progresses. This ensures every function is test-covered at the point it is committed.

### Unit Testing
- **Framework**: pytest with unittest.mock
- **Scope**: All new functions in data_types.py, data_functions.py, data_server.py
- **Test File**: `safebreach_mcp_data/tests/test_drift_tools.py` (created in Phase 1, extended in 2-4)
- **Phase-to-test mapping**:
  - Phase 1: `build_drift_api_payload`, `group_and_enrich_drift_records`
  - Phase 2: `_fetch_and_cache_simulation_drifts`, `_group_and_paginate_drifts`
  - Phase 3: `sb_get_simulation_result_drifts`, `sb_get_simulation_status_drifts`
  - Phase 4: MCP tool registration and parameter pass-through
- **Mock Pattern**: Mock `get_secret_for_console`, `get_api_base_url`, `get_api_account_id`,
  `requests.post` following existing test conventions
- **Coverage Target**: Match existing data server test coverage level

### E2E Testing (Phase 5)
- **Scope**: Basic smoke test against live SafeBreach environment
- **Scenarios**: Summary mode + drill-down mode for both tools
- **Environment**: Uses `E2E_CONSOLE` env var, `@skip_e2e` + `@pytest.mark.e2e` decorators

---

## 9. Implementation Phases

**Approach: TDD (Test-Driven Development)**
Each phase follows: Write failing tests → Implement code → Verify tests pass → Commit.
Tests are co-located with their implementation, not deferred to a later phase.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Data Types + Tests | ✅ Done | 2026-03-05 | 5d03400 | |
| Phase 2: Core Functions + Tests | ✅ Done | 2026-03-05 | 5d03400 | |
| Phase 3: Public Functions + Tests | ✅ Done | 2026-03-05 | 5d03400 | |
| Phase 4: MCP Tool Registration + Tests | ✅ Done | 2026-03-05 | 5d03400 | |
| Phase 5: E2E Tests | ✅ Done | 2026-03-05 | 5d03400 | 4 E2E tests on pentest01 |
| Phase 6: Docstring Cross-References | ✅ Done | 2026-03-05 | 5d03400 | |
| Phase 7: Manual LLM Tool Selection Tests | ✅ Done | 2026-03-06 | - | Signed off by product owner |
| Phase 8: Add look_back_time + Zero-Results Hints | ✅ Done | 2026-03-06 | 5d03400 | |
| Phase 9: Fix Result Drifts Grouping | ✅ Done | 2026-03-06 | 6986726 | Result drifts group by FAIL/SUCCESS |
| Phase 10: Drop driftType Field | ✅ Done | 2026-03-06 | 6986726 | Stripped redundant field |
| Phase 11: Attack-Level Sub-Grouping in Drill-Down | ✅ Done | 2026-03-06 | 6986726 | attack_summary in drill-down |
| Phase 12: Test ID Traceability in Drift Records | ✅ Done | 2026-03-06 | 6986726 | Option A: improved hints |

### Phase 1: Data Types + Tests

**Semantic Change**: Add drift record transformation and API payload builder to data_types.py
with full unit test coverage

**Deliverables**:
- `build_drift_api_payload(params)` function
- `group_and_enrich_drift_records(records)` function
- Unit tests for both functions

**TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_drift_tools.py`:

**build_drift_api_payload tests**:
- Epoch milliseconds correctly converted to ISO-8601 UTC strings
- Only non-None filters included in payload
- drift_type values mapped correctly (case-insensitive: "regression" → "Regression")
- Result mode params (from_status/to_status) included, final status params excluded
- Status mode params (from_final_status/to_final_status) included, result params excluded
- attack_type string values passed through correctly

**group_and_enrich_drift_records tests**:
- Records with same drift transition grouped together
- Known drift type (e.g., "prevented-logged") enriched with correct security_impact and description
- Unknown drift type gets fallback values with security_impact="unknown"
- Groups sorted by count descending
- Empty records list returns empty groups list
- All original API fields preserved within group drifts arrays
- Mixed drift types produce multiple groups with correct counts

**TDD Step 2 — Implement** in `safebreach_mcp_data/data_types.py`:

`build_drift_api_payload(window_start, window_end, drift_type, attack_id, attack_type, from_status,
to_status, from_final_status, to_final_status)`:
- Input: MCP tool parameters as keyword arguments. window_start and window_end are epoch timestamps
  in milliseconds. All other params are optional strings.
- Processing: Convert epoch milliseconds to ISO-8601 UTC strings for windowStart and windowEnd
  (using `datetime.utcfromtimestamp(epoch_ms / 1000).strftime('%Y-%m-%dT%H:%M:%S.000Z')`).
  Map snake_case params to camelCase API params. Only include non-None values in the payload.
  Map drift_type values: "improvement" → "Improvement", "regression" → "Regression",
  "not_applicable" → "NotApplicable" (case-insensitive input).
  Map attack_type values using VALID_ATTACK_TYPES dict if numeric mapping needed.
- Output: Dict ready to be sent as JSON body to the API.

`group_and_enrich_drift_records(records)`:
- Input: List of raw drift record dicts from the API.
- Processing:
  1. For each record, derive a drift_key by combining the from/to final statuses as
     `{from.finalStatus}-{to.finalStatus}` (lowercase). Also derive a result-level key as
     `{from.status}-{to.status}` (lowercase, e.g., "success-fail").
  2. Group records into a dict keyed by drift_key.
  3. For each group, look up the drift_key in `drift_types_mapping` from drifts_metadata.py.
     If not found, try the result-level key as a secondary lookup. If still not found, create
     fallback values with security_impact="unknown" and a generated description.
  4. Build a list of group dicts, each containing: `drift_key`, `security_impact`, `description`,
     `hint_to_llm`, `count` (number of records in group), and `drifts` (the list of raw records
     with all original API fields preserved).
  5. Sort groups by count descending (most impactful groups first).
- Output: List of enriched group dicts.

**TDD Step 3 — Verify all tests pass.**

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Create | Unit tests for payload builder and grouping/enrichment |
| `safebreach_mcp_data/data_types.py` | Modify | Add `build_drift_api_payload()` and `group_and_enrich_drift_records()` |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`

**Git Commit**: `feat(data): add drift API payload builder and grouped enrichment with tests (SAF-28330)`

---

### Phase 2: Core Functions + Tests

**Semantic Change**: Add shared internal functions for API fetching with caching and summary/drill-down
response building to data_functions.py with full unit test coverage

**Deliverables**:
- `simulation_drifts_cache` instance
- `_fetch_and_cache_simulation_drifts(console, payload, cache_key)` function
- `_group_and_paginate_drifts(records, page_number, drift_key, applied_filters)` function
- Unit tests for both functions

**TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_drift_tools.py`:

**_fetch_and_cache_simulation_drifts tests**:
- Successful API call returns parsed records
- Cache hit returns cached data without API call
- Cache miss calls API and stores result
- 400 error raises ValueError with descriptive message
- 401 error raises ValueError with auth message
- Timeout handled correctly
- Invalid JSON response handled

**_group_and_paginate_drifts tests**:
- **Summary mode (drift_key=None)**: Returns all groups with counts but no individual records,
  hint_to_agent guides to drill-down with drift_key
- **Drill-down mode (drift_key provided)**: Page 0 returns first PAGE_SIZE records from that group,
  last page returns remainder, out-of-range page raises ValueError
- **Invalid drift_key**: Raises ValueError listing available keys
- Empty records list returns empty summary with total_drifts=0
- hint_to_agent includes next page hint when more pages available in drill-down mode
- hint_to_agent includes get_simulation_details reference for further investigation

**Mock Pattern**: Mock `get_secret_for_console`, `get_api_base_url`, `get_api_account_id`,
`requests.post`. Use setUp to clear `simulation_drifts_cache` before each test.

**TDD Step 2 — Implement** in `safebreach_mcp_data/data_functions.py`:

`simulation_drifts_cache`:
- Instantiate at module level alongside existing caches (after line 32 in data_functions.py):
  `simulation_drifts_cache = SafeBreachCache(name="simulation_drifts", maxsize=3, ttl=600)`

`_fetch_and_cache_simulation_drifts(console, payload, cache_key)`:
- Input: console name (str), payload dict (API request body), cache_key (str for cache lookup)
- Processing:
  1. Check if caching is enabled via `is_caching_enabled("data")`
  2. If enabled, attempt cache lookup with `simulation_drifts_cache.get(cache_key)`
  3. On cache miss: get API credentials via `get_secret_for_console(console)`, build URL via
     `get_api_base_url(console, 'data')` and `get_api_account_id(console)`, construct full endpoint
     as `{base_url}/api/data/v1/accounts/{account_id}/drift/simulationStatus`
  4. Make HTTP POST with headers `{"Content-Type": "application/json", "x-apitoken": apitoken}`,
     json=payload, timeout=120
  5. Handle errors: Check status code — 400 means too many simulations or invalid filters (extract
     error message from response body), 401 means auth failure, other errors via raise_for_status()
  6. Parse JSON response (the response is a flat array of drift records)
  7. If caching enabled, store result with `simulation_drifts_cache.set(cache_key, records)`
  8. Return the list of drift records
- Output: List of raw drift record dicts

`_group_and_paginate_drifts(records, page_number, drift_key, applied_filters)`:
- Input: List of raw drift records, page_number (int, 0-based), drift_key (str or None),
  applied_filters (dict of active filters)
- Processing:
  1. Call `group_and_enrich_drift_records(records)` from data_types to get enriched groups
  2. **Summary mode** (drift_key is None):
     - Return all groups but strip out the individual `drifts` array from each group (keep only
       drift_key, security_impact, description, hint_to_llm, count)
     - Include total_drifts (sum of all group counts), total_groups (number of groups)
     - hint_to_agent: "To see individual drift records for a specific group, call this tool again
       with drift_key='<key>' (e.g., drift_key='prevented-logged'). Use get_simulation_details
       with include_drift_info=True to investigate a specific simulation."
  3. **Drill-down mode** (drift_key is provided):
     - Find the matching group by drift_key. If not found, raise ValueError with available keys.
     - Paginate the group's `drifts` array with PAGE_SIZE=10
     - Validate page_number bounds (raise ValueError if out of range)
     - Return: drift_key, security_impact, description, hint_to_llm (once), page_number,
       total_pages, total_drifts_in_group, drifts_in_page (paginated records), applied_filters
     - hint_to_agent: pagination hint if more pages + drill-down tool reference
- Output: Summary or paginated drill-down response dict

**TDD Step 3 — Verify all tests pass.**

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add unit tests for fetch/cache and group/paginate |
| `safebreach_mcp_data/data_functions.py` | Modify | Add cache instance, `_fetch_and_cache_simulation_drifts()`, `_group_and_paginate_drifts()` |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`

**Git Commit**: `feat(data): add drift fetch/cache and group/paginate core with tests (SAF-28330)`

---

### Phase 3: Public Functions + Tests

**Semantic Change**: Add two public entry-point functions that validate mode-specific parameters
and delegate to the shared core, with full unit test coverage

**Deliverables**:
- `sb_get_simulation_result_drifts()` function
- `sb_get_simulation_status_drifts()` function
- Unit tests for both functions

**TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_drift_tools.py`:

**sb_get_simulation_result_drifts tests**:
- Valid FAIL/SUCCESS from_status/to_status accepted
- Invalid from_status raises ValueError
- Missing required params (console, window_start, window_end) raise ValueError
- All optional filters passed through correctly
- applied_filters metadata reflects actual filters used
- Summary mode (no drift_key): returns grouped summary with counts
- Drill-down mode (with drift_key): returns paginated records from specific group

**sb_get_simulation_status_drifts tests**:
- Valid final status values accepted (prevented, stopped, detected, logged, missed, inconsistent)
- Invalid from_final_status raises ValueError
- Same validation, summary, and drill-down tests as result drifts

**TDD Step 2 — Implement** in `safebreach_mcp_data/data_functions.py`:

`sb_get_simulation_result_drifts(console, window_start, window_end, drift_type, attack_id,
attack_type, from_status, to_status, drift_key, page_number)`:
- Input: console (str, required), window_start (int, required, epoch ms), window_end (int, required,
  epoch ms), drift_type (str, optional — "improvement"/"regression"/"not_applicable"),
  attack_id (int, optional), attack_type (str, optional), from_status (str, optional — "FAIL"/"SUCCESS"),
  to_status (str, optional — "FAIL"/"SUCCESS"), drift_key (str, optional — e.g., "fail-success"),
  page_number (int, default 0)
- Validation:
  1. console, window_start, window_end are required — raise ValueError if missing
  2. If from_status provided, validate it is one of ["FAIL", "SUCCESS"] (case-insensitive)
  3. If to_status provided, validate it is one of ["FAIL", "SUCCESS"] (case-insensitive)
  4. If drift_type provided, validate it is one of ["improvement", "regression", "not_applicable"]
  5. page_number is only relevant when drift_key is provided (ignored in summary mode)
- Processing:
  1. Call `build_drift_api_payload()` with all params (pass from_status/to_status, leave
     from_final_status/to_final_status as None)
  2. Build cache_key as `f"result_drifts_{console}_{window_start}_{window_end}_{drift_type}_{attack_id}_{attack_type}_{from_status}_{to_status}"`
  3. Call `_fetch_and_cache_simulation_drifts(console, payload, cache_key)`
  4. Build applied_filters dict from non-None params
  5. Call `_group_and_paginate_drifts(records, page_number, drift_key, applied_filters)`
  6. Return summary (if drift_key is None) or paginated drill-down (if drift_key provided)
- Output: Summary response or paginated drill-down response

`sb_get_simulation_status_drifts(console, window_start, window_end, drift_type, attack_id,
attack_type, from_final_status, to_final_status, drift_key, page_number)`:
- Same structure as above but:
  - Validates from_final_status/to_final_status against
    ["prevented", "stopped", "detected", "logged", "missed", "inconsistent"] (case-insensitive)
  - Passes from_final_status/to_final_status to payload builder, leaves from_status/to_status as None
  - Cache key prefix is "status_drifts_" instead of "result_drifts_"

**TDD Step 3 — Verify all tests pass.**

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add unit tests for public result/status drift functions |
| `safebreach_mcp_data/data_functions.py` | Modify | Add `sb_get_simulation_result_drifts()` and `sb_get_simulation_status_drifts()` |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`

**Git Commit**: `feat(data): add simulation result and status drift functions with tests (SAF-28330)`

---

### Phase 4: MCP Tool Registration + Tests

**Semantic Change**: Register both new functions as MCP tools with comprehensive docstrings,
with tool registration and parameter pass-through tests

**Deliverables**:
- `get_simulation_result_drifts` MCP tool
- `get_simulation_status_drifts` MCP tool
- Updated imports in data_server.py
- Tool registration tests

**TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_drift_tools.py`:

**MCP tool registration tests**:
- Both tools registered and callable
- Parameters passed through correctly to underlying functions
- drift_key parameter accepted and forwarded

**TDD Step 2 — Implement** in `safebreach_mcp_data/data_server.py`:

Update the import block at the top of data_server.py to include `sb_get_simulation_result_drifts`
and `sb_get_simulation_status_drifts` from data_functions.

Register `get_simulation_result_drifts` tool:
- Docstring should include:
  - First line: "Returns time-window-based simulation result drift analysis showing transitions between
    blocked (FAIL) and not-blocked (SUCCESS) states."
  - "TWO-PHASE USAGE: Call without drift_key to get a grouped summary of all drift types with counts.
    Then call again with drift_key='<key>' to paginate through individual records in a specific group."
  - "USE THIS WHEN: You need to analyze how simulation RESULTS (blocked vs not-blocked) changed over a
    time period across all tests. This provides a security POSTURE view — did attacks that were previously
    blocked become unblocked, or vice versa?"
  - "DON'T USE FOR: Comparing two specific test runs (use get_test_drifts instead). Filtering drifted
    simulations within a single test (use get_test_simulations with drifted_only=True). Getting drift
    details for a single simulation (use get_simulation_details with include_drift_info=True)."
  - Parameter descriptions with types and valid values
  - Note about epoch milliseconds and convert_datetime_to_epoch tool
- Async wrapper function with all parameters including drift_key, delegates to
  `sb_get_simulation_result_drifts()`

Register `get_simulation_status_drifts` tool:
- Similar docstring structure but:
  - First line: "Returns time-window-based simulation status drift analysis showing transitions between
    security control final statuses (prevented, stopped, detected, logged, missed, inconsistent)."
  - Same "TWO-PHASE USAGE" guidance
  - "USE THIS WHEN: You need to analyze how security CONTROLS responded differently over time. This
    provides a security CONTROL view — did the detection method change? Did prevention degrade to
    just detection?"
  - Same "DON'T USE FOR" cross-references
  - Parameter descriptions for from_final_status/to_final_status with valid values list

**TDD Step 3 — Verify all tests pass.**

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add MCP tool registration tests |
| `safebreach_mcp_data/data_server.py` | Modify | Add imports and two @mcp.tool() registrations |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`

**Git Commit**: `feat(data): register simulation drift MCP tools with LLM guidance and tests (SAF-28330)`

---

### Phase 5: E2E Tests

**Semantic Change**: Add end-to-end smoke tests for both drift tools against a live environment

**Deliverables**:
- E2E test class with smoke tests for both tools

**Implementation Details**:

Add E2E tests to `safebreach_mcp_data/tests/test_drift_tools.py`.

**Test scenarios**:
1. Call `sb_get_simulation_result_drifts` without drift_key (summary mode), verify response has
   expected keys (total_drifts, total_groups, drift_groups with drift_key/security_impact/count)
2. Call `sb_get_simulation_status_drifts` without drift_key, verify same summary response structure
3. Verify drill-down: if any group has count > 0, call again with that group's drift_key and verify
   paginated response with page_number, total_pages, total_drifts_in_group, drifts_in_page
4. Verify enrichment: check that groups in summary contain security_impact and description fields

**Decorators**: `@skip_e2e` AND `@pytest.mark.e2e` on each test method.
**Environment**: Uses `E2E_CONSOLE` env var for target console.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add E2E smoke tests |

**Test Plan**: Run `source .vscode/set_env.sh && uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "e2e"`

**Git Commit**: `test(data): add E2E smoke tests for simulation drift tools (SAF-28330)`

---

### Phase 6: Docstring Cross-References

**Semantic Change**: Update existing drift tool docstrings with cross-references to new tools

**Deliverables**:
- Updated docstring for `get_test_drifts` tool
- Updated docstrings for `get_test_simulations` (drifted_only mention) and
  `get_simulation_details` (include_drift_info mention)

**Implementation Details**:

Update `get_test_drifts` docstring in data_server.py to add:
"For time-window-based drift analysis across all tests (not comparing two specific test runs),
use get_simulation_result_drifts or get_simulation_status_drifts instead."

Update `get_test_simulations` docstring to add a note near the drifted_only parameter:
"For broader drift analysis across a time window (not limited to a single test), see
get_simulation_result_drifts and get_simulation_status_drifts."

Update `get_simulation_details` docstring to add near include_drift_info:
"For time-window-based drift trends, see get_simulation_result_drifts and
get_simulation_status_drifts."

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_server.py` | Modify | Update existing tool docstrings with cross-references |

**Test Plan**: Verify docstrings render correctly by inspecting tool descriptions. Run existing tests
to ensure no regressions.

**Git Commit**: `docs(data): add cross-references between drift tools (SAF-28330)`

---

### Phase 7: Manual LLM Tool Selection Tests

**Semantic Change**: Validate that LLM agents select the correct drift tool based on natural language
prompts — verifies docstring effectiveness for tool selection

**Deliverables**:
- Execute 10 manual test scenarios from `prds/SAF-28330/manual-tests.md`
- Fill in results tracking table
- Sign-off with at least 9/10 pass rate

**Implementation Details**:

Connect an LLM agent to the data server MCP tools and run each test prompt from the manual test
file. The tests cover 5 categories:

1. **Correct tool selection** (Tests 1-5): Each prompt targets a specific drift tool — verify the
   agent picks the right one among `get_simulation_result_drifts`, `get_simulation_status_drifts`,
   `get_test_drifts`, `get_test_simulations(drifted_only)`, `get_test_simulation_details(drift_info)`.
2. **Two-phase usage** (Tests 6, 10): Verify the agent follows summary → drill-down → pagination
   flow as guided by docstrings and hint_to_agent.
3. **Ambiguous prompts** (Test 7): Verify the agent picks a reasonable tool when the prompt is broad.
4. **Filter pass-through** (Tests 8, 9): Verify correct parameters are extracted from prompts.

If any test consistently fails, the corresponding docstring needs revision before sign-off.

**Test file**: `prds/SAF-28330/manual-tests.md`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `prds/SAF-28330/manual-tests.md` | Modify | Fill in results tracking table and sign-off |

**Test Plan**: Manual execution — no automated tests

**Git Commit**: `test(data): complete manual LLM tool selection validation (SAF-28330)`

---

### Phase 8: Add look_back_time + Zero-Results Hints

**Semantic Change**: Expose the API's `earliestSearchTime` as `look_back_time` with a 7-day
default, and add smart `hint_to_agent` guidance when the API returns zero results

**Motivation**:
1. **look_back_time**: The backend defaults `earliestSearchTime` to 30 days, which causes slow
   responses on high-load consoles. A 7-day default reduces search scope while covering most
   attack cadences. Users can override for infrequently-run attacks.
2. **Zero-results hints**: When the API returns 0 drifts, the calling LLM agent has no guidance
   on what to try next. Smart hints based on API response time and active filters help the agent
   self-correct without user intervention.

**Deliverables**:
- `look_back_time` parameter threaded through all layers
- Default computation: `window_start - 7 * 86_400_000` ms (7 days)
- `earliestSearchTime` always sent in API payload
- Zero-results `hint_to_agent` with context-aware suggestions
- Updated tests and docstrings

#### Part A: look_back_time Parameter

**TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_drift_tools.py`:

**build_drift_api_payload tests** (extend existing TestBuildDriftApiPayload):
- Default look_back_time: when None, payload contains `earliestSearchTime` set to 7 days before
  window_start (converted to ISO-8601)
- Explicit look_back_time: when provided as epoch ms, payload contains `earliestSearchTime`
  matching that value (converted to ISO-8601)
- `earliestSearchTime` is always present in payload output (never omitted)

**sb_get_simulation_result_drifts / sb_get_simulation_status_drifts tests** (extend existing):
- look_back_time parameter accepted and passed through to payload builder
- Default look_back_time (None) produces correct default in API payload
- Explicit look_back_time overrides the default
- look_back_time included in cache key (different values produce different cache entries)

**MCP tool registration tests** (extend existing):
- Both tools accept look_back_time parameter

**TDD Step 2 — Implement**:

**`data_types.py` — `build_drift_api_payload()`**:
- Add `look_back_time: Optional[int] = None` parameter
- If None, compute default: `window_start - 7 * 86_400_000`
- Convert the resolved value to ISO-8601 and always include as `"earliestSearchTime"` in the payload

**`data_functions.py`**:
- Add `look_back_time: Optional[int] = None` parameter to `_fetch_and_cache_simulation_drifts()`,
  `sb_get_simulation_result_drifts()`, and `sb_get_simulation_status_drifts()`
- Include `look_back_time` in cache key strings for both public functions
- Pass through to `build_drift_api_payload()`

**`data_server.py`** — both tool registrations:
- Add `look_back_time: int = None` parameter to both tool wrapper functions
- Add docstring for the parameter: "How far back (epoch ms) to search for baseline simulations
  before the drift window. Defaults to 7 days before window_start. Increase for attacks that run
  infrequently (e.g., monthly). Decrease for faster responses on busy consoles."
- Pass through to underlying functions

#### Part B: Zero-Results Smart Hints

**Design**: When `_group_and_paginate_drifts` receives 0 records, it returns a response with
`total_drifts: 0` and a `hint_to_agent` containing context-aware suggestions. The hint logic
uses two inputs: the API call elapsed time (already tracked in `_fetch_and_cache_simulation_drifts`)
and the set of active filters.

**Hint decision tree** (evaluated in order):

1. **Active status/drift_type filters exist** (regardless of duration):
   "No drifts matched the current filters. Try removing [list specific active filters] to check
   if any drifts exist in this time window, then narrow down."

2. **Fast response (< 30s) + no active filters**:
   "No drifts found. The API responded quickly, suggesting a small dataset. Consider extending
   look_back_time — the current value covers N days before window_start. Attacks that run
   infrequently (e.g., monthly) may have baselines outside this range. Try 14 or 30 days.
   Alternatively, use get_test_drifts with a specific test ID for a targeted run-to-run
   comparison."

3. **Slow response (>= 30s) + no active filters**:
   "No drifts found despite a large dataset (API took Xs). Extending the search window would
   be slow. Consider: (a) trying a different or narrower time window, (b) filtering by
   attack_id or attack_type to focus the search, (c) using get_test_drifts with a specific
   test ID for a targeted comparison."

**Data flow**: `_fetch_and_cache_simulation_drifts` already logs elapsed time. It will return
the elapsed time alongside the records (as a tuple or by storing it). The public functions
(`sb_get_simulation_result_drifts` / `sb_get_simulation_status_drifts`) pass the elapsed time
and the applied_filters dict to `_group_and_paginate_drifts`, which uses them only when
records are empty.

**TDD Step 1 — Write failing tests**:

**_group_and_paginate_drifts tests** (extend existing):
- 0 records + active from_status filter → hint mentions removing the filter
- 0 records + active drift_type filter → hint mentions removing drift_type
- 0 records + fast elapsed (10s) + no filters → hint mentions extending look_back_time
- 0 records + slow elapsed (60s) + no filters → hint mentions narrower window / different filters
- 0 records + hint always includes get_test_drifts cross-reference
- Non-zero records → no zero-results hint (normal summary/drill-down behavior unchanged)

**sb_get_simulation_result_drifts / sb_get_simulation_status_drifts tests** (extend existing):
- Verify elapsed_seconds is passed through to pagination layer
- Verify zero-results response includes hint_to_agent

**TDD Step 2 — Implement**:

**`data_functions.py` — `_fetch_and_cache_simulation_drifts()`**:
- Return elapsed time alongside records: change return to `(records, elapsed_seconds)` tuple
- Update callers to unpack the tuple

**`data_functions.py` — `_group_and_paginate_drifts()`**:
- Add `elapsed_seconds: float = 0.0` parameter
- When records are empty, build hint_to_agent using the decision tree above
- Compute effective look_back_time days for the hint message:
  `(window_start - effective_look_back_time) / 86_400_000`
- Identify active filters from applied_filters dict (exclude console, window_start, window_end,
  look_back_time from the "removable filters" list)

**`data_functions.py` — `sb_get_simulation_result_drifts()` / `sb_get_simulation_status_drifts()`**:
- Unpack `(records, elapsed_seconds)` from fetch function
- Pass elapsed_seconds to `_group_and_paginate_drifts()`

**TDD Step 3 — Verify all tests pass.**

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add tests for look_back_time and zero-results hints |
| `safebreach_mcp_data/data_types.py` | Modify | Add look_back_time to `build_drift_api_payload()` |
| `safebreach_mcp_data/data_functions.py` | Modify | Thread look_back_time, return elapsed time, add zero-results hint logic |
| `safebreach_mcp_data/data_server.py` | Modify | Add look_back_time param to both MCP tool registrations |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`
then full cross-server regression.

**Git Commit**: `feat(data): add look_back_time and zero-results smart hints (SAF-28330)`

---

### Phase 9: Fix Result Drifts Grouping

**Semantic Change**: Make `get_simulation_result_drifts` group by result status (FAIL/SUCCESS)
instead of final status, so the two drift tools produce genuinely different views

**Source**: Claude Desktop LLM evaluation — both tools returned identical results when called
without filters because `group_and_enrich_drift_records()` always groups by
`from.finalStatus - to.finalStatus`.

**Problem**: The result drifts tool is supposed to provide a **posture-level** view
(blocked vs not-blocked), but it currently shows the same fine-grained finalStatus groups
as the status drifts tool. When called without filters, the two tools are indistinguishable.

**Root Cause**: `group_and_enrich_drift_records()` in `data_types.py:691-694` unconditionally
derives `drift_key` from `from.finalStatus - to.finalStatus`. There is no grouping mode
parameter.

**Fix**:

1. Add a `group_by` parameter to `group_and_enrich_drift_records()`:
   - `group_by="final_status"` (default) — current behavior, used by status drifts
   - `group_by="result_status"` — groups by `from.status - to.status` (FAIL/SUCCESS),
     used by result drifts
2. Thread `group_by` through `_group_and_paginate_drifts()` to `group_and_enrich_drift_records()`
3. `sb_get_simulation_result_drifts()` passes `group_by="result_status"`
4. `sb_get_simulation_status_drifts()` passes `group_by="final_status"` (or omits for default)

**Expected Outcome**: Result drifts produce 2-4 coarse groups (`fail-success`, `success-fail`,
etc.) as a posture summary. Status drifts keep the fine-grained finalStatus groups
(`prevented-logged`, `detected-missed`, etc.). The two tools become genuinely complementary.

**Drill-down behavior**: When drilling into a result drifts group (e.g., `fail-success`), the
records will contain mixed finalStatus transitions underneath (e.g., `prevented-logged` and
`stopped-missed` both map to `fail-success`). To give instant visibility, drill-down responses
for result drifts include a `final_status_breakdown` field — a dict of
`{finalStatus_transition: count}` computed from the **full group** (not just the current page).
Example: `{"prevented-logged": 3, "stopped-missed": 2}`. The drill-down hint guides the LLM to
`get_simulation_status_drifts` for finer granularity when needed.

**TDD Step 1 — Write failing tests**:
- `group_and_enrich_drift_records` with `group_by="result_status"` groups by `from.status`
- Result drifts summary produces coarse groups (fail-success, success-fail)
- Status drifts summary produces fine-grained groups (prevented-logged, etc.) — unchanged
- Same raw records, different grouping → different group counts and keys
- Metadata lookup works for result-level keys (fail-success, success-fail already in metadata)
- Result drifts drill-down contains `final_status_breakdown` field
- `final_status_breakdown` reflects the full group, not just the current page
- Status drifts drill-down does NOT include `final_status_breakdown`

**TDD Step 2 — Implement**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_types.py` | Modify | Add `group_by` param to `group_and_enrich_drift_records()` |
| `safebreach_mcp_data/data_functions.py` | Modify | Thread `group_by`, add `final_status_breakdown` to result drifts drill-down |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add grouping mode and breakdown tests |

**Test Plan**: `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`
then cross-server regression.

**Git Commit**: `fix(data): result drifts group by FAIL/SUCCESS instead of finalStatus (SAF-28330)`

---

### Phase 10: Drop driftType Field from Drift Records

**Semantic Change**: Remove the raw API `driftType` field from drift records to eliminate
LLM confusion with our authoritative `security_impact` enrichment

**Source**: Claude Desktop LLM evaluation — observed `driftType: NotApplicable` alongside
`security_impact: negative` on the same drift group, creating apparent contradiction.

**Problem**: The raw API `driftType` field (Improvement/Regression/NotApplicable) can appear
to contradict our enrichment `security_impact` field (positive/negative/neutral). Our
enrichment derives `security_impact` from domain-expert metadata based on the actual status
transition — it is strictly more informative than the API's classification. `driftType` has
3 values mapping to: Improvement→positive, Regression→negative, NotApplicable→cases we
can definitively classify. The field is redundant and confusing.

**Fix**: In `group_and_enrich_drift_records()`, strip the `driftType` key from each raw
record in the `drifts` array. One line: `record.pop("driftType", None)`.

**TDD Step 1 — Write failing tests**:
- Raw records in `drifts` array do NOT contain `driftType` key
- `security_impact` remains present and unchanged on each group
- All other raw API fields preserved (trackingId, attackId, from, to, etc.)

**TDD Step 2 — Implement**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_types.py` | Modify | Strip `driftType` from records in enrichment |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add field removal tests, update existing tests that assert on `driftType` |

**Test Plan**: `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`
then cross-server regression.

**Git Commit**: `fix(data): drop redundant driftType field from drift records (SAF-28330)`

---

### Phase 11: Attack-Level Sub-Grouping in Drill-Down

**Semantic Change**: Add an `attack_summary` to drill-down responses showing which attacks
contribute to each drift group, enabling automatic pattern detection

**Source**: Claude Desktop LLM evaluation — the LLM had to manually scan paginated records
to notice that "all 5 regressions are attack 3546". No automatic pattern aggregation exists.

**Problem**: In drill-down mode, individual drift records are paginated but there is no
aggregation showing which attacks are most affected. The LLM must infer patterns across
multiple pages of 10 records, which is error-prone and context-expensive.

**Fix**:

In `_group_and_paginate_drifts()` drill-down mode, add an `attack_summary` field to the
response: a list of `{attack_id, attack_types, count}` dicts sorted by count descending.
Computed from the **full group** (not just the current page), so the LLM gets the complete
picture regardless of which page it's viewing.

**Example output** (inside a drill-down response):
```json
"attack_summary": [
    {"attack_id": 3546, "attack_types": ["Remote Exploitation"], "count": 5},
    {"attack_id": 1263, "attack_types": ["Legitimate Channel Exfiltration"], "count": 2}
]
```

**TDD Step 1 — Write failing tests**:
- Drill-down response contains `attack_summary` field
- `attack_summary` sorted by count descending
- `attack_summary` reflects the full group, not just the current page
- Summary mode (no drill-down) does NOT include `attack_summary`

**TDD Step 2 — Implement**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_functions.py` | Modify | Add `attack_summary` to drill-down response |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add attack summary tests |

**Test Plan**: `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`
then cross-server regression.

**Git Commit**: `feat(data): add attack_summary to drift drill-down responses (SAF-28330)`

---

### Phase 12: Test ID Traceability in Drift Records

**Semantic Change**: Improve drift drill-down hints so LLMs can trace drifts back to their
parent test runs without guesswork

**Source**: Claude Desktop LLM evaluation — drift records contain `simulationId` but no
`planRunId`/`testId`. Tracing a drift to its parent test requires calling
`get_simulation_details` per simulation (N+1 problem).

**Problem**: The drift API returns `from.simulationId` and `to.simulationId` but no reference
to the parent test run. To follow the recommended investigation path
(`get_security_controls_events`, `get_test_details`), the LLM needs the test ID, which
requires a separate lookup per simulation.

**Chosen Approach: Improved Hints (Option A)**

Enhance `hint_to_llm` in drill-down mode to explicitly guide the agent through the
workaround: *"To trace this drift to its parent test, call get_simulation_details with
simulationId={from.simulationId} — the response includes the test ID (planRunId) for deeper
investigation via get_test_details."*

This is zero-cost, keeps the tool fast, and the LLM rarely needs to trace *all* drifts —
it typically picks the 1-2 most interesting ones to investigate.

**TDD Step 1 — Write failing tests**:
- Drill-down `hint_to_llm` mentions `get_simulation_details` with `simulationId`
- Drill-down `hint_to_llm` mentions `planRunId` and `get_test_details`
- Hint references specific simulationId values from the first record on the page

**TDD Step 2 — Implement**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_functions.py` | Modify | Enhance drill-down hint with traceability guidance |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Modify | Add traceability hint tests |

**Test Plan**: `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -m "not e2e"`
then cross-server regression.

**Git Commit**: `feat(data): add test ID traceability hints to drift drill-down (SAF-28330)`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| API returns 10K+ records causing slow enrichment | Medium | Enrichment is O(n) dict lookup — fast. Pagination limits response size. |
| 500K simulation limit exceeded by users | Medium | Clear error message guiding user to narrow time window |
| Cache key collisions between similar queries | Low | Include all filter params in cache key string |
| drifts_metadata.py missing new drift type combinations | Low | Fallback to "unknown" security_impact with generated description |

### Assumptions
- The drift API endpoint is stable and will not change its response format
- Existing drifts_metadata.py covers the most common drift type transitions
- Epoch milliseconds input is consistent with how other data server tools accept timestamps

---

## 11. Future Enhancements

- **Native ISO date support (separate JIRA ticket)**: All data server tools currently require
  epoch millisecond timestamps, forcing a pre-flight `convert_datetime_to_epoch` call for every
  time-filtered query. Accepting ISO-8601 strings natively would reduce tool-call overhead by
  ~2 calls per analysis session. This is a cross-cutting concern affecting all data server tools
  (`get_tests_history`, `get_test_simulations`, drift tools, etc.) and should be addressed via
  a dedicated JIRA ticket outside SAF-28330.
- **Drift trend aggregation**: Summary endpoint showing drift counts over time (daily/weekly trends)
- **Drift alerting**: Threshold-based alerts when regression count exceeds a configurable limit
- **Export functionality**: Export drift records to CSV/JSON for external analysis

---

## 12. Executive Summary

- **Issue**: SafeBreach MCP lacks time-window-based drift analysis tools; existing tools are
  test-run-centric only
- **What Will Be Built**: Two new MCP tools (`get_simulation_result_drifts` and
  `get_simulation_status_drifts`) exposing the SafeBreach drift API with full filtering, client-side
  pagination, caching, and drift metadata enrichment
- **Key Technical Decisions**: Shared core with validation layer (Approach C), single shared cache,
  grouped response with summary-first pagination for LLM context efficiency, drift metadata enrichment
  once per group (not per record), epoch input with ISO-8601 conversion
- **Business Value**: Enables AI agents to perform comprehensive security posture analysis across
  time windows, complementing existing test-run comparisons with a broader analytical lens

---

## 13. LLM Evaluation Findings

**Date**: 2026-03-06
**Evaluator**: Claude Desktop (Sonnet 4) connected to drift tools via MCP
**Console**: demo03
**Scenario**: "Analyze drift trends over the past week"

### Findings Summary

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | Both drift tools return identical results (same grouping by finalStatus) | Bug | Phase 9 |
| 2 | `driftType` field redundant and confusing alongside `security_impact` | Medium | Phase 10 |
| 3 | No automatic pattern detection by attack in drill-down | Medium | Phase 11 |
| 4 | Missing test ID traceability in drift records | Medium | Phase 12 |
| 5 | Epoch-only timestamps add pre-flight overhead | Low (drift) | Separate JIRA ticket |
| 6 | No console discovery tool | Low (drift) | Dropped — out of scope |

### Key Positive Feedback
- Two-phase summary/drill-down pattern well-suited for agentic workflows
- `hint_to_llm` and `hint_to_agent` fields praised as "exactly the right kind of guidance"
- `security_impact` field valued for triage ordering
- Tool docstrings clearly distinguished the two tools' intended use cases

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-03-04 18:30 | PRD created — initial draft |
| 2026-03-05 | Redesigned response format: grouped by drift transition type with summary-first pagination (Approach 3) |
| 2026-03-05 | Restructured phases to TDD approach: tests co-located with implementation in each phase (7→6 phases) |
| 2026-03-05 | Added Phase 7: Manual LLM tool selection tests with 10 scenarios in manual-tests.md |
| 2026-03-06 | Added Phase 8: look_back_time parameter (earliestSearchTime) with 7-day default for performance |
| 2026-03-06 | Extended Phase 8: zero-results smart hints with duration-based and filter-aware logic |
| 2026-03-06 | Added Phases 9-12 from Claude Desktop drift tool evaluation (Section 13) |
| 2026-03-06 | Noted epoch timestamp enhancement for separate JIRA ticket in Future Enhancements |
| 2026-03-06 | Phases 9-12 implemented, all 12 phases complete. 89 drift tests, 637 cross-server. PRD marked Complete. |
