"""Tests targeting uncovered lines in routes/leagues.py.

Covers: user-not-found paths for all platforms, _ensure_league_on_sync helper,
managed league routes (get_managed_league, get_league_members, generate_invite,
join_league, remove_member).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sleeper import SleeperLeague, SleeperUser

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


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _mock_db_session_multi(execute_results):
    """Create a mock db_service whose session.execute returns results in order.

    Each entry in execute_results is a MagicMock with the expected return methods.
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=execute_results)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.session.return_value = mock_ctx
    mock_db.is_configured = True
    return mock_db, mock_session


def _scalar_result(value):
    """Return a MagicMock whose scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(items):
    """Return a MagicMock whose scalars().all() returns items."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _make_mock_user(**overrides):
    """Create a mock User ORM object."""
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.email = overrides.get("email", "test@example.com")
    user.name = overrides.get("name", "Test User")
    user.sleeper_username = overrides.get("sleeper_username", None)
    user.sleeper_user_id = overrides.get("sleeper_user_id", None)
    user.sleeper_league_id = overrides.get("sleeper_league_id", None)
    user.roster_snapshot = overrides.get("roster_snapshot", None)
    user.sleeper_synced_at = overrides.get("sleeper_synced_at", None)
    user.espn_swid = overrides.get("espn_swid", None)
    user.espn_s2 = overrides.get("espn_s2", None)
    user.espn_league_id = overrides.get("espn_league_id", None)
    user.espn_team_id = overrides.get("espn_team_id", None)
    user.espn_sport = overrides.get("espn_sport", None)
    user.espn_roster_snapshot = overrides.get("espn_roster_snapshot", None)
    user.espn_synced_at = overrides.get("espn_synced_at", None)
    user.yahoo_access_token = overrides.get("yahoo_access_token", None)
    user.yahoo_refresh_token = overrides.get("yahoo_refresh_token", None)
    user.yahoo_token_expires_at = overrides.get("yahoo_token_expires_at", None)
    user.yahoo_user_guid = overrides.get("yahoo_user_guid", None)
    user.yahoo_league_key = overrides.get("yahoo_league_key", None)
    user.yahoo_team_key = overrides.get("yahoo_team_key", None)
    user.yahoo_sport = overrides.get("yahoo_sport", None)
    user.yahoo_roster_snapshot = overrides.get("yahoo_roster_snapshot", None)
    user.yahoo_synced_at = overrides.get("yahoo_synced_at", None)
    return user


def _make_mock_league(**overrides):
    """Create a mock League ORM object."""
    league = MagicMock()
    league.id = overrides.get("id", 10)
    league.external_league_id = overrides.get("external_league_id", "lg_456")
    league.platform = overrides.get("platform", "sleeper")
    league.name = overrides.get("name", "Fantasy Goblins")
    league.sport = overrides.get("sport", "nfl")
    league.season = overrides.get("season", "2025")
    league.commissioner_user_id = overrides.get("commissioner_user_id", 1)
    league.invite_code = overrides.get("invite_code", "abc123hex")
    return league


def _make_mock_membership(**overrides):
    """Create a mock LeagueMembership ORM object."""
    membership = MagicMock()
    membership.league_id = overrides.get("league_id", 10)
    membership.user_id = overrides.get("user_id", 1)
    membership.role = overrides.get("role", "member")
    membership.external_team_id = overrides.get("external_team_id", None)
    membership.status = overrides.get("status", "active")
    membership.joined_at = overrides.get("joined_at", datetime(2025, 1, 1, tzinfo=UTC))
    membership.league = overrides.get("league", _make_mock_league())
    membership.user = overrides.get("user", _make_mock_user())
    return membership


# =========================================================================
# Line 314: sync_sleeper — DB user not found
# =========================================================================


class TestSyncSleeperUserNotFound:
    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_sync_db_user_not_found(self, mock_svc, mock_db_svc, authed_client):
        """Line 314: User row missing from DB after Sleeper validation passes."""
        mock_svc.get_user = AsyncMock(
            return_value=SleeperUser(
                user_id="sl_123",
                username="goblinmaster",
                display_name="Goblin Master",
                avatar=None,
            )
        )
        mock_svc.get_league = AsyncMock(
            return_value=SleeperLeague(
                league_id="lg_456",
                name="Fantasy Goblins",
                sport="nfl",
                season="2025",
                season_type="regular",
                status="in_season",
                total_rosters=12,
                roster_positions=["QB"],
                scoring_settings={"pass_td": 4},
            )
        )
        mock_svc.get_user_roster = AsyncMock(return_value=None)

        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session
        mock_db_svc.is_configured = True

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "lg_456"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Lines 336-337: _ensure_league_on_sync exception swallowed
# =========================================================================


