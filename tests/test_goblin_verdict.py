"""
Tests for the Goblin Verdict service.

Covers: models, context builder, prompt generation, verdict service
(cache hit, cache miss, generation, error handling).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.goblin_verdict import (
    VERDICT_CACHE_TTL,
    GoblinVerdict,
    GoblinVerdictService,
    PlayerBrief,
    RiskMode,
    SwapRecommendation,
    build_verdict_context,
    build_verdict_prompt,
)

# Patch targets — lazy imports from source modules
_REDIS = "services.redis.redis_service"
_DB = "services.database.db_service"
_SLEEPER = "services.sleeper.sleeper_service"
_CLAUDE = "services.claude.claude_service"


# =============================================================================
# MODEL TESTS
# =============================================================================


class TestModels:
    """Test Pydantic model creation and validation."""

    def test_player_brief_defaults(self):
        p = PlayerBrief(name="Josh Allen", position="QB", team="BUF")
        assert p.opponent == ""
        assert p.projected_points == 0.0
        assert p.trend == "stable"
        assert p.injury_flag is None

    def test_swap_recommendation(self):
        s = SwapRecommendation(
            bench_player="Adams",
            start_player="Nacua",
            confidence=78,
            reasoning="Better matchup.",
            urgency="critical",
        )
        assert s.confidence == 78
        assert s.urgency == "critical"

    def test_swap_confidence_bounds(self):
        """Confidence must be 0-100."""
        with pytest.raises(Exception):
            SwapRecommendation(
                bench_player="A",
                start_player="B",
                confidence=150,
                reasoning="x",
            )

    def test_goblin_verdict_defaults(self):
        v = GoblinVerdict()
        assert v.risk_mode == RiskMode.MEDIAN
        assert v.swaps == []
        assert v.cached is False

    def test_risk_mode_values(self):
        assert RiskMode.FLOOR.value == "floor"
        assert RiskMode.MEDIAN.value == "median"
        assert RiskMode.CEILING.value == "ceiling"


# =============================================================================
# CONTEXT BUILDER
# =============================================================================


class TestContextBuilder:
    """Test the context assembly function."""

    def test_basic_context(self):
        starters = [
            {
                "name": "Josh Allen",
                "position": "QB",
                "team": "BUF",
                "opponent": "MIA",
                "projected_pts": 22.5,
                "goblin_score": 85,
            }
        ]
        bench = [
            {
                "name": "Jalen Hurts",
                "position": "QB",
                "team": "PHI",
                "opponent": "DAL",
                "projected_pts": 20.1,
                "goblin_score": 78,
                "injury_status": "Questionable - Knee",
            }
        ]

        ctx = build_verdict_context(
            league_name="Test League",
            scoring_format="PPR",
            week=14,
            season="2025",
            starters=starters,
            bench=bench,
            opponent_name="Team B",
            opponent_projected=110.5,
            win_probability=62.0,
        )

        assert "Test League" in ctx
        assert "PPR" in ctx
        assert "Week: 14" in ctx
        assert "Josh Allen" in ctx
        assert "Jalen Hurts" in ctx
        assert "INJURY: Questionable - Knee" in ctx
        assert "Team B" in ctx
        assert "110.5" in ctx
        assert "62.0%" in ctx

    def test_empty_roster(self):
        ctx = build_verdict_context(
            league_name="Empty",
            scoring_format="Standard",
            week=1,
            season="2025",
            starters=[],
            bench=[],
        )
        assert "(no starters set)" in ctx
        assert "(empty bench)" in ctx

    def test_no_win_probability(self):
        ctx = build_verdict_context(
            league_name="L",
            scoring_format="PPR",
            week=1,
            season="2025",
            starters=[],
            bench=[],
            win_probability=None,
        )
        assert "N/A" in ctx


# =============================================================================
# PROMPT BUILDER
# =============================================================================


class TestPromptBuilder:
    """Test prompt generation."""

    def test_prompt_includes_persona(self):
        prompt = build_verdict_prompt("context here", "median")
        assert "Goblin" in prompt
        assert "brutally honest" in prompt

    def test_prompt_includes_context(self):
        prompt = build_verdict_prompt("MY ROSTER DATA", "floor")
        assert "MY ROSTER DATA" in prompt

    def test_floor_mode_instructions(self):
        prompt = build_verdict_prompt("ctx", "floor")
        assert "FLOOR" in prompt
        assert "guaranteed volume" in prompt

    def test_ceiling_mode_instructions(self):
        prompt = build_verdict_prompt("ctx", "ceiling")
        assert "CEILING" in prompt
        assert "upside" in prompt

    def test_median_mode_instructions(self):
        prompt = build_verdict_prompt("ctx", "median")
        assert "MEDIAN" in prompt
        assert "expected value" in prompt

    def test_prompt_requests_json(self):
        prompt = build_verdict_prompt("ctx", "median")
        assert "JSON" in prompt
        assert "verdict_headline" in prompt
        assert "swaps" in prompt

    def test_unknown_risk_mode_falls_back(self):
        """Unknown risk mode should still produce a valid prompt."""
        prompt = build_verdict_prompt("ctx", "unknown")
        assert "UNKNOWN" in prompt
        # Falls back to median instructions
        assert "expected value" in prompt


# =============================================================================
# VERDICT SERVICE — CACHE
# =============================================================================


class TestVerdictServiceCache:
    """Test Redis cache hit/miss behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_verdict(self):
        svc = GoblinVerdictService()
        cached_data = GoblinVerdict(
            team_name="Cached Team",
            week=14,
            verdict_headline="Cached headline",
        ).model_dump()

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.get = AsyncMock(
            return_value=json.dumps(cached_data, default=str)
        )

        with patch(_REDIS, mock_redis):
            verdict = await svc.get_verdict("user123", "median", week=14)

        assert verdict is not None
        assert verdict.cached is True
        assert verdict.team_name == "Cached Team"

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_generation(self):
        svc = GoblinVerdictService()

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.get = AsyncMock(return_value=None)

        generated = GoblinVerdict(team_name="Generated", week=14)

        with (
            patch(_REDIS, mock_redis),
            patch.object(
                svc, "generate_verdict", new_callable=AsyncMock, return_value=generated
            ),
        ):
            verdict = await svc.get_verdict("user123", "median", week=14)

        assert verdict is not None
        assert verdict.team_name == "Generated"

    @pytest.mark.asyncio
    async def test_redis_unavailable_triggers_generation(self):
        svc = GoblinVerdictService()

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        generated = GoblinVerdict(team_name="OnDemand", week=14)

        with (
            patch(_REDIS, mock_redis),
            patch.object(
                svc, "generate_verdict", new_callable=AsyncMock, return_value=generated
            ),
        ):
            verdict = await svc.get_verdict("user123", "median", week=14)

        assert verdict is not None
        assert verdict.team_name == "OnDemand"

    @pytest.mark.asyncio
    async def test_redis_error_triggers_generation(self):
        svc = GoblinVerdictService()

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.get = AsyncMock(side_effect=Exception("Redis down"))

        generated = GoblinVerdict(team_name="Fallback", week=14)

        with (
            patch(_REDIS, mock_redis),
            patch.object(
                svc, "generate_verdict", new_callable=AsyncMock, return_value=generated
            ),
        ):
            verdict = await svc.get_verdict("user123", "median", week=14)

        assert verdict is not None
        assert verdict.team_name == "Fallback"


