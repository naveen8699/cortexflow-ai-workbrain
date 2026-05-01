from datetime import datetime, timezone
from typing import AsyncGenerator
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from config import settings


def _build_engine():
    url = (
        f"postgresql+asyncpg://{settings.db_user}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    connect_args = {
        "password": settings.db_password,
        "server_settings": {"search_path": settings.db_schema},
        "ssl": "require",
    }

    engine = create_async_engine(
        url,
        connect_args=connect_args,
        echo=not settings.is_production,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def connect(dbapi_connection, connection_record):
        async def setup(conn):
            try:
                from pgvector.asyncpg import register_vector
                await register_vector(conn)
            except Exception:
                try:
                    await conn.set_type_codec(
                        'vector',
                        encoder=lambda v: str(v),
                        decoder=lambda v: [float(x) for x in v.strip('[]').split(',')],
                        schema='workbrain_schema',
                        format='text'
                    )
                except Exception:
                    pass
        dbapi_connection.run_async(setup)

    return engine


engine = _build_engine()
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB connection failed: {e}")
        return False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)