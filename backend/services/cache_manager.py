"""
Enterprise Cache Manager — Distributed Redis with In-Memory LRU/TTL Fallback.
Provides unified async caching across multi-worker deployments.
"""
import asyncio
import json
import time
from typing import Any, Optional

import structlog

from config import get_settings

logger = structlog.get_logger()

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class CacheManager:
    def __init__(self):
        self.settings = get_settings()
        self.redis_url = getattr(self.settings, "redis_url", "")
        self.redis_client = None
        self._memory_cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._init_redis()

    def _init_redis(self):
        if HAS_REDIS and self.redis_url:
            try:
                self.redis_client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20
                )
            except Exception as e:
                logger.warning("redis_init_failed", error=str(e), fallback="in_memory")
                self.redis_client = None

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value by key from Redis or in-memory fallback."""
        if self.redis_client:
            try:
                val = await self.redis_client.get(key)
                if val is not None:
                    try:
                        return json.loads(val)
                    except json.JSONDecodeError:
                        return val
            except Exception as e:
                logger.error("redis_get_error", key=key, error=str(e), fallback="in_memory")

        # In-memory fallback
        async with self._lock:
            if key in self._memory_cache:
                expiry, val = self._memory_cache[key]
                if time.time() < expiry:
                    return val
                else:
                    del self._memory_cache[key]
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> bool:
        """Store value with TTL in Redis or in-memory fallback."""
        # Serialize for Redis/storage consistency
        try:
            serialized = json.dumps(value) if not isinstance(value, str) else value
        except (TypeError, ValueError):
            serialized = str(value)

        if self.redis_client:
            try:
                await self.redis_client.set(key, serialized, ex=ttl_seconds)
                return True
            except Exception as e:
                logger.error("redis_set_error", key=key, error=str(e), fallback="in_memory")

        # In-memory fallback
        async with self._lock:
            # Prune if memory cache exceeds 5000 items
            if len(self._memory_cache) > 5000:
                now = time.time()
                keys_to_del = [k for k, (exp, _) in self._memory_cache.items() if now >= exp]
                for k in keys_to_del:
                    del self._memory_cache[k]
                # If still too large, drop oldest 1000
                if len(self._memory_cache) > 5000:
                    for k in list(self._memory_cache.keys())[:1000]:
                        del self._memory_cache[k]

            self._memory_cache[key] = (time.time() + ttl_seconds, value)
        return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if self.redis_client:
            try:
                await self.redis_client.delete(key)
            except Exception:
                pass

        async with self._lock:
            if key in self._memory_cache:
                del self._memory_cache[key]
        return True

    async def clear(self):
        """Clear all cache entries."""
        if self.redis_client:
            try:
                await self.redis_client.flushdb()
            except Exception:
                pass

        async with self._lock:
            self._memory_cache.clear()


_cache_instance: Optional[CacheManager] = None

def get_cache() -> CacheManager:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance
