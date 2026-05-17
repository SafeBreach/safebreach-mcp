# Delete Historic Test Results — SAF-29972

## 1. Overview

- **Task Type**: Feature
- **Purpose**: Allow customers and LLM agents to permanently remove test results that have reached
  a terminal state, helping manage retention and preserve disk space on the management console.
- **Target Consumer**: LLM agents using the SafeBreach MCP server; SafeBreach platform administrators
- **Key Benefits**:
  - Clean up accidental or obsolete test runs without manual console intervention
  - Reduce disk usage on the management console
  - Consistent test management experience (pause/resume/cancel/delete) through a single tool
- **Originating Request**: SAF-29972

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-05-17 10:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

**Chosen Solution**: Delegate to a new `sb_delete_test()` function from the existing `sb_manage_test()`
when `action="delete"`. The MCP tool surface stays unchanged — agents use the same `manage_test` tool
with a new action value.

**Alternatives Considered**:
- **Inline in sb_manage_test**: All logic inside the main function. Rejected: makes the function
  too large with delete-specific branching (dry_run, mandatory reason, different API endpoint).
- **Separate MCP tool**: New `delete_test` tool. Rejected: contradicts the JIRA ticket requirement
  and adds unnecessary cognitive load for the LLM agent (two tools to choose from).

**Decision Rationale**: Most LLM-efficient — zero new tool discovery, consistent `manage_test`
pattern. Clean separation of concerns internally via delegation.

## 3. Core Feature Components

### Component A: Delete Test Function (`sb_delete_test`)

**Purpose**: New function in `studio_functions.py` that handles the full delete lifecycle: state
validation, test summary fetch, dry-run preview, and API deletion.

**Key Features**:
- Accepts `test_id`, `console`, `reason` (required), and `dry_run` (default `True`)
- Pre-checks test state via `get_orchestrator_test_state()` — only terminal states allowed
  (`COMPLETED`, `CANCELED`, `FAILED`)
- Fetches test summary from data API to get `planName` and preview data (name, simulation count,
  date range, status)
- **Dry-run mode** (default): returns preview of what will be deleted without executing
- **Execute mode** (`dry_run=False`): calls `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}`
- Rate limiting gates (check before, record after)
- Returns dict with `test_id`, `action`, `status`, preview data, and `hint_to_agent`

### Component B: Integration into `sb_manage_test`

**Purpose**: Extend the existing `sb_manage_test()` to accept `action="delete"` and new parameters
`dry_run`.

**Key Features**:
- Add `"delete"` to `valid_actions`
- Add `dry_run` parameter (default `None` — only meaningful for delete)
- When `action="delete"`: validate `reason` is provided, then delegate to `sb_delete_test()`
- Skip note append for delete (data gets deleted anyway)
- For non-delete actions, `dry_run` parameter is ignored

### Component C: Tool Handler Update

**Purpose**: Update the `manage_test` tool registration in `studio_server.py` to include the
`delete` action and `dry_run` parameter in the description, examples, and response formatting.

**Common use case**: An agent user asks something like "Help me identify and delete cancelled tests
that were launched by sbadmin." The agent would use `get_tests` to find matching tests, then call
`manage_test(action="delete", dry_run=True)` for each to preview storage savings, present the list
to the user, and execute deletions after confirmation.

**Key Features**:
- Update tool description to mention delete action with dry-run workflow
- Clearly state that delete is **irreversible** — test data cannot be restored after deletion
- Add `dry_run` parameter to the tool handler function signature
- Add delete-specific response formatting (preview with storage savings vs post-delete confirmation
  with updated storage headroom)
- Add examples for delete dry-run and execute flows

## 4. API Endpoints and Integration

**Existing API Consumed (new usage)**:
- **API Name**: Get Test Summary (for planName and preview data)
- **URL**: `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **Response**: JSON with `planRunId`, `status`, `originalPlan.name`, simulation statistics, timestamps
- **Already used by**: `_append_test_note()`, `_get_test_state()` (data API fallback)

**Existing API Consumed (new usage)**:
- **API Name**: Delete Test
- **URL**: `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **Request Body**: `{"id": "{test_id}", "planName": "{test_name}"}`
- **Response**: Success (200) or error
- **Note**: This is `/tests/` not `/testsummaries/`

