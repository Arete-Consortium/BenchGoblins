"""Tests for ESPN → Core scoring adapter."""

import pytest

from core.scoring import (
    calculate_indices,
    compare_players,
    RiskMode,
)
from services.espn import PlayerInfo, PlayerStats as ESPNPlayerStats
from services.scoring_adapter import adapt_espn_to_core


class TestAdaptESPNToCore:
    """Test ESPN → Core stat mapping."""

    def test_nba_starter_mapping(self, espn_nba_player_info, espn_nba_player_stats):
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)

        assert core.player_id == "12345"
        assert core.name == "Test Player A"
        assert core.team == "LAL"
        assert core.position == "PG"
        assert core.sport == "nba"
        assert core.points_per_game == 26.3
        assert core.minutes_per_game == 34.5
        assert core.usage_rate == 28.5
        assert core.field_goal_pct == 0.485

    def test_is_starter_derived_true(self, espn_nba_player_info, espn_nba_player_stats):
        """48/50 games started = 96% → starter."""
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        assert core.is_starter is True
        assert core.games_started_pct == pytest.approx(0.96, abs=0.01)

    def test_is_starter_derived_false(self, espn_nba_bench_info, espn_nba_bench_stats):
        """5/48 games started = 10.4% → not starter."""
        core = adapt_espn_to_core(espn_nba_bench_info, espn_nba_bench_stats)
        assert core.is_starter is False
        assert core.games_started_pct == pytest.approx(0.104, abs=0.01)

    def test_is_starter_boundary(self):
        """Exactly 80% → starter."""
        info = PlayerInfo(
            id="x",
            name="X",
            team="T",
            team_abbrev="T",
            position="G",
            jersey="0",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = ESPNPlayerStats(
            player_id="x",
            sport="nba",
            games_played=10,
            games_started=8,
        )
        core = adapt_espn_to_core(info, stats)
        assert core.is_starter is True

    def test_zero_games_played(self):
        """Zero games → not starter, 0% started."""
        info = PlayerInfo(
            id="x",
            name="X",
            team="T",
            team_abbrev="T",
            position="G",
            jersey="0",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = ESPNPlayerStats(
            player_id="x",
            sport="nba",
            games_played=0,
            games_started=0,
        )
        core = adapt_espn_to_core(info, stats)
        assert core.is_starter is False
        assert core.games_started_pct == 0.0

    def test_nfl_wr_mapping(self, espn_nfl_wr_info, espn_nfl_wr_stats):
        core = adapt_espn_to_core(espn_nfl_wr_info, espn_nfl_wr_stats)

        assert core.sport == "nfl"
        assert core.position == "WR"
        assert core.targets == 8.5
        assert core.receptions == 5.8
        assert core.receiving_yards == 78.4
        assert core.snap_pct == 85.0
        assert core.is_starter is True  # 12/12

    def test_none_stats_default_to_zero(self):
        """ESPN None fields should map to 0.0 in core."""
        info = PlayerInfo(
            id="x",
            name="X",
            team="T",
            team_abbrev="T",
            position="C",
            jersey="0",
            height="",
            weight="",
            age=None,
            experience=None,
            headshot_url=None,
        )
        stats = ESPNPlayerStats(
            player_id="x",
            sport="nba",
            games_played=10,
            games_started=10,
        )
        core = adapt_espn_to_core(info, stats)
        assert core.points_per_game == 0.0
        assert core.minutes_per_game == 0.0
        assert core.usage_rate == 0.0
        assert core.field_goal_pct == 0.0

    def test_trend_fields_default_to_zero(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        """ESPN doesn't expose trends; they should be 0.0."""
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        assert core.minutes_trend == 0.0
        assert core.usage_trend == 0.0
        assert core.points_trend == 0.0

    def test_matchup_fields_are_none(self, espn_nba_player_info, espn_nba_player_stats):
        """No matchup data from ESPN → None → neutral MSF = 50."""
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        assert core.opponent_def_rating is None
        assert core.opponent_pace is None
        assert core.opponent_vs_position is None


class TestAdapterRoundTrip:
    """Adapted stats should produce valid index scores."""

    def test_nba_produces_valid_indices(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        indices = calculate_indices(core)

        assert 0 <= indices.sci <= 100
        assert 0 <= indices.rmi <= 100
        assert 0 <= indices.gis <= 100
        assert -50 <= indices.od <= 50
        assert 0 <= indices.msf <= 100

    def test_nfl_produces_valid_indices(self, espn_nfl_wr_info, espn_nfl_wr_stats):
        core = adapt_espn_to_core(espn_nfl_wr_info, espn_nfl_wr_stats)
        indices = calculate_indices(core)

        assert 0 <= indices.sci <= 100
        assert 0 <= indices.rmi <= 100
        assert 0 <= indices.gis <= 100
        assert -50 <= indices.od <= 50
        assert 0 <= indices.msf <= 100

    def test_compare_adapted_players(
        self,
        espn_nba_player_info,
        espn_nba_player_stats,
        espn_nba_bench_info,
        espn_nba_bench_stats,
    ):
        core_a = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        core_b = adapt_espn_to_core(espn_nba_bench_info, espn_nba_bench_stats)

        result = compare_players(core_a, core_b, RiskMode.MEDIAN)

        assert "decision" in result
        assert result["confidence"] in ("low", "medium", "high")
        assert result["score_a"] > result["score_b"]  # Starter should outscore bench
        assert result["margin"] > 0

    def test_neutral_msf_for_no_matchup_data(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        """With no matchup data, MSF should be exactly 50."""
        core = adapt_espn_to_core(espn_nba_player_info, espn_nba_player_stats)
        indices = calculate_indices(core)
        assert indices.msf == 50.0


class TestAdapterTrends:
    """Test trends dict mapping in adapter."""

    def test_trends_mapped_correctly(self, espn_nba_player_info, espn_nba_player_stats):
        trends = {"minutes_trend": 3.5, "points_trend": 2.1, "usage_trend": 1.8}
        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, trends=trends
        )
        assert core.minutes_trend == 3.5
        assert core.points_trend == 2.1
        assert core.usage_trend == 1.8

    def test_none_trends_defaults_to_zero(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, trends=None
        )
        assert core.minutes_trend == 0.0
        assert core.points_trend == 0.0
        assert core.usage_trend == 0.0

    def test_trends_produce_nonzero_od(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        """Adapted stats with trends should produce non-zero OD."""
        from core.scoring import calculate_od

        trends = {"minutes_trend": 5.0, "points_trend": 3.0, "usage_trend": 2.0}
        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, trends=trends
        )
        od = calculate_od(core)
        assert od != 0.0


class TestAdapterMatchup:
    """Test matchup mapping in adapter."""

    def test_nba_matchup_mapped(self, espn_nba_player_info, espn_nba_player_stats):
        from services.espn import TeamDefense

        matchup = TeamDefense(
            team_abbrev="CHI",
            sport="nba",
            defensive_rating=115.0,
            points_allowed=118.5,
            pace=102.0,
            vs_pg=35.0,
        )
        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, matchup=matchup
        )
        assert core.opponent_def_rating == 115.0  # NBA uses defensive_rating
        assert core.opponent_pace == 102.0
        assert core.opponent_vs_position == 35.0  # PG position

    def test_nfl_matchup_uses_points_allowed(self, espn_nfl_wr_info, espn_nfl_wr_stats):
        from services.espn import TeamDefense

        matchup = TeamDefense(
            team_abbrev="DEN",
            sport="nfl",
            points_allowed=28.5,
        )
        core = adapt_espn_to_core(espn_nfl_wr_info, espn_nfl_wr_stats, matchup=matchup)
        assert core.opponent_def_rating == 28.5

    def test_none_matchup_yields_neutral_msf(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        from core.scoring import calculate_msf

        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, matchup=None
        )
        assert calculate_msf(core) == 50.0

    def test_matchup_produces_non50_msf(
        self, espn_nba_player_info, espn_nba_player_stats
    ):
        from services.espn import TeamDefense
        from core.scoring import calculate_msf

        matchup = TeamDefense(
            team_abbrev="CHI",
            sport="nba",
            defensive_rating=118.0,
            pace=105.0,
            vs_pg=40.0,
        )
        core = adapt_espn_to_core(
            espn_nba_player_info, espn_nba_player_stats, matchup=matchup
        )
        msf = calculate_msf(core)
        assert msf != 50.0


class TestAdapterSoccerMatchup:
    """Test soccer position matchup mapping (lines 20-44)."""

    def test_soccer_forward_matchup(
        self, espn_soccer_forward_info, espn_soccer_forward_stats
    ):
        """Soccer FW position maps to vs_fwd."""
        from services.espn import TeamDefense

        matchup = TeamDefense(
            team_abbrev="CHE",
            sport="soccer",
            points_allowed=25.0,
            pace=None,
            vs_fwd=18.5,
            vs_mid=12.0,
            vs_def=5.0,
            vs_gk=2.0,
        )
        core = adapt_espn_to_core(
            espn_soccer_forward_info, espn_soccer_forward_stats, matchup=matchup
        )
        assert core.opponent_vs_position == 18.5
        # Soccer uses points_allowed, not defensive_rating
        assert core.opponent_def_rating == 25.0

    def test_soccer_midfielder_matchup(self):
        """Soccer MF/MID/CM positions map to vs_mid."""
        from services.espn import TeamDefense
        from services.scoring_adapter import _position_matchup_field

        matchup = TeamDefense(
            team_abbrev="MCI",
            sport="soccer",
            vs_fwd=18.0,
            vs_mid=14.0,
            vs_def=6.0,
            vs_gk=1.0,
        )
        for pos in ("MF", "MID", "M", "CM", "CAM", "CDM"):
            result = _position_matchup_field(matchup, pos, sport="soccer")
            assert result == 14.0, f"Position {pos} should map to vs_mid"

    def test_soccer_defender_matchup(self):
        """Soccer DF/DEF/CB/LB/RB positions map to vs_def."""
        from services.espn import TeamDefense
        from services.scoring_adapter import _position_matchup_field

        matchup = TeamDefense(
            team_abbrev="LIV",
            sport="soccer",
            vs_fwd=18.0,
            vs_mid=14.0,
            vs_def=6.5,
            vs_gk=1.0,
        )
        for pos in ("DF", "DEF", "D", "CB", "LB", "RB"):
            result = _position_matchup_field(matchup, pos, sport="soccer")
            assert result == 6.5, f"Position {pos} should map to vs_def"

    def test_soccer_goalkeeper_matchup(self):
        """Soccer GK/G/GOALKEEPER positions map to vs_gk."""
        from services.espn import TeamDefense
        from services.scoring_adapter import _position_matchup_field

        matchup = TeamDefense(
            team_abbrev="ARS",
            sport="soccer",
            vs_fwd=18.0,
            vs_mid=14.0,
            vs_def=6.0,
            vs_gk=3.0,
        )
        for pos in ("GK", "G", "GOALKEEPER"):
            result = _position_matchup_field(matchup, pos, sport="soccer")
            assert result == 3.0, f"Position {pos} should map to vs_gk"

    def test_soccer_forward_aliases(self):
        """Soccer FW/FWD/F/ST/CF/LW/RW all map to vs_fwd."""
        from services.espn import TeamDefense
        from services.scoring_adapter import _position_matchup_field

        matchup = TeamDefense(
            team_abbrev="BAR",
            sport="soccer",
            vs_fwd=20.0,
            vs_mid=14.0,
            vs_def=6.0,
            vs_gk=1.0,
        )
        for pos in ("FW", "FWD", "F", "ST", "CF", "LW", "RW"):
            result = _position_matchup_field(matchup, pos, sport="soccer")
            assert result == 20.0, f"Position {pos} should map to vs_fwd"

    def test_soccer_unknown_position_returns_none(self):
        """Unknown soccer position returns None."""
        from services.espn import TeamDefense
        from services.scoring_adapter import _position_matchup_field

        matchup = TeamDefense(
            team_abbrev="BAR",
            sport="soccer",
            vs_fwd=20.0,
            vs_mid=14.0,
            vs_def=6.0,
            vs_gk=1.0,
        )
        result = _position_matchup_field(matchup, "XX", sport="soccer")
        assert result is None


class TestAdapterMLB:
    """Test MLB field mapping in adapter."""

    def test_mlb_hitter_mapping(self, espn_mlb_hitter_info, espn_mlb_hitter_stats):
        core = adapt_espn_to_core(espn_mlb_hitter_info, espn_mlb_hitter_stats)
        assert core.sport == "mlb"
        assert core.batting_avg == 0.285
        assert core.home_runs == 32.0
        assert core.rbis == 95.0
        assert core.stolen_bases == 12.0
        assert core.ops == 0.875

    def test_mlb_produces_valid_indices(
        self, espn_mlb_hitter_info, espn_mlb_hitter_stats
    ):
        core = adapt_espn_to_core(espn_mlb_hitter_info, espn_mlb_hitter_stats)
        indices = calculate_indices(core)
        assert 0 <= indices.sci <= 100
        assert 0 <= indices.rmi <= 100
        assert 0 <= indices.gis <= 100
        assert -50 <= indices.od <= 50
        assert 0 <= indices.msf <= 100


class TestAdapterNHL:
    """Test NHL field mapping in adapter."""

    def test_nhl_forward_mapping(self, espn_nhl_forward_info, espn_nhl_forward_stats):
        core = adapt_espn_to_core(espn_nhl_forward_info, espn_nhl_forward_stats)
        assert core.sport == "nhl"
        assert core.goals == 35.0
        assert core.assists_nhl == 45.0
        assert core.plus_minus == 15.0
        assert core.shots == 250.0

    def test_nhl_produces_valid_indices(
        self, espn_nhl_forward_info, espn_nhl_forward_stats
    ):
        core = adapt_espn_to_core(espn_nhl_forward_info, espn_nhl_forward_stats)
        indices = calculate_indices(core)
        assert 0 <= indices.sci <= 100
        assert 0 <= indices.rmi <= 100
        assert 0 <= indices.gis <= 100
        assert -50 <= indices.od <= 50
        assert 0 <= indices.msf <= 100
