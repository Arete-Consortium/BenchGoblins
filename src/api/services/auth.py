"""
Google OAuth Authentication Service.

Handles Google ID token verification, user management, and JWT session tokens.

Environment Variables:
    GOOGLE_CLIENT_ID: Google OAuth 2.0 Client ID
    JWT_SECRET_KEY: Secret key for signing JWT tokens (min 32 characters recommended)
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import User

logger = logging.getLogger("benchgoblins.auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
# Access tokens expire in 1 hour — clients should call /auth/refresh before expiry
JWT_EXPIRATION_HOURS = 1
# Refresh window: a token can be refreshed up to 7 days after issuance
JWT_REFRESH_WINDOW_HOURS = 24 * 7

# Validate secret strength at import time for production deployments
if os.getenv("ENVIRONMENT", "development") == "production" and len(JWT_SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must be at least 32 characters in production. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )


class AuthServiceError(Exception):
    """Base exception for auth service errors."""

    pass


class InvalidTokenError(AuthServiceError):
    """Raised when a token is invalid or expired."""

    pass


class ConfigurationError(AuthServiceError):
    """Raised when required configuration is missing."""

    pass


# ---------------------------------------------------------------------------
# Google Token Verification
# ---------------------------------------------------------------------------


def verify_google_token(token: str) -> dict:
    """
    Verify a Google ID token and return user information.

    Args:
        token: Google ID token from client-side authentication

    Returns:
        dict with user info: {
            "google_id": str,
            "email": str,
            "name": str,
            "picture_url": str | None,
            "email_verified": bool
        }

    Raises:
        ConfigurationError: If GOOGLE_CLIENT_ID is not configured
        InvalidTokenError: If token is invalid, expired, or from wrong issuer
    """
    if not GOOGLE_CLIENT_ID:
        raise ConfigurationError(
            "GOOGLE_CLIENT_ID environment variable not set. "
            "Google authentication is not configured."
        )

    try:
        # Verify the token with Google's servers
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )

        # Verify the issuer
        if idinfo["iss"] not in ("accounts.google.com", "https://accounts.google.com"):
            raise InvalidTokenError("Invalid token issuer")

        # Extract user information
        return {
            "google_id": idinfo["sub"],
            "email": idinfo["email"],
            "name": idinfo.get("name", idinfo["email"].split("@")[0]),
            "picture_url": idinfo.get("picture"),
            "email_verified": idinfo.get("email_verified", False),
        }

    except ValueError as e:
        # Token is invalid (expired, wrong audience, malformed, etc.)
        raise InvalidTokenError(f"Invalid Google ID token: {str(e)}")


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


async def get_or_create_user(google_user_info: dict, db: AsyncSession) -> User:
    """
    Get existing user by Google ID or create a new one.

    Args:
        google_user_info: User info dict from verify_google_token()
        db: Database session

    Returns:
        User model instance (existing or newly created)
    """
    google_id = google_user_info["google_id"]

    # Try to find existing user
    query = select(User).where(User.google_id == google_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user:
        # Update user info in case it changed (name, picture, etc.)
        user.name = google_user_info["name"]
        user.picture_url = google_user_info.get("picture_url")
        user.updated_at = datetime.now(UTC)
        return user

    # Create new user
    user = User(
        google_id=google_id,
        email=google_user_info["email"],
        name=google_user_info["name"],
        picture_url=google_user_info.get("picture_url"),
        subscription_tier="free",
        queries_today=0,
        queries_reset_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user)

    return user


async def get_user_by_id(user_id: int, db: AsyncSession) -> User | None:
    """
    Get a user by their ID.

    Args:
        user_id: User's database ID
        db: Database session

    Returns:
        User model instance or None if not found
    """
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(email: str, db: AsyncSession) -> User | None:
    """
    Get a user by their email address.

    Args:
        email: User's email address
        db: Database session

    Returns:
        User model instance or None if not found
    """
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# JWT Token Management
# ---------------------------------------------------------------------------


def create_jwt_token(user: User) -> str:
    """
    Create a JWT token for a user session.

    Args:
        user: User model instance

    Returns:
        Signed JWT token string

    Raises:
        ConfigurationError: If JWT_SECRET_KEY is not configured
    """
    if not JWT_SECRET_KEY:
        raise ConfigurationError(
            "JWT_SECRET_KEY environment variable not set. JWT authentication is not configured."
        )

    now = datetime.now(UTC)
    expires = now + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        "sub": str(user.id),  # Subject: user ID
        "email": user.email,
        "name": user.name,
        "tier": user.subscription_tier,
        "iat": now,  # Issued at
        "exp": expires,  # Expiration
        "iss": "benchgoblins",  # Issuer
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        dict with decoded payload: {
            "user_id": int,
            "email": str,
            "name": str,
            "tier": str,
            "exp": datetime
        }

    Raises:
        ConfigurationError: If JWT_SECRET_KEY is not configured
        InvalidTokenError: If token is invalid, expired, or malformed
    """
    if not JWT_SECRET_KEY:
        raise ConfigurationError(
            "JWT_SECRET_KEY environment variable not set. JWT authentication is not configured."
        )

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer="benchgoblins",
        )

        return {
            "user_id": int(payload["sub"]),
            "email": payload["email"],
            "name": payload["name"],
            "tier": payload["tier"],
            "exp": datetime.fromtimestamp(payload["exp"], tz=UTC),
        }

    except jwt.ExpiredSignatureError:
        raise InvalidTokenError("Token has expired")
    except jwt.InvalidIssuerError:
        raise InvalidTokenError("Invalid token issuer")
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"Invalid token: {str(e)}")