# =============================================================================
# VERDICT SERVICE — GENERATION
# =============================================================================


class TestVerdictServiceGeneration:
    """Test on-demand verdict generation."""

    @pytest.mark.asyncio
    async def test_no_user_data_returns_none(self):
        svc = GoblinVerdictService()

        with patch.object(
            svc, "_get_user_league_data", new_callable=AsyncMock, return_value=None
        ):
            result = await svc.generate_verdict("user123", "median", 14)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_league_returns_none(self):
        svc = GoblinVerdictService()
        user_data = {
            "sleeper_league_id": "league1",
            "sleeper_user_id": "sleeper1",
            "team_name": "Test",
            "sport": "nfl",
        }

        mock_sleeper = MagicMock()
        mock_sleeper.get_league = AsyncMock(return_value=None)

        with (
            patch.object(
                svc,
                "_get_user_league_data",
                new_callable=AsyncMock,
                return_value=user_data,
            ),
            patch(_SLEEPER, mock_sleeper),
        ):
            result = await svc.generate_verdict("user123", "median", 14)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_roster_returns_none(self):
        svc = GoblinVerdictService()
        user_data = {
            "sleeper_league_id": "league1",
            "sleeper_user_id": "sleeper1",
            "team_name": "Test",
            "sport": "nfl",
        }

        mock_league = MagicMock()
        mock_league.name = "Test League"
        mock_league.season = "2025"
        mock_league.scoring_settings = {"rec": 1}

        mock_sleeper = MagicMock()
        mock_sleeper.get_league = AsyncMock(return_value=mock_league)
        mock_sleeper.get_user_roster = AsyncMock(return_value=None)

        with (
            patch.object(
                svc,
                "_get_user_league_data",
                new_callable=AsyncMock,
                return_value=user_data,
            ),
            patch(_SLEEPER, mock_sleeper),
        ):
            result = await svc.generate_verdict("user123", "median", 14)

        assert result is None

    @pytest.mark.asyncio
    async def test_claude_failure_returns_none(self):
        svc = GoblinVerdictService()
        user_data = {
            "sleeper_league_id": "league1",
            "sleeper_user_id": "sleeper1",
            "team_name": "Test",
            "sport": "nfl",
        }

        mock_league = MagicMock()
        mock_league.name = "Test League"
        mock_league.season = "2025"
        mock_league.scoring_settings = {"rec": 1}

        mock_roster = MagicMock()
        mock_roster.roster_id = 1
        mock_roster.starters = ["p1"]
        mock_roster.players = ["p1", "p2"]

        mock_sleeper = MagicMock()
        mock_sleeper.get_league = AsyncMock(return_value=mock_league)
        mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
        mock_sleeper.get_all_players = AsyncMock(
            return_value={
                "p1": {"full_name": "Player A", "position": "QB", "team": "BUF"},
                "p2": {"full_name": "Player B", "position": "QB", "team": "PHI"},
            }
        )
        mock_sleeper.get_league_matchups = AsyncMock(return_value=[])

        with (
            patch.object(
                svc,
                "_get_user_league_data",
                new_callable=AsyncMock,
                return_value=user_data,
            ),
            patch(_SLEEPER, mock_sleeper),
            patch.object(
                svc, "_call_claude", new_callable=AsyncMock, return_value=None
            ),
        ):
            result = await svc.generate_verdict("user123", "median", 14)

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_generation(self):
        svc = GoblinVerdictService()
        user_data = {
            "sleeper_league_id": "league1",
            "sleeper_user_id": "sleeper1",
            "team_name": "Goblin Squad",
            "sport": "nfl",
        }

        mock_league = MagicMock()
        mock_league.name = "Test League"
        mock_league.season = "2025"
        mock_league.scoring_settings = {"rec": 1}

        mock_roster = MagicMock()
        mock_roster.roster_id = 1
        mock_roster.starters = ["p1"]
        mock_roster.players = ["p1", "p2"]

        mock_sleeper = MagicMock()
        mock_sleeper.get_league = AsyncMock(return_value=mock_league)
        mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
        mock_sleeper.get_all_players = AsyncMock(
            return_value={
                "p1": {"full_name": "Player A", "position": "QB", "team": "BUF"},
                "p2": {"full_name": "Player B", "position": "WR", "team": "PHI"},
            }
        )
        mock_sleeper.get_league_matchups = AsyncMock(return_value=[])

        claude_response = {
            "verdict_headline": "Your bench has a problem",
            "overall_outlook": "Looking shaky this week.",
            "swaps": [
                {
                    "bench_player": "Player A",
                    "start_player": "Player B",
                    "confidence": 72,
                    "reasoning": "Better matchup by far.",
                    "urgency": "critical",
                }
            ],
        }

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()

        with (
            patch.object(
                svc,
                "_get_user_league_data",
                new_callable=AsyncMock,
                return_value=user_data,
            ),
            patch(_SLEEPER, mock_sleeper),
            patch.object(
                svc,
                "_call_claude",
                new_callable=AsyncMock,
                return_value=claude_response,
            ),
            patch(_REDIS, mock_redis),
        ):
            result = await svc.generate_verdict("user123", "median", 14)

        assert result is not None
        assert result.team_name == "Goblin Squad"
        assert result.verdict_headline == "Your bench has a problem"
        assert len(result.swaps) == 1
        assert result.swaps[0].confidence == 72
        assert result.swaps[0].urgency == "critical"


