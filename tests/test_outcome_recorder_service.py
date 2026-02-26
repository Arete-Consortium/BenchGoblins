"""Tests for Outcome Recorder Service — coverage gap tests.

Targets uncovered lines: 155, 161, 167-168, 194, 251, 310-312,
351-410, 435-443.
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch


from services.outcome_recorder import (
    OutcomeRecordResult,
    determine_outcome,
    fetch_game_results,
    fetch_player_game_result,
    match_decision_to_outcome,
    record_outcomes_for_date,
    record_outcomes_for_date_range,
)


# ---------------------------------------------------------------------------
# fetch_player_game_result — empty game_logs (line 155)
# ---------------------------------------------------------------------------


class TestFetchPlayerGameResultNoLogs:
    """Cover the early return when game_logs is falsy."""

    async def test_returns_none_when_game_logs_empty(self):
        """Line 155: game_logs is an empty list."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=[])

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is None

    async def test_returns_none_when_game_logs_none(self):
        """Line 155: game_logs is None."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=None)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is None


# ---------------------------------------------------------------------------
# fetch_player_game_result — empty date string (line 161)
# ---------------------------------------------------------------------------


class TestFetchPlayerGameResultEmptyDate:
    """Cover the continue when log_date_str is empty."""

    async def test_skips_log_with_empty_date_string(self):
        """Line 161: log has date='' — should be skipped."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        game_logs = [
            {"date": "", "points": 20},
            {"date": "2024-03-01", "points": 30, "rebounds": 5},
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=game_logs)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            # Should skip the empty-date log and find the second one
            assert result is not None
            assert result.game_date == date(2024, 3, 1)

    async def test_skips_log_with_missing_date_key(self):
        """Line 161: log has no 'date' key — get returns '' (default)."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        game_logs = [
            {"points": 20},  # no "date" key at all
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=game_logs)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is None


# ---------------------------------------------------------------------------
# fetch_player_game_result — date parsing error (lines 167-168)
# ---------------------------------------------------------------------------


class TestFetchPlayerGameResultDateParseError:
    """Cover the ValueError/TypeError continue in date parsing."""

    async def test_skips_log_with_unparseable_date(self):
        """Lines 167-168: invalid date string triggers ValueError."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        game_logs = [
            {"date": "not-a-date", "points": 10},
            {"date": "2024-03-01", "points": 25, "rebounds": 6},
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=game_logs)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is not None
            assert result.game_date == date(2024, 3, 1)

    async def test_skips_log_with_partial_date_causing_value_error(self):
        """Lines 167-168: partial/malformed ISO date triggers ValueError in fromisoformat."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        game_logs = [
            {"date": "2024-13-99", "points": 10},  # invalid month/day → ValueError
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=game_logs)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is None

    async def test_all_logs_have_bad_dates_returns_none(self):
        """All logs unparseable — falls through to return None."""
        mock_player_info = MagicMock()
        mock_player_info.id = "1"
        mock_player_info.name = "Test"
        mock_player_info.team_abbrev = "TST"

        game_logs = [
            {"date": "bad1"},
            {"date": "bad2"},
        ]

        with patch("services.outcome_recorder.espn_service") as mock_espn:
            mock_espn.find_player_by_name = AsyncMock(
                return_value=(mock_player_info, None)
            )
            mock_espn.get_player_game_logs = AsyncMock(return_value=game_logs)

            result = await fetch_player_game_result("Test", "nba", date(2024, 3, 1))
            assert result is None


# ---------------------------------------------------------------------------
# fetch_game_results (line 194) — placeholder returns empty list
# ---------------------------------------------------------------------------


class TestFetchGameResults:
    """Cover the placeholder function that returns []."""

    async def test_returns_empty_list(self):
        """Line 194: fetch_game_results always returns []."""
        result = await fetch_game_results(date(2024, 3, 1), "nba")
        assert result == []
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# match_decision_to_outcome — created_at is None (line 251)
# ---------------------------------------------------------------------------


class TestMatchDecisionNoCreatedAt:
    """Cover the early return when decision.created_at is None."""

    async def test_returns_none_none_when_created_at_is_none(self):
        """Line 251: decision_date is None because created_at is None."""
        decision = MagicMock()
        decision.player_a_name = "Player A"
        decision.player_b_name = "Player B"
        decision.sport = "nba"
        decision.created_at = None

        points_a, points_b = await match_decision_to_outcome(decision)
        assert points_a is None
        assert points_b is None


# ---------------------------------------------------------------------------
# determine_outcome — player B mentioned first (lines 310-312)
# ---------------------------------------------------------------------------


class TestDetermineOutcomePlayerBFirst:
    """Cover the branch where player B appears before player A in decision text."""

    def _make_decision(self, text, player_a, player_b):
        decision = MagicMock()
        decision.decision = text
        decision.player_a_name = player_a
        decision.player_b_name = player_b
        return decision

    def test_player_b_mentioned_first_recommended_b_correct(self):
        """Lines 310-312: player B name appears before player A in text.

        Both names present but B appears first → recommended_a = False.
        Player B scores higher → correct.
        """
        decision = self._make_decision(
            "Start PlayerB over PlayerA",
            "PlayerA",
            "PlayerB",
        )
        result = determine_outcome(decision, 15.0, 30.0)
        assert result == "correct"

    def test_player_b_mentioned_first_recommended_b_incorrect(self):
        """Lines 310-312: player B first, but player A actually scores higher."""
        decision = self._make_decision(
            "Start PlayerB over PlayerA",
            "PlayerA",
            "PlayerB",
        )
        result = determine_outcome(decision, 30.0, 15.0)
        assert result == "incorrect"

    def test_player_b_only_in_text_not_a(self):
        """Line 308-309: player B in text but A is not → recommended_a = False."""
        decision = self._make_decision(
            "Start PlayerB tonight",
            "PlayerA",
            "PlayerB",
        )
        result = determine_outcome(decision, 10.0, 25.0)
        assert result == "correct"

    def test_player_a_mentioned_first(self):
        """Player A appears before B in text → recommended_a stays True."""
        decision = self._make_decision(
            "Start PlayerA over PlayerB",
            "PlayerA",
            "PlayerB",
        )
        result = determine_outcome(decision, 30.0, 15.0)
        assert result == "correct"

    def test_neither_player_in_text_defaults_to_a(self):
        """Neither name in text → default recommended_a = True."""
        decision = self._make_decision(
            "Go with the first option",
            "PlayerA",
            "PlayerB",
        )
        result = determine_outcome(decision, 30.0, 15.0)
        assert result == "correct"

    def test_empty_decision_text_defaults_to_a(self):
        """None decision text → defaults to recommending A."""
        decision = self._make_decision(None, "PlayerA", "PlayerB")
        result = determine_outcome(decision, 30.0, 15.0)
        assert result == "correct"


# ---------------------------------------------------------------------------
# record_outcomes_for_date — DB loop (lines 351-410)
# ---------------------------------------------------------------------------


class TestRecordOutcomesForDate:
    """Cover the full DB loop: query decisions, match outcomes, update records."""

    def _mock_decision(self, decision_id, player_a, player_b, sport="nba"):
        """Create a mock Decision row."""
        d = MagicMock()
        d.id = decision_id
        d.player_a_name = player_a
        d.player_b_name = player_b
        d.sport = sport
        d.decision = f"Start {player_a}"
        d.created_at = datetime(2024, 3, 1, 14, 0, 0)
        return d

    def _mock_db_session(self, decisions):
        """Wire up mock db_service with async session context manager."""
        mock_db = MagicMock()
        mock_db.is_configured = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = decisions
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        return mock_db, mock_session

    async def test_records_outcomes_for_matching_decisions(self):
        """Lines 351-402: happy path — decisions fetched, outcomes matched, DB updated."""
        decision = self._mock_decision(1, "Player A", "Player B")
        mock_db, mock_session = self._mock_db_session([decision])

        with (
            patch("services.outcome_recorder.db_service", mock_db),
            patch(
                "services.outcome_recorder.match_decision_to_outcome",
                new_callable=AsyncMock,
                return_value=(30.0, 20.0),
            ),
            patch(
                "services.outcome_recorder.determine_outcome",
                return_value="correct",
            ),
        ):
            result = await record_outcomes_for_date(date(2024, 3, 1), "nba")

        assert result.decisions_processed == 1
        assert result.outcomes_recorded == 1
        assert result.errors == []
        assert result.date == date(2024, 3, 1)
        assert result.sport == "nba"
        # session.execute called at least twice: once for the query, once for the update
        assert mock_session.execute.await_count >= 2

    async def test_skips_decision_when_no_outcome_points(self):
        """Line 380-381: match returns (None, None) — decision is skipped."""
        decision = self._mock_decision(1, "Player A", "Player B")
        mock_db, mock_session = self._mock_db_session([decision])

        with (
            patch("services.outcome_recorder.db_service", mock_db),
            patch(
                "services.outcome_recorder.match_decision_to_outcome",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
        ):
            result = await record_outcomes_for_date(date(2024, 3, 1), "nba")

        assert result.decisions_processed == 1
        assert result.outcomes_recorded == 0
        assert result.errors == []

    async def test_records_error_when_decision_processing_fails(self):
        """Lines 404-405: per-decision exception is caught and appended to errors."""
        decision = self._mock_decision(42, "Player A", "Player B")
        mock_db, mock_session = self._mock_db_session([decision])

        with (
            patch("services.outcome_recorder.db_service", mock_db),
            patch(
                "services.outcome_recorder.match_decision_to_outcome",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ESPN timeout"),
            ),
        ):
            result = await record_outcomes_for_date(date(2024, 3, 1))

        assert result.decisions_processed == 1
        assert result.outcomes_recorded == 0
        assert len(result.errors) == 1
        assert "Error processing decision 42" in result.errors[0]
        assert "ESPN timeout" in result.errors[0]

    async def test_records_database_error(self):
        """Lines 407-408: outer database exception is caught."""
        mock_db = MagicMock()
        mock_db.is_configured = True

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_db.session.return_value = mock_ctx

        with patch("services.outcome_recorder.db_service", mock_db):
            result = await record_outcomes_for_date(date(2024, 3, 1), "nba")

        assert result.decisions_processed == 0
        assert result.outcomes_recorded == 0
        assert len(result.errors) == 1
        assert "Database error" in result.errors[0]
        assert "connection refused" in result.errors[0]

    async def test_no_sport_filter_uses_all_label(self):
        """When sport is None, result.sport should be 'all'."""
        mock_db, _ = self._mock_db_session([])

        with patch("services.outcome_recorder.db_service", mock_db):
            result = await record_outcomes_for_date(date(2024, 3, 1))

        assert result.sport == "all"
        assert result.decisions_processed == 0
        assert result.outcomes_recorded == 0

    async def test_multiple_decisions_mixed_outcomes(self):
        """Multiple decisions: one succeeds, one has no points, one errors."""
        d1 = self._mock_decision(1, "Alpha", "Beta")
        d2 = self._mock_decision(2, "Gamma", "Delta")
        d3 = self._mock_decision(3, "Epsilon", "Zeta")
        mock_db, mock_session = self._mock_db_session([d1, d2, d3])

        async def mock_match(decision):
            if decision.id == 1:
                return 30.0, 20.0
            if decision.id == 2:
                return None, None
            raise RuntimeError("fetch failed")

        with (
            patch("services.outcome_recorder.db_service", mock_db),
            patch(
                "services.outcome_recorder.match_decision_to_outcome",
                new_callable=AsyncMock,
                side_effect=mock_match,
            ),
            patch(
                "services.outcome_recorder.determine_outcome",
                return_value="correct",
            ),
        ):
            result = await record_outcomes_for_date(date(2024, 3, 1), "nba")

        assert result.decisions_processed == 3
        assert result.outcomes_recorded == 1
        assert len(result.errors) == 1
        assert "decision 3" in result.errors[0]


# ---------------------------------------------------------------------------
# record_outcomes_for_date_range (lines 435-443)
# ---------------------------------------------------------------------------


class TestRecordOutcomesForDateRange:
    """Cover the date range iteration loop."""

    async def test_iterates_over_date_range(self):
        """Lines 435-443: iterates from start to end, collecting results."""
        start = date(2024, 3, 1)
        end = date(2024, 3, 3)

        mock_results = {
            date(2024, 3, 1): OutcomeRecordResult(
                date=date(2024, 3, 1),
                sport="nba",
                decisions_processed=2,
                outcomes_recorded=1,
                errors=[],
            ),
            date(2024, 3, 2): OutcomeRecordResult(
                date=date(2024, 3, 2),
                sport="nba",
                decisions_processed=3,
                outcomes_recorded=2,
                errors=[],
            ),
            date(2024, 3, 3): OutcomeRecordResult(
                date=date(2024, 3, 3),
                sport="nba",
                decisions_processed=0,
                outcomes_recorded=0,
                errors=[],
            ),
        }

        async def mock_record(target_date, sport=None):
            return mock_results[target_date]

        with patch(
            "services.outcome_recorder.record_outcomes_for_date",
            new_callable=AsyncMock,
            side_effect=mock_record,
        ):
            results = await record_outcomes_for_date_range(start, end, sport="nba")

        assert len(results) == 3
        assert results[0].date == date(2024, 3, 1)
        assert results[1].date == date(2024, 3, 2)
        assert results[2].date == date(2024, 3, 3)
        assert sum(r.decisions_processed for r in results) == 5
        assert sum(r.outcomes_recorded for r in results) == 3

    async def test_single_day_range(self):
        """Start == end → one call."""
        target = date(2024, 3, 1)
        expected = OutcomeRecordResult(
            date=target,
            sport="all",
            decisions_processed=1,
            outcomes_recorded=1,
            errors=[],
        )

        with patch(
            "services.outcome_recorder.record_outcomes_for_date",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            results = await record_outcomes_for_date_range(target, target)

        assert len(results) == 1
        assert results[0] is expected

    async def test_empty_range_returns_empty(self):
        """Start > end → no iterations, empty list."""
        with patch(
            "services.outcome_recorder.record_outcomes_for_date",
            new_callable=AsyncMock,
        ) as mock_record:
            results = await record_outcomes_for_date_range(
                date(2024, 3, 5), date(2024, 3, 1)
            )

        assert results == []
        mock_record.assert_not_awaited()

    async def test_passes_sport_to_each_call(self):
        """Sport kwarg is forwarded to each record_outcomes_for_date call."""
        expected = OutcomeRecordResult(
            date=date(2024, 3, 1),
            sport="nfl",
            decisions_processed=0,
            outcomes_recorded=0,
            errors=[],
        )

        with patch(
            "services.outcome_recorder.record_outcomes_for_date",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_record:
            await record_outcomes_for_date_range(
                date(2024, 3, 1), date(2024, 3, 2), sport="nfl"
            )

        assert mock_record.await_count == 2
        for call in mock_record.call_args_list:
            assert (
                call.args[1]
                if len(call.args) > 1
                else call.kwargs.get("sport") == "nfl"
            )
