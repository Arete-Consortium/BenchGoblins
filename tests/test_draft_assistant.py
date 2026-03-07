"""
Tests for the draft assistant feature.

Covers: rank_players core function, DraftResult/DraftPick dataclasses,
extract_draft_players parsing, classify_draft_query routing,
can_analyze_locally checks, and full /draft endpoint integration.
"""

import pytest
from core.scoring import PlayerStats, RiskMode, rank_players


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
def role_player():
    """Decent NBA role player."""
    return PlayerStats(
        player_id="r1",
        name="Role Player",
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
# TEST rank_players() CORE FUNCTION
# =============================================================================


class TestRankPlayers:
    """Tests for the core rank_players function."""

    def test_two_player_ordering(self, star_player, bench_player):
        """Star player should rank above bench player."""
        result = rank_players([bench_player, star_player], RiskMode.MEDIAN)

        assert len(result) == 2
        assert result[0]["name"] == "Star Player"
        assert result[0]["rank"] == 1
        assert result[1]["name"] == "Bench Player"
        assert result[1]["rank"] == 2
        assert result[0]["score"] > result[1]["score"]

    def test_three_player_ordering(self, star_player, role_player, bench_player):
        """Three players ranked in correct order."""
        result = rank_players([bench_player, star_player, role_player], RiskMode.MEDIAN)

        assert len(result) == 3
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2
        assert result[2]["rank"] == 3
        # Star should be on top, bench on bottom
        assert result[0]["name"] == "Star Player"
        assert result[2]["name"] == "Bench Player"
        # Scores should be descending
        assert result[0]["score"] >= result[1]["score"] >= result[2]["score"]

    def test_position_boost_applied(self, star_player, role_player):
        """Position boost increases score for matching positions."""
        # Boost SG (role_player's position)
        result = rank_players(
            [star_player, role_player], RiskMode.MEDIAN, position_needs=["SG"]
        )

        boosted = [p for p in result if p["name"] == "Role Player"][0]
        assert boosted["position_boosted"] is True
        assert boosted["score"] > boosted["base_score"]

        not_boosted = [p for p in result if p["name"] == "Star Player"][0]
        assert not_boosted["position_boosted"] is False
        assert not_boosted["score"] == not_boosted["base_score"]

    def test_boost_clamped_at_100(self, star_player):
        """Position boost should not exceed score of 100."""
        # Create a player with very high base score and give huge boost
        result = rank_players(
            [star_player], RiskMode.CEILING, position_needs=["SF"], position_boost=200.0
        )

        assert result[0]["score"] <= 100.0
        assert result[0]["position_boosted"] is True

    def test_all_risk_modes(self, star_player, bench_player):
        """All three risk modes produce valid ranked results."""
        for mode in RiskMode:
            result = rank_players([bench_player, star_player], mode)
            assert len(result) == 2
            assert all(isinstance(p["score"], float) for p in result)
            assert result[0]["rank"] == 1
            assert result[1]["rank"] == 2

    def test_nfl_players(self, nfl_wr_stats, nfl_rb_stats):
        """Ranking works for NFL players."""
        result = rank_players([nfl_rb_stats, nfl_wr_stats], RiskMode.MEDIAN)

        assert len(result) == 2
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2

    def test_mlb_players(self, mlb_hitter_stats, mlb_pitcher_stats):
        """Ranking works for MLB players."""
        result = rank_players([mlb_pitcher_stats, mlb_hitter_stats], RiskMode.MEDIAN)

        assert len(result) == 2

    def test_nhl_players(self, nhl_forward_stats, nhl_goalie_stats):
        """Ranking works for NHL players."""
        result = rank_players([nhl_goalie_stats, nhl_forward_stats], RiskMode.MEDIAN)

        assert len(result) == 2

    def test_indices_present(self, star_player, bench_player):
        """Each player entry includes IndexScores."""
        result = rank_players([bench_player, star_player], RiskMode.MEDIAN)

        for player in result:
            indices = player["indices"]
            assert hasattr(indices, "sci")
            assert hasattr(indices, "rmi")
            assert hasattr(indices, "gis")
            assert hasattr(indices, "od")
            assert hasattr(indices, "msf")

    def test_position_boost_case_insensitive(self, role_player):
        """Position needs matching is case-insensitive."""
        result = rank_players([role_player], RiskMode.MEDIAN, position_needs=["sg"])
        assert result[0]["position_boosted"] is True

        result = rank_players([role_player], RiskMode.MEDIAN, position_needs=["Sg"])
        assert result[0]["position_boosted"] is True


# =============================================================================
# TEST DraftResult DATACLASS
# =============================================================================


class TestDraftResult:
    """Tests for DraftResult computed properties."""

    def test_recommended_pick(self, star_player, bench_player):
        """Recommended pick is the #1 ranked player."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [bench_player, star_player], RiskMode.MEDIAN, "nba"
        )

        assert result.recommended_pick is not None
        assert result.recommended_pick.rank == 1
        assert result.recommended_pick.name == "Star Player"

    def test_confidence_high_wide_margin(self, star_player, bench_player):
        """Wide margin between #1 and #2 → high confidence."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [bench_player, star_player], RiskMode.MEDIAN, "nba"
        )

        margin = result.ranked_players[0].score - result.ranked_players[1].score
        if margin >= 10:
            assert result.confidence == "high"

    def test_confidence_low_close_scores(self, role_player):
        """When only one player, confidence is low."""
        from services.draft_assistant import DraftPick, DraftResult
        from core.scoring import IndexScores

        # Create two picks with nearly identical scores
        idx = IndexScores(sci=50.0, rmi=50.0, gis=50.0, od=0.0, msf=50.0)
        picks = [
            DraftPick(
                rank=1,
                name="A",
                team="T1",
                position="PG",
                score=50.0,
                base_score=50.0,
                indices=idx,
                position_boosted=False,
            ),
            DraftPick(
                rank=2,
                name="B",
                team="T2",
                position="SG",
                score=49.5,
                base_score=49.5,
                indices=idx,
                position_boosted=False,
            ),
        ]
        result = DraftResult(ranked_players=picks, risk_mode="median", sport="nba")
        assert result.confidence == "low"

    def test_confidence_medium(self):
        """Margin between 3 and 10 → medium confidence."""
        from services.draft_assistant import DraftPick, DraftResult
        from core.scoring import IndexScores

        idx = IndexScores(sci=50.0, rmi=50.0, gis=50.0, od=0.0, msf=50.0)
        picks = [
            DraftPick(
                rank=1,
                name="A",
                team="T1",
                position="PG",
                score=60.0,
                base_score=60.0,
                indices=idx,
                position_boosted=False,
            ),
            DraftPick(
                rank=2,
                name="B",
                team="T2",
                position="SG",
                score=55.0,
                base_score=55.0,
                indices=idx,
                position_boosted=False,
            ),
        ]
        result = DraftResult(ranked_players=picks, risk_mode="median", sport="nba")
        assert result.confidence == "medium"

    def test_rationale_contains_names(self, star_player, bench_player):
        """Rationale mentions player names."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [bench_player, star_player], RiskMode.MEDIAN, "nba"
        )

        assert "Star Player" in result.rationale
        assert "Bench Player" in result.rationale

    def test_rationale_contains_mode(self, star_player, bench_player):
        """Rationale mentions the risk mode."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [bench_player, star_player], RiskMode.FLOOR, "nba"
        )

        assert "floor" in result.rationale

    def test_rationale_position_boosted(self):
        """Rationale includes position-boost note when top pick is boosted (line 78)."""
        from core.scoring import IndexScores

        from services.draft_assistant import DraftPick, DraftResult

        idx = IndexScores(sci=60.0, rmi=60.0, gis=60.0, od=5.0, msf=55.0)
        picks = [
            DraftPick(
                rank=1,
                name="Boosted Player",
                team="LAL",
                position="PG",
                score=75.0,
                base_score=70.0,
                indices=idx,
                position_boosted=True,
            ),
            DraftPick(
                rank=2,
                name="Other Player",
                team="BOS",
                position="SF",
                score=65.0,
                base_score=65.0,
                indices=idx,
                position_boosted=False,
            ),
        ]
        result = DraftResult(ranked_players=picks, risk_mode="median", sport="nba")
        assert "boosted for position need" in result.rationale

    def test_rationale_single_player(self):
        """Rationale with one player uses mode-only suffix (line 87)."""
        from core.scoring import IndexScores

        from services.draft_assistant import DraftPick, DraftResult

        idx = IndexScores(sci=60.0, rmi=60.0, gis=60.0, od=5.0, msf=55.0)
        picks = [
            DraftPick(
                rank=1,
                name="Solo Player",
                team="LAL",
                position="PG",
                score=70.0,
                base_score=70.0,
                indices=idx,
                position_boosted=False,
            ),
        ]
        result = DraftResult(ranked_players=picks, risk_mode="floor", sport="nba")
        assert "(floor mode)." in result.rationale
        assert "over" not in result.rationale

    def test_to_details_dict_structure(self, star_player, bench_player):
        """to_details_dict returns expected structure."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [bench_player, star_player], RiskMode.MEDIAN, "nba"
        )
        details = result.to_details_dict()

        assert "ranked_players" in details
        assert "risk_mode" in details
        assert "sport" in details
        assert "position_needs" in details
        assert len(details["ranked_players"]) == 2

        # Player structure
        player = details["ranked_players"][0]
        assert "rank" in player
        assert "name" in player
        assert "team" in player
        assert "position" in player
        assert "score" in player
        assert "base_score" in player
        assert "indices" in player
        assert "position_boosted" in player
        assert set(player["indices"].keys()) == {"sci", "rmi", "gis", "od", "msf"}

    def test_empty_pool(self):
        """Empty player pool returns sensible defaults."""
        from services.draft_assistant import DraftResult

        result = DraftResult(ranked_players=[], risk_mode="median", sport="nba")
        assert result.recommended_pick is None
        assert result.confidence == "low"
        assert "No players" in result.rationale


# =============================================================================
# TEST DraftPick DATACLASS
# =============================================================================


class TestDraftPick:
    """Tests for DraftPick dataclass."""

    def test_indices_dict_keys(self, star_player):
        """indices_dict returns all 5 index keys."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze([star_player], RiskMode.MEDIAN, "nba")
        pick = result.ranked_players[0]

        assert set(pick.indices_dict.keys()) == {"sci", "rmi", "gis", "od", "msf"}
        assert all(isinstance(v, float) for v in pick.indices_dict.values())

    def test_position_boosted_flag_true(self, role_player):
        """Position-boosted player has flag set."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze(
            [role_player], RiskMode.MEDIAN, "nba", position_needs=["SG"]
        )

        assert result.ranked_players[0].position_boosted is True

    def test_position_boosted_flag_false(self, role_player):
        """Non-boosted player has flag unset."""
        from services.draft_assistant import draft_assistant

        result = draft_assistant.analyze([role_player], RiskMode.MEDIAN, "nba")

        assert result.ranked_players[0].position_boosted is False


# =============================================================================
# TEST extract_draft_players() QUERY PARSING
# =============================================================================


class TestExtractDraftPlayers:
    """Tests for draft query parsing."""

    def test_pick_from_pattern(self):
        """'pick from X, Y, Z' pattern."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("pick from LeBron James, Kevin Durant, Giannis")
        assert result is not None
        assert len(result) == 3
        assert "LeBron James" in result
        assert "Kevin Durant" in result
        assert "Giannis" in result

    def test_choose_from_pattern(self):
        """'choose from X, Y' pattern."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("choose from Jokic, Embiid")
        assert result is not None
        assert len(result) == 2

    def test_who_should_i_draft_pattern(self):
        """'who should I draft: X, Y' pattern."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("who should I draft: Luka, Shai, Tatum")
        assert result is not None
        assert len(result) == 3

    def test_who_should_i_draft_no_colon(self):
        """'who should I draft X, Y' without colon."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("who should I draft Luka or Shai")
        assert result is not None
        assert len(result) == 2

    def test_rank_pattern(self):
        """'rank X, Y, Z' pattern."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("rank Brunson, Maxey, and Haliburton")
        assert result is not None
        assert len(result) == 3

    def test_draft_or_pattern(self):
        """'draft X or Y' pattern."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("draft Brunson or Maxey?")
        assert result is not None
        assert len(result) == 2

    def test_and_separator(self):
        """'and' separator."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("pick from LeBron and KD and Giannis")
        assert result is not None
        assert len(result) == 3

    def test_plus_separator(self):
        """'+' separator."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("rank Tatum + Brown + Brunson")
        assert result is not None
        assert len(result) == 3

    def test_ampersand_separator(self):
        """'&' separator."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("draft Jokic & Embiid")
        assert result is not None
        assert len(result) == 2

    def test_single_player_returns_none(self):
        """Single player → None (need at least 2)."""
        from services.draft_assistant import extract_draft_players

        assert extract_draft_players("draft LeBron James") is None

    def test_no_match_returns_none(self):
        """Non-draft query → None."""
        from services.draft_assistant import extract_draft_players

        assert extract_draft_players("Should I start LeBron or KD?") is None
        assert extract_draft_players("Random text about basketball") is None

    def test_case_insensitive(self):
        """Parsing is case-insensitive."""
        from services.draft_assistant import extract_draft_players

        result = extract_draft_players("PICK FROM LeBron, KD, Giannis")
        assert result is not None
        assert len(result) == 3


