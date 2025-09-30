import asyncio
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from ..config import settings

logger = structlog.get_logger()

# Create async engine
engine = create_async_engine(
    settings.get_database_url(),
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
    # Connection arguments for better performance
    connect_args={
        "server_settings": {
            "jit": "off",  # Disable JIT for faster connection
        }
    }
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Database dependency for FastAPI.
    
    Usage:
        @app.post("/users/")
        async def create_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
            # Use db session here
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error("database_error", error=str(e))
            raise
        except Exception as e:
            await session.rollback()
            logger.error("unexpected_database_error", error=str(e))
            raise
        finally:
            await session.close()


async def init_database():
    """Initialize database tables."""
    try:
        from .models import Base
        
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("database_initialized", tables=list(Base.metadata.tables.keys()))
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise


async def check_database_health() -> bool:
    """Check database connectivity for health checks."""
    try:
        async with AsyncSessionLocal() as session:
            # Simple query to test connection
            result = await session.execute(text("SELECT 1"))
            result.scalar()
            return True
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return False


async def close_database():
    """Close database connections on shutdown."""
    try:
        await engine.dispose()
        logger.info("database_connections_closed")
    except Exception as e:
        logger.error("database_close_error", error=str(e))


# Database connection pool monitoring
def get_database_pool_info() -> dict:
    """Get database connection pool information for monitoring."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(), 
        "overflow": pool.overflow(),
        "invalid": pool.invalid()
    }