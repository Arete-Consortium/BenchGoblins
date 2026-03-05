"""
Authentication API Routes.

Handles Google OAuth login, JWT session management, and user info retrieval.

Dependencies exported for use in other routes:
    - get_current_user: FastAPI dependency that validates JWT and returns user info
    - get_current_user_token: FastAPI dependency that extracts JWT from Authorization header

Usage in other routes:
    from routes.auth import get_current_user

    @router.get("/protected")
    async def protected_endpoint(current_user: dict = Depends(get_current_user)):
        # current_user contains: user_id, email, name, tier, exp
        return {"user_id": current_user["user_id"]}
"""

import asyncio
import logging
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from services.auth import (
    ConfigurationError,
    InvalidTokenError,
    blacklist_token,
    create_jwt_token,
    get_or_create_user,
    get_user_by_id,
    is_configured,
    is_token_blacklisted,
    verify_google_token,
    verify_jwt_token,
)
from services.database import db_service

logger = logging.getLogger(__name__)

__all__ = [
    "router",
    "get_current_user",
    "get_current_user_token",
    "get_optional_user",
    "require_admin_key",
    "require_pro",
]

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class GoogleAuthRequest(BaseModel):
    """Request to authenticate with Google ID token."""

    id_token: str = Field(
        ...,
        description="Google ID token from client-side authentication (e.g., @react-native-google-signin/google-signin)",
    )


class AuthResponse(BaseModel):
    """Response after successful authentication."""

    access_token: str = Field(..., description="JWT access token for API requests")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: "UserResponse"


class UserResponse(BaseModel):
    """User information response."""

    id: int
    email: str
    name: str
    picture_url: str | None
    subscription_tier: str
    queries_today: int
    queries_limit: int
    created_at: str


class AuthStatusResponse(BaseModel):
    """Authentication service status."""

    google_oauth_configured: bool
    jwt_configured: bool
    fully_configured: bool


