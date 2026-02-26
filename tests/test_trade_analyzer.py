"""
Tests for the trade analyzer feature.

Covers: evaluate_trade core function, TradeResult/TradeSide/PlayerBreakdown
dataclasses, extract_trade_players parsing, classify_trade_query routing,
can_analyze_locally checks, and full /decide trade endpoint integration.
"""

import pytest
from core.scoring import PlayerStats, RiskMode, evaluate_trade


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def star_player():
    """High-quality NBA player."""
    return PlayerStats(
        player_id="s1",
        name="Star Player",
        team="LAL",
        position="SF",
        sport="nba",
        minutes_per_game=36.0,
        usage_rate=30.0,
        points_per_game=28.5,
        assists_per_game=7.0,
        rebounds_per_game=8.0,
        field_goal_pct=0.510,
        three_point_pct=0.390,
        is_starter=True,
        games_started_pct=1.0,
        games_played=60,
        minutes_trend=1.0,
        usage_trend=0.5,
        points_trend=2.0,
    )


@pytest.fixture
def role_player_a():
    """Decent NBA role player."""
    return PlayerStats(
        player_id="r1",
        name="Role Player A",
        team="BOS",
        position="SG",
        sport="nba",
        minutes_per_game=28.0,
        usage_rate=20.0,
        points_per_game=15.0,
        assists_per_game=3.5,
        rebounds_per_game=4.0,
        field_goal_pct=0.460,
        three_point_pct=0.370,
        is_starter=True,
        games_started_pct=0.9,
        games_played=55,
        minutes_trend=0.5,
        usage_trend=0.2,
        points_trend=0.5,
    )


@pytest.fixture
def role_player_b():
    """Decent NBA role player (slightly worse)."""
    return PlayerStats(
        player_id="r2",
        name="Role Player B",
        team="MIA",
        position="PF",
        sport="nba",
        minutes_per_game=26.0,
        usage_rate=18.0,
        points_per_game=13.5,
        assists_per_game=2.0,
        rebounds_per_game=5.5,
        field_goal_pct=0.450,
        three_point_pct=0.340,
        is_starter=True,
        games_started_pct=0.85,
        games_played=52,
        minutes_trend=0.0,
        usage_trend=-0.3,
        points_trend=-0.5,
    )


@pytest.fixture
def bench_player():
    """Low-end NBA bench player."""
    return PlayerStats(
        player_id="b1",
        name="Bench Player",
        team="CHA",
        position="PG",
        sport="nba",
        minutes_per_game=18.0,
        usage_rate=14.0,
        points_per_game=8.0,
        assists_per_game=2.5,
        rebounds_per_game=2.0,
        field_goal_pct=0.420,
        three_point_pct=0.310,
        is_starter=False,
        games_started_pct=0.15,
        games_played=40,
        minutes_trend=-1.0,
        usage_trend=-0.5,
        points_trend=-1.5,
    )


# =============================================================================
# TEST evaluate_trade() CORE FUNCTION
# =============================================================================


