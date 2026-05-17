# SAF-29972: Extend manage_test to support deleting historic test results

## Status
Phase 3: Create Working Branch and PRD Context

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
(Phase 4)
