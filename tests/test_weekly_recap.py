"""
Tests for the weekly recap generation service.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.weekly_recap import (
    _build_recap_prompt,
    _compute_week_range,
    _fallback_narrative,
    _gather_week_stats,
)


class TestComputeWeekRange:
    """Tests for week date range calculation."""

    def test_monday_returns_same_week(self):
        """Monday should return Mon-Sun of the same week."""
        monday = datetime(2026, 2, 23, 10, 0, tzinfo=UTC)  # Monday
        start, end = _compute_week_range(monday)
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday
        assert start.day == 23
        assert end.day == 1  # March 1

    def test_wednesday_returns_correct_week(self):
        """Mid-week should return the containing Mon-Sun."""
        wednesday = datetime(2026, 2, 25, 15, 30, tzinfo=UTC)
        start, end = _compute_week_range(wednesday)
        assert start.weekday() == 0
        assert start.day == 23  # Monday Feb 23
        assert end.day == 1  # Sunday Mar 1

    def test_sunday_returns_correct_week(self):
        """Sunday should be the end of the current week."""
        sunday = datetime(2026, 3, 1, 20, 0, tzinfo=UTC)
        start, end = _compute_week_range(sunday)
        assert start.weekday() == 0
        assert start.day == 23  # Monday Feb 23

    def test_start_is_midnight(self):
        """Week start should be 00:00:00."""
        ref = datetime(2026, 2, 25, 15, 30, 45, tzinfo=UTC)
        start, _ = _compute_week_range(ref)
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0

    def test_end_is_end_of_day(self):
        """Week end should be 23:59:59."""
        ref = datetime(2026, 2, 25, 10, 0, tzinfo=UTC)
        _, end = _compute_week_range(ref)
        assert end.hour == 23
        assert end.minute == 59
        assert end.second == 59

    def test_none_uses_now(self):
        """None reference should use current time."""
        start, end = _compute_week_range(None)
        assert start.weekday() == 0
        assert end.weekday() == 6
        assert end > start


class TestBuildRecapPrompt:
    """Tests for prompt construction."""

    def test_includes_total_decisions(self):
        stats = {
            "total": 15,
            "correct": 8,
            "incorrect": 3,
            "pending": 4,
            "accuracy_pct": 72.7,
            "avg_confidence": "medium",
            "most_asked_sport": "nfl",
            "sport_breakdown": {"nfl": 10, "nba": 5},
            "decisions": [],
        }
        prompt = _build_recap_prompt(stats, "TestUser", "Week of Feb 23 - Mar 1, 2026")
        assert "Total decisions: 15" in prompt
        assert "Correct: 8" in prompt
        assert "Incorrect: 3" in prompt
        assert "Accuracy: 72.7%" in prompt

    def test_includes_user_name_and_week(self):
        stats = {
            "total": 5,
            "correct": 2,
            "incorrect": 1,
            "pending": 2,
            "accuracy_pct": 66.7,
            "avg_confidence": "high",
            "most_asked_sport": "nba",
            "sport_breakdown": {"nba": 5},
            "decisions": [],
        }
        prompt = _build_recap_prompt(stats, "Alice", "Week of Feb 23")
        assert "Alice" in prompt
        assert "Week of Feb 23" in prompt

    def test_includes_decision_summaries(self):
        stats = {
            "total": 1,
            "correct": 1,
            "incorrect": 0,
            "pending": 0,
            "accuracy_pct": 100.0,
            "avg_confidence": "high",
            "most_asked_sport": "nba",
            "sport_breakdown": {"nba": 1},
            "decisions": [
                {
                    "sport": "nba",
                    "type": "start_sit",
                    "query": "Should I start LeBron or Giannis?",
                    "decision": "Start LeBron",
                    "confidence": "high",
                    "source": "claude",
                    "outcome": "correct",
                    "player_a": "LeBron James",
                    "player_b": "Giannis Antetokounmpo",
                }
            ],
        }
        prompt = _build_recap_prompt(stats, "Bob", "Week of Feb 23")
        assert "LeBron" in prompt
        assert "Giannis" in prompt
        assert "[NBA]" in prompt

    def test_no_accuracy_when_none(self):
        stats = {
            "total": 3,
            "correct": 0,
            "incorrect": 0,
            "pending": 3,
            "accuracy_pct": None,
            "avg_confidence": "medium",
            "most_asked_sport": "nfl",
            "sport_breakdown": {"nfl": 3},
            "decisions": [],
        }
        prompt = _build_recap_prompt(stats, "User", "Week")
        assert "Accuracy:" not in prompt

    def test_limits_to_10_decisions(self):
        decisions = [
            {
                "sport": "nfl",
                "type": "start_sit",
                "query": f"Query {i}",
                "decision": f"Decision {i}",
                "confidence": "medium",
                "source": "local",
                "outcome": "pending",
                "player_a": None,
                "player_b": None,
            }
            for i in range(20)
        ]
        stats = {
            "total": 20,
            "correct": 0,
            "incorrect": 0,
            "pending": 20,
            "accuracy_pct": None,
            "avg_confidence": "medium",
            "most_asked_sport": "nfl",
            "sport_breakdown": {"nfl": 20},
            "decisions": decisions,
        }
        prompt = _build_recap_prompt(stats, "User", "Week")
        # Should only include 10 decision lines
        decision_lines = [line for line in prompt.split("\n") if line.startswith("- [")]
        assert len(decision_lines) == 10


class TestFallbackNarrative:
    """Tests for the non-Claude fallback narrative."""

    def test_includes_total_decisions(self):
        stats = {
            "total": 10,
            "correct": 6,
            "incorrect": 4,
            "pending": 0,
            "accuracy_pct": 60.0,
            "avg_confidence": "medium",
            "most_asked_sport": "nba",
            "sport_breakdown": {"nba": 7, "nfl": 3},
        }
        narrative = _fallback_narrative(stats, "Week of Feb 23 - Mar 1, 2026")
        assert "10 decisions" in narrative
        assert "60.0%" in narrative
        assert "NBA" in narrative

    def test_no_outcomes(self):
        stats = {
            "total": 5,
            "correct": 0,
            "incorrect": 0,
            "pending": 5,
            "accuracy_pct": None,
            "avg_confidence": "low",
            "most_asked_sport": "nfl",
            "sport_breakdown": {"nfl": 5},
        }
        narrative = _fallback_narrative(stats, "Week of Feb 23")
        assert "No outcomes tracked" in narrative

    def test_includes_week_label_as_heading(self):
        stats = {
            "total": 1,
            "correct": 0,
            "incorrect": 0,
            "pending": 1,
            "accuracy_pct": None,
            "avg_confidence": "medium",
            "most_asked_sport": None,
            "sport_breakdown": {},
        }
        narrative = _fallback_narrative(stats, "Week of Mar 2")
        assert "**Week of Mar 2**" in narrative


class TestGatherWeekStats:
    """Tests for the DB aggregation query."""

    @pytest.mark.asyncio
    async def test_returns_zero_total_when_no_decisions(self):
        """Should return total=0 when no decisions found."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        stats = await _gather_week_stats(
            mock_session,
            user_id=1,
            week_start=datetime(2026, 2, 23, tzinfo=UTC),
            week_end=datetime(2026, 3, 1, tzinfo=UTC),
        )
        assert stats["total"] == 0
        assert stats["decisions"] == []

    @pytest.mark.asyncio
    async def test_aggregates_decisions_correctly(self):
        """Should count outcomes and sports correctly."""
        d1 = MagicMock()
        d1.sport = "nfl"
        d1.confidence = "high"
        d1.actual_outcome = "correct"
        d1.decision_type = "start_sit"
        d1.query = "Start Mahomes or Allen?"
        d1.decision = "Start Mahomes"
        d1.source = "claude"
        d1.player_a_name = "Patrick Mahomes"
        d1.player_b_name = "Josh Allen"

        d2 = MagicMock()
        d2.sport = "nfl"
        d2.confidence = "medium"
        d2.actual_outcome = "incorrect"
        d2.decision_type = "start_sit"
        d2.query = "Start Henry or Barkley?"
        d2.decision = "Start Henry"
        d2.source = "local"
        d2.player_a_name = "Derrick Henry"
        d2.player_b_name = "Saquon Barkley"

        d3 = MagicMock()
        d3.sport = "nba"
        d3.confidence = "low"
        d3.actual_outcome = None
        d3.decision_type = "trade"
        d3.query = "Trade Jokic for Embiid?"
        d3.decision = "Keep Jokic"
        d3.source = "claude"
        d3.player_a_name = "Nikola Jokic"
        d3.player_b_name = "Joel Embiid"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [d1, d2, d3]
        mock_session.execute = AsyncMock(return_value=mock_result)

        stats = await _gather_week_stats(
            mock_session,
            user_id=1,
            week_start=datetime(2026, 2, 23, tzinfo=UTC),
            week_end=datetime(2026, 3, 1, tzinfo=UTC),
        )

        assert stats["total"] == 3
        assert stats["correct"] == 1
        assert stats["incorrect"] == 1
        assert stats["pending"] == 1
        assert stats["accuracy_pct"] == 50.0
        assert stats["most_asked_sport"] == "nfl"
        assert stats["avg_confidence"] == "medium"
        assert len(stats["decisions"]) == 3
        assert stats["sport_breakdown"] == {"nfl": 2, "nba": 1}
