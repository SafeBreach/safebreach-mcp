# Add "running" Status Filter + Rename get_tests_history to get_tests — SAF-30863

## 1. Overview

- **Task Type**: Bug fix + refactor
- **Purpose**: HELM incorrectly reports "no tests are currently running" because the `get_tests_history`
  MCP tool description omits "running" from its `status_filter` values, and the tool name itself implies
  only historical data. Fix the tool description, add "running" as a supported filter, and rename the
  tool to `get_tests` to accurately reflect its capability.
- **Target Consumer**: AI agents (HELM) and SafeBreach customers interacting via HELM
- **Key Benefits**:
  1. HELM can directly filter for running tests without workaround
  2. Tool name accurately reflects its capability (not limited to history)
  3. Eliminates false negatives when users ask about active test runs
- **Business Alignment**: Improves HELM transparency and trust — users should not receive incorrect
  answers from the AI assistant
- **Originating Request**: [SAF-30863](https://safebreach.atlassian.net/browse/SAF-30863) — reported
  by Hadas Cohen on pentest01.safebreach.com (2026Q.2.2)

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-05-12 18:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution: Clean Rename

Rename the tool and function in one atomic change with no backward compatibility shim:

1. Rename MCP tool from `get_tests_history` to `get_tests`
2. Rename business logic function from `sb_get_tests_history` to `sb_get_tests`
3. Add `"running"` to the `status_filter` values in the tool description
4. Update all test references, imports, exports, and documentation

### Alternatives Considered

**Deprecation Shim**: Keep old tool name as an alias for one release cycle, then remove.
- Pros: Zero breakage risk, graceful migration
- Cons: Two tool names visible to AI agents (confusing), extra code to maintain, overkill given
  no external consumers were found
- Decision: Rejected — HELM discovers tools dynamically via MCP, so the rename is transparent.
  No external consumers reference the tool name directly.

### Decision Rationale

The clean rename is safe because:
- HELM discovers tools dynamically via MCP protocol (no hard-coded tool names)
- Investigation found zero cross-server references
- No external consumers reference the tool name
- The rename is fully isolated to the data server module

## 3. Core Feature Components

### Component A: Tool Description Fix (Primary Bug Fix)

- **Purpose**: Modify existing tool registration in `data_server.py` to expose "running" as a valid
  `status_filter` value
- **Key Features**:
  - Add `'running'` to the status_filter options in the tool description string
  - No business logic changes needed — `data_functions.py` already supports "running" with
    cache-bypass (line 127-128) and client-side filtering (line 302-304)

### Component B: Tool and Function Rename (Refactor)

- **Purpose**: Rename `get_tests_history` to `get_tests` across the entire data server module to
  accurately reflect that the tool returns tests in any status, not just historical ones
- **Key Features**:
  - Rename MCP tool name: `get_tests_history` -> `get_tests`
  - Rename wrapper function: `get_tests_history_tool` -> `get_tests_tool`
  - Rename business logic function: `sb_get_tests_history` -> `sb_get_tests`
  - Update all imports, exports, test references, mock patches, and documentation

### Component C: Test Coverage Addition

- **Purpose**: Add unit test for "running" status filtering to close the coverage gap
- **Key Features**:
  - New test case verifying `status_filter="running"` returns only running tests
  - Verify cache-bypass behavior when filtering for running tests

## 7. Definition of Done

- [ ] Tool is named `get_tests` (renamed from `get_tests_history`)
- [ ] Tool description lists `'running'` as a valid `status_filter` value
- [ ] Business logic function renamed from `sb_get_tests_history` to `sb_get_tests`
- [ ] All imports and exports updated (`__init__.py`, `data_server.py`)
- [ ] Unit test exists for filtering tests by "running" status
- [ ] All existing tests pass with updated references (10 test method renames, 18 call updates,
  7 mock patches, 4 tool name lookups)
- [ ] `CLAUDE.md` documents the new tool name and "running" status filter
- [ ] `README.md` updated to match CLAUDE.md changes
- [ ] `DESIGN.md`, `E2E_TESTING.md`, `tests/README.md` updated
- [ ] `tests/memory_profile_baseline.py` updated
- [ ] E2E test verifies `status_filter="running"` returns active tests (piggybacked on cancel test)
- [ ] No cross-server breakage (config, playbook, utilities, studio servers unaffected)

## 8. Testing Strategy

### Unit Testing

- **Scope**: `safebreach_mcp_data/tests/test_data_functions.py` and
  `safebreach_mcp_data/tests/test_timestamp_normalization.py`
- **Key Scenarios**:
  1. **New**: Filter by `status_filter="running"` returns only tests with RUNNING status
  2. **New**: Verify cache-bypass when `status_filter="running"` (existing logic, new test)
  3. **Existing**: All 10 renamed test methods pass with updated function references
  4. **Existing**: All mock patches reference the new function name `sb_get_tests`
  5. **Existing**: Timestamp normalization tests reference new tool name `get_tests`
- **Framework**: pytest
- **Coverage Target**: Maintain existing coverage, close "running" filter gap

### Integration / E2E Testing

- **Scope**: `safebreach_mcp_data/tests/test_e2e.py` and
  `safebreach_mcp_studio/tests/test_e2e_manage_test.py`
- **Changes**:
  1. Rename `test_get_tests_history_e2e` to `test_get_tests_e2e`, update imports and function calls
  2. **New E2E**: Piggyback on `test_e2e_cancel_test` in `test_e2e_manage_test.py` — between the
     `run_scenario` queue and the `manage_test(action="cancel")` call, insert a
     `sb_get_tests(status_filter="running")` check to verify the queued test appears in
     running results. This avoids adding a new scenario execution and keeps test duration minimal.
- **Note**: E2E tests require real SafeBreach environment — verify they pass when environment
  is available

### Verification Command

```bash
uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"
```

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Rename source code | ⏳ Pending | - | - | |
| Phase 2: Add "running" filter + new test | ⏳ Pending | - | - | |
| Phase 3: Update test references | ⏳ Pending | - | - | |
| Phase 4: Update documentation | ⏳ Pending | - | - | |

### Phase 1: Rename Source Code

**Semantic Change**: Rename the tool and function across the data server source files

**Deliverables**: Tool name `get_tests` operational, function name `sb_get_tests` in place

**Implementation Details**:

1. **`safebreach_mcp_data/data_functions.py`** (line 73):
   - Rename function definition from `sb_get_tests_history` to `sb_get_tests`
   - No other changes to function body — business logic stays identical

2. **`safebreach_mcp_data/data_server.py`**:
   - Line 19: Update import from `sb_get_tests_history` to `sb_get_tests`
   - Line 54: Change tool name from `"get_tests_history"` to `"get_tests"`
   - Line 64: Rename wrapper function from `get_tests_history_tool` to `get_tests_tool`
   - Line 77: Update call from `sb_get_tests_history(...)` to `sb_get_tests(...)`

3. **`safebreach_mcp_data/__init__.py`**:
   - Line 10: Update import from `sb_get_tests_history` to `sb_get_tests`
   - Line 18: Update `__all__` entry from `'sb_get_tests_history'` to `'sb_get_tests'`

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Rename function definition |
| `safebreach_mcp_data/data_server.py` | Rename import, tool name, wrapper function, function call |
| `safebreach_mcp_data/__init__.py` | Rename import and `__all__` export |

**Verification**: `uv run pytest safebreach_mcp_data/tests/test_data_functions.py -v -m "not e2e" -x`
(expect failures in tests that still reference old name — Phase 3 will fix)

**Git Commit**: `refactor(data): rename get_tests_history to get_tests (SAF-30863)`

---

### Phase 2: Add "running" Filter to Tool Description + New Test

**Semantic Change**: Expose "running" in the tool description and add test coverage

**Deliverables**: "running" visible to AI agents in tool description, unit test for running filter,
E2E test verifying running filter against a real console

**Implementation Details**:

1. **`safebreach_mcp_data/data_server.py`** (lines 56-62):
   - Update the tool description string to include `'running'` in the status_filter values
   - Change from `status_filter ('completed'/'canceled'/'failed'/None)` to
     `status_filter ('completed'/'canceled'/'failed'/'running'/None)`

2. **`safebreach_mcp_data/tests/test_data_functions.py`**:
   - Add a new test method `test_apply_filters_running_status` in the filter tests section
     (near line 292)
   - Test data: include tests with status "RUNNING", "completed", "failed"
   - Assert: filtering with `status_filter="running"` returns only RUNNING tests
   - Assert: filtering is case-insensitive ("running" matches "RUNNING")

3. **`safebreach_mcp_studio/tests/test_e2e_manage_test.py`**:
   - Piggyback on `test_e2e_cancel_test` (line ~115): after the scenario is queued and
     `test_id` is obtained, but before calling `manage_test(action="cancel")`, insert a call to
     `sb_get_tests(console=e2e_console, status_filter="running")` and assert the queued
     `test_id` appears in the results. This verifies the "running" filter works end-to-end
     against a real console without adding a separate scenario execution.
   - Import `sb_get_tests` from `safebreach_mcp_data.data_functions`

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_server.py` | Add "running" to status_filter in tool description |
| `safebreach_mcp_data/tests/test_data_functions.py` | Add `test_apply_filters_running_status` test |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add running filter check in cancel test |

**Verification**:
- Unit: `uv run pytest safebreach_mcp_data/tests/test_data_functions.py::TestApplyFilters -v`
- E2E: `source .vscode/set_env.sh && uv run pytest safebreach_mcp_studio/tests/test_e2e_manage_test.py::TestManageTestE2E::test_e2e_cancel_test -v -m e2e`

**Git Commit**: `fix(data): add "running" to get_tests status_filter + tests (SAF-30863)`

---

### Phase 3: Update Test References

**Semantic Change**: Rename all test references from `sb_get_tests_history`/`get_tests_history`
to `sb_get_tests`/`get_tests`

**Deliverables**: All data server tests pass with new function/tool names

**Implementation Details**:

1. **`safebreach_mcp_data/tests/test_data_functions.py`**:
   - Update import (line 15): `sb_get_tests_history` -> `sb_get_tests`
   - Rename 10 test methods: replace `_history` suffix pattern
     (e.g., `test_sb_get_tests_history_success` -> `test_sb_get_tests_success`)
   - Update 18 function calls: `sb_get_tests_history(...)` -> `sb_get_tests(...)`
   - Update 3 mock patches (lines 2134, 2248, 2370):
     `'safebreach_mcp_data.data_functions.sb_get_tests_history'` ->
     `'safebreach_mcp_data.data_functions.sb_get_tests'`

2. **`safebreach_mcp_data/tests/test_timestamp_normalization.py`**:
   - Rename test class (line 20): `TestGetTestsHistoryTimestampNormalization` ->
     `TestGetTestsTimestampNormalization`
   - Update 4 mock patches (lines 26, 38, 50, 61):
     `"safebreach_mcp_data.data_server.sb_get_tests_history"` ->
     `"safebreach_mcp_data.data_server.sb_get_tests"`
   - Update 4 tool name lookups (lines 29, 41, 53, 64):
     `["get_tests_history"]` -> `["get_tests"]`

3. **`safebreach_mcp_data/tests/test_e2e.py`**:
   - Update import (line 19): `sb_get_tests_history` -> `sb_get_tests`
   - Update 2 function calls (lines 49, 82): `sb_get_tests_history(...)` -> `sb_get_tests(...)`
   - Rename test method (line 80): `test_get_tests_history_e2e` -> `test_get_tests_e2e`

4. **`tests/memory_profile_baseline.py`**:
   - Update import (line 51): `sb_get_tests_history` -> `sb_get_tests`
   - Update 2 function calls (lines 158, 261): `sb_get_tests_history(...)` -> `sb_get_tests(...)`

| File | Change |
|------|--------|
| `safebreach_mcp_data/tests/test_data_functions.py` | Rename imports, 10 methods, 18 calls, 3 patches |
| `safebreach_mcp_data/tests/test_timestamp_normalization.py` | Rename class, 4 patches, 4 lookups |
| `safebreach_mcp_data/tests/test_e2e.py` | Rename import, 2 calls, 1 method |
| `tests/memory_profile_baseline.py` | Rename import, 2 calls |

**Verification**: `uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"`

**Git Commit**: `test(data): update test references for get_tests rename (SAF-30863)`

---

### Phase 4: Update Documentation

**Semantic Change**: Update all documentation to reflect the new tool name and "running" filter

**Deliverables**: All docs consistent with new naming and filter support

**Implementation Details**:

1. **`CLAUDE.md`** (~15 occurrences):
   - Replace all `get_tests_history` with `get_tests` in tool lists, descriptions, examples
   - Update status filter documentation to include "running":
     `Filter by "completed", "canceled", "failed"` -> `Filter by "completed", "canceled", "failed", "running"`
   - Update code examples that call `get_tests_history(...)` to `get_tests(...)`

2. **`README.md`** (~15 occurrences):
   - Mirror all changes from CLAUDE.md (README.md content matches CLAUDE.md for tool documentation)

3. **`DESIGN.md`** (~5 occurrences):
   - Replace `get_tests_history` / `sb_get_tests_history` with `get_tests` / `sb_get_tests`
   - Update function signature documentation and code examples

4. **`E2E_TESTING.md`** (2 occurrences):
   - Update test command: `test_get_tests_history_e2e` -> `test_get_tests_e2e`
   - Update function reference: `sb_get_tests_history` -> `sb_get_tests`

5. **`tests/README.md`** (1 occurrence):
   - Update function reference: `sb_get_tests_history` -> `sb_get_tests`

| File | Change |
|------|--------|
| `CLAUDE.md` | Replace ~15 occurrences + add "running" to status filter docs |
| `README.md` | Replace ~15 occurrences + add "running" to status filter docs |
| `DESIGN.md` | Replace ~5 occurrences |
| `E2E_TESTING.md` | Replace 2 occurrences |
| `tests/README.md` | Replace 1 occurrence |

**Verification**: Grep for any remaining `get_tests_history` references:
`grep -r "get_tests_history" --include="*.md" --include="*.py" .` (expect zero matches outside PRD folder)

**Git Commit**: `docs: update references for get_tests rename + add "running" filter (SAF-30863)`

## 12. Executive Summary

- **Issue Description**: HELM incorrectly tells users no tests are running because the
  `get_tests_history` MCP tool does not advertise "running" as a valid status filter
- **What Was Built**: Added "running" to the status_filter description and renamed the tool from
  `get_tests_history` to `get_tests` to eliminate the misleading "history-only" implication
- **Key Technical Decisions**: Clean rename with no backward compatibility shim — safe because HELM
  discovers tools dynamically and no external consumers were found
- **Scope Changes**: Added tool rename (originally just filter fix) after recognizing the name itself
  contributes to the problem
- **Business Value Delivered**: HELM can now reliably report on running tests, improving user trust
  and reducing false negative responses

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-12 18:00 | PRD created — initial draft |
