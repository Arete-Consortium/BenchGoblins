"""API Services"""

# Lazy imports to avoid requiring sqlalchemy for all service imports
__all__ = [
    "db_service",
    "get_db",
    "get_session_context",
    "redis_service",
]


def __getattr__(name):
    """Lazy import services only when needed."""
    if name in ("db_service", "get_db", "get_session_context"):
        from .database import db_service, get_db, get_session_context

        return {
            "db_service": db_service,
            "get_db": get_db,
            "get_session_context": get_session_context,
        }[name]
    if name == "redis_service":
        from .redis import redis_service

        return redis_service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