class TestSyncSleeperEnsureLeagueError:
    @patch("routes.leagues._ensure_league_on_sync")
    @patch("routes.leagues.db_service")
    @patch("routes.leagues.sleeper_service")
    def test_ensure_league_error_swallowed(
        self, mock_svc, mock_db_svc, mock_ensure, authed_client
    ):
        """Lines 336-337: _ensure_league_on_sync raises, sync still succeeds."""
        mock_svc.get_user = AsyncMock(
            return_value=SleeperUser(
                user_id="sl_123",
                username="goblinmaster",
                display_name="Goblin Master",
                avatar=None,
            )
        )
        mock_svc.get_league = AsyncMock(
            return_value=SleeperLeague(
                league_id="lg_456",
                name="Fantasy Goblins",
                sport="nfl",
                season="2025",
                season_type="regular",
                status="in_season",
                total_rosters=12,
                roster_positions=["QB"],
                scoring_settings={"pass_td": 4},
            )
        )
        mock_svc.get_user_roster = AsyncMock(return_value=None)

        mock_db, _ = _mock_db_session_multi([_scalar_result(_make_mock_user())])
        mock_db_svc.session = mock_db.session
        mock_db_svc.is_configured = True

        mock_ensure.side_effect = RuntimeError("DB connection failed")

        response = authed_client.post(
            "/leagues/sync",
            json={"username": "goblinmaster", "league_id": "lg_456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleeper_username"] == "goblinmaster"
        mock_ensure.assert_called_once()


# =========================================================================
# Line 359: get_my_league — user not found
# =========================================================================


class TestGetMyLeagueUserNotFound:
    @patch("routes.leagues.db_service")
    def test_me_user_not_found(self, mock_db_svc, authed_client):
        """Line 359: GET /leagues/me when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/me")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 383: disconnect_league — user not found
# =========================================================================


class TestDisconnectLeagueUserNotFound:
    @patch("routes.leagues.db_service")
    def test_disconnect_user_not_found(self, mock_db_svc, authed_client):
        """Line 383: DELETE /leagues/me when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/me")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 475: sync_espn — user not found
# =========================================================================


class TestSyncESPNUserNotFound:
    @patch("routes.leagues.db_service")
    @patch("routes.leagues.espn_fantasy_service")
    def test_sync_espn_db_user_not_found(self, mock_espn, mock_db_svc, authed_client):
        """Line 475: sync-espn when DB user row is missing."""
        mock_espn.verify_credentials = AsyncMock(return_value=True)
        mock_espn.get_roster = AsyncMock(return_value=[])

        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.post(
            "/leagues/sync-espn",
            json={
                "swid": "{ABCD-1234}",
                "espn_s2": "long_s2_cookie",
                "league_id": "espn_lg_1",
                "team_id": "3",
                "sport": "nfl",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 507: get_my_espn — user not found
# =========================================================================


class TestGetMyESPNUserNotFound:
    @patch("routes.leagues.db_service")
    def test_me_espn_user_not_found(self, mock_db_svc, authed_client):
        """Line 507: GET /leagues/me/espn when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/me/espn")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 531: disconnect_espn — user not found
# =========================================================================


class TestDisconnectESPNUserNotFound:
    @patch("routes.leagues.db_service")
    def test_disconnect_espn_user_not_found(self, mock_db_svc, authed_client):
        """Line 531: DELETE /leagues/me/espn when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/me/espn")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 618: sync_yahoo — user not found
# =========================================================================


class TestSyncYahooUserNotFound:
    @patch("routes.leagues.db_service")
    @patch("routes.leagues.yahoo_service")
    def test_sync_yahoo_db_user_not_found(self, mock_yahoo, mock_db_svc, authed_client):
        """Line 618: sync-yahoo when DB user row is missing."""
        mock_yahoo.get_team_roster = AsyncMock(return_value=[])

        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.post(
            "/leagues/sync-yahoo",
            json={
                "access_token": "yahoo_access_123",
                "refresh_token": "yahoo_refresh_456",
                "expires_at": 9999999999.0,
                "league_key": "449.l.12345",
                "team_key": "449.l.12345.t.1",
                "sport": "nfl",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 651: get_my_yahoo — user not found
# =========================================================================


class TestGetMyYahooUserNotFound:
    @patch("routes.leagues.db_service")
    def test_me_yahoo_user_not_found(self, mock_db_svc, authed_client):
        """Line 651: GET /leagues/me/yahoo when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/me/yahoo")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Line 675: disconnect_yahoo_profile — user not found
# =========================================================================


class TestDisconnectYahooUserNotFound:
    @patch("routes.leagues.db_service")
    def test_disconnect_yahoo_user_not_found(self, mock_db_svc, authed_client):
        """Line 675: DELETE /leagues/me/yahoo when DB user is missing."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/me/yahoo")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"


# =========================================================================
# Lines 794-802: _ensure_league_on_sync — new league creation path
# =========================================================================


class TestEnsureLeagueOnSync:
    @pytest.mark.asyncio
    @patch("routes.leagues.db_service")
    async def test_creates_new_league_and_membership(self, mock_db_svc):
        """Lines 794-802: No existing league — creates league + commissioner membership."""
        from routes.leagues import _ensure_league_on_sync

        # First execute: league lookup returns None (no existing league)
        mock_db, mock_session = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        await _ensure_league_on_sync(
            external_league_id="lg_new",
            platform="sleeper",
            season="2025",
            league_name="New League",
            sport="nfl",
            user_id=1,
            external_team_id="sl_123",
        )

        # session.add called twice: once for league, once for membership
        assert mock_session.add.call_count == 2
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

        # Verify the League object was created with correct args
        first_add_call = mock_session.add.call_args_list[0]
        league_obj = first_add_call[0][0]
        assert league_obj.external_league_id == "lg_new"
        assert league_obj.platform == "sleeper"
        assert league_obj.commissioner_user_id == 1

        # Verify the membership was created
        second_add_call = mock_session.add.call_args_list[1]
        membership_obj = second_add_call[0][0]
        assert membership_obj.user_id == 1
        assert membership_obj.role == "commissioner"
        assert membership_obj.external_team_id == "sl_123"
        assert membership_obj.status == "active"

    @pytest.mark.asyncio
    @patch("routes.leagues.db_service")
    async def test_adds_new_member_to_existing_league(self, mock_db_svc):
        """Lines 793-802: League exists, user not a member — creates member membership."""
        from routes.leagues import _ensure_league_on_sync

        existing_league = _make_mock_league(id=10)
        # First execute: league found; second execute: no existing membership
        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(existing_league), _scalar_result(None)]
        )
        mock_db_svc.session = mock_db.session

        result = await _ensure_league_on_sync(
            external_league_id="lg_456",
            platform="sleeper",
            season="2025",
            league_name="Fantasy Goblins",
            sport="nfl",
            user_id=2,
            external_team_id="sl_456",
        )

        assert result is existing_league
        # session.add called once for the new membership
        assert mock_session.add.call_count == 1
        membership_obj = mock_session.add.call_args[0][0]
        assert membership_obj.user_id == 2
        assert membership_obj.role == "member"
        assert membership_obj.external_team_id == "sl_456"
        mock_session.commit.assert_called_once()

    # =====================================================================
    # Lines 804-806: _ensure_league_on_sync — reactivating removed membership
    # =====================================================================

    @pytest.mark.asyncio
    @patch("routes.leagues.db_service")
    async def test_reactivates_removed_membership(self, mock_db_svc):
        """Lines 804-806: League exists, user was removed — reactivate."""
        from routes.leagues import _ensure_league_on_sync

        existing_league = _make_mock_league(id=10)
        removed_membership = _make_mock_membership(
            status="removed", external_team_id="old_id"
        )

        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(existing_league), _scalar_result(removed_membership)]
        )
        mock_db_svc.session = mock_db.session

        result = await _ensure_league_on_sync(
            external_league_id="lg_456",
            platform="sleeper",
            season="2025",
            league_name="Fantasy Goblins",
            sport="nfl",
            user_id=1,
            external_team_id="sl_new",
        )

        assert result is existing_league
        assert removed_membership.status == "active"
        assert removed_membership.external_team_id == "sl_new"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("routes.leagues.db_service")
    async def test_existing_active_membership_noop(self, mock_db_svc):
        """League exists, user already active — no changes."""
        from routes.leagues import _ensure_league_on_sync

        existing_league = _make_mock_league(id=10)
        active_membership = _make_mock_membership(status="active")

        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(existing_league), _scalar_result(active_membership)]
        )
        mock_db_svc.session = mock_db.session

        result = await _ensure_league_on_sync(
            external_league_id="lg_456",
            platform="sleeper",
            season="2025",
            league_name="Fantasy Goblins",
            sport="nfl",
            user_id=1,
            external_team_id="sl_123",
        )

        assert result is existing_league
        # No commit for active membership (no changes needed)
        mock_session.commit.assert_not_called()
        mock_session.add.assert_not_called()


