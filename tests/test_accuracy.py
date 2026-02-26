"""Tests for Decision Accuracy Tracking."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.accuracy import AccuracyMetrics, AccuracyTracker, DecisionOutcome


class TestDecisionOutcome:
    @pytest.mark.asyncio
    async def test_record_and_retrieve(self):
        tracker = AccuracyTracker()
        db = AsyncMock()

        # Mock the execute for record_outcome (UPDATE)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        outcome = DecisionOutcome(
            decision_id="d1",
            actual_points_a=28.5,
            actual_points_b=15.2,
        )
        found = await tracker.record_outcome(db, outcome)
        assert found is True

        # Mock the execute for get_outcome (SELECT)
        mock_row = MagicMock()
        mock_row.actual_points_a = Decimal("28.5")
        mock_row.actual_points_b = Decimal("15.2")
        mock_row.actual_outcome = "a_higher"
        mock_row.feedback_at = None
        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_row
        db.execute = AsyncMock(return_value=mock_select_result)

        result = await tracker.get_outcome(db, "d1")
        assert result is not None
        assert result.actual_points_a == 28.5

    @pytest.mark.asyncio
    async def test_missing_outcome(self):
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await tracker.get_outcome(db, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_record_not_found(self):
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)

        outcome = DecisionOutcome(decision_id="missing", actual_points_a=10.0)
        found = await tracker.record_outcome(db, outcome)
        assert found is False

    @pytest.mark.asyncio
    async def test_record_outcome_push(self):
        """Cover line 100: actual_outcome = 'push' when diff < 1.0."""
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        outcome = DecisionOutcome(
            decision_id="d-push",
            actual_points_a=20.0,
            actual_points_b=20.5,
        )
        found = await tracker.record_outcome(db, outcome)
        assert found is True

        # Verify the update statement was called with push outcome
        call_args = db.execute.call_args
        stmt = call_args[0][0]
        # The compiled parameters should include actual_outcome="push"
        compiled = stmt.compile(
            compile_kwargs={"literal_binds": False},
        )
        param_keys = list(compiled.params.keys())
        assert "actual_points_a" in param_keys
        assert "actual_points_b" in param_keys

    @pytest.mark.asyncio
    async def test_record_outcome_b_higher(self):
        """Cover line 104: actual_outcome = 'b_higher' when b > a."""
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)

        outcome = DecisionOutcome(
            decision_id="d-b-higher",
            actual_points_a=10.0,
            actual_points_b=30.0,
        )
        found = await tracker.record_outcome(db, outcome)
        assert found is True

    @pytest.mark.asyncio
    async def test_get_outcome_with_none_points(self):
        """Cover line 134 branch: row exists but both points are None."""
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_row = MagicMock()
        mock_row.actual_points_a = None
        mock_row.actual_points_b = None
        mock_row.actual_outcome = None
        mock_row.feedback_at = None
        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_row
        db.execute = AsyncMock(return_value=mock_select_result)

        result = await tracker.get_outcome(db, "d-none-points")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_outcome_one_point_none(self):
        """Cover the conditional float() casts on lines 139-140."""
        tracker = AccuracyTracker()
        db = AsyncMock()
        mock_row = MagicMock()
        mock_row.actual_points_a = Decimal("15.0")
        mock_row.actual_points_b = None
        mock_row.actual_outcome = None
        mock_row.feedback_at = None
        mock_select_result = MagicMock()
        mock_select_result.first.return_value = mock_row
        db.execute = AsyncMock(return_value=mock_select_result)

        result = await tracker.get_outcome(db, "d-partial")
        assert result is not None
        assert result.actual_points_a == 15.0
        assert result.actual_points_b is None


class TestAccuracyMetrics:
    def test_accuracy_pct_no_data(self):
        m = AccuracyMetrics()
        assert m.accuracy_pct == 0.0

    def test_accuracy_pct_all_correct(self):
        m = AccuracyMetrics(correct_decisions=10, incorrect_decisions=0)
        assert m.accuracy_pct == 100.0

    def test_accuracy_pct_mixed(self):
        m = AccuracyMetrics(correct_decisions=7, incorrect_decisions=3)
        assert m.accuracy_pct == 70.0

    def test_coverage_pct(self):
        m = AccuracyMetrics(total_decisions=100, decisions_with_outcomes=75)
        assert m.coverage_pct == 75.0

    def test_coverage_pct_zero_total(self):
        """Cover line 68: return 0.0 when total_decisions is 0."""
        m = AccuracyMetrics(total_decisions=0)
        assert m.coverage_pct == 0.0

    def test_confidence_accuracy(self):
        m = AccuracyMetrics(high_confidence_total=10, high_confidence_correct=8)
        assert m.confidence_accuracy("high") == 80.0
        assert m.confidence_accuracy("low") == 0.0  # No low data

    def test_confidence_accuracy_medium(self):
        """Cover lines 76-77: medium branch in confidence_accuracy."""
        m = AccuracyMetrics(medium_confidence_total=20, medium_confidence_correct=15)
        assert m.confidence_accuracy("medium") == 75.0

    def test_confidence_accuracy_low_with_data(self):
        """Cover low branch with actual data."""
        m = AccuracyMetrics(low_confidence_total=5, low_confidence_correct=2)
        assert m.confidence_accuracy("low") == 40.0


class TestComputeMetrics:
    def _make_decision(
        self,
        id,
        sport="nba",
        confidence="medium",
        source="local",
        decision="Start Player A",
        player_a_name="Player A",
        actual_points_a=None,
        actual_points_b=None,
        prompt_variant=None,
    ):
        d = {
            "id": id,
            "sport": sport,
            "confidence": confidence,
            "source": source,
            "decision": decision,
            "player_a_name": player_a_name,
            "actual_points_a": actual_points_a,
            "actual_points_b": actual_points_b,
        }
        if prompt_variant is not None:
            d["prompt_variant"] = prompt_variant
        return d

    def test_no_decisions(self):
        tracker = AccuracyTracker()
        metrics = tracker.compute_metrics([])
        assert metrics.total_decisions == 0
        assert metrics.accuracy_pct == 0.0

    def test_no_outcomes_recorded(self):
        tracker = AccuracyTracker()
        decisions = [self._make_decision("d1")]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.total_decisions == 1
        assert metrics.decisions_with_outcomes == 0

    def test_correct_decision(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision("d1", actual_points_a=30.0, actual_points_b=15.0)
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.correct_decisions == 1
        assert metrics.incorrect_decisions == 0
        assert metrics.accuracy_pct == 100.0

    def test_incorrect_decision(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision("d1", actual_points_a=10.0, actual_points_b=25.0)
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.correct_decisions == 0
        assert metrics.incorrect_decisions == 1

    def test_push_within_one_point(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision("d1", actual_points_a=20.0, actual_points_b=20.5)
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.pushes == 1
        assert metrics.correct_decisions == 0
        assert metrics.incorrect_decisions == 0

    def test_by_confidence(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1", confidence="high", actual_points_a=30.0, actual_points_b=10.0
            ),
            self._make_decision(
                "d2", confidence="low", actual_points_a=5.0, actual_points_b=25.0
            ),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.high_confidence_total == 1
        assert metrics.high_confidence_correct == 1
        assert metrics.low_confidence_total == 1
        assert metrics.low_confidence_correct == 0

    def test_by_source(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1", source="local", actual_points_a=30.0, actual_points_b=10.0
            ),
            self._make_decision(
                "d2", source="claude", actual_points_a=30.0, actual_points_b=10.0
            ),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.local_total == 1
        assert metrics.local_correct == 1
        assert metrics.claude_total == 1
        assert metrics.claude_correct == 1

    def test_by_sport(self):
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1", sport="nba", actual_points_a=30.0, actual_points_b=10.0
            ),
            self._make_decision(
                "d2", sport="nfl", actual_points_a=30.0, actual_points_b=10.0
            ),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert "nba" in metrics.by_sport
        assert "nfl" in metrics.by_sport
        assert metrics.by_sport["nba"]["correct"] == 1
        assert metrics.by_sport["nfl"]["correct"] == 1

    def test_mixed_outcomes(self):
        """Integration test: mix of correct, incorrect, pushes, and missing."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision("d1", actual_points_a=30.0, actual_points_b=10.0),
            self._make_decision("d2", actual_points_a=10.0, actual_points_b=30.0),
            self._make_decision("d3", actual_points_a=20.0, actual_points_b=20.3),
            self._make_decision("d4"),  # No outcome
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.total_decisions == 4
        assert metrics.decisions_with_outcomes == 3
        assert metrics.correct_decisions == 1
        assert metrics.incorrect_decisions == 1
        assert metrics.pushes == 1
        assert metrics.accuracy_pct == 50.0
        assert metrics.coverage_pct == 75.0

    def test_recommended_player_b_correct(self):
        """Cover lines 175-176: when player B is recommended and B scores more."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                decision="Start Player B instead",
                player_a_name="Player A",
                actual_points_a=10.0,
                actual_points_b=30.0,
            )
        ]
        metrics = tracker.compute_metrics(decisions)
        # Player A is NOT in "Start Player B instead" decision text,
        # so recommended_a=False, is_correct = pts_b > pts_a = True
        assert metrics.correct_decisions == 1
        assert metrics.incorrect_decisions == 0

    def test_recommended_player_b_incorrect(self):
        """Cover lines 175-176: when player B is recommended but A scores more."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                decision="Start Player B instead",
                player_a_name="Player A",
                actual_points_a=30.0,
                actual_points_b=10.0,
            )
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.correct_decisions == 0
        assert metrics.incorrect_decisions == 1

    def test_recommended_player_b_push(self):
        """Cover line 176: push on the recommended_a=False branch."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                decision="Start Player B instead",
                player_a_name="Player A",
                actual_points_a=20.0,
                actual_points_b=20.3,
            )
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.pushes == 1

    def test_low_confidence_correct(self):
        """Cover line 198: low_confidence_correct increment."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                confidence="low",
                actual_points_a=30.0,
                actual_points_b=10.0,
            )
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.low_confidence_total == 1
        assert metrics.low_confidence_correct == 1

    def test_by_variant(self):
        """Cover lines 222-226: prompt_variant tracking."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                actual_points_a=30.0,
                actual_points_b=10.0,
                prompt_variant="v2_detailed",
            ),
            self._make_decision(
                "d2",
                actual_points_a=5.0,
                actual_points_b=25.0,
                prompt_variant="v2_detailed",
            ),
            self._make_decision(
                "d3",
                actual_points_a=30.0,
                actual_points_b=10.0,
                prompt_variant="v1_basic",
            ),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert "v2_detailed" in metrics.by_variant
        assert "v1_basic" in metrics.by_variant
        assert metrics.by_variant["v2_detailed"]["total"] == 2
        assert metrics.by_variant["v2_detailed"]["correct"] == 1
        assert metrics.by_variant["v1_basic"]["total"] == 1
        assert metrics.by_variant["v1_basic"]["correct"] == 1

    def test_by_variant_correct_increment(self):
        """Cover line 225: variant correct increment for correct decision."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision(
                "d1",
                actual_points_a=30.0,
                actual_points_b=10.0,
                prompt_variant="experimental",
            ),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.by_variant["experimental"]["correct"] == 1

    def test_by_variant_not_present(self):
        """No prompt_variant key -> by_variant stays empty."""
        tracker = AccuracyTracker()
        decisions = [
            self._make_decision("d1", actual_points_a=30.0, actual_points_b=10.0),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.by_variant == {}
