# Make manage_test Idempotent with State Pre-Check — SAF-31111

## 1. Overview

- **Task Type**: Bug fix
- **Purpose**: The `manage_test` MCP tool fails when attempting lifecycle actions (cancel, pause,
  resume) on tests that are not in the expected state. The orchestrator API returns 404/500 errors
  for invalid transitions, which propagate as tool failures to LLM agents.
- **Target Consumer**: LLM agents using the SafeBreach MCP server
- **Key Benefits**:
  - Idempotent cancel: canceling an already-canceled/completed test returns success instead of error
  - Clear error messages for invalid transitions (e.g., cancel while paused)
  - Note append failures no longer confuse LLMs with embedded error text
- **Originating Request**: SAF-31111

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Approved |
| **Last Updated** | 2026-05-14 22:30 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

**Chosen Solution**: Add a state pre-check via `GET testsummaries/{test_id}` before executing any
lifecycle action. Map the current state against a transition matrix and either proceed, quick-return
(idempotent), or return an informative error.

**Alternatives Considered**:
- **Catch specific HTTP errors after the fact**: Parse 404/500 responses and translate them. Rejected
  because the orchestrator API error messages are inconsistent (500 for both "no plan was stopped"
  and server crashes) and this approach requires maintaining fragile error parsing.
- **Let the LLM handle retries**: Do nothing and rely on the LLM to understand the error. Rejected
  because LLMs interpret any error text as failure and enter retry loops.

**Decision Rationale**: Pre-checking state is one extra GET per call but provides deterministic
behavior. The data API `testsummaries` endpoint is reliable (verified via E2E testing) and returns
the test status consistently.

## 3. Core Feature Components

### Component A: State Pre-Check and Transition Validation

**Purpose**: Modify `sb_manage_test()` to fetch the test's current state before executing the
lifecycle action. Handle idempotent quick-returns and invalid transitions.

**Key Features**:
- New `_get_test_state()` helper that calls `GET testsummaries/{test_id}` and returns the status
- State transition validation matrix in `sb_manage_test()`:

| Current State | Cancel | Pause | Resume |
|--------------|--------|-------|--------|
| RUNNING | Execute DELETE | Execute PUT | Quick-return: already running |
| PAUSED | Error: resume first | Quick-return: already paused | Execute PUT |
| CANCELED | Quick-return: already canceled | Error: terminal state | Error: terminal state |
| COMPLETED | Quick-return: already completed | Error: terminal state | Error: terminal state |

- Quick-returns set `status="already_<state>"` with `hint_to_agent` explaining the situation
- Invalid transitions raise `ValueError` with actionable guidance

### Component B: Silent Note Append Failures

**Purpose**: Modify the tool response formatting in `studio_server.py` to not expose note append
error text in the tool response. Note failures should be logged but not shown to the LLM.

**Key Features**:
- Remove the `**Note Warning:**` line from the tool response when note append fails
- Keep logging the failure via `logger.warning()` for debugging
- The `note_status` and `note_error` fields remain in the function result dict for internal use

## 4. API Endpoints and Integration

