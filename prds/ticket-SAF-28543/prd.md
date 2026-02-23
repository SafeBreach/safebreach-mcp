# Reduce Cache Monitoring Log Verbosity — SAF-28543

## 1. Overview

- **Task Type**: Bug fix
- **Purpose**: Two related issues discovered on wandering-gharial during SAF-28436 feature flag work:
  1. Cache monitoring logs ~N INFO lines per polling cycle, filling Docker log buffers and drowning out
     startup/error logs critical for debugging.
  2. Uvicorn graceful shutdown stalls at "Waiting for connections to close" when SSE clients are connected,
     causing server restart to fail and the server to go down (502s).
- **Target Consumer**: Internal — DevOps / Platform team operating mcp-proxy deployments
- **Key Benefits**:
  - 1 INFO line per cycle instead of N, preserving Docker log buffer for meaningful events
  - Per-cache detail still available at DEBUG level for local troubleshooting
  - Capacity warnings (WARNING level) unchanged — actionable alerts remain visible
  - Uvicorn graceful shutdown completes within bounded time, preventing restart failures
- **Originating Request**: SAF-28543 — discovered on wandering-gharial mcp-proxy container

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-02-23 |
| **Owner** | AI Agent |
| **Current Phase** | N/A |

## 2. Solution Description

### Fix A: Cache Log Verbosity

**Chosen Solution**: Rewrite `log_cache_stats()` to emit a single condensed summary line at INFO level aggregating
all cache stats, move per-cache detail lines to DEBUG level, and preserve WARNING-level capacity alerts unchanged.

**Alternatives Considered**:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| Reduce polling frequency | Increase interval from 300s to e.g. 1800s | Zero code change | Still verbose per cycle; delays capacity warnings |
| Conditional logging | Only log caches with activity since last cycle | Fewer lines when idle | Still verbose under load; more complex state tracking |
| **Summary + DEBUG (chosen)** | Single INFO summary, per-cache at DEBUG | Minimal change; best signal-to-noise ratio | Slightly less visible per-cache detail at INFO |

**Decision Rationale**: The summary approach gives the best signal-to-noise ratio with minimal code change.
Operators who need per-cache detail can set the logger to DEBUG. Capacity warnings remain at WARNING regardless.

### Fix B: Uvicorn Graceful Shutdown Timeout

**Chosen Solution**: Add `timeout_graceful_shutdown=3` to the `uvicorn.Config` in `SafeBreachMCPBase.run_server()`.

**Problem**: When mcp-proxy restarts an MCP server (e.g., after a feature flag change), it calls
`request_shutdown()` which sets `uvicorn.Server.should_exit = True`. Uvicorn enters its shutdown path correctly
("Shutting down" → "Waiting for connections to close"), but stalls indefinitely at "Waiting for connections to
close" because active SSE clients keep connections open. After mcp-proxy's 5s timeout, it falls back to
`task.cancel()`, which orphans the listening socket. The port stays bound, restart fails, and the server goes down
returning 502s.

**Evidence from wandering-gharial logs (2026-02-23 10:40)**:
```
10:40:24 - Uvicorn: "Shutting down" → "Waiting for connections to close"
10:40:29 - WARNING: playbook graceful shutdown timed out after 5.0s
10:40:29 - Port 8003 free after shutdown: False
10:40:40 - ERROR: Cannot restart Playbook server: port 8003 still in use
10:42:27 - POST /playbook/messages/ → 502 (ConnectError: All connection attempts failed)
```

**Root Cause**: `uvicorn.Config` defaults to `timeout_graceful_shutdown=None`, which means uvicorn waits
indefinitely for active connections to close during shutdown. MCP servers use long-lived SSE connections that
never close on their own, so the shutdown hangs forever.

**Fix**: Set `timeout_graceful_shutdown=3` on the uvicorn config. After 3 seconds, uvicorn will force-close
lingering connections and complete its shutdown sequence (including closing the listening socket). This fits
within mcp-proxy's 5s outer timeout, so the graceful path completes and the port is released cleanly.

**Alternatives Considered**:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| Increase mcp-proxy timeout | Raise 5s to 30s+ | No safebreach-mcp change | Doesn't fix root cause; SSE connections never close voluntarily |
| Close SSE connections before shutdown | Actively disconnect SSE clients | Clean disconnection | Complex; requires tracking all SSE sessions |
| **timeout_graceful_shutdown (chosen)** | Let uvicorn force-close after 3s | 1-line fix; bounded shutdown | SSE clients get disconnected (acceptable — server is restarting) |