class TestEvaluateTrade:
    """Tests for the core evaluate_trade function."""

    def test_1v1_star_vs_bench_accept(self, bench_player, star_player):
        """Trading a bench player for a star should be 'Accept Trade'."""
        result = evaluate_trade([bench_player], [star_player], RiskMode.MEDIAN)

        assert result["decision"] == "Accept Trade"
        assert result["net_value"] > 0
        assert result["side_b_total"] > result["side_a_total"]
        assert len(result["side_a_players"]) == 1
        assert len(result["side_b_players"]) == 1

    def test_1v1_star_vs_bench_reject(self, star_player, bench_player):
        """Trading a star for a bench player should be 'Reject Trade'."""
        result = evaluate_trade([star_player], [bench_player], RiskMode.MEDIAN)

        assert result["decision"] == "Reject Trade"
        assert result["net_value"] < 0

    def test_2_for_1_trade(self, star_player, role_player_a, role_player_b):
        """Two role players for a star — tests multi-player evaluation."""
        result = evaluate_trade(
            [role_player_a, role_player_b], [star_player], RiskMode.MEDIAN
        )

        assert result["decision"] in ("Accept Trade", "Reject Trade")
        assert len(result["side_a_players"]) == 2
        assert len(result["side_b_players"]) == 1
        # Total should be sum of individual scores
        a_sum = sum(p["score"] for p in result["side_a_players"])
        assert abs(result["side_a_total"] - round(a_sum, 1)) < 0.2

    def test_confidence_low_close_trade(self, role_player_a, role_player_b):
        """Close trade should have low confidence."""
        result = evaluate_trade([role_player_a], [role_player_b], RiskMode.MEDIAN)

        # These are similar players, so margin should be small
        player_count = 2
        avg_margin = abs(result["net_value"]) / player_count
        if avg_margin < 3:
            assert result["confidence"] == "low"

    def test_confidence_high_lopsided_trade(self, star_player, bench_player):
        """Lopsided trade should have high confidence."""
        result = evaluate_trade([bench_player], [star_player], RiskMode.MEDIAN)

        player_count = 2
        avg_margin = abs(result["net_value"]) / player_count
        if avg_margin >= 8:
            assert result["confidence"] == "high"

    def test_floor_mode(self, star_player, role_player_a):
        """Trade evaluation works with floor risk mode."""
        result = evaluate_trade([role_player_a], [star_player], RiskMode.FLOOR)

        assert result["decision"] in ("Accept Trade", "Reject Trade")
        assert "confidence" in result

    def test_ceiling_mode(self, star_player, role_player_a):
        """Trade evaluation works with ceiling risk mode."""
        result = evaluate_trade([role_player_a], [star_player], RiskMode.CEILING)

        assert result["decision"] in ("Accept Trade", "Reject Trade")
        assert "confidence" in result

    def test_all_risk_modes_produce_scores(self, star_player, bench_player):
        """All three risk modes produce valid numeric results."""
        for mode in RiskMode:
            result = evaluate_trade([bench_player], [star_player], mode)
            assert isinstance(result["side_a_total"], float)
            assert isinstance(result["side_b_total"], float)
            assert isinstance(result["net_value"], float)

    def test_nfl_trade(self, nfl_wr_stats, nfl_rb_stats):
        """Trade evaluation works for NFL players."""
        result = evaluate_trade([nfl_rb_stats], [nfl_wr_stats], RiskMode.MEDIAN)

        assert result["decision"] in ("Accept Trade", "Reject Trade")
        assert result["side_a_players"][0]["name"] == "Test RB"
        assert result["side_b_players"][0]["name"] == "Test WR"

    def test_mlb_trade(self, mlb_hitter_stats, mlb_pitcher_stats):
        """Trade evaluation works for MLB players."""
        result = evaluate_trade(
            [mlb_pitcher_stats], [mlb_hitter_stats], RiskMode.MEDIAN
        )

        assert result["decision"] in ("Accept Trade", "Reject Trade")

    def test_nhl_trade(self, nhl_forward_stats, nhl_goalie_stats):
        """Trade evaluation works for NHL players."""
        result = evaluate_trade(
            [nhl_goalie_stats], [nhl_forward_stats], RiskMode.MEDIAN
        )

        assert result["decision"] in ("Accept Trade", "Reject Trade")

    def test_player_indices_present(self, star_player, bench_player):
        """Each player breakdown includes IndexScores."""
        result = evaluate_trade([bench_player], [star_player], RiskMode.MEDIAN)

        for player in result["side_a_players"] + result["side_b_players"]:
            indices = player["indices"]
            assert hasattr(indices, "sci")
            assert hasattr(indices, "rmi")
            assert hasattr(indices, "gis")
            assert hasattr(indices, "od")
            assert hasattr(indices, "msf")


