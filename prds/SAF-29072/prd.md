# PRD: SAF-29072 — Simulation Lineage Tracing by Drift Tracking Code

**Ticket**: SAF-29072
**Branch**: `SAF-29072-filter-simulation-by-tracking-id`
**Author**: Yossi Attas
**Status**: Approved
**Last Updated**: 2026-03-16

---

## Phase Status Tracking

| Phase | Name | Status | Completed | Commit | Notes |
|-------|------|--------|-----------|--------|-------|
| 1 | Normalize Tracking Code in Drill-Down Records | ✅ Complete | 2026-03-16 | - | `data_types.py` + tests |
| 2 | Lineage Query Function | ✅ Complete | 2026-03-16 | - | `data_functions.py` + 10 tests |
| 3 | MCP Tool Registration | ⏳ Pending | - | - | `data_server.py` |
| 4 | Docstring Terminology Update | ⏳ Pending | - | - | All 6 drift tools + 2 simulation tools |
| 5 | E2E Tests | ⏳ Pending | - | - | Against live console, zero mocks |

---

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Simulation Lineage Tracing by Drift Tracking Code |
| **JIRA** | SAF-29072 |
| **Task Type** | Feature |
| **Purpose** | Enable agents to trace the full execution history of a simulation lineage across test runs |
| **Target Consumer** | AI agents (LLMs) consuming MCP tools for drift analysis |
| **Key Benefits** | Complete drift investigation workflow, cross-test visibility, agent self-guidance |
| **Originating Request** | Gap identified during SAF-28331 implementation |

---

## 2. Solution Description

### Chosen Solution: Dedicated `get_simulation_lineage` Tool (Approach A)

A new MCP tool that accepts a `tracking_code` and returns all simulations sharing that lineage
across all test runs, ordered chronologically. Uses the existing SafeBreach API server-side
Elasticsearch query (`originalExecutionId:("{code}")` with `runId: "*"`) already proven in
`get_simulation_details`.

### Alternatives Considered

| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Extend `get_test_simulations` with `test_id=*` | Overload existing tool with wildcard | Muddies tool semantics, confusing conditional logic for LLMs |
| Enhance `get_simulation_details` drift info | Return full lineage in details response | Mixes single-entity and multi-entity response patterns |
| Filter within single test only | Add `tracking_code_filter` to `get_test_simulations` | Limited value — drifts commonly occur across test runs |

### Decision Rationale

- **Discoverable**: Agent sees `drift_tracking_code` in any simulation → naturally looks for a tool accepting it
- **Single-purpose**: Follows the pattern of existing drift tools (each has clear, distinct scope)
- **No conditional logic**: No "use `test_id=*` only when `tracking_code_filter` is set" rules
- **Response shape matches intent**: Chronological timeline of executions, not overloaded details

---

## 3. Core Feature Components

### Component A: `get_simulation_lineage` Tool

**Purpose**: New MCP tool enabling cross-test-run lineage tracing by drift tracking code.

**Key Features**:
- Accepts a `tracking_code` (the `drift_tracking_code` value from any simulation record)
- Queries the SafeBreach API with `runId: "*"` to search across all test runs
- Returns a paginated, chronologically-ordered list of all simulations sharing that lineage
- Each record uses the reduced simulation entity format (consistent with `get_test_simulations`)
- Includes `is_drifted` flag per simulation showing whether its result differs from the previous
- Response includes a timeline summary: total executions, first/last seen, status distribution

### Component B: Docstring Terminology Formalization

**Purpose**: Update all drift-related tool docstrings to formalize `drift_tracking_code` as a
first-class concept and create cross-tool workflow hints.

**Key Features**:
- Define `drift_tracking_code` consistently: "A lineage identifier that groups simulations of the
  same attack configuration across test runs. Use with `get_simulation_lineage` to trace execution
  history."
