"""
ESPN Data Service — Fetches real player stats and information.

Uses ESPN's public API endpoints for player data across NBA, NFL, MLB, NHL.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import httpx
from cachetools import TTLCache

# ESPN API base URLs
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_WEB_API = "https://site.web.api.espn.com/apis/common/v3/sports"
ESPN_SEARCH_API = "https://site.web.api.espn.com/apis/common/v3/search"

# Sport mappings
SPORT_PATHS = {
    "nba": "basketball/nba",
    "nfl": "football/nfl",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
}

# Cache: 15 min TTL, max 1000 players
_player_cache: TTLCache = TTLCache(maxsize=1000, ttl=900)
_team_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)
_schedule_cache: TTLCache = TTLCache(maxsize=50, ttl=300)


@dataclass
class PlayerInfo:
    """Basic player information."""
    id: str
    name: str
    team: str
    team_abbrev: str
    position: str
    jersey: str
    height: str
    weight: str
    age: Optional[int]
    experience: Optional[int]
    headshot_url: Optional[str]


@dataclass
class PlayerStats:
    """Player statistics for decision-making."""
    player_id: str
    sport: str

    # Common stats
    games_played: int
    games_started: int

    # NBA specific
    minutes_per_game: Optional[float] = None
    points_per_game: Optional[float] = None
    rebounds_per_game: Optional[float] = None
    assists_per_game: Optional[float] = None
    usage_rate: Optional[float] = None
    field_goal_pct: Optional[float] = None
    three_point_pct: Optional[float] = None

    # NFL specific
    pass_yards: Optional[float] = None
    pass_tds: Optional[float] = None
    rush_yards: Optional[float] = None
    rush_tds: Optional[float] = None
    receptions: Optional[float] = None
    receiving_yards: Optional[float] = None
    receiving_tds: Optional[float] = None
    targets: Optional[float] = None
    snap_pct: Optional[float] = None

    # MLB specific
    batting_avg: Optional[float] = None
    home_runs: Optional[float] = None
    rbis: Optional[float] = None
    stolen_bases: Optional[float] = None
    ops: Optional[float] = None
    era: Optional[float] = None  # Pitchers
    wins: Optional[int] = None
    strikeouts: Optional[float] = None

    # NHL specific
    goals: Optional[float] = None
    assists_nhl: Optional[float] = None
    plus_minus: Optional[float] = None
    shots: Optional[float] = None
    save_pct: Optional[float] = None  # Goalies

    # Recent trends (last 5-10 games)
    recent_avg: Optional[float] = None  # Fantasy points or main stat
    trend_direction: Optional[str] = None  # "up", "down", "stable"


@dataclass
class GameInfo:
    """Upcoming game information."""
    game_id: str
    date: datetime
    home_team: str
    away_team: str
    home_abbrev: str
    away_abbrev: str
    spread: Optional[float] = None
    over_under: Optional[float] = None


@dataclass
class TeamDefense:
    """Team defensive stats for matchup analysis."""
    team_abbrev: str
    sport: str
    defensive_rating: Optional[float] = None
    points_allowed: Optional[float] = None
    pace: Optional[float] = None

    # Position-specific (fantasy relevant)
    vs_pg: Optional[float] = None  # Points allowed to position
    vs_sg: Optional[float] = None
    vs_sf: Optional[float] = None
    vs_pf: Optional[float] = None
    vs_c: Optional[float] = None


class ESPNService:
    """Service for fetching ESPN player and game data."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def search_players(
        self, query: str, sport: str, limit: int = 10
    ) -> list[PlayerInfo]:
        """Search for players by name using ESPN's search API."""
        cache_key = f"search:{sport}:{query.lower()}"
        if cache_key in _player_cache:
            return _player_cache[cache_key][:limit]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return []

        # Map sport to ESPN league
        league_map = {"nba": "nba", "nfl": "nfl", "mlb": "mlb", "nhl": "nhl"}
        league = league_map.get(sport)

        try:
            # Use ESPN's search API
            params = {
                "query": query,
                "limit": limit * 2,
                "type": "player",
            }

            response = await self.client.get(ESPN_SEARCH_API, params=params)
            response.raise_for_status()
            data = response.json()

            players = []

            for item in data.get("items", []):
                # Filter by sport/league
                if item.get("league") != league:
                    continue

                player_id = item.get("id")
                if not player_id:
                    continue

                # Get full player details
                player = await self.get_player(player_id, sport)
                if player:
                    players.append(player)

                if len(players) >= limit:
                    break

            _player_cache[cache_key] = players
            return players[:limit]

        except Exception as e:
            print(f"ESPN search error: {e}")
            return []

    async def get_player(self, player_id: str, sport: str) -> Optional[PlayerInfo]:
        """Get player information by ID."""
        cache_key = f"player:{sport}:{player_id}"
        if cache_key in _player_cache:
            return _player_cache[cache_key]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return None

        try:
            # Use web API for athlete data
            url = f"{ESPN_WEB_API}/{sport_path}/athletes/{player_id}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            athlete_data = data.get("athlete", data)
            player = self._parse_player(athlete_data, sport)
            if player:
                _player_cache[cache_key] = player
            return player

        except Exception as e:
            print(f"ESPN get_player error: {e}")
            return None

    async def get_player_stats(
        self, player_id: str, sport: str
    ) -> Optional[PlayerStats]:
        """Get player statistics."""
        cache_key = f"stats:{sport}:{player_id}"
        if cache_key in _player_cache:
            return _player_cache[cache_key]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return None

        try:
            # Use overview endpoint which has stats
            url = f"{ESPN_WEB_API}/{sport_path}/athletes/{player_id}/overview"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            stats = self._parse_overview_stats(data, player_id, sport)
            if stats:
                _player_cache[cache_key] = stats
            return stats

        except Exception as e:
            print(f"ESPN get_player_stats error: {e}")
            return None

    def _parse_overview_stats(
        self, data: dict, player_id: str, sport: str
    ) -> Optional[PlayerStats]:
        """Parse stats from the overview endpoint."""
        try:
            statistics = data.get("statistics", {})
            names = statistics.get("names", [])
            splits = statistics.get("splits", [])

            if not splits:
                return None

            # Get current season stats (first split is usually regular season)
            current_stats = splits[0].get("stats", [])

            stats = PlayerStats(
                player_id=player_id,
                sport=sport,
                games_played=0,
                games_started=0,
            )

            # Build name-to-value mapping
            stat_map = {}
            for i, name in enumerate(names):
                if i < len(current_stats):
                    try:
                        stat_map[name.lower()] = float(current_stats[i])
                    except (ValueError, TypeError):
                        stat_map[name.lower()] = 0

            # Map to our stats object based on sport
            if sport == "nba":
                stats.games_played = int(stat_map.get("gamesplayed", 0))
                stats.minutes_per_game = stat_map.get("avgminutes", 0)
                stats.points_per_game = stat_map.get("avgpoints", 0)
                stats.rebounds_per_game = stat_map.get("avgrebounds", 0)
                stats.assists_per_game = stat_map.get("avgassists", 0)
                stats.field_goal_pct = stat_map.get("fieldgoalpct", 0) / 100 if stat_map.get("fieldgoalpct") else 0
                stats.three_point_pct = stat_map.get("threepointpct", 0) / 100 if stat_map.get("threepointpct") else 0
            elif sport == "nfl":
                stats.games_played = int(stat_map.get("gamesplayed", 0))
                stats.pass_yards = stat_map.get("passingyards", stat_map.get("passyards", 0))
                stats.pass_tds = stat_map.get("passingtouchdowns", stat_map.get("passtd", 0))
                stats.rush_yards = stat_map.get("rushingyards", stat_map.get("rushyards", 0))
                stats.rush_tds = stat_map.get("rushingtouchdowns", stat_map.get("rushtd", 0))
                stats.receptions = stat_map.get("receptions", stat_map.get("rec", 0))
                stats.receiving_yards = stat_map.get("receivingyards", stat_map.get("recyards", 0))
                stats.receiving_tds = stat_map.get("receivingtouchdowns", stat_map.get("rectd", 0))
                stats.targets = stat_map.get("targets", 0)
            elif sport == "mlb":
                stats.games_played = int(stat_map.get("gamesplayed", 0))
                stats.batting_avg = stat_map.get("avg", 0)
                stats.home_runs = stat_map.get("homeruns", stat_map.get("hr", 0))
                stats.rbis = stat_map.get("rbi", stat_map.get("rbis", 0))
                stats.stolen_bases = stat_map.get("stolenbases", stat_map.get("sb", 0))
                stats.ops = stat_map.get("ops", 0)
                stats.era = stat_map.get("era", 0)
                stats.wins = int(stat_map.get("wins", stat_map.get("w", 0)))
                stats.strikeouts = stat_map.get("strikeouts", stat_map.get("so", 0))
            elif sport == "nhl":
                stats.games_played = int(stat_map.get("gamesplayed", 0))
                stats.goals = stat_map.get("goals", stat_map.get("g", 0))
                stats.assists_nhl = stat_map.get("assists", stat_map.get("a", 0))
                stats.plus_minus = stat_map.get("plusminus", 0)
                stats.shots = stat_map.get("shots", 0)
                stats.save_pct = stat_map.get("savepct", stat_map.get("svpct", 0))

            return stats

        except Exception as e:
            print(f"Error parsing overview stats: {e}")
            return None

    async def find_player_by_name(
        self, name: str, sport: str
    ) -> Optional[tuple[PlayerInfo, PlayerStats]]:
        """Find a player by name and return info + stats."""
        cache_key = f"find:{sport}:{name.lower()}"
        if cache_key in _player_cache:
            cached = _player_cache[cache_key]
            if cached:
                return cached
            return None

        # Map sport to league for search
        league_map = {"nba": "nba", "nfl": "nfl", "mlb": "mlb", "nhl": "nhl"}
        league = league_map.get(sport)

        try:
            # Use search API to find player
            params = {"query": name, "limit": 5, "type": "player"}
            response = await self.client.get(ESPN_SEARCH_API, params=params)
            response.raise_for_status()
            data = response.json()

            # Find best match in correct sport
            best_match_id = None
            name_lower = name.lower()

            for item in data.get("items", []):
                if item.get("league") != league:
                    continue

                item_name = item.get("displayName", "").lower()
                if name_lower in item_name or item_name in name_lower:
                    best_match_id = item.get("id")
                    break

            if not best_match_id:
                # Take first match in sport if no exact match
                for item in data.get("items", []):
                    if item.get("league") == league:
                        best_match_id = item.get("id")
                        break

            if not best_match_id:
                _player_cache[cache_key] = None
                return None

            # Get player info and stats
            player = await self.get_player(best_match_id, sport)
            if not player:
                _player_cache[cache_key] = None
                return None

            stats = await self.get_player_stats(best_match_id, sport)

            result = (player, stats)
            _player_cache[cache_key] = result
            return result

        except Exception as e:
            print(f"ESPN find_player_by_name error: {e}")
            return None

    async def get_team_schedule(
        self, team_abbrev: str, sport: str
    ) -> list[GameInfo]:
        """Get upcoming games for a team."""
        cache_key = f"schedule:{sport}:{team_abbrev}"
        if cache_key in _schedule_cache:
            return _schedule_cache[cache_key]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return []

        try:
            # Get team's schedule
            url = f"{ESPN_API_BASE}/{sport_path}/teams/{team_abbrev}/schedule"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            games = []
            now = datetime.now()

            for event in data.get("events", []):
                game_date = datetime.fromisoformat(
                    event.get("date", "").replace("Z", "+00:00")
                )

                # Only future games
                if game_date < now:
                    continue

                competitions = event.get("competitions", [{}])
                if not competitions:
                    continue

                comp = competitions[0]
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue

                home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                away = next((c for c in competitors if c.get("homeAway") == "away"), {})

                game = GameInfo(
                    game_id=event.get("id", ""),
                    date=game_date,
                    home_team=home.get("team", {}).get("displayName", ""),
                    away_team=away.get("team", {}).get("displayName", ""),
                    home_abbrev=home.get("team", {}).get("abbreviation", ""),
                    away_abbrev=away.get("team", {}).get("abbreviation", ""),
                )
                games.append(game)

            _schedule_cache[cache_key] = games[:10]  # Next 10 games
            return games[:10]

        except Exception as e:
            print(f"ESPN get_team_schedule error: {e}")
            return []

    async def _search_rosters(
        self, name: str, sport: str
    ) -> Optional[PlayerInfo]:
        """Search team rosters for a player."""
        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return None

        try:
            # Get all teams
            url = f"{ESPN_API_BASE}/{sport_path}/teams"
            response = await self.client.get(url, params={"limit": 50})
            response.raise_for_status()
            data = response.json()

            name_lower = name.lower()

            for team in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
                team_data = team.get("team", {})
                team_id = team_data.get("id")

                if not team_id:
                    continue

                # Get roster
                roster_url = f"{ESPN_API_BASE}/{sport_path}/teams/{team_id}/roster"
                roster_resp = await self.client.get(roster_url)

                if roster_resp.status_code != 200:
                    continue

                roster_data = roster_resp.json()

                for athlete in roster_data.get("athletes", []):
                    athlete_name = athlete.get("displayName", "")
                    if name_lower in athlete_name.lower():
                        return self._parse_player(athlete, sport)

        except Exception as e:
            print(f"ESPN roster search error: {e}")

        return None

    def _parse_player(self, data: dict, sport: str) -> Optional[PlayerInfo]:
        """Parse player data from ESPN response."""
        try:
            team = data.get("team", {})
            if isinstance(team, dict):
                team_name = team.get("displayName", "Unknown")
                team_abbrev = team.get("abbreviation", "UNK")
            else:
                team_name = "Unknown"
                team_abbrev = "UNK"

            position = data.get("position", {})
            if isinstance(position, dict):
                pos = position.get("abbreviation", "")
            else:
                pos = str(position) if position else ""

            headshot = data.get("headshot", {})
            headshot_url = headshot.get("href") if isinstance(headshot, dict) else None

            return PlayerInfo(
                id=str(data.get("id", "")),
                name=data.get("displayName", data.get("fullName", "")),
                team=team_name,
                team_abbrev=team_abbrev,
                position=pos,
                jersey=str(data.get("jersey", "")),
                height=data.get("displayHeight", ""),
                weight=data.get("displayWeight", ""),
                age=data.get("age"),
                experience=data.get("experience", {}).get("years") if isinstance(data.get("experience"), dict) else None,
                headshot_url=headshot_url,
            )
        except Exception as e:
            print(f"Error parsing player: {e}")
            return None

    def _parse_stats(
        self, data: dict, player_id: str, sport: str
    ) -> Optional[PlayerStats]:
        """Parse player statistics from ESPN response."""
        try:
            # Find the most recent season stats
            splits = data.get("splits", {})
            categories = splits.get("categories", [])

            stats = PlayerStats(
                player_id=player_id,
                sport=sport,
                games_played=0,
                games_started=0,
            )

            for category in categories:
                cat_stats = category.get("stats", [])
                for stat in cat_stats:
                    name = stat.get("name", "").lower()
                    value = stat.get("value", 0)

                    # Map stats based on sport
                    if sport == "nba":
                        self._map_nba_stat(stats, name, value)
                    elif sport == "nfl":
                        self._map_nfl_stat(stats, name, value)
                    elif sport == "mlb":
                        self._map_mlb_stat(stats, name, value)
                    elif sport == "nhl":
                        self._map_nhl_stat(stats, name, value)

            return stats

        except Exception as e:
            print(f"Error parsing stats: {e}")
            return None

    def _map_nba_stat(self, stats: PlayerStats, name: str, value: float):
        """Map NBA stat names to PlayerStats fields."""
        mapping = {
            "gamesplayed": "games_played",
            "gamesstarted": "games_started",
            "minutespergame": "minutes_per_game",
            "avgminutes": "minutes_per_game",
            "pointspergame": "points_per_game",
            "avgpoints": "points_per_game",
            "reboundspergame": "rebounds_per_game",
            "avgrebounds": "rebounds_per_game",
            "assistspergame": "assists_per_game",
            "avgassists": "assists_per_game",
            "fieldgoalpct": "field_goal_pct",
            "threepointpct": "three_point_pct",
        }
        field = mapping.get(name.replace(" ", "").replace("-", ""))
        if field:
            setattr(stats, field, value)

    def _map_nfl_stat(self, stats: PlayerStats, name: str, value: float):
        """Map NFL stat names to PlayerStats fields."""
        mapping = {
            "gamesplayed": "games_played",
            "passingyards": "pass_yards",
            "passingtouchdowns": "pass_tds",
            "rushingyards": "rush_yards",
            "rushingtouchdowns": "rush_tds",
            "receptions": "receptions",
            "receivingyards": "receiving_yards",
            "receivingtouchdowns": "receiving_tds",
            "targets": "targets",
        }
        field = mapping.get(name.replace(" ", "").replace("-", "").lower())
        if field:
            setattr(stats, field, value)

    def _map_mlb_stat(self, stats: PlayerStats, name: str, value: float):
        """Map MLB stat names to PlayerStats fields."""
        mapping = {
            "gamesplayed": "games_played",
            "avg": "batting_avg",
            "homeruns": "home_runs",
            "rbi": "rbis",
            "stolenbases": "stolen_bases",
            "ops": "ops",
            "era": "era",
            "wins": "wins",
            "strikeouts": "strikeouts",
        }
        field = mapping.get(name.replace(" ", "").replace("-", "").lower())
        if field:
            setattr(stats, field, value)

    def _map_nhl_stat(self, stats: PlayerStats, name: str, value: float):
        """Map NHL stat names to PlayerStats fields."""
        mapping = {
            "gamesplayed": "games_played",
            "goals": "goals",
            "assists": "assists_nhl",
            "plusminus": "plus_minus",
            "shots": "shots",
            "savepct": "save_pct",
        }
        field = mapping.get(name.replace(" ", "").replace("-", "").lower())
        if field:
            setattr(stats, field, value)