# =========================================================================
# Lines 862-887: get_managed_league route
# =========================================================================


class TestGetManagedLeague:
    @patch("routes.leagues.db_service")
    def test_get_managed_league_success(self, mock_db_svc, authed_client):
        """Lines 862-887: Full path — member found, count returned."""
        league = _make_mock_league(id=10, invite_code="secret_code")
        membership = _make_mock_membership(
            role="commissioner", league=league, user_id=1
        )
        active_members = [
            _make_mock_membership(user_id=1),
            _make_mock_membership(user_id=2),
        ]

        # First execute: membership lookup; second execute: member count
        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(membership), _scalars_result(active_members)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/10")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 10
        assert data["external_league_id"] == "lg_456"
        assert data["platform"] == "sleeper"
        assert data["name"] == "Fantasy Goblins"
        assert data["role"] == "commissioner"
        assert data["member_count"] == 2
        assert data["invite_code"] == "secret_code"

    @patch("routes.leagues.db_service")
    def test_get_managed_league_not_found(self, mock_db_svc, authed_client):
        """Line 875: Membership not found — 404."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("routes.leagues.db_service")
    def test_get_managed_league_member_no_invite_code(self, mock_db_svc, authed_client):
        """Regular member should not see invite_code."""
        league = _make_mock_league(id=10, invite_code="secret_code")
        membership = _make_mock_membership(role="member", league=league, user_id=1)
        active_members = [_make_mock_membership(user_id=1)]

        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(membership), _scalars_result(active_members)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/10")

        assert response.status_code == 200
        assert response.json()["invite_code"] is None


# =========================================================================
# Lines 906-930: get_league_members route
# =========================================================================


class TestGetLeagueMembers:
    @patch("routes.leagues.db_service")
    def test_get_members_as_commissioner(self, mock_db_svc, authed_client):
        """Lines 906-930: Commissioner sees all members."""
        caller = _make_mock_membership(role="commissioner", user_id=1)
        member1 = _make_mock_membership(
            user_id=1,
            role="commissioner",
            status="active",
            external_team_id="t1",
            user=_make_mock_user(id=1, email="user1@test.com", name="User One"),
            joined_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        member2 = _make_mock_membership(
            user_id=2,
            role="member",
            status="active",
            external_team_id="t2",
            user=_make_mock_user(id=2, email="user2@test.com", name="User Two"),
            joined_at=datetime(2025, 1, 15, tzinfo=UTC),
        )

        # First execute: caller lookup; second execute: members list
        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(caller), _scalars_result([member1, member2])]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/10/members")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["user_id"] == 1
        assert data[0]["role"] == "commissioner"
        assert data[1]["user_id"] == 2
        assert data[1]["email"] == "user2@test.com"

    @patch("routes.leagues.db_service")
    def test_get_members_not_a_member(self, mock_db_svc, authed_client):
        """Line 917: Caller not a member — 403."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/10/members")

        assert response.status_code == 403
        assert "Not a member" in response.json()["detail"]

    @patch("routes.leagues.db_service")
    def test_get_members_as_regular_member(self, mock_db_svc, authed_client):
        """Non-commissioner member — sees active only (commissioner adds filter)."""
        caller = _make_mock_membership(role="member", user_id=1)
        active_member = _make_mock_membership(
            user_id=1,
            role="member",
            status="active",
            user=_make_mock_user(id=1),
            joined_at=datetime(2025, 1, 1, tzinfo=UTC),
        )

        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(caller), _scalars_result([active_member])]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.get("/leagues/managed/10/members")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


