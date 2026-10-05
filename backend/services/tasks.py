"""Supervised background tasks (audit R11).

``asyncio.create_task`` returns a task the event loop only weakly references; if nobody
keeps it, it can be garbage-collected mid-flight and its exception is never seen. This
module keeps strong references, logs failures, and drains pending work on shutdown so
audit/learning writes are not silently lost on deploy.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger()
_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)

    def _done(t: asyncio.Task[Any]) -> None:
        _tasks.discard(t)
        if t.cancelled():
            logger.warning("background_task_cancelled", task=name)
        elif (exc := t.exception()) is not None:
            logger.error("background_task_failed", task=name, error=repr(exc))

    task.add_done_callback(_done)
    return task


def pending_count() -> int:
    return len(_tasks)


async def drain(grace_period: float = 10.0) -> int:
    """Wait for in-flight tasks; returns how many were still pending at timeout."""
    if not _tasks:
        return 0
    done, pending = await asyncio.wait(set(_tasks), timeout=grace_period)
    for t in pending:
        logger.error("background_task_abandoned_on_shutdown", task=t.get_name())
    return len(pending)
