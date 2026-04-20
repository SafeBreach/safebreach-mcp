# Test Lifecycle Management Tool — SAF-29969

## 1. Overview

- **Task Type**: Feature
- **Purpose**: Enable AI agents to manage running SafeBreach test executions by pausing,
  resuming, or cancelling them via a single MCP tool, with optional audit trail.
- **Target Consumer**: AI agents (LLMs) interacting with SafeBreach via MCP protocol
- **Key Benefits**:
  - Agents gain full test lifecycle control (queue + manage)
  - Optional `reason` parameter creates an audit trail in the test's notes
  - Single tool design reduces LLM tool discovery overhead
- **Business Alignment**: Completes the test execution lifecycle in the MCP layer — agents
  can now queue tests (`run_scenario`) AND manage them (`manage_test`)
- **Originating Request**: [SAF-29969](https://safebreach.atlassian.net/browse/SAF-29969),
  linked to parent story SAF-29859 (MCP basic actions, part 1)

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | In Progress |
| **Last Updated** | 2026-04-20 13:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | Phase 3 of 7 |

---

## 2. Solution Description

### Chosen Solution

A single `manage_test` MCP tool with an `action` parameter (`pause`, `resume`, `cancel`) and an
optional `reason` parameter. Internally split into two helpers:

- `_set_test_state(test_id, action, console)` — calls the orchestrator API to change test state
- `_append_test_note(test_id, action, reason, console)` — calls the data API to append a
  timestamped note to the test's `comment` field

The public function `sb_manage_test` orchestrates both: it performs the lifecycle action first,
then appends the note if `reason` is provided. Note append is best-effort — failure does not
block the lifecycle operation.

### Alternatives Considered

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| A: Monolithic | Single function handles lifecycle + notes | Simplest code | Mixes API domains, harder to test independently |
| B: Split helpers | Separate lifecycle and notes functions (chosen) | Clean SRP, independently testable, reusable note helper | More functions |
| C: Per-action functions | Private function per action + orchestrator | Explicit per action | Over-engineering for 2 URL patterns |

### Decision Rationale

Approach B was chosen because it cleanly separates the two API domains (orchestrator for
lifecycle, data for notes), making each independently testable. The `_append_test_note` helper
is reusable by future tools that may need to annotate tests.

---

## 3. Core Feature Components

### Component A: Test Lifecycle State Manager (`_set_test_state`)

- **Purpose**: New private helper in `studio_functions.py` that calls the SafeBreach
  orchestrator API to change a running test's state.
- **Key Features**:
  - Validates `action` against allowed values: `pause`, `resume`, `cancel`
  - Routes to correct HTTP method: PUT for pause/resume, DELETE for cancel
  - Pause/resume: `PUT /api/orch/v4/accounts/{id}/queue/{test_id}/state`
    with body `{"status": "pause"|"resume"}`
  - Cancel: `DELETE /api/orch/v4/accounts/{id}/queue/{test_id}` (no body)
  - Uses existing auth pattern: `get_secret_for_console`, `get_api_base_url('orchestrator')`,
    `get_api_account_id`
  - Returns dict with `test_id`, `action`, `status` (success indicator)

### Component B: Test Note Appender (`_append_test_note`)

- **Purpose**: New private helper in `studio_functions.py` that appends a timestamped
  note to a test's `comment` field via the data API.
- **Key Features**:
  - Reads existing comment: `GET /api/data/v1/accounts/{id}/testsummaries/{test_id}`
  - Formats new note: `[YYYY-MM-DD HH:MM:SS UTC] Test {action}: {reason}`
  - Concatenates: existing comment + `\n` + new note (handles null/empty existing)
  - Writes back: `PUT /api/data/v1/accounts/{id}/testsummaries/{test_id}`
    with `{"comment": "concatenated_text"}`
  - Best-effort: logs warning on failure, returns status dict, does not raise

### Component C: Public Orchestrator (`sb_manage_test`)

- **Purpose**: New public function in `studio_functions.py` that orchestrates lifecycle +
  optional note append.
- **Key Features**:
  - Parameters: `test_id: str`, `action: str`, `console: str = "default"`,
    `reason: str = None`
  - Validates inputs (non-empty test_id, valid action)
  - Calls `_set_test_state` for the lifecycle operation
  - If `reason` is provided, calls `_append_test_note` (best-effort)
  - Returns combined result dict with lifecycle status + note status + `hint_to_agent`
  - `hint_to_agent` is contextual per action:
    - pause: suggests resume or cancel, and checking status via `get_test_details`
    - resume: suggests monitoring via `get_test_details`
    - cancel: notes partial results may be available via `get_test_details`

### Component D: MCP Tool Registration (`manage_test`)

- **Purpose**: New tool registration in `studio_server.py` that exposes `sb_manage_test`
  as an MCP tool.
- **Key Features**:
  - Tool name: `manage_test`
  - Description: multi-line with Parameters, Returns, Example sections
  - Return type: `str` (Markdown formatted)
  - Calls `sb_manage_test()` and formats result as Markdown
  - Error handling: try/except ValueError/Exception returning error strings
  - Includes `hint_to_agent` in the Markdown response

---

## 4. API Endpoints and Integration

### Existing APIs to Consume

**1. Pause/Resume Test State**
- **URL**: `PUT /api/orch/v4/accounts/{account_id}/queue/{test_id}/state`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Request Payload**:
  ```json
  {"status": "pause"}
  ```
  or
  ```json
  {"status": "resume"}
  ```
- **Auth**: `get_api_base_url(console, 'orchestrator')`

**2. Cancel Test**
- **URL**: `DELETE /api/orch/v4/accounts/{account_id}/queue/{test_id}`
- **Headers**: `x-apitoken: {token}`
- **No request body**
- **Auth**: `get_api_base_url(console, 'orchestrator')`

**3. Read Test Summary (for existing comment)**
- **URL**: `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Response**: JSON object with `comment` field (may be null or string)
- **Auth**: `get_api_base_url(console, 'data')`

**4. Update Test Summary (to write comment)**
- **URL**: `PUT /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Request Payload**:
  ```json
  {"comment": "existing comment\n[2026-04-20 14:30:00 UTC] Test paused: reason text"}
  ```
- **Auth**: `get_api_base_url(console, 'data')`

---

## 6. Non-Functional Requirements

### Security & Compliance

- **Secrets Management**: Uses existing `get_secret_for_console(console)` — no new secret
  storage needed
- **Authentication**: `x-apitoken` header pattern, consistent with all existing Studio tools
- **RBAC**: Inherits SafeBreach API-level RBAC — the API token's permissions determine
  whether pause/resume/cancel is allowed

### Technical Constraints

- **Integration**: Studio Server (port 8004), alongside `run_scenario`
- **Backward Compatibility**: New tool only, no changes to existing tools
- **Test IDs**: Dot-notation format (e.g., `1776488350786.15`) — must be passed as strings

---

## 7. Definition of Done

- [ ] `sb_manage_test` function implemented in `studio_functions.py` with `_set_test_state`
  and `_append_test_note` helpers
- [ ] `manage_test` MCP tool registered in `studio_server.py` with full description
- [ ] All three actions work: pause, resume, cancel
- [ ] Optional `reason` appends timestamped UTC note to test comment field
- [ ] Note append handles null/empty existing comments
- [ ] Note append failure does not block lifecycle operation
- [ ] `hint_to_agent` included in response, contextual per action
- [ ] Input validation: empty test_id, invalid action values
- [ ] Error handling: 404, 409, network errors return meaningful messages
- [ ] Unit tests: success, not-found, API error, reason/note, edge cases for all actions
- [ ] E2E tests: cancel test lifecycle (extend test_e2e_run_scenario.py)
- [x] All existing tests continue to pass

---

## 8. Testing Strategy

**Methodology: Pure TDD (Red-Green-Refactor)**

Every slice follows the same cycle:
1. **Red** — Write failing tests that define the expected behavior
2. **Green** — Write the minimum code to make tests pass
3. **Refactor** — Clean up while keeping tests green
4. **Commit** — One commit per slice (test + implementation together)

### Unit Testing

- **Framework**: pytest with unittest.mock
- **Mock Pattern**:
  - `@patch('safebreach_mcp_studio.studio_functions.requests.put')`
  - `@patch('safebreach_mcp_studio.studio_functions.requests.delete')`
  - `@patch('safebreach_mcp_studio.studio_functions.requests.get')`
  - Auth mocks: `mock_secret`, `mock_base_url`, `mock_account_id`
- **Coverage Target**: Maintain existing coverage baseline
- Tests are written FIRST in every phase — no production code without a failing test

### E2E Testing

- **Approach**: E2E test is created in Phase 1 and extended with each subsequent phase
- **Markers**: `@pytest.mark.e2e`, `@skip_e2e`
- **Environment**: Requires real SafeBreach console (E2E_CONSOLE env var)
- **File**: `test_e2e_manage_test.py` (new, dedicated file)
- **Growth**: Phase 1 creates the E2E skeleton (cancel), later phases extend it
  (pause, resume, reason/notes)

---

## 9. Implementation Phases

**Strategy: Elephant Carpaccio + Pure TDD**

Each phase is the thinnest possible vertical slice delivering end-to-end value.
Every phase follows Red-Green-Refactor: write failing tests first, then implement
the minimum code to pass. Each phase produces a working, tested, committable increment.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Cancel test (end-to-end) | ✅ Complete | 2026-04-20 | TBD | 4 unit + 1 E2E test |
| Phase 2: Pause test | ✅ Complete | 2026-04-20 | TBD | PUT /state with pause body |
| Phase 3: Resume test | ✅ Complete | 2026-04-20 | TBD | Same PUT, resume body |
| Phase 4: Input validation | ⏳ Pending | - | - | Guard rails (unit tests only) |
| Phase 5: Reason notes | ⏳ Pending | - | - | Read-then-append + extends E2E |
| Phase 6: Note resilience | ⏳ Pending | - | - | Best-effort (unit tests only) |
| Phase 7: hint_to_agent + Documentation | ⏳ Pending | - | - | LLM guidance + CLAUDE.md |

---

### Phase 1: Cancel Test (End-to-End Vertical Slice)

**Semantic Change**: Deliver a working `manage_test` tool that can cancel a running test.

This is the thinnest slice because cancel uses DELETE with no body — the simplest
HTTP pattern. After this phase, an agent can cancel a test end-to-end.

**TDD Cycle**:

**Red — Write failing tests:**

*Unit tests (`test_studio_functions.py`):*
1. In `test_studio_functions.py`, create `TestManageTest` class
2. `test_cancel_success`: mock auth + mock DELETE returning 200 →
   call `sb_manage_test(test_id="1776488350786.15", action="cancel", console="test")` →
   assert returns dict with `test_id`, `action="cancel"`, `status="success"` →
   assert DELETE called once with URL
   `https://test.safebreach.com/api/orch/v4/accounts/1234567890/queue/1776488350786.15`,
   header `x-apitoken`, timeout 30
3. `test_cancel_api_error`: mock DELETE raising `requests.exceptions.RequestException` →
   assert `sb_manage_test` propagates the exception
4. `test_cancel_tool_success`: call the tool function `manage_test(...)` directly →
   assert returns Markdown string containing `## Test Cancel` and test_id
5. `test_cancel_tool_error`: mock to raise → assert returns error string (no exception)

*E2E test (`test_e2e_manage_test.py` — new file):*
6. Create `test_e2e_manage_test.py` with `@pytest.mark.e2e`, `@skip_e2e` decorators
7. `test_e2e_cancel_test`: queue a small test via `sb_run_scenario`, extract `test_id`,
   call `sb_manage_test(test_id, action="cancel", console=E2E_CONSOLE)`,
   assert result has `status="success"` and `action="cancel"`,
   use try/finally to ensure test is cancelled even on assertion failure

**Green — Implement minimum code:**
1. In `studio_functions.py`:
   - Add `_set_test_state(test_id, action, console)` — initially handles cancel only
     - Auth: `get_secret_for_console`, `get_api_base_url(console, 'orchestrator')`,
       `get_api_account_id`
     - URL: `{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}`
     - DELETE request with `{"x-apitoken": apitoken}` header, timeout 30s
     - `response.raise_for_status()`, log info/error
     - Return `{"test_id": test_id, "action": action, "status": "success"}`
   - Add `sb_manage_test(test_id, action, console, reason)` — thin wrapper that
     calls `_set_test_state`, returns its result
2. In `studio_server.py`:
   - Register `manage_test` tool with `@self.mcp.tool()` decorator
   - Tool calls `sb_manage_test()`, formats result as Markdown
   - try/except ValueError/Exception returning error strings

**Refactor**: Verify all tests green, clean up.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add `TestManageTest` with cancel tests |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Create E2E skeleton with cancel test |
| `safebreach_mcp_studio/studio_functions.py` | Add `_set_test_state` (cancel), `sb_manage_test` |
| `safebreach_mcp_studio/studio_server.py` | Register `manage_test` tool |

**Git Commit**: `feat(studio): add manage_test tool with cancel support [TDD]`

---

### Phase 2: Pause Test

**Semantic Change**: Extend `manage_test` to support pausing a running test.

Adds PUT with JSON body — slightly more complex than DELETE.

**TDD Cycle**:

**Red — Write failing tests:**

*Unit tests:*
1. `test_pause_success`: mock auth + mock PUT returning 200 →
   call `sb_manage_test(test_id="...", action="pause")` →
   assert returns dict with `action="pause"`, `status="success"` →
   assert PUT called with URL `.../queue/{test_id}/state`,
   JSON body `{"status": "pause"}`, Content-Type header, timeout 120s

*E2E test (extend `test_e2e_manage_test.py`):*
2. `test_e2e_pause_test`: queue a test, call `sb_manage_test(test_id, action="pause")`,
   assert result has `status="success"`, cancel test in cleanup

**Green — Extend `_set_test_state`:**
1. Add pause branch: if action is "pause":
   - URL: `{base_url}/api/orch/v4/accounts/{account_id}/queue/{test_id}/state`
   - PUT with `json={"status": "pause"}`, headers with Content-Type, timeout 120s

**Refactor**: All tests green including Phase 1 cancel tests.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add `test_pause_success` |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add `test_e2e_pause_test` |
| `safebreach_mcp_studio/studio_functions.py` | Extend `_set_test_state` for pause |

**Git Commit**: `feat(studio): add pause support to manage_test [TDD]`

---

### Phase 3: Resume Test

**Semantic Change**: Extend `manage_test` to support resuming a paused test.

Same endpoint as pause, different body — trivial extension.

**TDD Cycle**:

**Red — Write failing tests:**

*Unit tests:*
1. `test_resume_success`: mock auth + mock PUT returning 200 →
   call `sb_manage_test(test_id="...", action="resume")` →
   assert returns dict with `action="resume"`, `status="success"` →
   assert PUT called with JSON body `{"status": "resume"}`

*E2E test (extend `test_e2e_manage_test.py`):*
2. `test_e2e_pause_and_resume_test`: queue a test, pause it, then resume it,
   assert both operations return `status="success"`, cancel test in cleanup.
   This is the full pause→resume lifecycle in a single E2E test.

**Green — Extend `_set_test_state`:**
1. Resume uses the same code path as pause — the action value is already passed as
   the `"status"` field in the PUT body. If pause was implemented with `{"status": action}`,
   resume works with zero code changes (just the test proves it).

**Refactor**: Verify all previous tests still green.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add `test_resume_success` |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add `test_e2e_pause_and_resume_test` |
| `safebreach_mcp_studio/studio_functions.py` | May need no change if pause used generic `action` |

**Git Commit**: `feat(studio): add resume support to manage_test [TDD]`

---

### Phase 4: Input Validation

**Semantic Change**: Add guard rails for invalid inputs.

**TDD Cycle**:

**Red — Write failing tests:**
1. `test_invalid_action`: call `sb_manage_test(test_id="...", action="stop")` →
   assert raises `ValueError` with message containing valid actions
2. `test_empty_test_id`: call `sb_manage_test(test_id="", action="cancel")` →
   assert raises `ValueError("test_id is required")`
3. `test_none_test_id`: call `sb_manage_test(test_id=None, action="cancel")` →
   assert raises `ValueError`
4. `test_not_found_404`: mock DELETE returning 404 with `raise_for_status` raising
   HTTPError → assert exception propagates with meaningful context

**Green — Add validation to `sb_manage_test`:**
1. Check test_id is non-empty/non-None, raise ValueError if not
2. Check action is in `["pause", "resume", "cancel"]`, raise ValueError with valid values
3. HTTP errors already propagate from `_set_test_state` — just verify they do

**Refactor**: All tests green.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add validation tests |
| `safebreach_mcp_studio/studio_functions.py` | Add input validation to `sb_manage_test` |

**Git Commit**: `feat(studio): add input validation to manage_test [TDD]`

---

### Phase 5: Reason Notes

**Semantic Change**: Add optional `reason` parameter that appends a timestamped note to the
test's comment field.

**TDD Cycle**:

**Red — Write failing tests:**
1. `test_append_to_existing_comment`: mock GET returning `{"comment": "existing note"}` +
   mock PUT returning 200 →
   call `_append_test_note(test_id, "pause", "maintenance window", console)` →
   assert PUT called with body containing
   `"existing note\n[YYYY-MM-DD HH:MM:SS UTC] Test pause: maintenance window"`
2. `test_append_to_null_comment`: mock GET returning `{"comment": null}` →
   assert PUT called with just the new note (no leading newline)
3. `test_append_to_empty_comment`: mock GET returning `{"comment": ""}` →
   assert PUT called with just the new note
4. `test_manage_test_with_reason`: mock lifecycle + mock note helpers →
   call `sb_manage_test(test_id, "cancel", reason="no longer needed")` →
   assert result contains `note_status="success"` and `note` text
5. `test_manage_test_without_reason`: mock lifecycle →
   call `sb_manage_test(test_id, "cancel")` →
   assert `_append_test_note` is NOT called, result has no `note_status`

*E2E test (extend `test_e2e_manage_test.py`):*
6. `test_e2e_cancel_with_reason`: queue a test, cancel with
   `reason="E2E automated cleanup"`, assert `note_status="success"`,
   optionally GET the test summary and verify `comment` field contains the note text

**Green — Implement `_append_test_note` + wire into `sb_manage_test`:**
1. Add `_append_test_note(test_id, action, reason, console)`:
   - Auth via `get_api_base_url(console, 'data')`
   - URL: `{base_url}/api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
   - GET existing comment (extract `comment` field, handle null/empty)
   - Format note: `[{utc_timestamp} UTC] Test {action}: {reason}`
   - Concatenate: `existing + "\n" + new_note` (or just `new_note` if empty)
   - PUT with `{"comment": concatenated}`
   - Return `{"note_status": "success", "note": new_note}`
2. In `sb_manage_test`: if reason is provided and non-empty, call `_append_test_note`
   and merge result

**Refactor**: All tests green.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add note tests |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | Add `test_e2e_cancel_with_reason` |
| `safebreach_mcp_studio/studio_functions.py` | Add `_append_test_note`, wire into `sb_manage_test` |

**Git Commit**: `feat(studio): add reason/notes support to manage_test [TDD]`

---

### Phase 6: Note Resilience

**Semantic Change**: Ensure note append failure does not block the lifecycle operation.

**TDD Cycle**:

**Red — Write failing tests:**
1. `test_note_get_failure`: mock GET raising exception →
   call `_append_test_note(...)` →
   assert returns `{"note_status": "failed", "note_error": "..."}`, does NOT raise
2. `test_note_put_failure`: mock GET succeeds, mock PUT raises exception →
   assert returns failure status, does NOT raise
3. `test_manage_test_note_failure_doesnt_block`: mock lifecycle succeeds,
   mock `_append_test_note` returning `{"note_status": "failed"}` →
   call `sb_manage_test(test_id, "pause", reason="test")` →
   assert result has `status="success"` (lifecycle succeeded) AND
   `note_status="failed"` (note failed but didn't block)

**Green — Add error handling to `_append_test_note`:**
1. Wrap entire `_append_test_note` body in try/except Exception
2. On any exception: log warning, return `{"note_status": "failed", "note_error": str(e)}`
3. `sb_manage_test` already merges results — note failure naturally coexists with
   lifecycle success

**Refactor**: All tests green. Update tool Markdown output in `studio_server.py` to show
note warning when `note_status="failed"`.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add resilience tests |
| `safebreach_mcp_studio/studio_functions.py` | Add try/except to `_append_test_note` |
| `safebreach_mcp_studio/studio_server.py` | Show note warning in Markdown output |

**Git Commit**: `feat(studio): add note failure resilience to manage_test [TDD]`

---

### Phase 7: hint_to_agent + Documentation

**Semantic Change**: Add contextual LLM guidance per action and update project documentation.

**TDD Cycle**:

**Red — Write failing tests:**
1. `test_pause_hint`: call `sb_manage_test(test_id, "pause")` →
   assert result `hint_to_agent` contains "resume" and "cancel" and "get_test_details"
2. `test_resume_hint`: call `sb_manage_test(test_id, "resume")` →
   assert result `hint_to_agent` contains "get_test_details" and "monitor"
3. `test_cancel_hint`: call `sb_manage_test(test_id, "cancel")` →
   assert result `hint_to_agent` contains "get_test_details" and "partial results"

**Green — Add hint_to_agent to `sb_manage_test`:**
1. Define hint map:
   - pause: "Test is paused. Use manage_test with action='resume' to continue,
     or action='cancel' to abort. Use get_test_details to check current status."
   - resume: "Test resumed. Use get_test_details to monitor progress."
   - cancel: "Test cancelled. Partial results may be available via get_test_details."
2. Add `hint_to_agent` key to result dict

**Refactor**: Update tool Markdown output to include hint. All tests green.

**Documentation:**
1. Add `manage_test` entry to the Studio Server tools section in CLAUDE.md
2. Include: tool name, parameters, description, supported actions, reason/note behavior,
   hint_to_agent behavior
3. Follow existing `run_scenario` documentation format
4. Update MCP Tools Available count

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add hint tests |
| `safebreach_mcp_studio/studio_functions.py` | Add `hint_to_agent` to result |
| `safebreach_mcp_studio/studio_server.py` | Include hint in Markdown output |
| `CLAUDE.md` | Add `manage_test` tool to Studio Server section |

**Git Commit**: `feat(studio): add hint_to_agent and docs for manage_test [TDD]`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Race condition: test completes before pause/cancel | Low | API returns appropriate error (404/409); tool handles gracefully |
| Comment API not truly non-additive | Medium | Read-then-append verified via browser network capture; test with E2E |
| Orchestrator returns unexpected status codes | Low | Catch all RequestException; return meaningful error messages |

### Assumptions

- Orchestrator API accepts `x-apitoken` authentication (same as queue POST)
- Data API `testsummaries/{test_id}` GET returns the full test summary object with `comment` field
- PUT to `testsummaries/{test_id}` with `{"comment": "..."}` updates only the comment
  field without affecting other test summary fields
- Pause/resume state changes are immediate (no async processing)

---

## 11. Future Enhancements

- **get_test_status tool**: Lightweight status check without full test details
- **Batch manage**: Pause/resume/cancel multiple tests at once
- **Schedule-based actions**: Auto-cancel tests running longer than a threshold
- **Note history**: Parse and display note history from the comment field
- **Reuse `_append_test_note`**: Other tools could use this helper to annotate tests

---

## 12. Executive Summary

- **Issue/Feature Description**: Add an MCP tool to manage running SafeBreach test lifecycles
  (pause, resume, cancel) with optional audit notes.
- **What Was Built**: Single `manage_test` tool in Studio Server with three actions, optional
  reason parameter that creates timestamped audit trail in test notes.
- **Key Technical Decisions**: Single tool over three separate tools (LLM usability);
  split architecture with lifecycle + notes helpers (testability);
  best-effort note append (resilience).
- **Scope Changes**: Added `reason` parameter and notes API integration beyond original
  ticket scope (which only mentioned pause/resume/cancel).
- **Business Value Delivered**: Completes the test execution lifecycle in MCP — agents
  can now fully manage tests from queue to completion/cancellation with audit trail.

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-04-20 12:00 | PRD created — initial draft |
| 2026-04-20 12:15 | Restructured to elephant carpaccio + pure TDD — 7 vertical slices |
| 2026-04-20 12:20 | E2E tests integrated into phases 1-3 and 5 instead of standalone phase |
| 2026-04-20 13:00 | Phase 1 complete — cancel test end-to-end (4 unit + 1 E2E, 315 tests pass) |
