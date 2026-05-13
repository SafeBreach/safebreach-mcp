# Enrich get_studio_attack_latest_result with Test-Level Context — SAF-30717

## 1. Overview

- **Task Type**: Bug fix
- **Purpose**: `get_studio_attack_latest_result` returns accurate simulation-level data but lacks test-level
  context, causing calling agents to misinterpret results — falsely concluding a test is complete after its
  first simulation finishes, reporting wrong timing (7 seconds vs 3+ minutes), and showing "1 execution found"
  when 22 exist.
- **Target Consumer**: AI agents (Helm agent, Claude) consuming SafeBreach MCP tools
- **Key Benefits**:
  1. Agents can correctly determine whether a test is still running or completed
  2. Agents see test-level timing alongside simulation-level timing, preventing false "done" conclusions
  3. Simulation status breakdown (missed/stopped/prevented/etc.) gives agents immediate posture awareness
- **Business Alignment**: Improves agent reliability and trust in MCP-driven breach simulation workflows
- **Originating Request**: [SAF-30717](https://safebreach.atlassian.net/browse/SAF-30717) — reported by
  Yossi Attas after observing the Helm agent misinterpret results on staging

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-05-13 17:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | Complete |

## 2. Solution Description

### Chosen Solution

Enrich the existing `get_studio_attack_latest_result` response with a **Test Overview** section by making one
additional `GET /testsummaries/{test_id}` call after fetching simulation results. The `test_id` (planRunId) is
already present in each simulation result, so no new user input is required.

Changes are purely **additive** — no existing response fields are modified or removed.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| When to fetch test summary | Always — use `test_id` param or extract from first simulation | Covers the common workflow; agent always gets full context |
| Status breakdown format | Status + count with total line | Compact; agents needing explanations can use `get_test_details` |
| hint_to_agent target | Suggest both: poll this tool OR `get_test_details` | Flexible; doesn't force cross-server knowledge |
| Multiple test runs | Overview for first (latest) test only | `max_results` defaults to 1; covers 99% of usage |
| API call failure | Graceful degradation (try/except, log warning) | Tool still works; test overview is best-effort |

### Alternatives Considered

1. **Add `include_test_overview` parameter** — Rejected: unlikely anyone would opt out; adds unnecessary
   complexity to the tool interface.
2. **Redirect agents to `get_test_details`** — Rejected: forces cross-server dependency; agents shouldn't need
   two tools to understand a single result.
3. **Cache test summaries in studio server** — Rejected: adds cache management complexity for a lightweight
   endpoint that returns quickly; not worth the overhead for this use case.

## 3. Core Feature Components

### Component A: Test Summary Fetch (studio_functions.py)

- **Purpose**: Extend `sb_get_studio_attack_latest_result()` to fetch test summary data after retrieving
  simulation results
- **Key Features**:
  - Determine `test_id`: use the parameter if provided, otherwise extract `planRunId` from the first simulation
  - Call `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
  - Extract: status, startTime, endTime, duration, finalStatus (simulation counts)
  - Compute total simulation count by summing all finalStatus values
  - Add `test_overview` dict to the return value
  - Wrap in try/except: on failure, log warning and set `test_overview` to None
  - Skip entirely when `total_found == 0` (no simulations → no test_id available)

### Component B: Response Formatting (studio_server.py)

- **Purpose**: Add a "Test Overview" section to the formatted markdown response
- **Key Features**:
  - Insert Test Overview section between the header metadata and the first execution result
  - Display: test status, test start/end times, duration, simulation status breakdown with total
  - When test is not in a terminal state (running/queued), add `hint_to_agent` suggesting polling
  - When `test_overview` is None (fetch failed or no simulations), omit the section silently

## 4. API Endpoints and Integration

### Existing API to Consume

- **API Name**: Test Summary (single test)
- **URL**: `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- **Headers**: `Content-Type: application/json`, `x-apitoken: {token}`
- **Response Example**:
  ```json
  {
    "planRunId": "1764570357286.4",
    "planName": "test registry shuit",
    "status": "completed",
    "startTime": "2025-11-02T07:58:00.000Z",
    "endTime": "2025-11-02T08:01:11.000Z",
    "duration": 191000,
    "finalStatus": {
      "missed": 5,
      "stopped": 3,
      "prevented": 10,
      "detected": 2,
      "logged": 1,
      "no-result": 0,
      "inconsistent": 1
    }
  }
  ```
- **Source**: Already used by `safebreach_mcp_data/data_functions.py:_fetch_single_test()`

## 6. Non-Functional Requirements

### Performance Requirements
- The `GET /testsummaries/{test_id}` endpoint is lightweight (single record lookup).
  Expected additional latency: ~100-200ms per invocation.
- No caching needed — the endpoint returns quickly and test status changes frequently
  during running tests (caching would return stale status).

### Technical Constraints
- **Backward Compatibility**: Fully backward compatible — additive changes only.
  No existing response fields are modified or removed.
- **No cross-server dependency**: The studio server calls the data API directly
  (same pattern as its existing `executionsHistoryResults` call). It does not depend on
  the data MCP server.

## 7. Definition of Done

- [x] `sb_get_studio_attack_latest_result()` fetches test summary via `GET /testsummaries/{test_id}`
- [x] Response includes `test_overview` with: status, start_time, end_time, duration, simulation_status_counts,
  total_simulations
- [x] `test_id` is resolved from parameter or extracted from first simulation's `planRunId`
- [x] When `total_found == 0`, test overview is skipped (no crash, no error)
- [x] When test summary API fails, tool returns existing response without test overview (graceful degradation)
- [x] When test status is non-terminal, `hint_to_agent` is included with polling guidance
- [x] Formatted markdown response includes "Test Overview" section before execution details
- [x] Simulation status breakdown shows status + count pairs with a total line
- [x] All existing unit tests pass without modification (additive change)
- [x] New unit tests cover: successful enrichment, graceful degradation, no-simulations skip,
  non-terminal status hint
- [x] CLAUDE.md updated with new response fields documentation

## 8. Testing Strategy

### Unit Testing
- **Scope**: `sb_get_studio_attack_latest_result()` in `studio_functions.py`
- **Key Scenarios**:
  1. Successful test summary fetch — verify `test_overview` fields
  2. Test summary API failure — verify graceful degradation (result still returned, `test_overview` is None)
  3. No simulations found (`total_found=0`) — verify test summary fetch is skipped
  4. Non-terminal test status (running) — verify `hint_to_agent` is present
  5. Terminal test status (completed) — verify no `hint_to_agent`
  6. `test_id` parameter provided — verify it's used directly
  7. `test_id` not provided — verify `planRunId` extracted from first simulation
- **Framework**: pytest (existing)
- **Coverage Target**: Maintain existing coverage; all new code paths tested

### Integration Testing
- Existing cross-server integration tests should continue passing (no behavioral changes to existing fields)

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Test summary fetch logic | ✅ Complete | 2026-05-13 | 2c83fed | TDD: 6 new tests + implementation |
| Phase 2: Response formatting | ✅ Complete | 2026-05-13 | 639c0ce | Test overview section in markdown |
| Phase 3: Unit tests + E2E | ✅ Complete | 2026-05-13 | 70f4a16 | E2E assertions added |
| Phase 4: Documentation | ✅ Complete | 2026-05-13 | 6533060 | CLAUDE.md updated |

### Phase 1: Test Summary Fetch Logic

**Semantic Change**: Add test summary fetching to `sb_get_studio_attack_latest_result()`

**Deliverables**: The function returns a `test_overview` dict alongside existing fields

**Implementation Details**:

1. In `studio_functions.py`, after the existing simulation fetch and transformation block (after line 1346),
   add a test summary fetch:
   - Determine `resolved_test_id`: if `test_id` parameter is provided, use it. Otherwise, extract
     `planRunId` from the first element of `transformed_executions` (key: `test_id`).
   - If `total_found == 0` (no simulations), skip test summary fetch entirely — set `test_overview` to None.
   - Call `GET {base_url}/api/data/v1/accounts/{account_id}/testsummaries/{resolved_test_id}` with the same
     `headers` and `timeout=120` already configured in the function.
   - Call `check_rbac_response(response)` on the response.
   - Parse the JSON response and extract: `status`, `startTime`, `endTime`, `duration`, `finalStatus` dict.
   - Build `simulation_status_counts`: iterate over the `finalStatus` dict, creating a list of
     `{"status": key, "count": value}` pairs for each status type.
   - Compute `total_simulations` by summing all values in the `finalStatus` dict.
   - Determine terminal status: `terminal_statuses = {'completed', 'canceled', 'failed'}`.
   - Build `test_overview` dict with keys: `status`, `start_time`, `end_time`, `duration`,
     `simulation_status_counts`, `total_simulations`.
   - If test status is not in `terminal_statuses`, add `hint_to_agent` to `test_overview` with message:
     `"Test is still {status} ({total_found} of {total_simulations} simulations completed so far).
     Poll this tool again in 30 seconds, or use get_test_details(test_id='{resolved_test_id}',
     console='{console}') from the Data Server for detailed status."`
   - Wrap the entire test summary fetch in a try/except block. On any exception, log a warning
     and set `test_overview` to None.

2. Add `test_overview` to the result dict (alongside `executions`, `returned_count`, etc.).

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add test summary fetch block after simulation processing |

**Git Commit**: `feat(studio): fetch test summary in get_studio_attack_latest_result (SAF-30717)`

### Phase 2: Response Formatting

**Semantic Change**: Format and display the test overview section in the tool's markdown response

**Deliverables**: The formatted response includes a "Test Overview" section between header metadata and
execution details

**Implementation Details**:

1. In `studio_server.py`, in the `get_studio_attack_latest_result` tool function, after building the
   header metadata lines (after line 696, the empty string after "Showing"), insert the test overview
   formatting block:
   - Check if `result['test_overview']` is not None.
   - If present, append a "### Test Overview" section with:
     - `**Test Status:** {status}`
     - `**Test Start Time:** {start_time}`
     - `**Test End Time:** {end_time}` (show "In progress" if empty/None)
     - `**Test Duration:** {duration}` (show "In progress" if empty/None)
     - A blank line, then "**Simulation Status Breakdown:**"
     - For each entry in `simulation_status_counts`: `- {status}: {count}`
     - `- **Total: {total_simulations}**`
   - If `hint_to_agent` is present in `test_overview`, append it as a highlighted line:
     `> **hint_to_agent:** {hint_text}`
   - Append a separator line (`---`) after the test overview section.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_server.py` | Add test overview formatting block in response builder |

**Git Commit**: `feat(studio): format test overview section in latest result response (SAF-30717)`

### Phase 3: Unit Tests

**Semantic Change**: Add unit tests covering all test summary enrichment paths

**Deliverables**: New test cases in `test_studio_functions.py`

**Implementation Details**:

1. Add a mock response fixture for the test summary API that matches the `testsummaries/{test_id}` response
   structure (status, startTime, endTime, duration, finalStatus dict with all 7 status types).

2. Add test cases:
   - **test_get_latest_result_with_test_overview**: Mock both the execution history API and the test summary
     API. Verify the result contains `test_overview` with correct status, timing, simulation_status_counts,
     and total_simulations. Verify the test summary API was called with the correct test_id (extracted from
     first simulation's planRunId).
   - **test_get_latest_result_test_overview_with_test_id_param**: Provide `test_id` parameter explicitly.
     Verify the test summary API is called with the provided test_id, not the simulation's planRunId.
   - **test_get_latest_result_test_overview_running**: Mock test summary with status "running". Verify
     `hint_to_agent` is present in `test_overview` and contains polling guidance.
   - **test_get_latest_result_test_overview_completed**: Mock test summary with status "completed". Verify
     `hint_to_agent` is NOT present in `test_overview`.
   - **test_get_latest_result_test_overview_api_failure**: Mock test summary API to raise an exception.
     Verify `test_overview` is None and the rest of the result is intact (graceful degradation).
   - **test_get_latest_result_no_results_skips_test_overview**: Use the existing no-results test scenario.
     Verify test summary API is NOT called and `test_overview` is None.

3. Update existing test assertions if needed — existing tests should still pass since `test_overview` is a
   new additive field. Existing tests may need to mock the test summary API call to avoid unexpected
   HTTP requests.

4. **E2E test updates** — piggyback on existing E2E tests in `test_e2e.py`:
   - **test_get_studio_attack_latest_result_e2e** (line 424): Inside the `if result['total_found'] > 0:`
     block, add assertions for the new `test_overview` field: verify it is present, and when not None,
     verify it contains `status`, `start_time`, `total_simulations`, and `simulation_status_counts`.
   - **test_debug_flow_e2e** (line 488): After fetching results with a known `test_id`, verify
     `test_overview` is present and its status is a valid value (running, completed, canceled, failed).
     Print test overview fields for diagnostic output.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add test summary mock fixture + 6 new test cases; update existing tests to mock test summary endpoint |
| `safebreach_mcp_studio/tests/test_e2e.py` | Add `test_overview` assertions to 2 existing E2E tests |

**Git Commit**: `test(studio): add unit tests and E2E assertions for test overview enrichment (SAF-30717)`

### Phase 4: Documentation

**Semantic Change**: Update CLAUDE.md with new response fields

**Deliverables**: CLAUDE.md documents the test overview section in `get_studio_attack_latest_result`

**Implementation Details**:

1. In CLAUDE.md, find the Studio Server tools section and update the `get_studio_attack_latest_result`
   description to mention the test overview enrichment: test status, test-level timing, simulation status
   breakdown with total, and hint_to_agent for running tests.

**Changes**:

| File | Change |
|------|--------|
| `CLAUDE.md` | Update Studio Server tool description with test overview fields |

**Git Commit**: `docs: document test overview enrichment in get_studio_attack_latest_result (SAF-30717)`

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Test summary API unavailable | Low — tool degrades gracefully | try/except wrapping; log warning; return response without test overview |
| Stale `planRunId` in simulation | Low — planRunId is an immutable identifier | No mitigation needed; planRunId never changes after creation |
| Extra latency per call | Low — ~100-200ms for lightweight GET | Acceptable tradeoff for the value provided |

### Assumptions

- The `GET /testsummaries/{test_id}` endpoint is available on all SafeBreach consoles with the same
  response schema as used by the data server.
- The `finalStatus` dict in the test summary response always contains all 7 status keys
  (missed, stopped, prevented, detected, logged, no-result, inconsistent). If a key is missing,
  it defaults to 0 via `.get()`.
- The `planRunId` field is always present in simulation results from the `executionsHistoryResults` API.

## 12. Executive Summary

- **Issue**: `get_studio_attack_latest_result` returns simulation-level data without test-level context,
  causing agents to misinterpret test completion status, timing, and simulation counts.
- **What Was Built**: Additive enrichment of the tool's response with a Test Overview section containing
  test status, test-level timing, simulation status breakdown, and polling hints for running tests.
- **Key Technical Decisions**: Always fetch test summary (no opt-out parameter); graceful degradation
  on API failure; compact status+count format without explanations; single test overview even for
  multi-test results.
- **Business Value Delivered**: Agents correctly understand test lifecycle, preventing false "done"
  conclusions and enabling accurate status reporting to users.

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-13 12:00 | PRD created — initial draft |
| 2026-05-13 12:30 | Added E2E test assertions to Phase 3 (piggyback on existing test_e2e.py tests) |
| 2026-05-13 17:00 | All 4 phases implemented via TDD — PRD complete |
