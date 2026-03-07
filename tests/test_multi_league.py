"""
Tests for multi-league support.

Covers: GET /leagues/all aggregation endpoint, _resolve_managed_league_context
helper for /decide league_id injection.
"""

from datetime import UTC, datetime
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


def _make_mock_user(
    sleeper=False,
    espn=False,
    yahoo=False,
):
    """Build a mock User with optional platform connections."""
    user = MagicMock()
    user.id = 1

    # Sleeper
    user.sleeper_league_id = "sl_123" if sleeper else None
    user.sleeper_user_id = "su_1" if sleeper else None
    user.sleeper_username = "sleeperuser" if sleeper else None
    user.roster_snapshot = (
        [
            {
                "full_name": "Patrick Mahomes",
                "position": "QB",
                "team": "KC",
                "is_starter": True,
            }
        ]
        if sleeper
        else None
    )
    user.sleeper_synced_at = datetime(2026, 3, 1, tzinfo=UTC) if sleeper else None

    # ESPN
    user.espn_league_id = "espn_456" if espn else None
    user.espn_team_id = "1" if espn else None
    user.espn_sport = "nfl" if espn else None
    user.espn_roster_snapshot = (
        [
            {
                "name": "Josh Allen",
                "position": "QB",
                "team": "BUF",
                "lineup_slot": "STARTER",
            }
        ]
        if espn
        else None
    )
    user.espn_synced_at = datetime(2026, 3, 2, tzinfo=UTC) if espn else None

    # Yahoo
    user.yahoo_league_key = "449.l.12345" if yahoo else None
    user.yahoo_team_key = "449.l.12345.t.1" if yahoo else None
    user.yahoo_sport = "nfl" if yahoo else None
    user.yahoo_roster_snapshot = (
        [{"name": "Lamar Jackson", "position": "QB", "team": "BAL", "status": "Active"}]
        if yahoo
        else None
    )
    user.yahoo_synced_at = datetime(2026, 3, 3, tzinfo=UTC) if yahoo else None

    return user


def _mock_db_for_user(mock_user):
    """Create a mock db_service.session context that returns mock_user on execute."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.session.return_value = mock_ctx
    mock_db.is_configured = True
    return mock_db


# =============================================================================
# GET /leagues/all
# =============================================================================


class TestGetAllLeagues:
    """Tests for the multi-league aggregation endpoint."""

    @patch("routes.leagues.db_service")
    def test_all_platforms_connected(self, mock_db_svc, authed_client):
        user = _make_mock_user(sleeper=True, espn=True, yahoo=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        platforms = {lg["platform"] for lg in data["leagues"]}
        assert platforms == {"sleeper", "espn", "yahoo"}

    @patch("routes.leagues.db_service")
    def test_no_platforms_connected(self, mock_db_svc, authed_client):
        user = _make_mock_user()
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["leagues"] == []

    @patch("routes.leagues.db_service")
    def test_only_sleeper_connected(self, mock_db_svc, authed_client):
        user = _make_mock_user(sleeper=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["leagues"][0]["platform"] == "sleeper"
        assert data["leagues"][0]["league_id"] == "sl_123"
        assert data["leagues"][0]["roster_player_count"] == 1

    @patch("routes.leagues.db_service")
    def test_only_espn_connected(self, mock_db_svc, authed_client):
        user = _make_mock_user(espn=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["leagues"][0]["platform"] == "espn"
        assert data["leagues"][0]["sport"] == "nfl"

    @patch("routes.leagues.db_service")
    def test_only_yahoo_connected(self, mock_db_svc, authed_client):
        user = _make_mock_user(yahoo=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["leagues"][0]["platform"] == "yahoo"
        assert data["leagues"][0]["league_id"] == "449.l.12345"

    @patch("routes.leagues.db_service")
    def test_user_not_found_returns_404(self, mock_db_svc, authed_client):
        db = _mock_db_for_user(None)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        assert response.status_code == 404

    @patch("routes.leagues.db_service")
    def test_synced_at_included(self, mock_db_svc, authed_client):
        user = _make_mock_user(espn=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        data = response.json()
        assert data["leagues"][0]["synced_at"] is not None

    @patch("routes.leagues.db_service")
    def test_sleeper_and_espn(self, mock_db_svc, authed_client):
        user = _make_mock_user(sleeper=True, espn=True)
        db = _mock_db_for_user(user)
        mock_db_svc.session = db.session
        mock_db_svc.is_configured = True

        response = authed_client.get("/leagues/all")
        data = response.json()
        assert data["total"] == 2


# =============================================================================
# _resolve_managed_league_context
# =============================================================================


class TestResolveManagedLeagueContext:
    """Tests for the managed league context resolution helper."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_user(self):
        from api.main import _resolve_managed_league_context

        result = await _resolve_managed_league_context("league_123", None)
        assert result is None

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_returns_none_when_db_not_configured(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = False
        user = _make_mock_user(espn=True)
        result = await _resolve_managed_league_context("league_123", user)
        assert result is None

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_returns_none_when_league_not_found(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        user = _make_mock_user(espn=True)
        result = await _resolve_managed_league_context("nonexistent", user)
        assert result is None

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_resolves_espn_league_context(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True

        managed_league = MagicMock()
        managed_league.platform = "espn"
        managed_league.name = "Fantasy League"
        managed_league.sport = "nfl"
        managed_league.season = "2025"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = managed_league
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        user = _make_mock_user(espn=True)
        result = await _resolve_managed_league_context("espn_456", user)
        assert result is not None
        assert "ESPN League: Fantasy League" in result
        assert "Josh Allen" in result

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_resolves_yahoo_league_context(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True

        managed_league = MagicMock()
        managed_league.platform = "yahoo"
        managed_league.name = "Yahoo League"
        managed_league.sport = "nfl"
        managed_league.season = "2025"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = managed_league
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        user = _make_mock_user(yahoo=True)
        result = await _resolve_managed_league_context("449.l.12345", user)
        assert result is not None
        assert "YAHOO League: Yahoo League" in result
        assert "Lamar Jackson" in result

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_resolves_sleeper_league_context(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True

        managed_league = MagicMock()
        managed_league.platform = "sleeper"
        managed_league.name = "Sleeper League"
        managed_league.sport = "nfl"
        managed_league.season = "2025"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = managed_league
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        user = _make_mock_user(sleeper=True)
        result = await _resolve_managed_league_context("sl_123", user)
        assert result is not None
        assert "SLEEPER League: Sleeper League" in result
        assert "Patrick Mahomes" in result
        assert "[STARTER]" in result

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_returns_header_only_if_no_roster(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True

        managed_league = MagicMock()
        managed_league.platform = "espn"
        managed_league.name = "Empty League"
        managed_league.sport = "nba"
        managed_league.season = "2025"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = managed_league
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        # User has no ESPN roster
        user = _make_mock_user()
        result = await _resolve_managed_league_context("espn_456", user)
        assert result is not None
        assert "ESPN League: Empty League" in result
        assert "roster" not in result.lower()

    @pytest.mark.asyncio
    @patch("api.main.db_service")
    async def test_handles_exception_gracefully(self, mock_db):
        from api.main import _resolve_managed_league_context

        mock_db.is_configured = True
        mock_db.session.side_effect = Exception("DB error")

        user = _make_mock_user(espn=True)
        result = await _resolve_managed_league_context("league_id", user)
        assert result is None
