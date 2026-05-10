# Ticket Summary: SAF-29871

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repository**: safebreach-mcp

---

## Current State
**Summary**: MCP: Limit the rate of repeated actions
**Issues Identified**: Ticket has functional requirements but lacks technical context,
acceptance criteria, and definition of done.

---

## Investigation Summary

### safebreach-mcp
- All 5 MCP servers inherit from `SafeBreachMCPBase` and share core middleware
- Existing concurrency limiter (`_create_concurrency_limited_app()`) provides the exact pattern
  to reuse: per-session tracking, stale cleanup, HTTP 429 responses
- Session IDs tracked via `_mcp_session_id` ContextVar (SSE UUID / streamable-http header)
- Tool annotations (`readOnlyHint`, `destructiveHint`) already classify tools
- Currently only Studio server has non-readOnly tools (7 tools), all other servers are read-only
- All servers run in same process via `MultiServerLauncher` — module-level dicts enable
  cross-server shared state without external storage
- Relevant files:
  - `safebreach_mcp_core/safebreach_base.py` (concurrency limiter, session tracking)
  - `safebreach_mcp_core/safebreach_cache.py` (TTL cache pattern)
  - `safebreach_mcp_core/token_context.py` (per-session auth artifacts)
  - `safebreach_mcp_studio/studio_server.py` (write tools with annotations)

---

## Problem Analysis

### Problem Description
The MCP servers have no rate limiting on tool invocations. A malicious or misconfigured MCP client
could repeatedly call write operations (run tests, manage tests, publish attacks, create drafts)
without restriction, causing operational damage before detection.

### Impact Assessment
- **Security**: Unrestricted write operations could be exploited to run mass tests, cancel running
  tests, or publish untested attacks
- **Operational**: Without rate limiting, a single client could overwhelm SafeBreach environments
  with test executions

### Risks & Edge Cases
- ASGI middleware doesn't have visibility into MCP tool names — interception must happen at the
  MCP SDK level (tool call wrapper or middleware hook)
- Sliding window implementation must be thread-safe (asyncio Lock or threading Lock) since all
  servers share the same process
- Session cleanup must handle abrupt disconnections
- Rate limits should reset cleanly when the sliding window advances

---

## Proposed Ticket Content

### Summary (Title)
MCP: Implement per-caller rate limiting for write operations

### Description

**Background**
As part of the MCP safety guardrails, we need to limit the rate at which actions (non-readOnly
tool calls) can be performed. This prevents misuse through repetitive requests and allows
identification of suspicious activity.

**Technical Context**
* All 5 MCP servers share `SafeBreachMCPBase` with existing concurrency limiter infrastructure
* Tool annotations (`readOnlyHint`) already classify tools as read-only vs write operations
* `token_context.py` provides `get_cache_user_suffix()` — SHA256 hash of auth token for identity
* All servers run in the same process — module-level shared state enables cross-server rate limiting
* Existing patterns: per-session semaphores, 10-min cleanup tasks, HTTP 429 responses

**Caller Identity (Hybrid Approach)**
Rate limits are tracked per caller identity using a hybrid approach:
* **External connections**: identity = SHA256 hash of auth token (from `get_cache_user_suffix()`)
  — survives reconnection, tied to real user identity
* **Localhost connections**: identity = transport session ID (from `_mcp_session_id`)
  — fallback for dev environments where auth is bypassed
This prevents rate limit bypass via session reconnection for external clients.

**Current Write Tools (non-readOnly)**
7 tools in Studio server are currently classified as write operations:
1. `save_studio_attack_draft` — create draft (mutating)
2. `update_studio_attack_draft` — edit draft (mutating)
3. `create_new_studio_attack` — create attack (mutating)
4. `run_studio_attack` — execute attack (destructive)
5. `set_studio_attack_status` — publish attack (destructive)
6. `run_scenario` — execute scenario test (destructive)
7. `manage_test` — pause/resume/cancel test (destructive)

All other servers (Config, Data, Utilities, Playbook) currently have only readOnly tools.

**Problem Description**
* Currently no rate limiting exists on MCP tool invocations
* A client can call write tools without any frequency restriction
* Need two independent sliding-window counters per caller:
  1. Total actions count (all non-readOnly calls) — default limit: 10 per 30 minutes
  2. Per-action-name count (same tool name) — default limit: 5 per 30 minutes
