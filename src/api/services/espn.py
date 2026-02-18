"""
ESPN Data Service — Fetches real player stats and information.

Uses ESPN's public API endpoints for player data across NBA, NFL, MLB, NHL.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

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
    "soccer": "soccer/eng.1",  # English Premier League as default
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
    age: int | None
    experience: int | None
    headshot_url: str | None


@dataclass
class PlayerStats:
    """Player statistics for decision-making."""

    player_id: str
    sport: str

    # Common stats
    games_played: int
    games_started: int

    # NBA specific
    minutes_per_game: float | None = None
    points_per_game: float | None = None
    rebounds_per_game: float | None = None
    assists_per_game: float | None = None
    usage_rate: float | None = None
    field_goal_pct: float | None = None
    three_point_pct: float | None = None

    # NFL specific
    pass_yards: float | None = None
    pass_tds: float | None = None
    rush_yards: float | None = None
    rush_tds: float | None = None
    receptions: float | None = None
    receiving_yards: float | None = None
    receiving_tds: float | None = None
    targets: float | None = None
    snap_pct: float | None = None

    # MLB specific
    batting_avg: float | None = None
    home_runs: float | None = None
    rbis: float | None = None
    stolen_bases: float | None = None
    ops: float | None = None
    era: float | None = None  # Pitchers
    wins: int | None = None
    strikeouts: float | None = None

    # NHL specific
    goals: float | None = None
    assists_nhl: float | None = None
    plus_minus: float | None = None
    shots: float | None = None
    save_pct: float | None = None  # Goalies

    # Soccer specific
    soccer_goals: float | None = None
    soccer_assists: float | None = None
    soccer_minutes: float | None = None
    soccer_shots: float | None = None
    soccer_shots_on_target: float | None = None
    soccer_key_passes: float | None = None
    soccer_tackles: float | None = None
    soccer_interceptions: float | None = None
    soccer_clean_sheets: float | None = None
    soccer_saves: float | None = None
    soccer_goals_conceded: float | None = None
    soccer_xg: float | None = None
    soccer_xa: float | None = None

    # Recent trends (last 5-10 games)
    recent_avg: float | None = None  # Fantasy points or main stat
    trend_direction: str | None = None  # "up", "down", "stable"


@dataclass
class GameInfo:
    """Upcoming game information."""

    game_id: str
    date: datetime
    home_team: str
    away_team: str
    home_abbrev: str
    away_abbrev: str
    spread: float | None = None
    over_under: float | None = None


@dataclass
class TeamDefense:
    """Team defensive stats for matchup analysis."""

    team_abbrev: str
    sport: str
    defensive_rating: float | None = None
    points_allowed: float | None = None
    pace: float | None = None

    # Position-specific (fantasy relevant)
    vs_pg: float | None = None  # Points allowed to position
    vs_sg: float | None = None
    vs_sf: float | None = None
    vs_pf: float | None = None
    vs_c: float | None = None

    # Soccer position-specific
    vs_fwd: float | None = None
    vs_mid: float | None = None
    vs_def: float | None = None
    vs_gk: float | None = None


class ESPNService:
    """Service for fetching ESPN player and game data."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def search_players(self, query: str, sport: str, limit: int = 10) -> list[PlayerInfo]:
        """Search for players by name using ESPN's search API."""
        cache_key = f"search:{sport}:{query.lower()}"
        if cache_key in _player_cache:
            return _player_cache[cache_key][:limit]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return []

        # Map sport to ESPN league
        league_map = {"nba": "nba", "nfl": "nfl", "mlb": "mlb", "nhl": "nhl", "soccer": "eng.1"}
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
            logger.error("ESPN search error: %s", e)
            return []

    async def get_player(self, player_id: str, sport: str) -> PlayerInfo | None:
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
            logger.error("ESPN get_player error: %s", e)
            return None

    async def get_player_stats(self, player_id: str, sport: str) -> PlayerStats | None:
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
            logger.error("ESPN get_player_stats error: %s", e)
            return None

    def _parse_overview_stats(self, data: dict, player_id: str, sport: str) -> PlayerStats | None:
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
                stats.field_goal_pct = (
                    stat_map.get("fieldgoalpct", 0) / 100 if stat_map.get("fieldgoalpct") else 0
                )
                stats.three_point_pct = (
                    stat_map.get("threepointpct", 0) / 100 if stat_map.get("threepointpct") else 0
                )
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
            elif sport == "soccer":
                stats.games_played = int(
                    stat_map.get("gamesplayed", stat_map.get("appearances", 0))
                )
                stats.soccer_goals = stat_map.get("goals", stat_map.get("totalgoals", 0))
                stats.soccer_assists = stat_map.get("assists", stat_map.get("goalassists", 0))
                stats.soccer_minutes = stat_map.get("minutesplayed", stat_map.get("minutes", 0))
                stats.soccer_shots = stat_map.get("totalshots", stat_map.get("shotsontarget", 0))
                stats.soccer_shots_on_target = stat_map.get(
                    "shotsontarget", stat_map.get("shotsongoal", 0)
                )
                stats.soccer_key_passes = stat_map.get("keypasses", 0)
                stats.soccer_tackles = stat_map.get("tackles", stat_map.get("totalTackles", 0))
                stats.soccer_interceptions = stat_map.get("interceptions", 0)
                stats.soccer_clean_sheets = stat_map.get("cleansheets", 0)
                stats.soccer_saves = stat_map.get("saves", 0)
                stats.soccer_goals_conceded = stat_map.get(
                    "goalsconceded", stat_map.get("goalagainst", 0)
                )

            return stats

        except Exception as e:
            logger.error("Error parsing overview stats: %s", e)
            return None

    async def find_player_by_name(
        self, name: str, sport: str
    ) -> tuple[PlayerInfo, PlayerStats] | None:
        """Find a player by name and return info + stats."""
        cache_key = f"find:{sport}:{name.lower()}"
        if cache_key in _player_cache:
            cached = _player_cache[cache_key]
            if cached:
                return cached
            return None

        # Map sport to league for search
        league_map = {"nba": "nba", "nfl": "nfl", "mlb": "mlb", "nhl": "nhl", "soccer": "eng.1"}
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
            logger.error("ESPN find_player_by_name error: %s", e)
            return None

    async def get_team_schedule(self, team_abbrev: str, sport: str) -> list[GameInfo]:
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
                game_date = datetime.fromisoformat(event.get("date", "").replace("Z", "+00:00"))

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
            logger.error("ESPN get_team_schedule error: %s", e)
            return []

    async def get_next_opponent(self, team_abbrev: str, sport: str) -> str | None:
        """Return opponent abbreviation for the next upcoming game."""
        games = await self.get_team_schedule(team_abbrev, sport)
        if not games:
            return None
        game = games[0]
        return game.away_abbrev if game.home_abbrev == team_abbrev else game.home_abbrev

    async def get_team_defense(self, team_abbrev: str, sport: str) -> TeamDefense | None:
        """Fetch team defensive stats from ESPN team stats endpoint."""
        cache_key = f"defense:{sport}:{team_abbrev}"
        if cache_key in _team_cache:
            return _team_cache[cache_key]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return None

        try:
            # Get team ID first
            url = f"{ESPN_API_BASE}/{sport_path}/teams/{team_abbrev}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            team_data = data.get("team", {})
            team_id = team_data.get("id")
            if not team_id:
                return None

            # Fetch team statistics
            stats_url = f"{ESPN_API_BASE}/{sport_path}/teams/{team_id}/statistics"
            stats_response = await self.client.get(stats_url)
            stats_response.raise_for_status()
            stats_data = stats_response.json()

            defense = TeamDefense(team_abbrev=team_abbrev, sport=sport)

            # Parse stats from the response
            for category in stats_data.get("splits", {}).get("categories", []):
                for stat in category.get("stats", []):
                    name = stat.get("name", "").lower()
                    value = stat.get("value", 0)
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        continue

                    if sport == "nba":
                        if name in ("defensiverating", "defrtg"):
                            defense.defensive_rating = value
                        elif name in ("opponentpointspergame", "oppptspergame"):
                            defense.points_allowed = value
                        elif name == "pace":
                            defense.pace = value
                    elif sport == "nfl":
                        if name in ("pointsallowed", "pointsagainst", "ptsagainst"):
                            defense.points_allowed = value

            _team_cache[cache_key] = defense
            return defense

        except Exception as e:
            logger.error("ESPN get_team_defense error: %s", e)
            return None

    async def _search_rosters(self, name: str, sport: str) -> PlayerInfo | None:
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
            logger.error("ESPN roster search error: %s", e)

        return None

    def _parse_player(self, data: dict, sport: str) -> PlayerInfo | None:
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
                experience=data.get("experience", {}).get("years")
                if isinstance(data.get("experience"), dict)
                else None,
                headshot_url=headshot_url,
            )
        except Exception as e:
            logger.error("Error parsing player: %s", e)
            return None

    def _parse_stats(self, data: dict, player_id: str, sport: str) -> PlayerStats | None:
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
                    elif sport == "soccer":
                        self._map_soccer_stat(stats, name, value)

            return stats

        except Exception as e:
            logger.error("Error parsing stats: %s", e)
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

    def _map_soccer_stat(self, stats: PlayerStats, name: str, value: float):
        """Map Soccer stat names to PlayerStats fields."""
        mapping = {
            "gamesplayed": "games_played",
            "appearances": "games_played",
            "goals": "soccer_goals",
            "totalgoals": "soccer_goals",
            "assists": "soccer_assists",
            "goalassists": "soccer_assists",
            "minutesplayed": "soccer_minutes",
            "minutes": "soccer_minutes",
            "totalshots": "soccer_shots",
            "shotsontarget": "soccer_shots_on_target",
            "shotsongoal": "soccer_shots_on_target",
            "keypasses": "soccer_key_passes",
            "tackles": "soccer_tackles",
            "totaltackles": "soccer_tackles",
            "interceptions": "soccer_interceptions",
            "cleansheets": "soccer_clean_sheets",
            "saves": "soccer_saves",
            "goalsconceded": "soccer_goals_conceded",
            "goalagainst": "soccer_goals_conceded",
        }
        field = mapping.get(name.replace(" ", "").replace("-", "").lower())
        if field:
            setattr(stats, field, value)

    async def get_player_game_logs(self, player_id: str, sport: str, limit: int = 10) -> list[dict]:
        """
        Fetch recent game-by-game stats for trend analysis.

        Returns list of game log dicts with sport-specific stats.
        Used for OD (Opportunity Delta) and RMI trend calculations.
        """
        cache_key = f"gamelog:{sport}:{player_id}:{limit}"
        if cache_key in _player_cache:
            return _player_cache[cache_key]

        sport_path = SPORT_PATHS.get(sport)
        if not sport_path:
            return []

        try:
            # ESPN gamelog endpoint
            url = f"{ESPN_WEB_API}/{sport_path}/athletes/{player_id}/gamelog"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            game_logs = []
            events = data.get("events", [])

            for event in events[:limit]:
                game_log = self._parse_game_log(event, sport)
                if game_log:
                    game_logs.append(game_log)

            _player_cache[cache_key] = game_logs
            return game_logs

        except Exception as e:
            logger.error("ESPN get_player_game_logs error: %s", e)
            return []

    def _parse_game_log(self, event: dict, sport: str) -> dict | None:
        """Parse a single game log entry."""
        try:
            stats_data = event.get("stats", [])
            opponent = event.get("opponent", {})

            game_log = {
                "game_id": event.get("id", ""),
                "date": event.get("date", ""),
                "opponent": opponent.get("abbreviation", ""),
                "home_away": "H" if event.get("homeAway") == "home" else "A",
                "result": "W" if event.get("gameResult") == "W" else "L",
            }

            # Parse stats based on sport
            if sport == "nba":
                game_log.update(self._parse_nba_game_log(stats_data, event))
            elif sport == "nfl":
                game_log.update(self._parse_nfl_game_log(stats_data, event))
            elif sport == "mlb":
                game_log.update(self._parse_mlb_game_log(stats_data, event))
            elif sport == "nhl":
                game_log.update(self._parse_nhl_game_log(stats_data, event))
            elif sport == "soccer":
                game_log.update(self._parse_soccer_game_log(stats_data, event))

            return game_log

        except Exception as e:
            logger.error("Error parsing game log: %s", e)
            return None

    def _parse_nba_game_log(self, stats: list, event: dict) -> dict:
        """Parse NBA game log stats."""
        stat_names = event.get("statNames", [])
        stat_map = {}
        for i, name in enumerate(stat_names):
            if i < len(stats):
                try:
                    stat_map[name.lower()] = float(stats[i]) if stats[i] else 0
                except (ValueError, TypeError):
                    stat_map[name.lower()] = 0

        return {
            "minutes": int(stat_map.get("min", 0)),
            "points": int(stat_map.get("pts", 0)),
            "rebounds": int(stat_map.get("reb", 0)),
            "assists": int(stat_map.get("ast", 0)),
            "steals": int(stat_map.get("stl", 0)),
            "blocks": int(stat_map.get("blk", 0)),
            "turnovers": int(stat_map.get("to", 0)),
            "fg_made": int(stat_map.get("fgm", 0)),
            "fg_attempted": int(stat_map.get("fga", 0)),
            "three_made": int(stat_map.get("3pm", stat_map.get("fg3m", 0))),
            "three_attempted": int(stat_map.get("3pa", stat_map.get("fg3a", 0))),
            "ft_made": int(stat_map.get("ftm", 0)),
            "ft_attempted": int(stat_map.get("fta", 0)),
        }

    def _parse_nfl_game_log(self, stats: list, event: dict) -> dict:
        """Parse NFL game log stats."""
        stat_names = event.get("statNames", [])
        stat_map = {}
        for i, name in enumerate(stat_names):
            if i < len(stats):
                try:
                    stat_map[name.lower()] = float(stats[i]) if stats[i] else 0
                except (ValueError, TypeError):
                    stat_map[name.lower()] = 0

        return {
            "pass_yards": int(stat_map.get("passyds", stat_map.get("pyds", 0))),
            "pass_tds": int(stat_map.get("passtd", stat_map.get("ptd", 0))),
            "pass_ints": int(stat_map.get("int", 0)),
            "rush_yards": int(stat_map.get("rushyds", stat_map.get("ryds", 0))),
            "rush_tds": int(stat_map.get("rushtd", stat_map.get("rtd", 0))),
            "receptions": int(stat_map.get("rec", 0)),
            "receiving_yards": int(stat_map.get("recyds", stat_map.get("yds", 0))),
            "receiving_tds": int(stat_map.get("rectd", stat_map.get("td", 0))),
            "targets": int(stat_map.get("tar", stat_map.get("tgt", 0))),
            "snaps": int(stat_map.get("snaps", 0)),
        }

    def _parse_mlb_game_log(self, stats: list, event: dict) -> dict:
        """Parse MLB game log stats."""
        stat_names = event.get("statNames", [])
        stat_map = {}
        for i, name in enumerate(stat_names):
            if i < len(stats):
                try:
                    stat_map[name.lower()] = float(stats[i]) if stats[i] else 0
                except (ValueError, TypeError):
                    stat_map[name.lower()] = 0

        return {
            "at_bats": int(stat_map.get("ab", 0)),
            "hits": int(stat_map.get("h", 0)),
            "home_runs": int(stat_map.get("hr", 0)),
            "rbis": int(stat_map.get("rbi", 0)),
            "stolen_bases": int(stat_map.get("sb", 0)),
            "walks": int(stat_map.get("bb", 0)),
            "strikeouts": int(stat_map.get("so", stat_map.get("k", 0))),
            "innings_pitched": stat_map.get("ip", 0),
            "earned_runs": int(stat_map.get("er", 0)),
        }

    def _parse_nhl_game_log(self, stats: list, event: dict) -> dict:
        """Parse NHL game log stats."""
        stat_names = event.get("statNames", [])
        stat_map = {}
        for i, name in enumerate(stat_names):
            if i < len(stats):
                try:
                    stat_map[name.lower()] = float(stats[i]) if stats[i] else 0
                except (ValueError, TypeError):
                    stat_map[name.lower()] = 0

        return {
            "goals": int(stat_map.get("g", 0)),
            "assists": int(stat_map.get("a", 0)),
            "plus_minus": int(stat_map.get("+/-", stat_map.get("plusminus", 0))),
            "shots": int(stat_map.get("sog", stat_map.get("shots", 0))),
            "time_on_ice": int(stat_map.get("toi", 0)),
            "saves": int(stat_map.get("sv", 0)),
            "goals_against": int(stat_map.get("ga", 0)),
        }

    def _parse_soccer_game_log(self, stats: list, event: dict) -> dict:
        """Parse Soccer game log stats."""
        stat_names = event.get("statNames", [])
        stat_map = {}
        for i, name in enumerate(stat_names):
            if i < len(stats):
                try:
                    stat_map[name.lower()] = float(stats[i]) if stats[i] else 0
                except (ValueError, TypeError):
                    stat_map[name.lower()] = 0

        return {
            "goals": int(stat_map.get("g", stat_map.get("goals", 0))),
            "assists": int(stat_map.get("a", stat_map.get("assists", 0))),
            "minutes": int(stat_map.get("min", stat_map.get("minutes", 0))),
            "shots": int(stat_map.get("sh", stat_map.get("shots", 0))),
            "shots_on_target": int(stat_map.get("sot", stat_map.get("shotsontarget", 0))),
            "key_passes": int(stat_map.get("kp", stat_map.get("keypasses", 0))),
            "tackles": int(stat_map.get("tk", stat_map.get("tackles", 0))),
            "interceptions": int(stat_map.get("int", stat_map.get("interceptions", 0))),
            "saves": int(stat_map.get("sv", stat_map.get("saves", 0))),
            "goals_conceded": int(stat_map.get("gc", stat_map.get("goalsconceded", 0))),
        }

    def calculate_trends(self, game_logs: list[dict], sport: str) -> dict:
        """
        Calculate trend metrics from game logs.

        Returns dict with:
        - minutes_trend: recent 5 games vs overall avg
        - points_trend: recent 5 games vs overall avg
        - usage_trend: if applicable
        """
        if len(game_logs) < 5:
            return {"minutes_trend": 0, "points_trend": 0, "usage_trend": 0}

        recent = game_logs[:5]
        baseline = game_logs[:10] if len(game_logs) >= 10 else game_logs

        trends = {}

        if sport == "nba":
            recent_mins = sum(g.get("minutes", 0) for g in recent) / len(recent)
            baseline_mins = sum(g.get("minutes", 0) for g in baseline) / len(baseline)
            trends["minutes_trend"] = recent_mins - baseline_mins

            recent_pts = sum(g.get("points", 0) for g in recent) / len(recent)
            baseline_pts = sum(g.get("points", 0) for g in baseline) / len(baseline)
            trends["points_trend"] = recent_pts - baseline_pts

            trends["usage_trend"] = 0  # Would need advanced stats

        elif sport == "nfl":
            # Use snap count or targets as proxy for "minutes"
            recent_snaps = sum(g.get("snaps", 0) for g in recent) / len(recent)
            baseline_snaps = sum(g.get("snaps", 0) for g in baseline) / len(baseline)
            trends["minutes_trend"] = recent_snaps - baseline_snaps

            recent_targets = sum(g.get("targets", 0) for g in recent) / len(recent)
            baseline_targets = sum(g.get("targets", 0) for g in baseline) / len(baseline)
            trends["usage_trend"] = recent_targets - baseline_targets

            trends["points_trend"] = 0

        elif sport == "mlb":
            # At-bats as proxy for "minutes"
            recent_ab = sum(g.get("at_bats", 0) for g in recent) / len(recent)
            baseline_ab = sum(g.get("at_bats", 0) for g in baseline) / len(baseline)
            trends["minutes_trend"] = recent_ab - baseline_ab

            recent_hr = sum(g.get("home_runs", 0) for g in recent) / len(recent)
            baseline_hr = sum(g.get("home_runs", 0) for g in baseline) / len(baseline)
            trends["points_trend"] = recent_hr - baseline_hr

            recent_hits = sum(g.get("hits", 0) for g in recent) / len(recent)
            baseline_hits = sum(g.get("hits", 0) for g in baseline) / len(baseline)
            trends["usage_trend"] = recent_hits - baseline_hits

        elif sport == "nhl":
            # Time on ice as minutes
            recent_toi = sum(g.get("time_on_ice", 0) for g in recent) / len(recent)
            baseline_toi = sum(g.get("time_on_ice", 0) for g in baseline) / len(baseline)
            trends["minutes_trend"] = recent_toi - baseline_toi

            recent_goals = sum(g.get("goals", 0) for g in recent) / len(recent)
            baseline_goals = sum(g.get("goals", 0) for g in baseline) / len(baseline)
            trends["points_trend"] = recent_goals - baseline_goals

            recent_shots = sum(g.get("shots", 0) for g in recent) / len(recent)
            baseline_shots = sum(g.get("shots", 0) for g in baseline) / len(baseline)
            trends["usage_trend"] = recent_shots - baseline_shots

        elif sport == "soccer":
            # Minutes played as primary involvement metric
            recent_mins = sum(g.get("minutes", 0) for g in recent) / len(recent)
            baseline_mins = sum(g.get("minutes", 0) for g in baseline) / len(baseline)
            trends["minutes_trend"] = recent_mins - baseline_mins

            # Goal involvement (goals + assists) as points proxy
            recent_gi = sum(g.get("goals", 0) + g.get("assists", 0) for g in recent) / len(recent)
            baseline_gi = sum(g.get("goals", 0) + g.get("assists", 0) for g in baseline) / len(
                baseline
            )
            trends["points_trend"] = recent_gi - baseline_gi

            # Shots as usage proxy
            recent_shots = sum(g.get("shots", 0) for g in recent) / len(recent)
            baseline_shots = sum(g.get("shots", 0) for g in baseline) / len(baseline)
            trends["usage_trend"] = recent_shots - baseline_shots

        else:
            trends = {"minutes_trend": 0, "points_trend": 0, "usage_trend": 0}

        return trends


