"""
Run this directly in Cloud Shell to diagnose the exact DB connection error.
Usage: python3 /tmp/test_db.py
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.expanduser('~/cortexflow-ai-workbrain/backend'))

async def test_direct_asyncpg():
    """Test 1: Direct asyncpg connection — bypasses SQLAlchemy"""
    import asyncpg
    print("\n=== Test 1: Direct asyncpg ===")
    try:
        conn = await asyncpg.connect(
            host='127.0.0.1', port=5432,
            user='workbrain_user', password='Workbrain!!4321',
            database='workbrain'
        )
        r = await conn.fetchval("SET search_path TO workbrain_schema; SELECT COUNT(*) FROM meetings")
        print(f"SUCCESS: {r} rows in meetings")
        await conn.close()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

async def test_sqlalchemy_url():
    """Test 2: SQLAlchemy with the URL from config"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    from config import settings

    url = settings.get_db_url()
    print(f"\n=== Test 2: SQLAlchemy URL ===")
    print(f"URL: {url}")
    try:
        engine = create_async_engine(url, echo=True)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM meetings"))
            print(f"SUCCESS: {result.scalar()} rows")
        await engine.dispose()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

async def test_sqlalchemy_params():
    """Test 3: SQLAlchemy with explicit params (no URL encoding issues)"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text, event
    from sqlalchemy.pool import NullPool

    print(f"\n=== Test 3: SQLAlchemy explicit params ===")
    try:
        engine = create_async_engine(
            "postgresql+asyncpg://workbrain_user:Workbrain!!4321@127.0.0.1:5432/workbrain",
            connect_args={
                "server_settings": {"search_path": "workbrain_schema"}
            },
            echo=False,
        )
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM meetings"))
            print(f"SUCCESS: {result.scalar()} rows")
        await engine.dispose()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

async def test_sqlalchemy_connect_args():
    """Test 4: Pass password via connect_args to avoid URL parsing"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    print(f"\n=== Test 4: SQLAlchemy connect_args with raw password ===")
    try:
        engine = create_async_engine(
            "postgresql+asyncpg://workbrain_user@127.0.0.1:5432/workbrain",
            connect_args={
                "password": "Workbrain!!4321",
                "server_settings": {"search_path": "workbrain_schema"},
            },
            echo=False,
        )
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM meetings"))
            print(f"SUCCESS: {result.scalar()} rows")
        await engine.dispose()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

async def main():
    await test_direct_asyncpg()
    await test_sqlalchemy_url()
    await test_sqlalchemy_params()
    await test_sqlalchemy_connect_args()

asyncio.run(main())
