# Ticket Summary: SAF-31111

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repository**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] manage_test tool is failing to cancel a test
**Issues Identified**: Original hypothesis (POST vs DELETE) was incorrect. The actual root cause
is lack of idempotency — `manage_test` doesn't check the test's current state before sending
the API call.

---

## Investigation Summary

### safebreach-mcp
- The cancel implementation has always used `requests.delete()` since the initial commit
- E2E cancel test passes when the test is in a running state
- Canceling non-running tests (paused, canceled, completed) returns HTTP errors (404/500)
- The orchestrator API does not support idempotent cancel operations
- Note append failures expose error text in the tool response, potentially confusing LLMs
- Relevant files:
  - `safebreach_mcp_studio/studio_functions.py` — `_set_test_state()`, `sb_manage_test()`,
    `_append_test_note()`
  - `safebreach_mcp_studio/studio_server.py` — tool registration and response formatting
  - `safebreach_mcp_studio/tests/test_studio_functions.py` — unit tests
  - `safebreach_mcp_studio/tests/test_e2e_manage_test.py` — E2E tests

---

## Problem Analysis

### Problem Description
The `manage_test` tool sends lifecycle API calls (cancel/pause/resume) without first checking the
test's current state. The SafeBreach orchestrator API returns errors for invalid state transitions:
- Cancel on paused test: 500 "no plan was stopped"
- Cancel on canceled/completed test: 404 "PLAN_NOT_EXISTS"
- Resume on canceled test: 500 (server crash)

These errors propagate through `raise_for_status()` and the tool returns an error message. An LLM
agent calling `manage_test` to cancel a test that was already canceled, paused, or completed sees
a failure — even though the desired outcome (test not running) is already achieved.

### Impact Assessment
- **LLM usability**: Agents retry failed operations, potentially sending unnecessary API calls
- **User experience**: Error messages for valid no-op scenarios create confusion
- **Paused test cancel**: Cannot cancel a paused test at all — must resume first, which is
  unintuitive

### Risks & Edge Cases
- Pre-check GET adds one extra API call per `manage_test` invocation
- Race condition: test state could change between pre-check and action (acceptable — the action
  would then succeed or get a retriable error)
- Note append on canceled/completed tests: data API GET works (200), PUT should also work

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Make manage_test idempotent with state pre-check

### Description

**Background**
The `manage_test` MCP tool allows LLM agents to pause, resume, or cancel running tests. Currently,
it sends lifecycle API calls without checking the test's current state, causing errors when the
test is not in the expected state.

**Important**: Canceling a test does NOT delete it from history. The test remains in test history
(accessible via `get_tests` and `get_test_details`) with a "canceled" status. A dedicated tool for
deleting tests from history will be created separately.

**Technical Context**
* The orchestrator queue API returns 404 for cancel on completed/canceled tests and 500 for cancel
  on paused tests
* `_set_test_state()` in `studio_functions.py` calls the API blindly without state pre-check
* `_append_test_note()` catches errors but includes error text in the tool response, which can
  confuse LLM agents

**Problem Description**
* Canceling a paused test returns 500 `"no plan was stopped"` — user must resume first then cancel
* Canceling an already-canceled or completed test returns 404 `PLAN_NOT_EXISTS`
* Resuming a canceled test causes a 500 server crash
* These are all surfaced as tool errors to the LLM, causing retry loops and confusion

**Affected Areas**
* `safebreach_mcp_studio/studio_functions.py`: `_set_test_state()`, `sb_manage_test()`,
  `_append_test_note()`
* `safebreach_mcp_studio/studio_server.py`: tool response formatting
* `safebreach_mcp_studio/tests/test_studio_functions.py`: unit tests
* `safebreach_mcp_studio/tests/test_e2e_manage_test.py`: E2E tests

### Acceptance Criteria

- [ ] `manage_test` pre-checks test state via `GET testsummaries/{test_id}` before action
- [ ] Cancel on canceled/completed test returns success (idempotent quick-return)
- [ ] Cancel on paused test returns informative error: suggest resume first
- [ ] Pause on already-paused test returns success (idempotent)
- [ ] Resume on already-running test returns success (idempotent)
- [ ] Actions on terminal states (canceled/completed) return informative messages, not errors
- [ ] Note append failures are logged but NOT exposed in the tool response
- [ ] Unit tests cover all state transition scenarios (running, paused, canceled, completed)
- [ ] E2E test for cancel-on-canceled idempotency

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
The `manage_test` MCP tool allows LLM agents to pause, resume, or cancel running tests.
Currently, it sends lifecycle API calls without checking the test's current state, causing
errors when the test is not in the expected state.

### Technical Context
* The orchestrator queue API returns 404 for cancel on completed/canceled tests and 500 for
  cancel on paused tests
* `_set_test_state()` in `studio_functions.py` calls the API without state pre-check
* `_append_test_note()` catches errors but includes error text in the tool response

### Problem Description
* Canceling a paused test returns 500 — user must resume first then cancel
* Canceling already-canceled or completed test returns 404 PLAN_NOT_EXISTS
* Resuming a canceled test causes a 500 server crash
* These are surfaced as tool errors, causing LLM retry loops and confusion

### Fix
* Add state pre-check via GET testsummaries/{test_id} before action
* Idempotent quick-return for terminal states (canceled/completed)
* Informative error for invalid transitions (e.g., cancel while paused)
* Silent note append failures (log only, don't expose in response)

### Affected Areas
* `safebreach_mcp_studio/studio_functions.py`
* `safebreach_mcp_studio/studio_server.py`
* `safebreach_mcp_studio/tests/`
```

**Acceptance Criteria:**
```markdown
* manage_test pre-checks test state via GET testsummaries before action
* Cancel on canceled/completed test returns success (idempotent quick-return)
* Cancel on paused test returns informative error: suggest resume first
* Pause on already-paused test returns success (idempotent)
* Resume on already-running test returns success (idempotent)
* Actions on terminal states return informative messages, not errors
* Note append failures are logged but NOT exposed in the tool response
* Unit tests cover all state transition scenarios
* E2E test for cancel-on-canceled idempotency
```