**Existing API Consumed (new usage)**:
- **API Name**: Get Test Summary
- **URL**: `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **Response**: JSON with `status` field — values: `RUNNING`, `PAUSED`, `CANCELED`, `COMPLETED`
- **Already used by**: `_append_test_note()` for comment read/write

## 7. Definition of Done

- [ ] `_get_test_state()` helper function fetches test status via GET testsummaries
- [ ] `sb_manage_test()` calls `_get_test_state()` before `_set_test_state()`
- [ ] Cancel on CANCELED/COMPLETED returns success with `status="already_canceled"` /
  `"already_completed"`
- [ ] Cancel on PAUSED raises ValueError with "resume first" guidance
- [ ] Pause on PAUSED returns success with `status="already_paused"`
- [ ] Resume on RUNNING returns success with `status="already_running"`
- [ ] Actions on terminal states (CANCELED/COMPLETED) for pause/resume raise ValueError
- [ ] Pre-check GET failure propagates as an error (don't silently skip)
- [ ] Note append failures are logged but NOT shown in tool response
- [ ] All existing tests pass
- [ ] Unit tests cover all state transition scenarios
- [ ] E2E test for cancel-on-canceled idempotency

## 8. Testing Strategy

**Unit Testing**:
- **Framework**: pytest with unittest.mock
- **Scope**: All state transition scenarios in `test_studio_functions.py`
- **Key Scenarios**:
  - Cancel on each state (RUNNING, PAUSED, CANCELED, COMPLETED)
  - Pause on each state
  - Resume on each state
  - Pre-check GET failure handling
  - Note append failure no longer in tool response
- **Mocking**: Mock `requests.get` for the testsummaries pre-check, existing mocks for
  `requests.delete`/`requests.put`

**E2E Testing**:
- Add idempotent cancel test: cancel an already-canceled test and verify success response
- Use existing E2E framework in `test_e2e_manage_test.py`

## 9. Implementation Phases

### Phase Status Tracking

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: State pre-check and idempotent handling | ⏳ Pending | - | - | |
| Phase 2: Silent note append failures | ⏳ Pending | - | - | |

---

### Phase 1: State Pre-Check and Idempotent Handling

**Semantic Change**: Add state pre-check to `sb_manage_test()` so lifecycle actions are validated
against the test's current state before execution.

**Deliverables**:
- `_get_test_state()` helper function
- State transition validation in `sb_manage_test()`
- Idempotent quick-returns and informative error messages
- Unit tests for all state transition scenarios
- E2E test for cancel-on-canceled idempotency

**Implementation Details**:

1. **New function `_get_test_state(test_id, console)`** in `studio_functions.py`:
   - Call `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}` (same endpoint as
     `_append_test_note` step 1)
   - Extract and return the `status` field from the response JSON
   - Use the same auth headers pattern as other functions (`get_auth_headers_for_console`)
   - Timeout: 30 seconds
   - On failure: let the exception propagate (caller handles it)
   - Return type: string (e.g., "RUNNING", "PAUSED", "CANCELED", "COMPLETED")

2. **Modify `sb_manage_test()`** — add state pre-check between input validation and
   `_set_test_state()`:
   - Call `_get_test_state(test_id, console)` to get current status
   - Normalize the status to uppercase for comparison
   - Define terminal states: `{"CANCELED", "COMPLETED"}`
   - Define the state transition logic:
     - **Cancel action**:
       - If CANCELED or COMPLETED: return quick-return dict with
         `status="already_canceled"` or `"already_completed"`, `was_already=True`,
         and appropriate `hint_to_agent`
       - If PAUSED: raise `ValueError` with message telling the agent to resume first
       - If RUNNING: proceed to `_set_test_state()`
     - **Pause action**:
       - If PAUSED: return quick-return dict with `status="already_paused"`, `was_already=True`
       - If CANCELED or COMPLETED: raise `ValueError` — cannot pause a terminal test
       - If RUNNING: proceed to `_set_test_state()`
     - **Resume action**:
       - If RUNNING: return quick-return dict with `status="already_running"`, `was_already=True`
       - If CANCELED or COMPLETED: raise `ValueError` — cannot resume a terminal test
       - If PAUSED: proceed to `_set_test_state()`
   - Quick-return dicts include: `test_id`, `action`, `status`, `was_already=True`,
     `current_state`, and `hint_to_agent`
   - Rate limiting: do NOT call `check_limit` or `record_action` for quick-returns
     (no mutation occurred)

3. **Update tool handler** in `studio_server.py` — handle the `was_already` flag:
   - When `result.get('was_already')` is True, format the response to indicate the test was
     already in the desired state (e.g., "Test is already canceled. No action needed.")
   - Include the `hint_to_agent` in the response

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_functions.py` | Add `_get_test_state()`, modify `sb_manage_test()` |
| `safebreach_mcp_studio/studio_server.py` | Update `manage_test` tool handler for `was_already` |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add state transition unit tests |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add cancel-on-canceled E2E test |

**Test Plan**:
- Unit tests for `_get_test_state()`: success, API error
- Unit tests for each cell in the state transition matrix (4 states x 3 actions = 12 tests)
- Unit test that quick-returns do NOT trigger rate limiting
- Unit test that the tool handler formats `was_already` responses correctly
- E2E test: queue a test, cancel it, cancel it again — second cancel returns success

**Git Commit**: `fix(studio): make manage_test idempotent with state pre-check (SAF-31111)`

---

### Phase 2: Silent Note Append Failures

**Semantic Change**: Remove note append error text from the tool response so LLMs don't interpret
it as an operation failure.

**Deliverables**:
- Modified tool response formatting — no `**Note Warning:**` line
- Unit test verifying note failures are not in the tool response

**Implementation Details**:

1. **Modify tool handler** in `studio_server.py`:
   - Remove the `elif result.get('note_status') == 'failed'` block that adds
     `**Note Warning:** Failed to append note — ...` to the response
   - The note failure is already logged via `logger.warning()` in `_append_test_note()`
   - The `note_status` and `note_error` fields remain in the function result dict (internal use)

2. **No changes to `_append_test_note()`** — it already handles errors correctly and logs them

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_server.py` | Remove note failure line from tool response |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add test verifying note error not in response |

**Test Plan**:
- Unit test: call `manage_test` tool handler with a result containing
  `note_status="failed"` — verify the response string does NOT contain "Note Warning"
  or error text

**Git Commit**: `fix(studio): suppress note append errors from manage_test tool response (SAF-31111)`

## 12. Executive Summary

- **Issue**: `manage_test` tool fails with HTTP errors (404/500) when attempting lifecycle actions
  on tests that are not in the expected state (already canceled, completed, or paused)
- **What Was Built**: State pre-check via data API before lifecycle actions, with idempotent
  quick-returns for terminal states and informative errors for invalid transitions
- **Key Technical Decisions**: Pre-check via GET testsummaries (one extra API call) rather than
  post-hoc error parsing; note append errors suppressed from tool response
- **Business Value**: LLM agents no longer enter retry loops on valid no-op scenarios; clearer
  error guidance for invalid state transitions

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-14 22:30 | PRD created — initial draft |
