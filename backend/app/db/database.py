from typing import Any, Dict, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import get_settings
from app.core.logging import logger

settings = get_settings()

# Configure SQLAlchemy engine with production-ready connection pooling
engine = create_engine(
    settings.sync_database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a transactional database session with guaranteed closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> Dict[str, Any]:
    """Probes PostgreSQL connectivity, server version, and enabled extensions."""
    try:
        with engine.connect() as conn:
            version_result = conn.execute(text("SELECT version();")).scalar()
            ext_results = conn.execute(text("SELECT extname FROM pg_extension ORDER BY extname;")).fetchall()
            extensions = [row[0] for row in ext_results]

            return {
                "connected": True,
                "version": version_result,
                "extensions": extensions,
            }
    except Exception as exc:
        logger.error(
            f"Database connectivity check failed: {exc}",
            extra={"operation": "check_db_connection", "status": "error"}
        )
        return {
            "connected": False,
            "error": str(exc),
            "extensions": [],
        }
