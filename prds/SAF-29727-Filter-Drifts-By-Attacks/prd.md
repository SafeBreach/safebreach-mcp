# Add Attack Filters to Drift Tools — SAF-29727

## 1. Overview

| Field | Value |
|-------|-------|
| **Task Type** | Feature |
| **Purpose** | Enable MCP drift tool consumers to filter drift results by attack properties |
| **Target Consumer** | Internal — AI agents and MCP tool consumers |
| **Key Benefits** | 1) Natural-language queries like "drifts for attack X" 2) No post-processing needed 3) Consistent filtering across all drift tools |
| **Business Alignment** | Improves SafeBreach MCP drift analysis usability for security posture assessment |
| **Originating Request** | [SAF-29727](https://safebreach.atlassian.net/browse/SAF-29727) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-04-09 11:30 |
| **Owner** | Yossi Attas |
| **Current Phase** | Complete |

## 2. Solution Description

### Chosen Solution

**Approach A: Separate builders, extended independently.**

Add `attack_name` to the existing `build_drift_api_payload()` used by result/status drift tools,
and add all three attack params (`attack_id`, `attack_type`, `attack_name`) to the separate
`build_security_control_drift_payload()` for SC drift tools.

Expose missing parameters in MCP tool signatures and add `attack_name` to response `attack_summary`.

### Alternatives Considered

**Approach B: Unified builder** — Merge both payload builders into one function.
- Pros: DRY, single source of truth
- Cons: Mixes v1/v2 API concerns, boolean status fields (SC) vs enum statuses (simulation),
  high diff, increased coupling
- Rejected: complexity outweighs DRY benefit for 3 trivial params

**Approach C: Shared attack filter helper** — Extract `_build_attack_filters()` called by both builders.
- Pros: DRY for attack filters without coupling builders
- Cons: Premature abstraction for 3 simple field mappings
- Rejected: over-engineering for current scope; can adopt later if attack filter logic grows

### Decision Rationale

Approach A minimizes diff, preserves the existing v1/v2 API separation, and keeps each builder
focused on its API contract. The duplication is 3 optional params with trivial mapping logic.

### Implementation Order

**Tool-by-tool with pure TDD and elephant carpaccio** (thinnest vertical slices):
1. Result drifts (smallest gap — only `attack_name` + `attack_type` exposure)
2. Status drifts (mirrors result drifts pattern)
3. Security control drifts (largest gap — all params at all layers)
4. Response enrichment (add `attack_name` to `attack_summary`)

## 3. Core Feature Components

### Component A: Simulation Result Drift Attack Filters

**Purpose**: Expose `attack_type` and add `attack_name` filtering to the existing
`get_simulation_result_drifts` MCP tool.

**Key Features**:
- Add `attack_name` parameter to `build_drift_api_payload()` mapped to `"attackName"` in API payload
- Add `attack_name` parameter to `sb_get_simulation_result_drifts()` function signature
- Expose `attack_type` (already in function, hidden from MCP tool) in tool registration
- Expose `attack_name` in tool registration
- All new params are optional; behavior unchanged when no filters are used

### Component B: Simulation Status Drift Attack Filters

**Purpose**: Mirror Component A for the `get_simulation_status_drifts` MCP tool.

**Key Features**:
- Add `attack_name` parameter to `sb_get_simulation_status_drifts()` function signature
- Expose `attack_type` and `attack_name` in tool registration
- Reuses the same `build_drift_api_payload()` already extended in Component A

### Component C: Security Control Drift Attack Filters

**Purpose**: Add all three attack filter params to the `get_security_control_drifts` MCP tool
(currently has zero attack filtering).

**Key Features**:
- Add `attack_id`, `attack_type`, `attack_name` to `build_security_control_drift_payload()`
- Add all three params to `sb_get_security_control_drifts()` function signature
- Expose all three in MCP tool registration
- Include attack params in cache key for correct cache invalidation

### Component D: Response Enrichment

**Purpose**: Add `attack_name` to the `attack_summary` field in drift drill-down responses.

**Key Features**:
- Extract `attackName` from drift records alongside existing `attackId` and `attackTypes`
- Include `attack_name` in each `attack_summary` entry
- Applies to both simulation and SC drift response enrichment

## 4. API Endpoints and Integration

### Existing APIs Consumed

**Simulation Status Drift API** (used by result + status drift tools):
- **URL**: `POST /api/data/v1/accounts/{account_id}/drift/simulationStatus`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **New request body params**:
  - `attackName` (string, optional) — match_phrase filter on `moveName` field
  - `attackId` (integer, optional) — already supported
  - `attackType` (string, optional) — already supported
- **Response drift pair fields**: `attackId` (int), `attackName` (string), `attackTypes` (string[])

**Security Control Drift API** (used by SC drift tool):
- **URL**: `POST /api/data/v2/accounts/{account_id}/drift/securityControl`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **New request body params**:
  - `attackId` (integer, optional) — exact match filter on `moveId`
  - `attackName` (string, optional) — match_phrase filter on `moveName`
  - `attackType` (string, optional) — exact match filter on `Attack_Type.value.keyword`
- **Response drift pair fields**: `attackId` (int), `attackName` (string), `attackTypes` (string[])

**Backend PR**: [data#2799](https://bitbucket.org/safebreach/data/pull-requests/2799) (MERGED)

## 7. Definition of Done

- [x] `get_simulation_result_drifts` accepts and passes `attack_type` and `attack_name` to the API
- [x] `get_simulation_status_drifts` accepts and passes `attack_type` and `attack_name` to the API
- [x] `get_security_control_drifts` accepts and passes `attack_id`, `attack_type`, `attack_name` to the API
- [x] `attack_summary` includes `attack_name` field in drill-down responses
- [x] All new params are optional — behavior unchanged when no filters used
- [x] Cache keys include new attack filter params for correct invalidation
- [x] Unit tests cover all new params at payload builder, function, and MCP tool layers
- [x] All existing tests continue to pass
- [x] Tool descriptions updated to document new attack filter parameters
- [ ] Product reviewed — user can query "drifts for CrowdStrike against attack X last 7 days"

## 8. Testing Strategy

### Unit Testing

**Framework**: pytest (existing)

**Test file**: `safebreach_mcp_data/tests/test_drift_tools.py`

**Key scenarios per tool**:
1. Payload builder includes `attackName` when `attack_name` is provided
2. Payload builder omits `attackName` when `attack_name` is None
3. Function passes `attack_name` through to payload builder
4. MCP tool passes `attack_type` and `attack_name` to function
5. Cache key includes new attack filter params
6. `attack_summary` includes `attack_name` from drift records

**For SC drift tool additionally**:
7. Payload builder includes `attackId`, `attackType`, `attackName`
8. Function passes all three through to payload builder
9. MCP tool exposes all three params

**Coverage target**: Maintain existing coverage level; all new code paths tested.

### Integration Testing

**Scope**: Existing multi-server integration tests should continue to pass.
No new integration tests needed — attack filtering is a backend API concern,
and the MCP layer is a pass-through.

### E2E Testing

Deferred — requires live SafeBreach environment with attack filter support deployed.

## 9. Implementation Phases

Each phase is a **thin vertical slice through ALL layers** (types → functions → server → tests),
delivering one E2E testable capability. After each phase, a user can immediately test the new
filtering on the affected tool.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Result drifts — full attack filtering (attack_id + attack_type + attack_name) | ✅ Complete | 2026-04-09 | - | 7 tests, 162 pass |
| Phase 2: Status drifts — full attack filtering (attack_id + attack_type + attack_name) | ✅ Complete | 2026-04-09 | - | 3 unit + 1 E2E |
| Phase 3: SC drifts — full attack filtering (attack_id + attack_type + attack_name) | ✅ Complete | 2026-04-09 | - | 7 unit + 1 E2E |
| Phase 4: Response enrichment — attack_name in attack_summary | ✅ Complete | 2026-04-09 | - | 1 unit, verified on staging |
| Phase 5: Documentation update | ✅ Complete | 2026-04-09 | - | CLAUDE.md + tool descriptions |
| Phase 6: attack_type discovery mode + zero-results hints | ✅ Complete | 2026-04-12 | - | 3 unit + 1 E2E |

---

### Phase 1: Result drifts — full attack filtering

**E2E Deliverable**: `get_simulation_result_drifts` tool supports full attack filtering:
`attack_id` (already working), `attack_type` (expose hidden param), and `attack_name` (new).
User can call the tool with any combination of these filters and get filtered drift results.

**Vertical slice** — changes across ALL layers in one phase:

**TDD Steps**:

1. **RED — Payload builder tests**:
   Write `test_build_payload_attack_name_filter` that calls `build_drift_api_payload()` with
   `attack_name="Malware Drop"` and asserts `"attackName": "Malware Drop"` is in the returned dict.
   Write `test_build_payload_attack_name_none` that asserts `"attackName"` is absent when None.

2. **GREEN — Payload builder implementation**:
   Add `attack_name: Optional[str] = None` parameter to `build_drift_api_payload()` in data_types.py.
   Add conditional inclusion: if not None, add `"attackName": attack_name` to the payload dict.

3. **RED — Function layer tests**:
   Write test that calls `sb_get_simulation_result_drifts()` with `attack_name="Test Attack"`
   and verifies it appears in the API payload (mock HTTP call), in `applied_filters`, and in cache key.

4. **GREEN — Function layer implementation**:
   Add `attack_name: Optional[str] = None` to `sb_get_simulation_result_drifts()` signature.
   Pass `attack_name=attack_name` to `build_drift_api_payload()` call.
   Include in cache key string and in `applied_filters`.

5. **RED — MCP tool tests**:
   Write test verifying `get_simulation_result_drifts_tool()` accepts `attack_type` and `attack_name`
   and passes both to `sb_get_simulation_result_drifts()`.

6. **GREEN — MCP tool implementation**:
   Add `attack_type: Optional[str] = None` and `attack_name: Optional[str] = None` to
   `get_simulation_result_drifts_tool()` signature. Pass both through. Update tool description.

7. **VERIFY**: Run full result drifts test suite:
   `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -k "result_drift"`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_types.py` | Add `attack_name` to `build_drift_api_payload()` |
| `safebreach_mcp_data/data_functions.py` | Add `attack_name` to `sb_get_simulation_result_drifts()` |
| `safebreach_mcp_data/data_server.py` | Expose `attack_type` + `attack_name` in result drifts tool |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Tests for all three layers |

**Git Commit**: `feat(data): add attack filtering to simulation result drifts (SAF-29727)`

---

### Phase 2: Status drifts — full attack filtering

**E2E Deliverable**: `get_simulation_status_drifts` tool supports full attack filtering:
`attack_id` (already working), `attack_type` (expose hidden param), and `attack_name` (new).
User can filter status drifts by any attack property.

**Vertical slice** — function + server layers (types already done in Phase 1):

**TDD Steps**:

1. **RED — Function layer tests**:
   Write test that calls `sb_get_simulation_status_drifts()` with `attack_name="Test Attack"`
   and verifies pass-through to payload builder, inclusion in `applied_filters` and cache key.

2. **GREEN — Function layer implementation**:
   Add `attack_name: Optional[str] = None` to `sb_get_simulation_status_drifts()` signature.
   Pass to `build_drift_api_payload()`. Include in cache key and `applied_filters`.

3. **RED — MCP tool tests**:
   Write test verifying `get_simulation_status_drifts_tool()` accepts `attack_type` and `attack_name`
   and passes both to `sb_get_simulation_status_drifts()`.

4. **GREEN — MCP tool implementation**:
   Add `attack_type: Optional[str] = None` and `attack_name: Optional[str] = None` to
   `get_simulation_status_drifts_tool()`. Pass both through. Update tool description.

5. **VERIFY**: Run full status drifts test suite:
   `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -k "status_drift"`

**Note**: `build_drift_api_payload()` already has `attack_name` from Phase 1 — no types change needed.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add `attack_name` to `sb_get_simulation_status_drifts()` |
| `safebreach_mcp_data/data_server.py` | Expose `attack_type` + `attack_name` in status drifts tool |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Tests for function + MCP tool layers |

**Git Commit**: `feat(data): add attack filtering to simulation status drifts (SAF-29727)`

---

### Phase 3: SC drifts — full attack filtering

**E2E Deliverable**: `get_security_control_drifts` tool now accepts `attack_id`, `attack_type`,
and `attack_name` filters. User can filter SC drifts by all attack properties.

**Vertical slice** — changes across ALL layers (SC has no attack support at any level):

**TDD Steps**:

1. **RED — Payload builder tests**:
   Write tests for `build_security_control_drift_payload()`:
   - Test with `attack_id=123` → asserts `"attackId": 123` in payload
   - Test with `attack_type="exfil"` → asserts `"attackType": "exfil"` in payload
   - Test with `attack_name="Malware Drop"` → asserts `"attackName": "Malware Drop"` in payload
   - Test with all None → asserts none of the attack keys present

2. **GREEN — Payload builder implementation**:
   Add `attack_id: Optional[int] = None`, `attack_type: Optional[str] = None`,
   `attack_name: Optional[str] = None` to `build_security_control_drift_payload()`.
   Add conditional inclusion for each: if not None, add camelCase key to payload.

3. **RED — Function layer tests**:
   Write test calling `sb_get_security_control_drifts()` with all three attack params.
   Verify they appear in API payload, cache key, and `applied_filters`.

4. **GREEN — Function layer implementation**:
   Add all three params to `sb_get_security_control_drifts()` signature.
   Pass to `build_security_control_drift_payload()`. Include in cache key and `applied_filters`.

5. **RED — MCP tool tests**:
   Write test verifying `get_security_control_drifts_tool()` accepts all three attack params
   and passes them to `sb_get_security_control_drifts()`.

6. **GREEN — MCP tool implementation**:
   Add all three params to `get_security_control_drifts_tool()`. Pass through.
   Update tool description.

7. **VERIFY**: Run full SC drifts test suite:
   `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -k "security_control_drift"`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_types.py` | Add 3 attack params to `build_security_control_drift_payload()` |
| `safebreach_mcp_data/data_functions.py` | Add 3 attack params to `sb_get_security_control_drifts()` |
| `safebreach_mcp_data/data_server.py` | Expose 3 attack params in SC drifts tool |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Tests for all three layers |

**Git Commit**: `feat(data): add attack filtering to security control drifts (SAF-29727)`

---

### Phase 4: Response enrichment — `attack_name` in `attack_summary`

**E2E Deliverable**: All drift tool drill-down responses now include `attack_name` in the
`attack_summary` field, allowing users to see human-readable attack names alongside IDs.

**Vertical slice** — response handling across all drift tools:

**TDD Steps**:

1. **RED**: Write test with mock drift records containing `"attackName": "Malware Drop via HTTP"`.
   Verify the `attack_summary` in the drill-down response includes
   `"attack_name": "Malware Drop via HTTP"` alongside existing `attack_id` and `attack_types`.
   Cover both simulation drifts (`_group_and_paginate_drifts`) and SC drifts (if separate function).

2. **GREEN**: In the attack_summary building logic, extract `d.get("attackName")` alongside
   existing `d.get("attackId")` and `d.get("attackTypes")`. Add `"attack_name": ...` to each
   `attack_counts` entry. If multiple records for the same `attackId` have different names,
   use the first non-None value encountered.

3. **VERIFY**: Run attack_summary tests across all drift tools:
   `uv run pytest safebreach_mcp_data/tests/test_drift_tools.py -v -k "attack_summary"`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add `attackName` extraction in attack_summary building |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Tests for attack_name in attack_summary |

**Git Commit**: `feat(data): include attack_name in drift attack_summary responses (SAF-29727)`

---

### Phase 5: Documentation update

**E2E Deliverable**: Tool descriptions and CLAUDE.md accurately document all new attack filter
parameters for all three drift tools.

**Steps**:
1. Update `CLAUDE.md` drift tools documentation: add `attack_type` and `attack_name` to
   result/status drift sections; add all three attack params to SC drift section.
2. Update tool description strings in `data_server.py` for all three tools.
3. Run full test suite to verify no regressions:
   `uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"`

**Changes**:

| File | Change |
|------|--------|
| `CLAUDE.md` | Update drift tools documentation sections |
| `safebreach_mcp_data/data_server.py` | Update tool description strings |

**Git Commit**: `docs: document attack filter params for drift tools (SAF-29727)`

---

### Phase 6: attack_type discovery mode + zero-results hints

**E2E Deliverable**: All 3 drift tools support `attack_type="__list__"` to discover valid
attack type values. When an `attack_type` filter returns zero results, the response hint
includes the list of valid attack types on that console.

**Problem**: `attack_type` is a case-sensitive exact match filter. "Suspicious File Creation"
returns drifts; "suspicious file creation" returns 0 with no error. The silent zero-result
is indistinguishable from "no drifts exist." The suggestions API at
`/executionsHistorySuggestions` provides the `attack_type` collection with 30 valid values
(verified on staging).

**Vertical slice** — all layers:

**TDD Steps**:

1. **RED — Unit tests**:
   - `test_result_drifts_attack_type_list_mode` — mock suggestions API, call with
     `attack_type="__list__"`, assert response contains `attack_types` list with `name`
     and `occurrences` fields, plus `hint_to_agent`
   - Same for status drifts and SC drifts
   - `test_zero_results_hint_includes_attack_types` — when `attack_type` filter produces
     zero results, assert the hint mentions valid attack types

2. **GREEN — Implementation**:
   - In `sb_get_simulation_result_drifts()`: add early return for `attack_type == "__list__"`
     using `_fetch_suggestions_entries(console, "attack_type")`. Return sorted list with
     `name`, `occurrences`, `total`, and `hint_to_agent` noting case-sensitive exact match.
   - Same in `sb_get_simulation_status_drifts()` and `sb_get_security_control_drifts()`
   - In `data_server.py`: add early return in all 3 tool functions before timestamp validation
   - In `_build_zero_results_hint()`: when `attack_type` is in applied_filters, fetch and
     include valid types in the hint
   - Update tool descriptions to document `__list__` mode and case sensitivity

3. **E2E test** against staging:
   - Call `attack_type="__list__"` on staging, assert non-empty list returned
   - Verify a returned value works as a filter (non-empty results)

**Existing infrastructure to reuse**:
- `safebreach_mcp_core/suggestions.py` — `_fetch_suggestions_entries(console, "attack_type")`
  already works, cached with 30-min TTL
- `__list__` pattern from `sb_get_security_control_drifts()` (line 2506) — copy structure

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add `__list__` mode to all 3 drift functions + enhance zero-results hints |
| `safebreach_mcp_data/data_server.py` | Add early return for `__list__` in all 3 tools + update descriptions |
| `safebreach_mcp_data/tests/test_drift_tools.py` | Unit + E2E tests for discovery mode and hints |
| `CLAUDE.md` | Document `__list__` mode and case-sensitivity |

**Git Commit**: `feat(data): add attack_type discovery mode to drift tools (SAF-29727)`

## 10. Risks and Assumptions

### Assumptions

| Assumption | Confidence | Validation |
|------------|------------|------------|
| Backend APIs support all 3 attack filters | High | Verified via merged PR #2799 |
| `attackName` uses match_phrase (not exact) | High | Confirmed in shared driftUtils.js |
| Response fields `attackId`, `attackName`, `attackTypes` present in drift pairs | High | Confirmed in PR |
| SC drift API (v2) accepts same attack param names as simulation (v1) | High | Same `parseAttackFiltersObject` |

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backend API not deployed to all environments | Low | E2E tests gated by environment availability |
| Cache key explosion with more filter params | Low | Bounded cache (maxsize=3, TTL=600s) handles this |
| `attackName` match_phrase may return unexpected results | Low | This is backend behavior, MCP is pass-through |

## 12. Executive Summary

- **Issue**: MCP drift tools lack attack-specific filtering, requiring post-processing to analyze
  drifts by attack properties
- **What Will Be Built**: Add `attack_id`, `attack_type`, `attack_name` filter parameters to all
  three drift MCP tools (result drifts, status drifts, security control drifts) and enrich
  `attack_summary` responses with `attack_name`
- **Key Technical Decisions**: Keep separate payload builders for v1/v2 APIs;
  tool-by-tool implementation with TDD and elephant carpaccio
- **Scope**: 3 drift tools, 4 files (data_types, data_functions, data_server, tests), no UI changes
- **Business Value**: Enables natural-language queries like "Show me drifts for attack X against
  CrowdStrike last 7 days" without additional processing

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-04-09 10:45 | PRD created — initial draft |
| 2026-04-09 11:30 | Phase 1 complete — result drifts attack filtering (7 unit + 1 E2E) |
| 2026-04-09 11:45 | Phase 2 complete — status drifts attack filtering (3 unit + 1 E2E) |
| 2026-04-09 12:00 | Phase 3 complete — SC drifts attack filtering (7 unit + 1 E2E) |
| 2026-04-09 12:30 | E2E tests upgraded to verify non-empty filtered results on staging |
| 2026-04-12 | Added Phase 6: attack_type discovery mode — addresses case-sensitive exact match usability issue |
