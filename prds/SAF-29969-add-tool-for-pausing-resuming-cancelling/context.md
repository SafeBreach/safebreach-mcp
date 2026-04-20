# Ticket Context: SAF-29969

## Status
Phase 5: Problem Analysis Complete

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] Add a tool to allow pausing, resuming or cancelling a running test by id
- **Description**: No description provided
- **Acceptance Criteria**: None defined
- **Status**: In Progress

## Task Scope
Add MCP tools for pausing, resuming, and cancelling SafeBreach test executions (running tests). Investigate the SafeBreach API endpoints available for these operations and determine which server(s) should host the new tools.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### API Endpoints (All Confirmed)

| Operation | HTTP Method | Endpoint | Body |
|-----------|-------------|----------|------|
| Queue test | POST | `/api/orch/v4/accounts/{id}/queue` | Complex plan payload |
| Pause test | PUT | `/api/orch/v4/accounts/{id}/queue/{test_id}/state` | `{"status":"pause"}` |
| Resume test | PUT | `/api/orch/v4/accounts/{id}/queue/{test_id}/state` | `{"status":"resume"}` |
| Cancel test | DELETE | `/api/orch/v4/accounts/{id}/queue/{test_id}` | (none) |

### Pause/Resume Endpoint Details
- Same endpoint, different body payload: `PUT .../queue/{test_id}/state`
- Content-Type: application/json
- Pause and resume share the same URL pattern, differentiated by `{"status": "pause"|"resume"}`

### Cancel Endpoint Details
- `DELETE /api/orch/v4/accounts/{account_id}/queue/{test_id}`
- No request body needed
- Also found as helper in `safebreach_mcp_studio/tests/test_e2e_run_scenario.py:65-73`

### Server Placement: Studio Server
- `run_scenario` (queue tests) is in Studio Server — lifecycle management belongs here
- Data Server handles read-only historical queries (different concern)
- Studio already uses orchestrator endpoint (`/api/orch/v4/`)

### Key Patterns
- Auth: `get_secret_for_console(console)` → `x-apitoken` header
- URL: `get_api_base_url(console, 'orchestrator')` + `/api/orch/v4/accounts/{id}/queue/{test_id}`
- Functions: `studio_functions.py` → `studio_server.py` tool registration
- Test IDs: dot-notation format (e.g., `1776488350786.15`)

### Files to Modify
- `safebreach_mcp_studio/studio_functions.py` — add `sb_cancel_test()`, `sb_pause_test()`,
  `sb_resume_test()`
- `safebreach_mcp_studio/studio_server.py` — register new MCP tools
- `safebreach_mcp_studio/tests/test_studio_functions.py` — unit tests
- `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` — E2E tests (already has cancel helper)

## Problem Analysis

### Problem Scope
The safebreach-mcp project can queue test executions via `run_scenario` but has no tools
for managing running tests. Users cannot pause, resume, or cancel a test once queued.
All three SafeBreach orchestrator API endpoints are now confirmed.

### Affected Areas
- `safebreach_mcp_studio/studio_functions.py` — new business logic functions
- `safebreach_mcp_studio/studio_server.py` — new MCP tool registrations
- `safebreach_mcp_studio/tests/test_studio_functions.py` — unit tests
- `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` — E2E tests

### Dependencies
- SafeBreach orchestrator API (`/api/orch/v4/`)
- Existing auth infrastructure (`get_secret_for_console`, `get_api_base_url`)
- Test ID from `run_scenario` output (`planRunId`)

### Risks & Edge Cases
- Race conditions: test may complete before pause/cancel arrives
- Idempotency: calling cancel on already-completed test
- Error handling: 404 (not found), 409 (conflict), already paused/resumed states
- Pause/resume share same endpoint — need validation of `action` parameter

## Proposed Improvements
(Phase 6)
