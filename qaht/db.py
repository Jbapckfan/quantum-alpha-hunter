"""
Database connection management with proper SQLite configuration
Fixes: WAL mode, busy timeout, composite primary key handling
"""
import os
import threading
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool, NullPool
from contextlib import contextmanager
import logging

from .config import get_config
from .schemas import Base

logger = logging.getLogger("qaht.db")

config = get_config()
_local = threading.local()


class DatabaseManager:
    """
    Manages database connections with proper pooling and SQLite optimization
    """

    def __init__(self):
        self.db_url = config.db_url
        self.is_sqlite = "sqlite" in self.db_url.lower()

        # Create engine with appropriate pool
        if self.is_sqlite:
            self.engine = create_engine(
                self.db_url,
                poolclass=NullPool,  # No pooling for SQLite (avoids locking issues)
                connect_args={"check_same_thread": False},
                echo=False  # Set to True for SQL debugging
            )
            self._configure_sqlite()
        else:
            # PostgreSQL or other databases
            self.engine = create_engine(
                self.db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False
            )

        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False  # Explicit control over flushing
        )
        self.ScopedSession = scoped_session(self.session_factory)

        logger.info(f"Database initialized: {self.db_url}")

    def _configure_sqlite(self):
        """
        CRITICAL FIX: Configure SQLite for production use
        - WAL mode for better concurrency
        - Increased busy timeout
        - Larger cache size
        """

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            # Write-Ahead Logging for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL")
            # Reduce lock conflicts
            cursor.execute("PRAGMA synchronous=NORMAL")
            # Wait up to 60 seconds for locks to clear
            cursor.execute("PRAGMA busy_timeout=60000")
            # 64MB cache size
            cursor.execute("PRAGMA cache_size=-64000")
            # Foreign key enforcement
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        logger.info("SQLite pragmas configured (WAL mode, busy timeout, cache)")

    def init_db(self):
        """Initialize database tables"""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables initialized")

    def drop_all(self):
        """Drop all tables (use with caution!)"""
        logger.warning("Dropping all database tables")
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session_scope(self):
        """
        Provide transactional scope around series of operations

        Usage:
            with session_scope() as session:
                session.add(obj)
                # Automatic commit on success, rollback on exception
        """
        session = self.ScopedSession()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database transaction failed: {str(e)}")
            raise
        finally:
            session.close()

    def get_session(self):
        """
        Get thread-local session

        Usage:
            session = db_manager.get_session()
            # ... use session ...
            session.close()  # Don't forget to close
        """
        if not hasattr(_local, "session"):
            _local.session = self.ScopedSession()
        return _local.session


# Global instance
db_manager = DatabaseManager()


# Convenience functions
def init_db():
    """Initialize database tables"""
    db_manager.init_db()


def drop_all():
    """Drop all tables"""
    db_manager.drop_all()


@contextmanager
def session_scope():
    """Get transactional session scope"""
    with db_manager.session_scope() as session:
        yield session


def get_session():
    """Get thread-local session"""
    return db_manager.get_session()
