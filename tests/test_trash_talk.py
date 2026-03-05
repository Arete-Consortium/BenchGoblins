"""
Tests for the Goblin trash talk generator endpoint.

Covers: request validation, Claude integration, JSON parsing,
error handling, and response structure.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

_VALID_USER = {
    "user_id": 1,
    "name": "Test User",
    "email": "test@example.com",
    "tier": "pro",
    "exp": 9999999999,
}

_CLAUDE = "services.claude.claude_service"


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def _make_claude_response(data: dict) -> MagicMock:
    """Build a mock Claude API response."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=json.dumps(data))]
    return mock_resp


# =============================================================================
# AUTH
# =============================================================================


class TestTrashTalkAuth:
    """Test authentication requirements."""

    def test_requires_auth(self, test_client):
        resp = test_client.post(
            "/goblin/trash-talk",
            json={"opponent_name": "Taco Team"},
        )
        assert resp.status_code in (401, 403)


# =============================================================================
# REQUEST VALIDATION
# =============================================================================


class TestTrashTalkValidation:
    """Test request body validation."""

    def test_requires_opponent_name(self, authed_client):
        resp = authed_client.post("/goblin/trash-talk", json={})
        assert resp.status_code == 422

    def test_spice_level_range(self, authed_client):
        resp = authed_client.post(
            "/goblin/trash-talk",
            json={"opponent_name": "Team X", "spice_level": 5},
        )
        assert resp.status_code == 422

    def test_spice_level_min(self, authed_client):
        resp = authed_client.post(
            "/goblin/trash-talk",
            json={"opponent_name": "Team X", "spice_level": 0},
        )
        assert resp.status_code == 422


# =============================================================================
# CLAUDE UNAVAILABLE
# =============================================================================


class TestTrashTalkClaudeUnavailable:
    """Test behavior when Claude is not available."""

    def test_returns_503_when_claude_unavailable(self, authed_client):
        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = False
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Taco Team"},
            )
        assert resp.status_code == 503
        assert "sleeping" in resp.json()["detail"].lower()


# =============================================================================
# SUCCESSFUL GENERATION
# =============================================================================


class TestTrashTalkGeneration:
    """Test successful trash talk generation."""

    def test_generates_trash_talk(self, authed_client):
        talk_data = {
            "lines": [
                "Your roster is a dumpster fire.",
                "Even your bye week players outscore your starters.",
                "The waiver wire is embarrassed you exist.",
            ],
            "gif_search_term": "dumpster fire",
        }

        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_claude.client.messages.create = AsyncMock(
                return_value=_make_claude_response(talk_data)
            )
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Taco Team", "spice_level": 3},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 3
        assert data["spice_level"] == 3
        assert data["gif_search_term"] == "dumpster fire"

    def test_caps_lines_at_5(self, authed_client):
        talk_data = {
            "lines": [f"Line {i}" for i in range(8)],
            "gif_search_term": "roasted",
        }

        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_claude.client.messages.create = AsyncMock(
                return_value=_make_claude_response(talk_data)
            )
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Team X"},
            )

        assert resp.status_code == 200
        assert len(resp.json()["lines"]) == 5

    def test_default_spice_level_is_2(self, authed_client):
        talk_data = {"lines": ["Burn."], "gif_search_term": "fire"}

        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_claude.client.messages.create = AsyncMock(
                return_value=_make_claude_response(talk_data)
            )
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Team X"},
            )

        assert resp.status_code == 200
        assert resp.json()["spice_level"] == 2

    def test_handles_context(self, authed_client):
        talk_data = {"lines": ["Context burn."], "gif_search_term": "boom"}

        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_claude.client.messages.create = AsyncMock(
                return_value=_make_claude_response(talk_data)
            )
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={
                    "opponent_name": "Rival Team",
                    "context": "They beat me by 0.5 last week",
                    "spice_level": 3,
                },
            )

        assert resp.status_code == 200

    def test_handles_markdown_fenced_json(self, authed_client):
        talk_data = {"lines": ["Fenced burn."], "gif_search_term": "fence"}
        fenced = f"```json\n{json.dumps(talk_data)}\n```"

        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text=fenced)]
            mock_claude.client.messages.create = AsyncMock(return_value=mock_resp)
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Team X"},
            )

        assert resp.status_code == 200
        assert resp.json()["lines"] == ["Fenced burn."]


# =============================================================================
# ERROR HANDLING
# =============================================================================


class TestTrashTalkErrors:
    """Test error handling in trash talk generation."""

    def test_invalid_json_from_claude(self, authed_client):
        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_resp = MagicMock()
            mock_resp.content = [MagicMock(text="not json at all")]
            mock_claude.client.messages.create = AsyncMock(return_value=mock_resp)
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Team X"},
            )

        assert resp.status_code == 500
        assert "incoherent" in resp.json()["detail"].lower()

    def test_claude_api_error(self, authed_client):
        with patch(_CLAUDE) as mock_claude:
            mock_claude.is_available = True
            mock_claude.client.messages.create = AsyncMock(
                side_effect=RuntimeError("API error")
            )
            resp = authed_client.post(
                "/goblin/trash-talk",
                json={"opponent_name": "Team X"},
            )

        assert resp.status_code == 500
        assert "choked" in resp.json()["detail"].lower()
