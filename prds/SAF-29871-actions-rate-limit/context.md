# Ticket Context: SAF-29871

## Status
Phase 6: Summary Created

## Mode
Improving

## Original Ticket
- **Summary**: MCP: Limit the rate of repeated actions
- **Description**: Implement rate limiting as a safety guardrail. Two mechanisms: (1) Total action cap - max 10 actions per MCP client in a 30-min sliding window. (2) Identical action rate limit - max 5 identical actions of the same type per client in the same window. Clear error messages when limits are reached.
- **Acceptance Criteria**: Not yet defined in ticket
- **Status**: To Do

## Task Scope
Investigate implementing rate limiting for MCP server actions to prevent misuse through repetitive requests.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### Existing Infrastructure (safebreach_mcp_core/)

**Concurrency Limiter** (`safebreach_base.py:570-772`):
- Per-session `asyncio.Semaphore` limits concurrent requests (default: 2)
- Session ID: UUID generated on `/sse` endpoint, or `Mcp-Session-Id` header for streamable-http
- Module-level `_session_semaphores: Dict[str, tuple[Semaphore, float]]`
- Cleanup task runs every 10 min, evicts stale entries after 1 hour
- Returns HTTP 429 with `retry-after` header when limit exceeded
- **This is the exact pattern to reuse for rate limiting**

**Session Tracking** (`safebreach_base.py:586-684`):
- `_mcp_session_id` ContextVar propagates session across async stack
- SSE: UUID on `/sse` GET, real_session_id from FastMCP response body
- Streamable-HTTP: `Mcp-Session-Id` header
- Fallback: query string `?session_id=...` for POST `/messages/`

**Auth/RBAC** (`token_context.py`):
- Per-request auth artifacts stored by session_id with TTL cleanup
- `get_cache_user_suffix()` returns SHA256 of auth token for user-scoped caching
- Rate limiting can use session_id as client identity (aligns with ticket scope)

**Caching** (`safebreach_cache.py:22-177`):
- `SafeBreachCache` wraps `cachetools.TTLCache`, thread-safe with Lock
- No sliding-window capability - new implementation needed for rate limiting

### Tool Classification by Annotations

All servers use `ToolAnnotations(readOnlyHint, destructiveHint)`:

| Server | Tool | readOnlyHint | destructiveHint | Classification |
|--------|------|---|---|---|
| Config | get_console_simulators, get_simulator_details, get_scenarios, get_scenario_details | True | - | Read-only |
| Data | All 15 tools | True | - | Read-only |
| Utilities | convert_datetime_to_epoch, convert_epoch_to_datetime | True | - | Read-only |
| Playbook | get_playbook_attacks, get_playbook_attack_details | True | - | Read-only |
| Studio | validate_studio_code, get_all_studio_attacks, get_studio_attack_source, etc. | True | - | Read-only |
| Studio | save_studio_attack_draft, update_studio_attack_draft, create_new_studio_attack | False | False | Mutating |
| Studio | run_studio_attack, run_scenario, manage_test, set_studio_attack_status | False | True | **Action** |

**Key insight**: Only Studio server has mutating/destructive tools. All other servers are read-only.

### Transport & Middleware Stack

Request flow: HTTP request -> Auth middleware -> Concurrency limiter -> MCP SDK -> Tool handler

Both SSE and streamable-http transports converge at `_create_concurrency_limited_app()`.
Rate limiting should count tool invocations (not HTTP requests).

### Tool Registration Pattern

Tools registered via `@self.mcp.tool(name=..., annotations=ToolAnnotations(...))` decorator.
Tool metadata accessible via `self.mcp._tool_manager.list_tools()` which returns tool definitions
including annotations.

## Problem Analysis

### Problem Description
The MCP servers have no rate limiting on tool invocations. A malicious or misconfigured client
could repeatedly call write operations (run tests, manage tests, publish attacks) without restriction.

### Scope Clarifications (from stakeholder)
- **"Action" definition**: Any MCP tool where `readOnlyHint != True` (i.e., all non-read-only tools)
- **Two independent counters per session**:
  1. **Total actions**: Count of all non-readOnly tool calls within the sliding window (default limit: 10)
  2. **Per-action-name**: Count of each specific tool name within the sliding window (default limit: 5)
- **Sliding window**: Default 30 minutes, configurable
- **Cross-server**: Shared state across all servers (same process, module-level dict)
- **All servers**: Rate limiter installed on every server, even if currently read-only (future-proofing)

### Affected Areas
- `safebreach_mcp_core/safebreach_base.py` - Middleware injection point
- `safebreach_mcp_core/` - New rate_limiter module
- All 5 server modules - Rate limiter installed in each

### Risks & Edge Cases
- ASGI middleware may not have tool name visibility - may need MCP SDK-level interception
- Session ID must be consistent across the tool call lifecycle
- Cross-server shared state requires thread-safe access (all servers in same process)
- Sliding window cleanup must handle disconnected sessions

## Proposed Improvements
(Phase 6)
