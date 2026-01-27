"""
Session Management API Routes.

Handles session creation, validation, refresh, and revocation.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.database import db_service
from services.session import session_service

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    platform: str = Field(..., description="Client platform: 'ios', 'android', or 'web'")
    device_id: str | None = Field(None, description="Unique device identifier")
    device_name: str | None = Field(None, description="Human-readable device name")


class SessionResponse(BaseModel):
    """Session information response."""

    session_id: str
    platform: str
    device_id: str | None
    device_name: str | None
    status: str
    created_at: str
    expires_at: str
    last_active_at: str
    credentials: dict[str, dict] = Field(default_factory=dict)


class SessionCreatedResponse(SessionResponse):
    """Response after creating a session - includes token."""

    session_token: str = Field(..., description="Session token (only returned on creation)")


class CredentialStatusResponse(BaseModel):
    """Status of connected credentials."""

    espn: dict | None = None
    yahoo: dict | None = None
    sleeper: dict | None = None


# -------------------------------------------------------------------------
# Dependencies
# -------------------------------------------------------------------------


async def get_session_token(
    x_session_token: Annotated[str | None, Header()] = None,
    session_id: str | None = Query(
        default=None, description="Session token (deprecated, use header)"
    ),
) -> str:
    """Extract session token from header or query parameter."""
    token = x_session_token or session_id
    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Session token required."
                " Provide X-Session-Token header or session_id query parameter."
            ),
        )
    return token


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("", response_model=SessionCreatedResponse)
async def create_session(request: CreateSessionRequest, req: Request):
    """
    Create a new session.

    Returns a session token that must be included in subsequent requests
    via the `X-Session-Token` header or `session_id` query parameter.
    """
    if request.platform not in ("ios", "android", "web"):
        raise HTTPException(
            status_code=400,
            detail="Invalid platform. Must be 'ios', 'android', or 'web'.",
        )

    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Session management unavailable.",
        )

    # Extract client info from request
    ip_address = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")

    async with db_service.session() as db:
        session = await session_service.create_session(
            db=db,
            platform=request.platform,
            device_id=request.device_id,
            device_name=request.device_name,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return SessionCreatedResponse(
            session_id=str(session.id),
            session_token=session.session_token,
            platform=session.platform,
            device_id=session.device_id,
            device_name=session.device_name,
            status=session.status,
            created_at=session.created_at.isoformat(),
            expires_at=session.expires_at.isoformat(),
            last_active_at=session.last_active_at.isoformat(),
            credentials={},
        )


@router.get("/current", response_model=SessionResponse)
async def get_current_session(token: str = Depends(get_session_token)):
    """
    Get information about the current session.

    Validates the session and returns its details including credential status.
    """
    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Session management unavailable.",
        )

    async with db_service.session() as db:
        is_valid, session, error = await session_service.validate_session(db, token)

        if not is_valid:
            raise HTTPException(status_code=401, detail=error or "Invalid session")

        # Get credential status
        cred_status = await session_service.get_credential_status(db, session)

        return SessionResponse(
            session_id=str(session.id),
            platform=session.platform,
            device_id=session.device_id,
            device_name=session.device_name,
            status=session.status,
            created_at=session.created_at.isoformat(),
            expires_at=session.expires_at.isoformat(),
            last_active_at=session.last_active_at.isoformat(),
            credentials=cred_status,
        )


@router.post("/refresh", response_model=SessionResponse)
async def refresh_session(
    token: str = Depends(get_session_token),
    extend_days: int | None = Query(default=None, description="Days to extend (max 90)"),
):
    """
    Refresh/extend the current session's expiration.

    Can optionally specify number of days to extend (default: 30, max: 90).
    """
    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Session management unavailable.",
        )

    async with db_service.session() as db:
        is_valid, session, error = await session_service.validate_session(
            db, token, update_activity=False
        )

        if not is_valid:
            raise HTTPException(status_code=401, detail=error or "Invalid session")

        session = await session_service.refresh_session(db, session, extend_days)
        cred_status = await session_service.get_credential_status(db, session)

        return SessionResponse(
            session_id=str(session.id),
            platform=session.platform,
            device_id=session.device_id,
            device_name=session.device_name,
            status=session.status,
            created_at=session.created_at.isoformat(),
            expires_at=session.expires_at.isoformat(),
            last_active_at=session.last_active_at.isoformat(),
            credentials=cred_status,
        )


@router.delete("/current")
async def revoke_current_session(token: str = Depends(get_session_token)):
    """
    Revoke the current session.

    This invalidates the session token and removes all associated credentials.
    """
    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Session management unavailable.",
        )

    async with db_service.session() as db:
        session = await session_service.get_session_by_token(db, token, update_activity=False)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        await session_service.revoke_session(db, session)

        return {"status": "revoked", "session_id": str(session.id)}


@router.get("/validate")
async def validate_session(token: str = Depends(get_session_token)):
    """
    Validate a session token without fetching full session details.

    Useful for quick authentication checks.
    """
    if not db_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Database not configured. Session management unavailable.",
        )

    async with db_service.session() as db:
        is_valid, session, error = await session_service.validate_session(db, token)

        return {
            "valid": is_valid,
            "session_id": str(session.id) if session else None,
            "error": error,
            "expires_at": session.expires_at.isoformat() if session else None,
        }
