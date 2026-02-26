"""Tests for HTTP route endpoints in api.main — covering uncovered lines."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decide_payload(**overrides):
    """Build a minimal /decide POST body."""
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


def _draft_payload(**overrides):
    """Build a minimal /draft POST body."""
    base = {
        "sport": "nba",
        "risk_mode": "median",
        "query": "Draft LeBron or Curry?",
    }
    base.update(overrides)
    return base


def _waiver_payload(**overrides):
    """Build a minimal /waiver/recommend POST body."""
    base = {
        "sport": "nfl",
        "risk_mode": "median",
        "query": "Who should I pick up on waivers?",
        "league_id": "league123",
        "sleeper_user_id": "user456",
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
    """Return a MagicMock that looks like a User ORM row."""
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


# =========================================================================
# Group 1: Health check + /players/search rate limit
# =========================================================================


class TestHealthCheck:
    """Cover lines 497-502, 518."""

    def test_health_db_configured_but_query_fails(self, test_client):
        """Line 497-502: db_service.is_configured=True but engine query raises."""
        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.redis_service") as mock_redis,
        ):
            mock_db.is_configured = True
            mock_engine = MagicMock()
            # Make engine.begin() raise when used as async context manager
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
            mock_engine.begin.return_value = mock_ctx
            mock_db._engine = mock_engine

            mock_redis.is_connected = False

            resp = test_client.get("/health")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "unhealthy"
            assert data["postgres_connected"] is False

    def test_health_db_healthy(self, test_client):
        """Line 518: db IS healthy — returns 200 payload."""
        with (
            patch("api.main.db_service") as mock_db,
            patch("api.main.redis_service") as mock_redis,
            patch("api.main.claude_service") as mock_claude,
        ):
            mock_db.is_configured = True
            mock_engine = MagicMock()
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_engine.begin.return_value = mock_ctx
            mock_db._engine = mock_engine

            mock_redis.is_connected = True
            mock_redis.health_check = AsyncMock(return_value=True)

            mock_claude.is_available = True

            resp = test_client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["postgres_connected"] is True
            assert data["redis_connected"] is True


class TestPlayerSearchRateLimit:
    """Cover line 527: /players/search rate limit exceeded."""

    def test_player_search_rate_limited(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

            resp = test_client.post(
                "/players/search",
                json={"query": "LeBron", "sport": "nba"},
            )
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]


# =========================================================================
# Group 2: /decide deep branches
# =========================================================================


class TestDecideRateLimit:
    """Cover line 886: rate limit exceeded on /decide."""

    def test_decide_rate_limit_exceeded(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 60))

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]


class TestDecideQuotaExceeded:
    """Cover line 897: quota exceeded (402) on /decide."""

    def test_decide_quota_exceeded(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(False, 5, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 402
                data = resp.json()["detail"]
                assert data["code"] == "QUOTA_EXCEEDED"
        finally:
            _clear_overrides()


class TestDecideLeagueProCheck:
    """Cover lines 816-817: stripe_billing.is_league_pro raises."""

    def test_league_pro_check_exception_degrades_gracefully(self, test_client):
        """When is_league_pro raises, user falls back to direct tier (free)."""
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main.db_service") as mock_db,
                patch("api.main.stripe_billing") as mock_stripe,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                # Set up DB session that returns a user with free tier
                mock_user_obj = _mock_user(subscription_tier="free", queries_today=0)
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_user_obj
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_db.is_configured = True
                mock_db.session.return_value = mock_ctx

                # is_league_pro raises
                mock_stripe.is_league_pro = AsyncMock(
                    side_effect=Exception("Stripe down")
                )

                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

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

                resp = test_client.post("/decide", json=_decide_payload())
                # Should succeed — graceful degradation from stripe error
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideFreeTierTzNaiveReset:
    """Cover line 854: tz-naive reset_at handling."""

    def test_tz_naive_reset_at_handled(self, test_client):
        """Free tier with tz-naive queries_reset_at from DB."""
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main.db_service") as mock_db,
                patch("api.main.stripe_billing") as mock_stripe,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                # tz-naive reset_at (no tzinfo) — line 826-827
                naive_dt = datetime(2025, 1, 1, 0, 0, 0)  # No tzinfo
                mock_user_obj = _mock_user(
                    subscription_tier="free",
                    queries_today=0,
                    queries_reset_at=naive_dt,
                )
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = mock_user_obj
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_session.add = MagicMock()
                mock_session.commit = AsyncMock()
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_db.is_configured = True
                mock_db.session.return_value = mock_ctx

                mock_stripe.is_league_pro = AsyncMock(return_value=False)

                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.MEDIUM,
                        rationale="Solid choice",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post("/decide", json=_decide_payload())
                assert resp.status_code == 200
        finally:
            _clear_overrides()


class TestDecideSinglePlayer:
    """Cover lines 965, 967: only player_a or only player_b."""

    def test_only_player_a(self, test_client):
        """Line 965: single player_a, no player_b."""
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.classify_query") as mock_classify,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch(
                "api.main._claude_decision", new_callable=AsyncMock
            ) as mock_claude_dec,
            patch("api.main._store_decision", new_callable=AsyncMock),
            patch("api.main.redis_service") as mock_redis,
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
            patch(
                "api.main.extract_players_from_query",
                return_value=("LeBron James", None),
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)
            mock_redis.is_connected = False

            from api.main import Confidence, DecisionResponse, QueryComplexity

            mock_classify.return_value = QueryComplexity.COMPLEX
            mock_claude_dec.return_value = (
                DecisionResponse(
                    decision="Start LeBron",
                    confidence=Confidence.MEDIUM,
                    rationale="Only option",
                    source="claude",
                ),
                100,
                50,
            )

            resp = test_client.post(
                "/decide",
                json=_decide_payload(
                    player_a=None, player_b=None, query="Should I start LeBron?"
                ),
            )
            assert resp.status_code == 200
            # find_player_by_name called once (only player_a)
            mock_espn.find_player_by_name.assert_called_once()

    def test_only_player_b(self, test_client):
        """Line 967: single player_b, no player_a."""
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.classify_query") as mock_classify,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch(
                "api.main._claude_decision", new_callable=AsyncMock
            ) as mock_claude_dec,
            patch("api.main._store_decision", new_callable=AsyncMock),
            patch("api.main.redis_service") as mock_redis,
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
            patch(
                "api.main.extract_players_from_query",
                return_value=(None, "Stephen Curry"),
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)
            mock_redis.is_connected = False

            from api.main import Confidence, DecisionResponse, QueryComplexity

            mock_classify.return_value = QueryComplexity.COMPLEX
            mock_claude_dec.return_value = (
                DecisionResponse(
                    decision="Start Curry",
                    confidence=Confidence.MEDIUM,
                    rationale="Only option",
                    source="claude",
                ),
                100,
                50,
            )

            resp = test_client.post(
                "/decide",
                json=_decide_payload(
                    player_a=None, player_b=None, query="Should I start Curry?"
                ),
            )
            assert resp.status_code == 200
            mock_espn.find_player_by_name.assert_called_once()


class TestDecideAutoFillSleeperContext:
    """Cover lines 990, 999-1029: auto-fill Sleeper league context."""

    def test_sleeper_league_auto_fill(self, test_client):
        _auth_override()
        try:
            user = _mock_user(
                sleeper_league_id="sl_12345",
                sleeper_user_id="su_789",
            )
            mock_league = MagicMock()
            mock_league.name = "My League"
            mock_league.season = "2025"
            mock_league.total_rosters = 12
            mock_league.scoring_settings = {"pass_td": 4.0, "rush_yd": 0.1}

            mock_roster = MagicMock()
            mock_roster.players = ["p1", "p2"]
            mock_roster.starters = ["p1"]

            mock_player = MagicMock()
            mock_player.full_name = "Test Player"
            mock_player.position = "QB"
            mock_player.team = "KC"
            mock_player.injury_status = None
            mock_player.player_id = "p1"

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
                patch("api.main.sleeper_service") as mock_sleeper,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                mock_sleeper.get_league = AsyncMock(return_value=mock_league)
                mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
                mock_sleeper.get_players_by_ids = AsyncMock(return_value=[mock_player])

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start LeBron",
                        confidence=Confidence.HIGH,
                        rationale="Better with league context",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post(
                    "/decide",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                # Sleeper league was fetched
                mock_sleeper.get_league.assert_called_once()
        finally:
            _clear_overrides()


class TestDecideESPNRosterContext:
    """Cover lines 1033-1047: auto-inject ESPN roster context."""

    def test_espn_roster_context_injected(self, test_client):
        _auth_override()
        try:
            user = _mock_user(
                espn_league_id="espn_123",
                espn_sport="nfl",
                espn_roster_snapshot=[
                    {
                        "name": "Mahomes",
                        "position": "QB",
                        "team": "KC",
                        "lineup_slot": "STARTER",
                    },
                ],
            )

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start Mahomes",
                        confidence=Confidence.HIGH,
                        rationale="ESPN context used",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post(
                    "/decide",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                # Claude was called with ESPN roster context
                call_args = mock_claude_dec.call_args
                assert "ESPN League" in (
                    call_args[1].get("player_context") or call_args[0][3] or ""
                )
        finally:
            _clear_overrides()


class TestDecideYahooRosterContext:
    """Cover lines 1057-1071: auto-inject Yahoo roster context."""

    def test_yahoo_roster_context_injected(self, test_client):
        _auth_override()
        try:
            user = _mock_user(
                espn_league_id=None,
                yahoo_league_key="yahoo_456",
                yahoo_sport="nfl",
                yahoo_roster_snapshot=[
                    {
                        "name": "Allen",
                        "position": "QB",
                        "team": "BUF",
                        "status": "Active",
                    },
                ],
            )

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.classify_query") as mock_classify,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch(
                    "api.main._claude_decision", new_callable=AsyncMock
                ) as mock_claude_dec,
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                from api.main import Confidence, DecisionResponse, QueryComplexity

                mock_classify.return_value = QueryComplexity.COMPLEX
                mock_claude_dec.return_value = (
                    DecisionResponse(
                        decision="Start Allen",
                        confidence=Confidence.HIGH,
                        rationale="Yahoo context used",
                        source="claude",
                    ),
                    100,
                    50,
                )

                resp = test_client.post(
                    "/decide",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                call_args = mock_claude_dec.call_args
                assert "Yahoo League" in (
                    call_args[1].get("player_context") or call_args[0][3] or ""
                )
        finally:
            _clear_overrides()


class TestDecideRedisCacheHit:
    """Cover lines 1083-1110: Redis cache hit for Claude decisions."""

    def test_redis_cache_hit(self, test_client):
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.classify_query") as mock_classify,
            patch("api.main.redis_service") as mock_redis,
            patch("api.main._store_decision", new_callable=AsyncMock),
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)

            from api.main import QueryComplexity

            mock_classify.return_value = QueryComplexity.COMPLEX

            mock_redis.is_connected = True
            mock_redis.get_decision = AsyncMock(
                return_value={
                    "decision": "Start LeBron",
                    "confidence": "high",
                    "rationale": "Cached rationale",
                    "details": None,
                    "source": "claude",
                }
            )

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 200
            data = resp.json()
            assert data["source"] == "claude_cached"
            assert data["decision"] == "Start LeBron"


class TestDecideBudgetExceeded:
    """Cover line 1123: budget exceeded before Claude call."""

    def test_budget_exceeded(self, test_client):
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
                return_value=(True, "Budget blown"),
            ),
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)
            mock_redis.is_connected = False

            from api.main import QueryComplexity

            mock_classify.return_value = QueryComplexity.COMPLEX

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 402
            assert "Budget blown" in resp.json()["detail"]


class TestDecideCacheClaudeResult:
    """Cover line 1150: cache Claude decision to Redis."""

    def test_claude_result_cached_to_redis(self, test_client):
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
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)

            from api.main import Confidence, DecisionResponse, QueryComplexity

            mock_classify.return_value = QueryComplexity.COMPLEX

            # Redis connected but no cache hit
            mock_redis.is_connected = True
            mock_redis.get_decision = AsyncMock(return_value=None)
            mock_redis.set_decision = AsyncMock()

            mock_claude_dec.return_value = (
                DecisionResponse(
                    decision="Start LeBron",
                    confidence=Confidence.HIGH,
                    rationale="Great matchup",
                    source="claude",
                ),
                100,
                50,
            )

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 200
            # set_decision should have been called to cache
            mock_redis.set_decision.assert_called_once()


class TestDecideLocalFallbackToClaude:
    """Cover lines 1177, 1183: _local_decision fallback when stats missing."""

    def test_local_decision_falls_back_no_player_data(self, test_client):
        """Line 1177: player_a_data missing — SIMPLE but one player None → else branch → Claude."""
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
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
            patch("api.main.format_player_context", return_value="context"),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            # player_a found, player_b NOT found → line 1116 check fails (player_b_data falsy)
            mock_espn.find_player_by_name = AsyncMock(
                side_effect=[("info_a", "stats_a"), None]
            )
            mock_redis.is_connected = False

            from api.main import Confidence, DecisionResponse, QueryComplexity

            mock_classify.return_value = QueryComplexity.SIMPLE

            mock_claude_dec.return_value = (
                DecisionResponse(
                    decision="Start LeBron",
                    confidence=Confidence.MEDIUM,
                    rationale="Claude fallback",
                    source="claude",
                ),
                100,
                50,
            )

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 200
            mock_claude_dec.assert_called_once()

    def test_local_decision_falls_back_no_stats(self, test_client):
        """Line 1183: both players found but stats None → _local_decision → _claude_decision.

        _local_decision internally calls _claude_decision when stats are missing.
        We mock _claude_decision to return just a DecisionResponse (not a tuple)
        since _local_decision returns the result of _claude_decision directly.
        """
        from api.main import Confidence, DecisionResponse, QueryComplexity

        response_obj = DecisionResponse(
            decision="Start LeBron",
            confidence=Confidence.MEDIUM,
            rationale="Claude fallback no stats",
            source="claude",
        )

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.classify_query") as mock_classify,
            patch("api.main.redis_service") as mock_redis,
            patch("api.main._store_decision", new_callable=AsyncMock),
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
            patch("api.main.format_player_context", return_value="context"),
            # Mock _local_decision to simulate the fallback path returning a plain response
            patch(
                "api.main._local_decision",
                new_callable=AsyncMock,
                return_value=response_obj,
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            # Both found with data — SIMPLE → enters _local_decision
            mock_espn.find_player_by_name = AsyncMock(
                side_effect=[("info_a", None), ("info_b", None)]
            )
            mock_redis.is_connected = True
            mock_redis.get_decision = AsyncMock(return_value=None)
            mock_redis.set_decision = AsyncMock()

            mock_classify.return_value = QueryComplexity.SIMPLE

            resp = test_client.post("/decide", json=_decide_payload())
            assert resp.status_code == 200
            assert resp.json()["source"] == "claude"


# =========================================================================
# Group 3: /draft rate limit + quota + off-topic
# =========================================================================


class TestDraftRateLimit:
    """Cover line 1393."""

    def test_draft_rate_limit_exceeded(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

            resp = test_client.post("/draft", json=_draft_payload())
            assert resp.status_code == 429


class TestDraftQuotaExceeded:
    """Cover lines 1402-1404."""

    def test_draft_quota_exceeded(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(False, 5, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                resp = test_client.post("/draft", json=_draft_payload())
                assert resp.status_code == 402
                assert resp.json()["detail"]["code"] == "QUOTA_EXCEEDED"
        finally:
            _clear_overrides()


class TestDraftOffTopic:
    """Cover line 1410."""

    def test_draft_off_topic_query(self, test_client):
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(False, "Not sports")),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

            resp = test_client.post(
                "/draft",
                json=_draft_payload(query="What is the meaning of life?"),
            )
            assert resp.status_code == 400
            assert "suggestions" in resp.json()["detail"]


# =========================================================================
# Group 4: /waiver rate limit + quota + edge cases
# =========================================================================


class TestWaiverRateLimit:
    """Cover line 1463."""

    def test_waiver_rate_limit_exceeded(self, test_client):
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 30))

            resp = test_client.post("/waiver/recommend", json=_waiver_payload())
            assert resp.status_code == 429


class TestWaiverQuotaExceeded:
    """Cover lines 1472-1474."""

    def test_waiver_quota_exceeded(self, test_client):
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(False, 5, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                resp = test_client.post("/waiver/recommend", json=_waiver_payload())
                assert resp.status_code == 402
                assert resp.json()["detail"]["code"] == "QUOTA_EXCEEDED"
        finally:
            _clear_overrides()


class TestWaiverConfidenceBranches:
    """Cover lines 1544-1545, 1554-1557: waiver confidence branches."""

    def _run_waiver_with_analysis(self, test_client, analysis_kwargs):
        """Helper: run /waiver/recommend with controlled analysis output."""
        mock_analysis = MagicMock()
        mock_analysis.position_needs = analysis_kwargs.get("position_needs", [])
        mock_analysis.injured = analysis_kwargs.get("injured", [])

        mock_roster = MagicMock()
        mock_roster.players = ["p1"]
        mock_roster.starters = ["p1"]

        mock_player = MagicMock()
        mock_player.full_name = "Test"
        mock_player.position = "QB"
        mock_player.team = "KC"
        mock_player.injury_status = None
        mock_player.player_id = "p1"

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main.sleeper_service") as mock_sleeper,
            patch("api.main.analyze_roster", return_value=mock_analysis),
            patch("api.main.build_waiver_prompt", return_value="prompt"),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.claude_service") as mock_claude,
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[mock_player])

            recommendations = analysis_kwargs.get("recommendations", [])
            mock_claude.make_decision = AsyncMock(
                return_value={
                    "rationale": '{"recommendations": '
                    + str(recommendations).replace("'", '"')
                    + ', "drop_candidates": [], "summary": "test summary"}',
                }
            )

            resp = test_client.post("/waiver/recommend", json=_waiver_payload())
            return resp

    def test_waiver_injured_players_high_confidence(self, test_client):
        """Lines 1544-1545: analysis.injured is truthy → HIGH confidence."""
        resp = self._run_waiver_with_analysis(
            test_client,
            {
                "position_needs": [],
                "injured": [{"name": "Hurt Player"}],
                "recommendations": [{"player": "Pickup"}],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["confidence"] == "high"

    def test_waiver_no_recommendations_low_confidence(self, test_client):
        """Lines 1556-1557: no recommendations → LOW confidence."""
        resp = self._run_waiver_with_analysis(
            test_client,
            {
                "position_needs": [],
                "injured": [],
                "recommendations": [],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["confidence"] == "low"


class TestWaiverExceptions:
    """Cover lines 1570-1576: JSONDecodeError + generic exception."""

    def test_waiver_json_decode_error(self, test_client):
        """Line 1570: JSONDecodeError from Claude response."""
        mock_analysis = MagicMock()
        mock_analysis.position_needs = []
        mock_analysis.injured = []

        mock_roster = MagicMock()
        mock_roster.players = ["p1"]
        mock_roster.starters = ["p1"]

        mock_player = MagicMock()

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main.sleeper_service") as mock_sleeper,
            patch("api.main.analyze_roster", return_value=mock_analysis),
            patch("api.main.build_waiver_prompt", return_value="prompt"),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.claude_service") as mock_claude,
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[mock_player])

            # Both { and } present but content is invalid JSON → JSONDecodeError
            mock_claude.make_decision = AsyncMock(
                return_value={"rationale": "{ not: valid, json: [broken }"}
            )

            resp = test_client.post("/waiver/recommend", json=_waiver_payload())
            assert resp.status_code == 500
            assert "Failed to parse" in resp.json()["detail"]

    def test_waiver_generic_exception(self, test_client):
        """Lines 1575-1576: generic exception from Claude."""
        mock_analysis = MagicMock()
        mock_analysis.position_needs = []
        mock_analysis.injured = []

        mock_roster = MagicMock()
        mock_roster.players = ["p1"]
        mock_roster.starters = ["p1"]

        mock_player = MagicMock()

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main.sleeper_service") as mock_sleeper,
            patch("api.main.analyze_roster", return_value=mock_analysis),
            patch("api.main.build_waiver_prompt", return_value="prompt"),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.claude_service") as mock_claude,
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
            mock_sleeper.get_players_by_ids = AsyncMock(return_value=[mock_player])

            mock_claude.make_decision = AsyncMock(
                side_effect=RuntimeError("Claude exploded")
            )

            resp = test_client.post("/waiver/recommend", json=_waiver_payload())
            assert resp.status_code == 500
            assert "Error generating waiver" in resp.json()["detail"]


# =========================================================================
# Group 5: /decide/stream
# =========================================================================


class TestDecideStream:
    """Cover lines 1725-1952: streaming endpoint."""

    def test_stream_basic_success(self, test_client):
        """Happy path: stream returns SSE events with content and done."""

        async def mock_stream(**kwargs):
            yield "Start LeBron"
            yield " because"
            yield {
                "_metadata": True,
                "full_response": "Start LeBron because great matchup",
                "input_tokens": 100,
                "output_tokens": 50,
            }

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.claude_service") as mock_claude,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main._store_decision", new_callable=AsyncMock),
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
            patch("api.main.redis_service") as mock_redis,
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)
            mock_redis.is_connected = False

            mock_claude.is_available = True
            mock_claude.make_decision_stream = mock_stream
            mock_claude._parse_response = MagicMock(
                return_value={
                    "decision": "Start LeBron",
                    "confidence": "high",
                    "rationale": "Great matchup",
                }
            )

            resp = test_client.post("/decide/stream", json=_decide_payload())
            assert resp.status_code == 200
            assert resp.headers.get("content-type", "").startswith("text/event-stream")

            body = resp.text
            assert "Start LeBron" in body
            assert "[DONE]" in body

    def test_stream_rate_limit(self, test_client):
        """Line 1727-1732: rate limit exceeded on stream."""
        with patch("api.main.rate_limiter") as mock_rl:
            mock_rl.check_rate_limit = AsyncMock(return_value=(False, 45))

            resp = test_client.post("/decide/stream", json=_decide_payload())
            assert resp.status_code == 429

    def test_stream_quota_exceeded(self, test_client):
        """Lines 1737-1739: quota exceeded on stream."""
        _auth_override()
        try:
            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(False, 5, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

                resp = test_client.post("/decide/stream", json=_decide_payload())
                assert resp.status_code == 402
        finally:
            _clear_overrides()

    def test_stream_claude_unavailable(self, test_client):
        """Line 1750-1754: Claude not available."""
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.claude_service") as mock_claude,
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_claude.is_available = False

            resp = test_client.post("/decide/stream", json=_decide_payload())
            assert resp.status_code == 503

    def test_stream_budget_exceeded(self, test_client):
        """Lines 1757-1762: budget exceeded on stream."""
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.claude_service") as mock_claude,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(True, "Over budget"),
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_claude.is_available = True

            resp = test_client.post("/decide/stream", json=_decide_payload())
            assert resp.status_code == 402

    def test_stream_off_topic(self, test_client):
        """Lines 1742-1748: off-topic query on stream."""
        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(False, "Not sports")),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))

            resp = test_client.post(
                "/decide/stream",
                json=_decide_payload(query="What is the meaning of life?"),
            )
            assert resp.status_code == 400

    def test_stream_with_sleeper_context(self, test_client):
        """Lines 1802-1841: stream with Sleeper auto-fill."""
        _auth_override()
        try:
            user = _mock_user(sleeper_league_id="sl_123", sleeper_user_id="su_456")
            mock_league = MagicMock()
            mock_league.name = "My League"
            mock_league.season = "2025"
            mock_league.total_rosters = 10
            mock_league.scoring_settings = {"pass_td": 4.0}

            mock_roster = MagicMock()
            mock_roster.players = ["p1"]
            mock_roster.starters = ["p1"]

            mock_sp = MagicMock()
            mock_sp.full_name = "Mahomes"
            mock_sp.position = "QB"
            mock_sp.team = "KC"
            mock_sp.injury_status = None
            mock_sp.player_id = "p1"

            async def mock_stream(**kwargs):
                yield "Pick Mahomes"
                yield {
                    "_metadata": True,
                    "full_response": "Pick Mahomes good matchup",
                    "input_tokens": 50,
                    "output_tokens": 25,
                }

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.claude_service") as mock_claude,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
                patch("api.main.sleeper_service") as mock_sleeper,
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                mock_claude.is_available = True
                mock_claude.make_decision_stream = mock_stream
                mock_claude._parse_response = MagicMock(
                    return_value={
                        "decision": "Pick Mahomes",
                        "confidence": "high",
                        "rationale": "Good matchup",
                    }
                )

                mock_sleeper.get_league = AsyncMock(return_value=mock_league)
                mock_sleeper.get_user_roster = AsyncMock(return_value=mock_roster)
                mock_sleeper.get_players_by_ids = AsyncMock(return_value=[mock_sp])

                resp = test_client.post(
                    "/decide/stream",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                assert "Pick Mahomes" in resp.text
        finally:
            _clear_overrides()

    def test_stream_with_espn_context(self, test_client):
        """Lines 1844-1859: stream with ESPN roster auto-inject."""
        _auth_override()
        try:
            user = _mock_user(
                espn_league_id="espn_99",
                espn_sport="nfl",
                espn_roster_snapshot=[
                    {"name": "Allen", "position": "QB", "team": "BUF"},
                ],
            )

            async def mock_stream(**kwargs):
                yield "Start Allen"
                yield {
                    "_metadata": True,
                    "full_response": "Start Allen because of volume",
                    "input_tokens": 50,
                    "output_tokens": 25,
                }

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.claude_service") as mock_claude,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                mock_claude.is_available = True
                mock_claude.make_decision_stream = mock_stream
                mock_claude._parse_response = MagicMock(
                    return_value={
                        "decision": "Start Allen",
                        "confidence": "medium",
                        "rationale": "Volume",
                    }
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                assert "Start Allen" in resp.text
        finally:
            _clear_overrides()

    def test_stream_with_yahoo_context(self, test_client):
        """Lines 1862-1883: stream with Yahoo roster auto-inject."""
        _auth_override()
        try:
            user = _mock_user(
                espn_league_id=None,
                yahoo_league_key="yahoo_88",
                yahoo_sport="nfl",
                yahoo_roster_snapshot=[
                    {
                        "name": "Lamar",
                        "position": "QB",
                        "team": "BAL",
                        "status": "Active",
                    },
                ],
            )

            async def mock_stream(**kwargs):
                yield "Start Lamar"
                yield {
                    "_metadata": True,
                    "full_response": "Start Lamar dual threat",
                    "input_tokens": 50,
                    "output_tokens": 25,
                }

            with (
                patch("api.main.rate_limiter") as mock_rl,
                patch("api.main._is_sports_query", return_value=(True, None)),
                patch("api.main.assign_variant", return_value="control"),
                patch("api.main.espn_service") as mock_espn,
                patch("api.main.claude_service") as mock_claude,
                patch(
                    "api.main._check_budget_exceeded",
                    new_callable=AsyncMock,
                    return_value=(False, None),
                ),
                patch("api.main._store_decision", new_callable=AsyncMock),
                patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
                patch("api.main.redis_service") as mock_redis,
                patch(
                    "api.main._get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch(
                    "api.main._check_and_increment_query_count",
                    new_callable=AsyncMock,
                    return_value=(True, 1, 5),
                ),
            ):
                mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
                mock_espn.find_player_by_name = AsyncMock(return_value=None)
                mock_redis.is_connected = False

                mock_claude.is_available = True
                mock_claude.make_decision_stream = mock_stream
                mock_claude._parse_response = MagicMock(
                    return_value={
                        "decision": "Start Lamar",
                        "confidence": "high",
                        "rationale": "Dual threat",
                    }
                )

                resp = test_client.post(
                    "/decide/stream",
                    json=_decide_payload(league_id=None),
                )
                assert resp.status_code == 200
                assert "Start Lamar" in resp.text
        finally:
            _clear_overrides()

    def test_stream_error_in_generator(self, test_client):
        """Lines 1949-1950: exception during streaming yields [ERROR]."""

        async def mock_stream(**kwargs):
            raise RuntimeError("Stream exploded")
            yield  # noqa: RET503 — unreachable but needed for async generator

        with (
            patch("api.main.rate_limiter") as mock_rl,
            patch("api.main._is_sports_query", return_value=(True, None)),
            patch("api.main.assign_variant", return_value="control"),
            patch("api.main.espn_service") as mock_espn,
            patch("api.main.claude_service") as mock_claude,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.redis_service") as mock_redis,
            patch(
                "api.main._get_user_by_id", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_rl.check_rate_limit = AsyncMock(return_value=(True, 0))
            mock_espn.find_player_by_name = AsyncMock(return_value=None)
            mock_redis.is_connected = False

            mock_claude.is_available = True
            mock_claude.make_decision_stream = mock_stream

            resp = test_client.post("/decide/stream", json=_decide_payload())
            assert resp.status_code == 200  # SSE returns 200 with error in body
            assert "[ERROR]" in resp.text