# =========================================================================
# Lines 964-973: generate_invite route — league found, regenerate invite
# =========================================================================


class TestGenerateInvite:
    @patch("routes.leagues.secrets")
    @patch("routes.leagues.db_service")
    def test_generate_invite_success(self, mock_db_svc, mock_secrets, authed_client):
        """Lines 964-973: Commissioner regenerates invite code."""
        mock_secrets.token_hex.return_value = "newinvitecode1234"

        commissioner = _make_mock_membership(role="commissioner", user_id=1)
        league = _make_mock_league(id=10, invite_code="oldinvite")

        # First execute: commissioner check; second execute: league lookup
        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(commissioner), _scalar_result(league)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/managed/10/invite")

        assert response.status_code == 200
        data = response.json()
        assert data["invite_code"] == "newinvitecode1234"
        assert "benchgoblins.com/leagues/join/newinvitecode1234" in data["invite_url"]
        mock_session.commit.assert_called_once()

    @patch("routes.leagues.db_service")
    def test_generate_invite_not_commissioner(self, mock_db_svc, authed_client):
        """Non-commissioner gets 403."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/managed/10/invite")

        assert response.status_code == 403
        assert "commissioner" in response.json()["detail"].lower()

    @patch("routes.leagues.db_service")
    def test_generate_invite_league_not_found(self, mock_db_svc, authed_client):
        """Commissioner exists but league row not found — 404."""
        commissioner = _make_mock_membership(role="commissioner", user_id=1)

        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(commissioner), _scalar_result(None)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/managed/10/invite")

        assert response.status_code == 404
        assert response.json()["detail"] == "League not found"


# =========================================================================
# Lines 1001-1007: join_league — already active and reactivated member paths
# =========================================================================


class TestJoinLeague:
    @patch("routes.leagues.db_service")
    def test_join_already_active_member(self, mock_db_svc, authed_client):
        """Line 1001-1002: Already active — returns joined=False."""
        league = _make_mock_league(id=10)
        existing_membership = _make_mock_membership(status="active")

        # First execute: league by invite_code; second: existing membership
        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(league), _scalar_result(existing_membership)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/join/abc123hex")

        assert response.status_code == 200
        data = response.json()
        assert data["joined"] is False
        assert data["reason"] == "Already a member"
        assert data["league_id"] == 10

    @patch("routes.leagues.db_service")
    def test_join_reactivate_removed_member(self, mock_db_svc, authed_client):
        """Lines 1003-1007: Removed member re-joins — reactivated."""
        league = _make_mock_league(id=10)
        removed_membership = _make_mock_membership(status="removed")

        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(league), _scalar_result(removed_membership)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/join/abc123hex")

        assert response.status_code == 200
        data = response.json()
        assert data["joined"] is True
        assert data["league_id"] == 10
        assert data["role"] == "member"
        assert removed_membership.status == "active"
        mock_session.commit.assert_called_once()

    @patch("routes.leagues.db_service")
    def test_join_invalid_invite_code(self, mock_db_svc, authed_client):
        """Invalid invite code — 404."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/join/invalid_code")

        assert response.status_code == 404
        assert response.json()["detail"] == "Invalid invite code"

    @patch("routes.leagues.db_service")
    def test_join_new_member(self, mock_db_svc, authed_client):
        """New user joins via invite — creates membership."""
        league = _make_mock_league(id=10)

        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(league), _scalar_result(None)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.post("/leagues/join/abc123hex")

        assert response.status_code == 200
        data = response.json()
        assert data["joined"] is True
        assert data["league_id"] == 10
        assert data["role"] == "member"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