**Existing API Consumed (dry-run storage impact preview)**:
- **API Name**: Detailed Test Summaries
- **URL**: `GET /api/data/v1/accounts/{account_id}/detailedTestSummaries?planRunIds={test_id}`
- **Headers**: `accept: application/json`, `x-apitoken`
- **Response fields** (storage-relevant):
  - `historyIndexLimitSizeInBytes` — configured max limit for test history index; retention kicks
    in when exceeded
  - `historyIndexSizeInBytes` — current size of test history index BEFORE deleting the target test
  - `testSizeBreakdown.executionsHistorySize` — size of the target test in the history index
    (will be removed on deletion)
  - `testSizeBreakdown.integrationLogIndexSize` — volume of associated security events from
    integrated security controls that will be removed from the logs index (separate from history)
- **Called during**: dry-run to show how much space the deletion will free up

**Existing API Consumed (post-delete storage stats)**:
- **API Name**: Database Storage Stats
- **URL**: `GET /api/data/v1/accounts/{account_id}/dbStorageStats`
- **Headers**: `accept: application/json`, `x-apitoken`
- **Response fields**:
  - `executionsHistoryIndexSizeInBytes` — actual volume of test results on disk after deletion
  - `executionsHistoryLimitSizeInBytes` — configured platform limit; retention kicks in when exceeded
  - `executionsHistoryIndexCount` — total number of historic test runs after deletion
  - `executionsHistoryLimitIndexesCount` — configured limit for total test runs
  - `lastTestsCleanupDate` — epoch timestamp of the last test deletion
  - `logHistoryIndexSizeInBytes` — current size of ingested security control events index
- **Called after**: successful delete execution (not on dry-run) to show updated storage headroom

**Existing API Consumed (pre-check)**:
- **API Name**: Orchestrator Queue State
- **URL**: `GET /api/orch/v4/accounts/{account_id}/queue`
- **Already used by**: `get_orchestrator_test_state()` in `queue_state.py`

## 7. Definition of Done

- [ ] `sb_delete_test()` function implements dry-run preview and execute modes
- [ ] `sb_manage_test()` accepts `action="delete"` and delegates to `sb_delete_test()`
- [ ] `reason` is mandatory for delete — raises ValueError if missing
- [ ] `dry_run=True` (default) returns preview without deleting
- [ ] `dry_run=False` executes the deletion via data API
- [ ] Delete only allowed on terminal states (COMPLETED, CANCELED, FAILED)
- [ ] Non-terminal state raises ValueError with guidance to cancel first
- [ ] Rate limiting gates applied (check before, record after — skip on dry-run)
- [ ] No note append for delete action
- [ ] Tool description updated with delete examples and dry-run workflow
- [ ] Response formatting handles delete preview and confirmation
- [ ] All existing manage_test tests still pass
- [ ] Unit tests cover: delete success, dry-run preview, non-terminal rejection, missing reason,
  already-deleted (404), API errors
- [ ] E2E test: queue test, cancel, delete (dry-run then execute), verify 404 on subsequent fetch

## 8. Testing Strategy

**Unit Testing**:
- **Framework**: pytest with unittest.mock
- **Scope**: `sb_delete_test()` function and `sb_manage_test()` integration
- **Key Scenarios**:
  - Delete dry-run returns preview with test name, sim count, status
  - Delete execute calls DELETE API and returns confirmation
  - Delete on RUNNING/PAUSED test raises ValueError
  - Delete without reason raises ValueError
  - Delete on already-deleted test (404) returns informative error
  - Rate limiting: check_limit before execute, record_action after; skip both on dry-run
  - Tool handler formats delete preview and confirmation correctly

**E2E Testing**:
- Queue a test via `sb_run_scenario()`, cancel it, wait for terminal state
- Call delete with `dry_run=True` — verify preview content
- Call delete with `dry_run=False` — verify success
- Call `GET /testsummaries/{test_id}` — verify 404 (test gone)

## 9. Implementation Phases

### Phase Status Tracking

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Validation and dispatch | ✅ Complete | 2026-05-17 | - | 5 tests |
| Phase 2: State pre-check and test summary fetch | ✅ Complete | 2026-05-17 | - | 8 tests |
| Phase 3: Dry-run preview with storage savings | ✅ Complete | 2026-05-17 | - | 4 tests |
| Phase 4: Execute delete with post-delete storage stats | ✅ Complete | 2026-05-17 | - | 8 tests |
| Phase 5: Tool handler and response formatting | ✅ Complete | 2026-05-17 | - | 3 tests |
| Phase 6: E2E test | ✅ Complete | 2026-05-17 | - | 1 E2E test (6-step lifecycle) |
| Phase 7: User lookup and launched_by field | ✅ Complete | 2026-05-17 | - | 8 tests |
| Phase 8: launched_by filter in get_tests | ✅ Complete | 2026-05-17 | - | 5 tests |
| Phase 9: Storage hint in get_test_details | ✅ Complete | 2026-05-17 | - | 2 tests |

