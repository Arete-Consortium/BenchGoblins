"""
Sports Reference Scrapers — Basketball Reference & Pro Football Reference.

Fetches advanced stats not available through ESPN's public API.
Rate-limited to respect robots.txt (3-second delay between requests).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

BBALL_REF_BASE = "https://www.basketball-reference.com"
PFR_BASE = "https://www.pro-football-reference.com"

# Respectful rate limiting: 3 seconds between requests per robots.txt
_RATE_LIMIT_SECONDS = 3.0
_last_request_time: float = 0.0

_USER_AGENT = "GameSpace/0.2.0 (Fantasy Sports Analytics; +https://github.com/AreteDriver/GameSpace)"


@dataclass
class AdvancedNBAStats:
    """Advanced stats from Basketball Reference."""

    player_name: str
    season: str
    # Advanced
    per: float = 0.0  # Player Efficiency Rating
    true_shooting_pct: float = 0.0
    win_shares: float = 0.0
    bpm: float = 0.0  # Box Plus/Minus
    vorp: float = 0.0  # Value Over Replacement Player
    offensive_rating: float = 0.0
    defensive_rating: float = 0.0
    # Per-100 possessions
    pts_per_100: float = 0.0
    ast_per_100: float = 0.0
    reb_per_100: float = 0.0


@dataclass
class AdvancedNFLStats:
    """Advanced stats from Pro Football Reference."""

    player_name: str
    season: str
    # QB
    passer_rating: float = 0.0
    qbr: float = 0.0  # ESPN Total QBR
    any_a: float = 0.0  # Adjusted Net Yards per Attempt
    # RB/WR
    yards_per_touch: float = 0.0
    catch_pct: float = 0.0
    yards_after_catch: float = 0.0
    # General
    approximate_value: int = 0  # Pro Football Reference AV
    fantasy_points_ppr: float = 0.0


async def _rate_limited_get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    """Make a rate-limited GET request."""
    global _last_request_time
    now = asyncio.get_event_loop().time()
    elapsed = now - _last_request_time
    if elapsed < _RATE_LIMIT_SECONDS:
        await asyncio.sleep(_RATE_LIMIT_SECONDS - elapsed)

    try:
        response = await client.get(url, headers={"User-Agent": _USER_AGENT})
        _last_request_time = asyncio.get_event_loop().time()
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Reference scraper error for {url}: {e}")
        return None


def _parse_float(text: str) -> float:
    """Parse a float from HTML text, returning 0.0 on failure."""
    try:
        return float(text.strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_int(text: str) -> int:
    try:
        return int(text.strip())
    except (ValueError, TypeError):
        return 0


def _extract_stat(html: str, stat_name: str) -> str:
    """Extract a stat value from a Basketball/Football Reference HTML row."""
    pattern = rf'data-stat="{stat_name}"[^>]*>([^<]*)<'
    match = re.search(pattern, html)
    return match.group(1) if match else ""


class BasketballReferenceService:
    """Scrapes advanced NBA stats from Basketball Reference."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    async def get_advanced_stats(
        self, player_slug: str, season: str = "2025"
    ) -> AdvancedNBAStats | None:
        """
        Fetch advanced stats for a player.

        player_slug: Basketball Reference URL slug (e.g., "jamesle01" for LeBron)
        season: End year of season (e.g., "2025" for 2024-25)
        """
        url = f"{BBALL_REF_BASE}/players/{player_slug[0]}/{player_slug}.html"
        resp = await _rate_limited_get(self.client, url)
        if not resp:
            return None

        html = resp.text
        stats = AdvancedNBAStats(player_name=player_slug, season=season)

        # Find the advanced stats table for the specified season
        # Look for the row with the matching season
        season_display = f"{int(season) - 1}-{season[-2:]}"  # e.g., "2024-25"
        season_pattern = rf'<tr[^>]*id="advanced\.{season}"[^>]*>(.*?)</tr>'
        match = re.search(season_pattern, html, re.DOTALL)
        if not match:
            return stats  # Return empty stats if season not found

        row = match.group(1)
        stats.per = _parse_float(_extract_stat(row, "per"))
        stats.true_shooting_pct = _parse_float(_extract_stat(row, "ts_pct"))
        stats.win_shares = _parse_float(_extract_stat(row, "ws"))
        stats.bpm = _parse_float(_extract_stat(row, "bpm"))
        stats.vorp = _parse_float(_extract_stat(row, "vorp"))
        stats.offensive_rating = _parse_float(_extract_stat(row, "off_rtg"))
        stats.defensive_rating = _parse_float(_extract_stat(row, "def_rtg"))

        return stats

    async def search_player_slug(self, name: str) -> str | None:
        """
        Search for a player's URL slug on Basketball Reference.

        Returns slug like "jamesle01" or None.
        """
        search_url = f"{BBALL_REF_BASE}/search/search.fcgi?search={name.replace(' ', '+')}"
        resp = await _rate_limited_get(self.client, search_url)
        if not resp:
            return None

        # If redirected directly to a player page
        if "/players/" in str(resp.url):
            # Extract slug from URL like /players/j/jamesle01.html
            match = re.search(r"/players/\w/(\w+)\.html", str(resp.url))
            return match.group(1) if match else None

        # Search results page — find first player link
        pattern = r'/players/\w/(\w+)\.html'
        match = re.search(pattern, resp.text)
        return match.group(1) if match else None