- Add cross-references from drift drill-down tools to `get_simulation_lineage`
- Add cross-references from `get_simulation_details` to `get_simulation_lineage`
- Update `get_test_simulations` to mention `drift_tracking_code` in response fields

---

## 4. API Endpoints and Integration

### Existing API to Consume

- **API Name**: Execution History Results
- **URL**: `POST /api/data/v1/accounts/{account_id}/executionsHistoryResults`
- **Headers**: `Content-Type: application/json`, `x-apitoken: {token}`
- **Request Payload**:
  ```json
  {
    "runId": "*",
    "query": "originalExecutionId:(\"<tracking_code>\")",
    "page": 1,
    "pageSize": 100,
    "orderBy": "asc",
    "sortBy": "executionTime"
  }
  ```
- **Response**: `{ "simulations": [...], "totalSimulations": N }`
- **Note**: `orderBy: "asc"` for chronological (oldest-first) lineage view. The `runId: "*"` wildcard
  searches across all test runs. This pattern is already used in `get_simulation_details` (line ~867).

---

## 5. Non-Functional Requirements

### Technical Constraints

- **Caching**: Use existing `SafeBreachCache` with a dedicated lineage cache (small maxsize, short TTL).
  Cache key: `lineage_{console}_{tracking_code}`. TTL should be short (300s) since lineage can change
  with new test runs.
- **Pagination**: Use existing `PAGE_SIZE = 10` for MCP response pagination (consistent with other tools).
  API-level pagination uses `pageSize=100` internally.
- **Backward Compatibility**: Phase 1 renames `trackingId` → `drift_tracking_code` in drill-down
  records — a field name change in 3 drift tools. This is intentional to establish consistent naming.
  Docstring updates are additive. No changes to tool signatures or behavior.
- **Field Presence**: `drift_tracking_code` (`originalExecutionId`) is not always present on simulations.
  The tool should return a clear error if the provided tracking code yields no results.

---

## 6. Definition of Done

- [x] Chosen approach validated (Approach A: dedicated tool)
- [x] `trackingId` normalized to `drift_tracking_code` in all drill-down records (Phase 1)
- [x] `get_simulation_lineage` function implemented in `data_functions.py`
- [ ] MCP tool registered in `data_server.py` with comprehensive docstring
- [ ] `drift_tracking_code` formalized across all 8 tool docstrings
- [x] Unit tests cover: happy path, pagination, empty results, API errors, caching
- [ ] E2E tests verify lineage tracing against live console (zero mocks)
- [x] All existing cross-server tests still pass
- [ ] No breaking changes to existing tools

---

## 7. Test Strategy

### Methodology

Phase 1 normalizes field naming (TDD). Phase 2 adds the lineage function (TDD). Code-first for
tool registration and docstrings (Phases 3-4). Post-implementation E2E tests (Phase 5).

### Phase 1 — Unit Tests (Tracking Code Normalization)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (update existing drill-down assertions)

All existing drill-down tests that assert `trackingId` on records must be updated to assert
`drift_tracking_code` instead. This is the TDD "red" step — tests change expectations before the
code changes.

### Phase 2 — Unit Tests (Lineage Function, TDD)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (new test class alongside existing drift tests)

| Test | What it verifies |
|------|-----------------|
| `test_lineage_happy_path` | Returns chronological list of simulations for a valid tracking code |
| `test_lineage_pagination` | Page 0 returns first 10, page 1 returns next batch |
| `test_lineage_empty_results` | Unknown tracking code returns empty with helpful hint |
| `test_lineage_single_result` | One simulation with that code returns a single-item list |
| `test_lineage_api_error` | API failure raises ValueError with descriptive message |
| `test_lineage_api_401` | Auth failure raises ValueError mentioning authentication |
| `test_lineage_cache_hit` | Second call returns cached data without API call |
| `test_lineage_includes_status_summary` | Response includes status distribution across the lineage |
| `test_lineage_includes_is_drifted` | Each record has `is_drifted` computed by comparing to previous |
| `test_lineage_chronological_order` | Results sorted oldest-first by execution time |

