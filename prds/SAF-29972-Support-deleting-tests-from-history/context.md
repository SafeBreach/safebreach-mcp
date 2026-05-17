# SAF-29972: Extend manage_test to support deleting historic test results

## Status
Phase 6: PRD Created

## Chosen Approach
**Approach B: Delegate to sb_delete_test function, same MCP tool.**
`sb_manage_test` dispatches to `sb_delete_test(test_id, console, reason, dry_run)` when
`action="delete"`. This keeps the MCP tool surface unchanged (single `manage_test` tool) while
separating delete-specific logic (dry_run, mandatory reason, different API endpoint) into a
self-contained, testable function.

**Rationale**: Most LLM-efficient — agent uses the same familiar `manage_test` tool with a new
action value. No new tool discovery needed. Clean separation of concerns internally.

## Ticket Info
- **Type**: Task
- **Priority**: Medium
- **Assignee**: Yossi Attas
- **Sprint**: Saf sprint 89 (active)
- **Branch**: SAF-29972-Support-deleting-tests-from-history

## Description
Add a `delete` action to the `manage_test` tool to allow customers to remove test results that
have reached a terminal state (`completed`, `canceled`, or `failed`). This helps manage retention
and preserve disk space by cleaning up accidental or obsolete test runs.

## Key Requirements
- Add `delete` to `manage_test` valid actions
- Only allow delete on terminal states — pre-check via `get_orchestrator_test_state()`
- Dry-run confirmation pattern: `dry_run=True` (default) returns preview, `dry_run=False` executes
- Mandatory `reason` parameter for delete (audit trail)
- No note append for delete (note gets deleted with the test)
- API: `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}` with body
  `{"id": "{test_id}", "planName": "{test_name}"}`
- Rate limiting gates apply
- `destructiveHint=True` annotation (already set on the tool)

## Dependencies
- `safebreach_mcp_core/queue_state.py` — `get_orchestrator_test_state()` (SAF-31111)
- `safebreach_mcp_core/rate_limiter.py` — rate limiting gates (SAF-29871)

## Investigation Findings

### Entry Points
- `sb_manage_test()` at `studio_functions.py:2740` — main function, accepts action parameter
- `manage_test` tool handler at `studio_server.py:1410` — MCP tool registration

### Delete API
- Endpoint: `DELETE /api/data/v1/accounts/{account_id}/tests/{test_id}` (data API, not orchestrator)
- Request body: `{"id": "{test_id}", "planName": "{test_name}"}`
- `planName` must be fetched from `GET /testsummaries/{test_id}` before delete
- No existing `/tests/` endpoint usage in the codebase

### Current Flow (pause/resume/cancel)
1. Input validation → 2. `_get_test_state()` pre-check (orchestrator queue + data API fallback)
   → 3. Rate limit check → 4. `_set_test_state()` → 5. Rate limit record → 6. Optional note → 7. Hints

### Delete Flow (new)
1. Input validation → 2. `_get_test_state()` pre-check (must be terminal) → 3. Fetch test summary
   for planName → 4. If dry_run: return preview → 5. Rate limit check → 6. `_delete_test()` DELETE
   → 7. Rate limit record → 8. Hints (no note append)

### Key Files
| File | Lines | Purpose |
|------|-------|---------|
| `studio_functions.py` | 2604-2639 | `_get_test_state()` |
| `studio_functions.py` | 2642-2683 | `_set_test_state()` |
| `studio_functions.py` | 2740-2846 | `sb_manage_test()` |
| `studio_server.py` | 1410-1483 | Tool registration |
| `queue_state.py` | 25-63 | `get_orchestrator_test_state()` |
| `test_studio_functions.py` | 7300-8043 | Unit tests |
| `test_e2e_manage_test.py` | 1-267 | E2E tests |
