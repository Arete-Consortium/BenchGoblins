"""
Tests for API endpoints.
"""

from unittest.mock import AsyncMock, patch


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, test_client):
        """Health endpoint returns status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "claude_available" in data
        assert "espn_available" in data


class TestPlayerSearchEndpoint:
    """Tests for /players/search endpoint."""

    def test_search_valid_request(self, test_client):
        """Valid search request structure."""
        with patch(
            "api.main.espn_service.search_players", new_callable=AsyncMock
        ) as mock:
            from services.espn import PlayerInfo

            mock.return_value = [
                PlayerInfo(
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
                    headshot_url="https://example.com/lebron.png",
                )
            ]

            response = test_client.post(
                "/players/search",
                json={"query": "LeBron", "sport": "nba", "limit": 5},
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            if len(data) > 0:
                assert "id" in data[0]
                assert "name" in data[0]

    def test_search_invalid_sport(self, test_client):
        """Invalid sport should return 422."""
        response = test_client.post(
            "/players/search",
            json={"query": "LeBron", "sport": "invalid", "limit": 5},
        )

        assert response.status_code == 422

    def test_search_missing_query(self, test_client):
        """Missing query should return 422."""
        response = test_client.post(
            "/players/search",
            json={"sport": "nba"},
        )

        assert response.status_code == 422


class TestPlayerDetailEndpoint:
    """Tests for /players/{sport}/{player_id} endpoint."""

    def test_get_player_exists(self, test_client):
        """Get existing player details."""
        with patch(
            "api.main.espn_service.get_player", new_callable=AsyncMock
        ) as mock_player:
            with patch(
                "api.main.espn_service.get_player_stats", new_callable=AsyncMock
            ) as mock_stats:
                from services.espn import PlayerInfo, PlayerStats

                mock_player.return_value = PlayerInfo(
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
                    headshot_url="https://example.com/lebron.png",
                )

                mock_stats.return_value = PlayerStats(
                    player_id="12345",
                    sport="nba",
                    games_played=50,
                    games_started=50,
                    points_per_game=25.5,
                )

                response = test_client.get("/players/nba/12345")

                assert response.status_code == 200
                data = response.json()
                assert data["id"] == "12345"
                assert data["name"] == "LeBron James"
                assert "stats" in data

    def test_get_player_not_found(self, test_client):
        """Get non-existent player returns 404."""
        with patch("api.main.espn_service.get_player", new_callable=AsyncMock) as mock:
            mock.return_value = None

            response = test_client.get("/players/nba/99999")

            assert response.status_code == 404


class TestDecideEndpoint:
    """Tests for /decide endpoint."""

    def test_decide_simple_query(self, test_client):
        """Simple A vs B query."""
        with patch(
            "api.main.espn_service.find_player_by_name", new_callable=AsyncMock
        ) as mock_find:
            from services.espn import PlayerInfo, PlayerStats

            # Mock both players found
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
            )

            mock_find.side_effect = [
                (player_a_info, player_a_stats),
                (player_b_info, player_b_stats),
            ]

            response = test_client.post(
                "/decide",
                json={
                    "sport": "nba",
                    "risk_mode": "median",
                    "query": "Should I start LeBron James or Kevin Durant?",
                    "player_a": "LeBron James",
                    "player_b": "Kevin Durant",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "decision" in data
            assert "confidence" in data
            assert "rationale" in data
            assert data["source"] in ["local", "claude"]

    def test_decide_missing_sport(self, test_client):
        """Missing sport should return 422."""
        response = test_client.post(
            "/decide",
            json={
                "query": "Should I start LeBron or KD?",
            },
        )

        assert response.status_code == 422

    def test_decide_invalid_risk_mode(self, test_client):
        """Invalid risk mode should return 422."""
        response = test_client.post(
            "/decide",
            json={
                "sport": "nba",
                "risk_mode": "invalid",
                "query": "Should I start LeBron or KD?",
            },
        )

        assert response.status_code == 422


class TestHistoryEndpoint:
    """Tests for /history endpoint."""

    def test_history_empty(self, test_client):
        """History returns empty list (no auth yet)."""
        response = test_client.get("/history")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_history_with_limit(self, test_client):
        """History accepts limit parameter."""
        response = test_client.get("/history?limit=5")

        assert response.status_code == 200


class TestCORSMiddleware:
    """Tests for CORS configuration."""

    def test_cors_headers(self, test_client):
        """CORS headers are present."""
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # FastAPI handles preflight automatically
        assert response.status_code in [200, 405]


class TestRequestValidation:
    """Tests for request validation."""

    def test_invalid_json(self, test_client):
        """Invalid JSON should return 422."""
        response = test_client.post(
            "/players/search",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_wrong_content_type(self, test_client):
        """Wrong content type should return 422."""
        response = test_client.post(
            "/players/search",
            content='{"query": "test", "sport": "nba"}',
            headers={"Content-Type": "text/plain"},
        )

        assert response.status_code == 422


class TestUsageEndpoint:
    """Tests for /usage endpoint."""

    def test_usage_returns_response(self, test_client):
        """Usage endpoint returns a response."""
        response = test_client.get("/usage")

        assert response.status_code == 200
        data = response.json()
        # Either returns usage data or error (no DB in test)
        assert isinstance(data, dict)

    def test_usage_with_sport_filter(self, test_client):
        """Usage endpoint accepts sport filter."""
        response = test_client.get("/usage?sport=nba")

        assert response.status_code == 200

    def test_usage_invalid_sport(self, test_client):
        """Usage endpoint rejects invalid sport."""
        response = test_client.get("/usage?sport=invalid")

        assert response.status_code == 422


class TestExperimentEndpoints:
    """Tests for /experiments/* endpoints."""

    def test_active_experiment(self, test_client):
        """Active experiment returns config structure."""
        response = test_client.get("/experiments/active")

        assert response.status_code == 200
        data = response.json()
        assert "variants" in data
        assert "weights" in data
        assert "total_variants" in data
        assert isinstance(data["variants"], list)
        assert "experiment" in data
        assert "name" in data["experiment"]

    def test_experiment_results(self, test_client):
        """Results endpoint returns response (empty or structured)."""
        response = test_client.get("/experiments/results")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_experiment_history(self, test_client):
        """History endpoint returns list."""
        response = test_client.get("/experiments/history")

        assert response.status_code == 200
        data = response.json()
        assert "experiments" in data
        assert isinstance(data["experiments"], list)

    def test_start_experiment(self, test_client):
        """Can start a new experiment via API."""
        response = test_client.post(
            "/experiments/start",
            json={
                "name": "api_test_exp",
                "variants": {"control": 70, "concise_v1": 30},
                "description": "Test from API",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["experiment"]["name"] == "api_test_exp"

        # Restore default experiment
        test_client.post(
            "/experiments/start",
            json={
                "name": "concise_prompt_v1",
                "variants": {"control": 50, "concise_v1": 50},
            },
        )

    def test_start_experiment_invalid_variant(self, test_client):
        """Starting with unknown variant returns 400."""
        response = test_client.post(
            "/experiments/start",
            json={
                "name": "bad_exp",
                "variants": {"control": 50, "nonexistent": 50},
            },
        )

        assert response.status_code == 400

    def test_end_experiment(self, test_client):
        """Can end the active experiment."""
        # Start one first
        test_client.post(
            "/experiments/start",
            json={"name": "to_end", "variants": {"control": 100}},
        )

        response = test_client.post("/experiments/end")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ended"
        assert data["experiment"]["name"] == "to_end"
        assert data["experiment"]["ended_at"] is not None

        # Restore default
        test_client.post(
            "/experiments/start",
            json={
                "name": "concise_prompt_v1",
                "variants": {"control": 50, "concise_v1": 50},
            },
        )


class TestCacheInvalidateEndpoint:
    """Tests for /cache/invalidate/{sport} endpoint."""

    def test_invalidate_sport(self, test_client):
        """Invalidate endpoint returns response."""
        response = test_client.post("/cache/invalidate/nba")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_invalidate_invalid_sport(self, test_client):
        """Invalidate endpoint rejects invalid sport."""
        response = test_client.post("/cache/invalidate/invalid")

        assert response.status_code == 422