---

### Phase 1: Validation and Dispatch

**Semantic Change**: Wire `action="delete"` into `sb_manage_test()` with input validation and
delegation to a new `sb_delete_test()` stub.

**Deliverables**:
- `sb_manage_test()` accepts `"delete"` and `dry_run` parameter
- `sb_delete_test()` stub validates reason is mandatory and delegates
- `sb_manage_test()` dispatches to `sb_delete_test()` early (before lifecycle pre-check)

**Implementation Details**:

1. **Modify `sb_manage_test()`**:
   - Add `dry_run: bool = None` parameter
   - Add `"delete"` to `valid_actions` list
   - Before the state pre-check block: if `action == "delete"`, default `dry_run` to `True` if
     None, then call `sb_delete_test(test_id, console, reason, dry_run)` and return directly

2. **New function `sb_delete_test(test_id, console, reason, dry_run=True)`**:
   - Validate `reason` is non-empty — raise ValueError("reason is required for delete") if
     missing/blank
   - For now, return a placeholder dict: `{"test_id": test_id, "action": "delete",
     "status": "not_implemented"}`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add `sb_delete_test()` stub, modify `sb_manage_test()` |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Tests: delete dispatch, missing reason, invalid action preserved |

**Test Plan**:
- `test_delete_dispatches_to_sb_delete_test` — verify `sb_manage_test(action="delete")` calls
  `sb_delete_test`
- `test_delete_missing_reason_raises` — missing/blank reason raises ValueError
- `test_delete_dry_run_defaults_to_true` — `dry_run=None` defaults to `True`
- `test_existing_actions_unaffected` — pause/resume/cancel still work (regression)

**Git Commit**: `feat(studio): wire delete action into manage_test with validation (SAF-29972)`

---

### Phase 2: State Pre-Check and Test Summary Fetch

**Semantic Change**: Add terminal state validation and test summary fetch to `sb_delete_test()`.

**Deliverables**:
- `_fetch_test_summary()` helper function
- State pre-check rejects non-terminal tests
- Test summary provides planName and preview data

**Implementation Details**:

1. **New function `_fetch_test_summary(test_id, console)`**:
   - Call `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
   - Return the raw JSON response dict
   - On 404: raise ValueError("Test not found")
   - On other errors: let RequestException propagate

2. **Extend `sb_delete_test()`**:
   - Call `_get_test_state(test_id, console)` to check current state
   - If state is not in `{"COMPLETED", "CANCELED", "FAILED"}`: raise ValueError with guidance
     ("Cannot delete a {state} test. Use manage_test with action='cancel' first.")
   - Call `_fetch_test_summary(test_id, console)` to get test details
   - Extract `plan_name` from `originalPlan.name`, `status`, simulation counts from `finalStatus`,
     `startTime`, `endTime`
   - Return dict with `test_id`, `action="delete"`, `status="dry_run"`, `dry_run=True`,
     `preview` dict (test_name, status, simulation_count, date_range) — no storage data yet

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add `_fetch_test_summary()`, extend `sb_delete_test()` |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Tests: state rejection, summary fetch, preview data |

**Test Plan**:
- `test_delete_on_running_raises` — RUNNING state raises ValueError with "cancel first"
- `test_delete_on_paused_raises` — PAUSED state raises ValueError
- `test_delete_on_completed_proceeds` — COMPLETED test passes pre-check
- `test_delete_on_canceled_proceeds` — CANCELED test passes pre-check
- `test_delete_on_failed_proceeds` — FAILED test passes pre-check
- `test_fetch_test_summary_success` — returns raw dict with planName
- `test_fetch_test_summary_404` — raises ValueError
- `test_delete_preview_contains_test_info` — preview has name, status, sim count, dates

**Git Commit**: `feat(studio): add state pre-check and summary fetch for delete (SAF-29972)`

---

### Phase 3: Dry-Run Preview with Storage Savings

**Semantic Change**: Enrich the dry-run preview with storage savings data from the
`detailedTestSummaries` API.

**Deliverables**:
- Storage savings fetch via `detailedTestSummaries` endpoint
- Preview includes `storage_savings` sub-dict

**Implementation Details**:

1. **New function `_fetch_test_storage_info(test_id, console)`**:
   - Call `GET /api/data/v1/accounts/{account_id}/detailedTestSummaries?planRunIds={test_id}`
   - Extract from first result: `historyIndexSizeInBytes`, `historyIndexLimitSizeInBytes`,
     `testSizeBreakdown.executionsHistorySize`, `testSizeBreakdown.integrationLogIndexSize`
   - Return dict with `space_freed_bytes`, `events_freed_bytes`, `current_usage_bytes`,
     `usage_limit_bytes`
   - On any error: return None (best-effort)

2. **Extend `sb_delete_test()` dry-run path**:
   - After building preview, call `_fetch_test_storage_info(test_id, console)`
   - If storage info available, add `storage_savings` sub-dict to the preview
   - Add `hint_to_agent` telling the agent to call again with `dry_run=False` to execute

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add `_fetch_test_storage_info()`, extend dry-run path |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Tests: storage savings in preview, API failure graceful |

**Test Plan**:
- `test_dry_run_includes_storage_savings` — preview contains space_freed_bytes, etc.
- `test_dry_run_storage_fetch_failure_graceful` — preview still returned without storage on API error
- `test_dry_run_hint_to_agent` — hint tells agent to call with `dry_run=False`

**Git Commit**: `feat(studio): add storage savings preview to delete dry-run (SAF-29972)`

---

### Phase 4: Execute Delete with Post-Delete Storage Stats

**Semantic Change**: Implement the actual delete execution path with rate limiting and post-delete
storage stats.

**Deliverables**:
- DELETE API call to `/tests/{test_id}`
- Rate limiting gates (skip on dry-run)
- Post-delete storage stats via `dbStorageStats`

**Implementation Details**:

1. **Extend `sb_delete_test()` execute path** (`dry_run=False`):
   - Rate limiting: `check_limit(caller_id, "manage_test")`
   - Call `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}` with body
     `{"id": test_id, "planName": plan_name}` — use data API base URL
   - `check_rbac_response(response)`
   - Rate limiting: `record_action(caller_id, "manage_test")`
   - Log: `logger.info(f"Test {test_id} deleted. Reason: {reason}")`

2. **New function `_fetch_storage_stats(console)`**:
   - Call `GET /api/data/v1/accounts/{account_id}/dbStorageStats`
   - Return dict with `tests_on_disk_bytes`, `tests_limit_bytes`, `tests_on_disk_count`,
     `tests_limit_count`, `last_cleanup_date`, `events_index_bytes`
   - On any error: return None (best-effort)

3. **Extend execute path**:
   - After successful delete, call `_fetch_storage_stats(console)`
   - Include in response as `storage_stats`
   - Return dict with `test_id`, `action="delete"`, `status="deleted"`, `deleted_test_name`,
     `reason`, `storage_stats`, `hint_to_agent`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add execute path, `_fetch_storage_stats()` |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Tests: delete execute, storage stats, API errors |
| `safebreach_mcp_studio/tests/test_rate_limiting.py` | Tests: rate limit gates, dry-run skip |

**Test Plan**:
- `test_delete_execute_calls_delete_api` — verifies DELETE to `/tests/` with correct body
- `test_delete_execute_returns_deleted_status` — status="deleted", includes test name and reason
- `test_delete_execute_includes_storage_stats` — post-delete stats in response
- `test_delete_execute_storage_failure_graceful` — deletion succeeds even if stats fetch fails
- `test_delete_rate_limit_check_before_delete` — check_limit called before DELETE
- `test_delete_rate_limit_record_after_success` — record_action called after DELETE
- `test_delete_dry_run_skips_rate_limit` — neither check_limit nor record_action on dry-run
- `test_delete_api_error_propagates` — HTTP error from DELETE propagates

**Git Commit**: `feat(studio): implement delete execution with storage stats (SAF-29972)`

---

### Phase 5: Tool Handler and Response Formatting

**Semantic Change**: Update the MCP tool registration and response formatting for delete action.

**Deliverables**:
- Updated tool description with delete documentation and irreversibility warning
- `dry_run` parameter on tool handler
- Delete-specific response formatting (preview with storage savings, confirmation with headroom)

**Implementation Details**:

1. **Update tool description** in `studio_server.py`:
   - Add `"delete"` to the action parameter: "pause", "resume", "cancel", or "delete"
   - Document `dry_run`: only used with delete, defaults to True, preview before irreversible action
   - Document that `reason` is **required** for delete
   - State clearly: "Delete is **irreversible** — test data cannot be restored after deletion"
   - Add examples for delete dry-run and execute

2. **Add `dry_run` parameter** to tool handler: `dry_run: bool = None`

3. **Add delete response formatting**:
   - **Dry-run**: heading "Delete Preview", test info, storage savings (human-readable bytes,
     e.g., "2.0 GB freed"), usage bar ("8.0 GB / 45.0 GB used"), hint to execute
   - **Execute**: heading "Test Deleted", deleted test name, reason, updated storage headroom,
     hint for next steps
   - Handle missing storage data gracefully (omit section)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_server.py` | Update description, add dry_run, add formatting |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Tests: handler formatting for preview and execute |

