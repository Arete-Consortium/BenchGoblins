"""
Tests for the waiver wire recommendation feature.

Covers: analyze_roster() position counting, position need detection,
injured player identification, build_waiver_prompt(), WaiverResult
properties, and /waiver/recommend endpoint integration.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.sleeper import SleeperPlayer
from services.waiver_wire import (
    DEPTH_MINIMUMS,
    RosterAnalysis,
    WaiverCandidate,
    WaiverResult,
    analyze_roster,
    build_waiver_prompt,
)


# =============================================================================
# FIXTURES
# =============================================================================


def _make_player(
    player_id: str,
    name: str,
    position: str,
    team: str = "LAL",
    injury_status: str | None = None,
) -> SleeperPlayer:
    """Helper to create a SleeperPlayer."""
    return SleeperPlayer(
        player_id=player_id,
        full_name=name,
        first_name=name.split()[0],
        last_name=name.split()[-1],
        team=team,
        position=position,
        sport="nfl",
        status="Active",
        injury_status=injury_status,
        age=27,
        years_exp=5,
    )


@pytest.fixture
def nfl_roster():
    """Standard NFL roster with starters and bench."""
    return [
        _make_player("1", "Josh Allen", "QB", "BUF"),
        _make_player("2", "Saquon Barkley", "RB", "PHI"),
        _make_player("3", "Derrick Henry", "RB", "BAL"),
        _make_player("4", "Tyreek Hill", "WR", "MIA"),
        _make_player("5", "CeeDee Lamb", "WR", "DAL"),
        _make_player("6", "Travis Kelce", "TE", "KC"),
        _make_player("7", "Tyler Bass", "K", "BUF"),
        _make_player("8", "Bills D", "DEF", "BUF"),
        # Bench
        _make_player("9", "Jaylen Waddle", "WR", "MIA"),
        _make_player("10", "Tony Pollard", "RB", "TEN"),
    ]


@pytest.fixture
def nfl_starters():
    """Starter IDs for the NFL roster."""
    return {"1", "2", "3", "4", "5", "6", "7", "8"}


# =============================================================================
# TEST analyze_roster()
# =============================================================================


class TestAnalyzeRoster:
    """Tests for roster analysis."""

    def test_position_counts(self, nfl_roster, nfl_starters):
        """Counts positions correctly."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")

        assert analysis.position_counts["QB"] == 1
        assert analysis.position_counts["RB"] == 3
        assert analysis.position_counts["WR"] == 3
        assert analysis.position_counts["TE"] == 1
        assert analysis.position_counts["K"] == 1
        assert analysis.position_counts["DEF"] == 1

    def test_starters_and_bench_split(self, nfl_roster, nfl_starters):
        """Correctly separates starters from bench."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")

        assert len(analysis.starters) == 8
        assert len(analysis.bench) == 2
        bench_names = [p["name"] for p in analysis.bench]
        assert "Jaylen Waddle" in bench_names
        assert "Tony Pollard" in bench_names

    def test_no_injured_players(self, nfl_roster, nfl_starters):
        """No injuries when none flagged."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        assert analysis.injured == []

    def test_injured_player_detected(self, nfl_starters):
        """Injured player shows up in injured list."""
        players = [
            _make_player("1", "Josh Allen", "QB", "BUF"),
            _make_player(
                "2", "Saquon Barkley", "RB", "PHI", injury_status="Questionable"
            ),
        ]
        analysis = analyze_roster(players, nfl_starters, "nfl")

        assert len(analysis.injured) == 1
        assert analysis.injured[0]["name"] == "Saquon Barkley"
        assert analysis.injured[0]["injury_status"] == "Questionable"

    def test_position_needs_thin_roster(self):
        """Thin roster triggers position needs."""
        # Only a QB — everything else is a need
        players = [_make_player("1", "Josh Allen", "QB", "BUF")]
        analysis = analyze_roster(players, {"1"}, "nfl")

        # Should need RB, WR, TE, K, DEF at minimum
        assert "RB" in analysis.position_needs
        assert "WR" in analysis.position_needs
        assert "TE" in analysis.position_needs

    def test_full_roster_no_needs(self, nfl_roster, nfl_starters):
        """Full roster has no position needs (meets depth minimums)."""
        # Add an extra TE to meet depth
        nfl_roster.append(_make_player("11", "Pat Freiermuth", "TE", "PIT"))
        # Add extra RB for depth (need 4)
        nfl_roster.append(_make_player("12", "Zack Moss", "RB", "CIN"))
        # Add extra WR for depth (need 4)
        nfl_roster.append(_make_player("13", "DK Metcalf", "WR", "SEA"))
        # Add backup QB (need 2)
        nfl_roster.append(_make_player("14", "Brock Purdy", "QB", "SF"))

        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        assert analysis.position_needs == []

    def test_injured_starter_adds_position_need(self, nfl_starters):
        """Injured starter's position becomes a need even if depth is met."""
        players = [
            _make_player("1", "Josh Allen", "QB", "BUF", injury_status="Out"),
            _make_player("2", "Brock Purdy", "QB", "SF"),
        ]
        analysis = analyze_roster(players, {"1"}, "nfl")

        # QB depth is 2 (meets minimum), but starter is injured
        assert "QB" in analysis.position_needs

    def test_empty_roster(self):
        """Empty roster returns empty analysis with needs."""
        analysis = analyze_roster([], set(), "nfl")

        assert analysis.position_counts == {}
        assert analysis.starters == []
        assert analysis.bench == []
        assert analysis.injured == []
        # All positions needed
        nfl_positions = set(DEPTH_MINIMUMS["nfl"].keys())
        assert set(analysis.position_needs) == nfl_positions

    def test_nba_sport(self):
        """Works for NBA sport."""
        players = [
            _make_player("1", "LeBron James", "SF", "LAL"),
            _make_player("2", "Steph Curry", "PG", "GSW"),
        ]
        analysis = analyze_roster(players, {"1", "2"}, "nba")

        assert analysis.position_counts["SF"] == 1
        assert analysis.position_counts["PG"] == 1
        assert "SG" in analysis.position_needs  # Missing SG

    def test_unknown_sport_no_crash(self):
        """Unknown sport falls back gracefully (no crash)."""
        players = [_make_player("1", "Player One", "FWD", "TEA")]
        analysis = analyze_roster(players, {"1"}, "cricket")

        assert analysis.position_counts == {"FWD": 1}
        assert analysis.position_needs == []  # No minimums defined


