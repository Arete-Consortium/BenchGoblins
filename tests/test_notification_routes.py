"""Tests for notification API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


VALID_USER = {
    "user_id": 1,
    "email": "test@example.com",
    "name": "Test User",
    "tier": "pro",
    "exp": 9999999999,
}


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from api.main import app

    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def _mock_db_session():
    """Create a mock async db session context manager."""
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_session


class TestRegisterToken:
    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_register_token(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.register_token = AsyncMock()

        resp = authed_client.post(
            "/notifications/register", json={"token": "ExponentPushToken[abc123]"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["registered"] is True
        assert "..." in data["token"]
        mock_notif.register_token.assert_called_once()

    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_register_token_unauthenticated(self, mock_notif, mock_db, test_client):
        resp = test_client.post(
            "/notifications/register", json={"token": "ExponentPushToken[abc123]"}
        )
        assert resp.status_code in (401, 403)


class TestUnregisterToken:
    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_unregister_token(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.unregister_token = AsyncMock()

        resp = authed_client.request(
            "DELETE",
            "/notifications/register",
            json={"token": "ExponentPushToken[abc123]"},
        )
        assert resp.status_code == 200
        assert resp.json()["unregistered"] is True
        mock_notif.unregister_token.assert_called_once()


class TestGetPreferences:
    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_get_preferences_no_device(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.get_user_tokens = AsyncMock(return_value=[])

        # No device tokens found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = authed_client.get("/notifications/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["injury_alerts"] is True
        assert data["preferences"]["lineup_reminders"] is True
        assert data["preferences"]["decision_updates"] is False
        assert data["preferences"]["trending_players"] is False
        assert data["token_count"] == 0

    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_get_preferences_with_device(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.get_user_tokens = AsyncMock(return_value=["tok1", "tok2"])

        # Device with custom preferences
        mock_device = MagicMock()
        mock_device.preferences = {
            "injury_alerts": False,
            "lineup_reminders": True,
            "decision_updates": True,
            "trending_players": False,
        }
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        mock_session.execute = AsyncMock(return_value=mock_result)

        resp = authed_client.get("/notifications/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["injury_alerts"] is False
        assert data["preferences"]["decision_updates"] is True
        assert data["token_count"] == 2


class TestUpdatePreferences:
    @patch("routes.notifications.db_service")
    def test_update_preferences(self, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm

        # Two devices
        device1 = MagicMock()
        device1.preferences = {}
        device2 = MagicMock()
        device2.preferences = {}
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [device1, device2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        prefs = {
            "injury_alerts": True,
            "lineup_reminders": False,
            "decision_updates": True,
            "trending_players": True,
        }
        resp = authed_client.put("/notifications/preferences", json=prefs)
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferences"]["lineup_reminders"] is False
        assert data["preferences"]["trending_players"] is True
        assert data["token_count"] == 2

    @patch("routes.notifications.db_service")
    def test_update_preferences_no_devices(self, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        prefs = {
            "injury_alerts": True,
            "lineup_reminders": True,
            "decision_updates": False,
            "trending_players": False,
        }
        resp = authed_client.put("/notifications/preferences", json=prefs)
        assert resp.status_code == 200
        assert resp.json()["token_count"] == 0


class TestSendTestNotification:
    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_send_test_no_tokens(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.get_user_tokens = AsyncMock(return_value=[])

        resp = authed_client.post("/notifications/test", json={})
        assert resp.status_code == 404
        assert "No registered devices" in resp.json()["detail"]

    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_send_test_with_tokens(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.get_user_tokens = AsyncMock(return_value=["tok1", "tok2"])
        mock_notif.send_notification = AsyncMock(
            return_value={"data": [{"status": "ok"}]}
        )

        resp = authed_client.post(
            "/notifications/test",
            json={"title": "Hello", "body": "World"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] == 2
        assert len(data["results"]) == 2

    @patch("routes.notifications.db_service")
    @patch("routes.notifications.notification_service")
    def test_send_test_default_message(self, mock_notif, mock_db, authed_client):
        mock_cm, mock_session = _mock_db_session()
        mock_db.session.return_value = mock_cm
        mock_notif.get_user_tokens = AsyncMock(return_value=["tok1"])
        mock_notif.send_notification = AsyncMock(
            return_value={"data": [{"status": "ok"}]}
        )

        resp = authed_client.post("/notifications/test", json={})
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1