# =============================================================================
# VERDICT SERVICE — HELPERS
# =============================================================================


class TestVerdictServiceHelpers:
    """Test internal helper methods."""

    def test_split_roster(self):
        svc = GoblinVerdictService()
        roster = MagicMock()
        roster.starters = ["p1"]
        roster.players = ["p1", "p2", "p3"]

        all_players = {
            "p1": {"full_name": "Starter A", "position": "QB", "team": "BUF"},
            "p2": {"full_name": "Bench B", "position": "WR", "team": "KC"},
            "p3": {"full_name": "Bench C", "position": "RB", "team": "SF"},
        }

        starters, bench = svc._split_roster(roster, all_players)
        assert len(starters) == 1
        assert starters[0]["name"] == "Starter A"
        assert len(bench) == 2

    def test_split_roster_missing_player(self):
        svc = GoblinVerdictService()
        roster = MagicMock()
        roster.starters = ["p1"]
        roster.players = ["p1", "p99"]  # p99 not in all_players

        all_players = {
            "p1": {"full_name": "Known", "position": "QB", "team": "BUF"},
        }

        starters, bench = svc._split_roster(roster, all_players)
        assert len(starters) == 1
        assert len(bench) == 0  # p99 skipped

    def test_find_opponent_found(self):
        svc = GoblinVerdictService()
        matchups = [
            MagicMock(matchup_id=1, roster_id=1, points=95.5),
            MagicMock(matchup_id=1, roster_id=2, points=110.2),
            MagicMock(matchup_id=2, roster_id=3, points=88.0),
        ]

        name, pts = svc._find_opponent(1, matchups)
        assert name == "Roster #2"
        assert pts == 110.2

    def test_find_opponent_not_found(self):
        svc = GoblinVerdictService()
        name, pts = svc._find_opponent(99, [])
        assert name == "Unknown"
        assert pts == 0.0

    def test_current_week_in_season(self):
        svc = GoblinVerdictService()
        week = svc._current_week()
        assert 1 <= week <= 18

    def test_scoring_format_detection(self):
        """Test PPR/Half-PPR/Standard detection in generate_verdict."""
        # PPR: rec >= 1
        assert _detect_format({"rec": 1}) == "PPR"
        assert _detect_format({"rec": 1.0}) == "PPR"
        # Half-PPR: rec >= 0.5
        assert _detect_format({"rec": 0.5}) == "Half-PPR"
        # Standard: rec < 0.5 or missing
        assert _detect_format({"rec": 0}) == "Standard"
        assert _detect_format({}) == "Standard"


