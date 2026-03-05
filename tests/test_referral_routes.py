"""
Tests for referral API routes.

Covers: GET /referral/code, POST /referral/apply, GET /referral/stats,
auth required, and error handling.
"""

from unittest.mock import AsyncMock, patch

import pytest

_VALID_USER = {
    "user_id": 1,
    "name": "Test User",
    "email": "test@example.com",
    "tier": "pro",
    "exp": 9999999999,
}

_REFERRAL = "routes.referral"


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from api.main import app
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


class TestGetReferralCode:
    @patch(f"{_REFERRAL}.get_or_create_referral_code", new_callable=AsyncMock)
    def test_returns_code(self, mock_get_code, authed_client):
        mock_get_code.return_value = "ABC12345"
        resp = authed_client.get("/referral/code")
        assert resp.status_code == 200
        data = resp.json()
        assert data["referral_code"] == "ABC12345"
        assert "benchgoblins.com" in data["share_url"]

    def test_requires_auth(self, test_client):
        resp = test_client.get("/referral/code")
        assert resp.status_code == 401


class TestApplyReferral:
    @patch(f"{_REFERRAL}.apply_referral", new_callable=AsyncMock)
    def test_success(self, mock_apply, authed_client):
        mock_apply.return_value = {
            "success": True,
            "referrer_name": "Friend",
            "pro_days": 7,
        }
        resp = authed_client.post("/referral/apply", json={"code": "FRIEND12"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["pro_days"] == 7

    @patch(f"{_REFERRAL}.apply_referral", new_callable=AsyncMock)
    def test_invalid_code(self, mock_apply, authed_client):
        mock_apply.return_value = {"success": False, "error": "Invalid referral code"}
        resp = authed_client.post("/referral/apply", json={"code": "BADCODE1"})
        assert resp.status_code == 400

    def test_requires_auth(self, test_client):
        resp = test_client.post("/referral/apply", json={"code": "ABC12345"})
        assert resp.status_code == 401

    def test_short_code_rejected(self, authed_client):
        resp = authed_client.post("/referral/apply", json={"code": "AB"})
        assert resp.status_code == 422


class TestReferralStats:
    @patch(f"{_REFERRAL}.get_referral_stats", new_callable=AsyncMock)
    def test_returns_stats(self, mock_stats, authed_client):
        mock_stats.return_value = {
            "referral_code": "ABC12345",
            "total_referrals": 5,
            "pro_days_remaining": 3,
            "max_referrals": 50,
        }
        resp = authed_client.get("/referral/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_referrals"] == 5
        assert data["max_referrals"] == 50

    def test_requires_auth(self, test_client):
        resp = test_client.get("/referral/stats")
        assert resp.status_code == 401