class ProFootballReferenceService:
    """Scrapes advanced NFL stats from Pro Football Reference."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    async def close(self):
        await self.client.aclose()

    async def get_advanced_stats(
        self, player_slug: str, season: str = "2024"
    ) -> AdvancedNFLStats | None:
        """
        Fetch advanced stats for a player.

        player_slug: PFR URL slug (e.g., "MahoPa00" for Mahomes)
        season: Year string (e.g., "2024")
        """
        first_letter = player_slug[0]
        url = f"{PFR_BASE}/players/{first_letter}/{player_slug}.htm"
        resp = await _rate_limited_get(self.client, url)
        if not resp:
            return None

        html = resp.text
        stats = AdvancedNFLStats(player_name=player_slug, season=season)

        # Find the passing table row for the season
        season_pattern = rf'<tr[^>]*id="passing\.{season}"[^>]*>(.*?)</tr>'
        match = re.search(season_pattern, html, re.DOTALL)
        if match:
            row = match.group(1)
            stats.passer_rating = _parse_float(_extract_stat(row, "pass_rating"))
            stats.qbr = _parse_float(_extract_stat(row, "qbr"))
            stats.any_a = _parse_float(_extract_stat(row, "pass_adj_net_yds_per_att"))
            stats.approximate_value = _parse_int(_extract_stat(row, "av"))
            return stats

        # Try rushing/receiving table
        for table in ("rushing_and_receiving", "receiving_and_rushing"):
            season_pattern = rf'<tr[^>]*id="{table}\.{season}"[^>]*>(.*?)</tr>'
            match = re.search(season_pattern, html, re.DOTALL)
            if match:
                row = match.group(1)
                stats.catch_pct = _parse_float(_extract_stat(row, "catch_pct"))
                stats.yards_after_catch = _parse_float(_extract_stat(row, "rec_yac"))
                stats.approximate_value = _parse_int(_extract_stat(row, "av"))
                return stats

        return stats

    async def search_player_slug(self, name: str) -> str | None:
        """
        Search for a player's URL slug on PFR.

        Returns slug like "MahoPa00" or None.
        """
        search_url = f"{PFR_BASE}/search/search.fcgi?search={name.replace(' ', '+')}"
        resp = await _rate_limited_get(self.client, search_url)
        if not resp:
            return None

        if "/players/" in str(resp.url):
            match = re.search(r"/players/\w/(\w+)\.htm", str(resp.url))
            return match.group(1) if match else None

        pattern = r'/players/\w/(\w+)\.htm'
        match = re.search(pattern, resp.text)
        return match.group(1) if match else None


# Module-level singletons
bball_ref_service = BasketballReferenceService()
pfr_service = ProFootballReferenceService()