# Singleton
espn_service = ESPNService()


def format_player_context(
    player: PlayerInfo, stats: Optional[PlayerStats], sport: str
) -> str:
    """Format player info and stats for Claude context injection."""
    lines = [
        f"**{player.name}** ({player.team_abbrev} - {player.position})",
    ]

    if stats:
        if sport == "nba":
            lines.extend([
                f"- Games: {stats.games_played} GP, {stats.games_started} GS",
                f"- Per Game: {stats.points_per_game or 0:.1f} PTS, {stats.rebounds_per_game or 0:.1f} REB, {stats.assists_per_game or 0:.1f} AST",
                f"- Minutes: {stats.minutes_per_game or 0:.1f} MPG",
                f"- Shooting: {(stats.field_goal_pct or 0)*100:.1f}% FG, {(stats.three_point_pct or 0)*100:.1f}% 3PT",
            ])
        elif sport == "nfl":
            if stats.pass_yards:
                lines.append(f"- Passing: {stats.pass_yards:.0f} YDS, {stats.pass_tds:.0f} TD")
            if stats.rush_yards:
                lines.append(f"- Rushing: {stats.rush_yards:.0f} YDS, {stats.rush_tds:.0f} TD")
            if stats.receptions:
                lines.append(f"- Receiving: {stats.receptions:.0f} REC, {stats.receiving_yards:.0f} YDS, {stats.receiving_tds:.0f} TD")
            if stats.targets:
                lines.append(f"- Targets: {stats.targets:.0f}")
        elif sport == "mlb":
            if stats.batting_avg:
                lines.append(f"- Batting: {stats.batting_avg:.3f} AVG, {stats.home_runs:.0f} HR, {stats.rbis:.0f} RBI")
            if stats.ops:
                lines.append(f"- OPS: {stats.ops:.3f}")
            if stats.era:
                lines.append(f"- Pitching: {stats.era:.2f} ERA, {stats.wins} W, {stats.strikeouts:.0f} K")
        elif sport == "nhl":
            lines.append(f"- Stats: {stats.goals or 0:.0f} G, {stats.assists_nhl or 0:.0f} A, {stats.plus_minus or 0:+.0f}")
            if stats.save_pct:
                lines.append(f"- Save %: {stats.save_pct:.3f}")

    return "\n".join(lines)