### Phase 5 — E2E Tests (Zero-Mock, Live Console)

**File**: `safebreach_mcp_data/tests/test_drift_tools.py` (new class alongside existing drift E2E tests)

**Infrastructure**: Uses the existing E2E test infrastructure with absolutely zero mocks:
- Dual decorators: `@skip_e2e` + `@pytest.mark.e2e` on every test method
- Class-scoped fixtures (`scope="class"`) to minimize API calls and chain dependencies
- Direct calls to `sb_get_simulation_lineage()` against a real SafeBreach console
- `E2E_CONSOLE` env var for target console, `pytest.skip()` when data unavailable
- Structure validation only (assert response keys/types, not exact values)

**Fixtures** (class-scoped, chained):
- `e2e_console()` — reads `E2E_CONSOLE` env var, skips if unset
- `drifted_tracking_code(e2e_console)` — fetches a real test with drifted simulations
  (`drifted_only=True`), extracts `drift_tracking_code` from first drifted sim, skips if none found

| Test | What it verifies |
|------|-----------------|
| `test_e2e_lineage_from_drifted_simulation` | Calls `sb_get_simulation_lineage` with real tracking code, validates response structure |
| `test_e2e_lineage_returns_multiple_test_runs` | `test_runs_spanned >= 2` — lineage crosses test boundaries |
| `test_e2e_lineage_unknown_code` | Fabricated code → `total_simulations == 0` + `hint_to_agent` present |

---

## 8. Implementation Phases

### Phase 1: Normalize Tracking Code in Drill-Down Records

**Semantic Change**: Rename `trackingId` → `drift_tracking_code` in all drift drill-down records
so every MCP tool uses the same field name for the lineage identifier.

**Deliverables**:
- Consistent `drift_tracking_code` field name across all drift drill-down records
- Updated unit tests asserting the new field name

**Implementation Details**:

The 3 time-window drift tools (`get_simulation_result_drifts`, `get_simulation_status_drifts`,
`get_security_control_drifts`) currently pass raw API records through without renaming `trackingId`.
Meanwhile, simulation records map it to `drift_tracking_code` via `reduced_simulation_results_mapping`.

**Fix**: In both grouping functions in `data_types.py`, rename the field on each record before grouping:

1. **`group_and_enrich_drift_records()`** (line ~702): Before `groups.setdefault(...)`, add a rename
   step: if the record has `trackingId`, pop it and set `drift_tracking_code` to the same value.

2. **`group_sc_drift_records()`** (line ~904): Same rename step before `groups.setdefault(...)`.

This is a minimal, surgical change — only the field name changes, all other record fields stay as-is.

