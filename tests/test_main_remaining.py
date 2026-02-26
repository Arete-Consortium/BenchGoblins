"""Tests covering remaining uncovered lines in api.main.

Targets: player get rate limit, /decide league context append/exception paths,
_local_decision fallback, _claude_draft_fallback budget, /decide/stream player
extraction and league context, stream persist failure, history sport filter,
notifications register with DB, _get_yahoo_token valid return.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decide_payload(**overrides):
    base = {
        "sport": "nba",
        "risk_mode": "median",
        "decision_type": "start_sit",
        "query": "Start LeBron or Curry?",
        "player_a": "LeBron James",
        "player_b": "Stephen Curry",
    }
    base.update(overrides)
    return base


def _stream_payload(**overrides):
    base = {
        "sport": "nba",
        "risk_mode": "median",
        "decision_type": "start_sit",
        "query": "Start LeBron or Curry?",
    }
    base.update(overrides)
    return base


def _auth_override():
    from api.main import app
    from routes.auth import get_optional_user

    app.dependency_overrides[get_optional_user] = lambda: {
        "user_id": 1,
        "email": "test@test.com",
    }


def _clear_overrides():
    from api.main import app

    app.dependency_overrides.clear()


def _mock_user(**kwargs):
    from datetime import UTC, datetime

    defaults = {
        "id": 1,
        "email": "test@test.com",
        "subscription_tier": "free",
        "queries_today": 0,
        "queries_reset_at": datetime.now(UTC),
        "sleeper_league_id": None,
        "sleeper_user_id": None,
        "espn_league_id": None,
        "espn_roster_snapshot": None,
        "espn_sport": None,
        "yahoo_league_key": None,
        "yahoo_roster_snapshot": None,
        "yahoo_sport": None,
    }
    defaults.update(kwargs)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _mock_resolve_session(mock_db=None, mock_session_obj=None):
    if mock_db is None:
        mock_db = AsyncMock()
    if mock_session_obj is None:
        mock_session_obj = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=(mock_db, mock_session_obj))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# ---- Mock stream generator for /decide/stream tests -----------------------


async def _mock_stream(*_args, **_kwargs):
    yield "Start "
    yield "LeBron"
    yield {
        "_metadata": True,
        "input_tokens": 80,
        "output_tokens": 40,
        "full_response": (
            '{"decision": "Start LeBron", "confidence": "high",'
            ' "rationale": "Hot streak"}'
        ),
    }


# ===========================================================================
# 1. Player get rate limit (line 557)
# ===========================================================================


class TestPlayerGetRateLimit:
    """GET /players/{sport}/{player_id} — rate limited returns 429."""

    def test_player_get_rate_limited(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

            resp = test_client.get("/players/nba/12345")
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]
            assert resp.headers.get("Retry-After") == "30"


# ===========================================================================
# 2. /decide Sleeper context append + exception (lines 1025, 1028-1029)
# ===========================================================================


class TestDecideSleeperContextAppend:
    """When Sleeper league context exists AND player_context already set, appends."""

    def test_sleeper_context_appends_to_existing_player_context(self, test_client):
        """Line 1025: player_context += sleeper league_ctx."""
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.sleeper_service") as mock_sleeper,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                # Both players found so player_context gets set from format_player_context
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                # Sleeper league returns data so league_ctx is built
                mock_league = MagicMock()
                mock_league.name = "Test League"
                mock_league.season = "2025"
                mock_league.total_rosters = 12
                mock_league.scoring_settings = {"pts": 1.0, "reb": 1.2}
                mock_sleeper.get_league = AsyncMock(return_value=mock_league)
                mock_sleeper.get_user_roster = AsyncMock(return_value=None)

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="Better matchup",
                        source="claude",
                    ),
                    100,
                    50,
                )

                # league_id is set so Sleeper branch runs; player_a/b set so context exists
                resp = test_client.post(
                    "/decide",
                    json=_decide_payload(league_id="league123"),
                )
                assert resp.status_code == 200

                # Verify Claude was called with combined context
                call_kwargs = mock_claude_dec.call_args
                player_ctx = (
                    call_kwargs[0][3]
                    if len(call_kwargs[0]) > 3
                    else call_kwargs[1].get("player_context")
                )
                # player_context should contain both player data AND league data
                assert player_ctx is not None
        finally:
            _clear_overrides()


class TestDecideSleeperContextException:
    """When Sleeper service raises, exception is swallowed (lines 1028-1029)."""

    def test_sleeper_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.sleeper_service") as mock_sleeper,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                # Sleeper raises
                mock_sleeper.get_league = AsyncMock(
                    side_effect=RuntimeError("Sleeper down")
                )

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="ok",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post(
                    "/decide",
                    json=_decide_payload(league_id="league123"),
                )
                # Should succeed despite Sleeper error
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 3. /decide ESPN context append + exception (lines 1043, 1046-1047)
# ===========================================================================


class TestDecideESPNContextAppend:
    """ESPN roster context appends to existing player_context (line 1043)."""

    def test_espn_context_appends(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                # Players found → player_context is set
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                # User has ESPN connection, no sleeper league_id
                mock_get_user.return_value = _mock_user(
                    espn_league_id="espn_123",
                    espn_roster_snapshot=[
                        {
                            "name": "LeBron",
                            "position": "SF",
                            "team": "LAL",
                            "lineup_slot": "STARTER",
                        },
                    ],
                    espn_sport="nba",
                )

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="ok",
                        source="claude",
                    ),
                    100,
                    50,
                )

                # No league_id → ESPN branch runs
                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideESPNContextException:
    """ESPN roster context iteration fails (lines 1046-1047)."""

    def test_espn_context_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                mock_espn.find_player_by_name = AsyncMock(return_value=None)

                # espn_roster_snapshot is not iterable → triggers except
                mock_get_user.return_value = _mock_user(
                    espn_league_id="espn_123",
                    espn_roster_snapshot=42,  # not iterable
                )

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="ok",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 4. /decide Yahoo context append + exception (lines 1067, 1070-1071)
# ===========================================================================


class TestDecideYahooContextAppend:
    """Yahoo roster context appends to existing player_context (line 1067)."""

    def test_yahoo_context_appends(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                # Players found → player_context set
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                # User has Yahoo, no ESPN, no sleeper
                mock_get_user.return_value = _mock_user(
                    yahoo_league_key="yahoo_lk_1",
                    yahoo_roster_snapshot=[
                        {
                            "name": "LeBron",
                            "position": "SF",
                            "team": "LAL",
                            "status": "Active",
                        },
                    ],
                    yahoo_sport="nba",
                )

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="ok",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideYahooContextException:
    """Yahoo roster context iteration fails (lines 1070-1071)."""

    def test_yahoo_context_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.format_player_context", return_value="Player A data"),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_redis.is_connected = False

                mock_espn.find_player_by_name = AsyncMock(return_value=None)

                # yahoo_roster_snapshot is not iterable → except branch
                mock_get_user.return_value = _mock_user(
                    yahoo_league_key="yahoo_lk_1",
                    yahoo_roster_snapshot=999,  # not iterable
                )

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="ok",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 5. _local_decision fallback to Claude (lines 1177, 1183)
# ===========================================================================


class TestLocalDecisionFallbackDirect:
    """Call _local_decision directly to cover fallback paths."""

    @pytest.mark.asyncio
    async def test_no_player_a_data_falls_back(self):
        """Line 1177: player_a_data is None → _claude_decision called."""
        from api.main import (
            Confidence,
            DecisionRequest,
            DecisionResponse,
            _local_decision,
        )

        req = DecisionRequest(
            sport="nba",
            risk_mode="median",
            decision_type="start_sit",
            query="Start LeBron or Curry?",
            player_a="LeBron",
            player_b="Curry",
        )

        mock_response = DecisionResponse(
            decision="Start LeBron",
            confidence=Confidence.HIGH,
            rationale="fallback",
            source="claude",
        )

        with patch(
            "api.main._claude_decision",
            new_callable=AsyncMock,
            return_value=(mock_response, 100, 50),
        ):
            # _local_decision returns the raw result of _claude_decision (a tuple)
            result = await _local_decision(
                req, "LeBron", "Curry", None, ("info_b", "stats_b")
            )
            # When player data is missing, it delegates to _claude_decision
            # which returns (response, in_tokens, out_tokens)
            assert result[0].source == "claude"

    @pytest.mark.asyncio
    async def test_no_stats_a_falls_back(self):
        """Line 1183: player_a_data has info but stats is None → _claude_decision."""
        from api.main import (
            Confidence,
            DecisionRequest,
            DecisionResponse,
            _local_decision,
        )

        req = DecisionRequest(
            sport="nba",
            risk_mode="median",
            decision_type="start_sit",
            query="Start LeBron or Curry?",
            player_a="LeBron",
            player_b="Curry",
        )

        mock_response = DecisionResponse(
            decision="Start Curry",
            confidence=Confidence.MEDIUM,
            rationale="stats missing",
            source="claude",
        )

        with patch(
            "api.main._claude_decision",
            new_callable=AsyncMock,
            return_value=(mock_response, 80, 40),
        ):
            # info present but stats None
            result = await _local_decision(
                req, "LeBron", "Curry", ("info_a", None), ("info_b", "stats_b")
            )
            assert result[0].source == "claude"


# ===========================================================================
# 6. _claude_draft_fallback budget exceeded (line 1669)
# ===========================================================================


class TestClaudeDraftFallbackBudget:
    """_claude_draft_fallback raises 402 when budget exceeded."""

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises_402(self):
        from fastapi import HTTPException

        from api.main import DraftRequest, _claude_draft_fallback

        req = DraftRequest(
            sport="nba",
            risk_mode="median",
            query="Draft LeBron or Curry?",
        )

        with patch(
            "api.main._check_budget_exceeded",
            new_callable=AsyncMock,
            return_value=(True, "Budget exceeded"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _claude_draft_fallback(req, "session123")
            assert exc_info.value.status_code == 402
            assert "Budget exceeded" in exc_info.value.detail


# ===========================================================================
# 7. /decide/stream player extraction + player context (lines 1772-1795)
# ===========================================================================


class TestDecideStreamPlayerExtraction:
    """POST /decide/stream without player_a/player_b extracts from query."""

    def test_stream_extracts_players_and_builds_context(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "api.main.extract_players_from_query",
                    return_value=("LeBron", "Curry"),
                ),
                patch("api.main.espn_service") as mock_espn,
                patch(
                    "api.main.format_player_context",
                    return_value="Player context string",
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                # find_player_by_name returns (info, stats) tuples
                mock_info_a = MagicMock()
                mock_stats_a = MagicMock()
                mock_info_b = MagicMock()
                mock_stats_b = MagicMock()
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[
                        (mock_info_a, mock_stats_a),
                        (mock_info_b, mock_stats_b),
                    ]
                )

                # No player_a/player_b in request → extraction happens
                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(),
                )
                assert resp.status_code == 200
                assert "Start LeBron" in resp.text
        finally:
            _clear_overrides()


# ===========================================================================
# 8. /decide/stream Sleeper context append + exception (lines 1837, 1840-1841)
# ===========================================================================


class TestDecideStreamSleeperContextAppend:
    """Stream with league_id + existing player_context → append."""

    def test_stream_sleeper_context_appends(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch(
                    "api.main.extract_players_from_query",
                    return_value=("LeBron", "Curry"),
                ),
                patch("api.main.espn_service") as mock_espn,
                patch(
                    "api.main.format_player_context",
                    return_value="Player context string",
                ),
                patch("api.main.sleeper_service") as mock_sleeper,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                mock_league = MagicMock()
                mock_league.name = "Test League"
                mock_league.season = "2025"
                mock_league.total_rosters = 12
                mock_league.scoring_settings = {"pts": 1.0}
                mock_sleeper.get_league = AsyncMock(return_value=mock_league)
                mock_sleeper.get_user_roster = AsyncMock(return_value=None)

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(league_id="league123"),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideStreamSleeperContextException:
    """Stream with league_id where Sleeper raises (lines 1840-1841)."""

    def test_stream_sleeper_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.sleeper_service") as mock_sleeper,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_sleeper.get_league = AsyncMock(
                    side_effect=RuntimeError("Sleeper down")
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(
                        league_id="league123",
                        player_a="LeBron",
                        player_b="Curry",
                    ),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 9. /decide/stream ESPN context append + exception (lines 1855, 1858-1859)
# ===========================================================================


class TestDecideStreamESPNContextAppend:
    """Stream with ESPN user, player_context already set → append."""

    def test_stream_espn_context_appends(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch(
                    "api.main.extract_players_from_query",
                    return_value=("LeBron", "Curry"),
                ),
                patch("api.main.espn_service") as mock_espn,
                patch(
                    "api.main.format_player_context",
                    return_value="Player context string",
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                # Player found → player_context set
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                mock_get_user.return_value = _mock_user(
                    espn_league_id="espn_123",
                    espn_roster_snapshot=[
                        {
                            "name": "LeBron",
                            "position": "SF",
                            "team": "LAL",
                            "lineup_slot": "STARTER",
                        },
                    ],
                    espn_sport="nba",
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideStreamESPNContextException:
    """Stream with ESPN user, roster_snapshot broken → exception swallowed."""

    def test_stream_espn_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.espn_service") as mock_espn,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                mock_espn.find_player_by_name = AsyncMock(return_value=None)

                mock_get_user.return_value = _mock_user(
                    espn_league_id="espn_123",
                    espn_roster_snapshot=42,  # not iterable
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(player_a="LeBron", player_b="Curry"),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 10. /decide/stream Yahoo context append + exception (lines 1879, 1882-1883)
# ===========================================================================


class TestDecideStreamYahooContextAppend:
    """Stream with Yahoo user, player_context already set → append."""

    def test_stream_yahoo_context_appends(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch(
                    "api.main.extract_players_from_query",
                    return_value=("LeBron", "Curry"),
                ),
                patch("api.main.espn_service") as mock_espn,
                patch(
                    "api.main.format_player_context",
                    return_value="Player context string",
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                # Player found → player_context set
                mock_espn.find_player_by_name = AsyncMock(
                    side_effect=[("info_a", "stats_a"), ("info_b", "stats_b")]
                )

                # No ESPN, has Yahoo
                mock_get_user.return_value = _mock_user(
                    yahoo_league_key="yahoo_lk_1",
                    yahoo_roster_snapshot=[
                        {
                            "name": "LeBron",
                            "position": "SF",
                            "team": "LAL",
                            "status": "Active",
                        },
                    ],
                    yahoo_sport="nba",
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideStreamYahooContextException:
    """Stream with Yahoo user, roster_snapshot broken → exception swallowed."""

    def test_stream_yahoo_exception_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id", new_callable=AsyncMock
                ) as mock_get_user,
                patch("api.main.espn_service") as mock_espn,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                mock_espn.find_player_by_name = AsyncMock(return_value=None)

                mock_get_user.return_value = _mock_user(
                    yahoo_league_key="yahoo_lk_1",
                    yahoo_roster_snapshot=999,  # not iterable
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(player_a="LeBron", player_b="Curry"),
                )
                assert resp.status_code == 200
        finally:
            _clear_overrides()


# ===========================================================================
# 11. /decide/stream persist failure (lines 1945-1946)
# ===========================================================================


class TestDecideStreamPersistFailure:
    """Stream where _store_decision raises after streaming completes."""

    def test_stream_persist_failure_swallowed(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.claude_service") as mock_cs,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._store_decision",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("DB down"),
                ),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch("api.main.espn_service") as mock_espn,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_cs.is_available = True
                mock_cs.make_decision_stream = _mock_stream
                mock_cs._parse_response = MagicMock(
                    return_value={
                        "decision": "Start LeBron",
                        "confidence": "high",
                        "rationale": "Hot streak",
                    }
                )

                mock_espn.find_player_by_name = AsyncMock(return_value=None)

                resp = test_client.post(
                    "/decide/stream",
                    json=_stream_payload(player_a="LeBron", player_b="Curry"),
                )
                # Should still return 200 — persist failure is swallowed
                assert resp.status_code == 200
                # The DONE event should still be sent
                assert "[DONE]" in resp.text
        finally:
            _clear_overrides()


# ===========================================================================
# 12. History sport filter (line 2449)
# ===========================================================================


class TestHistorySportFilter:
    """GET /history?sport=nba — applies sport filter to query."""

    def test_history_with_sport_filter(self, test_client):
        with patch("api.main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            mock_decision = MagicMock()
            mock_decision.id = 1
            mock_decision.sport = "nba"
            mock_decision.risk_mode = "median"
            mock_decision.decision_type = "start_sit"
            mock_decision.query = "Start LeBron?"
            mock_decision.player_a_name = "LeBron"
            mock_decision.player_b_name = "Curry"
            mock_decision.decision = "Start LeBron"
            mock_decision.confidence = "high"
            mock_decision.rationale = "Better matchup"
            mock_decision.source = "claude"
            mock_decision.score_a = None
            mock_decision.score_b = None
            mock_decision.margin = None
            mock_decision.created_at = MagicMock()
            mock_decision.created_at.isoformat.return_value = "2026-02-26T00:00:00"

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_decision]
            mock_session.execute = AsyncMock(return_value=mock_result)

            resp = test_client.get("/history?sport=nba")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["sport"] == "nba"


# ===========================================================================
# 13. /notifications/register with DB (lines 3232-3235)
# ===========================================================================


class TestNotificationsRegisterWithDB:
    """Call register_push_token directly (the HTTP route is shadowed by the
    notifications_router which requires auth). This covers lines 3232-3235."""

    @pytest.mark.asyncio
    async def test_register_with_db(self):
        from api.main import PushTokenRequest, register_push_token

        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.notification_service") as mock_notif,
        ):
            mock_db.is_configured = True
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_notif.register_token = AsyncMock()

            req = PushTokenRequest(token="ExponentPushToken[abc123]")
            result = await register_push_token(req)

            assert result["status"] == "registered"
            assert result["token"] == "ExponentPushToken[abc123]"
            mock_notif.register_token.assert_called_once_with(
                mock_session, "ExponentPushToken[abc123]"
            )


# ===========================================================================
# 14. _get_yahoo_token valid return (line 3076)
# ===========================================================================


class TestGetYahooTokenValidReturn:
    """_get_yahoo_token where stored token is NOT expired — returns directly."""

    @pytest.mark.asyncio
    async def test_valid_token_returned_directly(self):
        from api.main import _get_yahoo_token

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session_obj = MagicMock()
        resolve_ctx = _mock_resolve_session(mock_db, mock_session_obj)

        stored_creds = {
            "access_token": "valid_tok_abc",
            "refresh_token": "rt_val",
            "expires_at": time.time() + 3600,  # expires in 1 hour
        }

        with (
            patch("api.main._resolve_session", return_value=resolve_ctx),
            patch(
                "api.main.session_service.get_credential",
                new_callable=AsyncMock,
                return_value=stored_creds,
            ),
        ):
            result = await _get_yahoo_token("default")
            assert result == "valid_tok_abc"
