"""Tests for the core verdict engine."""

from core.scoring import IndexScores, PlayerStats
from core.verdicts import Verdict, _margin_to_confidence, generate_verdict


def _make_player(name="Player A", sport="nfl", **overrides):
    """Create a PlayerStats with sensible defaults."""
    defaults = {
        "player_id": name.lower().replace(" ", "_"),
        "name": name,
        "team": "KC",
        "position": "QB",
        "sport": sport,
        "minutes_per_game": 60.0,
        "usage_rate": 25.0,
        "points_per_game": 22.0,
        "assists_per_game": 6.0,
        "rebounds_per_game": 1.0,
        "field_goal_pct": 0.65,
        "three_point_pct": 0.0,
        "is_starter": True,
        "games_started_pct": 1.0,
        "games_played": 15,
        "minutes_trend": 0.0,
        "usage_trend": 0.0,
        "points_trend": 0.0,
        "targets": 0.0,
        "receptions": 0.0,
        "snap_pct": 100.0,
    }
    defaults.update(overrides)
    return PlayerStats(**defaults)


class TestMarginToConfidence:
    def test_zero_margin(self):
        assert _margin_to_confidence(0) == 0

    def test_negative_margin(self):
        assert _margin_to_confidence(-5) == 0

    def test_small_margin(self):
        assert _margin_to_confidence(5) == 20

    def test_medium_margin(self):
        assert _margin_to_confidence(15) == 60

    def test_large_margin(self):
        assert _margin_to_confidence(25) == 100

    def test_over_25(self):
        assert _margin_to_confidence(50) == 100

    def test_scales_linearly(self):
        c10 = _margin_to_confidence(10)
        c20 = _margin_to_confidence(20)
        assert c20 > c10


class TestGenerateVerdict:
    def test_clear_winner(self):
        """Player A dominates when given much better stats."""
        strong = _make_player(
            "Star QB",
            points_per_game=30.0,
            usage_rate=35.0,
            minutes_trend=5.0,
            points_trend=3.0,
        )
        weak = _make_player(
            "Bench QB",
            team="NYJ",
            points_per_game=12.0,
            usage_rate=15.0,
            minutes_trend=-2.0,
            points_trend=-1.0,
        )

        verdict = generate_verdict(strong, weak)

        assert isinstance(verdict, Verdict)
        assert verdict.decision == "Start Star QB"
        assert verdict.confidence > 0
        assert verdict.floor.winner == "Star QB"
        assert verdict.median.winner == "Star QB"
        assert verdict.ceiling.winner == "Star QB"

    def test_split_decision_median_tiebreaker(self):
        """When modes disagree, median breaks the tie."""
        # Player A: high floor (safe) but low ceiling
        safe_player = _make_player(
            "Safe Player",
            points_per_game=18.0,
            usage_rate=20.0,
            is_starter=True,
            games_started_pct=1.0,
            minutes_trend=0.0,
            points_trend=0.0,
        )
        # Player B: low floor but high ceiling (boom/bust)
        boom_player = _make_player(
            "Boom Player",
            team="BUF",
            points_per_game=20.0,
            usage_rate=30.0,
            is_starter=True,
            games_started_pct=0.7,
            minutes_trend=3.0,
            points_trend=5.0,
        )

        verdict = generate_verdict(safe_player, boom_player)

        assert isinstance(verdict, Verdict)
        # Winner should be determined by majority or median tiebreak
        assert verdict.decision.startswith("Start ")
        # All 3 breakdowns should exist
        assert verdict.floor.margin >= 0
        assert verdict.median.margin >= 0
        assert verdict.ceiling.margin >= 0

    def test_close_matchup_low_confidence(self):
        """Near-identical players should produce low confidence."""
        player_a = _make_player("Player A", points_per_game=20.0, usage_rate=25.0)
        player_b = _make_player(
            "Player B", team="BUF", points_per_game=20.0, usage_rate=25.0
        )

        verdict = generate_verdict(player_a, player_b)

        assert verdict.confidence < 30
        assert verdict.margin < 5

    def test_confidence_scaling(self):
        """Wider margin should produce higher confidence."""
        base = _make_player("Base", points_per_game=15.0, usage_rate=15.0)
        strong = _make_player(
            "Strong",
            team="BUF",
            points_per_game=30.0,
            usage_rate=35.0,
            minutes_trend=5.0,
        )
        close = _make_player(
            "Close",
            team="SF",
            points_per_game=16.0,
            usage_rate=16.0,
        )

        wide_verdict = generate_verdict(base, strong)
        close_verdict = generate_verdict(base, close)

        assert wide_verdict.confidence > close_verdict.confidence

    def test_risk_breakdown_structure(self):
        """All 3 risk modes should be present with correct fields."""
        a = _make_player("A", points_per_game=22.0)
        b = _make_player("B", team="BUF", points_per_game=18.0)

        verdict = generate_verdict(a, b)

        for bd in (verdict.floor, verdict.median, verdict.ceiling):
            assert isinstance(bd.score_a, float)
            assert isinstance(bd.score_b, float)
            assert isinstance(bd.winner, str)
            assert isinstance(bd.margin, float)
            assert bd.margin >= 0
            assert bd.winner in ("A", "B")

    def test_indices_present(self):
        """Indices should be calculated for both players."""
        a = _make_player("A")
        b = _make_player("B", team="BUF")

        verdict = generate_verdict(a, b)

        assert isinstance(verdict.indices_a, IndexScores)
        assert isinstance(verdict.indices_b, IndexScores)
        assert verdict.player_a_name == "A"
        assert verdict.player_b_name == "B"

    def test_scores_within_range(self):
        """All scores should be 0-100."""
        a = _make_player("A", points_per_game=30.0, usage_rate=35.0)
        b = _make_player("B", team="BUF", points_per_game=5.0, usage_rate=5.0)

        verdict = generate_verdict(a, b)

        for bd in (verdict.floor, verdict.median, verdict.ceiling):
            assert 0 <= bd.score_a <= 100
            assert 0 <= bd.score_b <= 100

    def test_margin_is_average(self):
        """Verdict margin should be average of all 3 mode margins."""
        a = _make_player("A", points_per_game=25.0, usage_rate=30.0)
        b = _make_player("B", team="BUF", points_per_game=15.0, usage_rate=18.0)

        verdict = generate_verdict(a, b)

        expected_avg = (
            verdict.floor.margin + verdict.median.margin + verdict.ceiling.margin
        ) / 3
        assert abs(verdict.margin - round(expected_avg, 1)) < 0.2