# Singleton
espn_service = ESPNService()


def format_player_context(player: PlayerInfo, stats: PlayerStats | None, sport: str) -> str:
    """Format player info and stats for Claude context injection."""
    lines = [
        f"**{player.name}** ({player.team_abbrev} - {player.position})",
    ]

    if stats:
        if sport == "nba":
            lines.extend(
                [
                    f"- Games: {stats.games_played} GP, {stats.games_started} GS",
                    f"- Per Game: {stats.points_per_game or 0:.1f} PTS, {stats.rebounds_per_game or 0:.1f} REB, {stats.assists_per_game or 0:.1f} AST",
                    f"- Minutes: {stats.minutes_per_game or 0:.1f} MPG",
                    f"- Shooting: {(stats.field_goal_pct or 0) * 100:.1f}% FG, {(stats.three_point_pct or 0) * 100:.1f}% 3PT",
                ]
            )
        elif sport == "nfl":
            if stats.pass_yards:
                lines.append(f"- Passing: {stats.pass_yards:.0f} YDS, {stats.pass_tds:.0f} TD")
            if stats.rush_yards:
                lines.append(f"- Rushing: {stats.rush_yards:.0f} YDS, {stats.rush_tds:.0f} TD")
            if stats.receptions:
                lines.append(
                    f"- Receiving: {stats.receptions:.0f} REC, {stats.receiving_yards:.0f} YDS, {stats.receiving_tds:.0f} TD"
                )
            if stats.targets:
                lines.append(f"- Targets: {stats.targets:.0f}")
        elif sport == "mlb":
            if stats.batting_avg:
                lines.append(
                    f"- Batting: {stats.batting_avg:.3f} AVG, {stats.home_runs:.0f} HR, {stats.rbis:.0f} RBI"
                )
            if stats.ops:
                lines.append(f"- OPS: {stats.ops:.3f}")
            if stats.era:
                lines.append(
                    f"- Pitching: {stats.era:.2f} ERA, {stats.wins} W, {stats.strikeouts:.0f} K"
                )
        elif sport == "nhl":
            lines.append(
                f"- Stats: {stats.goals or 0:.0f} G, {stats.assists_nhl or 0:.0f} A, {stats.plus_minus or 0:+.0f}"
            )
            if stats.save_pct:
                lines.append(f"- Save %: {stats.save_pct:.3f}")
        elif sport == "soccer":
            lines.append(
                f"- Stats: {stats.soccer_goals or 0:.0f} G, {stats.soccer_assists or 0:.0f} A"
            )
            if stats.soccer_minutes:
                lines.append(f"- Minutes: {stats.soccer_minutes:.0f}")
            if stats.soccer_key_passes:
                lines.append(f"- Key Passes: {stats.soccer_key_passes:.1f}")
            if stats.soccer_clean_sheets:
                lines.append(f"- Clean Sheets: {stats.soccer_clean_sheets:.0f}")
            if stats.soccer_saves:
                lines.append(f"- Saves: {stats.soccer_saves:.0f}")

    return "\n".join(lines)
