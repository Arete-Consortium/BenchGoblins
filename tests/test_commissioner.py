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


# -------------------------------------------------------------------------
# Power Rankings — Sleeper error
# -------------------------------------------------------------------------


class TestPowerRankingsSleeperError:
    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_sleeper_api_error_returns_502(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_sleeper.get_league_rosters = AsyncMock(
            side_effect=RuntimeError("Sleeper API timeout")
        )

        resp = commish_client.get("/commissioner/leagues/1/power-rankings")
        assert resp.status_code == 502
        assert "Sleeper" in resp.json()["detail"]


# -------------------------------------------------------------------------
# Trade Check — exception handler
# -------------------------------------------------------------------------


class TestTradeCheckErrors:
    @patch("routes.commissioner.claude_service")
    @patch("routes.commissioner.db_service")
    def test_trade_check_exception_returns_500(
        self, mock_db, mock_claude, commish_client
    ):
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
            side_effect=RuntimeError("Claude API error")
        )

        resp = commish_client.post(
            "/commissioner/leagues/1/trade-check",
            json={"team_a_players": ["A"], "team_b_players": ["B"]},
        )
        assert resp.status_code == 500
        assert "Trade analysis failed" in resp.json()["detail"]

    @patch("routes.commissioner.claude_service")
    @patch("routes.commissioner.db_service")
    def test_trade_check_non_dict_details(self, mock_db, mock_claude, commish_client):
        """When details is not a dict, should use fallback values."""
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
                "rationale": "Balanced",
                "details": "some string, not a dict",
            }
        )

        resp = commish_client.post(
            "/commissioner/leagues/1/trade-check",
            json={"team_a_players": ["X"], "team_b_players": ["Y"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fairness_score"] == 50.0
        assert data["verdict"] == "Fair Trade"


# -------------------------------------------------------------------------
# Roster Analysis
# -------------------------------------------------------------------------


class TestRosterAnalysis:
    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_roster_analysis_success(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Deep roster (15+ players, 9+ starters)
        deep_roster = MagicMock(spec=SleeperRoster)
        deep_roster.owner_id = "owner_deep"
        deep_roster.players = [f"p{i}" for i in range(16)]
        deep_roster.starters = [f"p{i}" for i in range(9)]

        # Thin roster (< 10 players, < 3 bench)
        thin_roster = MagicMock(spec=SleeperRoster)
        thin_roster.owner_id = "owner_thin"
        thin_roster.players = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
        thin_roster.starters = ["p1", "p2", "p3", "p4", "p5", "p6"]

        mock_sleeper.get_league_rosters = AsyncMock(
            return_value=[deep_roster, thin_roster]
        )

        resp = commish_client.get("/commissioner/leagues/1/roster-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["teams"]) == 2

        deep = next(t for t in data["teams"] if t["owner_id"] == "owner_deep")
        assert "Deep roster" in deep["strengths"]
        assert "Strong starting lineup" in deep["strengths"]

        thin = next(t for t in data["teams"] if t["owner_id"] == "owner_thin")
        assert "Thin roster" in thin["weaknesses"]
        assert "Limited bench depth" in thin["weaknesses"]

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_roster_analysis_sleeper_error(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_sleeper.get_league_rosters = AsyncMock(
            side_effect=RuntimeError("Sleeper down")
        )

        resp = commish_client.get("/commissioner/leagues/1/roster-analysis")
        assert resp.status_code == 502

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_roster_analysis_empty(self, mock_db, mock_sleeper, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = membership
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_sleeper.get_league_rosters = AsyncMock(return_value=None)

        resp = commish_client.get("/commissioner/leagues/1/roster-analysis")
        assert resp.status_code == 200
        assert resp.json()["teams"] == []

    @patch("routes.commissioner.sleeper_service")
    @patch("routes.commissioner.db_service")
    def test_roster_analysis_requires_commissioner(
        self, mock_db, mock_sleeper, member_client
    ):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.get("/commissioner/leagues/1/roster-analysis")
        assert resp.status_code == 403


# -------------------------------------------------------------------------
# Activity — null user edge case
# -------------------------------------------------------------------------


class TestActivityNullUser:
    @patch("routes.commissioner.db_service")
    def test_activity_skips_null_user(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        # Ensure the valid user has real attributes for Pydantic + comparison
        membership.user.updated_at = datetime.now(UTC)
        membership.user.name = f"User {membership.user_id}"
        membership.user.email = f"user{membership.user_id}@test.com"
        membership.user.queries_today = 3

        # A membership with user=None (deleted user)
        null_membership = MagicMock(spec=LeagueMembership)
        null_membership.user = None

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership

        members_result = MagicMock()
        members_result.scalars.return_value.all.return_value = [
            membership,
            null_membership,
        ]

        mock_session.execute = AsyncMock(side_effect=[commish_result, members_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/commissioner/leagues/1/activity")
        assert resp.status_code == 200
        data = resp.json()
        # Only the valid membership should appear
        assert data["total_members"] == 1

    @patch("routes.commissioner.db_service")
    def test_activity_inactive_user(self, mock_db, commish_client):
        """User with old updated_at should not be counted as active."""
        league = _mock_league()
        membership = _mock_membership(league)

        old_user = MagicMock(spec=User)
        old_user.id = 99
        old_user.name = "Stale User"
        old_user.email = "stale@test.com"
        old_user.queries_today = 0
        old_user.updated_at = datetime(2020, 1, 1, tzinfo=UTC)

        stale_membership = MagicMock(spec=LeagueMembership)
        stale_membership.user = old_user

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership

        members_result = MagicMock()
        members_result.scalars.return_value.all.return_value = [stale_membership]

        mock_session.execute = AsyncMock(side_effect=[commish_result, members_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/commissioner/leagues/1/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_members"] == 0
        assert data["members"][0]["is_active"] is False


# -------------------------------------------------------------------------
# Disputes — File, List, Resolve
# -------------------------------------------------------------------------


class TestFileDispute:
    @patch("routes.commissioner.db_service")
    def test_invalid_category(self, mock_db, commish_client):
        resp = commish_client.post(
            "/commissioner/leagues/1/disputes",
            json={
                "category": "invalid",
                "subject": "Test",
                "description": "Something happened",
            },
        )
        assert resp.status_code == 400
        assert "Invalid category" in resp.json()["detail"]

    @patch("routes.commissioner.db_service")
    def test_not_a_member(self, mock_db, member_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.post(
            "/commissioner/leagues/1/disputes",
            json={
                "category": "trade",
                "subject": "Unfair trade",
                "description": "This trade is unfair",
            },
        )
        assert resp.status_code == 403
        assert "Not an active member" in resp.json()["detail"]

    @patch("routes.commissioner.db_service")
    def test_file_dispute_success(self, mock_db, commish_client):
        mock_session = AsyncMock()

        # Membership check
        member_result = MagicMock()
        member_result.scalar_one_or_none.return_value = _mock_membership(
            _mock_league(), role="member"
        )

        mock_session.execute = AsyncMock(return_value=member_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # After refresh, the dispute object gets an id and created_at
        now = datetime.now(UTC)

        async def fake_refresh(obj):
            obj.id = 42
            obj.league_id = 1
            obj.filed_by_user_id = COMMISH_USER["user_id"]
            obj.against_user_id = None
            obj.category = "trade"
            obj.subject = "Unfair trade"
            obj.description = "This trade is clearly unfair"
            obj.status = "open"
            obj.created_at = now

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.post(
            "/commissioner/leagues/1/disputes",
            json={
                "category": "trade",
                "subject": "Unfair trade",
                "description": "This trade is clearly unfair",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 42
        assert data["category"] == "trade"
        assert data["status"] == "open"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestListDisputes:
    @patch("routes.commissioner.db_service")
    def test_list_disputes_as_commissioner(self, mock_db, commish_client):
        league = _mock_league(commissioner_user_id=COMMISH_USER["user_id"])
        membership = _mock_membership(league, role="commissioner")

        now = datetime.now(UTC)

        # Mock disputes
        dispute1 = MagicMock()
        dispute1.id = 1
        dispute1.league_id = 1
        dispute1.filed_by_user_id = 2
        dispute1.against_user_id = 3
        dispute1.category = "trade"
        dispute1.subject = "Trade dispute"
        dispute1.description = "Details"
        dispute1.status = "open"
        dispute1.resolution = None
        dispute1.resolved_by_user_id = None
        dispute1.resolved_at = None
        dispute1.created_at = now

        dispute2 = MagicMock()
        dispute2.id = 2
        dispute2.league_id = 1
        dispute2.filed_by_user_id = 2
        dispute2.against_user_id = None
        dispute2.category = "scoring"
        dispute2.subject = "Scoring error"
        dispute2.description = "Wrong points"
        dispute2.status = "resolved"
        dispute2.resolution = "Fixed"
        dispute2.resolved_by_user_id = 1
        dispute2.resolved_at = now
        dispute2.created_at = now

        # Mock users for name lookup
        user2 = MagicMock(spec=User)
        user2.id = 2
        user2.name = "Member"

        user3 = MagicMock(spec=User)
        user3.id = 3
        user3.name = "Opponent"

        user1 = MagicMock(spec=User)
        user1.id = 1
        user1.name = "Commissioner"

        mock_session = AsyncMock()

        # Call 1: require_commissioner (membership check)
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership

        # Call 2: select disputes
        disputes_result = MagicMock()
        disputes_result.scalars.return_value.all.return_value = [dispute1, dispute2]

        # Call 3: select users for names
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [user1, user2, user3]

        mock_session.execute = AsyncMock(
            side_effect=[commish_result, disputes_result, users_result]
        )
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.get("/commissioner/leagues/1/disputes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["open"] == 1
        assert data["resolved"] == 1
        assert data["disputes"][0]["filed_by_name"] == "Member"
        assert data["disputes"][0]["against_name"] == "Opponent"
        assert data["disputes"][1]["resolved_by_name"] == "Commissioner"

    @patch("routes.commissioner.db_service")
    def test_list_disputes_as_member(self, mock_db, member_client):
        """Regular members should only see their own disputes."""
        league = _mock_league(commissioner_user_id=COMMISH_USER["user_id"])
        membership = _mock_membership(
            league, user_id=MEMBER_USER["user_id"], role="member"
        )

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership

        disputes_result = MagicMock()
        disputes_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[commish_result, disputes_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.get("/commissioner/leagues/1/disputes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @patch("routes.commissioner.db_service")
    def test_list_disputes_not_a_member(self, mock_db, member_client):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = member_client.get("/commissioner/leagues/1/disputes")
        assert resp.status_code == 403


class TestResolveDispute:
    @patch("routes.commissioner.db_service")
    def test_invalid_status(self, mock_db, commish_client):
        resp = commish_client.patch(
            "/commissioner/leagues/1/disputes/1",
            json={"status": "invalid", "resolution": "Something"},
        )
        assert resp.status_code == 400
        assert "resolved" in resp.json()["detail"]

    @patch("routes.commissioner.db_service")
    def test_dispute_not_found(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        mock_session = AsyncMock()
        # Call 1: commissioner check
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership
        # Call 2: dispute not found
        dispute_result = MagicMock()
        dispute_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[commish_result, dispute_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.patch(
            "/commissioner/leagues/1/disputes/999",
            json={"status": "resolved", "resolution": "Fixed it"},
        )
        assert resp.status_code == 404

    @patch("routes.commissioner.db_service")
    def test_dispute_already_closed(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        closed_dispute = MagicMock()
        closed_dispute.status = "resolved"

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership
        dispute_result = MagicMock()
        dispute_result.scalar_one_or_none.return_value = closed_dispute

        mock_session.execute = AsyncMock(side_effect=[commish_result, dispute_result])
        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.patch(
            "/commissioner/leagues/1/disputes/1",
            json={"status": "dismissed", "resolution": "Already handled"},
        )
        assert resp.status_code == 400
        assert "already closed" in resp.json()["detail"]

    @patch("routes.commissioner.db_service")
    def test_resolve_success(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        now = datetime.now(UTC)
        open_dispute = MagicMock()
        open_dispute.id = 10
        open_dispute.league_id = 1
        open_dispute.filed_by_user_id = 2
        open_dispute.against_user_id = None
        open_dispute.category = "conduct"
        open_dispute.subject = "Bad behavior"
        open_dispute.description = "Details"
        open_dispute.status = "open"
        open_dispute.resolution = None
        open_dispute.resolved_by_user_id = None
        open_dispute.resolved_at = None
        open_dispute.created_at = now

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership
        dispute_result = MagicMock()
        dispute_result.scalar_one_or_none.return_value = open_dispute

        mock_session.execute = AsyncMock(side_effect=[commish_result, dispute_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.patch(
            "/commissioner/leagues/1/disputes/10",
            json={"status": "resolved", "resolution": "Warning issued"},
        )
        assert resp.status_code == 200
        # Verify the dispute was updated
        assert open_dispute.status == "resolved"
        assert open_dispute.resolution == "Warning issued"
        assert open_dispute.resolved_by_user_id == COMMISH_USER["user_id"]
        mock_session.commit.assert_called_once()

    @patch("routes.commissioner.db_service")
    def test_dismiss_success(self, mock_db, commish_client):
        league = _mock_league()
        membership = _mock_membership(league)

        now = datetime.now(UTC)
        open_dispute = MagicMock()
        open_dispute.id = 11
        open_dispute.league_id = 1
        open_dispute.filed_by_user_id = 2
        open_dispute.against_user_id = None
        open_dispute.category = "other"
        open_dispute.subject = "Minor issue"
        open_dispute.description = "Not a real issue"
        open_dispute.status = "under_review"
        open_dispute.resolution = None
        open_dispute.resolved_by_user_id = None
        open_dispute.resolved_at = None
        open_dispute.created_at = now

        mock_session = AsyncMock()
        commish_result = MagicMock()
        commish_result.scalar_one_or_none.return_value = membership
        dispute_result = MagicMock()
        dispute_result.scalar_one_or_none.return_value = open_dispute

        mock_session.execute = AsyncMock(side_effect=[commish_result, dispute_result])
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = commish_client.patch(
            "/commissioner/leagues/1/disputes/11",
            json={"status": "dismissed", "resolution": "Not actionable"},
        )
        assert resp.status_code == 200
        assert open_dispute.status == "dismissed"
