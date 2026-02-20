# Ticket Preparation Context: SAF-28428

## Status: Phase 6: PRD Created

## Ticket Information
- **Key**: SAF-28428
- **Summary**: [safebreach-mcp] Memory leak in MCP caching
- **Type**: Bug
- **Status**: To Do
- **Priority**: High
- **Sprint**: Saf sprint 83
- **Estimate**: 3h
- **Team**: AI Tools
- **Assignee**: Yossi Attas
- **Found in Phase**: dev testing

## Description
We have recently disabled the caching mechanism in the SafeBreach MCP servers because we observed a memory leak that caused the entire host to get exhausted and crash.

We now understand the bug in the caching mechanism and we can fix it as well as introduce some improvements to the caching mechanism to make it safer.

### Problems Identified
1. **No explicit cache eviction** - Data added to the cache is never explicitly removed. The caching mechanism assumes that when CACHE_TTL expires, the existing cached item will be implicitly released because a fresher item is added using the same cache_key. However, in reality cache_keys are concatenated of multiple parts making them unique. Cache piles up items without ever evacuating them.

2. **No size-based eviction** - No eviction rules based on number of cached items from each type. If agents invoke MCP tools at high pace, cache can explode. Need FIFO eviction policies to limit items of each type to 2-3 max.

3. **No granular cache control** - Currently all-or-nothing caching toggle for all MCP servers. Need per-server cache enablement.

4. **Single global TTL** - One CACHE_TTL for all caches. Need per-data-type TTLs. Heavier data entities should have shorter TTLs, except playbook entity (60MB singleton, rarely changes) which should cache ~30 minutes.

## Scope
- **Repositories**: /Users/yossiattas/Public/safebreach-mcp
- **Servers**: All server caches (Config, Data, Playbook, Studio)

## Investigation Findings

### 10 Cache Locations Identified

#### Global Unbounded Caches (Primary Leak Vectors)

| # | Cache | File | Line | Key Pattern | Cardinality | Risk |
|---|-------|------|------|-------------|-------------|------|
| 1 | `simulators_cache` | config_functions.py | 20 | `simulators_{console}` | Consoles | Low |
| 2 | `tests_cache` | data_functions.py | 28 | `tests_{console}` | Consoles | Low |
| 3 | `simulations_cache` | data_functions.py | 29 | `simulations_{console}_{test_id}` | Consoles×Tests | **HIGH** |
| 4 | `security_control_events_cache` | data_functions.py | 30 | `{console}:{test_id}:{sim_id}` | C×T×S | **CRITICAL** |
| 5 | `findings_cache` | data_functions.py | 1211 | `{console}:{test_id}` | Consoles×Tests | High |
| 6 | `full_simulation_logs_cache` | data_functions.py | 1661 | `full_sim_logs_{c}_{s}_{t}` | C×T×S (~40KB each) | **CRITICAL** |
| 7 | `playbook_cache` | playbook_functions.py | 26 | `attacks_{console}` | Consoles | Low |
| 8 | `studio_draft_cache` | studio_functions.py | 38 | `studio_draft_{console}_{draft}` | Consoles×Drafts | Medium |

#### Instance-Level & Session Caches

| # | Cache | File | Line | Notes |
|---|-------|------|------|-------|
| 9 | `self._cache` / `self._cache_timestamps` | safebreach_base.py | 63-64 | Lazy cleanup only |
| 10 | `_session_semaphores` | safebreach_base.py | 38 | Orphaned SSE connections leak |

### Root Causes
1. **No maximum cache size** - All global caches grow unbounded
2. **No proactive cleanup** - Expired entries remain in memory until accessed (lazy deletion only)
3. **Multiplicative key cardinality** - Keys multiply (console × test × simulation)
4. **Large data per entry** - Simulation logs ~40KB, full test/simulation objects
5. **Pagination stores everything** - `simulations_cache` stores ALL paginated results
6. **Session semaphore orphaning** - SSE disconnections leave entries forever
7. **Single global TTL** (3600s) - No per-type differentiation
8. **No metrics/monitoring** - No way to observe cache size growth

### Cache Configuration
- **File**: `safebreach_mcp_core/cache_config.py`
- **Control**: `SB_MCP_ENABLE_LOCAL_CACHING` env var
- **Default**: Disabled (currently disabled due to this bug)
- **Granularity**: All-or-nothing toggle across all servers

## Brainstorming Results

### Approach Selected: `cachetools.TTLCache` with thin wrapper

**Alternatives considered:**
- A: Custom `BoundedTTLCache` class — More control, but custom code to maintain
- B: `cachetools.TTLCache` (selected) — Battle-tested, LRU eviction, minimal custom code
- C: Decorator pattern — Poor fit for studio cache (set/get in different functions)

### Design Decisions
- **Eviction**: LRU (via cachetools) instead of FIFO — better cache hit rate
- **Per-server toggle**: Environment variables (SB_MCP_CACHE_CONFIG, etc.)
- **Thread safety**: Wrap with threading.Lock (multi-agent shared process)
- **SSE fix**: Periodic cleanup of orphaned `_session_semaphores`
- **Monitoring**: Periodic cache stats logging

### Cache Configuration (per cardinality analysis)

| Cache | maxsize | TTL | Cardinality Tier |
|-------|---------|-----|-----------------|
| `simulators_cache` | 5 | 3600s | Tier 1 (bounded by consoles) |
| `tests_cache` | 5 | 1800s | Tier 1 (bounded by consoles) |
| `simulations_cache` | 3 | 600s | Tier 2 (console×test) |
| `security_control_events_cache` | 3 | 600s | Tier 3 (console×test×sim) |
| `findings_cache` | 3 | 600s | Tier 2 (console×test) |
| `full_simulation_logs_cache` | 2 | 300s | Tier 3 (console×test×sim, ~40KB each) |
| `playbook_cache` | 5 | 1800s | Tier 1 (bounded by consoles) |
| `studio_draft_cache` | 5 | 1800s | Tier 2 (console×draft) |
