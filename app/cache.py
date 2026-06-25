"""In-memory TTL cache with a background janitor that auto-deletes stale entries."""
import time
import threading
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    """
    Thread-safe key-value cache where entries expire after `ttl_seconds`.
    A daemon thread runs every ttl/2 seconds and evicts expired keys automatically.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._store: dict[str, tuple] = {}  # key -> (value, inserted_at)
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._start_janitor()

    def _start_janitor(self) -> None:
        def _run():
            while True:
                time.sleep(self._ttl / 2)
                self._evict()

        t = threading.Thread(target=_run, daemon=True, name="cache-janitor")
        t.start()
        logger.debug("Cache janitor started (TTL=%ds)", self._ttl)

    def _evict(self) -> None:
        now = time.time()
        with self._lock:
            expired = [k for k, (_, ts) in self._store.items() if now - ts > self._ttl]
            for k in expired:
                del self._store[k]
        if expired:
            logger.debug("Cache janitor evicted %d expired entries", len(expired))

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, ts = entry
            if time.time() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (value, time.time())

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> dict:
        now = time.time()
        with self._lock:
            total = len(self._store)
            live = sum(1 for _, ts in self._store.values() if now - ts <= self._ttl)
        return {"total_keys": total, "live_keys": live, "ttl_seconds": self._ttl}


# Module-level singleton — 5-minute TTL for pricing data
pricing_cache = TTLCache(ttl_seconds=300)
