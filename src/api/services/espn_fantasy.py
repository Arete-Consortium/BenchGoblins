"""
ESPN Fantasy API Service — Authenticated access to user's fantasy leagues.

Implements OAuth 2.0 flow for ESPN Fantasy Sports.
Fetches leagues, rosters, and team data with user authentication.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger("benchgoblins.espn_fantasy")

# ESPN OAuth endpoints
ESPN_AUTH_URL = "https://www.espn.com/login"
ESPN_TOKEN_URL = "https://registerdisney.go.com/jgc/v6/client/ESPN-ONESITE.WEB-PROD/api-key"
ESPN_FANTASY_API = "https://lm-api-reads.fantasy.espn.com/apis/v3"
ESPN_FANTASY_V2 = "https://fantasy.espn.com/apis/v3/games"

# Sport to ESPN fantasy game key
FANTASY_SPORT_KEYS = {
    "nba": "fba",  # Fantasy Basketball
    "nfl": "ffl",  # Fantasy Football
    "mlb": "flb",  # Fantasy Baseball
    "nhl": "fhl",  # Fantasy Hockey
    "soccer": "fsc",  # Fantasy Soccer
}


@dataclass
class ESPNCredentials:
    """User's ESPN authentication tokens."""

    swid: str  # ESPN User ID cookie
    espn_s2: str  # ESPN Session token
    expires_at: datetime | None = None


@dataclass
class FantasyLeague:
    """ESPN Fantasy League information."""

    id: str
    name: str
    sport: str
    season: int
    team_count: int
    scoring_type: str
    user_team_id: int | None = None
    user_team_name: str | None = None


@dataclass
class FantasyTeam:
    """ESPN Fantasy Team (user's team in a league)."""

    id: int
    name: str
    owner: str
    owner_id: str
    league_id: str
    sport: str


@dataclass
class RosterPlayer:
    """Player on a fantasy roster."""

    player_id: str
    espn_id: str
    name: str
    position: str
    team: str
    lineup_slot: str  # 'BENCH', 'STARTER', 'IR', etc.
    acquisition_type: str  # 'DRAFT', 'ADD', 'TRADE'
    projected_points: float | None = None
    actual_points: float | None = None