def _queries_limit_for_tier(tier: str) -> int:
    """Return the weekly query limit for a subscription tier."""
    return -1 if tier == "pro" else 5


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_current_user_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Extract and validate JWT from Authorization header.

    Expects: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict | None:
    """Return current user if JWT provided, None if no header.

    Raises 401 if a token IS provided but is invalid/expired/blacklisted,
    so the client gets a clear signal to re-authenticate rather than
    silently falling back to anonymous.
    """
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1]
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_jwt_token(token)
    except ConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin_key(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Require a valid admin API key via X-Admin-Key header.

    Returns 503 if ADMIN_API_KEY env var is not configured (prevents
    accidental open access). Returns 403 if the key is missing or wrong.
    Uses secrets.compare_digest for timing-safe comparison.
    """
    admin_key = os.getenv("ADMIN_API_KEY")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin API key not configured")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, admin_key):
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")


async def get_current_user(token: str = Depends(get_current_user_token)) -> dict:
    """
    Validate JWT and return current user info.

    Use as dependency: current_user: dict = Depends(get_current_user)
    """
    # Check if token is blacklisted (logged out)
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verify_jwt_token(token)
    except ConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_pro(current_user: dict = Depends(get_current_user)) -> dict:
    """Require Pro subscription. Checks direct tier then league-inherited Pro.

    Use as dependency: current_user: dict = Depends(require_pro)
    Raises 403 if user is not on Pro tier.
    """
    from services import stripe_billing

    if not db_service.is_configured:
        raise HTTPException(status_code=503, detail="Database not configured")

    async with db_service.session() as session:
        user = await get_user_by_id(current_user["user_id"], session)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_pro = user.subscription_tier == "pro"
    if not is_pro:
        # Check referral-granted Pro
        if hasattr(user, "referral_pro_expires_at") and user.referral_pro_expires_at:
            from datetime import UTC, datetime

            if user.referral_pro_expires_at > datetime.now(UTC):
                is_pro = True
    if not is_pro:
        try:
            is_pro = await stripe_billing.is_league_pro(user.id)
        except Exception:
            pass

    if not is_pro:
        raise HTTPException(
            status_code=403,
            detail="This is a Pro feature. Upgrade to access.",
        )

    return current_user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status():
    """
    Check if authentication is properly configured.

    Useful for debugging deployment issues.
    """
    status = is_configured()
    return AuthStatusResponse(
        google_oauth_configured=status["google_oauth"],
        jwt_configured=status["jwt"],
        fully_configured=status["fully_configured"],
    )


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from Fly.io proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/google", response_model=AuthResponse)
async def authenticate_with_google(request: GoogleAuthRequest, req: Request):
    """
    Authenticate with Google ID token.

    The client should use Google Sign-In to obtain an ID token, then send it here.
    This endpoint will:
    1. Verify the Google ID token with Google's servers
    2. Create or update the user in our database
    3. Return a JWT access token for subsequent API requests

    Example flow:
    1. Client uses Google Sign-In SDK to authenticate user
    2. Client receives ID token from Google
    3. Client sends ID token to this endpoint
    4. Server returns JWT for use in Authorization header
    """
    # Rate limit login attempts by IP
    from services.rate_limiter import rate_limiter

    client_ip = _get_client_ip(req)
    allowed, retry_after = await rate_limiter.check_rate_limit(f"auth:{client_ip}")
    if not allowed:
        logger.warning("Auth rate limit exceeded for IP %s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Authentication unavailable.",
        )

    # Verify the Google ID token
    try:
        google_user_info = verify_google_token(request.id_token)
    except ConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except InvalidTokenError as e:
        logger.warning("Failed Google token verification from %s: %s", client_ip, e)
        raise HTTPException(status_code=401, detail=str(e))

    # Verify email is verified
    if not google_user_info.get("email_verified", False):
        raise HTTPException(
            status_code=401,
            detail="Email address not verified with Google",
        )

    # Get or create user in database
    async with db_service.session() as db:
        user = await get_or_create_user(google_user_info, db)
        # Flush to assign auto-generated id before reading it
        await db.flush()

        # Send welcome email for new users (no drip history = first login)
        if not user.drip_emails_sent:
            try:
                from services.email_drip import send_welcome

                asyncio.create_task(send_welcome(user.id, user.name, user.email))
            except Exception:
                pass  # Email is best-effort, never block auth

        # Create JWT token
        try:
            access_token = create_jwt_token(user)
        except ConfigurationError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Calculate expiration in seconds (7 days)
        expires_in = 7 * 24 * 60 * 60

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                picture_url=user.picture_url,
                subscription_tier=user.subscription_tier,
                queries_today=user.queries_today,
                queries_limit=_queries_limit_for_tier(user.subscription_tier),
                created_at=user.created_at.isoformat(),
            ),
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user's information.

    Requires valid JWT in Authorization header.
    """
    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. User lookup unavailable.",
        )

    async with db_service.session() as db:
        user = await get_user_by_id(current_user["user_id"], db)

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found. Account may have been deleted.",
            )

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            picture_url=user.picture_url,
            subscription_tier=user.subscription_tier,
            queries_today=user.queries_today,
            queries_limit=_queries_limit_for_tier(user.subscription_tier),
            created_at=user.created_at.isoformat(),
        )


@router.post("/logout")
async def logout(
    token: str = Depends(get_current_user_token),
    current_user: dict = Depends(get_current_user),
):
    """
    Logout the current user by invalidating their JWT.

    The token will be blacklisted and can no longer be used for authentication.
    Client should discard the token after calling this endpoint.
    """
    await blacklist_token(token)

    return {
        "status": "logged_out",
        "message": "Token has been revoked",
        "user_id": current_user["user_id"],
    }


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    req: Request,
    token: str = Depends(get_current_user_token),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a fresh JWT token.

    Use this to extend the session before the current token expires.
    The old token is blacklisted to prevent reuse.
    """
    # Rate limit refresh attempts by IP
    from services.rate_limiter import rate_limiter

    client_ip = _get_client_ip(req)
    allowed, retry_after = await rate_limiter.check_rate_limit(f"refresh:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many refresh attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Token refresh unavailable.",
        )

    async with db_service.session() as db:
        user = await get_user_by_id(current_user["user_id"], db)

        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found. Account may have been deleted.",
            )

        try:
            access_token = create_jwt_token(user)
        except ConfigurationError as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Blacklist the old token to prevent reuse
        await blacklist_token(token)

        expires_in = 7 * 24 * 60 * 60

        return AuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                picture_url=user.picture_url,
                subscription_tier=user.subscription_tier,
                queries_today=user.queries_today,
                queries_limit=_queries_limit_for_tier(user.subscription_tier),
                created_at=user.created_at.isoformat(),
            ),
        )
