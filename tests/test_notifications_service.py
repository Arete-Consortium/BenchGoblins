"""Tests for notification service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.notifications import (
    NotificationService,
    NotificationType,
    PushNotification,
)


@pytest.fixture
def svc():
    return NotificationService()


class TestNotificationType:
    def test_enum_values(self):
        assert NotificationType.INJURY == "injury"
        assert NotificationType.LINEUP_REMINDER == "lineup_reminder"
        assert NotificationType.DECISION_UPDATE == "decision_update"
        assert NotificationType.TRENDING_PLAYER == "trending_player"


class TestPushNotification:
    def test_defaults(self):
        n = PushNotification(to="token", title="Title", body="Body")
        assert n.sound == "default"
        assert n.priority == "high"
        assert n.channel_id == "default"
        assert n.badge is None
        assert n.data is None

    def test_with_data(self):
        n = PushNotification(
            to="token", title="T", body="B", data={"key": "val"}, badge=3
        )
        assert n.data == {"key": "val"}
        assert n.badge == 3


class TestTokenManagement:
    def test_register_token(self, svc):
        svc.register_token("tok1", user_id="user1")
        assert "tok1" in svc.get_all_tokens()

    def test_unregister_token(self, svc):
        svc.register_token("tok1")
        svc.unregister_token("tok1")
        assert "tok1" not in svc.get_all_tokens()

    def test_unregister_nonexistent(self, svc):
        svc.unregister_token("nonexistent")  # Should not raise

    def test_get_user_tokens(self, svc):
        svc.register_token("tok1", user_id="user1")
        svc.register_token("tok2", user_id="user2")
        svc.register_token("tok3", user_id="user1")
        assert set(svc.get_user_tokens("user1")) == {"tok1", "tok3"}
        assert svc.get_user_tokens("user2") == ["tok2"]
        assert svc.get_user_tokens("user3") == []

    def test_get_all_tokens(self, svc):
        svc.register_token("a")
        svc.register_token("b")
        assert set(svc.get_all_tokens()) == {"a", "b"}


class TestSendNotification:
    @pytest.mark.asyncio
    async def test_send_single(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        n = PushNotification(to="tok", title="T", body="B")
        result = await svc.send_notification(n)
        assert result == {"data": [{"status": "ok"}]}

    @pytest.mark.asyncio
    async def test_send_with_data_and_badge(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        n = PushNotification(to="tok", title="T", body="B", data={"x": 1}, badge=5)
        await svc.send_notification(n)

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["data"] == {"x": 1}
        assert payload["badge"] == 5

    @pytest.mark.asyncio
    async def test_send_batch_empty(self, svc):
        result = await svc.send_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_send_batch(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}, {"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        notifications = [
            PushNotification(to="tok1", title="T1", body="B1"),
            PushNotification(to="tok2", title="T2", body="B2"),
        ]
        result = await svc.send_batch(notifications)
        assert len(result) == 2


class TestNotificationTemplates:
    @pytest.mark.asyncio
    async def test_send_injury_alert(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        await svc.send_injury_alert(
            tokens=["tok1"],
            player_name="LeBron James",
            injury_status="Questionable",
            player_id="123",
        )
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload[0]["title"] == "Injury Alert: LeBron James"
        assert payload[0]["channelId"] == "injuries"

    @pytest.mark.asyncio
    async def test_send_lineup_reminder(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        await svc.send_lineup_reminder(
            tokens=["tok1"], sport="nba", lock_time="7:00 PM ET"
        )
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "NBA" in payload[0]["title"]
        assert payload[0]["channelId"] == "reminders"

    @pytest.mark.asyncio
    async def test_send_decision_update(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        await svc.send_decision_update(
            tokens=["tok1"],
            player_name="Mahomes",
            update_reason="Injury update",
        )
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "Mahomes" in payload[0]["body"]

    @pytest.mark.asyncio
    async def test_send_to_all_no_tokens(self, svc):
        result = await svc.send_to_all("Title", "Body")
        assert result == []

    @pytest.mark.asyncio
    async def test_send_to_all_with_tokens(self, svc):
        svc.register_token("tok1")
        svc.register_token("tok2")

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"status": "ok"}, {"status": "ok"}]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        svc._client = mock_client

        result = await svc.send_to_all("Title", "Body", data={"key": "val"})
        assert len(result) == 2


class TestClose:
    @pytest.mark.asyncio
    async def test_close_with_client(self, svc):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        svc._client = mock_client
        await svc.close()
        mock_client.aclose.assert_called_once()
        assert svc._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self, svc):
        await svc.close()  # Should not raise