**Decision Rationale**: SSE clients will need to reconnect anyway after a server restart. Letting uvicorn
force-close them after 3s is the simplest fix and aligns with the expected behavior.

## 3. Core Feature Components

### Component A: Condensed Cache Stats Logger

- **Purpose**: Modification to existing `log_cache_stats()` in `safebreach_mcp_core/safebreach_cache.py`
- **Key Features**:
  - Collect all cache stats via existing `get_all_cache_stats()`
  - Early return if no caches are registered
  - Compute aggregate metrics: total cache count, total entries vs total capacity, average hit rate
  - Emit one INFO line with the aggregate summary
  - Emit per-cache detail lines at DEBUG level (same format as current INFO lines)
  - Preserve existing WARNING logic for caches at capacity (3+ consecutive checks) — no change

### Component B: Uvicorn Graceful Shutdown Timeout

- **Purpose**: Add `timeout_graceful_shutdown` to uvicorn config in `safebreach_mcp_core/safebreach_base.py`
- **Key Features**:
  - Set `timeout_graceful_shutdown=3` on `uvicorn.Config` in `run_server()`
  - After 3 seconds, uvicorn force-closes lingering connections and completes shutdown
  - Listening socket is properly released, enabling mcp-proxy to restart the server on the same port
  - No behavioral change for normal (non-restart) shutdown — server still exits cleanly

## 7. Definition of Done

**Fix A — Cache Log Verbosity**:
- [ ] `log_cache_stats()` emits exactly 1 INFO line per invocation (aggregate summary)
- [ ] Per-cache detail lines emitted at DEBUG level
- [ ] WARNING for caches at capacity unchanged
- [ ] Early return when no caches are registered (no log output)
- [ ] Existing unit tests updated to match new log levels and format

**Fix B — Uvicorn Graceful Shutdown**:
- [ ] `timeout_graceful_shutdown=3` added to `uvicorn.Config` in `run_server()`
- [ ] Server restart via mcp-proxy completes without port conflict (verified on wandering-gharial)
- [ ] Playbook server (or any server) returns to healthy state after feature flag–triggered restart

**Shared**:
- [ ] All cross-server tests pass (`603+` tests)

## 8. Testing Strategy

**Unit Testing**:
- **Scope**: `safebreach_mcp_core/tests/test_safebreach_cache.py` — `TestLogCacheStats` class
- **Key Scenarios**:
  - Summary INFO line contains cache count, total entries, average hit rate
  - Per-cache lines are at DEBUG level, not INFO
  - Capacity WARNING still fires after 3 consecutive full checks
  - Capacity WARNING resets when cache drops below capacity
  - Empty registry produces no log output
- **Framework**: pytest with `caplog` fixture

**No E2E changes needed** — log format is internal, no API or behavior change.

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Rewrite log_cache_stats | ⏳ Pending | - | - | |
| Phase 2: Update cache log tests | ⏳ Pending | - | - | |
| Phase 3: Add uvicorn graceful shutdown timeout | ⏳ Pending | - | - | |

### Phase 1: Rewrite `log_cache_stats()`

**Semantic Change**: Change cache monitoring from per-cache INFO logging to single summary INFO + per-cache DEBUG.

**Deliverables**: Updated `log_cache_stats()` function.

**Implementation Details**:

Modify the `log_cache_stats()` function in `safebreach_mcp_core/safebreach_cache.py` (lines 127-138):

1. Call `get_all_cache_stats()` and store the result list
2. If the list is empty, return immediately (no log output)
3. Compute aggregates from the stats list:
   - `total_entries` = sum of all `size` values
   - `total_capacity` = sum of all `maxsize` values
   - `avg_hit_rate` = average of all `hit_rate` values
4. Emit one `logger.info()` line with format:
   `"Cache summary: %d caches, %d/%d total entries, %.1f%% avg hit rate"`
5. Loop through each stat dict and emit `logger.debug()` with the existing per-cache format:
   `"Cache '%s': %d/%d entries, %.1f%% hit rate, TTL=%ds"`
