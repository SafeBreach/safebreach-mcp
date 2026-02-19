"""
Tests for SafeBreachCache wrapper class.

Covers functional operations, memory safety (LRU eviction and TTL expiration
release references), and thread safety under concurrent access.
"""

import gc
import threading
import time
import weakref

from safebreach_mcp_core.safebreach_cache import SafeBreachCache


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------

class TestSafeBreachCacheBasicOps:
    """Test get/set/delete/clear basic operations."""

    def test_set_and_get(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key_returns_none(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_overwrite_existing_key(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"

    def test_delete_existing_key_returns_true(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_missing_key_returns_false(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        assert cache.delete("nonexistent") is False

    def test_clear_empties_cache(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get("c") is None

    def test_contains_present_key(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert "key1" in cache

    def test_contains_missing_key(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        assert "missing" not in cache

    def test_len_reflects_live_entries(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        assert len(cache) == 0
        cache.set("a", 1)
        assert len(cache) == 1
        cache.set("b", 2)
        assert len(cache) == 2
        cache.delete("a")
        assert len(cache) == 1

    def test_multiple_data_types(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("str", "hello")
        cache.set("int", 42)
        cache.set("list", [1, 2, 3])
        cache.set("dict", {"key": "val"})
        cache.set("none", None)
        assert cache.get("str") == "hello"
        assert cache.get("int") == 42
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"key": "val"}
        assert cache.get("none") is None  # Indistinguishable from miss


# ---------------------------------------------------------------------------
# TTL expiration tests
# ---------------------------------------------------------------------------

class TestSafeBreachCacheTTL:
    """Test TTL-based expiration."""

    def test_item_expires_after_ttl(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_contains_returns_false_for_expired(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=1)
        cache.set("key1", "value1")
        time.sleep(1.1)
        assert "key1" not in cache

    def test_len_excludes_expired(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=1)
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2
        time.sleep(1.1)
        assert len(cache) == 0


# ---------------------------------------------------------------------------
# LRU eviction tests
# ---------------------------------------------------------------------------

class TestSafeBreachCacheLRU:
    """Test LRU eviction when maxsize is exceeded."""

    def test_evicts_oldest_when_full(self):
        cache = SafeBreachCache("test", maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Cache full: a, b, c. Adding d should evict a (LRU).
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_access_refreshes_lru_order(self):
        cache = SafeBreachCache("test", maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access 'a' to refresh it — now b is LRU.
        cache.get("a")
        cache.set("d", 4)
        assert cache.get("a") == 1  # Was refreshed, should survive
        assert cache.get("b") is None  # b was LRU, should be evicted
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_maxsize_one(self):
        cache = SafeBreachCache("test", maxsize=1, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert len(cache) == 1

    def test_len_never_exceeds_maxsize(self):
        cache = SafeBreachCache("test", maxsize=5, ttl=60)
        for i in range(100):
            cache.set(f"key{i}", i)
        assert len(cache) <= 5


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestSafeBreachCacheStats:
    """Test hit/miss/set counters and stats reporting."""

    def test_stats_initial(self):
        cache = SafeBreachCache("my_cache", maxsize=10, ttl=60)
        stats = cache.stats()
        assert stats["name"] == "my_cache"
        assert stats["size"] == 0
        assert stats["maxsize"] == 10
        assert stats["ttl"] == 60
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_after_operations(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("a", 1)  # set +1
        cache.set("b", 2)  # set +1
        cache.get("a")     # hit +1
        cache.get("b")     # hit +1
        cache.get("c")     # miss +1
        stats = cache.stats()
        assert stats["sets"] == 2
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 2
        # hit_rate = hits / (hits + misses) = 2/3 ~= 66.7%
        assert abs(stats["hit_rate"] - 66.67) < 0.1

    def test_clear_resets_stats(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        cache.set("a", 1)
        cache.get("a")
        cache.get("missing")
        cache.clear()
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0
        assert stats["size"] == 0


# ---------------------------------------------------------------------------
# Memory safety tests
# ---------------------------------------------------------------------------

class _Trackable:
    """A simple object that supports weakref for memory safety tests."""

    def __init__(self, data=None):
        self.data = data


class TestSafeBreachCacheMemorySafety:
    """Verify that evicted/expired/deleted entries release references."""

    def test_lru_eviction_frees_memory(self):
        cache = SafeBreachCache("test", maxsize=2, ttl=60)
        obj = _Trackable([1, 2, 3])
        ref = weakref.ref(obj)
        cache.set("evict_me", obj)
        del obj  # drop local reference
        # Fill cache to force eviction
        cache.set("b", "b_val")
        cache.set("c", "c_val")  # evicts "evict_me"
        gc.collect()
        assert ref() is None, "Evicted value should be garbage collected"

    def test_ttl_expiration_frees_memory(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=1)
        obj = _Trackable({"large": "data"})
        ref = weakref.ref(obj)
        cache.set("expire_me", obj)
        del obj
        time.sleep(1.1)
        # Trigger cache cleanup: read (returns None) then write to force
        # internal TTLCache eviction of stale entries
        cache.get("expire_me")
        cache.set("trigger_cleanup", "x")
        gc.collect()
        assert ref() is None, "Expired value should be garbage collected"

    def test_clear_releases_all_references(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        objects = [_Trackable(i) for i in range(5)]
        refs = [weakref.ref(o) for o in objects]
        for i, o in enumerate(objects):
            cache.set(f"key{i}", o)
        # Drop all local references including loop variables
        del objects
        del o  # noqa: F821 — loop variable from enumerate
        del i  # noqa: F821 — loop variable from enumerate
        cache.clear()
        gc.collect()
        for idx, ref in enumerate(refs):
            assert ref() is None, f"Cleared value {idx} should be garbage collected"

    def test_delete_releases_reference(self):
        cache = SafeBreachCache("test", maxsize=10, ttl=60)
        obj = _Trackable([99, 100])
        ref = weakref.ref(obj)
        cache.set("del_me", obj)
        del obj
        cache.delete("del_me")
        gc.collect()
        assert ref() is None, "Deleted value should be garbage collected"

    def test_rapid_set_cycles_stay_bounded(self):
        cache = SafeBreachCache("test", maxsize=3, ttl=60)
        for i in range(10_000):
            cache.set(f"key{i}", f"value{i}")
            if i % 100 == 0:
                assert len(cache) <= 3, (
                    f"Cache size {len(cache)} exceeded maxsize 3 at iteration {i}"
                )
        assert len(cache) <= 3


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------

class TestSafeBreachCacheThreadSafety:
    """Verify thread-safe concurrent access."""

    def test_concurrent_get_set_no_exceptions(self):
        cache = SafeBreachCache("test", maxsize=5, ttl=60)
        errors = []
        stop_event = threading.Event()

        def worker(thread_id):
            try:
                while not stop_event.is_set():
                    key = f"key_{thread_id}_{threading.current_thread().ident}"
                    cache.set(key, thread_id)
                    cache.get(key)
                    cache.get("nonexistent")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()

        time.sleep(1)
        stop_event.set()

        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(cache) <= 5

    def test_concurrent_set_with_eviction_bounded(self):
        cache = SafeBreachCache("test", maxsize=3, ttl=60)
        errors = []

        def writer(thread_id):
            try:
                for i in range(100):
                    cache.set(f"t{thread_id}_k{i}", i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(cache) <= 3, f"Cache size {len(cache)} exceeds maxsize 3"

    def test_no_deadlock_under_contention(self):
        cache = SafeBreachCache("test", maxsize=5, ttl=60)
        errors = []

        def mixed_ops(thread_id):
            try:
                for i in range(50):
                    cache.set(f"t{thread_id}_{i}", i)
                    cache.get(f"t{thread_id}_{i}")
                    cache.delete(f"t{thread_id}_{i}")
                    _ = len(cache)
                    _ = f"t{thread_id}_{i}" in cache
                    cache.stats()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=mixed_ops, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()

        # Use timeout to detect deadlocks
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive(), f"Thread {t.name} appears deadlocked"

        assert not errors, f"Thread errors: {errors}"
