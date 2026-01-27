"""Tests for Unified Roster Service."""

from services.roster import (
    LineupSlot,
    Platform,
    UnifiedPlayer,
    UnifiedRoster,
    UnifiedRosterService,
    _normalize_lineup_slot,
)


class TestNormalizeLineupSlot:
    def test_bench_variants(self):
        assert _normalize_lineup_slot("BENCH") == LineupSlot.BENCH
        assert _normalize_lineup_slot("BN") == LineupSlot.BENCH
        assert _normalize_lineup_slot("BE") == LineupSlot.BENCH

    def test_ir_variants(self):
        assert _normalize_lineup_slot("IR") == LineupSlot.IR
        assert _normalize_lineup_slot("IL") == LineupSlot.IR
        assert _normalize_lineup_slot("IR+") == LineupSlot.IR
        assert _normalize_lineup_slot("DL") == LineupSlot.IR

    def test_starter_slots(self):
        assert _normalize_lineup_slot("QB") == LineupSlot.STARTER
        assert _normalize_lineup_slot("RB") == LineupSlot.STARTER
        assert _normalize_lineup_slot("FLEX") == LineupSlot.STARTER
        assert _normalize_lineup_slot("UTIL") == LineupSlot.STARTER

    def test_unknown(self):
        assert _normalize_lineup_slot("") == LineupSlot.UNKNOWN
        assert _normalize_lineup_slot("UNKNOWN") == LineupSlot.UNKNOWN


class TestUnifiedPlayer:
    def test_canonical_id_espn_preferred(self):
        p = UnifiedPlayer(
            name="Test", team="LAL", position="PG", sport="nba",
            espn_id="E123", sleeper_id="S456", yahoo_id="Y789",
        )
        assert p.canonical_id == "E123"

    def test_canonical_id_sleeper_fallback(self):
        p = UnifiedPlayer(
            name="Test", team="LAL", position="PG", sport="nba",
            sleeper_id="S456", yahoo_id="Y789",
        )
        assert p.canonical_id == "S456"

    def test_canonical_id_manual_fallback(self):
        p = UnifiedPlayer(name="Test Player", team="LAL", position="PG", sport="nba")
        assert p.canonical_id == "manual:Test Player"


class TestUnifiedRoster:
    def test_starters_and_bench(self):
        roster = UnifiedRoster(
            sport="nba", league_name="Test", platform=Platform.ESPN,
            players=[
                UnifiedPlayer(name="A", team="T", position="PG", sport="nba", lineup_slot=LineupSlot.STARTER),
                UnifiedPlayer(name="B", team="T", position="SG", sport="nba", lineup_slot=LineupSlot.BENCH),
                UnifiedPlayer(name="C", team="T", position="SF", sport="nba", lineup_slot=LineupSlot.STARTER),
            ],
        )
        assert len(roster.starters) == 2
        assert len(roster.bench) == 1

    def test_get_player(self):
        roster = UnifiedRoster(
            sport="nba", league_name="Test", platform=Platform.ESPN,
            players=[
                UnifiedPlayer(name="LeBron James", team="LAL", position="SF", sport="nba"),
            ],
        )
        assert roster.get_player("lebron james") is not None
        assert roster.get_player("Nobody") is None


class TestMergeRosters:
    def _make_service(self):
        return UnifiedRosterService(None, None, None)

    def test_merge_empty(self):
        svc = self._make_service()
        result = svc.merge_rosters([])
        assert len(result.players) == 0

    def test_merge_single_roster(self):
        svc = self._make_service()
        roster = UnifiedRoster(
            sport="nba", league_name="ESPN", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="A", team="T", position="PG", sport="nba", espn_id="E1")],
        )
        result = svc.merge_rosters([roster])
        assert len(result.players) == 1
        assert result.players[0].espn_id == "E1"

    def test_merge_deduplicates_by_name(self):
        svc = self._make_service()
        espn_roster = UnifiedRoster(
            sport="nba", league_name="ESPN", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="LeBron James", team="LAL", position="SF", sport="nba", espn_id="E1")],
        )
        sleeper_roster = UnifiedRoster(
            sport="nba", league_name="Sleeper", platform=Platform.SLEEPER,
            players=[UnifiedPlayer(name="LeBron James", team="LAL", position="SF", sport="nba", sleeper_id="S1")],
        )
        result = svc.merge_rosters([espn_roster, sleeper_roster])
        assert len(result.players) == 1
        # Both IDs should be filled
        assert result.players[0].espn_id == "E1"
        assert result.players[0].sleeper_id == "S1"

    def test_merge_espn_wins_priority(self):
        svc = self._make_service()
        espn_roster = UnifiedRoster(
            sport="nba", league_name="ESPN", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="Test", team="LAL", position="PG", sport="nba", espn_id="E1", projected_points=25.0)],
        )
        yahoo_roster = UnifiedRoster(
            sport="nba", league_name="Yahoo", platform=Platform.YAHOO,
            players=[UnifiedPlayer(name="Test", team="LAL", position="PG", sport="nba", yahoo_id="Y1", projected_points=22.0)],
        )
        result = svc.merge_rosters([espn_roster, yahoo_roster])
        # ESPN projected_points should win (higher priority)
        assert result.players[0].projected_points == 25.0
        assert result.players[0].yahoo_id == "Y1"  # But Yahoo ID is filled

    def test_merge_unique_players_kept(self):
        svc = self._make_service()
        r1 = UnifiedRoster(
            sport="nba", league_name="ESPN", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="A", team="T", position="PG", sport="nba")],
        )
        r2 = UnifiedRoster(
            sport="nba", league_name="Sleeper", platform=Platform.SLEEPER,
            players=[UnifiedPlayer(name="B", team="T", position="SG", sport="nba")],
        )
        result = svc.merge_rosters([r1, r2])
        assert len(result.players) == 2


class TestApplyOverrides:
    def test_override_lineup_slot(self):
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba", league_name="Test", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="A", team="T", position="PG", sport="nba", espn_id="E1", lineup_slot=LineupSlot.BENCH)],
        )
        result = svc.apply_overrides(roster, {"E1": {"lineup_slot": "STARTER"}})
        assert result.players[0].lineup_slot == LineupSlot.STARTER

    def test_override_injury_status(self):
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba", league_name="Test", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="A", team="T", position="PG", sport="nba", espn_id="E1")],
        )
        result = svc.apply_overrides(roster, {"E1": {"injury_status": "GTD"}})
        assert result.players[0].injury_status == "GTD"

    def test_override_no_match(self):
        svc = UnifiedRosterService(None, None, None)
        roster = UnifiedRoster(
            sport="nba", league_name="Test", platform=Platform.ESPN,
            players=[UnifiedPlayer(name="A", team="T", position="PG", sport="nba", espn_id="E1")],
        )
        result = svc.apply_overrides(roster, {"E999": {"lineup_slot": "IR"}})
        assert result.players[0].lineup_slot == LineupSlot.UNKNOWN  # Unchanged
