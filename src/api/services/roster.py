"""
Unified Roster Service — Normalizes rosters from ESPN, Yahoo, and Sleeper
into a single model with conflict resolution and manual overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Platform(str, Enum):
    ESPN = "espn"
    YAHOO = "yahoo"
    SLEEPER = "sleeper"
    MANUAL = "manual"


class LineupSlot(str, Enum):
    STARTER = "starter"
    BENCH = "bench"
    IR = "ir"
    UNKNOWN = "unknown"


@dataclass
class UnifiedPlayer:
    """Platform-agnostic player representation."""

    name: str
    team: str | None
    position: str
    sport: str
    lineup_slot: LineupSlot = LineupSlot.UNKNOWN
    injury_status: str | None = None
    headshot_url: str | None = None

    # Platform-specific IDs (at least one must be set)
    espn_id: str | None = None
    yahoo_id: str | None = None
    sleeper_id: str | None = None

    # Source tracking
    source_platform: Platform = Platform.MANUAL
    projected_points: float | None = None

    @property
    def canonical_id(self) -> str:
        """Best available ID, preferring ESPN > Sleeper > Yahoo."""
        return self.espn_id or self.sleeper_id or self.yahoo_id or f"manual:{self.name}"


@dataclass
class UnifiedRoster:
    """Merged roster from one or more fantasy platforms."""

    sport: str
    league_name: str
    platform: Platform
    players: list[UnifiedPlayer] = field(default_factory=list)

    # Manual overrides (canonical_id → override fields)
    overrides: dict[str, dict] = field(default_factory=dict)

    @property
    def starters(self) -> list[UnifiedPlayer]:
        return [p for p in self.players if p.lineup_slot == LineupSlot.STARTER]

    @property
    def bench(self) -> list[UnifiedPlayer]:
        return [p for p in self.players if p.lineup_slot == LineupSlot.BENCH]

    def get_player(self, name: str) -> UnifiedPlayer | None:
        name_lower = name.lower()
        for p in self.players:
            if p.name.lower() == name_lower:
                return p
        return None


def _normalize_lineup_slot(raw: str) -> LineupSlot:
    """Normalize platform-specific slot names to unified enum."""
    raw_upper = raw.upper().strip()
    if raw_upper in ("BENCH", "BN", "BE"):
        return LineupSlot.BENCH
    if raw_upper in ("IR", "IL", "IR+", "DL", "NA"):
        return LineupSlot.IR
    if raw_upper in ("", "UNKNOWN"):
        return LineupSlot.UNKNOWN
    # Everything else is a starter slot (QB, RB, WR, FLEX, UTIL, etc.)
    return LineupSlot.STARTER


class UnifiedRosterService:
    """Merges rosters from multiple platforms into a unified view."""

    def __init__(self, espn_fantasy_svc, sleeper_svc, yahoo_svc):
        self._espn = espn_fantasy_svc
        self._sleeper = sleeper_svc
        self._yahoo = yahoo_svc

    async def from_espn(
        self,
        creds,
        league_id: str,
        team_id: int,
        sport: str,
        season: int = 2024,
    ) -> UnifiedRoster:
        """Build unified roster from ESPN Fantasy."""
        roster_players = await self._espn.get_roster(
            creds=creds,
            league_id=league_id,
            team_id=team_id,
            sport=sport,
            season=season,
        )
        league_details = await self._espn.get_league_details(
            creds=creds,
            league_id=league_id,
            sport=sport,
            season=season,
        )
        league_name = (
            league_details.get("name", f"ESPN League {league_id}")
            if league_details
            else f"ESPN League {league_id}"
        )

        players = []
        for rp in roster_players:
            players.append(
                UnifiedPlayer(
                    name=rp.name,
                    team=rp.team,
                    position=rp.position,
                    sport=sport,
                    lineup_slot=_normalize_lineup_slot(rp.lineup_slot),
                    espn_id=rp.espn_id,
                    source_platform=Platform.ESPN,
                    projected_points=rp.projected_points,
                )
            )

        return UnifiedRoster(
            sport=sport, league_name=league_name, platform=Platform.ESPN, players=players
        )

    async def from_sleeper(
        self,
        league_id: str,
        user_id: str,
        sport: str,
    ) -> UnifiedRoster:
        """Build unified roster from Sleeper."""
        roster = await self._sleeper.get_user_roster(league_id, user_id)
        if not roster:
            return UnifiedRoster(
                sport=sport, league_name=f"Sleeper {league_id}", platform=Platform.SLEEPER
            )

        player_details = await self._sleeper.get_players_by_ids(roster.players, sport)
        starters_set = set(roster.starters)

        players = []
        for sp in player_details:
            is_starter = sp.player_id in starters_set
            players.append(
                UnifiedPlayer(
                    name=sp.full_name,
                    team=sp.team,
                    position=sp.position,
                    sport=sport,
                    lineup_slot=LineupSlot.STARTER if is_starter else LineupSlot.BENCH,
                    injury_status=sp.injury_status,
                    sleeper_id=sp.player_id,
                    source_platform=Platform.SLEEPER,
                )
            )

        return UnifiedRoster(
            sport=sport,
            league_name=f"Sleeper {league_id}",
            platform=Platform.SLEEPER,
            players=players,
        )

    async def from_yahoo(
        self,
        access_token: str,
        team_key: str,
        sport: str,
        week: int | None = None,
    ) -> UnifiedRoster:
        """Build unified roster from Yahoo Fantasy."""
        yahoo_players = await self._yahoo.get_team_roster(access_token, team_key, week)

        players = []
        for yp in yahoo_players:
            players.append(
                UnifiedPlayer(
                    name=yp.name,
                    team=yp.team_abbrev,
                    position=yp.position,
                    sport=sport,
                    lineup_slot=_normalize_lineup_slot(yp.status),
                    injury_status=yp.injury_status,
                    yahoo_id=yp.player_id,
                    headshot_url=getattr(yp, "headshot_url", None),
                    source_platform=Platform.YAHOO,
                )
            )

        return UnifiedRoster(
            sport=sport, league_name=f"Yahoo {team_key}", platform=Platform.YAHOO, players=players
        )

    def merge_rosters(self, rosters: list[UnifiedRoster]) -> UnifiedRoster:
        """
        Merge multiple platform rosters into one unified view.

        Conflict resolution priority: ESPN > Sleeper > Yahoo > Manual.
        Players are matched by name (case-insensitive).
        """
        if not rosters:
            return UnifiedRoster(sport="nba", league_name="Empty", platform=Platform.MANUAL)

        priority = {Platform.ESPN: 0, Platform.SLEEPER: 1, Platform.YAHOO: 2, Platform.MANUAL: 3}
        merged: dict[str, UnifiedPlayer] = {}

        # Sort rosters by priority (highest priority first)
        sorted_rosters = sorted(rosters, key=lambda r: priority.get(r.platform, 3))

        for roster in sorted_rosters:
            for player in roster.players:
                key = player.name.lower().strip()
                if key not in merged:
                    merged[key] = player
                else:
                    existing = merged[key]
                    # Fill in missing IDs from lower-priority sources
                    if player.espn_id and not existing.espn_id:
                        existing.espn_id = player.espn_id
                    if player.sleeper_id and not existing.sleeper_id:
                        existing.sleeper_id = player.sleeper_id
                    if player.yahoo_id and not existing.yahoo_id:
                        existing.yahoo_id = player.yahoo_id
                    # Fill missing projected points
                    if player.projected_points and not existing.projected_points:
                        existing.projected_points = player.projected_points
                    # Fill missing injury status
                    if player.injury_status and not existing.injury_status:
                        existing.injury_status = player.injury_status

        sport = sorted_rosters[0].sport
        league_names = [r.league_name for r in sorted_rosters]
        merged_name = " + ".join(league_names)

        return UnifiedRoster(
            sport=sport,
            league_name=merged_name,
            platform=sorted_rosters[0].platform,
            players=list(merged.values()),
        )

    def apply_overrides(self, roster: UnifiedRoster, overrides: dict[str, dict]) -> UnifiedRoster:
        """
        Apply manual overrides to a roster.

        overrides format: {canonical_id: {"lineup_slot": "starter", "injury_status": "GTD"}}
        """
        roster.overrides = overrides
        for player in roster.players:
            override = overrides.get(player.canonical_id)
            if not override:
                continue
            if "lineup_slot" in override:
                player.lineup_slot = _normalize_lineup_slot(override["lineup_slot"])
            if "injury_status" in override:
                player.injury_status = override["injury_status"]
            if "projected_points" in override:
                player.projected_points = override["projected_points"]
        return roster
