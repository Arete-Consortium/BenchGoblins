"""
Push Notification API Routes.

Handles device token registration, notification preferences,
and test notifications.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from models.database import DeviceToken
from routes.auth import get_current_user
from services.database import db_service
from services.notifications import PushNotification, notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class RegisterTokenRequest(BaseModel):
    """Request to register a push notification token."""

    token: str = Field(..., description="Expo push token or web push subscription")


class NotificationPreferences(BaseModel):
    """User notification preference settings."""

    injury_alerts: bool = True
    lineup_reminders: bool = True
    decision_updates: bool = False
    trending_players: bool = False


class PreferencesResponse(BaseModel):
    """Response with user's notification preferences."""

    preferences: NotificationPreferences
    token_count: int = 0


class TestNotificationRequest(BaseModel):
    """Request to send a test notification."""

    title: str = Field(default="Test Notification", description="Notification title")
    body: str = Field(default="This is a test from BenchGoblin!", description="Notification body")


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("/register")
async def register_token(
    request: RegisterTokenRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Register a device token for push notifications.

    Tokens are upserted — re-registering the same token updates the user association.
    """
    user_id = str(current_user["user_id"])

    async with db_service.session() as session:
        await notification_service.register_token(session, request.token, user_id)
        await session.commit()

    return {"registered": True, "token": request.token[:20] + "..."}


@router.delete("/register")
async def unregister_token(
    request: RegisterTokenRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Unregister a device token (stop receiving push notifications on this device).
    """
    async with db_service.session() as session:
        await notification_service.unregister_token(session, request.token)
        await session.commit()

    return {"unregistered": True}


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
):
    """
    Get the authenticated user's notification preferences.
    """
    user_id = str(current_user["user_id"])

    async with db_service.session() as session:
        # Get token count
        tokens = await notification_service.get_user_tokens(session, user_id)

        # Get preferences from the first device token (they share preferences)
        result = await session.execute(
            select(DeviceToken).where(DeviceToken.user_id == user_id).limit(1)
        )
        device = result.scalar_one_or_none()

    prefs = NotificationPreferences()
    if device and device.preferences:
        prefs = NotificationPreferences(**device.preferences)

    return PreferencesResponse(
        preferences=prefs,
        token_count=len(tokens),
    )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    prefs: NotificationPreferences,
    current_user: dict = Depends(get_current_user),
):
    """
    Update the authenticated user's notification preferences.

    Applies to all registered devices for this user.
    """
    user_id = str(current_user["user_id"])
    prefs_dict = prefs.model_dump()

    async with db_service.session() as session:
        result = await session.execute(select(DeviceToken).where(DeviceToken.user_id == user_id))
        devices = result.scalars().all()

        for device in devices:
            device.preferences = prefs_dict
            session.add(device)

        await session.commit()

    return PreferencesResponse(
        preferences=prefs,
        token_count=len(devices),
    )


@router.post("/test")
async def send_test_notification(
    request: TestNotificationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Send a test notification to all of the current user's registered devices.
    """
    user_id = str(current_user["user_id"])

    async with db_service.session() as session:
        tokens = await notification_service.get_user_tokens(session, user_id)

    if not tokens:
        raise HTTPException(
            status_code=404,
            detail="No registered devices. Register a push token first.",
        )

    results = []
    for token in tokens:
        result = await notification_service.send_notification(
            PushNotification(
                to=token,
                title=request.title,
                body=request.body,
                data={"type": "test"},
            )
        )
        results.append(result)

    return {"sent": len(tokens), "results": results}
