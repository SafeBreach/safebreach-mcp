# SAF-28582: Fix full simulation logs error for empty dataObj.data

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Fix full simulation logs error for empty dataObj.data — SAF-28582 |
| **Task Type** | Bug fix |
| **Purpose** | Fix two bugs in `get_full_simulation_logs`: cache-before-validation and unhandled empty data |
| **Target Consumer** | Internal — AI agents using SafeBreach MCP Data Server |
| **Key Benefits** | Graceful handling of empty logs, correct caching behavior, improved agent experience |
| **Originating Request** | [SAF-28582](https://safebreach.atlassian.net/browse/SAF-28582) |

During staging pressure testing (2026-02-24), the Data MCP server raised `ValueError("Response missing
dataObj.data structure")` when fetching full simulation logs for simulation 3213805 / test
1771853252399.2. The simulation had status `INTERNAL_FAIL` and the API returned HTTP 200 with valid
metadata but `dataObj.data = [[]]` (empty execution logs). Note: `INTERNAL_FAIL` does not inherently
mean empty logs — some internally-failed simulations may still have partial logs. The fix adds a safe
check for empty `dataObj.data` regardless of simulation status. Two bugs were discovered:

1. **Cache-before-validation**: The raw API response is cached for 300 seconds before the code discovers
   it has empty data, causing repeated failures on every subsequent call.
2. **Unhandled empty data**: The mapping function raises `ValueError` instead of returning a graceful
   response, propagating an exception to the MCP agent.

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-02-24 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution: Validate-Then-Cache (Approach A)

Move validation and transformation **before** caching, aligning with how all other data functions
(`_get_all_findings_from_cache_or_api`, `_get_all_tests_from_cache_or_api`, etc.) handle caching.
Handle empty `dataObj.data` as a valid state that returns a response with `logs_available: False`
instead of raising an exception.

### Alternatives Considered

| Approach | Description | Why Not Chosen |
|----------|-------------|----------------|
| **B: Validate-After-Fetch** | Add validation between fetch and cache, keep raw caching | Inconsistent with other data functions; cache hit still requires re-transformation |
| **C: Validation Wrapper** | Separate validation function before Approach A pattern | Over-engineering — one extra function layer with no real benefit |

### Decision Rationale

Approach A is the simplest fix that aligns with the established codebase pattern. All other data server
cache functions already validate/transform before caching. This fix brings `full_simulation_logs` into
alignment with zero new abstractions.

---

## 3. Core Feature Components

### Component A: Graceful Empty Data Handling (`data_types.py`)

**Purpose**: Modify `get_full_simulation_logs_mapping()` to handle empty `dataObj.data` as a valid
state instead of raising `ValueError`.

**Key changes**:
- When `dataObj.data` is empty (`[[]]`, `[]`, or missing), return a valid response dict with all
  available metadata (simulation_id, test_id, status, attack_info) but `target: None`,
  `attacker: None`, and two new fields: `logs_available: False` and `logs_status` with an
  explanatory message.
- Existing behavior for non-empty data remains unchanged.

### Component B: Validate-Then-Cache Pattern (`data_functions.py`)

**Purpose**: Restructure `_get_full_simulation_logs_from_cache_or_api()` to transform data before
caching (matching other data functions), and simplify `sb_get_full_simulation_logs()` accordingly.

**Key changes**:
- Move the `get_full_simulation_logs_mapping()` call from `sb_get_full_simulation_logs()` into
  `_get_full_simulation_logs_from_cache_or_api()`, after API fetch and before cache set.
- Cache the **transformed** result instead of the raw API response.
- Simplify `sb_get_full_simulation_logs()` to return the already-transformed result directly.
- Remove the `from .data_types import get_full_simulation_logs_mapping` import from
  `sb_get_full_simulation_logs()` and place it in `_get_full_simulation_logs_from_cache_or_api()`.

### Component C: MCP Tool Response Formatting (`data_server.py`)

**Purpose**: Ensure the MCP tool handler gracefully presents the `logs_available: False` case to agents.

**Key changes**:
- No structural change needed — the tool already returns the dict from `sb_get_full_simulation_logs()`.
- The response will now include `logs_available` and `logs_status` fields, which agents can interpret.
- Update tool description to document the new fields and the `logs_available: False` case.

---

## 4. API Endpoints and Integration

### Existing API Consumed

| Field | Value |
|-------|-------|
| **API Name** | SafeBreach Execution History Results |
| **URL** | `GET /api/data/v1/accounts/{account_id}/executionsHistoryResults/{simulation_id}?runId={test_id}` |
| **Headers** | `x-apitoken`, `Content-Type: application/json` |

**Known response variant (empty logs)**:
```json
{
  "id": 3213805,
  "status": "INTERNAL_FAIL",
  "moveName": "Email 'Azure token collector' Bash script as a ZIP attachment",
  "planRunId": "1771853252399.2",
  "dataObj": { "data": [[]] },
  "attackerNodeId": "...",
  "targetNodeId": "..."
}
```

No new APIs are created by this fix.

---

## 6. Non-Functional Requirements

### Technical Constraints

- **Backward Compatibility**: The response dict gains two new fields (`logs_available`, `logs_status`).
  Existing consumers that don't check these fields are unaffected. Consumers that previously caught
  `ValueError` will now receive a valid dict instead — this is the intended behavioral change.
- **Cache Behavior Change**: Cache now stores transformed dicts instead of raw API responses. Since the
  cache has a 300-second TTL and maxsize of 2, this transition is seamless — no migration needed.

### Performance Requirements

- No measurable performance impact. Transformation happens once per cache miss (same as before);
  cache hits now skip transformation entirely (slight improvement).

---

## 7. Definition of Done

- [ ] `get_full_simulation_logs_mapping()` handles empty `dataObj.data` gracefully (returns dict, no
  exception)
- [ ] Response includes `logs_available: False` and `logs_status` message for empty data
- [ ] Response includes all available metadata (simulation_id, test_id, status, attack_info) even when
  logs are empty
- [ ] `_get_full_simulation_logs_from_cache_or_api()` caches transformed data, not raw response
- [ ] Cache only stores validated/transformed responses (invalid responses never cached)
- [ ] `sb_get_full_simulation_logs()` simplified to return already-transformed result
- [ ] All 161 existing data server unit tests pass
- [ ] New unit tests cover empty data, missing dataObj, cache-after-transform, and cache-hit paths
- [ ] Cross-server test suite (all servers) passes
- [ ] Temporary E2E test file (`test_e2e_saf28582.py`) removed before merge

---

## 8. Testing Strategy

### Unit Testing

**Scope**: `safebreach_mcp_data/tests/test_data_types.py` and `safebreach_mcp_data/tests/test_data_functions.py`

**data_types.py tests** (new test class `TestFullSimulationLogsEmptyData`):
- `test_empty_data_array_returns_graceful_response` — Input: `{"dataObj": {"data": [[]]}, "id": 123, ...}` →
  Returns dict with `logs_available: False`
- `test_missing_data_obj_returns_graceful_response` — Input: `{}` → Returns dict with `logs_available: False`
- `test_missing_data_key_returns_graceful_response` — Input: `{"dataObj": {}}` → Returns dict with
  `logs_available: False`
- `test_empty_data_preserves_metadata` — Verify simulation_id, test_id, status, attack_info are populated
  from available API fields
- `test_empty_data_sets_target_and_attacker_none` — Verify `target: None` and `attacker: None`

**data_functions.py tests** (extend existing cache tests):
- `test_cache_stores_transformed_not_raw` — After cache miss, verify cached value is transformed dict
  (has `logs_available` key), not raw API response (has `dataObj` key)
- `test_cache_hit_returns_transformed_directly` — Verify cache hit skips API call and returns
  transformed dict
- `test_empty_data_response_is_cached` — Verify that graceful empty-data response IS cached (valid
  transformed response)
- `test_sb_get_full_simulation_logs_returns_dict_on_empty_data` — Verify no exception raised, returns
  dict with `logs_available: False`

**Coverage target**: Maintain or improve existing coverage.

### E2E Testing (Temporary)

- 4 existing E2E tests in `test_e2e_saf28582.py` confirm the current broken behavior.
- After fix: update test assertions to verify graceful response instead of `ValueError`.
- Remove `test_e2e_saf28582.py` entirely before merge (SSH tunnel dependency).

---

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Graceful empty data handling | ⏳ Pending | - | - | data_types.py |
| Phase 2: Validate-then-cache pattern | ⏳ Pending | - | - | data_functions.py |
| Phase 3: Update MCP tool description | ⏳ Pending | - | - | data_server.py |
| Phase 4: Cleanup | ⏳ Pending | - | - | Remove temp E2E tests |

### Phase 1: Graceful Empty Data Handling

**Semantic change**: `get_full_simulation_logs_mapping()` returns a valid response for empty data
instead of raising `ValueError`.

**Deliverables**: Modified mapping function + new unit tests.

**Implementation details**:

1. In `get_full_simulation_logs_mapping()` (`data_types.py`), replace the `raise ValueError` block
   (lines 470-471) with an early return that builds a valid response dict.
2. The early-return dict should use the same field structure as the normal response:
   - `simulation_id`: from `api_response.get('id', '')`, cast to string
   - `test_id`: from `api_response.get('planRunId', '')`
   - `run_id`: from `api_response.get('runId', '')`
   - `execution_times`: same extraction logic as normal path (startTime, endTime, etc.)
   - `status`: same extraction (overall, final_status, security_action)
   - `attack_info`: same extraction (move_id, move_name, etc.)
   - `target`: `None`
   - `attacker`: `None`
   - `logs_available`: `False` (new field)
   - `logs_status`: `"No execution logs available for this simulation"` (new field)
3. For the normal (non-empty) path, add `logs_available: True` and `logs_status: None` to the return
   dict at the end of the function, so both paths return the same schema.
4. Extract the metadata-building logic (execution_times, status, attack_info) into a helper
   `_build_response_metadata(api_response)` to avoid duplication between the empty and normal paths.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_types.py` | Modify `get_full_simulation_logs_mapping()`: replace ValueError with graceful return; add `logs_available`/`logs_status` fields; extract `_build_response_metadata()` helper |
| `safebreach_mcp_data/tests/test_data_types.py` | Add `TestFullSimulationLogsEmptyData` class with 5 test cases |

**Test plan**:
- Run `uv run pytest safebreach_mcp_data/tests/test_data_types.py -v -m "not e2e"` — all tests pass
- Verify new tests cover empty `[[]]`, missing `dataObj`, missing `data` key, metadata preservation,
  and `target`/`attacker` are `None`

**Git commit**: `fix(data): handle empty dataObj.data gracefully in full simulation logs mapping (SAF-28582)`

---

### Phase 2: Validate-Then-Cache Pattern

**Semantic change**: Move transformation before caching in the cache-or-API function; simplify the
public entry point.

**Deliverables**: Restructured cache function + updated entry point + cache unit tests.

**Implementation details**:

1. In `_get_full_simulation_logs_from_cache_or_api()` (`data_functions.py`):
   - After `_fetch_full_simulation_logs_from_api()` returns raw data, call
     `get_full_simulation_logs_mapping(raw_data)` to transform it.
   - Cache the **transformed** result (not raw), then return it.
   - Add the `from .data_types import get_full_simulation_logs_mapping` import at the top of the
     function (or at module level).
   - Update log messages: change "Cached full simulation logs" to include a note about transformed data.

2. In `sb_get_full_simulation_logs()` (`data_functions.py`):
   - Remove the `from .data_types import get_full_simulation_logs_mapping` import.
   - Remove the `result = get_full_simulation_logs_mapping(api_response)` line.
   - The function now simply returns the result from `_get_full_simulation_logs_from_cache_or_api()`
     directly (it's already transformed).

3. Update docstrings in both functions to reflect the new data flow.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Restructure `_get_full_simulation_logs_from_cache_or_api()` to transform before cache; simplify `sb_get_full_simulation_logs()` |
| `safebreach_mcp_data/tests/test_data_functions.py` | Add cache-stores-transformed, cache-hit-returns-transformed, empty-data-is-cached tests |

**Test plan**:
- Run `uv run pytest safebreach_mcp_data/tests/test_data_functions.py -v -m "not e2e"` — all tests pass
- Run `uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"` — all 161+ tests pass
- Verify new tests confirm: cache stores transformed dict (not raw), cache hit returns without API call,
  empty-data graceful response IS cached

**Git commit**: `fix(data): validate-then-cache pattern for full simulation logs (SAF-28582)`

---

### Phase 3: Update MCP Tool Description

**Semantic change**: Update the MCP tool description to document the new `logs_available` and
`logs_status` fields.

**Deliverables**: Updated tool description string.

**Implementation details**:

1. In `data_server.py`, update the `get_full_simulation_logs` tool description to mention:
   - New fields `logs_available` (bool) and `logs_status` (string or null) in the response.
   - When `logs_available` is `False`, `target` and `attacker` are `None`, and `logs_status` contains
     an explanation (e.g., simulation had `INTERNAL_FAIL` status).
   - All metadata fields (simulation_id, test_id, status, attack_info) are always present regardless
     of `logs_available`.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_server.py` | Update `get_full_simulation_logs` tool description string |

**Test plan**:
- Run full cross-server test suite:
  `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -v -m "not e2e"`

**Git commit**: `docs(data): update get_full_simulation_logs tool description for empty logs handling (SAF-28582)`

---

### Phase 4: Cleanup

**Semantic change**: Remove temporary E2E test file before merge.

**Deliverables**: Deleted temp file, final verification.

**Implementation details**:

1. Delete `safebreach_mcp_data/tests/test_e2e_saf28582.py`.
2. Run full test suite to confirm no regressions.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/tests/test_e2e_saf28582.py` | Delete (temporary E2E, SSH tunnel dependency) |

**Test plan**:
- Run cross-server test suite:
  `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -v -m "not e2e"`
- Verify all tests pass with no references to removed file.

**Git commit**: `chore: remove temporary SAF-28582 E2E tests`

---

## 10. Risks and Assumptions

| Risk | Impact | Mitigation |
|------|--------|------------|
| Other callers depend on `ValueError` being raised for empty data | Medium | No known callers catch this specifically; the MCP tool handler simply propagates the return value |
| Existing unit test mocks may assert on raw response caching | Low | Update mock assertions to expect transformed data in cache |
| `logs_available` field breaks consumers expecting exact schema | Low | New field is additive; no existing field is removed or renamed |

### Assumptions

- `INTERNAL_FAIL` status does NOT inherently mean empty logs — some `INTERNAL_FAIL` simulations may
  have partial logs. The fix handles empty `dataObj.data` regardless of simulation status.
- No other code paths depend on `_get_full_simulation_logs_from_cache_or_api()` returning raw API
  responses (investigation confirmed this is only called from `sb_get_full_simulation_logs()`).

---

## 12. Executive Summary

| Field | Value |
|-------|-------|
| **Issue** | `get_full_simulation_logs` raises unhandled `ValueError` and caches invalid data when API returns empty execution logs |
| **What Will Be Built** | Graceful empty-data handling + validate-then-cache pattern alignment |
| **Key Technical Decision** | Align with other data functions by caching transformed data, not raw API responses |
| **Scope** | 3 source files modified (data_types.py, data_functions.py, data_server.py), ~8 new unit tests |
| **Business Value** | Eliminates agent-facing errors for simulations with INTERNAL_FAIL status; prevents 5-minute cache poisoning |
