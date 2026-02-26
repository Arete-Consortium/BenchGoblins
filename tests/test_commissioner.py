"""Tests for commissioner routes and managed league endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.database import League, LeagueMembership, User
from services.sleeper import SleeperRoster

COMMISH_USER = {
    "user_id": 1,
    "email": "commish@test.com",
    "name": "Commissioner",
    "tier": "pro",
    "exp": 9999999999,
}

MEMBER_USER = {
    "user_id": 2,
    "email": "member@test.com",
    "name": "Member",
    "tier": "free",
    "exp": 9999999999,
}


@pytest.fixture
def commish_client(test_client):
    """Test client with commissioner auth."""
    from api.main import app
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: COMMISH_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def member_client(test_client):
    """Test client with member auth."""
    from api.main import app
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: MEMBER_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


def _mock_league(id_=1, commissioner_user_id=1, invite_code="abc123"):
    league = MagicMock(spec=League)
    league.id = id_
    league.external_league_id = "lg_456"
    league.platform = "sleeper"
    league.name = "Fantasy Goblins"
    league.sport = "nfl"
    league.season = "2025"
    league.commissioner_user_id = commissioner_user_id
    league.invite_code = invite_code
    league.created_at = datetime.now(UTC)
    league.updated_at = datetime.now(UTC)
    return league


def _mock_membership(league, user_id=1, role="commissioner"):
    m = MagicMock(spec=LeagueMembership)
    m.id = 1
    m.league_id = league.id
    m.user_id = user_id
    m.role = role
    m.external_team_id = "team_1"
    m.status = "active"
    m.joined_at = datetime.now(UTC)
    m.league = league
    m.user = MagicMock(
        spec=User, id=user_id, email=f"user{user_id}@test.com", name=f"User {user_id}"
    )
    return m


# -------------------------------------------------------------------------
# Managed League Listing
# -------------------------------------------------------------------------


class TestManagedLeagues:
    """Tests for /leagues/managed endpoints."""

    @patch("routes.leagues.db_service")
    def test_get_managed_leagues_empty(self, mock_db, commish_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/leagues/managed")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("routes.leagues.db_service")
    def test_get_managed_leagues_with_leagues(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        # First call: get memberships; Second call: count members
        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [membership]

        memberships_result = MagicMock()
        memberships_result.scalars.return_value.all.return_value = [membership]

        mock_session.execute = AsyncMock(side_effect=[memberships_result, count_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/leagues/managed")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Fantasy Goblins"
        assert data[0]["role"] == "commissioner"
        assert data[0]["invite_code"] == "abc123"


# -------------------------------------------------------------------------
# Invite Flow
# -------------------------------------------------------------------------


class TestInviteFlow:
    """Tests for invite generation and joining."""

    @patch("routes.leagues.db_service")
    def test_generate_invite_commissioner_only(self, mock_db, member_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Not commissioner
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.post("/leagues/managed/1/invite")
        assert resp.status_code == 403

    @patch("routes.leagues.db_service")
    def test_join_league_invalid_code(self, mock_db, commish_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No league found
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.post("/leagues/join/invalid_code")
        assert resp.status_code == 404

    @patch("routes.leagues.db_service")
    def test_join_league_success(self, mock_db, member_client):
        league = _mock_league()

        mock_session = AsyncMock()
        # First call: find league by invite code
        league_result = MagicMock()
        league_result.scalar_one_or_none.return_value = league
        # Second call: check existing membership
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(side_effect=[league_result, existing_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.post("/leagues/join/abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["joined"] is True


# -------------------------------------------------------------------------
# Remove Member
# -------------------------------------------------------------------------


class TestRemoveMember:
    """Tests for member removal."""

    @patch("routes.leagues.db_service")
    def test_cannot_remove_self(self, mock_db, commish_client):
        resp = commish_client.delete(
            f"/leagues/managed/1/members/{COMMISH_USER['user_id']}"
        )
        assert resp.status_code == 400
        assert "Cannot remove yourself" in resp.json()["detail"]

    @patch("routes.leagues.db_service")
    def test_non_commissioner_cannot_remove(self, mock_db, member_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.delete("/leagues/managed/1/members/99")
        assert resp.status_code == 403


# -------------------------------------------------------------------------
# Commissioner AI Endpoints
# -------------------------------------------------------------------------


class TestPowerRankings:
    """Tests for /commissioner/leagues/{id}/power-rankings."""

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_power_rankings_requires_commissioner(
        self, mock_db, mock_sleeper, member_client
    ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Not a commissioner
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.get("/commissioner/leagues/1/power-rankings")
        assert resp.status_code == 403

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_power_rankings_success(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        roster1 = MagicMock(spec=SleeperRoster)
        roster1.owner_id = "owner1"
        roster1.players = ["p1", "p2", "p3", "p4", "p5"]
        roster1.starters = ["p1", "p2", "p3"]

        roster2 = MagicMock(spec=SleeperRoster)
        roster2.owner_id = "owner2"
        roster2.players = ["p6", "p7"]
        roster2.starters = ["p6"]

        mock_sleeper.get_league_rosters = AsyncMock(return_value=[roster1, roster2])

        resp = commish_client.get("/commissioner/leagues/1/power-rankings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rankings"]) == 2
        assert data["rankings"][0]["rank"] == 1
        assert (
            data["rankings"][0]["strength_score"]
            > data["rankings"][1]["strength_score"]
        )

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_power_rankings_empty(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_sleeper.get_league_rosters = AsyncMock(return_value=[])

        resp = commish_client.get("/commissioner/leagues/1/power-rankings")
        assert resp.status_code == 200
        assert resp.json()["rankings"] == []


class TestTradeCheck:
    """Tests for /commissioner/leagues/{id}/trade-check."""

    @patch("routes.commissioner.claude_service")
    @patch("routes.commissioner.db_service")
    def test_trade_check_requires_commissioner(
        self, mock_db, mock_claude, member_client
    ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.post(
            "/commissioner/leagues/1/trade-check",
            json={"team_a_players": ["Player A"], "team_b_players": ["Player B"]},
        )
        assert resp.status_code == 403

    @patch("routes.commissioner.claude_service")
    @patch("routes.commissioner.db_service")
    def test_trade_check_success(self, mock_db, mock_claude, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_claude.is_available = True
        mock_claude.make_decision = AsyncMock(
            return_value={
                "decision": "Fair Trade",
                "confidence": "high",
                "rationale": "Both sides get comparable value",
                "details": {"fairness_score": 52, "verdict": "Fair"},
                "source": "claude",
            }
        )

        resp = commish_client.post(
            "/commissioner/leagues/1/trade-check",
            json={"team_a_players": ["Mahomes"], "team_b_players": ["Allen"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fairness_score"] == 52
        assert data["verdict"] == "Fair"

    @patch("routes.commissioner.claude_service")
    @patch("routes.commissioner.db_service")
    def test_trade_check_claude_unavailable(self, mock_db, mock_claude, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_claude.is_available = False

        resp = commish_client.post(
            "/commissioner/leagues/1/trade-check",
            json={"team_a_players": ["Mahomes"], "team_b_players": ["Allen"]},
        )
        assert resp.status_code == 503


class TestLeagueActivity:
    """Tests for /commissioner/leagues/{id}/activity."""

    @patch("routes.commissioner.db_service")
    def test_activity_requires_commissioner(self, mock_db, member_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.get("/commissioner/leagues/1/activity")
        assert resp.status_code == 403

    @patch("routes.commissioner.db_service")
    def test_activity_success(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.name = "Commissioner"
        mock_user.email = "commish@test.com"
        mock_user.queries_today = 3
        mock_user.updated_at = datetime.now(UTC)

        membership.user = mock_user

        mock_session = AsyncMock()
        # First call: require_commissioner
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership
        # Second call: get memberships with users
        members_result = MagicMock()
        members_result.scalars.return_value.all.return_value = [membership]

        mock_session.execute = AsyncMock(side_effect=[commish_result, members_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/commissioner/leagues/1/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_members"] == 1
        assert data["active_members"] == 1
        assert data["members"][0]["queries_this_week"] == 3


# -------------------------------------------------------------------------
# is_league_pro
# -------------------------------------------------------------------------


class TestIsLeaguePro:
    """Tests for stripe_billing.is_league_pro()."""

    @pytest.mark.asyncio
    @patch("services.stripe_billing.db_service")
    async def test_not_configured(self, mock_db):
        from services.stripe_billing import is_league_pro

        mock_db.is_configured = False
        result = await is_league_pro(1)
        assert result is False

    @pytest.mark.asyncio
    @patch("services.stripe_billing.db_service")
    async def test_no_league_memberships(self, mock_db):
        from services.stripe_billing import is_league_pro

        mock_db.is_configured = True
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await is_league_pro(1)
        assert result is False

    @pytest.mark.asyncio
    @patch("services.stripe_billing.db_service")
    async def test_commissioner_is_pro(self, mock_db):
        from services.stripe_billing import is_league_pro

        mock_db.is_configured = True
        mock_session = AsyncMock()

        league = MagicMock()
        league.commissioner_user_id = 10

        commissioner = MagicMock(spec=User)
        commissioner.subscription_tier = "pro"
        commissioner.stripe_subscription_id = "sub_123"

        league_result = MagicMock()
        league_result.scalars.return_value.all.return_value = [league]

        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = commissioner

        mock_session.execute = AsyncMock(side_effect=[league_result, commish_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await is_league_pro(2)
        assert result is True

    @pytest.mark.asyncio
    @patch("services.stripe_billing.db_service")
    async def test_commissioner_is_free(self, mock_db):
        from services.stripe_billing import is_league_pro

        mock_db.is_configured = True
        mock_session = AsyncMock()

        league = MagicMock()
        league.commissioner_user_id = 10

        commissioner = MagicMock(spec=User)
        commissioner.subscription_tier = "free"
        commissioner.stripe_subscription_id = None

        league_result = MagicMock()
        league_result.scalars.return_value.all.return_value = [league]

        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = commissioner

        mock_session.execute = AsyncMock(side_effect=[league_result, commish_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await is_league_pro(2)
        assert result is False


# -------------------------------------------------------------------------
# ORM Model Tests
# -------------------------------------------------------------------------


class TestLeagueModel:
    """Verify League and LeagueMembership ORM models are defined correctly."""

    def test_league_table_name(self):
        assert League.__tablename__ == "leagues"

    def test_league_has_required_columns(self):
        cols = {c.name for c in League.__table__.columns}
        expected = {
            "id",
            "external_league_id",
            "platform",
            "name",
            "sport",
            "season",
            "commissioner_user_id",
            "invite_code",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_membership_table_name(self):
        assert LeagueMembership.__tablename__ == "league_memberships"

    def test_membership_has_required_columns(self):
        cols = {c.name for c in LeagueMembership.__table__.columns}
        expected = {
            "id",
            "league_id",
            "user_id",
            "role",
            "external_team_id",
            "status",
            "joined_at",
        }
        assert expected.issubset(cols)

    def test_league_unique_constraint(self):
        constraints = [
            c.name
            for c in League.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "uq_leagues_external" in constraints

    def test_membership_unique_constraint(self):
        constraints = [
            c.name
            for c in LeagueMembership.__table__.constraints
            if hasattr(c, "name") and c.name
        ]
        assert "uq_league_memberships" in constraints


# -------------------------------------------------------------------------
# _ensure_league_on_sync
# -------------------------------------------------------------------------


class TestEnsureLeagueOnSync:
    """Tests for the auto-detect league helper."""

    @pytest.mark.asyncio
    @patch("routes.leagues.db_service")
    async def test_creates_new_league(self, mock_db):
        from routes.leagues import _ensure_league_on_sync

        mock_session = AsyncMock()

        # First query: league doesn't exist
        league_result = MagicMock()
        league_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=league_result)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        new_league = MagicMock(spec=League)
        new_league.id = 1
        mock_session.refresh = AsyncMock()

        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        await _ensure_league_on_sync(
            external_league_id="lg_456",
            platform="sleeper",
            season="2025",
            league_name="Test League",
            sport="nfl",
            user_id=1,
        )
        # Should have called session.add at least twice (league + membership)
        assert mock_session.add.call_count >= 2
