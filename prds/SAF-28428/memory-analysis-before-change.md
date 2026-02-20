# Memory Analysis: Before Cache Fix (SAF-28428)

## Executive Summary

The E2E memory baseline against live pentest01 console reveals **+301 MB cache overhead** from only **39 cache entries**.
With unbounded caching enabled, RSS grows by **590 MB** vs **289 MB** without caching -- a 2x memory amplification.
The playbook KB singleton alone accounts for ~450 MB per API fetch.

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Console | pentest01 |
| Tests | 5 (real test runs from production) |
| Simulations per test | 3 |
| Total simulations | 13 |
| Playbook pages iterated | 10 (of ~1,200 total) |
| Total API calls | 52 per scenario |
| API errors | 0 |
| Python version | 3.12.8 |
| Platform | macOS (Darwin) |
| Timestamp | 2026-02-19T10:25:46Z |

## Results Summary

| Metric | Caching DISABLED | Caching ENABLED (buggy) | Delta |
|--------|-----------------|------------------------|-------|
| RSS start | 255.3 MB | 544.7 MB | +289.4 MB (residual from Scenario A) |
| RSS end | 544.7 MB | 1,134.8 MB | +590.0 MB |
| RSS peak (OS) | 1,121.7 MB | 1,662.3 MB | +540.6 MB |
| RSS growth | +289.4 MB | +590.0 MB | +300.6 MB (cache overhead) |
| tracemalloc peak | 499.5 MB | 655.5 MB | +156.0 MB (Python heap) |
| Cache entries | 0 | 39 | 39 entries = 301 MB |

**Per-entry average: ~7.7 MB per cache entry.**

## RSS Growth Trajectory

### Scenario A: Caching DISABLED

```
RSS (MB)
 810 |          * *                    (playbook transient spike)
     |
 620 |                    * *  *  *    (data server workload)
     |
 545 |                                * (end - GC reclaimed transient data)
     |
 255 |  * *                            (start + simulators)
     +--+--+--+--+--+--+--+--+--+-->
        sim pb  t1 t2  t3 t4  t5 end
```

Samples: 255.3 -> 255.3 -> 807.5 -> 807.5 -> 802.8 -> 620.4 -> 625.3 -> 620.4 -> 544.7

### Scenario B: Caching ENABLED (unbounded)

```
RSS (MB)
1362 |                   *             (peak during large test caching)
     |
1135 |                            *    (end - data retained in caches)
     |
 993 |          * *  *                 (playbook cached + tests starting)
     |
 545 |  * *                            (start + simulators)
     +--+--+--+--+--+--+--+--+--+-->
        sim pb  t1 t2  t3 t4  t5 end
```

Samples: 544.7 -> 544.7 -> 993.2 -> 993.6 -> 1005.1 -> 1362.4 -> 1329.1 -> 1260.2 -> 1134.8

## Cache Entry Counts (Scenario B)

| Cache | Entries | Key Pattern | Notes |
|-------|---------|-------------|-------|
| simulators | 1 | `simulators_{console}` | Singleton per console |
| tests | 1 | `tests_{console}` | Contains all 196 tests as one blob |
| simulations | 5 | `simulations_{console}_{test_id}` | One per test; largest has 3,200+ sims |
| security_control_events | 13 | `{console}:{test_id}:{sim_id}` | One per simulation |
| findings | 5 | `{console}:{test_id}` | One per test |
| full_simulation_logs | 13 | `full_simulation_logs_{console}_{sim_id}_{test_id}` | ~40KB per role per sim |
| playbook | 1 | `attacks_{console}` | **~450 MB** - entire KB (~12K attacks) |
| studio_drafts | 0 | `{console}_{attack_id}` | Not exercised in baseline |
| **Total** | **39** | | |

## Key Findings

### 1. Playbook KB is the dominant memory consumer

The playbook cache stores the **entire SafeBreach attack knowledge base** (~12,000 attacks with full details)
as a single cache entry. Each API fetch transfers ~450 MB of data. With caching disabled, this is transient
(GC reclaims it). With caching enabled, it persists indefinitely.

- Playbook RSS impact (disabled): 255 -> 808 MB = **+553 MB transient spike**
- Playbook RSS impact (enabled): 545 -> 993 MB = **+448 MB retained**

### 2. Simulations cache has multiplicative cardinality

The `simulations_cache` stores ALL simulations for a test under one key. Test `1771431234550.41` has
**3,200+ simulations** fetched across 32+ API pages. The internal function `_get_all_simulations_from_cache_or_api`
fetches the entire dataset before local pagination.

This means:
- 1 console x 5 tests = 5 cache keys
- But each key holds hundreds to thousands of simulation objects
- Real-world agents query many tests across multiple consoles

### 3. No eviction means unbounded growth

Current caches are plain Python `dict` objects:
- No maximum size (LRU/FIFO eviction)
- No proactive TTL expiration (only lazy check on read)
- No per-server enable/disable control
- Cache grows monotonically until process restart

### 4. Memory never decreases with caching enabled

In Scenario A (disabled), RSS drops from 808 MB back to 545 MB after playbook processing completes,
because GC reclaims the transient response data. In Scenario B (enabled), RSS never drops below the
cached data watermark because references are held in the cache dicts.

### 5. Real-world extrapolation is alarming

This baseline used only:
- **1 console** (production agents query 5-10 consoles)
- **5 tests** (agents routinely scan 50-100 tests)
- **3 sims/test** (agents drill into 10-50 sims per test)
- **10 playbook pages** (full iteration = 1,200+ pages, each re-fetching the KB when uncached)

Projected real-world cache growth with current (buggy) implementation:
- 5 consoles x 50 tests x 10 sims = 2,500 simulation detail keys
- 5 consoles x 50 tests x 10 sims = 2,500 security event keys
- 5 consoles x 50 tests x 10 sims = 2,500 full log keys
- 5 playbook singletons = 5 x ~450 MB = **~2.25 GB just for playbook**
- **Total estimated: 3-5 GB+ unbounded growth**

### 6. SSE session semaphore leak (not measured)

The `_session_semaphores` dict in the base class accumulates `asyncio.Semaphore` objects per SSE session
but never removes them. While each semaphore is small (~200 bytes), long-running servers with thousands
of SSE connections accumulate entries indefinitely. This is a separate leak vector not captured in
this memory baseline.

## Acceptance Thresholds (Post-Fix)

After implementing bounded caches with `cachetools.TTLCache`:

| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Max RSS growth (disabled) | 350 MB | Transient API processing unchanged |
| Max RSS growth (enabled, fixed) | 400 MB | Bounded caches add minimal overhead |
| Max cache overhead (enabled - disabled) | 50 MB | Key metric: bounded caches should not accumulate |
| Max peak RSS above baseline | 1,200 MB | Transient spikes during playbook fetch still occur |

## Files

- Baseline script: `tests/memory_profile_baseline.py`
- Baseline results: `prds/SAF-28428/baseline-memory.json`
- E2E test baseline: `prds/SAF-28428/baseline-e2e-tests.txt`
- Process monitor: `tests/monitor_process_memory.py`
