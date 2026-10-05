"""Bounded, TTL-expiring LRU cache (audit R10). Safe for single-threaded asyncio use."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, TypeVar

V = TypeVar("V")
_MISSING = object()


class TTLCache(Generic[V]):
    def __init__(self, maxsize: int = 1024, ttl_seconds: float = 3600.0) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default: V | None = None) -> V | None:
        item = self._data.get(key)
        if item is None:
            self.misses += 1
            return default
        expires, value = item
        if expires < time.monotonic():
            del self._data[key]
            self.misses += 1
            return default
        self._data.move_to_end(key)
        self.hits += 1
        return value

    def __contains__(self, key: str) -> bool:
        return self.get(key, _MISSING) is not _MISSING  # type: ignore[arg-type]

    def __getitem__(self, key: str) -> V:
        value = self.get(key, _MISSING)  # type: ignore[arg-type]
        if value is _MISSING:
            raise KeyError(key)
        return value  # type: ignore[return-value]

    def set(self, key: str, value: V) -> None:
        self._data[key] = (time.monotonic() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    __setitem__ = set

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