**Test updates**: All existing drill-down test assertions referencing `trackingId` in records must
change to `drift_tracking_code`. This includes fixture data (`"trackingId": "abc123"` → keep as-is
in mock API responses, but assert `drift_tracking_code` in the grouped output).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_types.py` | EDIT | Add `trackingId` → `drift_tracking_code` rename in both grouping functions |
| `safebreach_mcp_data/tests/test_drift_tools.py` | EDIT | Update drill-down assertions from `trackingId` to `drift_tracking_code` |

**Test Plan**: TDD — update test assertions first (red), then fix the code (green). Run full
cross-server test suite to ensure no regressions.

**Git Commit**: `refactor(data): normalize trackingId to drift_tracking_code in drill-down records (SAF-29072)`

---

### Phase 2: Lineage Query Function (`data_functions.py`)

**Semantic Change**: Add `sb_get_simulation_lineage()` function that queries all simulations
sharing a drift tracking code across test runs.

**Deliverables**:
- New function `sb_get_simulation_lineage(console, tracking_code, page_number)` in `data_functions.py`
- Dedicated lineage cache entry in the simulations cache

**Implementation Details**:

New function `sb_get_simulation_lineage()`:
- Parameters: `console: str`, `tracking_code: str`, `page_number: int = 0`
- Validate `tracking_code` is non-empty, raise `ValueError` if blank
- Build API request to `POST /executionsHistoryResults` with:
  - `runId: "*"` (all test runs)
  - `query: originalExecutionId:("{tracking_code}")`
  - `orderBy: "asc"`, `sortBy: "executionTime"` (chronological)
  - Fetch all pages from API (pageSize=100 loop, same pattern as `_get_all_simulations_from_cache_or_api`)
- Transform each raw simulation via `get_reduced_simulation_result_entity()` (reuse existing mapper)
- Compute `is_drifted` per simulation by comparing each simulation's `status` to its predecessor
  in the chronological list (first simulation is never drifted)
- Build status summary: count occurrences of each `status` value across the lineage
- Apply MCP pagination (PAGE_SIZE=10) on the full list
- Cache the full result list with key `lineage_{console}_{tracking_code}`, TTL=300s
- If zero results, return a response with `total_simulations: 0` and a `hint_to_agent` suggesting
  the tracking code may be invalid or the simulations may have aged out

**Response format (summary)**:
```
{
  "tracking_code": "<code>",
  "total_simulations": N,
  "first_seen": "<earliest execution_time>",
  "last_seen": "<latest execution_time>",
  "status_summary": {"prevented": 5, "missed": 2, "detected": 1},
  "test_runs_spanned": M,
  "page_number": 0,
  "total_pages": P,
  "simulations": [
    {simulation_id, test_id, test_name, status, end_time, playbook_attack_id,
     playbook_attack_name, drift_tracking_code, is_drifted, ...},
    ...
  ],
  "hint_to_agent": "Showing page 0 of P. ... Use get_simulation_details for full details."
}
```

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_functions.py` | EDIT | Add `sb_get_simulation_lineage()` function |
| `safebreach_mcp_data/tests/test_drift_tools.py` | EDIT | Add `TestSbGetSimulationLineage` test class (TDD) |

**Test Plan**: Write 10 unit tests first (TDD red), then implement to make them pass (TDD green).

**Git Commit**: `feat(data): add simulation lineage query function (SAF-29072)`

---

### Phase 3: MCP Tool Registration (`data_server.py`)

**Semantic Change**: Register `get_simulation_lineage` as an MCP tool with comprehensive
agent-friendly docstring.

**Deliverables**:
- New `@self.mcp.tool` registration for `get_simulation_lineage`
- Docstring explaining what drift_tracking_code means, when to use this tool, and how it fits
  the drift investigation workflow

**Implementation Details**:

Register new tool `get_simulation_lineage` with parameters:
- `console: str` (required) — SafeBreach console name
- `tracking_code: str` (required) — The `drift_tracking_code` value from any simulation record
- `page_number: int = 0` — Pagination

Docstring must include:
- What `drift_tracking_code` is: "A lineage identifier that groups all executions of the same
  attack configuration across test runs"
- When to use: "After discovering a drift, use the `drift_tracking_code` from
  `get_simulation_details` or `get_test_simulations` to see the full execution timeline"
- What it returns: Chronological list of all simulations with that tracking code
- Cross-references: "For individual simulation details, use `get_simulation_details`.
  For drift analysis, see `get_simulation_result_drifts` and `get_security_control_drifts`."

Tool wrapper: call `sb_get_simulation_lineage(console, tracking_code, page_number)`
directly — no timestamp normalization needed (no time params).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_server.py` | EDIT | Add `get_simulation_lineage` tool registration |

**Test Plan**: Manual verification via MCP inspector or integration test.

**Git Commit**: `feat(data): register get_simulation_lineage MCP tool (SAF-29072)`

---

### Phase 4: Docstring Terminology Update (`data_server.py`)

**Semantic Change**: Formalize `drift_tracking_code` as a first-class concept across all
drift-related and simulation tool docstrings.

**Deliverables**:
- Updated docstrings for 8 tools with consistent `drift_tracking_code` terminology
- Cross-tool workflow hints enabling seamless drift investigation flow

**Implementation Details**:

Update docstrings for these tools:

1. **`get_test_simulations`** — Add: "Each simulation includes `drift_tracking_code` — a lineage
   identifier grouping all executions of the same attack configuration. Use with
   `get_simulation_lineage` to trace how results changed over time."

2. **`get_simulation_details`** — Add: "When `include_drift_info=True`, returns `drift_tracking_code`
   for drifted simulations. Pass this code to `get_simulation_lineage` to see the full execution
   timeline across all test runs."

3. **`get_test_drifts`** — Add reference to `get_simulation_lineage` for lineage tracing.

4. **`get_simulation_result_drifts`** — Add to drill-down hint: "Each drill-down record includes
   `drift_tracking_code`. Pass it directly to `get_simulation_lineage` for full execution history."

5. **`get_simulation_status_drifts`** — Same cross-reference as above.

6. **`get_security_control_drifts`** — Same cross-reference pattern.

7. **`get_full_simulation_logs`** — Add mention of `drift_tracking_code` for correlation.

8. **`get_test_findings_details`** — Add mention if applicable.

Only update tools where the cross-reference is natural and helpful. Do not force references
where they don't fit the tool's purpose.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_server.py` | EDIT | Update tool docstrings with drift_tracking_code terminology |

**Test Plan**: Review docstrings for consistency. No unit tests needed (documentation only).

**Git Commit**: `docs(data): formalize drift_tracking_code terminology across tool docstrings (SAF-29072)`

---

### Phase 5: E2E Tests (Zero-Mock, Live Console)

**Semantic Change**: Add end-to-end tests verifying lineage tracing against a live SafeBreach console
with absolutely zero mocks — real API calls only.

**Deliverables**:
- 3 E2E tests in `test_drift_tools.py` validating the full lineage workflow against a live console
- Class-scoped fixtures for efficient data reuse across tests

**Implementation Details**:

New test class `TestSimulationLineageE2E` in `test_drift_tools.py` (alongside existing
`TestDriftToolsE2E` and `TestSecurityControlDriftsE2E`).

**Zero-mock approach**: Every test calls real SafeBreach APIs. No `@patch`, no `MagicMock`, no
`side_effect`. All responses come from a live console specified by the `E2E_CONSOLE` env var.

**Fixtures** (class-scoped, chained):
- `e2e_console()` — Reuse existing fixture. Reads `E2E_CONSOLE` env var, `pytest.skip()` if unset.
- `drifted_tracking_code(e2e_console)` — New fixture. Calls `sb_get_test_simulations()` with
  `drifted_only=True` on a real test, extracts `drift_tracking_code` from the first drifted
  simulation. Skips with `pytest.skip()` if no drifted simulations found (graceful degradation).

**Tests** (each with `@skip_e2e` + `@pytest.mark.e2e` dual decorators):

1. **`test_e2e_lineage_from_drifted_simulation(self, e2e_console, drifted_tracking_code)`**:
   Call `sb_get_simulation_lineage(e2e_console, drifted_tracking_code)` with a real tracking code.
   Assert response structure: `tracking_code`, `total_simulations >= 1`, `simulations` is a list,
   each simulation has `simulation_id`, `test_id`, `status`, `drift_tracking_code`. Verify
   `status_summary` is a dict with string keys and int values. Verify chronological order
   (`end_time` non-decreasing).

2. **`test_e2e_lineage_returns_multiple_test_runs(self, e2e_console, drifted_tracking_code)`**:
   Call `sb_get_simulation_lineage` with same tracking code. Assert `test_runs_spanned >= 2` to
   confirm lineage crosses test run boundaries. Verify distinct `test_id` values in the simulations
   list match the reported `test_runs_spanned` count.

