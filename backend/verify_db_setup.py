
import asyncio
import os
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings

async def verify():
    print("Verifying DB connection and Checkpointer...")
    
    settings = get_settings()
    dsn = settings.DATABASE_URL
    if not dsn:
        print("ERROR: DATABASE_URL not set")
        return

    clean_dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    print(f"Using DSN: {clean_dsn.split('@')[-1]}") # Hide credentials
    
    try:
        # 1. Run Setup with Autocommit (required for concurrent index creation)
        print("Running setup with autocommit connection...")
        import psycopg
        async with await psycopg.AsyncConnection.connect(clean_dsn, autocommit=True) as conn:
            checkpointer_setup = AsyncPostgresSaver(conn)
            await checkpointer_setup.setup()
        print("✅ Checkpointer setup complete (tables/indexes ensured).")

        # 2. Verify Pool for Runtime
        pool = AsyncConnectionPool(conninfo=clean_dsn, open=False)
        await pool.open()
        print("✅ Pool result created and opened successfully.")
        
        checkpointer = AsyncPostgresSaver(pool)
        print(f"✅ Checkpointer initialized with pool: {checkpointer}")
        
        await pool.close()
        print("✅ Pool closed.")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify())
