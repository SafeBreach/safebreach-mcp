# Ticket Context: SAF-29969

## Status
Phase 6: PRD Created

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

## Design Decisions
- **Single tool**: `manage_test(test_id, action, console, reason)` with `action` = pause|resume|cancel
  - Chosen over 3 separate tools for better LLM usability (fewer tools to discover)
- **Optional `reason`**: Appends timestamped UTC note to test's `comment` field
  - Read-then-append pattern via data API (non-additive comment API)
  - Note format: `[YYYY-MM-DD HH:MM:SS UTC] Test {action}: {reason}`
  - Note failure does not block lifecycle operation

## Notes API (Data Server)
- Read: `GET /api/data/v1/accounts/{id}/testsummaries/{test_id}` → `comment` field
- Write: `PUT /api/data/v1/accounts/{id}/testsummaries/{test_id}` with `{"comment": "..."}`

## Deep Investigation Findings (Phase 4)

### Function Signature Convention
- Return type: `Dict[str, Any]`
- Console: `console: str = "default"`
- Optional params: `param: str = None` (studio uses bare None, not Optional wrapper)
- Function prefix: `sb_` for business logic (e.g., `sb_run_scenario`)
- Tool functions: no prefix (e.g., `validate_studio_code`)

### Auth Pattern (exact code)
```python
apitoken = get_secret_for_console(console)
base_url = get_api_base_url(console, 'orchestrator')  # or 'data'
account_id = get_api_account_id(console)
headers = {"x-apitoken": apitoken, "Content-Type": "application/json"}
```

### HTTP Request Pattern
- Timeout: 120s for POST/PUT, 30s for DELETE and best-effort operations
- Error: `except requests.exceptions.RequestException as e:` → log + raise
- Response: `response.raise_for_status()` then `response.json()`
- API response wrapper: `{"data": {...}}`

### Tool Registration Pattern
- Return type: always `str` (Markdown formatted)
- Description: multi-line with Parameters, Returns, Example sections
- Error handling: try/except ValueError/Exception → return error string
- Response: Markdown with `## Header`, `**Bold**`, code blocks

### Comment Helper (already exists in E2E)
`test_e2e_run_scenario.py:76-85` has `_comment_test(test_id, console, comment)`:
- `PUT /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`
- Body: `{"comment": comment}`
- Service type: `'data'`
- Timeout: 30s
- Best-effort: logs warning on failure, doesn't raise

### Cancel Helper (already exists in E2E)
`test_e2e_run_scenario.py:65-73` has `_cancel_test(test_id, console)`:
- `DELETE /api/orch/v4/accounts/{account_id}/queue/{test_id}`
- No Content-Type header needed for DELETE
- Timeout: 30s

### Test Structure
- Mock decorators: `@patch('safebreach_mcp_studio.studio_functions.requests.METHOD')`
- Mock order: `mock_secret`, `mock_base_url`, `mock_account_id`, `mock_http_method`
- Assertions: return value dict keys, mock call counts, URL verification
- Categories: success, not_found, api_error, empty_id, none_id

## Brainstorming Results (Phase 5)

### Additional Design: hint_to_agent in response
- Include `hint_to_agent` in tool response, contextual per action:
  - pause: "Test is paused. Use manage_test with action='resume' to continue,
    or action='cancel' to abort. Use get_test_details to check current status."
  - resume: "Test resumed. Use get_test_details to monitor progress."
  - cancel: "Test cancelled. Partial results may be available via get_test_details."

### Chosen Approach: B — Split lifecycle + notes helpers
- `_set_test_state(test_id, action, console)` — orchestrator API (pause/resume/cancel)
- `_append_test_note(test_id, action, reason, console)` — data API (read-then-append)
- `sb_manage_test(test_id, action, console, reason)` — thin orchestrator calling both
- Note separator: newline (`\n`) between existing comment and new note
- Note format: `[YYYY-MM-DD HH:MM:SS UTC] Test {action}: {reason}`

### Rejected Alternatives
- A: Monolithic — mixes orchestrator + data API concerns, harder to test
- C: Per-action functions — over-engineering for 2 URL patterns

## Proposed Improvements
(Phase 6)