# =========================================================================
# Lines 1045-1059: remove_member route — target found, mark removed
# =========================================================================


class TestRemoveMember:
    @patch("routes.leagues.db_service")
    def test_remove_member_success(self, mock_db_svc, authed_client):
        """Lines 1045-1059: Commissioner removes a member."""
        commissioner = _make_mock_membership(role="commissioner", user_id=1)
        target = _make_mock_membership(user_id=2, status="active")

        # First execute: commissioner check; second: target lookup
        mock_db, mock_session = _mock_db_session_multi(
            [_scalar_result(commissioner), _scalar_result(target)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/managed/10/members/2")

        assert response.status_code == 200
        data = response.json()
        assert data["removed"] is True
        assert data["user_id"] == 2
        assert target.status == "removed"
        mock_session.commit.assert_called_once()

    @patch("routes.leagues.db_service")
    def test_remove_member_not_commissioner(self, mock_db_svc, authed_client):
        """Non-commissioner gets 403."""
        mock_db, _ = _mock_db_session_multi([_scalar_result(None)])
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/managed/10/members/2")

        assert response.status_code == 403
        assert "commissioner" in response.json()["detail"].lower()

    @patch("routes.leagues.db_service")
    def test_remove_member_target_not_found(self, mock_db_svc, authed_client):
        """Target member not found — 404."""
        commissioner = _make_mock_membership(role="commissioner", user_id=1)

        mock_db, _ = _mock_db_session_multi(
            [_scalar_result(commissioner), _scalar_result(None)]
        )
        mock_db_svc.session = mock_db.session

        response = authed_client.delete("/leagues/managed/10/members/2")

        assert response.status_code == 404
        assert response.json()["detail"] == "Member not found"

    def test_remove_self_blocked(self, authed_client):
        """Cannot remove yourself — 400."""
        response = authed_client.delete("/leagues/managed/10/members/1")

        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot remove yourself"
