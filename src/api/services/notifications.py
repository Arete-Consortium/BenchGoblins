"""
Push Notification Service — Sends notifications via Expo Push API.

Uses Expo's push notification service for cross-platform delivery.
In production, this could be replaced with Firebase Cloud Messaging directly.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import httpx

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


@dataclass
class DeviceToken:
    """Registered device for push notifications."""

    token: str
    user_id: str | None
    created_at: datetime
    preferences: dict | None = None


class NotificationService:
    """
    Push notification service using Expo's Push API.

    Supports:
    - Sending single notifications
    - Sending batch notifications
    - Device token management
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        # In-memory token storage (should be database in production)
        self._tokens: dict[str, DeviceToken] = {}

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
    # Token Management
    # =========================================================================

    def register_token(self, token: str, user_id: str | None = None) -> None:
        """Register a device token for push notifications."""
        self._tokens[token] = DeviceToken(
            token=token,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )

    def unregister_token(self, token: str) -> None:
        """Unregister a device token."""
        if token in self._tokens:
            del self._tokens[token]

    def get_all_tokens(self) -> list[str]:
        """Get all registered tokens."""
        return list(self._tokens.keys())

    def get_user_tokens(self, user_id: str) -> list[str]:
        """Get tokens for a specific user."""
        return [
            dt.token for dt in self._tokens.values() if dt.user_id == user_id
        ]

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
        title: str,
        body: str,
        data: dict | None = None,
    ) -> list[dict]:
        """Send notification to all registered devices."""
        tokens = self.get_all_tokens()

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