* Rate limiting must be cross-server (shared state across all 5 servers)
* Rate limiter installed on all servers (future-proofing for when other servers add write tools)

**Affected Areas**
* `safebreach_mcp_core/` — new `rate_limiter.py` module + integration into `safebreach_base.py`
* `safebreach_mcp_core/token_context.py` — caller identity extraction
* All 5 server modules — rate limiter installed in middleware stack

### Acceptance Criteria

* A new `rate_limiter.py` module in `safebreach_mcp_core/` implements sliding-window rate limiting
* Two independent limits enforced per caller identity:
  * Total non-readOnly tool calls limited to configurable max (default: 10) within a sliding window
  * Per-tool-name non-readOnly calls limited to configurable max (default: 5) within the same window
* Caller identity uses hybrid approach: auth token hash for external connections, session ID
  for localhost connections
* Sliding window duration is configurable (default: 30 minutes)
* Rate limiter uses tool annotations (`readOnlyHint`) to classify tools — read-only tools are exempt
* Rate limiting state is shared across all 5 servers (cross-server enforcement)
* Rate limiter is installed on all servers regardless of current tool classification
* When a limit is exceeded, the client receives a clear error message:
  "You exceeded the allowed rate of actions. Please try again in a few minutes."
* Configuration via environment variables:
  * `SAFEBREACH_MCP_ACTION_LIMIT` (default: 10)
  * `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` (default: 5)
  * `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` (default: 30)
* Stale caller rate-limit data is cleaned up periodically (reuse existing cleanup pattern)
* Unit tests cover: both limit types, sliding window behavior, cross-server shared state,
  read-only exemption, hybrid identity (auth token + session fallback), error messages,
  configuration overrides, stale cleanup
* Logging: rate limit events logged with masked caller ID, action name, and current count

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
As part of the MCP safety guardrails, we need to limit the rate at which actions
(non-readOnly tool calls) can be performed. This prevents misuse through repetitive
requests and allows identification of suspicious activity.

### Technical Context
* All 5 MCP servers share `SafeBreachMCPBase` with existing concurrency limiter infrastructure
* Tool annotations (`readOnlyHint`) already classify tools as read-only vs write operations
* `token_context.py` provides auth token hash for caller identity
* All servers run in the same process — module-level shared state enables cross-server rate limiting

### Caller Identity
Rate limits tracked per caller using hybrid approach:
* **External connections**: SHA256 hash of auth token (survives reconnection)
* **Localhost connections**: transport session ID (fallback for dev environments)

### Current Write Tools
7 tools in Studio server: `save_studio_attack_draft`, `update_studio_attack_draft`,
`create_new_studio_attack`, `run_studio_attack`, `set_studio_attack_status`,
`run_scenario`, `manage_test`. All other servers currently read-only.

### Functional Requirements
1. Two independent sliding-window counters per caller:
   * **Total actions count**: all non-readOnly tool calls — default limit: 10 per 30 minutes
   * **Per-action-name count**: same tool name — default limit: 5 per 30 minutes
2. Sliding window duration: configurable (default: 30 minutes)
3. Rate limiting is cross-server (shared state across all 5 servers)
4. Rate limiter installed on all servers (future-proofing)
5. Clear error message when limit exceeded:
   "You exceeded the allowed rate of actions. Please try again in a few minutes."

### Configuration
* `SAFEBREACH_MCP_ACTION_LIMIT` (default: 10)
* `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` (default: 5)
* `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` (default: 30)

### Affected Areas
* `safebreach_mcp_core/` — new `rate_limiter.py` module + `safebreach_base.py` integration
* `safebreach_mcp_core/token_context.py` — caller identity extraction
* All 5 server modules — rate limiter in middleware stack
```

**Acceptance Criteria:**
```markdown
* Two independent sliding-window limits enforced per caller (total actions + per-tool-name)
* Hybrid caller identity: auth token hash (external) / session ID (localhost)
* Read-only tools exempt via `readOnlyHint` annotation
* Cross-server shared state (all 5 servers share rate limit counters)
* Rate limiter installed on all servers
* Clear error message on limit exceeded
* Configurable via environment variables (limits + window duration)
* Stale caller data cleanup (reuse existing pattern)
* Unit tests for both limits, sliding window, cross-server, identity, exemption, errors, config, cleanup
* Logging with masked caller ID
```
