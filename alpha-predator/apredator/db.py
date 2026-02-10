"""Database connection management with proper SQLite configuration."""
import os
import threading
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import logging

from .config import get_config
from .schemas import Base

logger = logging.getLogger("apredator.db")

config = get_config()
_local = threading.local()


class DatabaseManager:
    """Manages database connections with proper pooling and SQLite optimization."""

    def __init__(self):
        self.db_url = config.db_url
        self.is_sqlite = "sqlite" in self.db_url.lower()

        if self.is_sqlite:
            self.engine = create_engine(
                self.db_url,
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
                echo=False,
            )
            self._configure_sqlite()
        else:
            self.engine = create_engine(
                self.db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False,
            )

        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )
        self.ScopedSession = scoped_session(self.session_factory)
        logger.info(f"Database initialized: {self.db_url}")

    def _configure_sqlite(self):
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragmas(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        logger.info("SQLite pragmas configured (WAL mode, busy timeout, cache)")

    def init_db(self):
        Base.metadata.create_all(self.engine)
        logger.info("Database tables initialized")

    def drop_all(self):
        logger.warning("Dropping all database tables")
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session_scope(self):
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
        if not hasattr(_local, "session"):
            _local.session = self.ScopedSession()
        return _local.session


db_manager = DatabaseManager()


def init_db():
    db_manager.init_db()


def drop_all():
    db_manager.drop_all()


@contextmanager
def session_scope():
    with db_manager.session_scope() as session:
        yield session


def get_session():
    return db_manager.get_session()
