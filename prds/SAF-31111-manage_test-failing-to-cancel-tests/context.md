# SAF-31111: manage_test tool is failing to cancel a test

## Status
Phase 6: PRD Created

## Ticket Info
- **Type**: Bug
- **Priority**: Medium
- **Assignee**: Yossi Attas
- **Sprint**: Saf sprint 89 (May 12-26, 2026)
- **Branch**: SAF-31111-manage_test-failing-to-cancel-tests

## Description
The `manage_test` tool fails when attempting to cancel a test. The original ticket hypothesis was
that the code uses `POST` instead of `DELETE` — this was disproven. The actual root cause is a
**lack of idempotency**: `manage_test` doesn't check the test's current state before sending the
API call.

## Investigation Findings

### Repository: safebreach-mcp

#### Initial Hypothesis Disproven
The code at `studio_functions.py:2627` has always used `requests.delete()` since the initial commit
(`289efde`, SAF-29969). Verified at tag `1.1.0` and HEAD — identical. The E2E cancel test
(`test_e2e_cancel_test`) passes against pentest01.

#### Root Cause: Lack of Idempotency
`_set_test_state()` sends the API call without checking the test's current status. The orchestrator
API returns errors for invalid state transitions:

| Test State | Cancel (DELETE) | Pause (PUT) | Resume (PUT) |
|------------|----------------|-------------|--------------|
| Running | 200 (success) | 200 (success) | N/A |
| Paused | **500** `"no plan was stopped"` | N/A | 200 (success) |
| Canceled | **404** `PLAN_NOT_EXISTS` | 200 (silent no-op) | **500** crash |
| Completed | **404** `PLAN_NOT_EXISTS` | ? | ? |

These errors propagate through `check_rbac_response()` → `raise_for_status()` → exception →
tool returns `"Error managing test: ..."`.

**Notably**: Canceling a **paused** test returns 500 — the orchestrator requires the test to be
running for DELETE to work.

#### Secondary Issue: Note Append Error Exposure
`_append_test_note()` failures are caught but the error text (e.g., "500 Server Error") is
included in the tool response. An LLM may interpret this as the entire cancel having failed.

#### Code Flow (studio_functions.py)
1. `sb_manage_test()` (line 2702) — validates input, calls `_set_test_state()`
2. `_set_test_state()` (line 2604) — sends DELETE/PUT without state pre-check
3. `_append_test_note()` (line 2648) — best-effort GET+PUT to add comment

## Problem Analysis

### What Needs to Change
1. **Pre-check test state** via `GET testsummaries/{test_id}` before the action
2. **Idempotent quick-return** if test is already in the desired terminal state
   (cancel on canceled/completed → success, not error)
3. **Informative error** for invalid transitions
   (cancel on paused → "test is paused, resume first then cancel")
4. **Silent note failures** — log only, don't expose error text in tool response

### State Transition Matrix (proposed)
| Current State | Cancel | Pause | Resume |
|--------------|--------|-------|--------|
| Running | Execute DELETE | Execute PUT | Already running |
| Paused | Error: resume first | Already paused | Execute PUT |
| Canceled | Quick-return: already canceled | Error: already canceled | Error: already canceled |
| Completed | Quick-return: already completed | Error: already completed | Error: already completed |

## Files of Interest
| File | Lines | Purpose |
|------|-------|---------|
| `safebreach_mcp_studio/studio_functions.py` | 2604-2645 | `_set_test_state()` — HTTP call |
| `safebreach_mcp_studio/studio_functions.py` | 2648-2699 | `_append_test_note()` — note append |
| `safebreach_mcp_studio/studio_functions.py` | 2702-2756 | `sb_manage_test()` — orchestration |
| `safebreach_mcp_studio/studio_server.py` | 1410-1474 | Tool registration + response formatting |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | 7310-7341 | Cancel unit tests |
| `safebreach_mcp_studio/tests/test_e2e_manage_test.py` | 97-139 | Cancel E2E test |

## E2E Reproduction Evidence
```
# Cancel already-canceled test (1778761910751.16) — returns 404
DELETE /api/orch/v4/accounts/3471166703/queue/1778761910751.16
→ 404: {"error":{"statusCode":404,"message":"no test with runId ... was found","type":"PLAN_NOT_EXISTS"}}

# Cancel paused test (1778678311904.157) — returns 500
DELETE /api/orch/v4/accounts/3471166703/queue/1778678311904.157
→ 500: {"error":{"message":"no plan was stopped"}}

# Cancel completed test (1778774475413.82) — returns 404
DELETE /api/orch/v4/accounts/3471166703/queue/1778774475413.82
→ 404: {"error":{"statusCode":404,"message":"no test with runId ... was found","type":"PLAN_NOT_EXISTS"}}
```
