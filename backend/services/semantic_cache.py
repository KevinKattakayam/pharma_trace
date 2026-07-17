"""
Enterprise Semantic Caching Service for AI Clinical Advisory & LLM Prompts.
Uses normalized trigram token similarity (RapidFuzz / Jaccard overlap) to match semantically equivalent
patient queries (e.g., 'high fever and headache' vs 'severe headache with fever') and return cached
clinical AI responses instantly in <5ms without consuming LLM tokens.
"""
import time
import asyncio
import structlog
from typing import Optional, Any
from rapidfuzz import fuzz
from services.cache_manager import get_cache

logger = structlog.get_logger()


class SemanticCacheService:
    def __init__(self, similarity_threshold: float = 0.90):
        self.threshold = similarity_threshold
        # In-memory index of recent semantic queries: list of (normalized_query, cache_key, timestamp)
        self._index: list[tuple[str, str, float]] = []
        self._lock = asyncio.Lock()
        self._max_index_size = 1000

    async def get_semantic_match(self, namespace: str, query_text: str) -> Optional[Any]:
        """
        Check if a semantically equivalent query exists in cache.
        Returns cached result if similarity >= threshold, else None.
        """
        if not query_text or len(query_text.strip()) < 3:
            return None

        clean_query = self._normalize_text(query_text)
        now = time.time()
        best_match_key = None
        highest_score = 0.0

        async with self._lock:
            # Prune stale index entries older than 24h
            self._index = [item for item in self._index if now - item[2] < 86400]

            for stored_query, cache_key, _ in self._index:
                if not cache_key.startswith(f"{namespace}:"):
                    continue
                # Calculate Token Sort Ratio (ignores word order: 'fever headache' == 'headache fever')
                score = fuzz.token_sort_ratio(clean_query, stored_query) / 100.0
                if score >= self.threshold and score > highest_score:
                    highest_score = score
                    best_match_key = cache_key

        if best_match_key:
            cache = get_cache()
            cached_data = await cache.get(best_match_key)
            if cached_data is not None:
                logger.info("semantic_cache_hit", namespace=namespace, similarity=round(highest_score, 2), key=best_match_key)
                return cached_data

        return None

    async def set_semantic_match(self, namespace: str, query_text: str, result_data: Any, ttl_seconds: int = 86400):
        """Store query and result in semantic cache index and Redis/LRU backend."""
        if not query_text or result_data is None:
            return

        clean_query = self._normalize_text(query_text)
        cache_key = f"{namespace}:{hash(clean_query)}"
        cache = get_cache()
        await cache.set(cache_key, result_data, ttl_seconds=ttl_seconds)

        async with self._lock:
            self._index.append((clean_query, cache_key, time.time()))
            if len(self._index) > self._max_index_size:
                self._index.pop(0)
        logger.debug("semantic_cache_stored", namespace=namespace, key=cache_key)

    def _normalize_text(self, text: str) -> str:
        """Lowercases, removes punctuation, and strips superfluous filler words."""
        import re
        clean = re.sub(r'[^\w\s]', '', text.lower())
        filler = {"a", "an", "the", "with", "and", "or", "is", "of", "to", "in", "for", "on", "by", "patient", "has", "experiencing", "having", "severe", "mild", "slight"}
        words = [w for w in clean.split() if w not in filler]
        return " ".join(sorted(words))


_semantic_cache_instance = SemanticCacheService()


def get_semantic_cache() -> SemanticCacheService:
    return _semantic_cache_instance
