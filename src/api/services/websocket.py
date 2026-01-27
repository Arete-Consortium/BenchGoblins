"""
WebSocket Service — Real-time updates for live game data.

Provides:
- WebSocket connection management
- Live stat updates during games
- Injury alerts and lineup changes
- Broadcast to subscribed clients
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"

    # Server -> Client
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"
    STAT_UPDATE = "stat_update"
    INJURY_ALERT = "injury_alert"
    LINEUP_CHANGE = "lineup_change"
    GAME_START = "game_start"
    GAME_END = "game_end"
    ERROR = "error"


class ConnectionManager:
    """Manages WebSocket connections and subscriptions."""

    def __init__(self):
        # connection_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # connection_id -> set of subscribed topics
        self._subscriptions: dict[str, set[str]] = {}
        # topic -> set of connection_ids
        self._topic_subscribers: dict[str, set[str]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> str:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        connection_id = str(uuid4())

        async with self._lock:
            self._connections[connection_id] = websocket
            self._subscriptions[connection_id] = set()

        logger.info(f"WebSocket connected: {connection_id}")

        # Send welcome message
        await self._send(
            websocket,
            MessageType.CONNECTED,
            {"connection_id": connection_id},
        )

        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Handle WebSocket disconnection."""
        async with self._lock:
            # Remove from all subscribed topics
            if connection_id in self._subscriptions:
                for topic in self._subscriptions[connection_id]:
                    if topic in self._topic_subscribers:
                        self._topic_subscribers[topic].discard(connection_id)
                        if not self._topic_subscribers[topic]:
                            del self._topic_subscribers[topic]
                del self._subscriptions[connection_id]

            # Remove connection
            if connection_id in self._connections:
                del self._connections[connection_id]

        logger.info(f"WebSocket disconnected: {connection_id}")

    async def subscribe(self, connection_id: str, topic: str) -> bool:
        """Subscribe a connection to a topic."""
        async with self._lock:
            if connection_id not in self._connections:
                return False

            self._subscriptions[connection_id].add(topic)

            if topic not in self._topic_subscribers:
                self._topic_subscribers[topic] = set()
            self._topic_subscribers[topic].add(connection_id)

        logger.debug(f"Connection {connection_id} subscribed to {topic}")

        # Confirm subscription
        websocket = self._connections.get(connection_id)
        if websocket:
            await self._send(
                websocket,
                MessageType.SUBSCRIBED,
                {"topic": topic},
            )

        return True

    async def unsubscribe(self, connection_id: str, topic: str) -> bool:
        """Unsubscribe a connection from a topic."""
        async with self._lock:
            if connection_id not in self._subscriptions:
                return False

            self._subscriptions[connection_id].discard(topic)

            if topic in self._topic_subscribers:
                self._topic_subscribers[topic].discard(connection_id)
                if not self._topic_subscribers[topic]:
                    del self._topic_subscribers[topic]

        logger.debug(f"Connection {connection_id} unsubscribed from {topic}")

        # Confirm unsubscription
        websocket = self._connections.get(connection_id)
        if websocket:
            await self._send(
                websocket,
                MessageType.UNSUBSCRIBED,
                {"topic": topic},
            )

        return True

    async def broadcast_to_topic(
        self,
        topic: str,
        message_type: MessageType,
        data: dict[str, Any],
    ) -> int:
        """Broadcast a message to all subscribers of a topic."""
        async with self._lock:
            subscriber_ids = self._topic_subscribers.get(topic, set()).copy()

        sent_count = 0
        for connection_id in subscriber_ids:
            websocket = self._connections.get(connection_id)
            if websocket:
                try:
                    await self._send(websocket, message_type, data)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to {connection_id}: {e}")

        return sent_count

    async def broadcast_to_all(
        self,
        message_type: MessageType,
        data: dict[str, Any],
    ) -> int:
        """Broadcast a message to all connected clients."""
        async with self._lock:
            connection_ids = list(self._connections.keys())

        sent_count = 0
        for connection_id in connection_ids:
            websocket = self._connections.get(connection_id)
            if websocket:
                try:
                    await self._send(websocket, message_type, data)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to {connection_id}: {e}")

        return sent_count

    async def handle_message(self, connection_id: str, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == MessageType.PING:
                websocket = self._connections.get(connection_id)
                if websocket:
                    await self._send(websocket, MessageType.PONG, {})

            elif msg_type == MessageType.SUBSCRIBE:
                topic = data.get("topic")
                if topic:
                    await self.subscribe(connection_id, topic)
                else:
                    await self._send_error(connection_id, "Missing topic")

            elif msg_type == MessageType.UNSUBSCRIBE:
                topic = data.get("topic")
                if topic:
                    await self.unsubscribe(connection_id, topic)
                else:
                    await self._send_error(connection_id, "Missing topic")

            else:
                await self._send_error(connection_id, f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            await self._send_error(connection_id, "Invalid JSON")

    async def _send(
        self,
        websocket: WebSocket,
        message_type: MessageType,
        data: dict[str, Any],
    ) -> None:
        """Send a message to a WebSocket."""
        message = {
            "type": message_type.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }
        await websocket.send_json(message)

    async def _send_error(self, connection_id: str, error: str) -> None:
        """Send an error message to a connection."""
        websocket = self._connections.get(connection_id)
        if websocket:
            await self._send(websocket, MessageType.ERROR, {"error": error})

    def get_stats(self) -> dict[str, Any]:
        """Get connection manager statistics."""
        return {
            "connections": len(self._connections),
            "topics": len(self._topic_subscribers),
            "subscriptions": sum(len(s) for s in self._subscriptions.values()),
        }


# Global connection manager instance
connection_manager = ConnectionManager()


# =============================================================================
# Topic Helpers
# =============================================================================


def player_topic(sport: str, player_id: str) -> str:
    """Generate topic for player updates."""
    return f"player:{sport}:{player_id}"


def game_topic(sport: str, game_id: str) -> str:
    """Generate topic for game updates."""
    return f"game:{sport}:{game_id}"


def sport_topic(sport: str) -> str:
    """Generate topic for all updates in a sport."""
    return f"sport:{sport}"


def injury_topic() -> str:
    """Generate topic for all injury alerts."""
    return "injuries"


# =============================================================================
# Broadcast Helpers
# =============================================================================


async def broadcast_stat_update(
    sport: str,
    player_id: str,
    player_name: str,
    stats: dict[str, Any],
    game_id: str | None = None,
) -> None:
    """Broadcast a player stat update."""
    data = {
        "sport": sport,
        "player_id": player_id,
        "player_name": player_name,
        "stats": stats,
        "game_id": game_id,
    }

    # Send to player-specific subscribers
    await connection_manager.broadcast_to_topic(
        player_topic(sport, player_id),
        MessageType.STAT_UPDATE,
        data,
    )

    # Send to sport-wide subscribers
    await connection_manager.broadcast_to_topic(
        sport_topic(sport),
        MessageType.STAT_UPDATE,
        data,
    )

    # Send to game subscribers if applicable
    if game_id:
        await connection_manager.broadcast_to_topic(
            game_topic(sport, game_id),
            MessageType.STAT_UPDATE,
            data,
        )


async def broadcast_injury_alert(
    sport: str,
    player_id: str,
    player_name: str,
    team: str,
    injury_status: str,
    description: str,
) -> None:
    """Broadcast an injury alert."""
    data = {
        "sport": sport,
        "player_id": player_id,
        "player_name": player_name,
        "team": team,
        "injury_status": injury_status,
        "description": description,
    }

    # Send to player subscribers
    await connection_manager.broadcast_to_topic(
        player_topic(sport, player_id),
        MessageType.INJURY_ALERT,
        data,
    )

    # Send to injury topic
    await connection_manager.broadcast_to_topic(
        injury_topic(),
        MessageType.INJURY_ALERT,
        data,
    )

    # Send to sport-wide subscribers
    await connection_manager.broadcast_to_topic(
        sport_topic(sport),
        MessageType.INJURY_ALERT,
        data,
    )


async def broadcast_lineup_change(
    sport: str,
    team: str,
    changes: list[dict[str, Any]],
) -> None:
    """Broadcast lineup changes."""
    data = {
        "sport": sport,
        "team": team,
        "changes": changes,
    }

    await connection_manager.broadcast_to_topic(
        sport_topic(sport),
        MessageType.LINEUP_CHANGE,
        data,
    )


async def broadcast_game_event(
    sport: str,
    game_id: str,
    event_type: MessageType,
    home_team: str,
    away_team: str,
    score: dict[str, int] | None = None,
) -> None:
    """Broadcast game start/end events."""
    data = {
        "sport": sport,
        "game_id": game_id,
        "home_team": home_team,
        "away_team": away_team,
        "score": score,
    }

    await connection_manager.broadcast_to_topic(
        game_topic(sport, game_id),
        event_type,
        data,
    )

    await connection_manager.broadcast_to_topic(
        sport_topic(sport),
        event_type,
        data,
    )