3. **`test_e2e_lineage_unknown_code(self, e2e_console)`**:
   Call `sb_get_simulation_lineage(e2e_console, "nonexistent-tracking-code-12345")`. Assert
   `total_simulations == 0`, `simulations` is an empty list, and `hint_to_agent` is present with
   guidance text.

**Assertion philosophy**: Validate response structure (keys exist, correct types) and logical
invariants (chronological order, non-negative counts), NOT exact values. Live data changes over time.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/tests/test_drift_tools.py` | EDIT | Add `TestSimulationLineageE2E` class |

**Test Plan**: Run via `source .vscode/set_env.sh && SKIP_E2E_TESTS=false uv run pytest -m "e2e" -v -k "lineage"`

**Git Commit**: `test: add E2E tests for simulation lineage tracing (SAF-29072)`

---

## 9. File Change Summary

| File | Phases | Action |
|------|--------|--------|
| `safebreach_mcp_data/data_types.py` | 1 | Rename `trackingId` → `drift_tracking_code` in grouping functions |
| `safebreach_mcp_data/data_functions.py` | 2 | Add `sb_get_simulation_lineage()` |
| `safebreach_mcp_data/data_server.py` | 3, 4 | Add tool registration + update all docstrings |
| `safebreach_mcp_data/tests/test_drift_tools.py` | 1, 2, 5 | Update drill-down assertions + `TestSbGetSimulationLineage` (TDD) + `TestSimulationLineageE2E` (zero-mock) |

---

## 10. Risks and Assumptions

| Risk | Impact | Mitigation |
|------|--------|------------|
| `originalExecutionId` not present on all simulations | Low | Tool returns empty results with helpful hint |
| Large lineage (1000+ executions) slows API | Low | Server-side pagination (pageSize=100), MCP pagination (10) |
| Tracking code format changes across API versions | Low | Treated as opaque string, no parsing |

**Assumptions**:
- The `executionsHistoryResults` API with `runId: "*"` is available on all SafeBreach consoles
- `originalExecutionId` is stable and consistent across test runs for the same attack configuration
- The E2E test console has drifted simulations with tracking codes spanning multiple test runs

---

## 11. Future Enhancements

- **Lineage diff view**: Compare two specific simulations in a lineage side-by-side
- **Lineage timeline visualization**: Return data formatted for timeline rendering

---

## 12. Executive Summary

**Issue**: Agents performing drift analysis can discover that simulations drifted but cannot trace
the full execution history — the `drift_tracking_code` field appears in responses but no tool
accepts it as input.

**Solution**: First, normalize `trackingId` → `drift_tracking_code` in all drift drill-down records
so every MCP tool uses consistent naming. Then, a new `get_simulation_lineage` MCP tool that takes
a tracking code and returns the complete chronological execution history across all test runs.
Combined with formalized `drift_tracking_code` terminology and cross-tool workflow hints across all
8 relevant tool docstrings.

**Key Decision**: Dedicated tool over extending existing tools — cleaner mental model for LLM agents,
no conditional parameter logic, response shape matches the query intent.

**Business Value**: Completes the drift investigation workflow: discover drift → understand impact →
trace full history. Agents can now answer "How has this simulation's result changed over time?"
without manual correlation.

---

## Change Log

| Date | Change Description |
|------|-------------------|
| 2026-03-15 12:00 | PRD created — initial draft |
| 2026-03-15 13:00 | Updated E2E tests: zero-mock live console pattern, moved to test_drift_tools.py, added chained class-scoped fixtures |
| 2026-03-15 14:00 | Added Phase 1: normalize trackingId → drift_tracking_code in drill-down records. Renumbered all phases (now 1-5). Removed "Tracking code in drill-down" from Future Enhancements. Updated docstring phase to reference direct drift_tracking_code in drill-down records. |
| 2026-03-16 | Phase 2 complete: `sb_get_simulation_lineage()` function + 10 unit tests. 740 cross-server tests passing. |
