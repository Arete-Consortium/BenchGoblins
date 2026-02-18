"""
Sleeper Fantasy API Service — Public API access to Sleeper leagues.

Sleeper's API is public and doesn't require authentication.
Users just need their Sleeper username to fetch their leagues and rosters.

API Docs: https://docs.sleeper.com/
"""

import logging
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger("benchgoblins.sleeper")

# Sleeper API base URL
SLEEPER_API = "https://api.sleeper.app/v1"


class SleeperSport(str, Enum):
    """Sports supported by Sleeper."""

    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"
    NHL = "nhl"


@dataclass
class SleeperUser:
    """Sleeper user information."""

    user_id: str
    username: str
    display_name: str
    avatar: str | None


@dataclass
class SleeperLeague:
    """Sleeper fantasy league information."""

    league_id: str
    name: str
    sport: str
    season: str
    season_type: str  # regular, playoffs
    status: str  # drafting, in_season, complete
    total_rosters: int
    roster_positions: list[str]
    scoring_settings: dict


@dataclass
class SleeperRoster:
    """Sleeper fantasy roster."""

    roster_id: int
    owner_id: str
    players: list[str]  # List of Sleeper player IDs
    starters: list[str]  # Starter player IDs
    reserve: list[str] | None  # IR/reserve player IDs


@dataclass
class SleeperPlayer:
    """Sleeper player information."""

    player_id: str
    full_name: str
    first_name: str
    last_name: str
    team: str | None
    position: str
    sport: str
    status: str  # Active, Inactive, Injured Reserve, etc.
    injury_status: str | None
    age: int | None
    years_exp: int | None


