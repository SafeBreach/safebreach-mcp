# Ticket Summary: SAF-29969

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] Add a tool to allow pausing, resuming or cancelling a running test by id
**Issues Identified**: No description, no acceptance criteria. API endpoints needed discovery.

---

## Investigation Summary

### safebreach-mcp
- All three orchestrator API endpoints confirmed via browser network capture
- Pause/Resume: `PUT /api/orch/v4/accounts/{id}/queue/{test_id}/state`
  with body `{"status":"pause"}` or `{"status":"resume"}`
- Cancel: `DELETE /api/orch/v4/accounts/{id}/queue/{test_id}` (no body)
- Test notes (comment) API: read-then-append via data API
  - Read: `GET /api/data/v1/accounts/{id}/testsummaries/{test_id}` (extract `comment` field)
  - Write: `PUT /api/data/v1/accounts/{id}/testsummaries/{test_id}` with `{"comment": "..."}`
  - API is NOT additive — must read existing comment, concatenate new note, then save
- Studio Server is the correct placement (owns test execution lifecycle)
- Existing `run_scenario` tool follows the same orchestrator API pattern
- Cancel helper already exists in E2E test file (`test_e2e_run_scenario.py:65-73`)
- Relevant files: `studio_functions.py`, `studio_server.py`,
  `tests/test_studio_functions.py`, `tests/test_e2e_run_scenario.py`

---

## Problem Analysis

### Problem Description
The safebreach-mcp project can queue test executions via `run_scenario` but provides
no tools for managing running tests. AI agents cannot pause, resume, or cancel tests
once they are queued or running. Additionally, agents have no way to document
why they performed a lifecycle action on a test.

### Impact Assessment
- **User experience**: Agents must wait for tests to complete even when cancelled is desired
- **Test management**: No way to pause long-running tests during maintenance windows
- **Auditability**: No record of why an agent paused/resumed/cancelled a test

### Risks & Edge Cases
- Race conditions when test completes before pause/cancel request arrives
- Idempotent handling of already-cancelled or already-paused tests
- Error responses for invalid test IDs or tests in incompatible states
- Comment concatenation: existing comment may be null/empty — handle gracefully
- Comment write may fail independently of lifecycle operation — lifecycle should
  still succeed, with a warning about failed note

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Add MCP tools for pausing, resuming, and cancelling running tests

### Description

**Background**
The Studio Server already supports queuing test executions via `run_scenario`, but lacks
tools for managing tests after they are queued. Users need the ability to pause, resume,
and cancel running tests by their test ID (`planRunId`). Each operation should also
support an optional `reason` parameter to document the action in the test's notes.

**Technical Context**
* Lifecycle operations use the SafeBreach orchestrator API (`/api/orch/v4/`)
* Pause/Resume: `PUT .../queue/{test_id}/state` with `{"status":"pause"|"resume"}`
* Cancel: `DELETE .../queue/{test_id}` (no body)
* Test notes use the data API (`/api/data/v1/accounts/{id}/testsummaries/{test_id}`)
  - Read existing `comment` field via GET, append new note, write back via PUT
  - Comment API is NOT additive — read-then-append pattern required
* Authentication uses existing `x-apitoken` header pattern
* Test IDs use dot-notation format (e.g., `1776488350786.15`)

**Note Format**
When `reason` is provided, a timestamped note is appended to the test's comment field:
```
[2026-04-20 14:30:00 UTC] Test paused: <reason text>
```

**Problem Description**
* No MCP tools exist for test lifecycle management after queuing
* AI agents cannot pause tests during maintenance windows
* AI agents cannot cancel tests that were started in error
* AI agents cannot resume paused tests
* No audit trail for why lifecycle actions were taken

**Affected Areas**
* `safebreach_mcp_studio/`: studio_functions.py, studio_server.py, tests/

### Acceptance Criteria

- [ ] `pause_test` MCP tool: accepts `test_id`, `console`, and optional `reason`;
  calls `PUT /api/orch/v4/accounts/{id}/queue/{test_id}/state` with
  `{"status":"pause"}`; returns confirmation with test_id and status
- [ ] `resume_test` MCP tool: accepts `test_id`, `console`, and optional `reason`;
  calls `PUT /api/orch/v4/accounts/{id}/queue/{test_id}/state` with
  `{"status":"resume"}`; returns confirmation with test_id and status
- [ ] `cancel_test` MCP tool: accepts `test_id`, `console`, and optional `reason`;
  calls `DELETE /api/orch/v4/accounts/{id}/queue/{test_id}`;
  returns confirmation with test_id and status
- [ ] Optional `reason` parameter: when provided, appends a timestamped note
  (UTC) to the test's `comment` field via read-then-append pattern using
  `GET/PUT /api/data/v1/accounts/{id}/testsummaries/{test_id}`
- [ ] Note format: `[YYYY-MM-DD HH:MM:SS UTC] Test {action}: {reason}`
- [ ] Note append handles null/empty existing comments gracefully
- [ ] Note write failure does not block the lifecycle operation — lifecycle
  succeeds with a warning about failed note
- [ ] All three tools handle error cases gracefully (404 not found,
  409 conflict/already completed, network errors)
- [ ] Unit tests covering success, not-found, API error, reason/note,
  and edge cases for all three tools
- [ ] E2E tests for cancel (extend existing test_e2e_run_scenario.py)
- [ ] Tools follow existing Studio Server patterns (auth, error handling,
  response format)

### Suggested Labels/Components
- Component: safebreach-mcp-studio
- Labels: mcp, studio-server

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
The Studio Server already supports queuing test executions via `run_scenario`,
but lacks tools for managing tests after they are queued. Users need the ability
to pause, resume, and cancel running tests by their test ID (planRunId).
Each operation supports an optional `reason` parameter to document the action
in the test's notes (comment field).

### Technical Context
* Lifecycle operations use the orchestrator API (/api/orch/v4/)
* Pause/Resume: PUT .../queue/{test_id}/state with {"status":"pause"|"resume"}
* Cancel: DELETE .../queue/{test_id} (no body)
* Test notes via data API: GET/PUT /api/data/v1/.../testsummaries/{test_id}
* Comment API is NOT additive - read existing comment, append new note, write back
* Note format: [YYYY-MM-DD HH:MM:SS UTC] Test {action}: {reason}
* Test IDs use dot-notation format (e.g., 1776488350786.15)

### Problem Description
* No MCP tools exist for test lifecycle management after queuing
* AI agents cannot pause/resume/cancel tests
* No audit trail for why lifecycle actions were taken

### Affected Areas
* safebreach_mcp_studio/: studio_functions.py, studio_server.py, tests/
```

**Acceptance Criteria:**
```markdown
* pause_test MCP tool with optional reason parameter
* resume_test MCP tool with optional reason parameter
* cancel_test MCP tool with optional reason parameter
* Reason appends timestamped UTC note to test comment via read-then-append
* Note append handles null/empty existing comments
* Note write failure does not block lifecycle operation
* All tools handle error cases (404, 409, network errors)
* Unit tests for success, not-found, API error, reason/note, edge cases
* E2E tests for cancel
* Tools follow existing Studio Server patterns
```
