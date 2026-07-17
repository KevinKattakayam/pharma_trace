"""
Enterprise ACID Database Transaction Manager.
Provides async connection pooling via asyncpg (if configured) with ACID-compliant SQLite EXCLUSIVE transaction fallback.
"""
import sqlite3
import asyncio
import re
import structlog
from contextlib import asynccontextmanager
from typing import Optional, Any, Generator, AsyncGenerator
from pathlib import Path
from config import get_settings

logger = structlog.get_logger()

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

DB_PATH = Path(__file__).parent.parent / "data" / "local_fallback.db"


class DatabaseTransactionManager:
    def __init__(self):
        self.settings = get_settings()
        self.database_url = getattr(self.settings, "database_url", "")
        self.pool: Optional[Any] = None
        self._sqlite_lock = asyncio.Lock()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async def init_pool(self):
        """Initialize asyncpg connection pool if DATABASE_URL is present."""
        if HAS_ASYNCPG and self.database_url:
            try:
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=2,
                    max_size=20,
                    timeout=10.0
                )
            except Exception as e:
                logger.error("asyncpg_pool_init_error", error=str(e), exc_info=True)
                self.pool = None

    async def close_pool(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Any, None]:
        """
        ACID Transaction Context Manager.
        Yields either an asyncpg transaction/connection object or a locked SQLite cursor.
        Automatically commits on success or rolls back on exception.
        """
        if self.pool:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    yield conn
        else:
            # ACID-compliant SQLite transaction fallback using BEGIN EXCLUSIVE
            async with self._sqlite_lock:
                conn = sqlite3.connect(DB_PATH, isolation_level=None)  # Manual transaction management
                try:
                    conn.execute("BEGIN EXCLUSIVE")
                    cursor = conn.cursor()
                    yield cursor
                    conn.execute("COMMIT")
                except Exception as e:
                    conn.execute("ROLLBACK")
                    raise e
                finally:
                    conn.close()

    async def execute_in_tx(self, queries: list[tuple[str, tuple]]) -> bool:
        """Execute a batch of parameterized queries inside an atomic transaction."""
        async with self.transaction() as tx:
            if self.pool:
                # asyncpg connection
                for sql, params in queries:
                    await tx.execute(sql, *params)
            else:
                # SQLite cursor
                for sql, params in queries:
                    # Convert postgres %s / $n to sqlite ? without altering quoted literals
                    sqlite_sql = re.sub(r'(?<![\'"])\$([0-9]+)(?![\'"])', '?', sql)
                    sqlite_sql = re.sub(r'(?<![\'"])%s(?![\'"])', '?', sqlite_sql)
                    tx.execute(sqlite_sql, params)
        return True


_db_pool_instance: Optional[DatabaseTransactionManager] = None

def get_db_pool() -> DatabaseTransactionManager:
    global _db_pool_instance
    if _db_pool_instance is None:
        _db_pool_instance = DatabaseTransactionManager()
    return _db_pool_instance
