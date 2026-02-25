# SAF-28585: Concurrency Rate Limiter Fix

## 1. Background

**Ticket**: [SAF-28585](https://safebreach.atlassian.net/browse/SAF-28585)
**Type**: Bug | **Priority**: Medium | **Assignee**: Yossi Attas | **Created**: Feb 24, 2026

The per-session concurrency limiter was introduced in SAF-28298 (Component C) to prevent MCP agents from
firing too many expensive tool calls simultaneously. Each SSE session gets a semaphore with
`SAFEBREACH_MCP_CONCURRENCY_LIMIT` slots (default: 2). When all slots are in use, additional POST
`/messages/` requests should receive HTTP 429 (Too Many Requests) with a `Retry-After: 5` header.

**Observed behavior on staging (2026-02-24)**: During pressure testing, 3 concurrent requests exceeded the
limit of 2 across data and playbook servers. Zero HTTP 429 responses were returned. Zero concurrency-related
warning logs appeared. The limiter was completely non-functional.

---

## 2. Root Cause Analysis

### 2.1 The ContextVar Problem

The middleware stored the session ID in a `contextvars.ContextVar`:

```
_mcp_session_id: contextvars.ContextVar[Optional[str]]
```

**How the MCP SSE transport works:**
1. Client opens a long-lived `GET /sse` connection (SSE stream)
2. Server sends an `endpoint` event containing `data: /messages/?session_id=<hex>`
3. Client sends tool calls as `POST /messages/?session_id=<hex>` (separate HTTP requests)

**Why the ContextVar approach fails:** Python's `contextvars.ContextVar` is scoped to the current async
task. In uvicorn, each HTTP request runs as a separate `asyncio.Task`. The ContextVar set during the SSE
GET handler is **invisible** to all subsequent POST `/messages/` handlers. Every POST sees
`_mcp_session_id.get() == None`, falls through the limiter, and executes unthrottled.

### 2.2 UUID Mismatch (Secondary Issue)

Even if ContextVar propagation worked, the middleware created its own `str(uuid.uuid4())` (hyphenated
format: `550e8400-e29b-41d4-a716-446655440000`) while FastMCP uses `uuid4().hex` (no hyphens:
`550e8400e29b41d4a716446655440000`). The session IDs would never match between SSE and POST.

### 2.3 Why Existing Unit Tests Passed

The original tests in `TestConcurrencyLimiter` manually inject session IDs:

```python
_mcp_session_id.set(session_id)                    # Set ContextVar in the same task
_session_semaphores[session_id] = (sem, time.time())  # Directly populate the dict
```

Both operations run in the **same async task** as the middleware, so `_mcp_session_id.get()` returns the
injected value. This bypasses the real-world SSE-to-POST task boundary entirely. The 429 response logic
works correctly in isolation -- it's the session lookup via ContextVar that fails.

### 2.4 Impact

- **All 5 MCP servers** (Config, Data, Utilities, Playbook, Studio) were affected
- No protection against agents firing many expensive tool calls simultaneously
- Risk of API rate limiting from upstream SafeBreach platform, or excessive resource consumption

---

## 3. Approach Considerations

### 3.1 Option A: Parse session_id from query string (Chosen)

Parse `session_id` from the ASGI `scope["query_string"]` on POST `/messages/` requests. This is the same
session_id that FastMCP already embeds in every POST URL.

**Pros**: Simple, no dependency on response interception, uses data already available in every request.
**Cons**: Needs lazy semaphore creation if SSE migration hasn't happened yet.

### 3.2 Option B: Propagate ContextVar across tasks

Use `asyncio.Task` context copying or a custom task factory to propagate ContextVar values.

**Rejected**: Invasive, uvicorn doesn't expose task creation hooks, and would couple the middleware to
uvicorn internals.

### 3.3 Option C: Store session_id in a thread-local or global mapping by client IP/port

**Rejected**: Multiple sessions can share the same client IP. Port reuse makes this unreliable.

### 3.4 Semaphore Leak Prevention

The initial query-string fix introduced a leak: SSE creates a semaphore under a middleware-generated UUID,
while POST creates a *second* semaphore under the FastMCP session_id via lazy creation. The SSE disconnect
cleanup only removes the middleware UUID key, leaving the FastMCP key orphaned until the stale semaphore
cleanup runs (every 10 minutes, max age 1 hour).

**Solution**: Session ID migration. On SSE, intercept the outgoing response body to capture the real
FastMCP session_id from the `endpoint` event. Re-key the semaphore from the middleware UUID to the
FastMCP session_id. On SSE disconnect, clean up the migrated key. Result: exactly one semaphore per
session, properly cleaned up on disconnect.

---

## 4. Details of Fix

### 4.1 Files Modified

| File | Change |
|------|--------|
| `safebreach_mcp_core/safebreach_base.py` | Added `import re`. Rewrote SSE and messages paths in `_create_concurrency_limited_app()` |
| `tests/test_concurrency_limiter.py` | Added `TestConcurrencyLimiterSAF28585` class (8 tests). Updated `make_scope()` helper |
| `tests/test_e2e_concurrency_limiter.py` | New file. E2E test with real uvicorn + SSE + concurrent POSTs |

### 4.2 SSE Path Changes (`/sse`)

**Before**: Created a middleware UUID, stored it in ContextVar and `_session_semaphores`. Cleaned up the
middleware UUID on SSE disconnect.

**After**: Still creates a middleware UUID and semaphore immediately (backward compat with unit tests that
use AsyncMock as original_app). Additionally intercepts outgoing SSE response body chunks via
`cleanup_send()`. When the FastMCP `endpoint` event is detected (regex: `session_id=([a-f0-9]+)`),
migrates the semaphore from the middleware key to the real FastMCP key. On SSE disconnect, cleans up
whichever key is active (migrated or middleware fallback).

Key code flow:
```
SSE connect → middleware_session_id created → semaphore stored
  ↓
FastMCP sends endpoint event → regex captures real_session_id
  ↓
_session_semaphores[middleware_session_id] removed
_session_semaphores[real_session_id] = (same semaphore, timestamp)
  ↓
SSE disconnect → _session_semaphores[real_session_id] removed → clean
```

### 4.3 Messages Path Changes (`/messages/`)

**Before**: `session_id = _mcp_session_id.get()` -- always `None` in separate task.

**After**: Two-phase lookup:
1. Try ContextVar (backward compat with unit tests running in same task)
2. If ContextVar is `None` or doesn't match a known session, parse `session_id` from
   `scope["query_string"]`

If the session_id is found but not yet in `_session_semaphores` (edge case: POST arrives before SSE
migration), lazy-creates a new semaphore as a defensive fallback.

The `lookup_source` variable (`"contextvar"` or `"query_string"`) is logged in debug output to confirm
which path was taken in production.

### 4.4 Additional Improvements

- Removed `sem._value == 0` private attribute access (redundant with `sem.locked()`)
- Added comprehensive debug/info/warning logs at every decision point (see Section 7)

---

## 5. Test Coverage

### 5.1 Test Summary

| Suite | File | Tests | Purpose |
|-------|------|-------|---------|
| Unit (pre-existing) | `tests/test_concurrency_limiter.py` `TestConcurrencyLimiter` | 11 | Original limiter behavior (ContextVar path) |
| Integration (new) | `tests/test_concurrency_limiter.py` `TestConcurrencyLimiterSAF28585` | 8 | Bug reproduction + fix verification + leak prevention |
| Stale cleanup | `tests/test_concurrency_limiter.py` `TestStaleSemaphoreCleanup` | 4 | Stale semaphore TTL cleanup |
| E2E (new) | `tests/test_e2e_concurrency_limiter.py` | 1 | Real uvicorn + SSE + concurrent POSTs |
| **Total** | | **24** | |

### 5.2 New Integration Tests (TestConcurrencyLimiterSAF28585)

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_contextvar_not_propagated_between_tasks` | ContextVar set in one `asyncio.Task` is invisible in another (root cause proof) |
| 2 | `test_separate_task_post_bypasses_exhausted_semaphore` | POST in separate task bypasses exhausted semaphore when no query string (documents the bug path) |
| 3 | `test_query_string_session_id_should_produce_429` | POST with session_id in query string gets 429 when semaphore exhausted |
| 4 | `test_query_string_session_id_under_limit_acquires_semaphore` | POST with session_id in query string acquires semaphore (uses `TrackingSemaphore` subclass) |
| 5 | `test_sse_migration_cleanup_no_leak` | After SSE disconnect with migration, zero semaphores remain (no leak) |
| 6 | `test_sse_migration_rekeys_semaphore` | After SSE sends endpoint event, semaphore is re-keyed to FastMCP session_id (no duplicate) |

Tests 1-2 document the **bug behavior** (pass on both buggy and fixed code).
Tests 3-4 were **TDD red** tests (failed on buggy code, pass after fix).
Tests 5-6 verify **leak prevention**.

### 5.3 E2E Test (TestConcurrencyLimiterE2ESAF28585)

`test_concurrency_limiter_enforced` -- starts a real MCP server with:
- `uvicorn.Server` running in an `asyncio.Task`
- Raw TCP connection to `/sse` to extract the messages URL (httpx doesn't flush chunked SSE reliably)
- MCP session initialization (`initialize` + `notifications/initialized`)
- 10 concurrent tool calls via `asyncio.gather`
- Asserts: some HTTP 429 responses (limiter enforced)
- Asserts: all responses are 200, 202, or 429

**Design decisions**:
- Raw TCP for SSE (httpx chunked encoding doesn't flush SSE events reliably)
- Single test method (sse_starlette's `AppStatus.should_exit_event` binds to the first event loop;
  multiple `asyncio.run()` calls break it)
- Marked `@pytest.mark.e2e` but does **not** require a real SafeBreach environment

### 5.4 Tested Flows

| Flow | Coverage |
|------|----------|
| SSE → POST with query string (normal production flow) | E2E test + integration tests 3, 4 |
| SSE → POST without query string (ContextVar path) | Unit tests (TestConcurrencyLimiter) |
| Session migration (middleware UUID → FastMCP session_id) | Integration tests 5, 6 |
| Session cleanup on SSE disconnect (migrated) | Integration test 5 |
| Session cleanup on SSE disconnect (non-migrated) | Unit test `test_sse_cleanup_on_end` |
| 429 response format (status, headers, body) | Unit tests `test_message_over_limit_returns_429`, `test_retry_after_header_in_429` |
| Independent session limits | Unit test `test_different_sessions_independent_limits` |
| No session → pass through | Unit test `test_no_session_passes_through` |
| Non-HTTP scope → pass through | Unit test `test_non_http_passes_through` |
| Stale semaphore cleanup (TTL) | Stale cleanup tests (4 tests) |
| ContextVar non-propagation proof | Integration test 1 |
| Concurrent requests exceeding limit (real HTTP) | E2E test |

### 5.5 Cross-Server Regression

Full test suite: **607 passed, 1 skipped, 0 failed** (Config + Data + Utilities + Playbook + Studio +
concurrency tests).

---

## 6. Semaphore Lifecycle

```
Phase              _session_semaphores                     Notes
─────              ───────────────────                     ─────
SSE connects       {mw_uuid: (sem, ts)}                   Middleware creates semaphore
FastMCP endpoint   {real_id: (sem, ts)}                    Migrated (same sem object)
POST /messages/    sem.acquire() → process → sem.release() Query string lookup finds real_id
SSE disconnects    {}                                      cleanup_send removes real_id
```

**Defensive fallback**: If POST arrives before migration (unlikely but possible), lazy-creates a new
semaphore under the query string session_id. This semaphore would be cleaned up by the stale semaphore
cleanup task (runs every 10 min, removes entries older than 1 hour).

---

## 7. Staging Investigation and Troubleshooting

### 7.1 Log Messages Reference

| Log Message | Level | When | What to Check |
|-------------|-------|------|---------------|
| `🆔 New SSE session: abc12... (limit=2, active_sessions=3)` | INFO | SSE connects | Session count growing? |
| `SSE body chunk for abc12... — no session_id found (len=0)` | DEBUG | SSE response body without session_id | Migration not happening? |
| `🔄 Session migrated: abc12... → def45...` | INFO | FastMCP session_id captured | Confirms migration works |
| `🧹 Cleaned up session: def45... (migrated=yes, remaining=2)` | INFO | SSE disconnects | `remaining` should trend toward 0 |
| `🆔 Session registered (from query): def45...` | INFO | Lazy creation fallback | Should be rare -- investigate if frequent |
| `🔓 Acquired semaphore for def45... (slots=1/2, lookup=query_string)` | DEBUG | POST passes through | `lookup` should be `query_string` in production |
| `⚠️ Rate limited session def45... (limit=2, lookup=query_string)` | WARNING | 429 returned | Limiter is working |
| `⏩ No session_id found — pass through (path=/messages/)` | DEBUG | No session to track | Should not happen in normal MCP flow |
| `🧹 Cleaned up N stale SSE semaphore(s), M remaining` | INFO | Stale cleanup (every 10 min) | `N` should be 0 in healthy state |

### 7.2 Staging Verification Steps

1. **Enable DEBUG logging** on one server:
   ```bash
   LOG_LEVEL=DEBUG uv run -m safebreach_mcp_data.data_server
   ```

2. **Connect a client** (Claude Desktop or mcp-remote) and verify log sequence:
   ```
   INFO  🆔 New SSE session: abc12... (limit=2, active_sessions=1)
   INFO  🔄 Session migrated: abc12... → def45...
   DEBUG 🔓 Acquired semaphore for def45... (slots=1/2, lookup=query_string)
   ```

3. **Confirm `lookup=query_string`**: If you see `lookup=contextvar`, the ContextVar path is being
   used -- this should not happen in production uvicorn.

4. **Pressure test**: Send 5+ concurrent tool calls and verify:
   - `⚠️ Rate limited` warnings appear
   - HTTP 429 responses are returned to the client
   - `slots=0/2` visible in debug logs before 429

5. **Disconnect client** and verify cleanup:
   ```
   INFO  🧹 Cleaned up session: def45... (migrated=yes, remaining=0)
   ```

6. **Check for leaks**: After all clients disconnect, `remaining=0` should appear. If `remaining > 0`
   persists, check if lazy-created semaphores are accumulating (the `🆔 Session registered (from query)`
   log indicates this path).

### 7.3 Troubleshooting Decision Tree

```
Problem: No 429s during concurrent load
├── Check: Are WARNING logs appearing?
│   ├── No → session_id lookup is failing
│   │   ├── Check: Is "lookup=query_string" in DEBUG logs?
│   │   │   ├── No → query string not being parsed (check scope["query_string"])
│   │   │   └── Yes → session_id not in _session_semaphores (migration issue)
│   │   └── Check: Is "Session migrated" log appearing?
│   │       ├── No → FastMCP endpoint event not captured (check regex)
│   │       └── Yes → timing issue (POST before migration)
│   └── Yes → 429 is being sent but client not seeing it
│       └── Check: proxy/load balancer swallowing 429?

Problem: Semaphore count growing (remaining > 0 after disconnect)
├── Check: Is "Cleaned up session" log appearing?
│   ├── No → SSE disconnect not detected (check more_body=False)
│   └── Yes → wrong key being cleaned up
│       └── Check: Is "migrated=yes" in cleanup log?
│           ├── No → migration didn't happen, middleware key cleaned but lazy key orphaned
│           └── Yes → should be clean -- check for duplicate SSE connections
```

---

## 8. Staging Validation Results (2026-02-25)

### 8.1 Deployment

- **Environment**: staging.safebreach.com (`i-05fe824175e5d416c`)
- **Image**: `feature_SAF-28436-Add-cache-environment-variables-to-mcp-proxy-latest` (SHA `7d8269cb4ae1`)
- **Service**: `sbmcp-proxy` — confirmed running at 08:36:54 UTC
- **Servers**: All 5 MCP servers initialized with concurrency limiter (limit=2)

### 8.2 Fix Verification

Session lifecycle confirmed working end-to-end via disk log file (`sbmcp-proxy.log`):

1. **SSE session creation**: 3 sessions created with `active_sessions` counter
2. **Session ID migration**: All 3 migrated from middleware UUID to FastMCP session ID
   (e.g., `a82498cc → 5af78873`)
3. **Query string lookup**: All rate limit events logged with `lookup=query_string`
   (not broken ContextVar path)
4. **Session cleanup**: Previous sessions cleaned up with `migrated=yes, remaining=0`

**Comparison with broken image (SHA `67d0d7d5`):** A console redeploy at 08:19 overwrote our image
with the default image. That deployment showed zero session migrations and zero 429s during the same
pressure test — confirming the fix is not in the default image and the query-string path is essential.

**Important operational note**: The `safebreach_mcp_core.safebreach_base` logger output does NOT appear
in docker container logs (`docker logs mcp-proxy`). Concurrency limiter logs are only visible in the disk
log file at `/datadb/logs/sbmcp-proxy.log` via `mgmt_get_log_file`. This is because the systemd service
redirects stdout to the log file (`>> /datadb/logs/sbmcp-proxy.log`), while docker's log driver only
captures the container's internal stdout/stderr.

### 8.3 Pressure Test 1 — Data Server (08:42)

| Metric | Value |
|--------|-------|
| **Target** | Data server, session `5af78873` |
| **Peak burst** | ~12 concurrent `get_test_details` calls in 30ms |
| **Proxy 429s** | 3 (WARNING logs with `lookup=query_string`) |
| **Agent-visible errors** | 3 (`safebreachData_get_test_details` HTTP 429) |
| **Post-burst behavior** | Agent settled to 2 concurrent after rejection |
| **Memory** | 64.5 MiB → 398 MiB (+333.5 MiB from data payloads) |

Agent request timeline:
```
08:42:09   ████████████  ~12 concurrent (BURST — 3 agent errors)
08:42:13   ██            2 sequential (agent respects limit)
08:42:16   ██            2 sequential
08:42:21   ██            2 sequential
           ··· 28s gap — long-running data processing ···
08:42:49   ██            2 sequential
08:42:55   ████          2 pairs interleaved
08:42:59   ████          4 playbook requests
08:43:08   ████          4 data requests
```

Total: 42 requests across 3 servers (data 86%, playbook 10%, config 5%).

### 8.4 Pressure Test 2 — Playbook Server (09:13)

| Metric | Value |
|--------|-------|
| **Target** | Playbook server, session `37f20b32` |
| **Peak burst** | ~10+ concurrent requests in 5ms |
| **Proxy 429s** | 10 (8 at 09:13:30, 2 at 09:13:35) |
| **Retry behavior** | Agent retried after exactly 5s (honoring Retry-After) but burst again |
| **Memory** | 398 MiB → 492.4 MiB (70.3% of 700 MiB limit) |

More aggressive than test 1: 10 rejections vs 3. The agent honored the `Retry-After: 5` header
(5.0s gap between bursts) but fired another burst on retry, exceeding the limit again.

### 8.5 Redundant Layered Rate Limiting — Discovery and Analysis

During staging analysis, we discovered that rate limiting is applied at **two independent layers**
in the proxy deployment architecture:

```
Agent → Proxy (port 4150) → MCP Server (port 8002)
         ↑ limiter #1            ↑ limiter #2
```

Both layers exist because the proxy and MCP servers independently inherit from `SafeBreachMCPBase`,
which always wraps the ASGI app with `_create_concurrency_limited_app()`. In a direct deployment
(client → MCP server), there's correctly one layer. In the proxy deployment, both apply.

**How requests flow through the layers:**

- **Rejected at proxy**: `sem.locked()` → immediate 429, request never forwarded to backend.
  The proxy middleware logs a WARNING and the agent receives an HTTP 429 error.
- **Passed proxy, rejected at backend**: Request passes the proxy's TOCTOU pre-check, proxy acquires
  its semaphore and forwards to the MCP server. The MCP server's own limiter rejects it with 429.
  The proxy returns this 429 to the agent, but the agent's MCP SDK may handle it differently from
  a direct proxy rejection.

**Observed in pressure test 1:**

| Layer | 429 count | Evidence |
|-------|-----------|----------|
| Proxy middleware | 3 | 3 WARNING logs at 08:42:09.975-09.986 |
| MCP server backend | 3 | 3 httpx 429 responses from port 8002 |
| Agent-visible errors | 3 | Only the proxy-level rejections surfaced |

The agent saw exactly 3 errors despite 6 total rejections — the backend rejections were absorbed
by the proxy/SDK layer and did not surface as tool execution failures.

**Problems with the double layer:**

1. **Orphaned semaphores**: The backend MCP server lazy-creates semaphores from the forwarded URL's
   session_id. These have no SSE lifecycle (no migration, no disconnect cleanup) and are only cleaned
   up by the stale cleanup task (every 10 min, max age 1 hour).
2. **Confusing logs**: 6 server-side events for 3 logical rejections. Log analysis requires
   understanding which layer produced each entry.
3. **Wasted work**: Requests that pass the proxy limiter, get forwarded, and are rejected at the
   backend consume a proxy semaphore slot and an HTTP round-trip for nothing.
4. **Not defense-in-depth**: A single request cannot be caught by both layers. The proxy either
   rejects (backend never sees it) or passes (backend may catch it). The layers don't reinforce
   each other — they independently race to reject.

### 8.6 Sign-Off

- Fix confirmed working on staging with real agent traffic (breach-genie v1.65.0)
- Concurrency limiter correctly bounds per-session requests to the configured limit
- Session lifecycle (create → migrate → rate limit → cleanup) fully validated
- No semaphore leaks observed across multiple test cycles
- Agent correctly receives 429 with `retry_after: 5` and adapts its concurrency

---

## 9. Future Considerations

1. **MCP Streamable HTTP transport**: FastMCP is migrating from SSE to Streamable HTTP. The session_id
   mechanism may change. Monitor FastMCP releases and update the regex pattern if needed.

2. **Blocking vs rejecting**: Current behavior rejects with 429 when all slots are full. An alternative
   is to queue requests and wait for a slot (blocking acquire). This would increase latency but reduce
   client-side retry complexity. Not implemented -- current 429 approach is simpler and matches HTTP
   semantics.

3. **Per-tool granularity**: The current limiter is per-session (all tools share the same semaphore). A
   future enhancement could apply different limits to expensive vs cheap tools.

4. **TOCTOU window**: The `sem.locked()` check followed by `async with sem:` has a tiny race window
   where two simultaneous requests could both see `locked() == False` and both enter the semaphore.
   The second request would block (not get 429) until the first completes. This is acceptable behavior
   -- the semaphore still bounds concurrency correctly; the 429 fast-path is best-effort.

5. **Eliminate redundant backend limiting in proxy deployments**: The double-layer rate limiting
   discovered during staging validation (Section 8.5) should be resolved. Recommended approach:
   add a configuration flag `SAFEBREACH_MCP_BEHIND_PROXY=true` (or detect automatically via
   request origin) to disable `_create_concurrency_limited_app()` on backend MCP servers when
   they run behind the proxy. The proxy is the correct enforcement point — it owns the client
   session lifecycle (SSE connect → migrate → disconnect → cleanup) and is the only layer that
   can properly manage semaphore state. Backend servers behind the proxy should skip the limiter
   to avoid orphaned semaphores, confusing logs, and wasted forwarding round-trips.

6. **Memory growth under pressure**: Staging tests showed mcp-proxy memory growing from 64.5 MiB
   to 492.4 MiB (70.3% of 700 MiB limit) across two pressure tests without releasing between them.
   This is driven by large data payloads (simulation data), not the concurrency limiter itself.
   The concurrency limiter helps indirectly by capping the number of concurrent heavy requests,
   but payload-level memory management (streaming responses, bounded response buffers) may be
   needed if memory pressure becomes a production issue.

---

## 10. Document Status

| Field | Value |
|-------|-------|
| **Status** | Complete |
| **Last Updated** | 2026-02-25 |
| **Owner** | Yossi Attas |
| **Branch** | `SAF-28582-full-sim-logs-error` |
