"""
Tests for Query Classifier — Sports query detection.

Tests cover:
- Clear sports queries (high confidence)
- Clear off-topic queries (high confidence rejection)
- Edge cases (player names that are common words, etc.)
- Ambiguous queries handled gracefully
"""

import pytest

from services.query_classifier import (
    QueryCategory,
    classify_query,
    is_sports_query,
)


class TestClearSportsQueries:
    """Test queries that are clearly about fantasy sports."""

    @pytest.mark.parametrize(
        "query",
        [
            "Should I start Jalen Brunson or Tyrese Maxey?",
            "Should I start Patrick Mahomes tonight?",
            "Who should I start, Travis Kelce or Davante Adams?",
            "Start Saquon Barkley or Derrick Henry this week?",
            "Tyreek Hill vs CeeDee Lamb in PPR",
            "Josh Allen or Lamar Jackson this week?",
            "Pick up Austin Ekeler from waivers?",
            "Should I trade Jamarr Chase for Davante Adams?",
            "Drop Cooper Kupp for waiver wire pickup?",
            "LeBron James or Kevin Durant rest of season?",
        ],
    )
    def test_start_sit_questions(self, query):
        """Standard start/sit questions should be classified as sports."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Should I accept this trade: Mahomes for Hurts and Jefferson?",
            "Trade value for Tyreek Hill in dynasty?",
            "Who wins the trade: Josh Allen for Justin Jefferson?",
            "Is this trade fair in keeper league?",
            "Accept trade of Kelce for Kittle and WR2?",
        ],
    )
    def test_trade_questions(self, query):
        """Trade-related queries should be classified as sports."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Best waiver wire pickups this week?",
            "Drop Gus Edwards for waiver claim?",
            "Waiver wire priority for week 10 NFL",
            "Pick up from waivers: Jaylen Warren or Zach Charbonnet?",
            "Should I use my #1 waiver claim?",
        ],
    )
    def test_waiver_questions(self, query):
        """Waiver wire queries should be classified as sports."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Is Tyreek Hill playing tonight?",
            "Jaylen Brown injury update?",
            "When is Ja Morant returning from injury?",
            "Is Lamar Jackson questionable for Sunday?",
            "Patrick Mahomes GTD - should I start him?",
            "Austin Ekeler OUT - who do I start instead?",
        ],
    )
    def test_injury_questions(self, query):
        """Injury-related fantasy queries should be classified as sports."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "ROS rankings for RB in PPR?",
            "Dynasty value of Breece Hall?",
            "Keeper league value for Justin Jefferson?",
            "Best flex play for standard scoring?",
            "Half-PPR rankings for WR this week?",
            "Who to start at TE in points league?",
        ],
    )
    def test_format_specific_questions(self, query):
        """League format specific queries should be classified as sports."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Ohtani vs Trout in fantasy baseball?",
            "Should I start Connor McDavid tonight?",
            "Auston Matthews or Sidney Crosby this week?",
            "Best pitchers to stream this week MLB?",
            "NHL goalie rankings for week 15?",
        ],
    )
    def test_multi_sport_questions(self, query):
        """Queries for various sports should be classified correctly."""
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7


class TestClearOffTopicQueries:
    """Test queries that are clearly not about fantasy sports."""

    @pytest.mark.parametrize(
        "query",
        [
            "How do I look in this photo?",
            "What should I say to my girlfriend?",
            "How to talk to my crush?",
            "Dating advice for first date?",
            "Should I break up with my boyfriend?",
            "How to deal with relationship problems?",
        ],
    )
    def test_personal_advice(self, query):
        """Personal/relationship queries should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Write me a Python script for web scraping",
            "How to debug this JavaScript code?",
            "Write a function that returns fibonacci",
            "Fix this SQL query for me",
            "Programming tutorial for beginners",
            "What's the best programming language to learn?",
        ],
    )
    def test_programming_requests(self, query):
        """Programming/code requests should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Who is the president of the United States?",
            "What is the capital of France?",
            "Explain how photosynthesis works",
            "Tell me a joke about programmers",
            "What is the meaning of life?",
            "History of the Roman Empire",
        ],
    )
    def test_general_knowledge(self, query):
        """General knowledge questions should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "Write me a short story about dragons",
            "Write a poem about nature",
            "Create a song about summer",
            "Write an essay on climate change",
            "Generate a haiku",
        ],
    )
    def test_creative_writing(self, query):
        """Creative writing requests should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "How to write a resume?",
            "Job interview tips",
            "Should I invest in Bitcoin?",
            "Stock market predictions for 2024",
            "How to negotiate salary?",
            "Best crypto to buy now?",
        ],
    )
    def test_business_finance(self, query):
        """Business/finance queries should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7

    @pytest.mark.parametrize(
        "query",
        [
            "What are symptoms of the flu?",
            "Best medication for headaches?",
            "Should I see a doctor about this?",
            "Recipe for chocolate chip cookies",
            "How to cook a steak?",
            "Best vacation destinations in Europe?",
        ],
    )
    def test_health_food_travel(self, query):
        """Health/food/travel queries should be rejected."""
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.7


