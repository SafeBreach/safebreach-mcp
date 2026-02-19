# PRD: Fix Cache Memory Leak — SAF-28428

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Fix Cache Memory Leak — SAF-28428 |
| **Task Type** | Bug fix + refactor |
| **Purpose** | Eliminate unbounded memory growth in MCP server caching that crashes host machines |
| **Target Consumer** | Internal — AI Tools team, DevOps |
| **Key Benefits** | 1) Stable memory under extended operation 2) Per-server cache control 3) Operational visibility |
| **Business Alignment** | Restore caching capability (currently disabled) to accelerate AI agent workflows |
| **Originating Request** | [SAF-28428](https://safebreach.atlassian.net/browse/SAF-28428) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-02-19 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution: `cachetools.TTLCache` with Thread-Safe Wrapper

Replace all 8 global unbounded `dict` caches with `cachetools.TTLCache` instances wrapped in a
thread-safe `SafeBreachCache` class. Each cache gets per-type `maxsize` (LRU eviction) and `ttl`.
Add per-server cache enable/disable env vars, fix orphaned SSE session semaphore leak, and add
periodic cache stats monitoring.

### Alternatives Considered

**A: Custom `BoundedTTLCache` class**
- Pros: Full control, no external dependency, FIFO eviction
- Cons: Custom code to maintain, reinventing the wheel, more bugs likely

**B: Decorator pattern (`@cached`)**
- Pros: Clean API, each function declares its cache policy
- Cons: Poor fit for Studio cache (set in `save_draft`, read in `get_draft` — different functions),
  harder to inspect/clear caches externally

### Decision Rationale

`cachetools` is battle-tested (50M+ monthly downloads), provides built-in LRU eviction and TTL
expiration, and requires minimal custom code. LRU is superior to FIFO for cache hit rate. The thin
wrapper adds thread safety and monitoring without reinventing core cache logic.

## 3. Core Feature Components

### Component A: SafeBreachCache Wrapper

**Purpose**: New reusable thread-safe cache class in `safebreach_mcp_core/`.

**Key Features**:
- Wraps `cachetools.TTLCache` with `threading.Lock` for multi-agent thread safety
- Configurable `maxsize` and `ttl` per instance
- Built-in stats tracking (hits, misses, evictions)
- `stats()` method for monitoring
- `clear()` method for manual cache invalidation
- Standard dict-like `get`/`set`/`delete` API matching existing cache usage patterns

### Component B: Per-Server Cache Configuration

**Purpose**: Extend `cache_config.py` to support per-server cache enable/disable.

**Key Features**:
- Per-server env vars: `SB_MCP_CACHE_CONFIG`, `SB_MCP_CACHE_DATA`,
  `SB_MCP_CACHE_PLAYBOOK`, `SB_MCP_CACHE_STUDIO`
- `SB_MCP_ENABLE_LOCAL_CACHING` remains as global override (enables all)
- `is_caching_enabled(server_name)` function signature — backward compatible
  (calling without arg still checks global toggle)
- Startup logging showing which servers have caching enabled

### Component C: Cache Migration (All Servers)

**Purpose**: Replace 8 global `dict` caches with `SafeBreachCache` instances.

**Key Features**:
- Per-type `maxsize` and `ttl` based on cardinality analysis:

| Cache | maxsize | TTL | Cardinality |
|-------|---------|-----|-------------|
| `simulators_cache` | 5 | 3600s (1h) | Tier 1: console only |
| `tests_cache` | 5 | 1800s (30m) | Tier 1: console only |
| `simulations_cache` | 3 | 600s (10m) | Tier 2: console×test |
| `security_control_events_cache` | 3 | 600s (10m) | Tier 3: console×test×sim |
| `findings_cache` | 3 | 600s (10m) | Tier 2: console×test |
| `full_simulation_logs_cache` | 2 | 300s (5m) | Tier 3: console×test×sim, ~40KB/entry |
| `playbook_cache` | 5 | 1800s (30m) | Tier 1: console only, 60MB singleton |
| `studio_draft_cache` | 5 | 1800s (30m) | Tier 2: console×draft |

- Remove manual TTL checking code (cachetools handles expiration internally)
- Remove manual `(data, timestamp)` tuple wrapping — TTLCache manages timestamps
- Simplify `_get_all_*_from_cache_or_api` functions

### Component D: SSE Session Semaphore Cleanup

**Purpose**: Fix memory leak in `_session_semaphores` dict for orphaned SSE connections.

**Key Features**:
- Add timestamp tracking alongside each semaphore entry
- Periodic asyncio task (every 5 minutes) sweeps entries older than 1 hour
- Logs cleanup actions for observability

### Component E: Cache Monitoring

**Purpose**: Periodic logging of cache health metrics.

**Key Features**:
- Background task logs cache stats every 5 minutes
- Stats per cache: current size / max size, hit rate, miss rate
- Warning log when any cache consistently runs at capacity (potential maxsize tuning signal)

## 6. Non-Functional Requirements

### Performance Requirements
- Cache `get` operations must remain O(1) — `TTLCache` provides this
- Lock contention should be negligible (locks held only during dict operations, microseconds)
- Memory usage must remain bounded: worst case = sum of all maxsize × avg entry size
  - Estimated max: ~5×1MB + 5×500KB + 3×2MB + 3×100KB + 3×500KB + 2×40KB + 5×60MB + 5×50KB ≈ 315MB
  - Playbook cache dominates — 60MB singleton per console is the heaviest item

### Technical Constraints
- `cachetools>=5.3.0` — new dependency, pure Python, no C extensions
- Must maintain backward compatibility with `SB_MCP_ENABLE_LOCAL_CACHING` env var
- Thread safety required (multi-agent shared process model)
- Python 3.12+ required (already a project requirement)

### Monitoring & Observability
- Cache stats logged at INFO level every 5 minutes
- WARNING level when cache runs at capacity for 3+ consecutive intervals
- SSE semaphore cleanup logged at DEBUG level

## 7. Definition of Done

- [ ] `cachetools>=5.3.0` added to `pyproject.toml` dependencies
- [ ] `SafeBreachCache` wrapper class created with thread-safe LRU+TTL eviction
- [ ] All 8 global dict caches replaced with `SafeBreachCache` instances
- [ ] Each cache has per-type `maxsize` and `ttl` configuration
- [ ] LRU eviction prevents unbounded memory growth
- [ ] Per-server cache enable/disable via `SB_MCP_CACHE_*` env vars
- [ ] `SB_MCP_ENABLE_LOCAL_CACHING` still works as global toggle
- [ ] `SafeBreachMCPBase._cache` migrated to use `SafeBreachCache`
- [ ] Orphaned SSE `_session_semaphores` cleaned up periodically
- [ ] Cache stats logged periodically for monitoring
- [ ] All existing unit tests pass (updated for new cache API)
- [ ] New unit tests for: cache wrapper, LRU eviction, TTL expiration, per-server toggles
- [ ] Cross-server test suite passes
- [ ] Memory usage remains stable during extended operation

## 8. Testing Strategy

### Unit Testing

**Scope**: `SafeBreachCache` wrapper, `cache_config.py` per-server toggles, each server's
cache migration.

**Key Scenarios**:
- `SafeBreachCache`: get/set, TTL expiration, LRU eviction at maxsize, thread safety
  under concurrent access, stats tracking accuracy, clear behavior
- `cache_config.py`: per-server env vars, global toggle override, backward compatibility
  (no arg = global check), reset behavior for tests
- Each server: cache hit returns data, cache miss fetches from API, expired entry triggers
  API fetch, evicted entry triggers API fetch, caching disabled skips cache entirely

**Framework**: pytest + pytest-mock (existing)
**Coverage Target**: Maintain existing coverage baseline

### Integration Testing

**Scope**: Cross-server cache behavior, SSE semaphore cleanup.

**Key Scenarios**:
- Multiple servers running with mixed cache enable/disable settings
- SSE semaphore cleanup removes stale entries while preserving active ones
- Cache monitoring logs correct stats across all servers

### E2E Testing

**Scope**: End-to-end with real SafeBreach environments (existing E2E framework).

**Key Scenarios**:
- Verify cached responses match fresh API responses
- Verify cache eviction doesn't cause data corruption

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 0: Quality & Memory Baseline | ⏳ Pending | - | - | |
| Phase 1: Foundation | ⏳ Pending | - | - | |
| Phase 2: Per-Server Cache Config | ⏳ Pending | - | - | |
| Phase 3: Config Server Migration | ⏳ Pending | - | - | |
| Phase 4: Data Server Migration | ⏳ Pending | - | - | |
| Phase 5: Playbook Server Migration | ⏳ Pending | - | - | |
| Phase 6: Studio Server Migration | ⏳ Pending | - | - | |
| Phase 7: Base Server + SSE Fix | ⏳ Pending | - | - | |
| Phase 8: Cache Monitoring | ⏳ Pending | - | - | |
| Phase 9: Memory Stress Tests | ⏳ Pending | - | - | |
| Phase 10: Documentation + Cleanup | ⏳ Pending | - | - | |

---

### Phase 0: Quality & Memory Baseline

**Semantic Change**: Capture baseline metrics before any code changes — test suite results and
memory consumption of MCP servers with and without caching.

**Deliverables**:
- Baseline test suite results captured and committed
- Memory profiling harness created
- Baseline memory measurements captured (caching disabled vs enabled with current buggy code)
- External process metrics collection script

**Implementation Details**:

**0a. Test Suite Baseline:**
- Run full cross-server test suite, capture results to `prds/SAF-28428/baseline-tests.txt`
- Record: total tests, passed, failed, skipped, duration
- Command: `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/
  safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/
  -v -m "not e2e" | tee prds/SAF-28428/baseline-tests.txt`

**0b. Memory Profiling Harness:**
Create `tests/memory_profile_baseline.py` — a standalone script that:
1. Starts MCP servers in-process (or via subprocess)
2. Simulates agent-like cache operations: queries across multiple consoles, tests, simulations
3. Measures memory using **external observation**, not just internal logs:
   - `psutil.Process().memory_info().rss` — Resident Set Size (actual RAM used by OS)
   - `psutil.Process().memory_info().vms` — Virtual Memory Size
   - `tracemalloc` snapshots — Python-level heap allocation tracking
   - `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` — Peak RSS from OS
4. Runs two scenarios:
   - **Scenario A: Caching disabled** (`SB_MCP_ENABLE_LOCAL_CACHING=false`)
     - Simulate 100 agent queries (mix of tests, simulations, playbook)
     - Record RSS at start, during, and after queries
   - **Scenario B: Caching enabled (current buggy code)** (`SB_MCP_ENABLE_LOCAL_CACHING=true`)
     - Same 100 agent queries
     - Record RSS at start, during, and after queries
     - This captures the unbounded growth pattern we're fixing
5. Outputs structured results to `prds/SAF-28428/baseline-memory.json`:
   ```
   {
     "timestamp": "2026-02-19T...",
     "scenarios": {
       "caching_disabled": {
         "rss_start_mb": X, "rss_peak_mb": X, "rss_end_mb": X,
         "tracemalloc_peak_mb": X
       },
       "caching_enabled_buggy": {
         "rss_start_mb": X, "rss_peak_mb": X, "rss_end_mb": X,
         "tracemalloc_peak_mb": X, "cache_entry_count": X
       }
     }
   }
   ```

**0c. External Process Monitoring Script:**
Create `tests/monitor_process_memory.py` — a lightweight script that:
1. Takes a PID or starts a subprocess
2. Polls RSS/VMS every 1 second for a configurable duration
3. Outputs time-series CSV: `timestamp,rss_mb,vms_mb,cpu_percent`
4. Can be used during E2E testing or manual testing to observe real MCP server behavior
5. Generates a summary: min, max, mean, p95, growth rate (MB/minute)

This script runs **outside** the MCP process, providing independent observation that can't be
affected by bugs in the caching code itself.

**0d. Acceptance Thresholds:**
Define acceptable memory bounds for post-implementation comparison:
- **Caching disabled**: RSS growth during 100 queries should be < 10MB (no caching overhead)
- **Caching enabled (after fix)**: RSS growth during 100 queries should be < 50MB
  (bounded by sum of all maxsize × estimated entry sizes)
- **Peak RSS**: Should never exceed baseline + 100MB under any test scenario
- **Growth rate**: Should plateau (not grow linearly) — measure as slope over last 50% of queries

These thresholds will be validated in Phase 9 (Memory Stress Tests) after the fix.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `psutil>=5.9.0` to dev dependencies |
| `tests/memory_profile_baseline.py` | Create | Memory profiling harness |
| `tests/monitor_process_memory.py` | Create | External process memory monitor |
| `prds/SAF-28428/baseline-tests.txt` | Create | Test suite baseline results |
| `prds/SAF-28428/baseline-memory.json` | Create | Memory baseline measurements |

**Test Plan**:
- Profiling harness runs without errors
- Baseline test results captured (record pass/fail counts)
- Memory measurements captured for both scenarios
- External monitor produces valid CSV output

**Git Commit**: `test: capture quality and memory baseline before cache fix (SAF-28428)`

---

### Phase 1: Foundation — Add `cachetools` dependency and `SafeBreachCache` wrapper

**Semantic Change**: Create the reusable thread-safe cache class that all servers will use.

**Deliverables**:
- `cachetools` added to project dependencies
- `SafeBreachCache` class in `safebreach_mcp_core/`
- Full unit test coverage for the wrapper

**Implementation Details**:

`SafeBreachCache` class in `safebreach_mcp_core/safebreach_cache.py`:
- Constructor accepts `name` (str), `maxsize` (int), `ttl` (int seconds)
- Internally creates a `cachetools.TTLCache(maxsize=maxsize, ttl=ttl)` and a `threading.Lock`
- `get(key)` method: acquires lock, returns value if present (TTLCache handles expiration),
  increments hit/miss counter, returns `None` on miss
- `set(key, value)` method: acquires lock, sets value in TTLCache (LRU eviction happens
  automatically when maxsize exceeded), increments set counter
- `delete(key)` method: acquires lock, removes key if present, returns bool indicating
  whether key existed
- `clear()` method: acquires lock, clears all entries
- `stats()` method: returns dict with `name`, `size` (current entries), `maxsize`, `ttl`,
  `hits`, `misses`, `hit_rate` (percentage)
- `__contains__(key)` method: acquires lock, checks if key exists and is not expired
- `__len__()` method: acquires lock, returns current entry count

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `cachetools>=5.3.0` to dependencies |
| `safebreach_mcp_core/safebreach_cache.py` | Create | `SafeBreachCache` wrapper class |
| `safebreach_mcp_core/__init__.py` | Modify | Export `SafeBreachCache` if needed |
| `safebreach_mcp_core/tests/test_safebreach_cache.py` | Create | Unit tests for wrapper |

**Test Plan**:

*Functional tests:*
- Test get/set basic operations (set value, get same key returns value, get unknown key returns None)
- Test TTL expiration (set item, advance time past TTL via `time.sleep` mock, verify get returns None)
- Test LRU eviction (fill to maxsize, add one more, verify least-recently-used key is evicted)
- Test LRU access order (access oldest key before adding new one, verify a different key is evicted)
- Test stats accuracy (hit/miss/set counters after known sequence of operations)
- Test clear empties cache and resets stats
- Test delete removes specific key, returns True; delete missing key returns False
- Test `__contains__` returns True for present keys, False for expired/missing
- Test `__len__` reflects current live entries (not expired ones)

*Memory safety tests:*
- Test LRU eviction frees memory: use `weakref.ref()` on cached value, evict it, call `gc.collect()`,
  verify weakref is dead (value was garbage collected)
- Test TTL expiration frees memory: same weakref approach — set item, advance time past TTL,
  trigger cache access to expire it, verify weakref is dead after `gc.collect()`
- Test clear releases all references: populate cache, take weakrefs to all values, call `clear()`,
  `gc.collect()`, verify all weakrefs are dead
- Test delete releases reference: set item, take weakref, `delete(key)`, `gc.collect()`,
  verify weakref is dead
- Test rapid set cycles stay bounded: loop 10,000 `set()` calls on `maxsize=3` cache with unique
  keys, assert `len(cache) <= maxsize` after every 100 iterations
- Test large value eviction: set 1MB string values, evict them, use `tracemalloc` to verify
  memory delta returns near baseline

*Thread safety tests:*
- Test concurrent get/set: 10 threads doing random get/set for 1 second on `maxsize=5` cache,
  verify no exceptions, no deadlocks (use `threading.Timer` as timeout), `len() <= maxsize`
- Test concurrent set with eviction: 10 threads each setting 100 unique keys on `maxsize=3`,
  verify cache size never exceeds maxsize

**Git Commit**: `feat(core): add SafeBreachCache wrapper with LRU eviction and TTL (SAF-28428)`

---

### Phase 2: Per-Server Cache Configuration

**Semantic Change**: Extend `cache_config.py` to support per-server cache toggles.

**Deliverables**:
- `is_caching_enabled()` accepts optional `server_name` parameter
- Per-server env vars documented and functional
- Backward compatible — no args = global check

**Implementation Details**:

Modify `is_caching_enabled()` in `cache_config.py`:
- Add optional `server_name` parameter (default `None`)
- When `server_name` is `None`: check `SB_MCP_ENABLE_LOCAL_CACHING` (existing behavior)
- When `server_name` is provided (e.g., `"config"`, `"data"`, `"playbook"`, `"studio"`):
  1. First check server-specific var `SB_MCP_CACHE_{SERVER_NAME}` (uppercase)
  2. If not set, fall back to global `SB_MCP_ENABLE_LOCAL_CACHING`
  3. Server-specific var overrides global (so you can enable globally but disable one server)
- Cache the resolved value per server_name to avoid repeated env lookups
- Add `reset_cache_config()` update to clear per-server cached values too

Server name to env var mapping:
- `"config"` → `SB_MCP_CACHE_CONFIG`
- `"data"` → `SB_MCP_CACHE_DATA`
- `"playbook"` → `SB_MCP_CACHE_PLAYBOOK`
- `"studio"` → `SB_MCP_CACHE_STUDIO`

Startup logging: when caching is enabled, log which servers have caching active.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/cache_config.py` | Modify | Add per-server toggle logic |
| `safebreach_mcp_core/tests/test_cache_config.py` | Create/Modify | Tests for per-server toggles |

**Test Plan**:

*Toggle logic tests:*
- Test global toggle on → all servers enabled (check each server name)
- Test global toggle off → all servers disabled (check each server name)
- Test server-specific on with global off → only that server enabled, others disabled
- Test server-specific off with global on → that server disabled, others still enabled
- Test both global and server-specific set → server-specific takes precedence
- Test backward compatibility: `is_caching_enabled()` (no args) still checks global only
- Test unknown server name falls back to global toggle
- Test `reset_cache_config()` clears all per-server cached state
- Test env var values: "true", "1", "yes", "on" are truthy; "false", "0", "", unset are falsy
- Test case insensitivity: "TRUE", "True", "true" all work

*Integration tests:*
- Test startup logging outputs correct per-server cache status summary
- Test that each server's `*_functions.py` passes its server name correctly

**Git Commit**: `feat(core): add per-server cache enable/disable toggles (SAF-28428)`

---

### Phase 3: Config Server Migration

**Semantic Change**: Replace `simulators_cache` dict with `SafeBreachCache` instance.

**Deliverables**:
- `simulators_cache` uses `SafeBreachCache(name="simulators", maxsize=5, ttl=3600)`
- `_get_all_simulators_from_cache_or_api()` simplified
- `is_caching_enabled(server_name="config")` used for cache checks

**Implementation Details**:

In `config_functions.py`:
- Replace `simulators_cache = {}` with
  `simulators_cache = SafeBreachCache(name="simulators", maxsize=5, ttl=3600)`
- Remove `CACHE_TTL = 3600` constant (TTL now in cache instance)
- In `_get_all_simulators_from_cache_or_api()`:
  - Replace manual TTL check with `simulators_cache.get(cache_key)`
  - Replace manual `simulators_cache[cache_key] = (simulators, current_time)` with
    `simulators_cache.set(cache_key, simulators)` (no timestamp tuple needed)
  - Replace `is_caching_enabled()` with `is_caching_enabled("config")`
  - Remove manual timestamp comparison logic

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/config_functions.py` | Modify | Replace dict cache with SafeBreachCache |
| `safebreach_mcp_config/tests/test_config_functions.py` | Modify | Update cache assertions |

**Test Plan**:

*Functional tests:*
- Test cache hit returns cached simulators without API call (mock API, verify not called on 2nd request)
- Test cache miss fetches from API and stores result via `cache.set()`
- Test expired cache triggers fresh API call (advance time past TTL)
- Test caching disabled (`SB_MCP_CACHE_CONFIG=false`): verify `cache.set()` never called,
  every request hits API
- Test caching disabled globally: verify same behavior as server-specific disable
- Test `is_caching_enabled("config")` is called (not bare `is_caching_enabled()`)

*Memory safety tests:*
- Test no tuple/timestamp wrapper: verify `cache.set()` receives raw simulator list,
  not `(data, timestamp)` tuple
- Test cache size stays bounded: simulate 10 different consoles being queried on `maxsize=5`,
  verify cache never exceeds 5 entries

*Regression tests:*
- All existing `test_config_functions.py` tests pass with updated assertions

**Git Commit**: `refactor(config): migrate simulators_cache to SafeBreachCache (SAF-28428)`

---

### Phase 4: Data Server Migration

**Semantic Change**: Replace all 5 Data server dict caches with `SafeBreachCache` instances.

**Deliverables**:
- `tests_cache` → `SafeBreachCache(name="tests", maxsize=5, ttl=1800)`
- `simulations_cache` → `SafeBreachCache(name="simulations", maxsize=3, ttl=600)`
- `security_control_events_cache` → `SafeBreachCache(name="security_control_events", maxsize=3, ttl=600)`
- `findings_cache` → `SafeBreachCache(name="findings", maxsize=3, ttl=600)`
- `full_simulation_logs_cache` → `SafeBreachCache(name="full_simulation_logs", maxsize=2, ttl=300)`
- All `_get_all_*_from_cache_or_api()` functions simplified
- `is_caching_enabled("data")` used for all cache checks

**Implementation Details**:

In `data_functions.py`:
- Replace all 5 global dict declarations with `SafeBreachCache` instances
- Remove `CACHE_TTL = 3600` constant
- For each `_get_all_*_from_cache_or_api()` function:
  - Replace manual cache check + TTL comparison with `.get(cache_key)`
  - Replace manual cache set with timestamp tuple/dict with `.set(cache_key, data)`
  - Replace `is_caching_enabled()` with `is_caching_enabled("data")`

Note: Two different cache value patterns exist in current code:
1. Tuple pattern: `cache[key] = (data, timestamp)` — used by tests, simulations, full_sim_logs
2. Dict pattern: `cache[key] = {'data': data, 'timestamp': timestamp}` — used by sec_ctrl_events,
   findings

Both patterns get simplified to `cache.set(key, data)` — the wrapper handles timestamps internally.
The `get()` return value will be the raw data (not a tuple or dict wrapper).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_data/data_functions.py` | Modify | Replace 5 dict caches with SafeBreachCache |
| `safebreach_mcp_data/tests/test_data_functions.py` | Modify | Update cache assertions for all 5 caches |

**Test Plan**:

*Per-cache functional tests (for each of the 5 caches):*
- Test cache hit returns cached data without API call
- Test cache miss fetches from API and stores via `cache.set()`
- Test expired cache triggers fresh API call
- Test caching disabled (`SB_MCP_CACHE_DATA=false`): API called every time, `cache.set()` never called
- Test `is_caching_enabled("data")` is called (not bare `is_caching_enabled()`)

*Memory safety tests (critical for Tier 3 caches):*
- Test no tuple wrapper leakage: verify `cache.set()` receives raw data, not `(data, timestamp)`
- Test no dict wrapper leakage: verify `cache.set()` receives raw data, not `{'data': ..., 'timestamp': ...}`
- **Pagination storm test** (`simulations_cache`): mock agent querying 100 different test_ids
  in sequence on `maxsize=3`, verify only 3 entries exist after all queries
- **Multiplicative key test** (`security_control_events_cache`): simulate 5 consoles × 5 tests × 5
  simulations = 125 unique keys on `maxsize=3`, verify cache never exceeds 3 entries
- **Large payload test** (`full_simulation_logs_cache`): mock 40KB log payloads, set 10 entries
  on `maxsize=2`, verify only 2 entries retained, use weakref to confirm evicted payloads are GC'd
- **Cross-test cache isolation**: query sims for test A → test B → test C → test A again,
  verify test A triggers fresh API call (was evicted by LRU)

*TTL/maxsize configuration tests:*
- Verify `tests_cache.ttl == 1800` and `tests_cache.maxsize == 5`
- Verify `simulations_cache.ttl == 600` and `simulations_cache.maxsize == 3`
- Verify `security_control_events_cache.ttl == 600` and `maxsize == 3`
- Verify `findings_cache.ttl == 600` and `maxsize == 3`
- Verify `full_simulation_logs_cache.ttl == 300` and `maxsize == 2`

*Regression tests:*
- All existing `test_data_functions.py` tests pass with updated assertions

**Git Commit**: `refactor(data): migrate 5 data caches to SafeBreachCache (SAF-28428)`

---

### Phase 5: Playbook Server Migration

**Semantic Change**: Replace `playbook_cache` dict with `SafeBreachCache` instance.

**Deliverables**:
- `playbook_cache` → `SafeBreachCache(name="playbook_attacks", maxsize=5, ttl=1800)`
- `_get_all_attacks_from_cache_or_api()` simplified
- `is_caching_enabled("playbook")` used for cache checks

**Implementation Details**:

In `playbook_functions.py`:
- Replace `playbook_cache = {}` with
  `playbook_cache = SafeBreachCache(name="playbook_attacks", maxsize=5, ttl=1800)`
- Remove `CACHE_TTL = 3600` constant
- In `_get_all_attacks_from_cache_or_api()`:
  - Replace manual dict pattern `playbook_cache[cache_key]['timestamp']` check with `.get(cache_key)`
  - Replace `playbook_cache[cache_key] = {'data': ..., 'timestamp': ...}` with
    `.set(cache_key, attacks_data)`
  - Replace `is_caching_enabled()` with `is_caching_enabled("playbook")`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_playbook/playbook_functions.py` | Modify | Replace dict cache with SafeBreachCache |
| `safebreach_mcp_playbook/tests/test_playbook_functions.py` | Modify | Update cache assertions |

**Test Plan**:

*Functional tests:*
- Test cache hit returns cached playbook attacks without API call
- Test cache miss fetches from API and stores via `cache.set()`
- Test expired cache triggers fresh API call
- Test caching disabled (`SB_MCP_CACHE_PLAYBOOK=false`): API called every time
- Test `is_caching_enabled("playbook")` is called

*Memory safety tests:*
- Test no dict wrapper leakage: verify `cache.set()` receives `attacks_data` directly,
  not `{'data': attacks_data, 'timestamp': ...}`
- Test large payload handling: playbook can be ~60MB — verify LRU eviction works correctly
  with large payloads (mock with 1MB placeholder)
- Test multiple consoles on `maxsize=5`: simulate 8 consoles, verify only 5 entries retained

*Regression tests:*
- All existing `test_playbook_functions.py` tests pass with updated assertions

**Git Commit**: `refactor(playbook): migrate playbook_cache to SafeBreachCache (SAF-28428)`

---

### Phase 6: Studio Server Migration

**Semantic Change**: Replace `studio_draft_cache` dict with `SafeBreachCache` instance.

**Deliverables**:
- `studio_draft_cache` → `SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)`
- Cache set/get/delete operations updated across save, update, get, and publish functions
- `is_caching_enabled("studio")` used for cache checks

**Implementation Details**:

In `studio_functions.py`:
- Replace `studio_draft_cache = {}` with
  `studio_draft_cache = SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)`
- Remove `CACHE_TTL` constant if defined locally

Studio has a more complex cache usage pattern than other servers:
- **Save draft** (line ~699): `studio_draft_cache.set(cache_key, result)` — stores after API save
- **Update draft** (line ~956): `studio_draft_cache.set(cache_key, result)` — updates after API update
- **Get draft** (`_get_draft_from_cache`, line ~1419): `studio_draft_cache.get(cache_key)` — reads
- **Publish/delete** (line ~1629): `studio_draft_cache.delete(cache_key)` — invalidates on status change

Update each location:
- Replace `studio_draft_cache[cache_key] = {'data': result, 'timestamp': time.time()}`
  with `studio_draft_cache.set(cache_key, result)`
- Replace `_get_draft_from_cache()` internals: use `.get(cache_key)` instead of manual TTL check
- Replace `del studio_draft_cache[cache_key]` with `studio_draft_cache.delete(cache_key)`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_functions.py` | Modify | Replace dict cache with SafeBreachCache |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Modify | Update cache assertions |

**Test Plan**:

*Functional tests:*
- Test save draft populates cache via `cache.set()` (not dict assignment)
- Test update draft overwrites existing cache entry
- Test get draft retrieves from cache via `cache.get()`
- Test get draft on expired entry returns None, does not return stale data
- Test publish invalidates cache entry via `cache.delete()`
- Test delete draft invalidates cache entry via `cache.delete()`
- Test caching disabled (`SB_MCP_CACHE_STUDIO=false`): no cache operations occur

*Memory safety tests:*
- Test no dict wrapper leakage: verify `cache.set()` receives `result` directly,
  not `{'data': result, 'timestamp': ...}`
- Test save→delete→GC cycle: save draft, take weakref to cached value, delete it,
  `gc.collect()`, verify weakref is dead
- Test multiple drafts on `maxsize=5`: save 8 different drafts, verify only 5 retained
- Test publish clears cache reference: after publish, the draft's data should not be
  held by the cache

*Regression tests:*
- All existing `test_studio_functions.py` tests pass with updated assertions

**Git Commit**: `refactor(studio): migrate studio_draft_cache to SafeBreachCache (SAF-28428)`

---

### Phase 7: Base Server Migration + SSE Semaphore Fix

**Semantic Change**: Migrate `SafeBreachMCPBase._cache` and fix `_session_semaphores` leak.

**Deliverables**:
- `self._cache` and `self._cache_timestamps` replaced with single `SafeBreachCache` instance
- `get_from_cache()` and `set_cache()` methods simplified
- `_session_semaphores` entries track creation time and get cleaned periodically

**Implementation Details**:

Base cache migration in `safebreach_base.py`:
- Replace `self._cache = {}` and `self._cache_timestamps = {}` with
  `self._cache = SafeBreachCache(name=f"{server_name}_base", maxsize=10, ttl=3600)`
- Simplify `get_from_cache(key)`: delegate to `self._cache.get(key)`
- Simplify `set_cache(key, data)`: delegate to `self._cache.set(key, data)`
- Remove manual TTL comparison and `del` statements

SSE semaphore fix:
- Change `_session_semaphores` from `Dict[str, asyncio.Semaphore]` to
  `Dict[str, tuple[asyncio.Semaphore, float]]` — stores `(semaphore, creation_timestamp)`
- Update session creation (line ~471) to include `time.time()` in tuple
- Update session cleanup callback to still pop entry
- Add `_cleanup_stale_semaphores()` async function: iterate dict, remove entries where
  `time.time() - creation_timestamp > 3600` (1 hour)
- Register periodic asyncio task that calls `_cleanup_stale_semaphores()` every 5 minutes
  — start this task in the server's startup/lifespan event

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/safebreach_base.py` | Modify | Migrate _cache, fix _session_semaphores |
| `safebreach_mcp_core/tests/test_safebreach_base.py` | Create/Modify | Tests for base cache + SSE fix |

**Test Plan**:

*Base cache migration tests:*
- Test `get_from_cache(key)` delegates to `self._cache.get(key)` correctly
- Test `set_cache(key, data)` delegates to `self._cache.set(key, data)` correctly
- Test `set_cache` when caching disabled does nothing
- Test `get_from_cache` when caching disabled returns None
- Test no `_cache_timestamps` dict exists (removed — TTLCache handles timestamps)

*SSE semaphore cleanup tests:*
- Test `_session_semaphores` stores `(semaphore, timestamp)` tuple on session creation
- Test normal session cleanup (SSE disconnect) still removes entry correctly
- Test `_cleanup_stale_semaphores` removes entries older than 1 hour
- Test `_cleanup_stale_semaphores` preserves entries younger than 1 hour
- Test mixed stale/active: create 500 stale + 500 active entries, run cleanup, verify
  exactly 500 removed and 500 preserved
- **Orphaned connection storm**: create 1000 orphaned entries (old timestamps), run cleanup,
  verify all 1000 removed, `len(_session_semaphores) == 0`
- Test cleanup task runs on interval (mock `asyncio.sleep`, verify `_cleanup_stale_semaphores`
  called on each iteration)
- Test semaphore objects are actually GC'd after cleanup: take weakref to semaphore,
  run cleanup, `gc.collect()`, verify weakref is dead

**Git Commit**: `fix(core): migrate base cache and fix SSE semaphore leak (SAF-28428)`

---

### Phase 8: Cache Monitoring

**Semantic Change**: Add periodic cache stats logging for operational visibility.

**Deliverables**:
- Registry of all `SafeBreachCache` instances
- Periodic background task logs stats every 5 minutes
- Warning when caches consistently run at capacity

**Implementation Details**:

Cache registry in `safebreach_cache.py`:
- Add module-level `_cache_registry: List[SafeBreachCache] = []`
- `SafeBreachCache.__init__` auto-registers the instance in the registry
- Add `get_all_cache_stats()` function: iterates registry, returns list of stats dicts
- Add `log_cache_stats()` function: calls `get_all_cache_stats()`, logs at INFO level
  with format like: `Cache 'simulators': 3/5 entries, 85% hit rate, TTL=3600s`
- Add WARNING log when `size == maxsize` for 3+ consecutive stat checks (tracks via
  counter on each cache instance)

Background monitoring task:
- Add `start_cache_monitoring(interval_seconds=300)` function that creates an asyncio task
- The task calls `log_cache_stats()` every `interval_seconds`
- Call `start_cache_monitoring()` from each server's startup

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/safebreach_cache.py` | Modify | Add registry, stats logging, monitoring |
| `safebreach_mcp_core/safebreach_base.py` | Modify | Start monitoring task on server startup |
| `safebreach_mcp_core/tests/test_safebreach_cache.py` | Modify | Add monitoring tests |

**Test Plan**:

*Registry tests:*
- Test cache auto-registration: creating `SafeBreachCache` adds it to `_cache_registry`
- Test multiple caches all registered: create 3 caches, verify all 3 in registry
- Test `get_all_cache_stats()` returns stats dict for each registered cache
- Test stats dict contains expected fields: `name`, `size`, `maxsize`, `ttl`, `hits`, `misses`, `hit_rate`

*Logging tests:*
- Test `log_cache_stats()` produces INFO log per cache with correct format
- Test capacity warning: fill cache to maxsize, call `log_cache_stats()` 3 times,
  verify WARNING log on 3rd call
- Test capacity warning resets: fill cache, trigger warning, then evict an item,
  verify WARNING counter resets

*Monitoring task tests:*
- Test `start_cache_monitoring()` creates an asyncio task
- Test monitoring task calls `log_cache_stats()` on interval (mock `asyncio.sleep`)
- Test monitoring task handles exceptions gracefully (doesn't crash on error)

*Memory safety of registry:*
- Test registry doesn't prevent cache garbage collection: create cache, take weakref,
  delete all references, verify cache is NOT GC'd (registry holds strong reference — this is
  expected and correct behavior, but document it)

**Git Commit**: `feat(core): add cache monitoring and stats logging (SAF-28428)`

---

### Phase 9: Memory Stress Tests + Baseline Comparison

**Semantic Change**: Add dedicated stress tests that prove memory stays bounded under all
conditions, and validate against Phase 0 baseline thresholds.

**Deliverables**:
- Comprehensive memory stress test suite
- `tracemalloc`-based memory measurement tests
- Multi-agent simulation tests
- Baseline comparison: re-run `memory_profile_baseline.py` with fixed code, compare against
  Phase 0 measurements
- All stress tests pass and meet acceptance thresholds from Phase 0

**Implementation Details**:

Create `safebreach_mcp_core/tests/test_memory_stress.py` with the following test categories:

**1. Cache Wrapper Stress Tests:**
- `test_rapid_insertion_bounded`: Insert 100,000 unique keys into `maxsize=3` cache in tight loop.
  Assert `len(cache) <= maxsize` after every 1000 iterations. Verify final size equals `maxsize`.
- `test_memory_returns_to_baseline`: Use `tracemalloc` to snapshot memory before and after:
  fill cache with 100 large (100KB) entries on `maxsize=3`, then `clear()`, then `gc.collect()`.
  Assert memory delta from baseline is < 500KB (accounting for overhead).
- `test_concurrent_agent_simulation`: Simulate 5 concurrent "agents" (threads), each doing
  1000 get/set operations with unique keys on shared `maxsize=5` cache. After all threads
  complete: assert `len(cache) <= maxsize`, no exceptions raised, no deadlocks.

**2. Data Server Cache Stress Tests (Tier 3 — highest risk):**
- `test_simulation_pagination_storm`: Mock API returning paginated simulations. Simulate agent
  querying 200 different `(console, test_id)` combinations in sequence on
  `simulations_cache` (`maxsize=3`). After all queries: assert `len(cache) == 3`,
  use `tracemalloc` to verify memory is bounded.
- `test_security_events_multiplicative_keys`: Simulate 10 consoles × 20 tests × 50 simulations =
  10,000 unique cache keys on `security_control_events_cache` (`maxsize=3`). Assert cache
  never exceeds 3 entries. Verify memory bounded via `tracemalloc`.
- `test_full_logs_large_payload_eviction`: Set 50 entries of 40KB each on
  `full_simulation_logs_cache` (`maxsize=2`). Assert only 2 entries retained.
  Use weakrefs on all 50 values, verify 48 are GC'd after `gc.collect()`.

**3. Cross-Server Stress Tests:**
- `test_all_caches_under_load`: Instantiate all 8 `SafeBreachCache` instances with production
  maxsize/TTL values. Bombard each with 1000 unique keys via 3 threads per cache.
  Snapshot memory via `tracemalloc` before and after. Assert total memory growth is bounded
  (< 50MB above baseline).
- `test_mixed_operations_no_leak`: For each cache: interleave 1000 set, 500 get, 200 delete,
  50 clear operations in random order from 3 threads. Assert `len(cache) <= maxsize` throughout.
  Assert no unhandled exceptions.

**4. SSE Semaphore Stress Tests:**
- `test_semaphore_mass_orphan`: Create 10,000 orphaned semaphore entries with timestamps
  2 hours old. Run `_cleanup_stale_semaphores()`. Assert dict is empty. Use `tracemalloc` to
  verify memory returns to baseline.
- `test_semaphore_leak_over_time`: Simulate 1000 "connect then orphan" cycles (create entry
  with old timestamp, never clean up). Then run cleanup. Assert all cleared. Memory bounded.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/tests/test_memory_stress.py` | Create | Memory stress test suite |

**5. Baseline Comparison Tests:**
- Re-run `memory_profile_baseline.py` Scenario B (caching enabled) with fixed code
- Save results to `prds/SAF-28428/post-fix-memory.json`
- Compare against Phase 0 baseline:
  - `test_rss_growth_bounded`: RSS growth during 100 queries < 50MB (threshold from Phase 0)
  - `test_rss_plateaus`: Memory growth rate over last 50% of queries ≈ 0 (not linear)
  - `test_peak_rss_acceptable`: Peak RSS < baseline + 100MB
  - `test_cache_entry_count_bounded`: Total entries across all caches ≤ sum of all maxsizes
- Run external monitor (`monitor_process_memory.py`) during stress tests to capture
  independent RSS measurements — compare CSV output against internal tracemalloc readings

**Test Plan**:
- All stress tests pass
- Memory measurements (tracemalloc) show bounded growth
- External process monitoring (psutil/RSS) confirms internal measurements
- Baseline comparison passes all acceptance thresholds
- No deadlocks or exceptions under concurrent load
- Run with: `uv run pytest safebreach_mcp_core/tests/test_memory_stress.py -v`

**Git Commit**: `test(core): add memory stress tests for cache safety (SAF-28428)`

---

### Phase 10: Documentation + Cleanup

**Semantic Change**: Update documentation and run final verification.

**Deliverables**:
- CLAUDE.md updated with new cache configuration env vars
- All cross-server tests passing
- PRD status updated

**Implementation Details**:

Documentation updates:
- Add `SB_MCP_CACHE_*` env vars to CLAUDE.md "Environment Setup" and
  "Caching Strategy" sections
- Update cache-related descriptions in CLAUDE.md to reflect bounded TTLCache approach
- Document new env vars in the "External Connection Support" / environment vars section

Final verification:
- Run full cross-server test suite
- Run linter/type checks if configured
- Verify no regressions

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Document new cache env vars and behavior |
| `prds/SAF-28428/prd.md` | Modify | Update PRD status to Complete |

**Test Plan**:
- Run full cross-server test suite:
  `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/
  safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/ -v -m "not e2e"`
- Verify all tests pass

**Git Commit**: `docs: update CLAUDE.md with new cache configuration (SAF-28428)`

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `cachetools` introduces subtle behavior differences vs raw dict | Medium | Comprehensive unit tests for each cache migration |
| Thread lock contention under high agent concurrency | Low | Lock held only for dict operations (microseconds); benchmark if needed |
| Test assertion updates miss edge cases | Medium | Run full cross-server suite after each phase |
| Studio cache pattern (set/get in different functions) complicates migration | Low | Phase 6 addresses explicitly; pattern is straightforward with wrapper |

### Assumptions

- `cachetools.TTLCache` LRU eviction is acceptable (ticket says FIFO but LRU is superior) — confirmed
- maxsize values (2-5) are sufficient for typical agent workloads — can tune post-deployment
- 5-minute monitoring interval is sufficient for observability
- Playbook cache 30-minute TTL is appropriate for ~60MB singleton entity

## 11. Future Enhancements

- **Redis-backed caching**: For multi-process deployments where process-local caches aren't shared
- **Cache warming**: Pre-populate frequently-accessed caches on server startup
- **Adaptive TTL**: Automatically adjust TTL based on data change frequency
- **Cache size metrics endpoint**: Expose cache stats via MCP tool for real-time monitoring
- **Per-console cache limits**: Different maxsize for high-volume vs low-volume consoles

## 12. Executive Summary

- **Issue**: MCP server caching uses unbounded Python dicts that grow indefinitely due to
  multiplicative cache keys (console×test×simulation), causing host memory exhaustion and crashes.
  Caching is currently disabled as a workaround.
- **Solution**: Replace 8 dict caches with `cachetools.TTLCache` instances wrapped in a
  thread-safe `SafeBreachCache` class with per-type maxsize/TTL, add per-server cache toggles,
  fix SSE session semaphore leak, and add cache monitoring.
- **Key Decisions**: Use `cachetools` library (battle-tested), LRU eviction (better than FIFO),
  per-server env var toggles, thread-safe wrapper for multi-agent deployment.
- **Business Value**: Restores caching capability safely, accelerating AI agent workflows while
  preventing memory exhaustion. Per-server toggles enable gradual rollout.