def _detect_format(scoring: dict) -> str:
    """Helper: replicate the scoring format logic from generate_verdict."""
    rec = scoring.get("rec", 0)
    if rec >= 1:
        return "PPR"
    elif rec >= 0.5:
        return "Half-PPR"
    return "Standard"


# =============================================================================
# VERDICT SERVICE — CLAUDE INTEGRATION
# =============================================================================


class TestClaudeIntegration:
    """Test Claude API call handling."""

    @pytest.mark.asyncio
    async def test_claude_unavailable_returns_none(self):
        svc = GoblinVerdictService()
        mock_claude = MagicMock()
        mock_claude.is_available = False

        with patch(_CLAUDE, mock_claude):
            result = await svc._call_claude("context", "median")

        assert result is None

    @pytest.mark.asyncio
    async def test_claude_valid_json_response(self):
        svc = GoblinVerdictService()
        expected = {"verdict_headline": "Test", "swaps": []}

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(expected))]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_claude = MagicMock()
        mock_claude.is_available = True
        mock_claude.client = mock_client

        with patch(_CLAUDE, mock_claude):
            result = await svc._call_claude("context", "median")

        assert result == expected

    @pytest.mark.asyncio
    async def test_claude_markdown_fenced_json(self):
        svc = GoblinVerdictService()
        expected = {"verdict_headline": "Fenced", "swaps": []}
        fenced = f"```json\n{json.dumps(expected)}\n```"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=fenced)]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_claude = MagicMock()
        mock_claude.is_available = True
        mock_claude.client = mock_client

        with patch(_CLAUDE, mock_claude):
            result = await svc._call_claude("context", "median")

        assert result is not None
        assert result["verdict_headline"] == "Fenced"

    @pytest.mark.asyncio
    async def test_claude_invalid_json_returns_none(self):
        svc = GoblinVerdictService()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Not valid JSON at all")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_claude = MagicMock()
        mock_claude.is_available = True
        mock_claude.client = mock_client

        with patch(_CLAUDE, mock_claude):
            result = await svc._call_claude("context", "median")

        assert result is None

    @pytest.mark.asyncio
    async def test_claude_api_error_returns_none(self):
        svc = GoblinVerdictService()

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API timeout"))

        mock_claude = MagicMock()
        mock_claude.is_available = True
        mock_claude.client = mock_client

        with patch(_CLAUDE, mock_claude):
            result = await svc._call_claude("context", "median")

        assert result is None