6. Keep the existing WARNING check inside the loop — if `full_consecutive >= 3`, emit `logger.warning()`
   with the existing capacity message

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_core/safebreach_cache.py` | Rewrite `log_cache_stats()` (lines 127-138) |

**Test Plan**: Run existing tests (they will fail — expected, fixed in Phase 2).

**Git Commit**: `fix(cache): reduce monitoring log verbosity to single summary line (SAF-28543)`

### Phase 2: Update Tests

**Semantic Change**: Update `TestLogCacheStats` tests to assert new log levels and format.

**Deliverables**: Updated test class with correct assertions for summary INFO + per-cache DEBUG.

**Implementation Details**:

Modify `safebreach_mcp_core/tests/test_safebreach_cache.py`, class `TestLogCacheStats` (lines 427-469):

1. **Update `test_log_cache_stats_produces_info_log`** (line 436):
   - Change assertion to check for the new summary format ("Cache summary:") at INFO level
   - Add assertion that per-cache detail ("Cache 'log_test':") appears at DEBUG level, not INFO
   - Use `caplog.at_level(logging.DEBUG)` to capture both levels

2. **Add `test_log_cache_stats_empty_registry`**:
   - With empty `_cache_registry`, call `log_cache_stats()`
   - Assert no log records produced

3. **`test_capacity_warning_after_3_consecutive`** (line 444): No changes needed — WARNING assertions are
   unaffected by the INFO→DEBUG change

4. **`test_capacity_warning_resets_when_below_capacity`** (line 456): No changes needed — WARNING assertions
   are unaffected

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_core/tests/test_safebreach_cache.py` | Update `TestLogCacheStats` test assertions |

**Test Plan**: Run full test suite — all tests should pass.

**Git Commit**: `test(cache): update log_cache_stats tests for summary format (SAF-28543)`

### Phase 3: Add Uvicorn Graceful Shutdown Timeout

**Semantic Change**: Bound uvicorn's graceful shutdown so it force-closes lingering SSE connections after 3
seconds instead of waiting indefinitely.

**Deliverables**: One-line config change in `run_server()`.

**Implementation Details**:

Modify `safebreach_mcp_core/safebreach_base.py`, method `run_server()` (line 174):

1. Add `timeout_graceful_shutdown=3` to the `uvicorn.Config()` call:

```python
# Before (line 174)
config = uvicorn.Config(app=app, host=bind_host, port=port, log_level="info")

# After
config = uvicorn.Config(app=app, host=bind_host, port=port, log_level="info",
                        timeout_graceful_shutdown=3)
```

That's the entire change. No other files affected.

**Context — Why this matters**:

mcp-proxy's `_graceful_shutdown_server()` calls `request_shutdown()` (which sets `should_exit = True`) and
then waits up to 5s for the task to complete. Without `timeout_graceful_shutdown`, uvicorn's shutdown sequence
hangs at "Waiting for connections to close" because SSE clients never disconnect voluntarily. After 5s,
mcp-proxy falls back to `task.cancel()`, which orphans the listening socket (same root cause as the original
Phase 5 issue in SAF-28436). With `timeout_graceful_shutdown=3`, uvicorn force-closes connections and completes
shutdown within the 5s window.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_core/safebreach_base.py` | Add `timeout_graceful_shutdown=3` to `uvicorn.Config()` (line 174) |

**Test Plan**: No unit test needed — this is a uvicorn config parameter. Verification is on wandering-gharial:
trigger a feature flag change and confirm the server restarts without port conflict.

**Git Commit**: `fix(base): add uvicorn graceful shutdown timeout to prevent port release stall (SAF-28543)`

## 12. Executive Summary

- **Issue**: Two problems discovered on wandering-gharial during SAF-28436 feature flag work: (1) cache
  monitoring logs ~80 INFO lines per 5-minute cycle, filling Docker log buffers; (2) uvicorn graceful shutdown
  stalls on SSE connections, causing server restart failures and 502s.
- **What Will Be Built**: (A) Condensed `log_cache_stats()` with single INFO summary + per-cache DEBUG.
  (B) `timeout_graceful_shutdown=3` on uvicorn config to bound shutdown time.
- **Key Technical Decisions**: Summary + DEBUG approach for logs; uvicorn-native timeout for shutdown rather
  than active connection tracking.
- **Scope Changes**: Extended from log verbosity fix to include uvicorn shutdown timeout (same root cause
  investigation, same ticket).
- **Business Value Delivered**: ~13x reduction in cache log volume; server restarts complete reliably without
  port conflicts or downtime.
