from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger

db_url = settings.DATABASE_URL
if not db_url or "postgresql" in db_url:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        logger.info("asyncpg not installed; using SQLite database.")
        db_url = "sqlite+aiosqlite:///./aivastra.db"

# Initialize async engine
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False,
}

if not db_url.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
    })

engine = create_async_engine(db_url, **engine_kwargs)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an asynchronous SQLAlchemy database session.
    Automatically handles transaction closing and cleanup.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error occurred: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