# =============================================================================
# CACHE WRITE
# =============================================================================


class TestCacheWrite:
    """Test verdict caching in Redis."""

    @pytest.mark.asyncio
    async def test_cache_verdict_stores_in_redis(self):
        svc = GoblinVerdictService()
        verdict = GoblinVerdict(team_name="Cached", week=14)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()

        with patch(_REDIS, mock_redis):
            await svc._cache_verdict("key:123", verdict)

        mock_redis._client.setex.assert_called_once()
        args = mock_redis._client.setex.call_args
        assert args[0][0] == "key:123"
        assert args[0][1] == VERDICT_CACHE_TTL

    @pytest.mark.asyncio
    async def test_cache_verdict_redis_unavailable(self):
        svc = GoblinVerdictService()
        verdict = GoblinVerdict(team_name="NoCacheAvail", week=14)

        mock_redis = MagicMock()
        mock_redis.is_connected = False

        with patch(_REDIS, mock_redis):
            # Should not crash
            await svc._cache_verdict("key:123", verdict)

    @pytest.mark.asyncio
    async def test_cache_verdict_redis_error(self):
        svc = GoblinVerdictService()
        verdict = GoblinVerdict(team_name="Error", week=14)

        mock_redis = MagicMock()
        mock_redis.is_connected = True
        mock_redis._client = AsyncMock()
        mock_redis._client.setex = AsyncMock(side_effect=Exception("Redis write fail"))

        with patch(_REDIS, mock_redis):
            # Should not crash
            await svc._cache_verdict("key:123", verdict)


# =============================================================================
# GOBLIN ROUTE TESTS
# =============================================================================


VALID_USER = {
    "user_id": "google-123",
    "email": "test@example.com",
    "name": "Test User",
    "tier": "pro",
    "exp": 9999999999,
}


@pytest.fixture
def authed_client(test_client):
    """Test client with auth bypassed."""
    from api.main import app
    from routes.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: VALID_USER
    yield test_client
    app.dependency_overrides.pop(get_current_user, None)


class TestGoblinRoutes:
    """Test /goblin/* API routes."""

    def test_verdict_no_auth(self, test_client):
        resp = test_client.get("/goblin/verdict")
        assert resp.status_code in (401, 403)

    def test_verdict_no_league(self, authed_client):
        with patch(
            "services.goblin_verdict.goblin_verdict_service.get_verdict",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = authed_client.get("/goblin/verdict")
            assert resp.status_code == 404

    def test_verdict_success(self, authed_client):
        verdict = GoblinVerdict(
            team_name="Test Team",
            week=14,
            risk_mode=RiskMode.FLOOR,
            verdict_headline="You're fine",
            swaps=[],
        )

        with patch(
            "services.goblin_verdict.goblin_verdict_service.get_verdict",
            new_callable=AsyncMock,
            return_value=verdict,
        ):
            resp = authed_client.get("/goblin/verdict?risk_mode=floor&week=14")
            assert resp.status_code == 200
            data = resp.json()
            assert data["team_name"] == "Test Team"
            assert data["risk_mode"] == "floor"

    def test_generate_no_auth(self, test_client):
        resp = test_client.post("/goblin/verdict/generate")
        assert resp.status_code in (401, 403)

    def test_generate_success(self, authed_client):
        verdict = GoblinVerdict(
            team_name="Fresh",
            week=14,
            verdict_headline="Generated fresh",
        )

        with patch(
            "services.goblin_verdict.goblin_verdict_service.generate_verdict",
            new_callable=AsyncMock,
            return_value=verdict,
        ):
            resp = authed_client.post(
                "/goblin/verdict/generate?risk_mode=ceiling&week=14"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["verdict_headline"] == "Generated fresh"

    def test_generate_failure(self, authed_client):
        with patch(
            "services.goblin_verdict.goblin_verdict_service.generate_verdict",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = authed_client.post("/goblin/verdict/generate")
            assert resp.status_code == 404
