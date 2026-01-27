"""Tests for Decision Accuracy Tracking."""

from services.accuracy import AccuracyMetrics, AccuracyTracker, DecisionOutcome


class TestDecisionOutcome:
    def test_record_and_retrieve(self):
        tracker = AccuracyTracker()
        outcome = DecisionOutcome(
            decision_id="d1",
            actual_points_a=28.5,
            actual_points_b=15.2,
        )
        tracker.record_outcome(outcome)
        assert tracker.get_outcome("d1") is not None
        assert tracker.get_outcome("d1").actual_points_a == 28.5

    def test_missing_outcome(self):
        tracker = AccuracyTracker()
        assert tracker.get_outcome("nonexistent") is None

    def test_overwrite_outcome(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=10.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=20.0))
        assert tracker.get_outcome("d1").actual_points_a == 20.0


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

    def test_confidence_accuracy(self):
        m = AccuracyMetrics(high_confidence_total=10, high_confidence_correct=8)
        assert m.confidence_accuracy("high") == 80.0
        assert m.confidence_accuracy("low") == 0.0  # No low data


class TestComputeMetrics:
    def _make_decision(self, id, sport="nba", confidence="medium", source="local",
                       decision="Start Player A", player_a_name="Player A"):
        return {
            "id": id,
            "sport": sport,
            "confidence": confidence,
            "source": source,
            "decision": decision,
            "player_a_name": player_a_name,
        }

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
        tracker.record_outcome(DecisionOutcome(
            decision_id="d1", actual_points_a=30.0, actual_points_b=15.0,
        ))
        decisions = [self._make_decision("d1")]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.correct_decisions == 1
        assert metrics.incorrect_decisions == 0
        assert metrics.accuracy_pct == 100.0

    def test_incorrect_decision(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(
            decision_id="d1", actual_points_a=10.0, actual_points_b=25.0,
        ))
        decisions = [self._make_decision("d1")]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.correct_decisions == 0
        assert metrics.incorrect_decisions == 1

    def test_push_within_one_point(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(
            decision_id="d1", actual_points_a=20.0, actual_points_b=20.5,
        ))
        decisions = [self._make_decision("d1")]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.pushes == 1
        assert metrics.correct_decisions == 0
        assert metrics.incorrect_decisions == 0

    def test_by_confidence(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=30.0, actual_points_b=10.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d2", actual_points_a=5.0, actual_points_b=25.0))
        decisions = [
            self._make_decision("d1", confidence="high"),
            self._make_decision("d2", confidence="low"),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.high_confidence_total == 1
        assert metrics.high_confidence_correct == 1
        assert metrics.low_confidence_total == 1
        assert metrics.low_confidence_correct == 0

    def test_by_source(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=30.0, actual_points_b=10.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d2", actual_points_a=30.0, actual_points_b=10.0))
        decisions = [
            self._make_decision("d1", source="local"),
            self._make_decision("d2", source="claude"),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.local_total == 1
        assert metrics.local_correct == 1
        assert metrics.claude_total == 1
        assert metrics.claude_correct == 1

    def test_by_sport(self):
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=30.0, actual_points_b=10.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d2", actual_points_a=30.0, actual_points_b=10.0))
        decisions = [
            self._make_decision("d1", sport="nba"),
            self._make_decision("d2", sport="nfl"),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert "nba" in metrics.by_sport
        assert "nfl" in metrics.by_sport
        assert metrics.by_sport["nba"]["correct"] == 1
        assert metrics.by_sport["nfl"]["correct"] == 1

    def test_mixed_outcomes(self):
        """Integration test: mix of correct, incorrect, pushes, and missing."""
        tracker = AccuracyTracker()
        tracker.record_outcome(DecisionOutcome(decision_id="d1", actual_points_a=30.0, actual_points_b=10.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d2", actual_points_a=10.0, actual_points_b=30.0))
        tracker.record_outcome(DecisionOutcome(decision_id="d3", actual_points_a=20.0, actual_points_b=20.3))
        # d4 has no outcome
        decisions = [
            self._make_decision("d1"),
            self._make_decision("d2"),
            self._make_decision("d3"),
            self._make_decision("d4"),
        ]
        metrics = tracker.compute_metrics(decisions)
        assert metrics.total_decisions == 4
        assert metrics.decisions_with_outcomes == 3
        assert metrics.correct_decisions == 1
        assert metrics.incorrect_decisions == 1
        assert metrics.pushes == 1
        assert metrics.accuracy_pct == 50.0
        assert metrics.coverage_pct == 75.0
