"""
Push Notification Service — Sends notifications via Expo Push API.

Uses Expo's push notification service for cross-platform delivery.
Device tokens are persisted in the device_tokens table.
"""

from dataclasses import dataclass
from enum import Enum

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# Expo Push API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationType(str, Enum):
    """Types of notifications we send."""

    INJURY = "injury"
    LINEUP_REMINDER = "lineup_reminder"
    DECISION_UPDATE = "decision_update"
    TRENDING_PLAYER = "trending_player"


@dataclass
class PushNotification:
    """A push notification to be sent."""

    to: str  # Expo push token
    title: str
    body: str
    data: dict | None = None
    sound: str = "default"
    priority: str = "high"
    channel_id: str = "default"
    badge: int | None = None


class NotificationService:
    """
    Push notification service using Expo's Push API.

    Supports:
    - Sending single notifications
    - Sending batch notifications
    - Device token management (persisted to DB)
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # Token Management (DB-backed)
    # =========================================================================

    async def register_token(
        self, db: AsyncSession, token: str, user_id: str | None = None
    ) -> None:
        """Register a device token for push notifications."""
        from models.database import DeviceToken

        stmt = pg_insert(DeviceToken).values(token=token, user_id=user_id)
        stmt = stmt.on_conflict_do_update(
            index_elements=["token"],
            set_={"user_id": user_id},
        )
        await db.execute(stmt)

    async def unregister_token(self, db: AsyncSession, token: str) -> None:
        """Unregister a device token."""
        from models.database import DeviceToken

        await db.execute(delete(DeviceToken).where(DeviceToken.token == token))

    async def get_all_tokens(self, db: AsyncSession) -> list[str]:
        """Get all registered tokens."""
        from models.database import DeviceToken

        result = await db.execute(select(DeviceToken.token))
        return [row[0] for row in result.all()]

    async def get_user_tokens(self, db: AsyncSession, user_id: str) -> list[str]:
        """Get tokens for a specific user."""
        from models.database import DeviceToken

        result = await db.execute(select(DeviceToken.token).where(DeviceToken.user_id == user_id))
        return [row[0] for row in result.all()]

    # =========================================================================
    # Sending Notifications
    # =========================================================================

    async def send_notification(self, notification: PushNotification) -> dict:
        """
        Send a single push notification.

        Returns the Expo Push API response.
        """
        client = await self._get_client()

        payload = {
            "to": notification.to,
            "title": notification.title,
            "body": notification.body,
            "sound": notification.sound,
            "priority": notification.priority,
            "channelId": notification.channel_id,
        }

        if notification.data:
            payload["data"] = notification.data

        if notification.badge is not None:
            payload["badge"] = notification.badge

        try:
            response = await client.post(EXPO_PUSH_URL, json=payload)
            return response.json()
        except httpx.HTTPError as e:
            return {"error": str(e)}

    async def send_batch(self, notifications: list[PushNotification]) -> list[dict]:
        """
        Send multiple notifications in a batch.

        More efficient than sending individually.
        """
        if not notifications:
            return []

        client = await self._get_client()

        payloads = []
        for notification in notifications:
            payload = {
                "to": notification.to,
                "title": notification.title,
                "body": notification.body,
                "sound": notification.sound,
                "priority": notification.priority,
                "channelId": notification.channel_id,
            }

            if notification.data:
                payload["data"] = notification.data

            if notification.badge is not None:
                payload["badge"] = notification.badge

            payloads.append(payload)

        try:
            response = await client.post(EXPO_PUSH_URL, json=payloads)
            return response.json().get("data", [])
        except httpx.HTTPError as e:
            return [{"error": str(e)}]

    # =========================================================================
    # Notification Templates
    # =========================================================================

    async def send_injury_alert(
        self,
        tokens: list[str],
        player_name: str,
        injury_status: str,
        player_id: str,
    ) -> list[dict]:
        """Send injury alert notification to multiple devices."""
        notifications = [
            PushNotification(
                to=token,
                title=f"Injury Alert: {player_name}",
                body=f"{player_name} is now listed as {injury_status}",
                data={
                    "type": NotificationType.INJURY.value,
                    "playerId": player_id,
                    "status": injury_status,
                },
                channel_id="injuries",
                priority="high",
            )
            for token in tokens
        ]
        return await self.send_batch(notifications)

    async def send_lineup_reminder(
        self,
        tokens: list[str],
        sport: str,
        lock_time: str,
    ) -> list[dict]:
        """Send lineup lock reminder to multiple devices."""
        notifications = [
            PushNotification(
                to=token,
                title=f"{sport.upper()} Lineups Lock Soon",
                body=f"Lineups lock at {lock_time}. Make your final decisions!",
                data={
                    "type": NotificationType.LINEUP_REMINDER.value,
                    "sport": sport,
                    "lockTime": lock_time,
                },
                channel_id="reminders",
            )
            for token in tokens
        ]
        return await self.send_batch(notifications)

    async def send_decision_update(
        self,
        tokens: list[str],
        player_name: str,
        update_reason: str,
    ) -> list[dict]:
        """Send notification about decision update."""
        notifications = [
            PushNotification(
                to=token,
                title="Decision Update",
                body=f"Your pick {player_name} has an update: {update_reason}",
                data={
                    "type": NotificationType.DECISION_UPDATE.value,
                    "playerName": player_name,
                },
            )
            for token in tokens
        ]
        return await self.send_batch(notifications)

    async def send_to_all(
        self,
        db: AsyncSession,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> list[dict]:
        """Send notification to all registered devices."""
        tokens = await self.get_all_tokens(db)

        if not tokens:
            return []

        notifications = [
            PushNotification(
                to=token,
                title=title,
                body=body,
                data=data,
            )
            for token in tokens
        ]
        return await self.send_batch(notifications)


# Singleton instance
notification_service = NotificationService()
