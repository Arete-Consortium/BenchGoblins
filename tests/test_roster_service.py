"""Tests for UnifiedRosterService — async platform methods, merge edge cases, overrides."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.roster import (
    LineupSlot,
    Platform,
    UnifiedPlayer,
    UnifiedRoster,
    UnifiedRosterService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_espn_roster_player(
    name="Player A",
    team="LAL",
    position="PG",
    lineup_slot="QB",
    espn_id="E100",
    projected_points=20.5,
):
    """Create a mock ESPN roster player with the attributes from_espn expects."""
    p = MagicMock()
    p.name = name
    p.team = team
    p.position = position
    p.lineup_slot = lineup_slot
    p.espn_id = espn_id
    p.projected_points = projected_points
    return p


def _make_sleeper_player(
    player_id="S100",
    full_name="Player B",
    team="BOS",
    position="SG",
    injury_status=None,
):
    """Create a mock Sleeper player detail object."""
    p = MagicMock()
    p.player_id = player_id
    p.full_name = full_name
    p.team = team
    p.position = position
    p.injury_status = injury_status
    return p


def _make_sleeper_roster(players=None, starters=None, reserve=None):
    """Create a mock Sleeper roster."""
    r = MagicMock()
    r.players = players or ["S100", "S200"]
    r.starters = starters or ["S100"]
    r.reserve = reserve or []
    return r


def _make_yahoo_player(
    name="Player C",
    team_abbrev="KC",
    position="WR",
    status="QB",
    injury_status=None,
    player_id="Y100",
    headshot_url="https://example.com/photo.png",
):
    """Create a mock Yahoo player object."""
    p = MagicMock()
    p.name = name
    p.team_abbrev = team_abbrev
    p.position = position
    p.status = status
    p.injury_status = injury_status
    p.player_id = player_id
    p.headshot_url = headshot_url
    return p


def _make_service():
    """Build a UnifiedRosterService with AsyncMock platform services."""
    espn = AsyncMock()
    sleeper = AsyncMock()
    yahoo = AsyncMock()
    return UnifiedRosterService(espn, sleeper, yahoo), espn, sleeper, yahoo


# ---------------------------------------------------------------------------
# from_espn
# ---------------------------------------------------------------------------


class TestFromESPN:
    @pytest.mark.asyncio
    async def test_from_espn_builds_roster(self):
        svc, espn, _, _ = _make_service()

        espn.get_roster.return_value = [
            _make_espn_roster_player(
                name="LeBron James",
                team="LAL",
                position="SF",
                lineup_slot="SF",
                espn_id="E1",
                projected_points=28.5,
            ),
            _make_espn_roster_player(
                name="Anthony Davis",
                team="LAL",
                position="PF",
                lineup_slot="BN",
                espn_id="E2",
                projected_points=24.0,
            ),
        ]
        espn.get_league_details.return_value = {"name": "My ESPN League"}

        creds = MagicMock()
        result = await svc.from_espn(
            creds=creds, league_id="123", team_id=1, sport="nba", season=2024
        )

        assert isinstance(result, UnifiedRoster)
        assert result.sport == "nba"
        assert result.league_name == "My ESPN League"
        assert result.platform == Platform.ESPN
        assert len(result.players) == 2

        lebron = result.players[0]
        assert lebron.name == "LeBron James"
        assert lebron.team == "LAL"
        assert lebron.position == "SF"
        assert lebron.lineup_slot == LineupSlot.STARTER
        assert lebron.espn_id == "E1"
        assert lebron.source_platform == Platform.ESPN
        assert lebron.projected_points == 28.5

        ad = result.players[1]
        assert ad.lineup_slot == LineupSlot.BENCH
        assert ad.espn_id == "E2"

        espn.get_roster.assert_awaited_once_with(
            creds=creds, league_id="123", team_id=1, sport="nba", season=2024
        )
        espn.get_league_details.assert_awaited_once_with(
            creds=creds, league_id="123", sport="nba", season=2024
        )

    @pytest.mark.asyncio
    async def test_from_espn_league_details_none_uses_fallback_name(self):
        svc, espn, _, _ = _make_service()

        espn.get_roster.return_value = [
            _make_espn_roster_player(name="A", lineup_slot="RB"),
        ]
        espn.get_league_details.return_value = None

        result = await svc.from_espn(
            creds=MagicMock(), league_id="456", team_id=2, sport="nfl"
        )

        assert result.league_name == "ESPN League 456"

    @pytest.mark.asyncio
    async def test_from_espn_league_details_missing_name_key(self):
        svc, espn, _, _ = _make_service()

        espn.get_roster.return_value = []
        espn.get_league_details.return_value = {"id": "456"}

        result = await svc.from_espn(
            creds=MagicMock(), league_id="456", team_id=2, sport="nfl"
        )

        assert result.league_name == "ESPN League 456"
        assert len(result.players) == 0

    @pytest.mark.asyncio
    async def test_from_espn_default_season(self):
        svc, espn, _, _ = _make_service()
        espn.get_roster.return_value = []
        espn.get_league_details.return_value = {"name": "L"}

        await svc.from_espn(creds=MagicMock(), league_id="1", team_id=1, sport="nba")

        # Default season=2024 should be passed
        espn.get_roster.assert_awaited_once()
        call_kwargs = espn.get_roster.call_args.kwargs
        assert call_kwargs["season"] == 2024


# ---------------------------------------------------------------------------
# from_sleeper
# ---------------------------------------------------------------------------


class TestFromSleeper:
    @pytest.mark.asyncio
    async def test_from_sleeper_no_roster_returns_empty(self):
        svc, _, sleeper, _ = _make_service()
        sleeper.get_user_roster.return_value = None

        result = await svc.from_sleeper(league_id="SL1", user_id="U1", sport="nfl")

        assert isinstance(result, UnifiedRoster)
        assert result.sport == "nfl"
        assert result.league_name == "Sleeper SL1"
        assert result.platform == Platform.SLEEPER
        assert len(result.players) == 0

    @pytest.mark.asyncio
    async def test_from_sleeper_builds_roster_with_starters_and_bench(self):
        svc, _, sleeper, _ = _make_service()

        roster_mock = _make_sleeper_roster(
            players=["S1", "S2", "S3"],
            starters=["S1", "S3"],
        )
        sleeper.get_user_roster.return_value = roster_mock

        sleeper.get_players_by_ids.return_value = [
            _make_sleeper_player(
                player_id="S1",
                full_name="Patrick Mahomes",
                team="KC",
                position="QB",
                injury_status=None,
            ),
            _make_sleeper_player(
                player_id="S2",
                full_name="Travis Kelce",
                team="KC",
                position="TE",
                injury_status="Questionable",
            ),
            _make_sleeper_player(
                player_id="S3",
                full_name="Tyreek Hill",
                team="MIA",
                position="WR",
                injury_status=None,
            ),
        ]

        result = await svc.from_sleeper(league_id="SL99", user_id="U5", sport="nfl")

        assert result.sport == "nfl"
        assert result.league_name == "Sleeper SL99"
        assert result.platform == Platform.SLEEPER
        assert len(result.players) == 3

        mahomes = result.players[0]
        assert mahomes.name == "Patrick Mahomes"
        assert mahomes.team == "KC"
        assert mahomes.position == "QB"
        assert mahomes.lineup_slot == LineupSlot.STARTER
        assert mahomes.sleeper_id == "S1"
        assert mahomes.source_platform == Platform.SLEEPER
        assert mahomes.injury_status is None

        kelce = result.players[1]
        assert kelce.lineup_slot == LineupSlot.BENCH
        assert kelce.injury_status == "Questionable"
        assert kelce.sleeper_id == "S2"

        hill = result.players[2]
        assert hill.lineup_slot == LineupSlot.STARTER

        sleeper.get_user_roster.assert_awaited_once_with("SL99", "U5")
        sleeper.get_players_by_ids.assert_awaited_once_with(["S1", "S2", "S3"], "nfl")

    @pytest.mark.asyncio
    async def test_from_sleeper_empty_starters_all_bench(self):
        svc, _, sleeper, _ = _make_service()

        roster_mock = _make_sleeper_roster(
            players=["S1"],
            starters=[],
        )
        sleeper.get_user_roster.return_value = roster_mock
        sleeper.get_players_by_ids.return_value = [
            _make_sleeper_player(player_id="S1", full_name="Bench Guy"),
        ]

        result = await svc.from_sleeper(league_id="SL2", user_id="U2", sport="nba")

        assert result.players[0].lineup_slot == LineupSlot.BENCH


# ---------------------------------------------------------------------------
# from_yahoo
# ---------------------------------------------------------------------------


class TestFromYahoo:
    @pytest.mark.asyncio
    async def test_from_yahoo_builds_roster(self):
        svc, _, _, yahoo = _make_service()

        yahoo.get_team_roster.return_value = [
            _make_yahoo_player(
                name="Saquon Barkley",
                team_abbrev="PHI",
                position="RB",
                status="RB",
                injury_status=None,
                player_id="Y1",
                headshot_url="https://example.com/saquon.png",
            ),
            _make_yahoo_player(
                name="CeeDee Lamb",
                team_abbrev="DAL",
                position="WR",
                status="BN",
                injury_status="Out",
                player_id="Y2",
                headshot_url="https://example.com/ceedee.png",
            ),
        ]

        result = await svc.from_yahoo(
            access_token="tok123", team_key="nfl.l.123.t.1", sport="nfl", week=5
        )

        assert isinstance(result, UnifiedRoster)
        assert result.sport == "nfl"
        assert result.league_name == "Yahoo nfl.l.123.t.1"
        assert result.platform == Platform.YAHOO
        assert len(result.players) == 2

        saquon = result.players[0]
        assert saquon.name == "Saquon Barkley"
        assert saquon.team == "PHI"
        assert saquon.position == "RB"
        assert saquon.lineup_slot == LineupSlot.STARTER
        assert saquon.yahoo_id == "Y1"
        assert saquon.source_platform == Platform.YAHOO
        assert saquon.headshot_url == "https://example.com/saquon.png"

        ceedee = result.players[1]
        assert ceedee.lineup_slot == LineupSlot.BENCH
        assert ceedee.injury_status == "Out"
        assert ceedee.yahoo_id == "Y2"

        yahoo.get_team_roster.assert_awaited_once_with("tok123", "nfl.l.123.t.1", 5)

    @pytest.mark.asyncio
    async def test_from_yahoo_default_week_is_none(self):
        svc, _, _, yahoo = _make_service()
        yahoo.get_team_roster.return_value = []

        await svc.from_yahoo(access_token="tok", team_key="nfl.l.1.t.1", sport="nfl")

        yahoo.get_team_roster.assert_awaited_once_with("tok", "nfl.l.1.t.1", None)

    @pytest.mark.asyncio
    async def test_from_yahoo_no_headshot_attr(self):
        """Player object without headshot_url attribute gets None."""
        svc, _, _, yahoo = _make_service()

        yp = MagicMock(
            spec=[
                "name",
                "team_abbrev",
                "position",
                "status",
                "injury_status",
                "player_id",
            ]
        )
        yp.name = "No Photo"
        yp.team_abbrev = "NYG"
        yp.position = "TE"
        yp.status = "TE"
        yp.injury_status = None
        yp.player_id = "Y99"

        yahoo.get_team_roster.return_value = [yp]

        result = await svc.from_yahoo(access_token="tok", team_key="t1", sport="nfl")

        assert result.players[0].headshot_url is None

    @pytest.mark.asyncio
    async def test_from_yahoo_empty_roster(self):
        svc, _, _, yahoo = _make_service()
        yahoo.get_team_roster.return_value = []

        result = await svc.from_yahoo(access_token="tok", team_key="t1", sport="nba")

        assert result.players == []
        assert result.league_name == "Yahoo t1"


# ---------------------------------------------------------------------------
# merge_rosters — edge cases for missing field fills
# ---------------------------------------------------------------------------


class TestMergeRostersMissingFields:
    def _make_service(self):
        return UnifiedRosterService(None, None, None)

    def test_merge_fills_espn_id_from_lower_priority(self):
        """Line 243: existing.espn_id = player.espn_id when existing has None."""
        svc = self._make_service()

        # Sleeper roster first (higher priority than Yahoo, but no ESPN ID)
        sleeper_roster = UnifiedRoster(
            sport="nba",
            league_name="Sleeper",
            platform=Platform.SLEEPER,
            players=[
                UnifiedPlayer(
                    name="LeBron James",
                    team="LAL",
                    position="SF",
                    sport="nba",
                    sleeper_id="S1",
                )
            ],
        )
        # Yahoo roster with an ESPN ID (maybe cross-referenced)
        yahoo_roster = UnifiedRoster(
            sport="nba",
            league_name="Yahoo",
            platform=Platform.YAHOO,
            players=[
                UnifiedPlayer(
                    name="LeBron James",
                    team="LAL",
                    position="SF",
                    sport="nba",
                    yahoo_id="Y1",
                    espn_id="E999",
                )
            ],
        )

        result = svc.merge_rosters([sleeper_roster, yahoo_roster])
        assert len(result.players) == 1
        player = result.players[0]
        # Sleeper was higher priority, so sleeper_id is from first encounter
        assert player.sleeper_id == "S1"
        # ESPN ID was filled from Yahoo (lower priority)
        assert player.espn_id == "E999"
        # Yahoo ID was filled from Yahoo
        assert player.yahoo_id == "Y1"

    def test_merge_fills_projected_points_from_lower_priority(self):
        """Line 250: existing.projected_points = player.projected_points when existing is None."""
        svc = self._make_service()

        espn_roster = UnifiedRoster(
            sport="nba",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Test Player",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    espn_id="E1",
                    projected_points=None,  # ESPN has no projection
                )
            ],
        )
        sleeper_roster = UnifiedRoster(
            sport="nba",
            league_name="Sleeper",
            platform=Platform.SLEEPER,
            players=[
                UnifiedPlayer(
                    name="Test Player",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    sleeper_id="S1",
                    projected_points=18.5,  # Sleeper has projection
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, sleeper_roster])
        assert result.players[0].projected_points == 18.5

    def test_merge_fills_injury_status_from_lower_priority(self):
        """Line 253: existing.injury_status = player.injury_status when existing is None."""
        svc = self._make_service()

        espn_roster = UnifiedRoster(
            sport="nfl",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Injured Star",
                    team="KC",
                    position="WR",
                    sport="nfl",
                    espn_id="E5",
                    injury_status=None,  # ESPN didn't report injury
                )
            ],
        )
        yahoo_roster = UnifiedRoster(
            sport="nfl",
            league_name="Yahoo",
            platform=Platform.YAHOO,
            players=[
                UnifiedPlayer(
                    name="Injured Star",
                    team="KC",
                    position="WR",
                    sport="nfl",
                    yahoo_id="Y5",
                    injury_status="Questionable",
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, yahoo_roster])
        assert result.players[0].injury_status == "Questionable"

    def test_merge_does_not_overwrite_existing_espn_id(self):
        """ESPN ID already present should NOT be overwritten by lower-priority source."""
        svc = self._make_service()

        espn_roster = UnifiedRoster(
            sport="nba",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    espn_id="E_ORIGINAL",
                )
            ],
        )
        yahoo_roster = UnifiedRoster(
            sport="nba",
            league_name="Yahoo",
            platform=Platform.YAHOO,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    espn_id="E_DIFFERENT",
                    yahoo_id="Y1",
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, yahoo_roster])
        assert result.players[0].espn_id == "E_ORIGINAL"

    def test_merge_does_not_overwrite_existing_projected_points(self):
        """Projected points already present should NOT be overwritten."""
        svc = self._make_service()

        espn_roster = UnifiedRoster(
            sport="nba",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    espn_id="E1",
                    projected_points=30.0,
                )
            ],
        )
        sleeper_roster = UnifiedRoster(
            sport="nba",
            league_name="Sleeper",
            platform=Platform.SLEEPER,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="LAL",
                    position="PG",
                    sport="nba",
                    sleeper_id="S1",
                    projected_points=22.0,
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, sleeper_roster])
        assert result.players[0].projected_points == 30.0

    def test_merge_does_not_overwrite_existing_injury_status(self):
        """Injury status already present should NOT be overwritten."""
        svc = self._make_service()

        espn_roster = UnifiedRoster(
            sport="nfl",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="KC",
                    position="WR",
                    sport="nfl",
                    espn_id="E1",
                    injury_status="Out",
                )
            ],
        )
        yahoo_roster = UnifiedRoster(
            sport="nfl",
            league_name="Yahoo",
            platform=Platform.YAHOO,
            players=[
                UnifiedPlayer(
                    name="Star",
                    team="KC",
                    position="WR",
                    sport="nfl",
                    yahoo_id="Y1",
                    injury_status="Doubtful",
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, yahoo_roster])
        assert result.players[0].injury_status == "Out"

    def test_merge_league_name_concatenation(self):
        svc = self._make_service()

        r1 = UnifiedRoster(
            sport="nba",
            league_name="ESPN League",
            platform=Platform.ESPN,
            players=[],
        )
        r2 = UnifiedRoster(
            sport="nba",
            league_name="Sleeper League",
            platform=Platform.SLEEPER,
            players=[],
        )

        result = svc.merge_rosters([r1, r2])
        assert result.league_name == "ESPN League + Sleeper League"

    def test_merge_all_three_fields_filled_at_once(self):
        """Merge where ESPN player is missing espn_id, projected, and injury all at once."""
        svc = self._make_service()

        # ESPN has the player but missing everything
        espn_roster = UnifiedRoster(
            sport="nba",
            league_name="ESPN",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="Gap Player",
                    team="MIA",
                    position="C",
                    sport="nba",
                    espn_id=None,
                    projected_points=None,
                    injury_status=None,
                )
            ],
        )
        # Yahoo has all the data
        yahoo_roster = UnifiedRoster(
            sport="nba",
            league_name="Yahoo",
            platform=Platform.YAHOO,
            players=[
                UnifiedPlayer(
                    name="Gap Player",
                    team="MIA",
                    position="C",
                    sport="nba",
                    espn_id="E_FROM_YAHOO",
                    yahoo_id="Y1",
                    projected_points=15.0,
                    injury_status="GTD",
                )
            ],
        )

        result = svc.merge_rosters([espn_roster, yahoo_roster])
        p = result.players[0]
        assert p.espn_id == "E_FROM_YAHOO"
        assert p.projected_points == 15.0
        assert p.injury_status == "GTD"
        assert p.yahoo_id == "Y1"


# ---------------------------------------------------------------------------
# apply_overrides — projected_points
# ---------------------------------------------------------------------------


class TestApplyOverridesProjectedPoints:
    def test_override_projected_points(self):
        """Line 282: player.projected_points = override['projected_points']."""
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba",
            league_name="Test",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="A",
                    team="T",
                    position="PG",
                    sport="nba",
                    espn_id="E1",
                    projected_points=20.0,
                )
            ],
        )

        result = svc.apply_overrides(roster, {"E1": {"projected_points": 35.0}})
        assert result.players[0].projected_points == 35.0

    def test_override_projected_points_from_none(self):
        """Override projected_points when it was previously None."""
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba",
            league_name="Test",
            platform=Platform.ESPN,
            players=[
                UnifiedPlayer(
                    name="B",
                    team="T",
                    position="SG",
                    sport="nba",
                    espn_id="E2",
                    projected_points=None,
                )
            ],
        )

        result = svc.apply_overrides(roster, {"E2": {"projected_points": 12.5}})
        assert result.players[0].projected_points == 12.5

    def test_override_multiple_fields_including_projected(self):
        """Override lineup_slot, injury_status, and projected_points together."""
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nfl",
            league_name="Test",
            platform=Platform.SLEEPER,
            players=[
                UnifiedPlayer(
                    name="C",
                    team="KC",
                    position="WR",
                    sport="nfl",
                    sleeper_id="S1",
                    lineup_slot=LineupSlot.BENCH,
                    injury_status=None,
                    projected_points=10.0,
                )
            ],
        )

        result = svc.apply_overrides(
            roster,
            {
                "S1": {
                    "lineup_slot": "STARTER",
                    "injury_status": "Probable",
                    "projected_points": 22.0,
                }
            },
        )

        p = result.players[0]
        assert p.lineup_slot == LineupSlot.STARTER
        assert p.injury_status == "Probable"
        assert p.projected_points == 22.0

    def test_override_sets_overrides_dict_on_roster(self):
        """apply_overrides stores the overrides dict on the roster."""
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba",
            league_name="Test",
            platform=Platform.ESPN,
            players=[],
        )
        overrides = {"E1": {"lineup_slot": "IR"}}

        result = svc.apply_overrides(roster, overrides)
        assert result.overrides is overrides