# =============================================================================
# TEST TradeResult DATACLASS
# =============================================================================


class TestTradeResult:
    """Tests for TradeResult computed properties."""

    def test_net_value_positive_accept(self, star_player, bench_player):
        """Positive net_value → Accept Trade."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [bench_player], [star_player], RiskMode.MEDIAN, "nba"
        )

        assert result.net_value > 0
        assert result.decision == "Accept Trade"

    def test_net_value_negative_reject(self, star_player, bench_player):
        """Negative net_value → Reject Trade."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [star_player], [bench_player], RiskMode.MEDIAN, "nba"
        )

        assert result.net_value < 0
        assert result.decision == "Reject Trade"

    def test_rationale_contains_names(self, star_player, bench_player):
        """Rationale mentions player names."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [bench_player], [star_player], RiskMode.MEDIAN, "nba"
        )

        assert "Star Player" in result.rationale
        assert "Bench Player" in result.rationale

    def test_rationale_contains_mode(self, star_player, bench_player):
        """Rationale mentions the risk mode."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [bench_player], [star_player], RiskMode.FLOOR, "nba"
        )

        assert "floor" in result.rationale

    def test_to_details_dict_structure(self, star_player, bench_player):
        """to_details_dict returns expected structure."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [bench_player], [star_player], RiskMode.MEDIAN, "nba"
        )
        details = result.to_details_dict()

        assert "side_giving" in details
        assert "side_receiving" in details
        assert "net_value" in details
        assert "margin" in details
        assert "risk_mode" in details
        assert "sport" in details

        # Player lists
        assert len(details["side_giving"]["players"]) == 1
        assert len(details["side_receiving"]["players"]) == 1

        # Player structure
        player = details["side_giving"]["players"][0]
        assert "name" in player
        assert "team" in player
        assert "score" in player
        assert "indices" in player
        assert set(player["indices"].keys()) == {"sci", "rmi", "gis", "od", "msf"}

    def test_confidence_property(self, star_player, bench_player):
        """Confidence is computed from net_value and player count."""
        from services.trade_analyzer import trade_analyzer

        result = trade_analyzer.analyze(
            [bench_player], [star_player], RiskMode.MEDIAN, "nba"
        )

        assert result.confidence in ("low", "medium", "high")

    def test_confidence_high_direct(self):
        """Line 84: avg_margin >= 8 returns 'high' confidence."""
        from core.scoring import IndexScores
        from services.trade_analyzer import PlayerBreakdown, TradeResult, TradeSide

        # Construct a trade with large net_value to guarantee high confidence
        # 1 player each side: net_value=20, player_count=2, avg_margin=10 >= 8
        idx = IndexScores(sci=50, rmi=30, gis=60, od=10, msf=55)
        side_giving = TradeSide(
            players=[PlayerBreakdown(name="Low", team="AAA", score=10.0, indices=idx)]
        )
        side_receiving = TradeSide(
            players=[PlayerBreakdown(name="High", team="BBB", score=30.0, indices=idx)]
        )
        result = TradeResult(
            side_giving=side_giving,
            side_receiving=side_receiving,
            risk_mode="median",
            sport="nba",
        )
        assert result.confidence == "high"

    def test_confidence_medium_direct(self):
        """Line 84: avg_margin in [3, 8) returns 'medium' confidence."""
        from core.scoring import IndexScores
        from services.trade_analyzer import PlayerBreakdown, TradeResult, TradeSide

        # 1 player each side: net_value=10, player_count=2, avg_margin=5 → medium
        idx = IndexScores(sci=50, rmi=30, gis=60, od=10, msf=55)
        side_giving = TradeSide(
            players=[PlayerBreakdown(name="A", team="AAA", score=20.0, indices=idx)]
        )
        side_receiving = TradeSide(
            players=[PlayerBreakdown(name="B", team="BBB", score=30.0, indices=idx)]
        )
        result = TradeResult(
            side_giving=side_giving,
            side_receiving=side_receiving,
            risk_mode="median",
            sport="nba",
        )
        assert result.confidence == "medium"


# =============================================================================
# TEST TradeSide DATACLASS
# =============================================================================


class TestTradeSide:
    """Tests for TradeSide computed properties."""

    def test_empty_side(self):
        """Empty TradeSide has zero total and empty names."""
        from services.trade_analyzer import TradeSide

        side = TradeSide(players=[])
        assert side.total_score == 0.0
        assert side.player_count == 0
        assert side.player_names == []

    def test_multi_player_side(self, role_player_a, role_player_b):
        """Multi-player side aggregates correctly."""
        from core.scoring import calculate_indices, composite_score
        from services.trade_analyzer import PlayerBreakdown, TradeSide

        breakdowns = []
        for player in [role_player_a, role_player_b]:
            indices = calculate_indices(player)
            score = composite_score(indices, RiskMode.MEDIAN)
            breakdowns.append(
                PlayerBreakdown(
                    name=player.name,
                    team=player.team,
                    score=round(score, 1),
                    indices=indices,
                )
            )

        side = TradeSide(players=breakdowns)
        assert side.player_count == 2
        assert len(side.player_names) == 2
        assert side.total_score == round(sum(b.score for b in breakdowns), 1)


# =============================================================================
# TEST extract_trade_players() QUERY PARSING
# =============================================================================


class TestExtractTradePlayers:
    """Tests for trade query parsing."""

    def test_trade_x_for_y(self):
        """'trade X for Y' pattern."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("Should I trade LeBron James for Kevin Durant?")
        assert result is not None
        giving, receiving = result
        assert giving == ["LeBron James"]
        assert receiving == ["Kevin Durant"]

    def test_multi_player_and(self):
        """'trade X and Y for Z' with 'and' separator."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players(
            "trade Jayson Tatum and Marcus Smart for Giannis Antetokounmpo"
        )
        assert result is not None
        giving, receiving = result
        assert giving == ["Jayson Tatum", "Marcus Smart"]
        assert receiving == ["Giannis Antetokounmpo"]

    def test_multi_player_plus(self):
        """'trade X + Y for Z' with '+' separator."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("trade Tatum + Smart for Giannis")
        assert result is not None
        giving, receiving = result
        assert giving == ["Tatum", "Smart"]
        assert receiving == ["Giannis"]

    def test_multi_player_ampersand(self):
        """'trade X & Y for Z' with '&' separator."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("trade Tatum & Smart for Giannis")
        assert result is not None
        giving, receiving = result
        assert giving == ["Tatum", "Smart"]
        assert receiving == ["Giannis"]

    def test_give_up_pattern(self):
        """'give up X for Y' pattern."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("give up Anthony Davis for Nikola Jokic?")
        assert result is not None
        giving, receiving = result
        assert giving == ["Anthony Davis"]
        assert receiving == ["Nikola Jokic"]

    def test_giving_up_pattern(self):
        """'giving up X for Y' pattern."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("I'm giving up Luka for Shai")
        assert result is not None
        giving, receiving = result
        assert giving == ["Luka"]
        assert receiving == ["Shai"]

    def test_receive_pattern_reversed(self):
        """'receive Y for X' pattern — groups reversed."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("receive Jokic for Davis?")
        assert result is not None
        giving, receiving = result
        assert giving == ["Davis"]
        assert receiving == ["Jokic"]

    def test_unparseable_returns_none(self):
        """Non-trade query returns None."""
        from services.trade_analyzer import extract_trade_players

        assert extract_trade_players("Should I start LeBron or KD?") is None
        assert extract_trade_players("Who is better, Jokic or Embiid?") is None
        assert extract_trade_players("Random text about basketball") is None

    def test_case_insensitive(self):
        """Parsing is case-insensitive."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players("TRADE LeBron FOR KD")
        assert result is not None

    def test_multi_player_both_sides(self):
        """Multiple players on both sides."""
        from services.trade_analyzer import extract_trade_players

        result = extract_trade_players(
            "trade Tatum and Brown for Giannis and Middleton"
        )
        assert result is not None
        giving, receiving = result
        assert len(giving) == 2
        assert len(receiving) == 2


# =============================================================================
# TEST classify_trade_query()
# =============================================================================


class TestClassifyTradeQuery:
    """Tests for trade query complexity classification."""

    def test_simple_trade(self):
        """Simple trade with players found → SIMPLE."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for Kevin Durant", trade_players_found=True
        )
        assert result == QueryComplexity.SIMPLE

    def test_no_players_found_complex(self):
        """No players found → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for Kevin Durant", trade_players_found=False
        )
        assert result == QueryComplexity.COMPLEX

    def test_dynasty_keyword_complex(self):
        """Dynasty keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD in my dynasty league", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_keeper_keyword_complex(self):
        """Keeper keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD as a keeper", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_ros_keyword_complex(self):
        """ROS keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD ROS value", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_injury_keyword_complex(self):
        """Injury keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD considering his injury", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_explain_keyword_complex(self):
        """Explain keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD explain why", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_why_keyword_complex(self):
        """Why keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "why should I trade LeBron for KD", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_playoffs_keyword_complex(self):
        """Playoffs keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD for the playoffs", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_rest_of_season_complex(self):
        """'rest of season' → COMPLEX."""
        from services.router import QueryComplexity, classify_trade_query

        result = classify_trade_query(
            "trade LeBron for KD rest of season", trade_players_found=True
        )
        assert result == QueryComplexity.COMPLEX


