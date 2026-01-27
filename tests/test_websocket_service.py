"""Tests for WebSocket connection manager and helpers."""

import json
from unittest.mock import AsyncMock

import pytest

from services.websocket import (
    ConnectionManager,
    MessageType,
    game_topic,
    injury_topic,
    player_topic,
    sport_topic,
)


@pytest.fixture
def mgr():
    return ConnectionManager()


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestMessageType:
    def test_values(self):
        assert MessageType.SUBSCRIBE == "subscribe"
        assert MessageType.STAT_UPDATE == "stat_update"
        assert MessageType.PONG == "pong"
        assert MessageType.ERROR == "error"


class TestTopicHelpers:
    def test_player_topic(self):
        assert player_topic("nba", "123") == "player:nba:123"

    def test_game_topic(self):
        assert game_topic("nfl", "g1") == "game:nfl:g1"

    def test_sport_topic(self):
        assert sport_topic("mlb") == "sport:mlb"

    def test_injury_topic(self):
        assert injury_topic() == "injuries"


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        assert conn_id is not None
        assert mgr.connection_count == 1
        mock_ws.accept.assert_called_once()
        mock_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.disconnect(conn_id)
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent(self, mgr):
        await mgr.disconnect("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_subscribe(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        result = await mgr.subscribe(conn_id, "player:nba:123")
        assert result is True
        # Should have sent CONNECTED + SUBSCRIBED
        assert mock_ws.send_json.call_count == 2

    @pytest.mark.asyncio
    async def test_subscribe_nonexistent_connection(self, mgr):
        result = await mgr.subscribe("fake", "topic")
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribe(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.subscribe(conn_id, "topic1")
        result = await mgr.unsubscribe(conn_id, "topic1")
        assert result is True

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(self, mgr):
        result = await mgr.unsubscribe("fake", "topic")
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_topic(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.subscribe(conn_id, "topic1")
        mock_ws.send_json.reset_mock()

        sent = await mgr.broadcast_to_topic(
            "topic1", MessageType.STAT_UPDATE, {"pts": 30}
        )
        assert sent == 1
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "stat_update"
        assert msg["data"]["pts"] == 30

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_topic(self, mgr):
        sent = await mgr.broadcast_to_topic("empty", MessageType.STAT_UPDATE, {})
        assert sent == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, mgr):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        sent = await mgr.broadcast_to_all(MessageType.INJURY_ALERT, {"player": "X"})
        assert sent == 2

    @pytest.mark.asyncio
    async def test_disconnect_cleans_subscriptions(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.subscribe(conn_id, "topic1")
        await mgr.subscribe(conn_id, "topic2")
        await mgr.disconnect(conn_id)
        # Topic subscribers should be cleaned
        assert "topic1" not in mgr._topic_subscribers
        assert "topic2" not in mgr._topic_subscribers

    @pytest.mark.asyncio
    async def test_get_stats(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.subscribe(conn_id, "topic1")
        stats = mgr.get_stats()
        assert stats["connections"] == 1
        assert stats["topics"] == 1
        assert stats["subscriptions"] == 1


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_ping(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        mock_ws.send_json.reset_mock()
        await mgr.handle_message(conn_id, json.dumps({"type": "ping"}))
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "pong"

    @pytest.mark.asyncio
    async def test_subscribe_message(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.handle_message(
            conn_id, json.dumps({"type": "subscribe", "topic": "t1"})
        )
        assert "t1" in mgr._subscriptions[conn_id]

    @pytest.mark.asyncio
    async def test_subscribe_missing_topic(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        mock_ws.send_json.reset_mock()
        await mgr.handle_message(conn_id, json.dumps({"type": "subscribe"}))
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_unsubscribe_message(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        await mgr.subscribe(conn_id, "t1")
        await mgr.handle_message(
            conn_id, json.dumps({"type": "unsubscribe", "topic": "t1"})
        )
        assert "t1" not in mgr._subscriptions.get(conn_id, set())

    @pytest.mark.asyncio
    async def test_unknown_type(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        mock_ws.send_json.reset_mock()
        await mgr.handle_message(conn_id, json.dumps({"type": "unknown_type"}))
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_json(self, mgr, mock_ws):
        conn_id = await mgr.connect(mock_ws)
        mock_ws.send_json.reset_mock()
        await mgr.handle_message(conn_id, "not json{{{")
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Invalid JSON" in msg["data"]["error"]