class ESPNFantasyService:
    """
    ESPN Fantasy API client with OAuth support.

    ESPN uses cookie-based authentication with two key cookies:
    - SWID: User identifier
    - espn_s2: Session token (expires ~1 year)

    Users must provide these cookies from their ESPN account.
    To get them:
    1. Log into ESPN Fantasy
    2. Open browser DevTools > Application > Cookies
    3. Copy SWID and espn_s2 values
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; BenchGoblin/1.0)",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _auth_cookies(self, creds: ESPNCredentials) -> dict[str, str]:
        """Build authentication cookies."""
        return {
            "SWID": creds.swid,
            "espn_s2": creds.espn_s2,
        }

    # =========================================================================
    # League Discovery
    # =========================================================================

    async def get_user_leagues(
        self, creds: ESPNCredentials, sport: str | None = None
    ) -> list[FantasyLeague]:
        """
        Fetch all fantasy leagues for the authenticated user.

        Args:
            creds: User's ESPN credentials
            sport: Optional filter by sport ('nba', 'nfl', etc.)

        Returns:
            List of FantasyLeague objects
        """
        client = await self._get_client()
        leagues = []

        # Determine which sports to query
        sports_to_check = [sport] if sport else list(FANTASY_SPORT_KEYS.keys())

        for sport_key in sports_to_check:
            if sport_key not in FANTASY_SPORT_KEYS:
                continue

            game_key = FANTASY_SPORT_KEYS[sport_key]

            try:
                # ESPN Fantasy API endpoint for user's leagues
                # This returns leagues where the user is a member
                url = f"{ESPN_FANTASY_V2}/{game_key}/seasons/2025"
                params = {
                    "view": "mSettings",
                }

                response = await client.get(
                    url,
                    params=params,
                    cookies=self._auth_cookies(creds),
                )

                if response.status_code == 200:
                    data = response.json()
                    # Parse league data
                    if isinstance(data, dict) and "settings" in data:
                        league = self._parse_league(data, sport_key)
                        if league:
                            leagues.append(league)
                    elif isinstance(data, list):
                        for league_data in data:
                            league = self._parse_league(league_data, sport_key)
                            if league:
                                leagues.append(league)

            except httpx.HTTPError as e:
                logger.warning("ESPN Fantasy API error for %s: %s", sport_key, e)
                continue

        return leagues

    def _parse_league(self, data: dict, sport: str) -> FantasyLeague | None:
        """Parse league data from ESPN API response."""
        try:
            settings = data.get("settings", {})
            return FantasyLeague(
                id=str(data.get("id", "")),
                name=settings.get("name", "Unknown League"),
                sport=sport,
                season=data.get("seasonId", 2025),
                team_count=settings.get("size", 0),
                scoring_type=settings.get("scoringSettings", {}).get("scoringType", "STANDARD"),
            )
        except (KeyError, TypeError):
            return None

    # =========================================================================
    # League Details
    # =========================================================================

    async def get_league_details(
        self, creds: ESPNCredentials, league_id: str, sport: str, season: int = 2025
    ) -> dict | None:
        """
        Fetch detailed league information including teams.

        Args:
            creds: User's ESPN credentials
            league_id: ESPN league ID
            sport: Sport key ('nba', 'nfl', etc.)
            season: Season year

        Returns:
            League details dict or None
        """
        if sport not in FANTASY_SPORT_KEYS:
            return None

        client = await self._get_client()
        game_key = FANTASY_SPORT_KEYS[sport]

        url = f"{ESPN_FANTASY_V2}/{game_key}/seasons/{season}/segments/0/leagues/{league_id}"
        params = {
            "view": ["mTeam", "mRoster", "mSettings", "mMatchup"],
        }

        try:
            response = await client.get(
                url,
                params=params,
                cookies=self._auth_cookies(creds),
            )

            if response.status_code == 200:
                return response.json()

        except httpx.HTTPError as e:
            logger.warning("Error fetching ESPN league %s: %s", league_id, e)

        return None

    # =========================================================================
    # Roster Sync
    # =========================================================================

    async def get_roster(
        self,
        creds: ESPNCredentials,
        league_id: str,
        team_id: int,
        sport: str,
        season: int = 2025,
    ) -> list[RosterPlayer]:
        """
        Fetch roster for a specific team in a league.

        Args:
            creds: User's ESPN credentials
            league_id: ESPN league ID
            team_id: Team ID within the league
            sport: Sport key
            season: Season year

        Returns:
            List of RosterPlayer objects
        """
        if sport not in FANTASY_SPORT_KEYS:
            return []

        client = await self._get_client()
        game_key = FANTASY_SPORT_KEYS[sport]

        url = f"{ESPN_FANTASY_V2}/{game_key}/seasons/{season}/segments/0/leagues/{league_id}"
        params = {
            "forTeamId": team_id,
            "view": ["mRoster", "mTeam"],
        }

        try:
            response = await client.get(
                url,
                params=params,
                cookies=self._auth_cookies(creds),
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_roster(data, team_id, sport)

        except httpx.HTTPError as e:
            logger.warning("Error fetching ESPN roster for team %d: %s", team_id, e)

        return []

    def _parse_roster(self, data: dict, team_id: int, sport: str) -> list[RosterPlayer]:
        """Parse roster data from ESPN API response."""
        players = []

        teams = data.get("teams", [])
        team_data = None

        for team in teams:
            if team.get("id") == team_id:
                team_data = team
                break

        if not team_data:
            return []

        roster = team_data.get("roster", {})
        entries = roster.get("entries", [])

        for entry in entries:
            player_pool_entry = entry.get("playerPoolEntry", {})
            player = player_pool_entry.get("player", {})

            if not player:
                continue

            # Get position from eligibleSlots
            position = self._get_primary_position(player.get("eligibleSlots", []), sport)

            players.append(
                RosterPlayer(
                    player_id=str(player.get("id", "")),
                    espn_id=str(player.get("id", "")),
                    name=player.get("fullName", "Unknown"),
                    position=position,
                    team=player.get("proTeamId", "FA"),
                    lineup_slot=self._slot_to_name(entry.get("lineupSlotId", 0), sport),
                    acquisition_type=entry.get("acquisitionType", "UNKNOWN"),
                    projected_points=player.get("stats", [{}])[0].get("projectedPoints")
                    if player.get("stats")
                    else None,
                )
            )

        return players

    def _get_primary_position(self, eligible_slots: list[int], sport: str) -> str:
        """Convert ESPN slot IDs to position string."""
        # ESPN position slot mappings vary by sport
        nba_positions = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "UTIL"}
        nfl_positions = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K", 23: "FLEX"}
        mlb_positions = {
            0: "C",
            1: "1B",
            2: "2B",
            3: "3B",
            4: "SS",
            5: "LF",
            6: "CF",
            7: "RF",
            10: "DH",
            14: "SP",
            15: "RP",
        }
        nhl_positions = {0: "C", 1: "LW", 2: "RW", 3: "D", 4: "G"}

        positions = {
            "nba": nba_positions,
            "nfl": nfl_positions,
            "mlb": mlb_positions,
            "nhl": nhl_positions,
        }

        sport_positions = positions.get(sport, {})

        for slot_id in eligible_slots:
            if slot_id in sport_positions:
                return sport_positions[slot_id]

        return "UTIL"

    def _slot_to_name(self, slot_id: int, sport: str) -> str:
        """Convert lineup slot ID to readable name."""
        # Common bench/IR slots
        if slot_id == 20 or slot_id == 21:  # Bench slots
            return "BENCH"
        if slot_id == 13:  # IR
            return "IR"

        return self._get_primary_position([slot_id], sport)

    # =========================================================================
    # User Info
    # =========================================================================

    async def verify_credentials(self, creds: ESPNCredentials) -> bool:
        """
        Verify that credentials are valid.

        Returns:
            True if credentials work, False otherwise
        """
        # Try to fetch a public endpoint with auth
        client = await self._get_client()

        # Use NFL fantasy as a test (most common)
        url = f"{ESPN_FANTASY_V2}/ffl/seasons/2025"

        try:
            response = await client.get(
                url,
                cookies=self._auth_cookies(creds),
            )
            # If we get 200 or 401, we at least connected
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_user_id(self, creds: ESPNCredentials) -> str | None:
        """
        Get the user ID from credentials.

        The SWID cookie contains the user ID in format {GUID}.
        """
        swid = creds.swid.strip("{}")
        return swid if swid else None


# Singleton instance
espn_fantasy_service = ESPNFantasyService()