class SleeperService:
    """
    Sleeper Fantasy API client.

    All endpoints are public - no authentication required.
    Just need a username to get started.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._players_cache: dict[str, dict] = {}  # sport -> {player_id -> player_data}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # User Lookup
    # =========================================================================

    async def get_user(self, username: str) -> SleeperUser | None:
        """
        Get user by username.

        Args:
            username: Sleeper username (case-insensitive)

        Returns:
            SleeperUser or None if not found
        """
        client = await self._get_client()

        try:
            response = await client.get(f"{SLEEPER_API}/user/{username}")

            if response.status_code == 200:
                data = response.json()
                if data:
                    return SleeperUser(
                        user_id=data.get("user_id", ""),
                        username=data.get("username", ""),
                        display_name=data.get("display_name", data.get("username", "")),
                        avatar=data.get("avatar"),
                    )
        except httpx.HTTPError as e:
            logger.warning("Sleeper API error looking up user: %s", e)

        return None

    async def get_user_by_id(self, user_id: str) -> SleeperUser | None:
        """Get user by user ID."""
        client = await self._get_client()

        try:
            response = await client.get(f"{SLEEPER_API}/user/{user_id}")

            if response.status_code == 200:
                data = response.json()
                if data:
                    return SleeperUser(
                        user_id=data.get("user_id", ""),
                        username=data.get("username", ""),
                        display_name=data.get("display_name", data.get("username", "")),
                        avatar=data.get("avatar"),
                    )
        except httpx.HTTPError:
            pass

        return None

    # =========================================================================
    # League Discovery
    # =========================================================================

    async def get_user_leagues(
        self,
        user_id: str,
        sport: str = "nfl",
        season: str = "2024",
    ) -> list[SleeperLeague]:
        """
        Get all leagues for a user.

        Args:
            user_id: Sleeper user ID
            sport: Sport key (nfl, nba, etc.)
            season: Season year

        Returns:
            List of SleeperLeague objects
        """
        client = await self._get_client()
        leagues = []

        try:
            response = await client.get(f"{SLEEPER_API}/user/{user_id}/leagues/{sport}/{season}")

            if response.status_code == 200:
                data = response.json()
                for league_data in data or []:
                    leagues.append(self._parse_league(league_data))

        except httpx.HTTPError as e:
            logger.warning("Sleeper API error fetching leagues: %s", e)

        return leagues

    def _parse_league(self, data: dict) -> SleeperLeague:
        """Parse league data from API response."""
        return SleeperLeague(
            league_id=data.get("league_id", ""),
            name=data.get("name", "Unknown League"),
            sport=data.get("sport", "nfl"),
            season=data.get("season", ""),
            season_type=data.get("season_type", "regular"),
            status=data.get("status", ""),
            total_rosters=data.get("total_rosters", 0),
            roster_positions=data.get("roster_positions", []),
            scoring_settings=data.get("scoring_settings", {}),
        )

    # =========================================================================
    # League Details
    # =========================================================================

    async def get_league(self, league_id: str) -> SleeperLeague | None:
        """Get league details by ID."""
        client = await self._get_client()

        try:
            response = await client.get(f"{SLEEPER_API}/league/{league_id}")

            if response.status_code == 200:
                data = response.json()
                if data:
                    return self._parse_league(data)

        except httpx.HTTPError:
            pass

        return None

    async def get_league_users(self, league_id: str) -> list[SleeperUser]:
        """Get all users in a league."""
        client = await self._get_client()
        users = []

        try:
            response = await client.get(f"{SLEEPER_API}/league/{league_id}/users")

            if response.status_code == 200:
                data = response.json()
                for user_data in data or []:
                    users.append(
                        SleeperUser(
                            user_id=user_data.get("user_id", ""),
                            username=user_data.get("username", ""),
                            display_name=user_data.get(
                                "display_name", user_data.get("username", "")
                            ),
                            avatar=user_data.get("avatar"),
                        )
                    )

        except httpx.HTTPError:
            pass

        return users

    # =========================================================================
    # Rosters
    # =========================================================================

    async def get_league_rosters(self, league_id: str) -> list[SleeperRoster]:
        """Get all rosters in a league."""
        client = await self._get_client()
        rosters = []

        try:
            response = await client.get(f"{SLEEPER_API}/league/{league_id}/rosters")

            if response.status_code == 200:
                data = response.json()
                for roster_data in data or []:
                    rosters.append(
                        SleeperRoster(
                            roster_id=roster_data.get("roster_id", 0),
                            owner_id=roster_data.get("owner_id", ""),
                            players=roster_data.get("players") or [],
                            starters=roster_data.get("starters") or [],
                            reserve=roster_data.get("reserve"),
                        )
                    )

        except httpx.HTTPError:
            pass

        return rosters

    async def get_user_roster(
        self,
        league_id: str,
        user_id: str,
    ) -> SleeperRoster | None:
        """Get a specific user's roster in a league."""
        rosters = await self.get_league_rosters(league_id)

        for roster in rosters:
            if roster.owner_id == user_id:
                return roster

        return None

    # =========================================================================
    # Players Database
    # =========================================================================

    async def get_all_players(self, sport: str = "nfl") -> dict[str, dict]:
        """
        Get all players for a sport.

        This returns a large dataset (~10MB for NFL).
        Results are cached in memory.

        Args:
            sport: Sport key (nfl, nba, etc.)

        Returns:
            Dict mapping player_id to player data
        """
        # Check cache first
        if sport in self._players_cache:
            return self._players_cache[sport]

        client = await self._get_client()

        try:
            response = await client.get(f"{SLEEPER_API}/players/{sport}")

            if response.status_code == 200:
                data = response.json()
                self._players_cache[sport] = data or {}
                return self._players_cache[sport]

        except httpx.HTTPError as e:
            logger.warning("Sleeper API error fetching players: %s", e)

        return {}

    async def get_player(self, player_id: str, sport: str = "nfl") -> SleeperPlayer | None:
        """Get a specific player by ID."""
        players = await self.get_all_players(sport)
        player_data = players.get(player_id)

        if not player_data:
            return None

        return SleeperPlayer(
            player_id=player_id,
            full_name=player_data.get("full_name", ""),
            first_name=player_data.get("first_name", ""),
            last_name=player_data.get("last_name", ""),
            team=player_data.get("team"),
            position=player_data.get("position", ""),
            sport=sport,
            status=player_data.get("status", ""),
            injury_status=player_data.get("injury_status"),
            age=player_data.get("age"),
            years_exp=player_data.get("years_exp"),
        )

    async def get_players_by_ids(
        self,
        player_ids: list[str],
        sport: str = "nfl",
    ) -> list[SleeperPlayer]:
        """Get multiple players by their IDs."""
        players = await self.get_all_players(sport)
        result = []

        for player_id in player_ids:
            player_data = players.get(player_id)
            if player_data:
                result.append(
                    SleeperPlayer(
                        player_id=player_id,
                        full_name=player_data.get("full_name", ""),
                        first_name=player_data.get("first_name", ""),
                        last_name=player_data.get("last_name", ""),
                        team=player_data.get("team"),
                        position=player_data.get("position", ""),
                        sport=sport,
                        status=player_data.get("status", ""),
                        injury_status=player_data.get("injury_status"),
                        age=player_data.get("age"),
                        years_exp=player_data.get("years_exp"),
                    )
                )

        return result

    # =========================================================================
    # Trending Players
    # =========================================================================

    async def get_trending_players(
        self,
        sport: str = "nfl",
        trend_type: str = "add",  # "add" or "drop"
        limit: int = 25,
    ) -> list[dict]:
        """
        Get trending players (most added/dropped).

        Args:
            sport: Sport key
            trend_type: "add" for most added, "drop" for most dropped
            limit: Number of players to return (max 50)

        Returns:
            List of dicts with player_id and count
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{SLEEPER_API}/players/{sport}/trending/{trend_type}",
                params={"lookback_hours": 24, "limit": min(limit, 50)},
            )

            if response.status_code == 200:
                return response.json() or []

        except httpx.HTTPError:
            pass

        return []

    # =========================================================================
    # Helper: Roster with Player Details
    # =========================================================================

    async def get_roster_with_players(
        self,
        league_id: str,
        user_id: str,
        sport: str = "nfl",
    ) -> list[SleeperPlayer]:
        """
        Get a user's roster with full player details.

        Convenience method that combines roster + player lookup.
        """
        roster = await self.get_user_roster(league_id, user_id)

        if not roster:
            return []

        return await self.get_players_by_ids(roster.players, sport)


# Singleton instance
sleeper_service = SleeperService()
