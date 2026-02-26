"""Tests for Claude API service."""

from unittest.mock import MagicMock, patch

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


@pytest.fixture
def svc_with_client():
    """ClaudeService with a mocked Anthropic client."""
    s = ClaudeService()
    s.client = MagicMock()
    ClaudeService.clear_cache()

    # Build a mock response
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 100
    mock_response.output_tokens = 50
    mock_response.usage.output_tokens = 50
    mock_response.content = [
        MagicMock(
            text='{"decision": "Start LeBron", "confidence": "high", "rationale": "Hot streak"}'
        )
    ]
    s.client.messages.create.return_value = mock_response
    yield s
    ClaudeService.clear_cache()


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


class TestParseResponseJSONDecodeError:
    def test_invalid_json_with_braces_falls_back(self, svc):
        """Lines 269-270: regex matches braces but json.loads fails."""
        response = "{this is not: valid json content}"
        result = svc._parse_response(response)
        # Falls through to freeform parsing
        assert result["source"] == "claude"
        assert "details" in result


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


class TestMakeDecisionWithClient:
    """Lines 150-193: make_decision full flow with mocked client."""

    @pytest.mark.asyncio
    @patch("services.claude.track_claude_request")
    @patch("services.claude.get_prompt", return_value="system prompt")
    async def test_fresh_call(self, _mock_prompt, mock_track, svc_with_client):
        result = await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        assert result["decision"] == "Start LeBron"
        assert result["cached"] is False
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        svc_with_client.client.messages.create.assert_called_once()
        mock_track.assert_called_once_with(100, 50, success=True, variant="control")

    @pytest.mark.asyncio
    @patch("services.claude.track_claude_request")
    @patch("services.claude.get_prompt", return_value="system prompt")
    async def test_cache_hit(self, _mock_prompt, _mock_track, svc_with_client):
        # First call populates cache
        await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        # Second call should hit cache
        result = await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        assert result["cached"] is True
        # API only called once
        assert svc_with_client.client.messages.create.call_count == 1
        assert ClaudeService._cache_hits == 1

    @pytest.mark.asyncio
    @patch("services.claude.track_claude_request")
    @patch("services.claude.get_prompt", return_value="system prompt")
    async def test_use_cache_false(self, _mock_prompt, _mock_track, svc_with_client):
        # First call populates cache
        await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        )
        # Second call with use_cache=False should call API again
        result = await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
            use_cache=False,
        )
        assert result["cached"] is False
        assert svc_with_client.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    @patch("services.claude.track_claude_request")
    @patch("services.claude.get_prompt", return_value="system prompt")
    async def test_prompt_variant_forwarded(
        self, mock_prompt, _mock_track, svc_with_client
    ):
        await svc_with_client.make_decision(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
            prompt_variant="concise_v1",
        )
        mock_prompt.assert_called_with("concise_v1")


class TestMakeDecisionStream:
    """Lines 195-251: make_decision_stream with mocked client."""

    @pytest.mark.asyncio
    @patch("services.claude.track_claude_request")
    @patch("services.claude.get_prompt", return_value="system prompt")
    async def test_stream_yields_text_and_metadata(
        self, _mock_prompt, mock_track, svc_with_client
    ):
        # Build mock stream context manager
        mock_final = MagicMock()
        mock_final.usage.input_tokens = 80
        mock_final.usage.output_tokens = 40

        mock_stream = MagicMock()
        mock_stream.text_stream = iter(["Start ", "LeBron"])
        mock_stream.get_final_message.return_value = mock_final
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        svc_with_client.client.messages.stream.return_value = mock_stream

        chunks = []
        async for chunk in svc_with_client.make_decision_stream(
            query="Start LeBron?",
            sport="nba",
            risk_mode="safe",
            decision_type="start_sit",
        ):
            chunks.append(chunk)

        # Text chunks first, then metadata dict
        assert chunks[0] == "Start "
        assert chunks[1] == "LeBron"
        assert isinstance(chunks[2], dict)
        assert chunks[2]["_metadata"] is True
        assert chunks[2]["input_tokens"] == 80
        assert chunks[2]["output_tokens"] == 40
        assert chunks[2]["full_response"] == "Start LeBron"
        mock_track.assert_called_once_with(80, 40, success=True, variant="control")
