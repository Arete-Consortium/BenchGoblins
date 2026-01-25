"""
Tests for query routing logic.
"""


class TestQueryClassification:
    """Tests for query complexity classification."""

    def test_simple_start_sit(self):
        """Simple start/sit is SIMPLE."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I start LeBron or KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.SIMPLE

    def test_vs_query_simple(self):
        """Player vs player is SIMPLE."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="LeBron vs KD this week",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.SIMPLE

    def test_trade_is_complex(self):
        """Trade decisions are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I trade LeBron for KD?",
            decision_type="trade",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_waiver_is_complex(self):
        """Waiver decisions are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I pick up Player X?",
            decision_type="waiver",
            player_a="Player X",
            player_b=None,
        )

        assert result == QueryComplexity.COMPLEX

    def test_explain_is_complex(self):
        """Explanation requests are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Why should I start LeBron?",
            decision_type="explain",
            player_a="LeBron",
            player_b=None,
        )

        assert result == QueryComplexity.COMPLEX

    def test_why_pattern_is_complex(self):
        """'Why' questions are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Why is LeBron better than KD this week?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_injury_mention_is_complex(self):
        """Injury mentions are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I start LeBron or KD with the injury concerns?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_ros_is_complex(self):
        """Rest of season questions are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Who is better rest of season: LeBron or KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_rank_is_complex(self):
        """Ranking requests are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Rank these players: LeBron, KD, Giannis",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_long_query_is_complex(self):
        """Very long queries are COMPLEX."""
        from services.router import QueryComplexity, classify_query

        long_query = (
            "I need help deciding between LeBron James and Kevin Durant for this week's "
            "matchup because I'm really not sure who would be better given the recent "
            "games and the opponents they're facing and also considering their minutes "
            "and usage rates over the past few weeks."
        )

        result = classify_query(
            query=long_query,
            decision_type="start_sit",
            player_a="LeBron James",
            player_b="Kevin Durant",
        )

        assert result == QueryComplexity.COMPLEX

    def test_no_players_defaults_complex(self):
        """Missing player info defaults to COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Who should I start?",
            decision_type="start_sit",
            player_a=None,
            player_b=None,
        )

        assert result == QueryComplexity.COMPLEX

    def test_one_player_missing_complex(self):
        """One player missing defaults to COMPLEX."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I start LeBron?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b=None,
        )

        assert result == QueryComplexity.COMPLEX


class TestPlayerExtraction:
    """Tests for player name extraction from queries."""

    def test_extract_or_pattern(self):
        """Extract players from 'X or Y' pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query(
            "Should I start LeBron James or Kevin Durant?"
        )

        assert player_a is not None
        assert player_b is not None
        assert "lebron" in player_a.lower()
        assert "kevin" in player_b.lower() or "durant" in player_b.lower()

    def test_extract_vs_pattern(self):
        """Extract players from 'X vs Y' pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query("LeBron vs KD")

        assert player_a is not None
        assert player_b is not None

    def test_extract_versus_pattern(self):
        """Extract players from 'X versus Y' pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query(
            "LeBron James versus Kevin Durant"
        )

        assert player_a is not None
        assert player_b is not None

    def test_extract_no_pattern(self):
        """Return None for queries without clear pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query("Who is the best player?")

        assert player_a is None
        assert player_b is None

    def test_extract_sit_pattern(self):
        """Extract from 'sit X or Y' pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query("Should I sit LeBron or KD?")

        assert player_a is not None
        assert player_b is not None

    def test_extract_between_pattern(self):
        """Extract from 'between X or Y' pattern."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query(
            "Choosing between LeBron or KD this week"
        )

        assert player_a is not None
        assert player_b is not None

    def test_extract_handles_special_chars(self):
        """Handle player names with special characters."""
        from services.router import extract_players_from_query

        player_a, player_b = extract_players_from_query(
            "Start De'Aaron Fox or Ja Morant?"
        )

        # Should extract something, even if not perfect
        # The regex allows apostrophes and hyphens
        assert player_a is not None or player_b is not None


class TestComplexPatterns:
    """Tests for complex pattern detection."""

    def test_give_up_pattern(self):
        """'Give up' indicates trade."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I give up LeBron for KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_pick_n_pattern(self):
        """'Pick N' indicates multi-player decision."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Pick 2 from LeBron, KD, Giannis",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_drop_for_pattern(self):
        """'Drop X for Y' indicates waiver."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Should I drop LeBron for KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_playoffs_pattern(self):
        """'Playoffs' indicates long-term thinking."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="Who is better for playoffs: LeBron or KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_dynasty_pattern(self):
        """'Dynasty' indicates long-term league."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="In dynasty, LeBron or KD?",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX

    def test_not_sure_pattern(self):
        """'Not sure' indicates uncertainty needing Claude."""
        from services.router import QueryComplexity, classify_query

        result = classify_query(
            query="I'm not sure if I should start LeBron or KD",
            decision_type="start_sit",
            player_a="LeBron",
            player_b="KD",
        )

        assert result == QueryComplexity.COMPLEX
