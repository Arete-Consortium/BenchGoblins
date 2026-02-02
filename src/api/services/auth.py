"""
Google OAuth Authentication Service.

Handles Google ID token verification, user management, and JWT session tokens.

Environment Variables:
    GOOGLE_CLIENT_ID: Google OAuth 2.0 Client ID
    JWT_SECRET_KEY: Secret key for signing JWT tokens (min 32 characters recommended)
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Optional

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import User

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days


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


async def get_user_by_id(user_id: int, db: AsyncSession) -> Optional[User]:
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


async def get_user_by_email(email: str, db: AsyncSession) -> Optional[User]:
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
            "JWT_SECRET_KEY environment variable not set. "
            "JWT authentication is not configured."
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
            "JWT_SECRET_KEY environment variable not set. "
            "JWT authentication is not configured."
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


# ---------------------------------------------------------------------------
# Token Blacklist (for logout)
# ---------------------------------------------------------------------------

# In-memory blacklist for revoked tokens
# In production, use Redis or database for persistence across restarts
_token_blacklist: set[str] = set()


def blacklist_token(token: str) -> None:
    """
    Add a token to the blacklist (for logout).

    Args:
        token: JWT token to blacklist
    """
    _token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token has been blacklisted.

    Args:
        token: JWT token to check

    Returns:
        True if token is blacklisted, False otherwise
    """
    return token in _token_blacklist


def clear_expired_blacklist_entries() -> int:
    """
    Remove expired tokens from the blacklist (maintenance task).

    Returns:
        Number of entries removed
    """
    global _token_blacklist
    initial_count = len(_token_blacklist)

    valid_tokens = set()
    for token in _token_blacklist:
        try:
            # Try to decode - if expired, we can remove it
            verify_jwt_token(token)
            valid_tokens.add(token)
        except InvalidTokenError:
            # Token is expired or invalid, don't keep it
            pass

    _token_blacklist = valid_tokens
    return initial_count - len(_token_blacklist)


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
