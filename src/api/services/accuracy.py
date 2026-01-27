"""
Decision Accuracy Tracking Service.

Records outcomes for past decisions and computes accuracy metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecisionOutcome:
    """Outcome data for a single decision."""

    decision_id: str
    actual_points_a: float | None = None
    actual_points_b: float | None = None
    user_followed: bool | None = None  # Did the user play the recommended player?
    feedback_note: str | None = None


@dataclass
class AccuracyMetrics:
    """Aggregate accuracy metrics."""

    total_decisions: int = 0
    decisions_with_outcomes: int = 0
    correct_decisions: int = 0  # Recommended player scored more
    incorrect_decisions: int = 0
    pushes: int = 0  # Margin < 1 point

    # By confidence level
    high_confidence_total: int = 0
    high_confidence_correct: int = 0
    medium_confidence_total: int = 0
    medium_confidence_correct: int = 0
    low_confidence_total: int = 0
    low_confidence_correct: int = 0

    # By sport
    by_sport: dict[str, dict] = field(default_factory=dict)

    # By source (local vs claude)
    local_total: int = 0
    local_correct: int = 0
    claude_total: int = 0
    claude_correct: int = 0

    @property
    def accuracy_pct(self) -> float:
        evaluated = self.correct_decisions + self.incorrect_decisions
        if evaluated == 0:
            return 0.0
        return round(self.correct_decisions / evaluated * 100, 1)

    @property
    def coverage_pct(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        return round(self.decisions_with_outcomes / self.total_decisions * 100, 1)

    def confidence_accuracy(self, level: str) -> float:
        if level == "high":
            total = self.high_confidence_total
            correct = self.high_confidence_correct
        elif level == "medium":
            total = self.medium_confidence_total
            correct = self.medium_confidence_correct
        else:
            total = self.low_confidence_total
            correct = self.low_confidence_correct
        return round(correct / total * 100, 1) if total > 0 else 0.0


class AccuracyTracker:
    """
    Tracks decision outcomes and computes accuracy metrics.

    Designed to work with in-memory decision store (list of dicts)
    or database Decision rows.
    """

    def __init__(self):
        # In-memory store for portfolio demo; production would use DB
        self._outcomes: dict[str, DecisionOutcome] = {}

    def record_outcome(self, outcome: DecisionOutcome) -> None:
        """Record the actual outcome for a decision."""
        self._outcomes[outcome.decision_id] = outcome

    def get_outcome(self, decision_id: str) -> DecisionOutcome | None:
        return self._outcomes.get(decision_id)

    def compute_metrics(self, decisions: list[dict]) -> AccuracyMetrics:
        """
        Compute accuracy metrics from a list of decision dicts.

        Each decision dict should have:
        - id, sport, confidence, source, decision, player_a_name, player_b_name
        """
        metrics = AccuracyMetrics()
        metrics.total_decisions = len(decisions)

        for dec in decisions:
            dec_id = str(dec.get("id", ""))
            outcome = self._outcomes.get(dec_id)
            if not outcome or (outcome.actual_points_a is None and outcome.actual_points_b is None):
                continue

            metrics.decisions_with_outcomes += 1
            pts_a = outcome.actual_points_a or 0.0
            pts_b = outcome.actual_points_b or 0.0

            # Determine which player was recommended
            decision_text = dec.get("decision", "")
            player_a_name = dec.get("player_a_name", "")
            recommended_a = player_a_name.lower() in decision_text.lower() if player_a_name else True

            if recommended_a:
                is_correct = pts_a > pts_b
                is_push = abs(pts_a - pts_b) < 1.0
            else:
                is_correct = pts_b > pts_a
                is_push = abs(pts_a - pts_b) < 1.0

            if is_push:
                metrics.pushes += 1
            elif is_correct:
                metrics.correct_decisions += 1
            else:
                metrics.incorrect_decisions += 1

            # By confidence
            confidence = dec.get("confidence", "medium")
            if confidence == "high":
                metrics.high_confidence_total += 1
                if is_correct:
                    metrics.high_confidence_correct += 1
            elif confidence == "medium":
                metrics.medium_confidence_total += 1
                if is_correct:
                    metrics.medium_confidence_correct += 1
            else:
                metrics.low_confidence_total += 1
                if is_correct:
                    metrics.low_confidence_correct += 1

            # By source
            source = dec.get("source", "local")
            if source == "claude":
                metrics.claude_total += 1
                if is_correct:
                    metrics.claude_correct += 1
            else:
                metrics.local_total += 1
                if is_correct:
                    metrics.local_correct += 1

            # By sport
            sport = dec.get("sport", "unknown")
            if sport not in metrics.by_sport:
                metrics.by_sport[sport] = {"total": 0, "correct": 0}
            metrics.by_sport[sport]["total"] += 1
            if is_correct:
                metrics.by_sport[sport]["correct"] += 1

        return metrics