# =============================================================================
# TEST classify_draft_query()
# =============================================================================


class TestClassifyDraftQuery:
    """Tests for draft query complexity classification."""

    def test_simple_draft(self):
        """Simple draft with players found → SIMPLE."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or Kevin Durant", draft_players_found=True
        )
        assert result == QueryComplexity.SIMPLE

    def test_no_players_found_complex(self):
        """No players found → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "who should I draft next", draft_players_found=False
        )
        assert result == QueryComplexity.COMPLEX

    def test_dynasty_keyword_complex(self):
        """Dynasty keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD in my dynasty league", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_keeper_keyword_complex(self):
        """Keeper keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD as a keeper pick", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_auction_keyword_complex(self):
        """Auction keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD in an auction league", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_explain_keyword_complex(self):
        """Explain keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD explain why", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_upside_keyword_complex(self):
        """Upside keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD who has more upside", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_ros_keyword_complex(self):
        """ROS keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD ROS value", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX

    def test_injury_keyword_complex(self):
        """Injury keyword → COMPLEX."""
        from services.router import QueryComplexity, classify_draft_query

        result = classify_draft_query(
            "draft LeBron or KD considering his injury", draft_players_found=True
        )
        assert result == QueryComplexity.COMPLEX


# =============================================================================
# TEST can_analyze_locally()
# =============================================================================


