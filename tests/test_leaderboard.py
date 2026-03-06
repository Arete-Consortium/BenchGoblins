"""
Tests for the leaderboard API routes.

Covers: input validation, position filtering, score modes, rate limiting,
        DB error handling, and response structure.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routes.leaderboard import POSITIONS, VALID_MODES, VALID_SPORTS, router

app = FastAPI()
app.include_router(router)


def _make_player(
    name="Patrick Mahomes",
    position="QB",
    sport="nfl",
    team="KC",
    espn_id="12345",
):
    p = MagicMock()
    p.id = uuid4()
    p.espn_id = espn_id
    p.name = name
    p.position = position
    p.sport = sport
    p.team = team
    p.team_abbrev = team
    return p


def _make_index(
    player_id=None,
    floor_score=70.0,
    median_score=80.0,
    ceiling_score=95.0,
    sci=85.0,
    rmi=78.0,
    gis=82.0,
    od=30.0,
    msf=88.0,
):
    idx = MagicMock()
    idx.player_id = player_id or uuid4()
    idx.floor_score = Decimal(str(floor_score))
    idx.median_score = Decimal(str(median_score))
    idx.ceiling_score = Decimal(str(ceiling_score))
    idx.sci = Decimal(str(sci))
    idx.rmi = Decimal(str(rmi))
    idx.gis = Decimal(str(gis))
    idx.od = Decimal(str(od))
    idx.msf = Decimal(str(msf))
    idx.calculated_at = datetime(2026, 3, 6, tzinfo=timezone.utc)
    return idx


@pytest.fixture
def _allow_rate_limit():
    with patch(
        "routes.leaderboard.rate_limiter.check_rate_limit",
        new_callable=AsyncMock,
        return_value=(True, 0),
    ):
        yield


@pytest.fixture
def _db_configured():
    with patch("routes.leaderboard.db_service") as mock_db:
        mock_db.is_configured = True
        yield mock_db


class TestLeaderboardValidation:
    @pytest.mark.asyncio
    async def test_invalid_sport(self, _allow_rate_limit):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/leaderboard/curling/top")
        assert resp.status_code == 400
        assert "Invalid sport" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_mode(self, _allow_rate_limit):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/leaderboard/nfl/top?mode=yolo")
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_position_for_sport(self, _allow_rate_limit, _db_configured):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/leaderboard/nba/top?position=QB")
        assert resp.status_code == 400
        assert "Invalid position" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_limit_bounds(self, _allow_rate_limit):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/leaderboard/nfl/top?limit=100")
        assert resp.status_code == 422  # FastAPI validation

    def test_positions_mapping_completeness(self):
        for sport in VALID_SPORTS:
            assert sport in POSITIONS, f"Missing positions for {sport}"
            assert len(POSITIONS[sport]) > 0

    def test_valid_modes(self):
        assert VALID_MODES == {"floor", "median", "ceiling"}


class TestLeaderboardRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        with patch(
            "routes.leaderboard.rate_limiter.check_rate_limit",
            new_callable=AsyncMock,
            return_value=(False, 30),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top")
            assert resp.status_code == 429
            assert resp.headers["retry-after"] == "30"


class TestLeaderboardDBNotConfigured:
    @pytest.mark.asyncio
    async def test_db_not_configured(self, _allow_rate_limit):
        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = False
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top")
        assert resp.status_code == 503
        assert "Database not configured" in resp.json()["detail"]


class TestLeaderboardQuery:
    @pytest.mark.asyncio
    async def test_returns_top_players_by_median(self, _allow_rate_limit):
        p1 = _make_player(name="Pat Mahomes", position="QB", espn_id="1")
        idx1 = _make_index(player_id=p1.id, median_score=90.0)
        p2 = _make_player(name="Josh Allen", position="QB", espn_id="2")
        idx2 = _make_index(player_id=p2.id, median_score=85.0)

        mock_result = MagicMock()
        mock_result.all.return_value = [(p1, idx1), (p2, idx2)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?position=QB&mode=median")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sport"] == "nfl"
        assert data["position"] == "QB"
        assert data["mode"] == "median"
        assert len(data["players"]) == 2
        assert data["players"][0]["rank"] == 1
        assert data["players"][0]["name"] == "Pat Mahomes"
        assert data["players"][1]["rank"] == 2
        assert "QB" in data["positions"]

    @pytest.mark.asyncio
    async def test_returns_all_positions_when_no_filter(self, _allow_rate_limit):
        p1 = _make_player(name="Pat Mahomes", position="QB", espn_id="1")
        idx1 = _make_index(player_id=p1.id)

        mock_result = MagicMock()
        mock_result.all.return_value = [(p1, idx1)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top")

        assert resp.status_code == 200
        data = resp.json()
        assert data["position"] is None
        assert len(data["players"]) == 1

    @pytest.mark.asyncio
    async def test_floor_mode(self, _allow_rate_limit):
        p1 = _make_player(name="Safe Player", espn_id="1")
        idx1 = _make_index(player_id=p1.id, floor_score=75.0)

        mock_result = MagicMock()
        mock_result.all.return_value = [(p1, idx1)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?mode=floor")

        assert resp.status_code == 200
        assert resp.json()["mode"] == "floor"

    @pytest.mark.asyncio
    async def test_ceiling_mode(self, _allow_rate_limit):
        p1 = _make_player(name="Boom Player", espn_id="1")
        idx1 = _make_index(player_id=p1.id, ceiling_score=99.0)

        mock_result = MagicMock()
        mock_result.all.return_value = [(p1, idx1)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?mode=ceiling")

        assert resp.status_code == 200
        assert resp.json()["mode"] == "ceiling"

    @pytest.mark.asyncio
    async def test_empty_leaderboard(self, _allow_rate_limit):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?position=K")

        assert resp.status_code == 200
        data = resp.json()
        assert data["players"] == []
        assert data["position"] == "K"

    @pytest.mark.asyncio
    async def test_position_case_insensitive(self, _allow_rate_limit):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?position=qb")

        assert resp.status_code == 200
        assert resp.json()["position"] == "QB"

    @pytest.mark.asyncio
    async def test_position_whitespace_trimmed(self, _allow_rate_limit):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top?position= QB ")

        assert resp.status_code == 200
        assert resp.json()["position"] == "QB"

    @pytest.mark.asyncio
    async def test_db_error_returns_500(self, _allow_rate_limit):
        from sqlalchemy.exc import SQLAlchemyError

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=SQLAlchemyError("DB down"))

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top")

        assert resp.status_code == 500
        assert "Failed to load leaderboard" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_response_includes_all_index_fields(self, _allow_rate_limit):
        p1 = _make_player(name="Full Index", espn_id="99")
        idx1 = _make_index(
            player_id=p1.id,
            sci=91.5,
            rmi=82.3,
            gis=77.8,
            od=35.2,
            msf=88.9,
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [(p1, idx1)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/leaderboard/nfl/top")

        player = resp.json()["players"][0]
        assert player["sci"] == 91.5
        assert player["rmi"] == 82.3
        assert player["gis"] == 77.8
        assert player["od"] == 35.2
        assert player["msf"] == 88.9
        assert "calculated_at" in player

    @pytest.mark.asyncio
    async def test_nba_positions_accepted(self, _allow_rate_limit):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                for pos in ["PG", "SG", "SF", "PF", "C"]:
                    resp = await client.get(f"/leaderboard/nba/top?position={pos}")
                    assert resp.status_code == 200, f"Failed for NBA position {pos}"

    @pytest.mark.asyncio
    async def test_all_sports_return_positions_list(self, _allow_rate_limit):
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("routes.leaderboard.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                for sport in VALID_SPORTS:
                    resp = await client.get(f"/leaderboard/{sport}/top")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["positions"] == POSITIONS[sport]