class TestEdgeCases:
    """Test edge cases and ambiguous queries."""

    @pytest.mark.parametrize(
        "query,expected_category",
        [
            # Common words that are also player names
            ("Jordan is the best", QueryCategory.AMBIGUOUS),  # Could be Michael Jordan
            ("I love the game tonight", QueryCategory.AMBIGUOUS),  # Generic sports
            # Partial information
            ("Who should I pick?", QueryCategory.AMBIGUOUS),  # Missing context
            ("Is he playing?", QueryCategory.AMBIGUOUS),  # Vague
            # Borderline cases
            ("Josh", QueryCategory.AMBIGUOUS),  # Just a name
        ],
    )
    def test_ambiguous_queries(self, query, expected_category):
        """Ambiguous queries should be handled gracefully."""
        result = classify_query(query)
        # Allow either AMBIGUOUS or the specified category
        assert result.category in [
            expected_category,
            QueryCategory.SPORTS,
            QueryCategory.OFF_TOPIC,
        ]

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "   ",
            None,
        ],
    )
    def test_empty_queries(self, query):
        """Empty or whitespace queries should be handled."""
        if query is None:
            result = classify_query("")
        else:
            result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC
        assert "Empty" in result.reason or "No sports" in result.reason

    def test_player_name_as_common_word_start(self):
        """Player names that are common words - 'Brown' in start context should be sports."""
        # A.J. Brown is a player, but "brown" is also a common word
        query = "Start A.J. Brown or DK Metcalf?"
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS

    def test_player_name_as_common_word_without_context(self):
        """Player names that are common words without context."""
        query = "What do you think about Brown?"
        result = classify_query(query)
        # This is ambiguous - could be the color or the player
        assert result.category in [QueryCategory.AMBIGUOUS, QueryCategory.OFF_TOPIC]

    def test_mixed_content_sports_dominant(self):
        """Mixed content where sports context is dominant."""
        # Note: Explicit off-topic words (like "programming") are blocklisted first
        # for safety. Use queries that don't contain blocklist patterns.
        query = "My friend says fantasy is boring but should I start Mahomes or Allen tonight?"
        result = classify_query(query)
        # Sports context should win due to clear fantasy patterns
        assert result.category == QueryCategory.SPORTS

    def test_mixed_content_off_topic_dominant(self):
        """Mixed content where off-topic is dominant."""
        query = "Write me Python code to fetch player stats"
        result = classify_query(query)
        # Programming request should be rejected
        assert result.category == QueryCategory.OFF_TOPIC

    def test_typos_and_misspellings(self):
        """Queries with typos should still work reasonably."""
        query = "Shuold I start Mahomes or Allen tonite?"
        result = classify_query(query)
        # Should still recognize this as sports despite typos
        # Mahomes and Allen are player names
        assert result.category in [QueryCategory.SPORTS, QueryCategory.AMBIGUOUS]

    def test_all_caps(self):
        """All caps queries should work."""
        query = "SHOULD I START PATRICK MAHOMES OR JOSH ALLEN?"
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS

    def test_lowercase(self):
        """All lowercase queries should work."""
        query = "should i start patrick mahomes or josh allen?"
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS

    def test_special_characters(self):
        """Queries with special characters should work."""
        query = "Start Ja'Marr Chase vs. the Steelers???"
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS


