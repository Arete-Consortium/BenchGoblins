"""
Yahoo Fantasy API Service — OAuth-authenticated access to Yahoo Fantasy leagues.

Yahoo Fantasy uses OAuth 2.0 for API access. Users need to:
1. Register an app at https://developer.yahoo.com/apps/
2. Configure redirect URI
3. Complete OAuth flow to get access tokens

API Docs: https://developer.yahoo.com/fantasysports/guide/
"""

import os
import time
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

import httpx

# Yahoo API configuration
YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# Yahoo game keys for current seasons (updated annually)
YAHOO_GAME_KEYS = {
    "nfl": "449",  # 2024 NFL
    "nba": "428",  # 2024-25 NBA
    "mlb": "431",  # 2024 MLB
    "nhl": "427",  # 2024-25 NHL
}


class YahooSport(str, Enum):
    """Sports supported by Yahoo Fantasy."""

    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"
    NHL = "nhl"


@dataclass
class YahooToken:
    """OAuth token response from Yahoo."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    expires_at: float  # Unix timestamp when token expires


@dataclass
class YahooUser:
    """Yahoo user profile."""

    guid: str
    nickname: str | None
    email: str | None


@dataclass
class YahooLeague:
    """Yahoo fantasy league information."""

    league_key: str
    league_id: str
    name: str
    sport: str
    season: str
    num_teams: int
    scoring_type: str
    current_week: int | None
    start_week: int | None
    end_week: int | None
    draft_status: str | None


@dataclass
class YahooTeam:
    """Yahoo fantasy team (user's team in a league)."""

    team_key: str
    team_id: str
    name: str
    logo_url: str | None
    waiver_priority: int | None
    faab_balance: int | None
    number_of_moves: int
    number_of_trades: int


@dataclass
class YahooPlayer:
    """Yahoo fantasy player."""

    player_key: str
    player_id: str
    name: str
    team_abbrev: str | None
    position: str
    status: str  # Active, IR, etc.
    injury_status: str | None
    bye_week: int | None
    headshot_url: str | None


class YahooService:
    """
    Yahoo Fantasy API client with OAuth 2.0 support.

    Usage:
        service = YahooService(client_id, client_secret)

        # Step 1: Get authorization URL
        auth_url = service.get_auth_url(redirect_uri)

        # Step 2: After user authorizes, exchange code for tokens
        tokens = await service.exchange_code(code, redirect_uri)

        # Step 3: Use tokens to make API calls
        leagues = await service.get_user_leagues(tokens.access_token)
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.client_id = client_id or os.getenv("YAHOO_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("YAHOO_CLIENT_SECRET", "")
        self._client: httpx.AsyncClient | None = None

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
    # OAuth 2.0 Flow
    # =========================================================================

    def get_auth_url(self, redirect_uri: str, state: str | None = None) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: URL to redirect after authorization
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "language": "en-us",
        }

        if state:
            params["state"] = state

        return f"{YAHOO_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> YahooToken | None:
        """
        Exchange authorization code for access tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Same redirect URI used in auth request

        Returns:
            YahooToken or None if exchange fails
        """
        client = await self._get_client()

        try:
            response = await client.post(
                YAHOO_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 3600)
                return YahooToken(
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", ""),
                    token_type=data.get("token_type", "bearer"),
                    expires_in=expires_in,
                    expires_at=time.time() + expires_in,
                )
            else:
                print(f"Yahoo OAuth error: {response.status_code} - {response.text}")

        except httpx.HTTPError as e:
            print(f"Yahoo OAuth error: {e}")

        return None

    async def refresh_token(self, refresh_token: str) -> YahooToken | None:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Refresh token from previous token response

        Returns:
            New YahooToken or None if refresh fails
        """
        client = await self._get_client()

        try:
            response = await client.post(
                YAHOO_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 3600)
                return YahooToken(
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", refresh_token),
                    token_type=data.get("token_type", "bearer"),
                    expires_in=expires_in,
                    expires_at=time.time() + expires_in,
                )

        except httpx.HTTPError as e:
            print(f"Yahoo token refresh error: {e}")

        return None

    # =========================================================================
    # API Helpers
    # =========================================================================

    async def _api_request(
        self,
        access_token: str,
        endpoint: str,
        params: dict | None = None,
    ) -> dict | None:
        """Make authenticated API request to Yahoo Fantasy."""
        client = await self._get_client()

        try:
            # Request JSON format
            url = f"{YAHOO_API_BASE}/{endpoint}"
            if "?" in url:
                url += "&format=json"
            else:
                url += "?format=json"

            response = await client.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print("Yahoo API: Token expired or invalid")
            else:
                print(f"Yahoo API error: {response.status_code} - {response.text}")

        except httpx.HTTPError as e:
            print(f"Yahoo API error: {e}")

        return None

    # =========================================================================
    # User Information
    # =========================================================================

    async def get_user_info(self, access_token: str) -> YahooUser | None:
        """Get authenticated user's profile."""
        data = await self._api_request(
            access_token,
            "users;use_login=1",
        )

        if not data:
            return None

        try:
            users = data.get("fantasy_content", {}).get("users", {})
            user_data = users.get("0", {}).get("user", [[{}]])[0]

            return YahooUser(
                guid=user_data.get("guid", ""),
                nickname=user_data.get("nickname"),
                email=user_data.get("email"),
            )

        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing Yahoo user: {e}")
            return None

    # =========================================================================
    # League Discovery
    # =========================================================================

    async def get_user_leagues(
        self,
        access_token: str,
        sport: str | None = None,
        season: str | None = None,
    ) -> list[YahooLeague]:
        """
        Get all leagues for the authenticated user.

        Args:
            access_token: Valid OAuth access token
            sport: Optional sport filter (nfl, nba, etc.)
            season: Optional season filter

        Returns:
            List of YahooLeague objects
        """
        # Build endpoint - get all games user is in
        endpoint = "users;use_login=1/games"

        if sport:
            game_key = YAHOO_GAME_KEYS.get(sport)
            if game_key:
                endpoint += f";game_keys={game_key}"

        endpoint += "/leagues"

        data = await self._api_request(access_token, endpoint)

        if not data:
            return []

        leagues = []

        try:
            users = data.get("fantasy_content", {}).get("users", {})
            user = users.get("0", {}).get("user", [])

            if len(user) < 2:
                return []

            games = user[1].get("games", {})

            # Iterate through games
            game_idx = 0
            while True:
                game_data = games.get(str(game_idx))
                if not game_data:
                    break

                game = game_data.get("game", [[{}], {}])
                game_info = game[0] if isinstance(game[0], dict) else {}
                game_leagues = game[1].get("leagues", {}) if len(game) > 1 else {}

                # Get sport from game info
                game_sport = game_info.get("code", "").lower()

                # Iterate through leagues in this game
                league_idx = 0
                while True:
                    league_data = game_leagues.get(str(league_idx))
                    if not league_data:
                        break

                    league_info = league_data.get("league", [[{}]])[0]
                    leagues.append(self._parse_league(league_info, game_sport))

                    league_idx += 1

                game_idx += 1

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error parsing Yahoo leagues: {e}")

        return leagues

    def _parse_league(self, data: dict, sport: str) -> YahooLeague:
        """Parse league data from API response."""
        return YahooLeague(
            league_key=data.get("league_key", ""),
            league_id=data.get("league_id", ""),
            name=data.get("name", "Unknown League"),
            sport=sport or data.get("game_code", "").lower(),
            season=data.get("season", ""),
            num_teams=data.get("num_teams", 0),
            scoring_type=data.get("scoring_type", ""),
            current_week=data.get("current_week"),
            start_week=data.get("start_week"),
            end_week=data.get("end_week"),
            draft_status=data.get("draft_status"),
        )

    # =========================================================================
    # League Details
    # =========================================================================

    async def get_league(
        self,
        access_token: str,
        league_key: str,
    ) -> YahooLeague | None:
        """Get details for a specific league."""
        data = await self._api_request(
            access_token,
            f"league/{league_key}",
        )

        if not data:
            return None

        try:
            league_data = data.get("fantasy_content", {}).get("league", [[{}]])[0]
            return self._parse_league(league_data, "")

        except (KeyError, TypeError, IndexError):
            return None

    async def get_league_standings(
        self,
        access_token: str,
        league_key: str,
    ) -> list[dict]:
        """Get league standings."""
        data = await self._api_request(
            access_token,
            f"league/{league_key}/standings",
        )

        if not data:
            return []

        standings = []

        try:
            league = data.get("fantasy_content", {}).get("league", [])
            if len(league) < 2:
                return []

            teams_data = league[1].get("standings", [[{}], {}])[0].get("teams", {})

            team_idx = 0
            while True:
                team_data = teams_data.get(str(team_idx))
                if not team_data:
                    break

                team_info = team_data.get("team", [[{}], {}])
                if len(team_info) >= 2:
                    basic = team_info[0][0] if isinstance(team_info[0], list) else team_info[0]
                    standings_info = team_info[1].get("team_standings", {})

                    standings.append(
                        {
                            "team_key": basic.get("team_key", ""),
                            "team_name": basic.get("name", ""),
                            "rank": standings_info.get("rank", 0),
                            "wins": standings_info.get("outcome_totals", {}).get("wins", 0),
                            "losses": standings_info.get("outcome_totals", {}).get("losses", 0),
                            "ties": standings_info.get("outcome_totals", {}).get("ties", 0),
                            "points_for": standings_info.get("points_for", 0),
                            "points_against": standings_info.get("points_against", 0),
                        }
                    )

                team_idx += 1

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error parsing standings: {e}")

        return standings

    # =========================================================================
    # Teams and Rosters
    # =========================================================================

    async def get_user_teams(
        self,
        access_token: str,
        league_key: str,
    ) -> list[YahooTeam]:
        """Get user's teams in a specific league."""
        data = await self._api_request(
            access_token,
            f"league/{league_key}/teams;team_keys={league_key}.t.1",
        )

        # Actually get user's teams
        data = await self._api_request(
            access_token,
            "users;use_login=1/teams",
        )

        if not data:
            return []

        teams = []

        try:
            users = data.get("fantasy_content", {}).get("users", {})
            user = users.get("0", {}).get("user", [])

            if len(user) < 2:
                return []

            teams_data = user[1].get("teams", {})

            team_idx = 0
            while True:
                team_data = teams_data.get(str(team_idx))
                if not team_data:
                    break

                team_info = team_data.get("team", [[{}]])
                basic = team_info[0][0] if isinstance(team_info[0], list) else team_info[0]

                # Filter by league if specified
                if (
                    league_key
                    and basic.get("team_key", "").split(".t.")[0]
                    != league_key.split(".l.")[0] + ".l." + league_key.split(".l.")[1]
                ):
                    team_idx += 1
                    continue

                teams.append(self._parse_team(basic))
                team_idx += 1

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error parsing teams: {e}")

        return teams

    def _parse_team(self, data: dict) -> YahooTeam:
        """Parse team data from API response."""
        return YahooTeam(
            team_key=data.get("team_key", ""),
            team_id=data.get("team_id", ""),
            name=data.get("name", "Unknown Team"),
            logo_url=data.get("team_logos", [{}])[0].get("url") if data.get("team_logos") else None,
            waiver_priority=data.get("waiver_priority"),
            faab_balance=data.get("faab_balance"),
            number_of_moves=data.get("number_of_moves", 0),
            number_of_trades=data.get("number_of_trades", 0),
        )

    async def get_team_roster(
        self,
        access_token: str,
        team_key: str,
        week: int | None = None,
    ) -> list[YahooPlayer]:
        """
        Get roster for a specific team.

        Args:
            access_token: Valid OAuth access token
            team_key: Yahoo team key (e.g., "449.l.123456.t.1")
            week: Optional week number to get roster for

        Returns:
            List of YahooPlayer objects
        """
        endpoint = f"team/{team_key}/roster"
        if week:
            endpoint += f";week={week}"

        endpoint += "/players"

        data = await self._api_request(access_token, endpoint)

        if not data:
            return []

        players = []

        try:
            team = data.get("fantasy_content", {}).get("team", [])
            if len(team) < 2:
                return []

            roster = team[1].get("roster", {})
            players_data = roster.get("0", {}).get("players", {})

            player_idx = 0
            while True:
                player_data = players_data.get(str(player_idx))
                if not player_data:
                    break

                player_info = player_data.get("player", [[{}]])
                basic = player_info[0][0] if isinstance(player_info[0], list) else player_info[0]
                players.append(self._parse_player(basic))
                player_idx += 1

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error parsing roster: {e}")

        return players

    def _parse_player(self, data: dict) -> YahooPlayer:
        """Parse player data from API response."""
        # Get name from nested structure
        name_data = data.get("name", {})
        if isinstance(name_data, dict):
            full_name = name_data.get("full", "")
        else:
            full_name = str(name_data) if name_data else ""

        # Get position
        eligible_positions = data.get("eligible_positions", [])
        if isinstance(eligible_positions, list) and eligible_positions:
            position = (
                eligible_positions[0].get("position", "")
                if isinstance(eligible_positions[0], dict)
                else str(eligible_positions[0])
            )
        else:
            position = data.get("display_position", "")

        return YahooPlayer(
            player_key=data.get("player_key", ""),
            player_id=data.get("player_id", ""),
            name=full_name or data.get("full", ""),
            team_abbrev=data.get("editorial_team_abbr"),
            position=position,
            status=data.get("status", ""),
            injury_status=data.get("status") if data.get("status") not in ["", "O", "IR"] else None,
            bye_week=data.get("bye_weeks", {}).get("week")
            if isinstance(data.get("bye_weeks"), dict)
            else None,
            headshot_url=data.get("headshot", {}).get("url")
            if isinstance(data.get("headshot"), dict)
            else None,
        )

    # =========================================================================
    # Player Search
    # =========================================================================

    async def search_players(
        self,
        access_token: str,
        query: str,
        sport: str = "nfl",
        limit: int = 10,
    ) -> list[YahooPlayer]:
        """
        Search for players by name.

        Args:
            access_token: Valid OAuth access token
            query: Player name to search
            sport: Sport key
            limit: Max results to return

        Returns:
            List of matching YahooPlayer objects
        """
        game_key = YAHOO_GAME_KEYS.get(sport)
        if not game_key:
            return []

        endpoint = f"game/{game_key}/players;search={query};count={limit}"

        data = await self._api_request(access_token, endpoint)

        if not data:
            return []

        players = []

        try:
            game = data.get("fantasy_content", {}).get("game", [])
            if len(game) < 2:
                return []

            players_data = game[1].get("players", {})

            player_idx = 0
            while True:
                player_data = players_data.get(str(player_idx))
                if not player_data:
                    break

                player_info = player_data.get("player", [[{}]])
                basic = player_info[0][0] if isinstance(player_info[0], list) else player_info[0]
                players.append(self._parse_player(basic))
                player_idx += 1

        except (KeyError, TypeError, IndexError) as e:
            print(f"Error parsing player search: {e}")

        return players[:limit]

    # =========================================================================
    # Matchups
    # =========================================================================

    async def get_team_matchup(
        self,
        access_token: str,
        team_key: str,
        week: int | None = None,
    ) -> dict | None:
        """Get current matchup for a team."""
        endpoint = f"team/{team_key}/matchups"
        if week:
            endpoint += f";weeks={week}"

        data = await self._api_request(access_token, endpoint)

        if not data:
            return None

        try:
            team = data.get("fantasy_content", {}).get("team", [])
            if len(team) < 2:
                return None

            matchups = team[1].get("matchups", {})
            matchup_data = matchups.get("0", {}).get("matchup", {})

            return {
                "week": matchup_data.get("week"),
                "status": matchup_data.get("status"),
                "is_playoffs": matchup_data.get("is_playoffs") == "1",
                "is_consolation": matchup_data.get("is_consolation") == "1",
            }

        except (KeyError, TypeError, IndexError):
            return None


# Singleton instance
yahoo_service = YahooService()
