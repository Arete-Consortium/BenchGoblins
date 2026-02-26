"""Tests for services __init__.py lazy imports."""

import pytest


class TestServicesLazyImport:
    def test_db_service(self):
        """Lazy import of db_service works."""
        from services import db_service

        assert db_service is not None

    def test_get_db(self):
        """Lazy import of get_db works."""
        from services import get_db

        assert callable(get_db)

    def test_get_session_context(self):
        """Lazy import of get_session_context works."""
        from services import get_session_context

        assert callable(get_session_context)

    def test_redis_service(self):
        """Lazy import of redis_service works."""
        from services import redis_service

        assert redis_service is not None

    def test_unknown_attribute_raises(self):
        """Unknown attribute raises AttributeError."""
        import services

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = services.nonexistent_thing
