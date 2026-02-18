# SAF-28428: Fix Cache Memory Leak in MCP Servers

## Proposed Title
**[safebreach-mcp] Fix cache memory leak with bounded TTLCache, per-server control, and monitoring**

## Summary
Replace all 8 unbounded `dict` caches with `cachetools.TTLCache` instances that have per-type
`maxsize` and `ttl` settings. Add per-server cache enable/disable env vars, fix orphaned SSE
session semaphore leak, and add periodic cache stats monitoring.

## Root Cause
Cache dictionaries grow unbounded because:
1. Cache keys are composed of multiple parts (console×test×simulation), creating unique entries
   that never get overwritten
2. No maximum size limits — caches grow indefinitely
3. No proactive cleanup — expired entries only removed on access (lazy deletion)
4. Single global TTL (1h) applied uniformly regardless of data size or volatility

## Solution: `cachetools.TTLCache` + Thin Wrapper

### 1. Add `cachetools` dependency
Add `cachetools>=5.3.0` to `pyproject.toml` dependencies.

### 2. Replace global dict caches with `TTLCache`
Each cache gets per-type `maxsize` (LRU eviction) and `ttl`:

| Cache | File | maxsize | TTL | Rationale |
|-------|------|---------|-----|-----------|
| `simulators_cache` | config_functions.py | 5 | 3600s | Bounded by console count |
| `tests_cache` | data_functions.py | 5 | 1800s | Bounded by console count |
| `simulations_cache` | data_functions.py | 3 | 600s | Medium cardinality (console×test) |
| `sec_ctrl_events_cache` | data_functions.py | 3 | 600s | High cardinality (C×T×S) |
| `findings_cache` | data_functions.py | 3 | 600s | Medium cardinality (console×test) |
| `full_sim_logs_cache` | data_functions.py | 2 | 300s | High cardinality, ~40KB/entry |
| `playbook_cache` | playbook_functions.py | 5 | 1800s | Bounded, large singleton |
| `studio_draft_cache` | studio_functions.py | 5 | 1800s | Medium cardinality (console×draft) |

### 3. Thread-safe wrapper
Wrap `TTLCache` with `threading.Lock` since multiple agents share the same server process.
Create a thin `SafeBreachCache` wrapper in `safebreach_mcp_core/` that encapsulates
the lock + TTLCache + stats tracking.

### 4. Per-server cache control (env vars)
Extend `cache_config.py` with per-server toggles:
- `SB_MCP_CACHE_CONFIG=true/false` — Config server
- `SB_MCP_CACHE_DATA=true/false` — Data server
- `SB_MCP_CACHE_PLAYBOOK=true/false` — Playbook server
- `SB_MCP_CACHE_STUDIO=true/false` — Studio server
- `SB_MCP_ENABLE_LOCAL_CACHING=true` — Global override (enables all)

Each `*_functions.py` checks its server-specific toggle via `is_caching_enabled(server_name)`.

### 5. Fix `_session_semaphores` leak
Add timestamp tracking to `_session_semaphores` in `safebreach_base.py`.
Periodic asyncio task sweeps entries older than 1 hour (orphaned SSE connections).

### 6. Cache monitoring
Add periodic logging (every 5 minutes) of cache stats:
- Entries count / max size per cache
- Hit/miss ratio
- Total estimated memory usage

### 7. Migrate `SafeBreachMCPBase._cache`
Replace the instance-level `self._cache` dict in `safebreach_base.py` with the same
`SafeBreachCache` wrapper for consistency.

## Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `cachetools>=5.3.0` dependency |
| `safebreach_mcp_core/cache_config.py` | Per-server toggles, `is_caching_enabled(server)` |
| `safebreach_mcp_core/safebreach_cache.py` | **NEW** — `SafeBreachCache` wrapper class |
| `safebreach_mcp_core/safebreach_base.py` | SSE semaphore cleanup, migrate `self._cache` |
| `safebreach_mcp_config/config_functions.py` | Replace `simulators_cache = {}` with TTLCache |
| `safebreach_mcp_data/data_functions.py` | Replace 5 global dict caches with TTLCache |
| `safebreach_mcp_playbook/playbook_functions.py` | Replace `playbook_cache = {}` with TTLCache |
| `safebreach_mcp_studio/studio_functions.py` | Replace `studio_draft_cache = {}` with TTLCache |
| Tests for each server | Update cache assertions for TTLCache API |

## Acceptance Criteria

1. [ ] All 8 global caches replaced with bounded `TTLCache` instances
2. [ ] Each cache has per-type `maxsize` and `ttl` configuration
3. [ ] LRU eviction prevents unbounded memory growth
4. [ ] Per-server cache enable/disable via environment variables
5. [ ] `SB_MCP_ENABLE_LOCAL_CACHING` still works as global toggle
6. [ ] Thread-safe cache access (multi-agent deployment)
7. [ ] Orphaned SSE `_session_semaphores` cleaned up periodically
8. [ ] Cache stats logged periodically for monitoring
9. [ ] All existing unit tests pass (updated for new cache API)
10. [ ] New unit tests for cache wrapper, eviction behavior, per-server toggles
11. [ ] Memory usage remains stable during extended operation

## Risk Assessment
- **Low risk**: `cachetools` is a well-maintained, widely-used library (50M+ downloads/month)
- **Medium risk**: Changing cache API across 4 servers requires updating all test assertions
- **Mitigation**: Per-server toggles allow gradual rollout (enable one server at a time)