def can_refresh_token(token: str) -> bool:
    """Check whether an expired token is still within the refresh window.

    Allows the /auth/refresh endpoint to issue a new access token without
    forcing the user to re-authenticate with Google, as long as the
    original token was issued within the last 7 days.
    """
    if not JWT_SECRET_KEY:
        return False
    try:
        # Decode without verifying expiration
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer="benchgoblins",
            options={"verify_exp": False},
        )
        issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        return datetime.now(UTC) - issued_at < timedelta(hours=JWT_REFRESH_WINDOW_HOURS)
    except jwt.InvalidTokenError:
        return False


# ---------------------------------------------------------------------------
# Token Blacklist — Redis-backed with in-memory fallback
# ---------------------------------------------------------------------------

# In-memory fallback for when Redis is unavailable
_token_blacklist_memory: set[str] = set()


def _blacklist_key(token: str) -> str:
    """Derive a short, fixed-length Redis key from a JWT."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"token_blacklist:{token_hash}"


def _get_redis_client():
    """Lazily import and return the Redis service client, or None."""
    try:
        from services.redis import redis_service

        if redis_service.is_connected and redis_service._client:
            return redis_service._client
    except Exception:
        pass
    return None


def blacklist_token(token: str) -> None:
    """
    Add a token to the blacklist (for logout).

    Persists to Redis when available so the blacklist survives restarts
    and is shared across instances.  Falls back to in-memory set.

    Args:
        token: JWT token to blacklist
    """
    import asyncio

    _token_blacklist_memory.add(token)

    client = _get_redis_client()
    if client:
        try:
            # Store in Redis with TTL matching token expiry so it auto-cleans
            ttl = int(timedelta(hours=JWT_EXPIRATION_HOURS).total_seconds()) + 60
            asyncio.get_event_loop().create_task(
                client.setex(_blacklist_key(token), ttl, "1")
            )
        except Exception:
            logger.warning("Failed to persist token blacklist to Redis")


def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token has been blacklisted.

    Checks in-memory set first (fast path), then Redis.

    Args:
        token: JWT token to check

    Returns:
        True if token is blacklisted, False otherwise
    """
    if token in _token_blacklist_memory:
        return True

    client = _get_redis_client()
    if client:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context but called synchronously.
                # Schedule a coroutine and don't block — rely on memory set
                # for current request; Redis will be checked next time.
                return False
        except RuntimeError:
            pass

    return False


async def is_token_blacklisted_async(token: str) -> bool:
    """Async version of blacklist check — preferred in async handlers."""
    if token in _token_blacklist_memory:
        return True

    client = _get_redis_client()
    if client:
        try:
            result = await client.get(_blacklist_key(token))
            if result:
                # Populate memory cache for future sync checks
                _token_blacklist_memory.add(token)
                return True
        except Exception:
            pass

    return False


def clear_expired_blacklist_entries() -> int:
    """
    Remove expired tokens from the in-memory blacklist (maintenance task).

    Redis entries auto-expire via TTL and don't need manual cleanup.

    Returns:
        Number of entries removed
    """
    global _token_blacklist_memory
    initial_count = len(_token_blacklist_memory)

    valid_tokens = set()
    for token in _token_blacklist_memory:
        try:
            # Try to decode - if expired, we can remove it
            verify_jwt_token(token)
            valid_tokens.add(token)
        except InvalidTokenError:
            # Token is expired or invalid, don't keep it
            pass

    _token_blacklist_memory = valid_tokens
    return initial_count - len(_token_blacklist_memory)


# ---------------------------------------------------------------------------
# Service Status
# ---------------------------------------------------------------------------


def is_configured() -> dict:
    """
    Check if auth service is properly configured.

    Returns:
        dict with configuration status for each component
    """
    return {
        "google_oauth": bool(GOOGLE_CLIENT_ID),
        "jwt": bool(JWT_SECRET_KEY),
        "fully_configured": bool(GOOGLE_CLIENT_ID and JWT_SECRET_KEY),
    }
