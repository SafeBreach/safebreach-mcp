# Per-Caller Rate Limiting for MCP Write Operations — SAF-29871

## 1. Overview

- **Task Type**: Feature
- **Purpose**: Prevent misuse of MCP write operations by limiting the rate at which actions can
  be performed per caller, containing potential damage and enabling detection of suspicious activity
- **Target Consumer**: Internal — MCP server infrastructure (affects all MCP clients)
- **Key Benefits**:
  - Safety guardrail against malicious or misconfigured clients performing unlimited write operations
  - Enables identification of suspicious repetitive action patterns
  - Configurable limits allow tuning per deployment environment
- **Business Alignment**: Part of MCP safety guardrails initiative for responsible AI agent operation
- **Originating Request**: [SAF-29871](https://safebreach.atlassian.net/browse/SAF-29871)

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | In Progress |
| **Last Updated** | 2026-05-11 11:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | Phase 1 of 7 complete |

---

## 2. Solution Description

### Chosen Solution: Explicit Two-Phase Gate with Shared Helper

A new `rate_limiter.py` module in `safebreach_mcp_core/` provides a singleton `RateLimiter` class
with two methods: `check_limit()` (pre-check, raises `ToolError` if exceeded) and `record_action()`
(post-success increment). A `get_caller_identity()` helper encapsulates hybrid caller identification
(auth token hash for external connections, session ID fallback for localhost).

Each write tool explicitly calls both methods at the appropriate points in its code — after
validation but before the mutating API call (`check_limit`), and after the API call succeeds
(`record_action`). This per-tool placement ensures dry-run invocations and failures are not counted.

**Data structure**: Module-level dict mapping caller ID to a list of action timestamps.
On each check/record, entries older than the sliding window are pruned. Cross-server sharing is
automatic since all 5 servers run in the same process.

### Alternatives Considered

**Approach A — Fully Explicit (no shared helper)**:
Each tool extracts caller identity and manages gate calls independently.
- Pros: Maximum clarity, no abstractions
- Cons: Repeated boilerplate in each tool, caller ID extraction duplicated 6 times

**Approach C — Decorator-Based**:
A `@rate_limited()` decorator wraps each write tool, with `skip_record_if` lambdas for dry-run.
- Pros: Minimal boilerplate, hard to forget
- Cons: Hides gate timing, fights per-tool placement (e.g., `run_scenario` has early returns
  before real work; `set_studio_attack_status` does pre-check GETs)

### Decision Rationale

Approach B provides explicit control over gate placement (critical for `run_scenario`'s dry-run
branches and `set_studio_attack_status`'s pre-check reads) while reducing boilerplate through the
shared `get_caller_identity()` helper. The two-phase pattern (check without increment, then record
on success) can only work correctly with per-tool placement since "success" is defined differently
for each tool.

---

## 3. Core Feature Components

### Component A: Rate Limiter Module (`safebreach_mcp_core/rate_limiter.py`)

**Purpose**: New module providing the rate limiting engine and caller identity helper.

**Key Features**:
- `RateLimiter` singleton class with cross-server shared state (module-level dict)
- `check_limit(caller_id, tool_name)` — verifies both total and per-tool-name counts are below
  limits within the sliding window. Raises `ToolError` with user-friendly message if exceeded.
  Does NOT increment any counter.
- `record_action(caller_id, tool_name)` — appends current timestamp to both the total actions
  list and the per-tool-name list for the caller. Called only after successful, non-dry-run execution.
- `get_caller_identity()` — hybrid caller identification:
  - External connections: SHA256 hash of auth token (from `get_cache_user_suffix()` pattern)
  - Localhost connections: transport session ID (from `_get_session_id_from_mcp_ctx()`)
  - Fallback: `'anonymous'` if neither is available
- Sliding window pruning: on every `check_limit` and `record_action` call, timestamps older than
  the window duration are removed
- `_cleanup_stale_rate_limits()` — background async task (every 10 minutes) that evicts caller
  entries with no activity within the TTL period (1 hour, matching existing semaphore cleanup)
- Configuration read from environment variables at module load time

**Data Structure**:
```
_rate_limit_store: Dict[str, CallerRateLimitData]

CallerRateLimitData:
  total_actions: List[float]          # timestamps of all write tool calls
  per_tool_actions: Dict[str, List[float]]  # tool_name -> timestamps
  last_activity: float                # for stale cleanup
```

### Component B: Per-Tool Gate Integration (Studio Server)

**Purpose**: Integrate `check_limit` and `record_action` calls into each of the 6 write tools.

**Key Features**:
- Each tool calls `get_caller_identity()` to obtain the caller key
- `check_limit` placed after parameter validation, before the mutating API call
- `record_action` placed after the API call succeeds and response is parsed
- Special handling per tool:
  - `run_scenario`: gates only on the queue-submission branch (skip diagnostic and dry_run returns)
  - `set_studio_attack_status`: `check_limit` placed after the pre-check GET (allow reads first)
  - `manage_test`: `record_action` after state change (note append is best-effort, doesn't gate)

**6 Tools Requiring Gates**:

| Tool | check_limit placement | record_action placement | Special handling |
|------|----------------------|------------------------|------------------|
| `save_studio_attack_draft` | After param validation | After POST + cache write | None |
| `update_studio_attack_draft` | After param validation | After PUT + cache update | None |
| `run_studio_attack` | After input validation | After POST queue response | None |
| `set_studio_attack_status` | After pre-check GET confirms status | After PUT + cache invalidate | Allow pre-check read first |
| `run_scenario` | After early returns (not_ready, dry_run) | After POST queue response | Skip gates on non-queue branches |
| `manage_test` | After input validation | After state change + note | Note append is best-effort |

Note: `create_new_studio_attack` was initially classified as write but is actually read-only
(returns static boilerplate templates, no API calls). It does NOT need rate limiting gates.

### Component C: Documentation Update (CLAUDE.md)

**Purpose**: Document the two-phase gate pattern so future write tools follow it consistently.

**Key Features**:
- Add a "Rate Limiting" section to CLAUDE.md under Key Design Patterns
- Document the `check_limit` / `record_action` API and gate placement rules
- Include the gate placement table for existing tools as reference
- Specify that any new non-readOnly tool must integrate rate limiting gates

---

## 6. Non-Functional Requirements

### Security & Compliance

- **Caller Identity**: Auth token hash provides stable identity that survives reconnection,
  preventing rate limit bypass via session reset
- **Logging**: Rate limit events logged with masked caller ID (first 8 chars of hash) —
  never log raw tokens
- **Fail-open vs fail-closed**: If caller identity cannot be determined, rate limiting still
  applies using `'anonymous'` as the caller key (fail-closed)

### Performance Requirements

- **Overhead**: Sliding window check/prune is O(n) where n = number of timestamps in window.
  With max 10 actions per 30 minutes, this is negligible
- **Memory**: Per-caller storage is bounded by window size × action count. With 10 actions max
  per caller per 30 minutes, memory per caller is ~80 bytes (10 floats)
- **Cleanup**: Background task every 10 minutes prevents unbounded growth from disconnected clients

### Technical Constraints

- **Thread safety**: All servers run in the same asyncio event loop (single-threaded).
  Module-level dict operations are safe. No explicit locking needed for the rate limit store.
- **Cross-server**: Module-level dict is automatically shared across all 5 servers since
  `MultiServerLauncher` runs them in the same process via `asyncio.gather()`
- **Backward Compatibility**: No breaking changes. Rate limiter is transparent to read-only tools.
  Write tools get gates added but behavior is unchanged when within limits.

### Monitoring & Observability

- **Logging**: Info-level log on each `record_action` (caller masked, tool name, current counts)
- **Warning log**: When a caller is rate-limited (which limit was hit, current count, limit value)
- **Debug log**: On `check_limit` pass (for troubleshooting)
- **Cleanup log**: Info-level when stale entries are evicted

---

## 7. Definition of Done

- [ ] `rate_limiter.py` module created with `RateLimiter` class, `get_caller_identity()`, and cleanup task
- [ ] Two independent sliding-window limits enforced: total actions (default 10) and
  per-tool-name (default 5) within configurable window (default 30 min)
- [ ] Hybrid caller identity: auth token hash for external, session ID for localhost, `'anonymous'` fallback
- [ ] `check_limit` raises `ToolError` with an informative message that includes:
  which limit was exceeded (total actions or specific tool name), and how many seconds
  until the oldest action in the window expires (computed retry-after).
  Example: "Rate limit exceeded: total actions (10/10 in last 30 min). Try again in 847 seconds."
  or: "Rate limit exceeded: run_scenario (5/5 in last 30 min). Try again in 423 seconds."
- [ ] `record_action` only increments on successful, non-dry-run execution
- [ ] All 6 write tools in Studio server have gates at correct positions
- [ ] `run_scenario` dry-run and diagnostic branches do not trigger gates
- [ ] Configuration via environment variables:
  - `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` (default: true)
  - `SAFEBREACH_MCP_ACTION_LIMIT` (default: 10)
  - `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` (default: 5)
  - `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` (default: 30)
- [ ] Cross-server shared state verified (module-level dict across all 5 servers)
- [ ] Stale caller data cleaned up periodically (10-min interval, 1-hour TTL)
- [ ] CLAUDE.md updated with rate limiting pattern documentation
- [ ] Unit tests pass for: both limit types, sliding window behavior, two-phase gate (dry-run
  excluded, failures excluded), hybrid identity, informative error messages (limit type +
  retry-after), configuration overrides, enable/disable, stale cleanup
- [ ] E2E tests pass: rate limit trigger, dry-run exclusion, disable switch, window expiry
- [ ] Logging with masked caller ID on record, warning on limit hit, info on cleanup

---

## 8. Testing Strategy

### Unit Testing

**Scope**: `safebreach_mcp_core/rate_limiter.py` and gate integration in Studio server tools

**Key Scenarios**:

**RateLimiter class**:
- `check_limit` passes when count is below both limits
- `check_limit` raises `ToolError` when total action limit exceeded
- `check_limit` raises `ToolError` when per-tool-name limit exceeded
- `check_limit` does NOT increment counters (verify count unchanged after call)
- `record_action` increments both total and per-tool-name counters
- Sliding window correctly prunes timestamps older than window duration
- Window boundary: action at exactly window edge is counted; action 1ms past is pruned
- Multiple callers tracked independently
- Multiple tool names tracked independently per caller
- Stale cleanup removes entries with no activity past TTL
- Stale cleanup preserves entries with recent activity

**get_caller_identity()**:
- Returns auth token hash when auth artifacts available
- Returns session ID when no auth artifacts (localhost)
- Returns `'anonymous'` when neither is available
- Hash is stable: same token always produces same identity

**Configuration**:
- Custom limits via environment variables are respected
- `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=false` disables all rate limiting
- Default values used when env vars not set

**Gate integration (per-tool)**:
- `check_limit` called before API mutation (mock API, verify check happens first)
- `record_action` called after successful API response
- `record_action` NOT called on API failure (exception path)
- `run_scenario`: gates NOT called on dry_run or not_ready branches
- `set_studio_attack_status`: pre-check GET allowed before `check_limit`

**Cross-server**:
- Actions recorded on one server instance are visible to another
  (import same module, verify shared state)

**Framework**: pytest with unittest.mock

### Integration Testing

**Scope**: Multi-server rate limit enforcement

**Key Scenarios**:
- Rate limit state shared across Config and Studio server instances
- Cleanup task runs and evicts stale entries
- Rate limiter disabled via env var does not interfere with tool execution

### E2E Testing

**Scope**: End-to-end rate limit enforcement against a real SafeBreach environment.
Marked with `@pytest.mark.e2e`, excluded by default. Use a short sliding window
(`SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES=1`) to keep tests fast.

**Key Scenarios**:
- Call a write tool (e.g., `run_scenario` with `dry_run=False` or `manage_test`) multiple times
  against a real console and verify rate limit triggers after exceeding the configured limit
- Verify dry-run invocations (`run_scenario` with `dry_run=True`) do NOT count toward limits
- Verify the error message includes which limit was exceeded and retry-after seconds
- Verify that after the window expires, the tool can be called again successfully
- Verify rate limiter can be disabled via `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=false`

**Test Environment**:
- Requires `source .vscode/set_env.sh` for real SafeBreach credentials
- Use `E2E_CONSOLE` env var for target console
- Set `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES=1` and `SAFEBREACH_MCP_ACTION_LIMIT=2`
  / `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT=1` to trigger limits quickly

---

## 9. Implementation Phases

Each phase is a thin vertical slice following TDD: write tests first, then implement the minimum
code to pass them. Every phase produces a working, tested increment that can be committed and
verified independently.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Total action limit on manage_test | ✅ Complete | 2026-05-11 | pending | 14 unit + 3 gate tests pass |
| Phase 2: Per-tool-name limit | ⏳ Pending | - | - | Second limit type |
| Phase 3: Dry-run exclusion (run_scenario) | ⏳ Pending | - | - | Most complex gate |
| Phase 4: Remaining 4 tools | ⏳ Pending | - | - | Full tool coverage |
| Phase 5: Hybrid caller identity | ⏳ Pending | - | - | Production-ready identity |
| Phase 6: Cleanup + server lifecycle | ⏳ Pending | - | - | Memory management |
| Phase 7: Documentation | ⏳ Pending | - | - | CLAUDE.md pattern |

---

### Phase 1: Total Action Limit on `manage_test`

**Semantic Change**: Deliver a working rate limiter that enforces the total action limit on
the simplest write tool (`manage_test`), fully tested end-to-end.

**Deliverables**: `rate_limiter.py` with `RateLimiter` class + `get_caller_identity()`,
`manage_test` with gates, unit tests, E2E test.

**Tests First (TDD)**:

1. **Unit tests** (`safebreach_mcp_core/tests/test_rate_limiter.py`):
   - `check_limit` passes when count is zero
   - `check_limit` passes when count is below total limit
   - `check_limit` raises `ToolError` when total limit reached
   - `check_limit` does NOT increment counters
   - `record_action` increments total count
   - Sliding window: record actions, advance time past window, verify pruned
   - Error message contains "total actions", count/limit, and retry-after seconds
   - Multiple callers are independent
   - Disabled via env var: `check_limit` passes, `record_action` is no-op
   - Custom limit via `SAFEBREACH_MCP_ACTION_LIMIT` env var is respected
   - Custom window via `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` is respected

2. **Unit tests** for `get_caller_identity()`:
   - Returns session ID when no auth artifacts (localhost)
   - Returns `'anonymous'` when neither available
   - (Auth token hash tests deferred to Phase 5)

3. **Gate integration test** (`safebreach_mcp_studio/tests/test_rate_limiting.py`):
   - `manage_test`: mock API, verify `check_limit` called before `_set_test_state`
   - `manage_test`: mock API, verify `record_action` called after success
   - `manage_test`: mock API to raise exception, verify `record_action` NOT called

4. **E2E test** (`tests/test_rate_limiting_e2e.py`):
   - Set `SAFEBREACH_MCP_ACTION_LIMIT=2`, `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES=1`
   - Call `manage_test` 2 times successfully, 3rd call raises `ToolError`
   - Verify error message contains "total actions" and retry-after seconds

**Implementation (to pass the tests)**:

1. Create `safebreach_mcp_core/rate_limiter.py`:
   - `CallerRateLimitData` dataclass: `total_actions: List[float]`,
     `per_tool_actions: Dict[str, List[float]]`, `last_activity: float`
   - Module-level `_rate_limit_store: Dict[str, CallerRateLimitData]`
   - Configuration from env vars: `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` (default True),
     `SAFEBREACH_MCP_ACTION_LIMIT` (default 10),
     `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` (default 5),
     `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES` (default 30, convert to seconds)
   - `RateLimiter.check_limit(caller_id, tool_name)`:
     prune total_actions older than window, check `len(total_actions) >= ACTION_LIMIT`,
     compute `retry_after = window_seconds - (now - oldest_timestamp)`,
     raise `ToolError` with informative message. No increment.
   - `RateLimiter.record_action(caller_id, tool_name)`:
     append `time.time()` to `total_actions` and `per_tool_actions[tool_name]`,
     update `last_activity`, log with masked caller ID
   - `get_caller_identity()`: try `_get_session_id_from_mcp_ctx()`, fallback `'anonymous'`
     (minimal — auth token hash added in Phase 5)
   - Module-level `rate_limiter` singleton instance

2. Add gates to `manage_test` in `studio_server.py`:
   - `caller_id = get_caller_identity()` + `rate_limiter.check_limit(caller_id, "manage_test")`
     after input validation, before `_set_test_state()`
   - `rate_limiter.record_action(caller_id, "manage_test")` after `_set_test_state()` succeeds

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/rate_limiter.py` | Create | Rate limiter with total limit + session identity |
| `safebreach_mcp_studio/studio_server.py` | Modify | Add gates to manage_test |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Create | Core rate limiter + identity unit tests |
| `safebreach_mcp_studio/tests/test_rate_limiting.py` | Create | manage_test gate integration tests |
| `tests/test_rate_limiting_e2e.py` | Create | E2E: total action limit on manage_test |

**Git Commit**: `feat: rate limiter with total action limit on manage_test (TDD)`

---

### Phase 2: Per-Tool-Name Limit

**Semantic Change**: Add the second limit type — per-tool-name count — and verify it works
alongside the total action limit.

**Deliverables**: Per-tool-name enforcement in `check_limit`, tests for both limits interacting.

**Tests First (TDD)**:

1. **Unit tests** (add to `test_rate_limiter.py`):
   - `check_limit` raises `ToolError` when per-tool limit reached (5 identical actions)
   - Error message contains tool name, count/limit, and retry-after seconds
   - Per-tool limit enforced independently from total limit (can hit per-tool before total)
   - Multiple tool names tracked independently per caller
   - Custom `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT` env var is respected
   - Window boundary: per-tool timestamps pruned correctly

2. **E2E test** (add to `test_rate_limiting_e2e.py`):
   - Set `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT=1`, `SAFEBREACH_MCP_ACTION_LIMIT=10`
   - Call `manage_test` 1 time successfully, 2nd call raises `ToolError`
   - Verify error message contains "manage_test" (tool name) and retry-after seconds

**Implementation (to pass the tests)**:

1. Extend `RateLimiter.check_limit()`:
   - After total limit check, prune `per_tool_actions[tool_name]`
   - If `len(per_tool_actions[tool_name]) >= IDENTICAL_ACTION_LIMIT`:
     compute retry_after from oldest per-tool timestamp,
     raise `ToolError` with per-tool message

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/rate_limiter.py` | Modify | Add per-tool-name limit to check_limit |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Modify | Add per-tool limit tests |
| `tests/test_rate_limiting_e2e.py` | Modify | Add per-tool E2E test |

**Git Commit**: `feat: add per-tool-name rate limit (TDD)`

---

### Phase 3: Dry-Run Exclusion (`run_scenario`)

**Semantic Change**: Add gates to `run_scenario` with dry-run and diagnostic exclusion —
proving the most complex gate pattern.

**Deliverables**: `run_scenario` gates with dry-run awareness, tested E2E.

**Tests First (TDD)**:

1. **Gate integration tests** (add to `test_rate_limiting.py`):
   - `run_scenario` with `dry_run=False`: verify `check_limit` called before queue POST,
     `record_action` called after success
   - `run_scenario` with `dry_run=True`: verify neither `check_limit` nor `record_action` called
   - `run_scenario` with not_ready diagnostic: verify gates NOT called
   - `run_scenario` API failure: verify `record_action` NOT called

2. **E2E test** (add to `test_rate_limiting_e2e.py`):
   - Set `SAFEBREACH_MCP_IDENTICAL_ACTION_LIMIT=1`
   - Call `run_scenario` with `dry_run=True` multiple times — no rate limit triggered
   - Call `run_scenario` with `dry_run=False` once, second call triggers limit
   - Verify dry-run calls did not consume rate limit budget

**Implementation (to pass the tests)**:

1. Add gates to `run_scenario` in `studio_server.py`:
   - `check_limit` placed AFTER all early return branches (not_ready diagnostic return,
     dry_run prediction return, simulation count validation), immediately before the POST
     to `/api/orch/v4/accounts/{id}/queue`
   - `record_action` after the POST response is parsed and result with status='queued' is built
   - The key: gates only exist on the queue-submission code path, not on the diagnostic or
     dry-run branches

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_server.py` | Modify | Add gates to run_scenario |
| `safebreach_mcp_studio/tests/test_rate_limiting.py` | Modify | Add run_scenario gate tests |
| `tests/test_rate_limiting_e2e.py` | Modify | Add dry-run exclusion E2E test |

**Git Commit**: `feat: rate limit run_scenario with dry-run exclusion (TDD)`

---

### Phase 4: Remaining 4 Tools

**Semantic Change**: Add gates to the remaining 4 write tools, achieving full tool coverage.

**Deliverables**: All 6 write tools gated and tested.

**Tests First (TDD)**:

1. **Gate integration tests** (add to `test_rate_limiting.py`), for each tool:
   - `save_studio_attack_draft`: `check_limit` before POST, `record_action` after cache write,
     NOT called on validation failure
   - `update_studio_attack_draft`: `check_limit` before PUT, `record_action` after cache update,
     NOT called on validation failure
   - `run_studio_attack`: `check_limit` before queue POST, `record_action` after response parsed,
     NOT called on API error
   - `set_studio_attack_status`: `check_limit` AFTER pre-check GET (allow read first),
     before PUT. `record_action` after PUT + cache invalidate. NOT called on pre-check failure.

**Implementation (to pass the tests)**:

1. Add gates to `save_studio_attack_draft`:
   - `check_limit` after param validation (OS, dual-script), before POST to customMethods
   - `record_action` after POST response parsed, transformed, and cached

2. Add gates to `update_studio_attack_draft`:
   - `check_limit` after param validation, before PUT to customMethods
   - `record_action` after PUT response parsed and cache updated

3. Add gates to `run_studio_attack`:
   - `check_limit` after input validation (attack_id, simulators, filters), before queue POST
   - `record_action` after POST response parsed with planRunId/stepRunId

4. Add gates to `set_studio_attack_status`:
   - `check_limit` AFTER pre-check GET confirms attack exists and status validated,
     before PUT to customMethods
   - `record_action` after PUT succeeds and cache invalidated

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_server.py` | Modify | Add gates to 4 remaining write tools |
| `safebreach_mcp_studio/tests/test_rate_limiting.py` | Modify | Add gate tests for 4 tools |

**Git Commit**: `feat: rate limit all remaining write tools (TDD)`

---

### Phase 5: Hybrid Caller Identity

**Semantic Change**: Upgrade caller identity from session-only to hybrid
(auth token hash for external, session fallback for localhost).

**Deliverables**: Production-ready `get_caller_identity()` with auth token support.

**Tests First (TDD)**:

1. **Unit tests** (add to `test_rate_limiter.py`):
   - Mock `_user_auth_artifacts` with `x-apitoken` → returns SHA256 hash (first 16 chars)
   - Mock `_get_auth_from_mcp_request_ctx()` as fallback → returns hash
   - Priority: x-apitoken > x-token > cookie value
   - Same token always produces same hash (stability)
   - Auth token identity survives across session reconnection (same hash)
   - Empty auth bundle with session ID → returns session ID
   - No auth, no session → returns `'anonymous'`

2. **E2E test** (add to `test_rate_limiting_e2e.py`):
   - Verify rate limits are enforced correctly when auth token is present
     (external connection scenario)

**Implementation (to pass the tests)**:

1. Upgrade `get_caller_identity()` in `rate_limiter.py`:
   - Try `_user_auth_artifacts` ContextVar first
   - Fallback to `_get_auth_from_mcp_request_ctx()`
   - If auth artifacts found, hash the most stable value
     (priority: x-apitoken > x-token > cookie), return `SHA256[:16]`
   - If no auth, fall back to `_get_session_id_from_mcp_ctx()`
   - Final fallback: `'anonymous'`
   - Debug logging for which identity source was used

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/rate_limiter.py` | Modify | Upgrade get_caller_identity() with auth token hash |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Modify | Add hybrid identity tests |
| `tests/test_rate_limiting_e2e.py` | Modify | Add auth-token identity E2E test |

**Git Commit**: `feat: hybrid caller identity for rate limiting (TDD)`

---

### Phase 6: Cleanup + Server Lifecycle

**Semantic Change**: Add stale entry cleanup and integrate rate limiter into the server
lifecycle, preventing unbounded memory growth.

**Deliverables**: Cleanup task, server integration, disable/enable E2E, window expiry E2E.

**Tests First (TDD)**:

1. **Unit tests** (add to `test_rate_limiter.py`):
   - Record actions, advance time past TTL (1 hour), run cleanup, verify entries removed
   - Record recent actions, run cleanup, verify entries preserved
   - Multiple callers: only stale ones removed, active ones kept
   - Cleanup singleton: calling `start_rate_limit_cleanup()` twice only starts one task

2. **E2E tests** (add to `test_rate_limiting_e2e.py`):
   - Set `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=false`: verify tools execute without
     rate limit interference regardless of call count
   - Set `SAFEBREACH_MCP_RATE_LIMIT_WINDOW_MINUTES=1`: trigger limit, wait 60+ seconds,
     verify tool succeeds again (window expiry)

**Implementation (to pass the tests)**:

1. Add `_cleanup_stale_rate_limits()` async function to `rate_limiter.py`:
   - Infinite loop with `await asyncio.sleep(600)` (every 10 minutes)
   - Find entries with `last_activity` older than 3600 seconds, remove them
   - Log eviction count, wrap in try/except

2. Add `start_rate_limit_cleanup()` singleton async function:
   - Module-level `_cleanup_started: bool = False` flag
   - First call creates the task, subsequent calls are no-ops

3. In `safebreach_base.py` `run_server()`:
   - Import and start cleanup task alongside existing tasks
   - Cancel in `finally` block

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/rate_limiter.py` | Modify | Add cleanup task + singleton starter |
| `safebreach_mcp_core/safebreach_base.py` | Modify | Start cleanup task in run_server() |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Modify | Add cleanup + lifecycle tests |
| `tests/test_rate_limiting_e2e.py` | Modify | Add disable switch + window expiry E2E |

**Git Commit**: `feat: rate limit cleanup task and server lifecycle (TDD)`

---

### Phase 7: Documentation

**Semantic Change**: Document the rate limiting pattern in CLAUDE.md for future write tools.

**Deliverables**: Updated CLAUDE.md with rate limiting design pattern.

**Implementation Details**:

1. Add a "Rate Limiting" subsection under "Key Design Patterns" in `CLAUDE.md`
2. Document:
   - Two-phase gate pattern: `check_limit` (pre-check) + `record_action` (post-success)
   - Gate placement rules (5 rules from investigation)
   - Configuration environment variables and their defaults
   - The `get_caller_identity()` helper and hybrid identity approach
   - The gate placement table for existing 6 tools as reference
   - Instruction: any new tool with `readOnlyHint=False` MUST add rate limiting gates
3. Add `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` to the environment variable documentation section
4. Update the "MCP Tools Available" section to note which tools are rate-limited

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Add rate limiting pattern documentation |

**Git Commit**: `docs: add rate limiting pattern to CLAUDE.md`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `get_caller_identity()` returns empty/anonymous for legitimate callers | Medium — all anonymous callers share one bucket | Log warnings when anonymous identity used; monitor in production |
| Sliding window pruning on every check adds latency | Low — max 10 entries per caller, O(10) is negligible | Benchmark if concerns arise |
| Module-level dict not persisted across server restarts | Low — rate limits reset on restart (acceptable for safety guardrail) | Documented as expected behavior |

### Assumptions

- All 5 MCP servers will continue to run in the same process (cross-server sharing depends on this)
- `time.time()` provides sufficient precision for sliding window (float seconds)
- The existing `_get_auth_from_mcp_request_ctx()` and `_get_session_id_from_mcp_ctx()` functions
  are accessible from within tool handlers (verified during investigation)
- `create_new_studio_attack` is genuinely read-only (confirmed: returns static boilerplate)

---

## 11. Future Enhancements

- **Bulk action rate limiting**: The original ticket mentions future bulk action APIs that should
  also be capped. When bulk endpoints are added, apply similar per-tool gate placement.
- **Persistent rate limit state**: If servers move to multi-process deployment, rate limit state
  would need Redis or similar shared storage.
- **Per-console rate limiting**: Currently rate limits are per-caller across all consoles.
  Could be refined to per-caller-per-console if needed.
- **Configurable per-tool limits**: Allow different limits for different tools
  (e.g., `run_scenario` might have a tighter limit than `save_studio_attack_draft`).
- **Rate limit metrics endpoint**: Expose current rate limit state via a monitoring endpoint.

---

## 12. Executive Summary

- **Issue/Feature Description**: MCP servers have no rate limiting on write operations, allowing
  unlimited repetitive actions by a single client.
- **What Will Be Built**: A two-phase rate limiter (`check_limit` + `record_action`) integrated
  into 6 Studio server write tools, with hybrid caller identity and cross-server shared state.
- **Key Technical Decisions**: Explicit per-tool gate placement over decorator-based approach;
  ToolError (MCP-level) over HTTP 429; auth token hash identity with session fallback;
  module-level dict for cross-server sharing (same process).
- **Scope**: 6 write tools in Studio server, new `rate_limiter.py` module, CLAUDE.md documentation.
  Future bulk action APIs are out of scope.
- **Business Value**: Safety guardrail preventing abuse of MCP write operations, enabling
  detection of suspicious activity patterns, configurable per deployment.

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-11 09:15 | PRD created — initial draft |
| 2026-05-11 09:45 | Revised: informative error messages with limit type + retry-after; added E2E testing |
| 2026-05-11 10:15 | Restructured to elephant carpaccio TDD slices: 7 thin vertical phases, each with tests-first |
| 2026-05-11 11:00 | Phase 1 complete: rate_limiter.py + manage_test gates + 17 tests (14 unit + 3 gate) |