**Test Plan**:
- `test_tool_handler_delete_preview_format` — response contains "Delete Preview", storage savings
- `test_tool_handler_delete_execute_format` — response contains "Test Deleted", reason, storage
- `test_tool_handler_delete_missing_reason_error` — ValueError formatted as error message

**Git Commit**: `feat(studio): update manage_test tool handler for delete action (SAF-29972)`

---

### Phase 6: E2E Test

**Semantic Change**: End-to-end test verifying the full delete lifecycle against a real console.

**Deliverables**:
- E2E test: queue → cancel → delete dry-run → delete execute → verify gone

**Implementation Details**:

1. **New E2E test `test_e2e_delete_test`** in `test_e2e_manage_test.py`:
   - Queue a test via `sb_run_scenario()`
   - Cancel it via `sb_manage_test(action="cancel")`
   - Wait for terminal state propagation (10s, matching cancel-on-canceled pattern)
   - Call `sb_manage_test(action="delete", dry_run=True, reason="E2E cleanup")` — verify
     `status="dry_run"`, preview contains test name, storage_savings present
   - Call `sb_manage_test(action="delete", dry_run=False, reason="E2E cleanup")` — verify
     `status="deleted"`, storage_stats present
   - Call `GET /testsummaries/{test_id}` directly — verify 404 (test removed from history)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add `test_e2e_delete_test` |

**Test Plan**:
- Single E2E test covering full lifecycle with both dry-run and execute

**Git Commit**: `test(studio): add E2E test for delete action lifecycle (SAF-29972)`

---

### Phase 7: User Lookup and `launched_by` Field

**Semantic Change**: Resolve numeric `ranBy`/`userId` to human-readable usernames and expose
as `launched_by` in `get_tests` and `get_test_details` responses.

**Deliverables**:
- User lookup helper in core (fetches users from config API, cached, graceful failure)
- `launched_by` field added to test summary mapping
- `get_test_details` includes `launched_by`

**Implementation Details**:

1. **New module `safebreach_mcp_core/user_lookup.py`** (follows `suggestions.py` pattern):
   - Module-level `SafeBreachCache(name="users", maxsize=5, ttl=3600)` — long TTL, users rarely change
   - Cache is **always-on** (not gated by `is_caching_enabled`) since user lookup is a cross-cutting
     concern used across servers and the data changes infrequently
   - Function `get_user_name(user_id, console)` → returns username string or None
   - Internal `_fetch_users_map(console)` → calls
     `GET /api/config/v1/accounts/{account_id}/users?details=false&deleted=true`
     on the **config** API, returns `{user_id: user_name}` dict, cached per console
   - On any error (e.g., 403 insufficient permissions): log warning, return empty dict
   - This is best-effort — missing user data should not break test listing

2. **Extend `get_reduced_test_summary_mapping()` in `data_types.py`**:
   - Add `ranBy` to `reduced_test_summary_mapping`: `'ran_by_user_id': 'ranBy'`
   - The raw numeric ID is always included

