"""Tests for WebSocket connection manager and helpers."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.websocket import (
    ConnectionManager,
    MessageType,
    broadcast_game_event,
    broadcast_injury_alert,
    broadcast_lineup_change,
    broadcast_stat_update,
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

    @pytest.mark.asyncio
    async def test_unsubscribe_missing_topic(self, mgr, mock_ws):
        """Line 218: UNSUBSCRIBE message without a topic field sends error."""
        conn_id = await mgr.connect(mock_ws)
        mock_ws.send_json.reset_mock()
        await mgr.handle_message(conn_id, json.dumps({"type": "unsubscribe"}))
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "error"
        assert "Missing topic" in msg["data"]["error"]


class TestBroadcastErrors:
    """Cover exception handling in broadcast_to_topic and broadcast_to_all."""

    @pytest.fixture
    def mgr(self):
        return ConnectionManager()

    @pytest.mark.asyncio
    async def test_broadcast_to_topic_send_failure(self, mgr):
        """Lines 169-170: send failure to a subscriber during topic broadcast."""
        ws_good = AsyncMock()
        ws_bad = AsyncMock()

        # Connect both normally (send_json works during connect/subscribe)
        conn_good = await mgr.connect(ws_good)
        conn_bad = await mgr.connect(ws_bad)
        await mgr.subscribe(conn_good, "topic1")
        await mgr.subscribe(conn_bad, "topic1")

        # Now make ws_bad fail on subsequent sends
        ws_bad.send_json = AsyncMock(side_effect=RuntimeError("connection lost"))
        ws_good.send_json.reset_mock()

        sent = await mgr.broadcast_to_topic(
            "topic1", MessageType.STAT_UPDATE, {"pts": 10}
        )
        # Only the good connection should count as sent
        assert sent == 1
        ws_good.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_all_send_failure(self, mgr):
        """Lines 190-191: send failure to a connection during broadcast_to_all."""
        ws_good = AsyncMock()
        ws_bad = AsyncMock()

        # Connect both normally
        await mgr.connect(ws_good)
        await mgr.connect(ws_bad)

        # Now make ws_bad fail on subsequent sends
        ws_bad.send_json = AsyncMock(side_effect=RuntimeError("connection lost"))
        ws_good.send_json.reset_mock()

        sent = await mgr.broadcast_to_all(MessageType.INJURY_ALERT, {"player": "X"})
        # Only the good connection should count
        assert sent == 1
        ws_good.send_json.assert_called_once()


class TestBroadcastStatUpdate:
    """Lines 297-321: broadcast_stat_update module-level helper."""

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_stat_update_without_game_id(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        await broadcast_stat_update(
            sport="nba",
            player_id="p1",
            player_name="LeBron",
            stats={"pts": 30},
        )

        expected_data = {
            "sport": "nba",
            "player_id": "p1",
            "player_name": "LeBron",
            "stats": {"pts": 30},
            "game_id": None,
        }

        assert mock_cm.broadcast_to_topic.call_count == 2
        calls = mock_cm.broadcast_to_topic.call_args_list

        # Call 1: player topic
        assert calls[0].args == (
            player_topic("nba", "p1"),
            MessageType.STAT_UPDATE,
            expected_data,
        )
        # Call 2: sport topic
        assert calls[1].args == (
            sport_topic("nba"),
            MessageType.STAT_UPDATE,
            expected_data,
        )

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_stat_update_with_game_id(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        await broadcast_stat_update(
            sport="nba",
            player_id="p1",
            player_name="LeBron",
            stats={"pts": 30},
            game_id="g42",
        )

        expected_data = {
            "sport": "nba",
            "player_id": "p1",
            "player_name": "LeBron",
            "stats": {"pts": 30},
            "game_id": "g42",
        }

        # 3 calls: player, sport, game
        assert mock_cm.broadcast_to_topic.call_count == 3
        calls = mock_cm.broadcast_to_topic.call_args_list

        assert calls[0].args == (
            player_topic("nba", "p1"),
            MessageType.STAT_UPDATE,
            expected_data,
        )
        assert calls[1].args == (
            sport_topic("nba"),
            MessageType.STAT_UPDATE,
            expected_data,
        )
        assert calls[2].args == (
            game_topic("nba", "g42"),
            MessageType.STAT_UPDATE,
            expected_data,
        )


class TestBroadcastInjuryAlert:
    """Lines 337-361: broadcast_injury_alert module-level helper."""

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_injury_alert(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        await broadcast_injury_alert(
            sport="nfl",
            player_id="p99",
            player_name="Derrick Henry",
            team="BAL",
            injury_status="questionable",
            description="Knee soreness",
        )

        expected_data = {
            "sport": "nfl",
            "player_id": "p99",
            "player_name": "Derrick Henry",
            "team": "BAL",
            "injury_status": "questionable",
            "description": "Knee soreness",
        }

        assert mock_cm.broadcast_to_topic.call_count == 3
        calls = mock_cm.broadcast_to_topic.call_args_list

        # Call 1: player topic
        assert calls[0].args == (
            player_topic("nfl", "p99"),
            MessageType.INJURY_ALERT,
            expected_data,
        )
        # Call 2: injury topic
        assert calls[1].args == (
            injury_topic(),
            MessageType.INJURY_ALERT,
            expected_data,
        )
        # Call 3: sport topic
        assert calls[2].args == (
            sport_topic("nfl"),
            MessageType.INJURY_ALERT,
            expected_data,
        )


class TestBroadcastLineupChange:
    """Lines 374-380: broadcast_lineup_change module-level helper."""

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_lineup_change(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        changes = [{"player": "Jones", "action": "benched"}]
        await broadcast_lineup_change(
            sport="nba",
            team="LAL",
            changes=changes,
        )

        expected_data = {
            "sport": "nba",
            "team": "LAL",
            "changes": changes,
        }

        mock_cm.broadcast_to_topic.assert_called_once_with(
            sport_topic("nba"),
            MessageType.LINEUP_CHANGE,
            expected_data,
        )


class TestBroadcastGameEvent:
    """Lines 396-410: broadcast_game_event module-level helper."""

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_game_event_without_score(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        await broadcast_game_event(
            sport="nba",
            game_id="g1",
            event_type=MessageType.GAME_START,
            home_team="LAL",
            away_team="BOS",
        )

        expected_data = {
            "sport": "nba",
            "game_id": "g1",
            "home_team": "LAL",
            "away_team": "BOS",
            "score": None,
        }

        assert mock_cm.broadcast_to_topic.call_count == 2
        calls = mock_cm.broadcast_to_topic.call_args_list

        # Call 1: game topic
        assert calls[0].args == (
            game_topic("nba", "g1"),
            MessageType.GAME_START,
            expected_data,
        )
        # Call 2: sport topic
        assert calls[1].args == (
            sport_topic("nba"),
            MessageType.GAME_START,
            expected_data,
        )

    @pytest.mark.asyncio
    @patch("services.websocket.connection_manager")
    async def test_broadcast_game_event_with_score(self, mock_cm):
        mock_cm.broadcast_to_topic = AsyncMock()

        score = {"home": 110, "away": 105}
        await broadcast_game_event(
            sport="nba",
            game_id="g1",
            event_type=MessageType.GAME_END,
            home_team="LAL",
            away_team="BOS",
            score=score,
        )

        expected_data = {
            "sport": "nba",
            "game_id": "g1",
            "home_team": "LAL",
            "away_team": "BOS",
            "score": score,
        }

        assert mock_cm.broadcast_to_topic.call_count == 2
        calls = mock_cm.broadcast_to_topic.call_args_list

        assert calls[0].args == (
            game_topic("nba", "g1"),
            MessageType.GAME_END,
            expected_data,
        )
        assert calls[1].args == (
            sport_topic("nba"),
            MessageType.GAME_END,
            expected_data,
        )
