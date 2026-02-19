"""
SafeBreachCache — Thread-safe LRU + TTL cache wrapper.

Wraps ``cachetools.TTLCache`` with a ``threading.Lock`` for safe concurrent
access and lightweight hit/miss/set counters for operational monitoring.
"""

from __future__ import annotations

import threading

from cachetools import TTLCache


class SafeBreachCache:
    """Thread-safe bounded cache with LRU eviction and TTL expiration.

    Parameters
    ----------
    name : str
        Human-readable label used in stats and logging.
    maxsize : int
        Maximum number of entries before LRU eviction kicks in.
    ttl : int
        Time-to-live in seconds for each entry.
    """

    def __init__(self, name: str, maxsize: int, ttl: int) -> None:
        self._name = name
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._sets = 0

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> object | None:
        """Return cached value for *key*, or ``None`` on miss/expired."""
        with self._lock:
            value = self._cache.get(key)
            if value is not None:
                self._hits += 1
            else:
                self._misses += 1
            return value

    def set(self, key: str, value: object) -> None:
        """Store *value* under *key*. LRU eviction fires when full."""
        with self._lock:
            self._cache[key] = value
            self._sets += 1

    def delete(self, key: str) -> bool:
        """Remove *key*. Returns ``True`` if it existed, ``False`` otherwise."""
        with self._lock:
            try:
                del self._cache[key]
                return True
            except KeyError:
                return False

    def clear(self) -> None:
        """Drop all entries and reset counters."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._sets = 0

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict:
        """Return a snapshot of cache metrics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "name": self._name,
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "sets": self._sets,
                "hit_rate": round(self._hits / total * 100, 2) if total else 0.0,
            }