3. **Add `launched_by` resolution in `data_functions.py`**:
   - After building the reduced test summary, call `_fetch_users(console)` to get the lookup
   - Resolve `ran_by_user_id` → `launched_by` (username string)
   - If user not found in lookup, set `launched_by` to None
   - Apply to both `sb_get_tests()` (list) and `sb_get_test_details()` (single)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_core/user_lookup.py` | New module: `get_user_name()`, `_fetch_users_map()`, cached |
| `safebreach_mcp_data/data_functions.py` | Enrich tests with `launched_by` via `get_user_name()` |
| `safebreach_mcp_data/data_types.py` | Add `ran_by_user_id` to mapping |
| `safebreach_mcp_data/tests/test_data_functions.py` | Tests: user lookup, resolution, API failure graceful |

**Test Plan**:
- `test_fetch_users_success` — returns {id: name} dict
- `test_fetch_users_api_error_returns_empty` — graceful on 403
- `test_launched_by_resolved_in_test_details` — username appears in response
- `test_launched_by_none_when_user_unknown` — unknown userId → None

**Git Commit**: `feat(data): add launched_by field to test results via user lookup (SAF-29972)`

---

### Phase 8: `launched_by` Filter in `get_tests`

**Semantic Change**: Add `launched_by_filter` parameter to `get_tests` for filtering tests by
launcher username.

**Deliverables**:
- `launched_by_filter` parameter in `sb_get_tests()` and `get_tests` tool
- Case-insensitive partial match on resolved username

**Implementation Details**:

1. **Extend `sb_get_tests()` in `data_functions.py`**:
   - Add `launched_by_filter: str = None` parameter
   - After enriching tests with `launched_by`, filter by case-insensitive partial match
     (same pattern as `name_filter`)
   - Include filter in response metadata

2. **Update `get_tests` tool** in `data_server.py`:
   - Add `launched_by_filter` parameter to tool handler
   - Add to tool description with example

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add `launched_by_filter` to `sb_get_tests()` |
| `safebreach_mcp_data/data_server.py` | Add `launched_by_filter` to tool handler |
| `safebreach_mcp_data/tests/test_data_functions.py` | Tests: filter matching, case-insensitive |

**Test Plan**:
- `test_launched_by_filter_matches` — "sbadmin" matches test launched by "sbadmin"
- `test_launched_by_filter_case_insensitive` — "SBAdmin" matches "sbadmin"
- `test_launched_by_filter_partial_match` — "admin" matches "sbadmin"
- `test_launched_by_filter_no_match` — returns empty when no tests match

**Git Commit**: `feat(data): add launched_by_filter to get_tests (SAF-29972)`

---

### Phase 9: Storage Hint in `get_test_details`

**Semantic Change**: Add a `hint_to_agent` in `get_test_details` for terminal tests, guiding the
agent to use `manage_test(action="delete", dry_run=True)` for storage estimation.

**Deliverables**:
- Hint added to terminal test details response

**Implementation Details**:

1. **Extend `sb_get_test_details()` in `data_functions.py`**:
   - After building the response, if the test status is terminal (completed/canceled/failed),
     add `hint_to_agent`: "To see how much space this test uses and preview deletion, call
     manage_test with action='delete' and dry_run=True."
   - Only add if not already present (avoid overwriting existing hints)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add storage hint for terminal tests |
| `safebreach_mcp_data/tests/test_data_functions.py` | Test: hint present for terminal, absent for running |

**Test Plan**:
- `test_terminal_test_has_delete_hint` — completed test includes delete hint
- `test_running_test_no_delete_hint` — running test does not include delete hint

**Git Commit**: `feat(data): add storage hint for terminal tests in get_test_details (SAF-29972)`

## 10. Risks and Assumptions

**Technical Risks**:
- **Irreversible operation** (High): Delete permanently removes test data. Mitigated by dry-run
  confirmation pattern and mandatory reason.
- **404 on already-deleted test** (Low): Agent might try to delete a test that was already deleted
  (by another agent or UI). The DELETE API should return 404 — handle gracefully with an informative
  message.

**Assumptions**:
- The `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}` endpoint exists and accepts the
  documented request body format. Verified via browser curl.
- The `planName` field is available in the test summary response under `originalPlan.name`.

## 12. Executive Summary

- **Feature**: Add `delete` action to the `manage_test` MCP tool for permanent removal of terminal
  test results
- **What Was Built**: Dry-run confirmation workflow, terminal state validation via orchestrator queue,
  deletion via data API with audit logging
- **Key Technical Decisions**: Delegate pattern (separate `sb_delete_test` function), dry-run as
  default for safety, orchestrator queue pre-check for state validation
- **Business Value**: Customers can manage test retention through the MCP agent, reducing manual
  console maintenance and disk usage

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-17 10:00 | PRD created — initial draft |
