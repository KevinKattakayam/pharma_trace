"""
Enterprise Circuit Breaker Pattern & Adaptive Bulkheading.
Prevents connection pool starvation and thread exhaustion during external API outages.
"""
import asyncio
import time
from functools import wraps
from typing import Any, Callable, Dict

import structlog

logger = structlog.get_logger()

class CircuitBreakerOpenException(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Circuit breaker '{name}' is OPEN. Failing fast without network blocking.")


class CircuitState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        async with self._lock:
            now = time.time()
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            return True

    async def record_success(self):
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("circuit_breaker_recovered", breaker_name=self.name, new_state="CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
                if self.state != CircuitState.OPEN:
                    logger.warning("circuit_breaker_tripped", breaker_name=self.name, failures=self.failure_count, new_state="OPEN")
                self.state = CircuitState.OPEN


_breakers: Dict[str, CircuitBreaker] = {}

def get_breaker(name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _breakers[name]


def circuit_breaker(name: str, failure_threshold: int = 3, recovery_timeout: float = 30.0):
    """Decorator to wrap async functions with circuit breaker protection."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            breaker = get_breaker(name, failure_threshold, recovery_timeout)
            if not await breaker.can_execute():
                raise CircuitBreakerOpenException(name)
            
            try:
                result = await func(*args, **kwargs)
                await breaker.record_success()
                return result
            except Exception as e:
                # Do not trip on logical validation/HTTP 4xx errors if raised as exceptions
                if isinstance(e, CircuitBreakerOpenException):
                    raise e
                await breaker.record_failure()
                raise e
        return wrapper
    return decorator
