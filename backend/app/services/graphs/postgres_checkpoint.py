import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global pool variable
_pool = None

async def get_db_pool():
    """Get or create the global DB pool (psycopg 3 for LangGraph)."""
    global _pool
    if _pool is None:
        dsn = settings.DATABASE_URL
        if not dsn:
            raise ValueError("DATABASE_URL is not set in configuration.")
        
        # Make sure we use the postgresql:// scheme for psycopg, 
        # asyncpg might use postgresql+asyncpg:// which psycopg handles or might need cleaning
        # SQLAlchemy URLs often look like postgresql+asyncpg://...
        # psycopg 3 expects postgresql://...
        clean_dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        
        logger.info("Creating new Psycopg Connection Pool for Checkpointer...")
        _pool = AsyncConnectionPool(conninfo=clean_dsn, open=False)
        await _pool.open()
        
    return _pool

async def ensure_checkpoint_schema():
    """
    Ensures the Postgres tables for the checkpointer exist.
    Must be run with autocommit=True because it creates indexes concurrently.
    """
    import psycopg
    settings = get_settings()
    dsn = settings.DATABASE_URL
    clean_dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    
    logger.info("Verifying checkpoint schema...")
    try:
        # Connect directly with autocommit=True for DDL operations
        async with await psycopg.AsyncConnection.connect(clean_dsn, autocommit=True) as conn:
            checkpointer = AsyncPostgresSaver(conn)
            await checkpointer.setup()
        logger.info("Checkpoint schema verified.")
    except Exception as e:
        logger.error(f"Failed to setup checkpoint schema: {e}")
        # We re-raise because if schema is missing, app shouldn't start
        raise e

async def get_postgres_checkpointer() -> AsyncPostgresSaver:
    """
    Returns an AsyncPostgresSaver initialized with the shared connection pool.
    Use this to persist graph state.
    """
    pool = await get_db_pool()
    checkpointer = AsyncPostgresSaver(pool)
    
    # We do NOT call setup() here anymore to avoid transaction issues
    # and performance overhead. It is called in main.py lifespan.
    
    return checkpointer

@asynccontextmanager
async def execution_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """
    Context manager to safely get the checkpointer.
    Useful for main execution loops.
    """
    cp = await get_postgres_checkpointer()
    yield cp
    # We generally don't close the global pool here, as it's shared.