# =============================================================================
# TEST can_analyze_locally()
# =============================================================================


class TestCanAnalyzeLocally:
    """Tests for TradeAnalyzer.can_analyze_locally."""

    def test_all_found(self):
        """All lookups successful → True."""
        from services.trade_analyzer import trade_analyzer

        giving = [("info_a", "stats_a"), ("info_b", "stats_b")]
        receiving = [("info_c", "stats_c")]
        assert trade_analyzer.can_analyze_locally(giving, receiving) is True

    def test_one_missing_giving(self):
        """One missing on giving side → False."""
        from services.trade_analyzer import trade_analyzer

        giving = [("info_a", "stats_a"), None]
        receiving = [("info_c", "stats_c")]
        assert trade_analyzer.can_analyze_locally(giving, receiving) is False

    def test_one_missing_receiving(self):
        """One missing on receiving side → False."""
        from services.trade_analyzer import trade_analyzer

        giving = [("info_a", "stats_a")]
        receiving = [None]
        assert trade_analyzer.can_analyze_locally(giving, receiving) is False

    def test_all_missing(self):
        """All lookups failed → False."""
        from services.trade_analyzer import trade_analyzer

        giving = [None, None]
        receiving = [None]
        assert trade_analyzer.can_analyze_locally(giving, receiving) is False

    def test_empty_lists(self):
        """Empty lists → True (vacuously true)."""
        from services.trade_analyzer import trade_analyzer

        assert trade_analyzer.can_analyze_locally([], []) is True