# =============================================================================
# TEST build_waiver_prompt()
# =============================================================================


class TestBuildWaiverPrompt:
    """Tests for prompt construction."""

    def test_contains_roster_info(self, nfl_roster, nfl_starters):
        """Prompt contains roster player names."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "median", "Who should I pick up?")

        assert "Josh Allen" in prompt
        assert "Saquon Barkley" in prompt
        assert "[STARTER]" in prompt
        assert "[BENCH]" in prompt

    def test_contains_position_needs(self):
        """Prompt mentions position needs."""
        players = [_make_player("1", "Josh Allen", "QB", "BUF")]
        analysis = analyze_roster(players, {"1"}, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "median", "Who should I pick up?")

        assert "RB" in prompt
        assert "POSITION NEEDS" in prompt

    def test_contains_risk_mode(self, nfl_roster, nfl_starters):
        """Prompt includes risk mode."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "ceiling", "test")

        assert "ceiling" in prompt

    def test_contains_query(self, nfl_roster, nfl_starters):
        """Prompt includes user's question."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(
            analysis, "nfl", "median", "Need a backup RB badly"
        )

        assert "Need a backup RB badly" in prompt

    def test_position_filter_included(self, nfl_roster, nfl_starters):
        """Position filter instruction is added when provided."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(
            analysis, "nfl", "median", "test", position_filter="RB"
        )

        assert "Focus specifically on RB" in prompt

    def test_position_filter_omitted(self, nfl_roster, nfl_starters):
        """No position filter instruction when not provided."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "median", "test")

        assert "Focus specifically" not in prompt

    def test_json_format_instructions(self, nfl_roster, nfl_starters):
        """Prompt includes JSON format instructions."""
        analysis = analyze_roster(nfl_roster, nfl_starters, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "median", "test")

        assert "JSON" in prompt
        assert '"recommendations"' in prompt
        assert '"drop_candidates"' in prompt

    def test_injured_players_mentioned(self):
        """Prompt mentions injured players when present."""
        players = [
            _make_player("1", "Josh Allen", "QB", "BUF", injury_status="Doubtful"),
        ]
        analysis = analyze_roster(players, {"1"}, "nfl")
        prompt = build_waiver_prompt(analysis, "nfl", "median", "test")

        assert "Josh Allen" in prompt
        assert "Doubtful" in prompt


# =============================================================================
# TEST WaiverResult DATACLASS
# =============================================================================


class TestWaiverResult:
    """Tests for WaiverResult computed properties."""

    def test_confidence_high_many_needs(self):
        """Multiple position needs → high confidence."""
        analysis = RosterAnalysis(position_needs=["RB", "WR"])
        candidate = WaiverCandidate(
            name="Test", position="RB", team="TEA", rationale="Good", priority=1
        )
        result = WaiverResult(roster_analysis=analysis, recommendations=[candidate])
        assert result.confidence == "high"

    def test_confidence_high_injured(self):
        """Injured players → high confidence."""
        analysis = RosterAnalysis(injured=[{"name": "Player A", "position": "RB"}])
        candidate = WaiverCandidate(
            name="Test", position="RB", team="TEA", rationale="Good", priority=1
        )
        result = WaiverResult(roster_analysis=analysis, recommendations=[candidate])
        assert result.confidence == "high"

    def test_confidence_medium_default(self):
        """Default → medium confidence."""
        analysis = RosterAnalysis(position_needs=["RB"])
        candidate = WaiverCandidate(
            name="Test", position="RB", team="TEA", rationale="Good", priority=1
        )
        result = WaiverResult(roster_analysis=analysis, recommendations=[candidate])
        assert result.confidence == "medium"

    def test_confidence_low_no_recommendations(self):
        """No recommendations → low confidence."""
        result = WaiverResult()
        assert result.confidence == "low"

    def test_rationale_with_recommendations(self):
        """Rationale mentions top pickup and position needs."""
        analysis = RosterAnalysis(position_needs=["RB"])
        candidate = WaiverCandidate(
            name="De'Von Achane",
            position="RB",
            team="MIA",
            rationale="Great",
            priority=1,
        )
        result = WaiverResult(roster_analysis=analysis, recommendations=[candidate])

        assert "De'Von Achane" in result.rationale
        assert "RB" in result.rationale

    def test_rationale_no_recommendations(self):
        """No recommendations → solid roster message."""
        result = WaiverResult()
        assert "solid" in result.rationale.lower() or "No urgent" in result.rationale

    def test_to_details_dict(self):
        """to_details_dict returns expected structure."""
        analysis = RosterAnalysis(position_needs=["WR", "TE"])
        candidates = [
            WaiverCandidate(
                name="Player A",
                position="WR",
                team="DAL",
                rationale="Deep threat",
                priority=1,
            ),
        ]
        drop = [{"name": "Bad Player", "position": "WR", "reason": "Declining"}]
        result = WaiverResult(
            roster_analysis=analysis,
            recommendations=candidates,
            drop_candidates=drop,
        )
        details = result.to_details_dict()

        assert "recommendations" in details
        assert "drop_candidates" in details
        assert "position_needs" in details
        assert len(details["recommendations"]) == 1
        assert details["recommendations"][0]["name"] == "Player A"
        assert details["position_needs"] == ["WR", "TE"]


# =============================================================================
# TEST WaiverCandidate DATACLASS
# =============================================================================


class TestWaiverCandidate:
    """Tests for WaiverCandidate."""

    def test_to_dict(self):
        """to_dict returns all fields."""
        c = WaiverCandidate(
            name="Test Player", position="RB", team="NYG", rationale="Good", priority=2
        )
        d = c.to_dict()

        assert d["name"] == "Test Player"
        assert d["position"] == "RB"
        assert d["team"] == "NYG"
        assert d["rationale"] == "Good"
        assert d["priority"] == 2


# =============================================================================
# TEST /waiver/recommend ENDPOINT
# =============================================================================


class TestWaiverEndpoint:
    """Integration tests for the /waiver/recommend endpoint."""

    def _mock_sleeper_player(
        self, pid: str, name: str, pos: str, team: str = "BUF"
    ) -> SleeperPlayer:
        return _make_player(pid, name, pos, team)

    def test_happy_path(self, test_client):
        """Waiver recommend returns structured recommendations."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1,
            owner_id="user1",
            players=["1", "2"],
            starters=["1"],
            reserve=None,
        )
        players = [
            self._mock_sleeper_player("1", "Josh Allen", "QB"),
            self._mock_sleeper_player("2", "Saquon Barkley", "RB", "PHI"),
        ]

        claude_response = {
            "decision": "Add Puka Nacua",
            "confidence": "high",
            "rationale": json.dumps(
                {
                    "recommendations": [
                        {
                            "name": "Puka Nacua",
                            "position": "WR",
                            "team": "LAR",
                            "rationale": "Rising target share",
                            "priority": 1,
                        }
                    ],
                    "drop_candidates": [],
                    "summary": "Add a WR to fill your need.",
                }
            ),
            "source": "claude",
        }

        with (
            patch(
                "api.main.sleeper_service.get_user_roster",
                new_callable=AsyncMock,
                return_value=roster,
            ),
            patch(
                "api.main.sleeper_service.get_players_by_ids",
                new_callable=AsyncMock,
                return_value=players,
            ),
            patch(
                "api.main.claude_service.make_decision",
                new_callable=AsyncMock,
                return_value=claude_response,
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "query": "Who should I pick up?",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "claude"
            assert len(data["recommendations"]) == 1
            assert data["recommendations"][0]["name"] == "Puka Nacua"
            assert "WR" in data["position_needs"]

    def test_no_roster_returns_404(self, test_client):
        """Missing roster returns 404."""
        with patch(
            "api.main.sleeper_service.get_user_roster",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            assert response.status_code == 404

    def test_empty_roster_returns_404(self, test_client):
        """Roster with no players returns 404."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1, owner_id="user1", players=[], starters=[], reserve=None
        )

        with patch(
            "api.main.sleeper_service.get_user_roster",
            new_callable=AsyncMock,
            return_value=roster,
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            assert response.status_code == 404

    def test_no_player_data_returns_404(self, test_client):
        """No player data returns 404."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1, owner_id="user1", players=["1"], starters=["1"], reserve=None
        )

        with (
            patch(
                "api.main.sleeper_service.get_user_roster",
                new_callable=AsyncMock,
                return_value=roster,
            ),
            patch(
                "api.main.sleeper_service.get_players_by_ids",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            assert response.status_code == 404

    def test_budget_exceeded_returns_402(self, test_client):
        """Budget exceeded returns 402."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1, owner_id="user1", players=["1"], starters=["1"], reserve=None
        )
        players = [self._mock_sleeper_player("1", "Josh Allen", "QB")]

        with (
            patch(
                "api.main.sleeper_service.get_user_roster",
                new_callable=AsyncMock,
                return_value=roster,
            ),
            patch(
                "api.main.sleeper_service.get_players_by_ids",
                new_callable=AsyncMock,
                return_value=players,
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(True, "Budget exceeded"),
            ),
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            assert response.status_code == 402

    def test_position_filter_passed(self, test_client):
        """Position filter is included in the prompt."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1, owner_id="user1", players=["1"], starters=["1"], reserve=None
        )
        players = [self._mock_sleeper_player("1", "Josh Allen", "QB")]

        claude_response = {
            "decision": "No pickups needed",
            "confidence": "low",
            "rationale": json.dumps(
                {
                    "recommendations": [],
                    "drop_candidates": [],
                    "summary": "No RB recommendations.",
                }
            ),
            "source": "claude",
        }

        with (
            patch(
                "api.main.sleeper_service.get_user_roster",
                new_callable=AsyncMock,
                return_value=roster,
            ),
            patch(
                "api.main.sleeper_service.get_players_by_ids",
                new_callable=AsyncMock,
                return_value=players,
            ),
            patch(
                "api.main.claude_service.make_decision",
                new_callable=AsyncMock,
                return_value=claude_response,
            ) as mock_send,
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                    "position_filter": "RB",
                },
            )

            assert response.status_code == 200
            # Verify position filter was in the prompt sent to Claude
            call_kwargs = mock_send.call_args[1]
            prompt_arg = call_kwargs.get("query", "") or call_kwargs.get(
                "player_context", ""
            )
            assert "Focus specifically on RB" in prompt_arg

    def test_malformed_claude_response(self, test_client):
        """Non-JSON Claude response handled gracefully."""
        from services.sleeper import SleeperRoster

        roster = SleeperRoster(
            roster_id=1, owner_id="user1", players=["1"], starters=["1"], reserve=None
        )
        players = [self._mock_sleeper_player("1", "Josh Allen", "QB")]

        with (
            patch(
                "api.main.sleeper_service.get_user_roster",
                new_callable=AsyncMock,
                return_value=roster,
            ),
            patch(
                "api.main.sleeper_service.get_players_by_ids",
                new_callable=AsyncMock,
                return_value=players,
            ),
            patch(
                "api.main.claude_service.make_decision",
                new_callable=AsyncMock,
                return_value={
                    "decision": "No waivers",
                    "confidence": "low",
                    "rationale": "No JSON here, just plain text about waivers.",
                    "source": "claude",
                },
            ),
            patch(
                "api.main._check_budget_exceeded",
                new_callable=AsyncMock,
                return_value=(False, None),
            ),
            patch("api.main.check_and_send_alerts", new_callable=AsyncMock),
        ):
            response = test_client.post(
                "/waiver/recommend",
                json={
                    "sport": "nfl",
                    "risk_mode": "median",
                    "league_id": "league123",
                    "sleeper_user_id": "user1",
                },
            )

            # Should still return 200 with empty recommendations
            assert response.status_code == 200
            data = response.json()
            assert data["recommendations"] == []

    def test_missing_league_id_returns_422(self, test_client):
        """Missing required league_id returns 422."""
        response = test_client.post(
            "/waiver/recommend",
            json={
                "sport": "nfl",
                "risk_mode": "median",
                "sleeper_user_id": "user1",
            },
        )

        assert response.status_code == 422

    def test_missing_sleeper_user_id_returns_422(self, test_client):
        """Missing required sleeper_user_id returns 422."""
        response = test_client.post(
            "/waiver/recommend",
            json={
                "sport": "nfl",
                "risk_mode": "median",
                "league_id": "league123",
            },
        )

        assert response.status_code == 422
