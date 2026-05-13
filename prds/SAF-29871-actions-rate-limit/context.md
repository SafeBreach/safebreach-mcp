# Ticket Context: SAF-29871

## Status
Phase 6: PRD Created

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

### Deep Investigation: Infrastructure Patterns

**Concurrency Limiter (`safebreach_base.py:570-772`)**:
- ASGI middleware closure wrapping original app
- Installed in `run_server()` at line 253 as outermost middleware
- SSE: session UUID on `/sse` GET, migrated to real_session_id via regex
- Streamable-HTTP: `Mcp-Session-Id` header
- `_session_semaphores: Dict[str, tuple[Semaphore, float]]` — module-level, shared across servers
- Cleanup: every 600s, TTL=3600s (`_SEMAPHORE_MAX_AGE`)
- HTTP 429: JSON body with error/message/retry_after, plus `retry-after: 5` header

**Caller Identity (`token_context.py:160-187`)**:
- `get_cache_user_suffix()` returns `'_' + SHA256(token)[:8]` or empty string
- Priority: x-apitoken > x-token > cookie value
- Sources: `_user_auth_artifacts` ContextVar → `_get_auth_from_mcp_request_ctx()` fallback
- Session ID from `_get_session_id_from_mcp_ctx()`: query_params (SSE) or mcp-session-id header

**Tool Manager Wrapping (`safebreach_base.py:143-175`)**:
- `_install_disable_filtering()` monkey-patches `tool_manager.call_tool` and `list_tools`
- Pattern: wrap `original_call_tool` with custom logic, raise `ToolError` to reject
- Signature: `call_tool(name, arguments, context=None, convert_result=False)`

**Middleware Installation Order** (innermost to outermost):
1. MCP app (sse_app/streamable_http_app)
2. Base URL mount
3. External auth wrapper
4. Disable-filtering wrapper
5. Concurrency limiter (outermost)

**Background Tasks** (started in `run_server()`):
- `_cleanup_stale_semaphores()` — every 10 min
- `start_cache_monitoring()` — every 5 min (singleton, only one per process)

### Deep Investigation: Write Tool Gate Placement

**CORRECTION: `create_new_studio_attack` is READ-ONLY** (returns static boilerplate templates,
no API calls). Only **6 tools** need rate limiting gates.

| Tool | Pre-check point | check_limit placement | record_action placement | Dry-run? |
|------|-----------------|----------------------|------------------------|----------|
| `save_studio_attack_draft` | None | After param validation (~L632) | After POST response + cache (~L701) | No |
| `update_studio_attack_draft` | None | After param validation (~L885) | After PUT response + cache (~L954) | No |
| `run_studio_attack` | None | After validation (~L1089) | After POST queue response (~L1191) | No |
| `set_studio_attack_status` | Pre-check GET (~L1480) | After status confirmed (~L1508) | After PUT + cache invalidate (~L1617) | No |
| `run_scenario` | Readiness + dry_run early returns | After all early returns, before POST (~L2483) | After POST queue response (~L2517) | Yes |
| `manage_test` | None | After validation (~L2648) | After state change + note (~L2656) | No |

**Gate placement rules:**
1. `check_limit` goes after all validation/reads, before the first mutating API call
2. `record_action` goes after confirming the API call succeeded (response parsed)
3. For `run_scenario`: skip both gates on diagnostic (not_ready) and dry_run branches
4. For `set_studio_attack_status`: allow pre-check GET before check_limit
5. For `manage_test`: record after state change (note append is best-effort)

## Brainstorm Results (Phase 5)

### Chosen Approach: Explicit Two-Phase with Shared Helper (Approach B)

**Design decisions:**
- New `safebreach_mcp_core/rate_limiter.py` with singleton `RateLimiter` class
- `get_caller_identity()` helper encapsulates hybrid logic (auth token hash / session fallback)
- Each write tool explicitly calls `check_limit()` and `record_action()` at appropriate points
- `check_limit` raises `ToolError` (MCP-level, not HTTP 429)
- Sliding window: list of timestamps per (caller, tool_name), pruned on check/record

**Configuration (env vars, all have defaults):**
- `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` — default: true
- `SAFEBREACH_MCP_ACTION_LIMIT` — default: 10
- `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` — default: 5
- `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` — default: 30

**Rejected alternatives:**
- Approach A (fully explicit): too much boilerplate, caller ID extraction repeated per tool
- Approach C (decorator): fights per-tool gate placement, hides timing, complex for dry-run

**Error type:** ToolError (MCP-level) — agent sees it as a tool failure with meaningful message
**Enable/disable:** Env var, default enabled
