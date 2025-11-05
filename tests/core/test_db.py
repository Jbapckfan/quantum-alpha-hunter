"""
Tests for Database Connection Management
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from sqlalchemy import Column, Integer, String, text
from sqlalchemy.orm import declarative_base


# Create a test base and model for testing
TestBase = declarative_base()


class TestModel(TestBase):
    __tablename__ = 'test_model_table'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50))


class TestDatabaseManagerBasics:
    """Test basic DatabaseManager functionality"""

    def test_database_manager_has_required_attributes(self):
        """Test DatabaseManager has all required attributes"""
        from qaht.db import db_manager

        assert hasattr(db_manager, 'engine')
        assert hasattr(db_manager, 'session_factory')
        assert hasattr(db_manager, 'ScopedSession')
        assert hasattr(db_manager, 'db_url')
        assert hasattr(db_manager, 'is_sqlite')

    def test_database_manager_is_sqlite(self):
        """Test database manager correctly identifies SQLite"""
        from qaht.db import db_manager

        # Default config should be SQLite
        assert db_manager.is_sqlite is True

    def test_session_factory_is_callable(self):
        """Test session factory can be called"""
        from qaht.db import db_manager

        session = db_manager.session_factory()
        assert session is not None
        session.close()


class TestSessionScope:
    """Test session_scope context manager"""

    def test_session_scope_provides_session(self, tmp_path):
        """Test session_scope provides a session"""
        from qaht.db import db_manager

        # Create temp database
        test_db = tmp_path / "test_session.db"
        original_url = db_manager.db_url

        try:
            # Use a fresh database for this test
            TestBase.metadata.create_all(db_manager.engine)

            with db_manager.session_scope() as session:
                assert session is not None
                # Session should be usable
                result = session.execute(text("SELECT 1")).scalar()
                assert result == 1

        finally:
            TestBase.metadata.drop_all(db_manager.engine)

    def test_session_scope_commits_on_success(self, tmp_path):
        """Test session_scope commits changes"""
        from qaht.db import db_manager

        TestBase.metadata.create_all(db_manager.engine)

        try:
            # Add a record
            with db_manager.session_scope() as session:
                model = TestModel(name='test')
                session.add(model)

            # Verify it was committed
            with db_manager.session_scope() as session:
                count = session.query(TestModel).count()
                assert count >= 1

        finally:
            TestBase.metadata.drop_all(db_manager.engine)

    def test_session_scope_rollback_on_exception(self):
        """Test session_scope rolls back on exception"""
        from qaht.db import db_manager

        TestBase.metadata.create_all(db_manager.engine)

        try:
            # Get initial count
            with db_manager.session_scope() as session:
                initial_count = session.query(TestModel).count()

            # Try to add but fail
            with pytest.raises(ValueError):
                with db_manager.session_scope() as session:
                    model = TestModel(name='will_fail')
                    session.add(model)
                    raise ValueError("Intentional error")

            # Verify nothing was committed
            with db_manager.session_scope() as session:
                final_count = session.query(TestModel).count()
                assert final_count == initial_count

        finally:
            TestBase.metadata.drop_all(db_manager.engine)


class TestGetSession:
    """Test get_session functionality"""

    def test_get_session_returns_session(self):
        """Test get_session returns a session"""
        from qaht.db import db_manager

        session = db_manager.get_session()
        assert session is not None
        session.close()

    def test_get_session_thread_local(self):
        """Test get_session returns same session in same thread"""
        from qaht.db import db_manager

        session1 = db_manager.get_session()
        session2 = db_manager.get_session()

        # Should be same session
        assert session1 is session2

        session1.close()


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_init_db_function_exists(self):
        """Test init_db convenience function exists"""
        from qaht import db

        assert hasattr(db, 'init_db')
        assert callable(db.init_db)

    def test_drop_all_function_exists(self):
        """Test drop_all convenience function exists"""
        from qaht import db

        assert hasattr(db, 'drop_all')
        assert callable(db.drop_all)

    def test_session_scope_function_exists(self):
        """Test session_scope convenience function exists"""
        from qaht import db

        assert hasattr(db, 'session_scope')

    def test_get_session_function_exists(self):
        """Test get_session convenience function exists"""
        from qaht import db

        assert hasattr(db, 'get_session')
        assert callable(db.get_session)

    def test_convenience_session_scope_works(self):
        """Test convenience session_scope function works"""
        from qaht.db import session_scope

        with session_scope() as session:
            assert session is not None
            # Test basic query
            result = session.execute(text("SELECT 1")).scalar()
            assert result == 1

    def test_convenience_get_session_works(self):
        """Test convenience get_session function works"""
        from qaht.db import get_session

        session = get_session()
        assert session is not None
        session.close()


class TestDatabaseInitialization:
    """Test database initialization"""

    def test_init_db_creates_tables(self):
        """Test init_db creates tables"""
        from qaht.db import db_manager
        from sqlalchemy import inspect

        # Clean slate
        TestBase.metadata.drop_all(db_manager.engine)

        # Initialize our test table
        TestBase.metadata.create_all(db_manager.engine)

        # Verify table exists
        inspector = inspect(db_manager.engine)
        tables = inspector.get_table_names()

        assert 'test_model_table' in tables

        # Cleanup
        TestBase.metadata.drop_all(db_manager.engine)

    def test_drop_all_function_callable(self):
        """Test drop_all function is callable"""
        from qaht.db import db_manager

        # Should not raise exception
        TestBase.metadata.create_all(db_manager.engine)
        TestBase.metadata.drop_all(db_manager.engine)


class TestErrorHandling:
    """Test error handling"""

    def test_session_scope_logs_on_exception(self, caplog):
        """Test session_scope logs errors"""
        from qaht.db import db_manager
        import logging

        caplog.set_level(logging.ERROR)

        with pytest.raises(ValueError):
            with db_manager.session_scope() as session:
                raise ValueError("Test error")

        # Check error was logged
        assert "Database transaction failed" in caplog.text

    def test_session_scope_reraises_exception(self):
        """Test session_scope re-raises exceptions"""
        from qaht.db import db_manager

        with pytest.raises(ValueError, match="Custom error"):
            with db_manager.session_scope() as session:
                raise ValueError("Custom error")


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database operations"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Setup and teardown for each test"""
        from qaht.db import db_manager

        # Setup: create tables
        TestBase.metadata.create_all(db_manager.engine)

        yield

        # Teardown: drop tables
        TestBase.metadata.drop_all(db_manager.engine)

    def test_crud_operations(self):
        """Test Create, Read, Update, Delete operations"""
        from qaht.db import session_scope

        # Create
        with session_scope() as session:
            model = TestModel(name='test_crud')
            session.add(model)
            session.flush()
            created_id = model.id

        # Read
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            assert model is not None
            assert model.name == 'test_crud'

        # Update
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            model.name = 'updated'

        # Verify update
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            assert model.name == 'updated'

        # Delete
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            session.delete(model)

        # Verify deletion
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            assert model is None

    def test_transaction_isolation(self):
        """Test transactions are isolated"""
        from qaht.db import session_scope

        # Transaction 1: Add record
        with session_scope() as session:
            model = TestModel(name='isolated')
            session.add(model)
            session.flush()
            created_id = model.id

        # Transaction 2: Read in separate session
        with session_scope() as session:
            model = session.query(TestModel).filter_by(id=created_id).first()
            assert model is not None
            assert model.name == 'isolated'

    def test_multiple_records(self):
        """Test handling multiple records"""
        from qaht.db import session_scope

        # Add multiple records
        with session_scope() as session:
            for i in range(5):
                model = TestModel(name=f'record_{i}')
                session.add(model)

        # Verify all were added
        with session_scope() as session:
            count = session.query(TestModel).count()
            assert count >= 5


class TestThreadSafety:
    """Test thread safety"""

    def test_different_threads_get_different_sessions(self):
        """Test threads get different sessions"""
        from qaht.db import db_manager
        import threading

        session_ids = []

        def get_session_id():
            session = db_manager.get_session()
            session_ids.append(id(session))
            session.close()

        threads = [threading.Thread(target=get_session_id) for _ in range(3)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should have collected 3 different session IDs
        assert len(session_ids) == 3
        # All should be different
        assert len(set(session_ids)) == 3