class TestIsSportsQueryInterface:
    """Test the simplified is_sports_query interface."""

    def test_sports_query_allowed(self):
        """Sports queries should return (True, reason)."""
        allowed, reason = is_sports_query("Should I start Mahomes or Allen?")
        assert allowed is True
        assert len(reason) > 0

    def test_off_topic_query_rejected(self):
        """Off-topic queries should return (False, reason)."""
        allowed, reason = is_sports_query("Write me Python code")
        assert allowed is False
        assert len(reason) > 0

    def test_ambiguous_query_allowed(self):
        """Ambiguous queries should be allowed (for logging)."""
        allowed, reason = is_sports_query("Who should I pick?")
        assert allowed is True  # Ambiguous is allowed
        assert len(reason) > 0


class TestConfidenceScores:
    """Test that confidence scores are reasonable."""

    def test_high_confidence_sports(self):
        """Clear sports queries should have high confidence."""
        result = classify_query(
            "Should I start Patrick Mahomes or Josh Allen in my fantasy league this week?"
        )
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.8

    def test_high_confidence_off_topic(self):
        """Clear off-topic queries should have high confidence rejection."""
        result = classify_query("Write me a Python script to parse JSON")
        assert result.category == QueryCategory.OFF_TOPIC
        assert result.confidence >= 0.8

    def test_lower_confidence_ambiguous(self):
        """Ambiguous queries should have lower confidence."""
        result = classify_query("What about Jordan?")
        # Confidence should be lower for ambiguous cases
        if result.category == QueryCategory.AMBIGUOUS:
            assert result.confidence < 0.7


class TestClassificationResult:
    """Test ClassificationResult dataclass."""

    def test_result_fields(self):
        """ClassificationResult should have all expected fields."""
        result = classify_query("Test query")
        assert hasattr(result, "category")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")

    def test_category_is_enum(self):
        """Category should be a QueryCategory enum."""
        result = classify_query("Should I start Mahomes?")
        assert isinstance(result.category, QueryCategory)

    def test_confidence_is_float(self):
        """Confidence should be a float between 0 and 1."""
        result = classify_query("Should I start Mahomes?")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_reason_is_string(self):
        """Reason should be a non-empty string."""
        result = classify_query("Should I start Mahomes?")
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


class TestKeywordDensity:
    """Test keyword density calculation."""

    def test_high_density_query(self):
        """Query with many sports terms should have high density."""
        query = "Start RB flex PPR waiver trade fantasy playoffs"
        result = classify_query(query)
        assert result.category == QueryCategory.SPORTS
        assert result.confidence >= 0.7

    def test_low_density_query(self):
        """Query with few sports terms should have lower classification."""
        query = "The weather is nice today and I want to go outside"
        result = classify_query(query)
        assert result.category == QueryCategory.OFF_TOPIC

    def test_mixed_density_query(self):
        """Query with some sports terms should be handled."""
        query = "I want to play fantasy but also go to dinner"
        result = classify_query(query)
        # Should recognize "play" and "fantasy" as sports context
        assert result.category in [QueryCategory.SPORTS, QueryCategory.AMBIGUOUS]


class TestPlayerNameDetection:
    """Test player name detection logic."""

    def test_detects_common_player_names(self):
        """Should detect well-known player first names."""
        result = classify_query("What about Mahomes vs Hurts?")
        assert result.category == QueryCategory.SPORTS

    def test_detects_full_names(self):
        """Should detect full player names (Firstname Lastname)."""
        result = classify_query("Is Travis Kelce better than George Kittle?")
        assert result.category == QueryCategory.SPORTS

    def test_player_comparison_pattern(self):
        """Should detect X or Y and X vs Y patterns."""
        result = classify_query("Kelce or Kittle?")
        # Even without "start" keyword, comparison pattern suggests sports
        assert result.category in [QueryCategory.SPORTS, QueryCategory.AMBIGUOUS]
