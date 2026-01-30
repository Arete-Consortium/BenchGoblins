"""Tests for Outcome Recorder Service."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.outcome_recorder import (
    PlayerGameResult,
    OutcomeRecordResult,
    calculate_fantasy_points,
    _calculate_nba_fantasy_points,
    _calculate_nfl_fantasy_points,
    _calculate_mlb_fantasy_points,
    _calculate_nhl_fantasy_points,
    _normalize_player_name,
    _names_match,
    determine_outcome,
    fetch_player_game_result,
    match_decision_to_outcome,
    record_outcomes_for_date,
    sync_recent_outcomes,
)


class TestFantasyPointsCalculation:
    """Tests for fantasy points calculation functions."""

    def test_nba_fantasy_points_basic(self):
        """Test NBA fantasy points calculation."""
        game_log = {
            "points": 25,
            "rebounds": 10,
            "assists": 5,
            "steals": 2,
            "blocks": 1,
            "turnovers": 3,
        }
        # 25*1 + 10*1.2 + 5*1.5 + 2*3 + 1*3 - 3*1 = 25 + 12 + 7.5 + 6 + 3 - 3 = 50.5
        expected = 50.5
        assert _calculate_nba_fantasy_points(game_log) == expected

    def test_nba_fantasy_points_zero_stats(self):
        """Test NBA fantasy points with zero/missing stats."""
        game_log = {"points": 0, "rebounds": 0}
        assert _calculate_nba_fantasy_points(game_log) == 0.0

    def test_nba_fantasy_points_missing_keys(self):
        """Test NBA fantasy points with missing keys (defaults to 0)."""
        game_log = {"points": 10}
        assert _calculate_nba_fantasy_points(game_log) == 10.0

    def test_nfl_fantasy_points_qb(self):
        """Test NFL fantasy points for a QB stat line."""
        game_log = {
            "pass_yards": 300,  # 0.04 * 300 = 12
            "pass_tds": 3,  # 4 * 3 = 12
            "pass_ints": 1,  # -2 * 1 = -2
            "rush_yards": 20,  # 0.1 * 20 = 2
            "rush_tds": 0,
            "receptions": 0,
            "receiving_yards": 0,
            "receiving_tds": 0,
        }
        # 12 + 12 - 2 + 2 = 24
        expected = 24.0
        assert _calculate_nfl_fantasy_points(game_log, scoring="ppr") == expected

    def test_nfl_fantasy_points_wr_ppr(self):
        """Test NFL fantasy points for a WR in PPR."""
        game_log = {
            "pass_yards": 0,
            "pass_tds": 0,
            "pass_ints": 0,
            "rush_yards": 0,
            "rush_tds": 0,
            "receptions": 8,  # 1 * 8 = 8 (PPR)
            "receiving_yards": 120,  # 0.1 * 120 = 12
            "receiving_tds": 1,  # 6 * 1 = 6
        }
        # 8 + 12 + 6 = 26
        expected = 26.0
        assert _calculate_nfl_fantasy_points(game_log, scoring="ppr") == expected

    def test_nfl_fantasy_points_half_ppr(self):
        """Test NFL fantasy points in half-PPR."""
        game_log = {
            "receptions": 8,  # 0.5 * 8 = 4
            "receiving_yards": 100,  # 0.1 * 100 = 10
            "receiving_tds": 0,
        }
        expected = 14.0
        assert _calculate_nfl_fantasy_points(game_log, scoring="half_ppr") == expected

    def test_mlb_fantasy_points_hitter(self):
        """Test MLB fantasy points for a hitter."""
        game_log = {
            "hits": 3,  # 3 * 3 = 9
            "home_runs": 1,  # 6 * 1 = 6
            "rbis": 2,  # 2 * 2 = 4
            "stolen_bases": 1,  # 5 * 1 = 5
        }
        expected = 24.0
        assert _calculate_mlb_fantasy_points(game_log) == expected

    def test_nhl_fantasy_points_forward(self):
        """Test NHL fantasy points for a forward."""
        game_log = {
            "goals": 2,  # 3 * 2 = 6
            "assists": 1,  # 2 * 1 = 2
            "shots": 6,  # 0.5 * 6 = 3
        }
        expected = 11.0
        assert _calculate_nhl_fantasy_points(game_log) == expected

    def test_calculate_fantasy_points_routing(self):
        """Test that calculate_fantasy_points routes to correct sport function."""
        nba_log = {"points": 20, "rebounds": 5}
        nfl_log = {"receptions": 5, "receiving_yards": 50}
        mlb_log = {"hits": 2}
        nhl_log = {"goals": 1}

        assert calculate_fantasy_points(
            nba_log, "nba"
        ) == _calculate_nba_fantasy_points(nba_log)
        assert calculate_fantasy_points(
            nfl_log, "nfl"
        ) == _calculate_nfl_fantasy_points(nfl_log)
        assert calculate_fantasy_points(
            mlb_log, "mlb"
        ) == _calculate_mlb_fantasy_points(mlb_log)
        assert calculate_fantasy_points(
            nhl_log, "nhl"
        ) == _calculate_nhl_fantasy_points(nhl_log)

    def test_calculate_fantasy_points_unknown_sport(self):
        """Test that unknown sport returns 0."""
        assert calculate_fantasy_points({}, "tennis") == 0.0


class TestPlayerNameMatching:
    """Tests for player name matching functions."""

    def test_normalize_player_name_basic(self):
        """Test basic name normalization."""
        assert _normalize_player_name("LeBron James") == "lebron james"
        assert _normalize_player_name("  LeBron James  ") == "lebron james"

    def test_normalize_player_name_suffixes(self):
        """Test removing common suffixes."""
        assert _normalize_player_name("Patrick Mahomes Jr.") == "patrick mahomes"
        assert _normalize_player_name("Gary Trent Jr") == "gary trent"
        assert _normalize_player_name("Robert Griffin III") == "robert griffin"

    def test_normalize_player_name_none(self):
        """Test normalization of None."""
        assert _normalize_player_name(None) == ""

    def test_names_match_exact(self):
        """Test exact name matching."""
        assert _names_match("LeBron James", "LeBron James") is True
        assert _names_match("lebron james", "LEBRON JAMES") is True

    def test_names_match_partial(self):
        """Test partial name matching."""
        assert _names_match("LeBron", "LeBron James") is True
        assert _names_match("LeBron James", "LeBron") is True

    def test_names_match_last_name_initial(self):
        """Test matching by last name and first initial."""
        assert _names_match("L. James", "LeBron James") is True
        assert _names_match("LeBron James", "L. James") is True

    def test_names_match_no_match(self):
        """Test non-matching names."""
        assert _names_match("LeBron James", "Kevin Durant") is False
        assert _names_match("LeBron James", "") is False
        assert _names_match("", "Kevin Durant") is False
        assert _names_match(None, "Kevin Durant") is False


class TestDetermineOutcome:
    """Tests for outcome determination logic."""

    def _make_decision(
        self,
        decision_text: str = "Start Player A",
        player_a_name: str = "Player A",
        player_b_name: str = "Player B",
    ):
        """Create a mock decision object."""
        decision = MagicMock()
        decision.decision = decision_text
        decision.player_a_name = player_a_name
        decision.player_b_name = player_b_name
        return decision

    def test_correct_decision_player_a(self):
        """Test correct outcome when player A was recommended and scored higher."""
        decision = self._make_decision("Start Player A")
        result = determine_outcome(decision, 30.0, 20.0)
        assert result == "correct"

    def test_incorrect_decision_player_a(self):
        """Test incorrect outcome when player A was recommended but scored lower."""
        decision = self._make_decision("Start Player A")
        result = determine_outcome(decision, 15.0, 25.0)
        assert result == "incorrect"

    def test_correct_decision_player_b(self):
        """Test correct outcome when player B was recommended and scored higher."""
        decision = self._make_decision("Start Player B", "Player A", "Player B")
        result = determine_outcome(decision, 15.0, 30.0)
        assert result == "correct"

    def test_incorrect_decision_player_b(self):
        """Test incorrect outcome when player B was recommended but scored lower."""
        decision = self._make_decision("Start Player B", "Player A", "Player B")
        result = determine_outcome(decision, 30.0, 15.0)
        assert result == "incorrect"

    def test_push_within_one_point(self):
        """Test push when margin is less than 1 point."""
        decision = self._make_decision("Start Player A")
        assert determine_outcome(decision, 20.0, 20.5) == "push"
        assert determine_outcome(decision, 20.5, 20.0) == "push"
        assert determine_outcome(decision, 20.0, 20.99) == "push"

    def test_not_push_at_one_point(self):
        """Test that exactly 1 point difference is not a push."""
        decision = self._make_decision("Start Player A")
        assert determine_outcome(decision, 21.0, 20.0) == "correct"

    def test_none_when_missing_points(self):
        """Test None returned when points are missing."""
        decision = self._make_decision("Start Player A")
        assert determine_outcome(decision, None, 20.0) is None
        assert determine_outcome(decision, 20.0, None) is None
        assert determine_outcome(decision, None, None) is None


class TestFetchPlayerGameResult:
    """Tests for fetching player game results."""

    @pytest.mark.asyncio
    async def test_fetch_player_game_result_found(self):
        """Test fetching game result when player and game exist."""
        mock_player_info = MagicMock()
        mock_player_info.id = "12345"
        mock_player_info.name = "LeBron James"
        mock_player_info.team_abbrev = "LAL"

        mock_game_logs = [
            {
                "date": "2024-01-15",
                "points": 30,
                "rebounds": 8,
                "assists": 10,
                "steals": 2,
                "blocks": 1,
                "turnovers": 3,
            }
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=mock_game_logs)

            result = await fetch_player_game_result(
                "LeBron James", "nba", date(2024, 1, 15)
            )

            assert result is not None
            assert result.player_name == "LeBron James"
            assert result.espn_id == "12345"
            assert result.game_date == date(2024, 1, 15)
            assert result.fantasy_points == calculate_fantasy_points(
                mock_game_logs[0], "nba"
            )

    @pytest.mark.asyncio
    async def test_fetch_player_game_result_player_not_found(self):
        """Test fetching game result when player not found."""
        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(return_value=None)

            result = await fetch_player_game_result(
                "Unknown Player", "nba", date(2024, 1, 15)
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_player_game_result_no_game_on_date(self):
        """Test fetching game result when no game on target date."""
        mock_player_info = MagicMock()
        mock_player_info.id = "12345"
        mock_player_info.name = "LeBron James"
        mock_player_info.team_abbrev = "LAL"

        mock_game_logs = [
            {"date": "2024-01-10", "points": 25},  # Different date
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=mock_game_logs)

            result = await fetch_player_game_result(
                "LeBron James", "nba", date(2024, 1, 15)
            )

            assert result is None


class TestMatchDecisionToOutcome:
    """Tests for matching decisions to outcomes."""

    @pytest.mark.asyncio
    async def test_match_decision_with_both_players(self):
        """Test matching a decision with both players having results."""
        decision = MagicMock()
        decision.player_a_name = "Player A"
        decision.player_b_name = "Player B"
        decision.sport = "nba"
        decision.created_at = datetime(2024, 1, 15, 12, 0, 0)

        mock_result_a = PlayerGameResult(
            player_name="Player A",
            espn_id="111",
            team="LAL",
            game_date=date(2024, 1, 15),
            fantasy_points=35.0,
            sport="nba",
        )
        mock_result_b = PlayerGameResult(
            player_name="Player B",
            espn_id="222",
            team="BOS",
            game_date=date(2024, 1, 15),
            fantasy_points=28.0,
            sport="nba",
        )

        with patch("services.outcome_recorder.fetch_player_game_result") as mock_fetch:
            mock_fetch.side_effect = [mock_result_a, mock_result_b]

            points_a, points_b = await match_decision_to_outcome(decision)

            assert points_a == 35.0
            assert points_b == 28.0

    @pytest.mark.asyncio
    async def test_match_decision_missing_player_names(self):
        """Test matching a decision without player names."""
        decision = MagicMock()
        decision.player_a_name = None
        decision.player_b_name = None
        decision.created_at = datetime(2024, 1, 15, 12, 0, 0)

        points_a, points_b = await match_decision_to_outcome(decision)

        assert points_a is None
        assert points_b is None


class TestRecordOutcomesForDate:
    """Tests for recording outcomes for a date."""

    @pytest.mark.asyncio
    async def test_record_outcomes_database_not_configured(self):
        """Test recording outcomes when database is not configured."""
        with patch("services.outcome_recorder.db_service") as mock_db:
            mock_db.is_configured = False

            result = await record_outcomes_for_date(date(2024, 1, 15), "nba")

            assert result.decisions_processed == 0
            assert result.outcomes_recorded == 0
            assert "Database not configured" in result.errors


class TestSyncRecentOutcomes:
    """Tests for syncing recent outcomes."""

    @pytest.mark.asyncio
    async def test_sync_recent_outcomes_returns_summary(self):
        """Test that sync_recent_outcomes returns proper summary."""
        mock_result = OutcomeRecordResult(
            date=date(2024, 1, 14),
            sport="nba",
            decisions_processed=5,
            outcomes_recorded=3,
            errors=[],
        )

        with patch(
            "services.outcome_recorder.record_outcomes_for_date_range"
        ) as mock_record:
            mock_record.return_value = [mock_result]

            result = await sync_recent_outcomes(days_back=1, sport="nba")

            assert result["total_decisions_processed"] == 5
            assert result["total_outcomes_recorded"] == 3
            assert result["sport"] == "nba"
            assert len(result["daily_results"]) == 1


class TestOutcomeRecordResult:
    """Tests for OutcomeRecordResult dataclass."""

    def test_outcome_record_result_creation(self):
        """Test creating an OutcomeRecordResult."""
        result = OutcomeRecordResult(
            date=date(2024, 1, 15),
            sport="nba",
            decisions_processed=10,
            outcomes_recorded=8,
            errors=["Error 1", "Error 2"],
        )

        assert result.date == date(2024, 1, 15)
        assert result.sport == "nba"
        assert result.decisions_processed == 10
        assert result.outcomes_recorded == 8
        assert len(result.errors) == 2


class TestPlayerGameResult:
    """Tests for PlayerGameResult dataclass."""

    def test_player_game_result_creation(self):
        """Test creating a PlayerGameResult."""
        result = PlayerGameResult(
            player_name="LeBron James",
            espn_id="12345",
            team="LAL",
            game_date=date(2024, 1, 15),
            fantasy_points=45.5,
            sport="nba",
        )

        assert result.player_name == "LeBron James"
        assert result.espn_id == "12345"
        assert result.team == "LAL"
        assert result.game_date == date(2024, 1, 15)
        assert result.fantasy_points == 45.5
        assert result.sport == "nba"
