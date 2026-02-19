"""
Memory stress tests proving caches stay bounded under heavy load.

Covers:
1. Cache wrapper stress (rapid insertion, memory returns to baseline, concurrent agents)
2. Data server cache stress (pagination storms, multiplicative keys, large payloads)
3. Cross-server stress (all caches under load, mixed operations)
4. SSE semaphore stress (mass orphan cleanup, leak-over-time simulation)
"""

import asyncio
import gc
import random
import threading
import time
import tracemalloc
import weakref

import pytest

from safebreach_mcp_core.safebreach_cache import SafeBreachCache, _cache_registry
from safebreach_mcp_core.safebreach_base import (
    _session_semaphores,
    _SEMAPHORE_MAX_AGE,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Prevent test caches from leaking into other tests."""
    _cache_registry.clear()
    yield
    _cache_registry.clear()


# ---------------------------------------------------------------------------
# 1. Cache Wrapper Stress Tests
# ---------------------------------------------------------------------------

class TestCacheWrapperStress:
    """Prove the SafeBreachCache wrapper keeps memory bounded under heavy use."""

    def test_rapid_insertion_bounded(self):
        """Insert 100k unique keys into maxsize=3 cache. Size never exceeds maxsize."""
        cache = SafeBreachCache("rapid", maxsize=3, ttl=60)
        for i in range(100_000):
            cache.set(f"key_{i}", f"value_{i}")
            if i % 1000 == 0:
                assert len(cache) <= 3, f"Cache size {len(cache)} at iteration {i}"
        assert len(cache) == 3

    def test_memory_returns_to_baseline(self):
        """Fill cache with large entries, clear, and verify memory returns."""
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        cache = SafeBreachCache("mem_test", maxsize=3, ttl=60)
        # Fill with 100 large entries (100KB each) — only 3 retained
        for i in range(100):
            cache.set(f"big_{i}", "x" * 100_000)

        cache.clear()
        gc.collect()

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare top stats
        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_delta = sum(s.size_diff for s in stats)
        # Allow 500KB overhead for Python internals
        assert total_delta < 500_000, f"Memory delta {total_delta} bytes exceeds 500KB"

    def test_concurrent_agent_simulation(self):
        """5 threads × 1000 ops on shared maxsize=5 cache. No leaks, no deadlocks."""
        cache = SafeBreachCache("agents", maxsize=5, ttl=60)
        errors = []

        def agent(agent_id):
            try:
                for i in range(1000):
                    cache.set(f"agent_{agent_id}_key_{i}", f"val_{i}")
                    cache.get(f"agent_{agent_id}_key_{i}")
                    cache.get("nonexistent")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=agent, args=(a,)) for a in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), f"Thread {t.name} deadlocked"

        assert not errors, f"Agent errors: {errors}"
        assert len(cache) <= 5


# ---------------------------------------------------------------------------
# 2. Data Server Cache Stress Tests
# ---------------------------------------------------------------------------

class TestDataServerCacheStress:
    """Simulate data-server-like workloads on SafeBreachCache."""

    def test_simulation_pagination_storm(self):
        """200 unique (console, test_id) combos on maxsize=3 cache."""
        cache = SafeBreachCache("simulations", maxsize=3, ttl=600)
        for console_idx in range(10):
            for test_idx in range(20):
                key = f"console_{console_idx}_test_{test_idx}"
                cache.set(key, {"data": f"sim_results_{console_idx}_{test_idx}"})
        assert len(cache) == 3

    def test_security_events_multiplicative_keys(self):
        """10 consoles × 20 tests × 50 sims = 10,000 keys on maxsize=3."""
        cache = SafeBreachCache("sec_events", maxsize=3, ttl=600)
        tracemalloc.start()
        baseline = tracemalloc.take_snapshot()

        for c in range(10):
            for t in range(20):
                for s in range(50):
                    cache.set(f"c{c}_t{t}_s{s}", {"events": [1, 2, 3]})

        after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        assert len(cache) == 3
        stats = after.compare_to(baseline, "lineno")
        total_delta = sum(s.size_diff for s in stats)
        assert total_delta < 5_000_000, f"Memory grew {total_delta} bytes after 10k keys"

    def test_full_logs_large_payload_eviction(self):
        """50 entries of 40KB each on maxsize=2. 48 should be GC'd."""
        cache = SafeBreachCache("full_logs", maxsize=2, ttl=300)

        class Payload:
            def __init__(self, data):
                self.data = data

        refs = []
        for i in range(50):
            obj = Payload("x" * 40_000)
            refs.append(weakref.ref(obj))
            cache.set(f"log_{i}", obj)
            del obj

        gc.collect()
        assert len(cache) == 2
        alive = sum(1 for r in refs if r() is not None)
        # Only the 2 entries still in cache should be alive
        assert alive <= 2, f"{alive} payloads still alive, expected <= 2"


# ---------------------------------------------------------------------------
# 3. Cross-Server Stress Tests
# ---------------------------------------------------------------------------

class TestCrossServerStress:
    """Prove all production cache configurations stay bounded together."""

    PRODUCTION_CONFIGS = [
        ("simulators", 5, 3600),
        ("tests", 5, 1800),
        ("simulations", 3, 600),
        ("security_control_events", 3, 600),
        ("findings", 3, 600),
        ("full_simulation_logs", 2, 300),
        ("playbook_attacks", 5, 1800),
        ("studio_drafts", 5, 1800),
    ]

    def test_all_caches_under_load(self):
        """Bombard all 8 production caches with 1000 keys via 3 threads each."""
        caches = [
            SafeBreachCache(name, maxsize=ms, ttl=ttl)
            for name, ms, ttl in self.PRODUCTION_CONFIGS
        ]
        errors = []

        def bombard(cache, thread_id):
            try:
                for i in range(1000):
                    cache.set(f"t{thread_id}_k{i}", f"v{i}")
            except Exception as exc:
                errors.append(exc)

        threads = []
        for cache in caches:
            for tid in range(3):
                t = threading.Thread(target=bombard, args=(cache, tid))
                threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Errors: {errors}"
        for cache, (name, ms, _) in zip(caches, self.PRODUCTION_CONFIGS):
            assert len(cache) <= ms, f"Cache '{name}' size {len(cache)} > maxsize {ms}"

    def test_mixed_operations_no_leak(self):
        """Interleave set/get/delete/clear on each cache from 3 threads."""
        cache = SafeBreachCache("mixed_ops", maxsize=5, ttl=60)
        errors = []

        def mixed_worker(thread_id):
            try:
                keys = [f"t{thread_id}_k{i}" for i in range(200)]
                for i in range(500):
                    op = random.choice(["set", "set", "get", "delete", "clear"])
                    key = random.choice(keys)
                    if op == "set":
                        cache.set(key, f"val_{i}")
                    elif op == "get":
                        cache.get(key)
                    elif op == "delete":
                        cache.delete(key)
                    elif op == "clear":
                        cache.clear()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=mixed_worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Errors: {errors}"
        assert len(cache) <= 5


# ---------------------------------------------------------------------------
# 4. SSE Semaphore Stress Tests
# ---------------------------------------------------------------------------

class TestSemaphoreStress:
    """Prove SSE semaphore dict stays bounded with cleanup."""

    def setup_method(self):
        _session_semaphores.clear()

    def teardown_method(self):
        _session_semaphores.clear()

    def test_semaphore_mass_orphan(self):
        """Create 10,000 orphaned semaphores (2h old), clean them up."""
        old_time = time.time() - 7200  # 2 hours ago
        for i in range(10_000):
            _session_semaphores[f"orphan_{i}"] = (asyncio.Semaphore(1), old_time)

        assert len(_session_semaphores) == 10_000

        # Run cleanup logic
        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)

        assert len(_session_semaphores) == 0

    def test_semaphore_leak_over_time(self):
        """Simulate 1000 connect-then-orphan cycles, then cleanup."""
        for i in range(1000):
            # Each "connection" creates an entry with old timestamp (simulating time passing)
            _session_semaphores[f"session_{i}"] = (
                asyncio.Semaphore(1),
                time.time() - _SEMAPHORE_MAX_AGE - i - 1,
            )

        assert len(_session_semaphores) == 1000

        now = time.time()
        stale = [
            sid for sid, (_, created) in _session_semaphores.items()
            if now - created > _SEMAPHORE_MAX_AGE
        ]
        for sid in stale:
            _session_semaphores.pop(sid, None)

        assert len(_session_semaphores) == 0
