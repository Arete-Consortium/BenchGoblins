"""Tests for Claude API service."""

from unittest.mock import patch

import pytest

from services.claude import ClaudeService


@pytest.fixture
def svc():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        # Remove key so ClaudeService doesn't init client
        import os

        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        svc = ClaudeService()
        ClaudeService.clear_cache()
        yield svc
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old


class TestCacheKey:
    def test_deterministic(self):
        k1 = ClaudeService._cache_key("q", "nba", "safe", "start_sit", "A", "B")
        k2 = ClaudeService._cache_key("q", "nba", "safe", "start_sit", "A", "B")
        assert k1 == k2

    def test_case_insensitive(self):
        k1 = ClaudeService._cache_key("Query", "NBA", "SAFE", "start_sit", "A", "B")
        k2 = ClaudeService._cache_key("query", "nba", "safe", "start_sit", "a", "b")
        assert k1 == k2

    def test_different_queries_differ(self):
        k1 = ClaudeService._cache_key("q1", "nba", "safe", "start_sit", None, None)
        k2 = ClaudeService._cache_key("q2", "nba", "safe", "start_sit", None, None)
        assert k1 != k2

    def test_none_players(self):
        k = ClaudeService._cache_key("q", "nba", "safe", "start_sit", None, None)
        assert isinstance(k, str) and len(k) > 0

    def test_variant_matters(self):
        k1 = ClaudeService._cache_key("q", "nba", "safe", "ss", "A", "B", "control")
        k2 = ClaudeService._cache_key("q", "nba", "safe", "ss", "A", "B", "concise_v1")
        assert k1 != k2


class TestCacheStats:
    def test_initial_stats(self, svc):
        stats = ClaudeService.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0
        assert stats["size"] == 0

    def test_clear_cache(self, svc):
        ClaudeService._cache_hits = 5
        ClaudeService._cache_misses = 3
        ClaudeService.clear_cache()
        assert ClaudeService._cache_hits == 0
        assert ClaudeService._cache_misses == 0


class TestIsAvailable:
    def test_not_available_without_key(self, svc):
        assert svc.is_available is False


class TestBuildUserMessage:
    def test_basic(self, svc):
        msg = svc.build_user_message(
            query="Should I start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        assert "NBA" in msg
        assert "SAFE" in msg
        assert "start/sit" in msg
        assert "Should I start LeBron?" in msg

    def test_with_players(self, svc):
        msg = svc.build_user_message(
            query="Who?",
            sport="nfl",
            risk_mode="risky",
            decision_type="start_sit",
            player_a="Mahomes",
            player_b="Allen",
        )
        assert "Player A: Mahomes" in msg
        assert "Player B: Allen" in msg

    def test_with_league_type(self, svc):
        msg = svc.build_user_message(
            query="Q",
            sport="nba",
            risk_mode="safe",
            decision_type="add_drop",
            league_type="PPR",
        )
        assert "League Type: PPR" in msg

    def test_with_player_context(self, svc):
        msg = svc.build_user_message(
            query="Q",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
            player_context="Recent stats: 25 ppg",
        )
        assert "<player_data>" in msg
        assert "Recent stats: 25 ppg" in msg

    def test_without_player_context(self, svc):
        msg = svc.build_user_message(
            query="Q",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        assert "<player_data>" not in msg


class TestParseResponse:
    def test_parse_json_response(self, svc):
        response = '{"decision": "Start LeBron", "confidence": "high", "rationale": "He is great"}'
        result = svc._parse_response(response)
        assert result["decision"] == "Start LeBron"
        assert result["confidence"] == "high"
        assert result["source"] == "claude"

    def test_parse_json_with_extra_text(self, svc):
        response = 'Here is my analysis: {"decision": "Sit Player B", "confidence": "low", "rationale": "Injured"}'
        result = svc._parse_response(response)
        assert result["decision"] == "Sit Player B"

    def test_parse_json_missing_fields(self, svc):
        response = '{"other": "data"}'
        result = svc._parse_response(response)
        assert result["decision"] == "Unable to determine"
        assert result["confidence"] == "medium"

    def test_parse_freeform(self, svc):
        response = "Start LeBron James. He has been playing well. Confidence: high."
        result = svc._parse_freeform_response(response)
        assert "Start LeBron James" in result["decision"]
        assert result["confidence"] == "high"

    def test_parse_freeform_no_confidence(self, svc):
        response = "I would recommend sitting this player due to matchup."
        result = svc._parse_freeform_response(response)
        assert result["confidence"] == "medium"  # default

    def test_parse_freeform_arrow_pattern(self, svc):
        response = "→ Start Mahomes — he's been hot"
        result = svc._parse_freeform_response(response)
        assert result["source"] == "claude"

    def test_parse_invalid_json_falls_back(self, svc):
        response = "{ broken json here"
        result = svc._parse_response(response)
        assert result["source"] == "claude"


class TestMakeDecisionNoClient:
    @pytest.mark.asyncio
    async def test_raises_without_api_key(self, svc):
        with pytest.raises(RuntimeError, match="Claude API not configured"):
            await svc.make_decision(
                query="test", sport="nba", risk_mode="safe", decision_type="start_sit"
            )

    @pytest.mark.asyncio
    async def test_stream_raises_without_api_key(self, svc):
        with pytest.raises(RuntimeError, match="Claude API not configured"):
            async for _ in svc.make_decision_stream(
                query="test", sport="nba", risk_mode="safe", decision_type="start_sit"
            ):
                pass