# =============================================================================
# TEST /decide TRADE ENDPOINT
# =============================================================================


class TestDecideTradeEndpoint:
    """Integration test for /decide with trade decision_type."""

    def test_simple_trade_local_routing(self, test_client):
        """Simple trade with all data available routes to local scoring."""
        from unittest.mock import AsyncMock, patch

        from services.espn import PlayerInfo, PlayerStats

        player_a_info = PlayerInfo(
            id="12345",
            name="LeBron James",
            team="Los Angeles Lakers",
            team_abbrev="LAL",
            position="SF",
            jersey="23",
            height="6'9\"",
            weight="250 lbs",
            age=39,
            experience=21,
            headshot_url=None,
        )
        player_a_stats = PlayerStats(
            player_id="12345",
            sport="nba",
            games_played=50,
            games_started=50,
            points_per_game=25.5,
            rebounds_per_game=7.5,
            assists_per_game=8.0,
            usage_rate=28.0,
            field_goal_pct=0.500,
            three_point_pct=0.380,
        )

        player_b_info = PlayerInfo(
            id="67890",
            name="Kevin Durant",
            team="Phoenix Suns",
            team_abbrev="PHX",
            position="SF",
            jersey="35",
            height="6'10\"",
            weight="240 lbs",
            age=35,
            experience=16,
            headshot_url=None,
        )
        player_b_stats = PlayerStats(
            player_id="67890",
            sport="nba",
            games_played=45,
            games_started=45,
            points_per_game=27.0,
            rebounds_per_game=6.5,
            assists_per_game=5.0,
            usage_rate=30.0,
            field_goal_pct=0.520,
            three_point_pct=0.400,
        )

        with (
            patch(
                "api.main.espn_service.find_player_by_name",
                new_callable=AsyncMock,
            ) as mock_find,
            patch(
                "api.main.espn_service.get_player_game_logs",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "api.main.espn_service.calculate_trends",
                return_value={
                    "minutes_trend": 0.0,
                    "usage_trend": 0.0,
                    "points_trend": 0.0,
                },
            ),
            patch(
                "api.main.espn_service.get_next_opponent",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "api.main._store_decision",
                new_callable=AsyncMock,
            ),
        ):
            mock_find.side_effect = [
                (player_a_info, player_a_stats),
                (player_b_info, player_b_stats),
            ]

            response = test_client.post(
                "/decide",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "decision_type": "trade",
                    "query": "Should I trade LeBron James for Kevin Durant?",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["decision"] in ("Accept Trade", "Reject Trade")
            assert data["confidence"] in ("low", "medium", "high")
            assert data["source"] == "local"
            assert "side_giving" in data.get("details", {})
            assert "side_receiving" in data.get("details", {})

    def test_complex_trade_falls_through(self, test_client):
        """Trade with complex keywords falls through to Claude path."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
            patch(
                "api.main.espn_service.find_player_by_name",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ClaudeService,
                "is_available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch(
                "api.main._claude_decision",
                new_callable=AsyncMock,
            ) as mock_claude,
            patch(
                "api.main._store_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Accept Trade",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/decide",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "decision_type": "trade",
                    "query": "trade LeBron for KD in my dynasty league, explain why?",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"

    def test_trade_unparseable_query_falls_through(self, test_client):
        """Trade query that can't be parsed falls through to Claude."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
            patch(
                "api.main.espn_service.find_player_by_name",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ClaudeService,
                "is_available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch(
                "api.main._claude_decision",
                new_callable=AsyncMock,
            ) as mock_claude,
            patch(
                "api.main._store_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Accept Trade",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/decide",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "decision_type": "trade",
                    "query": "What do you think about this trade situation?",
                },
            )

            assert response.status_code == 200
            # Falls through to Claude since we can't parse players
            data = response.json()
            assert data["source"] == "claude"

    def test_trade_missing_espn_data_falls_through(self, test_client):
        """Trade where ESPN lookup fails falls through to Claude."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
            patch(
                "api.main.espn_service.find_player_by_name",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                ClaudeService,
                "is_available",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch(
                "api.main._claude_decision",
                new_callable=AsyncMock,
            ) as mock_claude,
            patch(
                "api.main._store_decision",
                new_callable=AsyncMock,
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Accept Trade",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/decide",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "decision_type": "trade",
                    "query": "trade LeBron for Kevin Durant",
                },
            )

            assert response.status_code == 200
            data = response.json()
            # ESPN data not found, falls through to Claude
            assert data["source"] == "claude"