class TestCanAnalyzeLocally:
    """Tests for DraftAssistant.can_analyze_locally."""

    def test_all_found(self):
        """All lookups successful → True."""
        from services.draft_assistant import draft_assistant

        data = [("info_a", "stats_a"), ("info_b", "stats_b"), ("info_c", "stats_c")]
        assert draft_assistant.can_analyze_locally(data) is True

    def test_one_missing(self):
        """One missing lookup → False."""
        from services.draft_assistant import draft_assistant

        data = [("info_a", "stats_a"), None, ("info_c", "stats_c")]
        assert draft_assistant.can_analyze_locally(data) is False

    def test_all_missing(self):
        """All lookups failed → False."""
        from services.draft_assistant import draft_assistant

        data = [None, None, None]
        assert draft_assistant.can_analyze_locally(data) is False

    def test_empty(self):
        """Empty list → True (vacuously true)."""
        from services.draft_assistant import draft_assistant

        assert draft_assistant.can_analyze_locally([]) is True


# =============================================================================
# TEST /draft ENDPOINT
# =============================================================================


class TestDraftEndpoint:
    """Integration tests for the /draft endpoint."""

    def _make_player_data(self, player_id, name, team_abbrev, position, ppg, usage):
        """Helper to create mock ESPN PlayerInfo + PlayerStats tuple."""
        from services.espn import PlayerInfo, PlayerStats

        info = PlayerInfo(
            id=player_id,
            name=name,
            team=f"Team {team_abbrev}",
            team_abbrev=team_abbrev,
            position=position,
            jersey="1",
            height="6'5\"",
            weight="210 lbs",
            age=27,
            experience=5,
            headshot_url=None,
        )
        stats = PlayerStats(
            player_id=player_id,
            sport="nba",
            games_played=50,
            games_started=48,
            minutes_per_game=32.0,
            points_per_game=ppg,
            rebounds_per_game=5.0,
            assists_per_game=4.0,
            usage_rate=usage,
            field_goal_pct=0.470,
            three_point_pct=0.370,
        )
        return info, stats

    def test_happy_path_local(self, test_client):
        """Simple draft query with all data available routes to local scoring."""
        from unittest.mock import AsyncMock, patch

        player_a = self._make_player_data("1", "LeBron James", "LAL", "SF", 25.5, 28.0)
        player_b = self._make_player_data("2", "Kevin Durant", "PHX", "SF", 27.0, 30.0)

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
                "api.main.espn_service.get_next_game",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "api.main._store_draft_decision",
                new_callable=AsyncMock,
            ),
        ):
            mock_find.side_effect = [player_a, player_b]

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "draft LeBron James or Kevin Durant?",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "local"
            assert data["recommended_pick"] in ("LeBron James", "Kevin Durant")
            assert data["confidence"] in ("low", "medium", "high")
            assert "ranked_players" in data.get("details", {})

    def test_explicit_players_list(self, test_client):
        """Players provided via explicit list field."""
        from unittest.mock import AsyncMock, patch

        player_a = self._make_player_data("1", "Jalen Brunson", "NYK", "PG", 24.0, 27.0)
        player_b = self._make_player_data("2", "Tyrese Maxey", "PHI", "PG", 22.0, 25.0)

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
                "api.main.espn_service.get_next_game",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "api.main._store_draft_decision",
                new_callable=AsyncMock,
            ),
        ):
            mock_find.side_effect = [player_a, player_b]

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "who should I take next?",
                    "players": ["Jalen Brunson", "Tyrese Maxey"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "local"
            assert data["recommended_pick"] in ("Jalen Brunson", "Tyrese Maxey")

    def test_position_needs(self, test_client):
        """Position needs boost is applied."""
        from unittest.mock import AsyncMock, patch

        # SF star vs PG role player — boost PG
        player_a = self._make_player_data("1", "Star SF", "LAL", "SF", 25.5, 28.0)
        player_b = self._make_player_data("2", "Role PG", "BOS", "PG", 15.0, 20.0)

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
                "api.main.espn_service.get_next_game",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "api.main._store_draft_decision",
                new_callable=AsyncMock,
            ),
        ):
            mock_find.side_effect = [player_a, player_b]

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "draft Star SF or Role PG?",
                    "position_needs": ["PG"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            # Check that PG got boosted
            ranked = data["details"]["ranked_players"]
            pg_entry = [p for p in ranked if p["position"] == "PG"][0]
            assert pg_entry["position_boosted"] is True

    def test_complex_query_falls_to_claude(self, test_client):
        """Draft with complex keywords falls to Claude."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
            patch(
                "api.main.espn_service.find_player_by_name",
                new_callable=AsyncMock,
                return_value=("info", "stats"),
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
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Draft LeBron",
                    confidence=Confidence.MEDIUM,
                    rationale="Dynasty value analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "draft LeBron or KD in my dynasty league, explain why?",
                    "players": ["LeBron", "KD"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"

    def test_unparseable_falls_to_claude(self, test_client):
        """Unparseable query with no explicit players falls to Claude."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
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
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Pick the best player available",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "What should I do with my next pick?",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"

    def test_missing_espn_falls_to_claude(self, test_client):
        """Missing ESPN data falls to Claude."""
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
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Draft LeBron",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "draft LeBron or Kevin Durant",
                    "players": ["LeBron", "Kevin Durant"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"

    def test_single_player_falls_to_claude(self, test_client):
        """Single player in query falls to Claude (need >= 2)."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        from services.claude import ClaudeService

        with (
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
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
        ):
            from api.main import Confidence, DecisionResponse

            mock_claude.return_value = (
                DecisionResponse(
                    decision="Draft LeBron",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude analysis",
                    details=None,
                    source="claude",
                ),
                100,
                50,
            )

            response = test_client.post(
                "/draft",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "should I draft LeBron?",
                    "players": ["LeBron"],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"
