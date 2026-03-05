"""
Goblin Verdict Service — Weekly lineup analysis with swap recommendations.

Pre-generates verdicts for all users (Thursday AM for NFL) and caches in Redis.
Falls back to on-demand generation if no cached verdict exists.

The Goblin is a brutally honest fantasy analyst persona powered by Claude.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RiskMode(str, Enum):
    FLOOR = "floor"
    MEDIAN = "median"
    CEILING = "ceiling"


class PlayerBrief(BaseModel):
    """Condensed player info for verdict display."""

    name: str
    position: str
    team: str
    opponent: str = ""
    projected_points: float = 0.0
    goblin_score: float = 0.0
    injury_flag: str | None = None
    trend: str = "stable"  # up, down, stable


class SwapRecommendation(BaseModel):
    """A single start/bench swap recommendation."""

    bench_player: str
    start_player: str
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    urgency: str = "recommended"  # critical, recommended, optional


class GoblinVerdict(BaseModel):
    """Full Goblin Verdict for a user's lineup."""

    team_name: str = ""
    week: int = 0
    season: int = 2025
    risk_mode: RiskMode = RiskMode.MEDIAN
    swaps: list[SwapRecommendation] = Field(default_factory=list)
    verdict_headline: str = ""
    overall_outlook: str = ""
    generated_at: str = ""
    cached: bool = False


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

GOBLIN_BASE_PERSONA = """You are the Goblin — a brutally honest, sharply intelligent fantasy sports analyst.
Your personality: direct, a little savage, but always right. You don't hedge.
You give verdicts, not suggestions.

Rules:
- Never say "it depends" — always commit to a recommendation
- Lead with the most important swap first
- Use plain language. No jargon dumps.
- Keep reasoning tight: 2-3 sentences max per swap
- Flag injury risks explicitly
- Confidence scores are honest — if it's a coin flip, say 55%, not 75%"""


def build_verdict_prompt(context: str, risk_mode: str) -> str:
    """Build the Claude prompt for verdict generation."""
    risk_instructions = {
        "floor": "Prioritize guaranteed volume and role stability. Avoid volatility. Best for comfortable leads.",
        "median": "Maximize expected value. Balance upside with floor. Standard week.",
        "ceiling": "Maximize upside and spike potential. Accept volatility. User is chasing points.",
    }

    return f"""{GOBLIN_BASE_PERSONA}

RISK MODE: {risk_mode.upper()}
{risk_instructions.get(risk_mode, risk_instructions["median"])}

ROSTER CONTEXT:
{context}

TASK:
Analyze this roster and identify the best swap opportunities (bench a starter, start a bench player).
Return a JSON object with this exact structure:

{{
  "verdict_headline": "one punchy line summarizing the situation",
  "overall_outlook": "1-2 sentences on the team's week outlook",
  "swaps": [
    {{
      "urgency": "critical|recommended|optional",
      "bench_player": "player name to bench",
      "start_player": "player name to start instead",
      "confidence": 0-100,
      "reasoning": "2-3 sentence explanation, Goblin voice"
    }}
  ]
}}

Only include swaps where you're at least 55% confident. Maximum 3 swaps.
If the lineup looks solid, return an empty swaps array with an encouraging headline.
Return ONLY the JSON. No preamble."""


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------


def build_verdict_context(
    league_name: str,
    scoring_format: str,
    week: int,
    season: str,
    starters: list[dict],
    bench: list[dict],
    opponent_name: str = "Unknown",
    opponent_projected: float = 0.0,
    win_probability: float | None = None,
) -> str:
    """
    Build a narrative brief from roster data for the Goblin prompt.

    Each player dict should have: name, position, team, opponent,
    projected_pts, goblin_score, and optionally injury_status.
    """
    starter_lines = []
    for p in starters:
        line = (
            f"{p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) "
            f"vs {p.get('opponent', '?')} | "
            f"Proj: {p.get('projected_pts', 0)} | "
            f"Goblin Score: {p.get('goblin_score', 0)}"
        )
        if p.get("injury_status"):
            line += f" | INJURY: {p['injury_status']}"
        starter_lines.append(line)

    bench_lines = []
    for p in bench:
        line = (
            f"{p['name']} ({p.get('position', '?')}, {p.get('team', '?')}) "
            f"vs {p.get('opponent', '?')} | "
            f"Proj: {p.get('projected_pts', 0)} | "
            f"Goblin Score: {p.get('goblin_score', 0)}"
        )
        if p.get("injury_status"):
            line += f" | INJURY: {p['injury_status']}"
        bench_lines.append(line)

    win_prob_str = f"{win_probability}%" if win_probability is not None else "N/A"

    return f"""LEAGUE CONTEXT:
- League: {league_name}
- Scoring: {scoring_format}
- Week: {week} of {season}

USER'S CURRENT STARTERS:
{chr(10).join(starter_lines) if starter_lines else "(no starters set)"}

USER'S BENCH:
{chr(10).join(bench_lines) if bench_lines else "(empty bench)"}

OPPONENT THIS WEEK: {opponent_name}
Opponent projected score: {opponent_projected}
Win probability (current): {win_prob_str}"""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

# Redis cache TTL: 6 hours
VERDICT_CACHE_TTL = 6 * 60 * 60


class GoblinVerdictService:
    """
    Generates and caches Goblin Verdicts.

    Verdicts are cached in Redis keyed by user_id:risk_mode:week.
    Pre-generation populates the cache; on-demand fills misses.
    """

    async def get_verdict(
        self,
        user_id: str,
        risk_mode: str = "median",
        week: int | None = None,
    ) -> GoblinVerdict | None:
        """
        Get a verdict, preferring cache, falling back to on-demand generation.

        Returns None if generation fails or user has no league data.
        """
        from services.redis import redis_service

        if week is None:
            week = self._current_week()

        cache_key = f"goblin:verdict:{user_id}:{risk_mode}:week{week}"

        # Try cache first
        if redis_service.is_connected:
            try:
                cached = await redis_service._client.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    verdict = GoblinVerdict(**data)
                    verdict.cached = True
                    return verdict
            except Exception:
                logger.debug("Redis cache miss for verdict %s", cache_key)

        # Generate on-demand
        return await self.generate_verdict(user_id, risk_mode, week, cache_key)

    async def generate_verdict(
        self,
        user_id: str,
        risk_mode: str,
        week: int,
        cache_key: str | None = None,
    ) -> GoblinVerdict | None:
        """
        Generate a fresh verdict by assembling context and calling Claude.

        Steps:
        1. Fetch user's league/roster from Sleeper
        2. Enrich players with projections
        3. Build context brief
        4. Call Claude with verdict prompt
        5. Parse response and cache
        """
        from services.sleeper import sleeper_service

        # Look up user's Sleeper league info
        user_data = await self._get_user_league_data(user_id)
        if not user_data:
            return None

        league_id = user_data["sleeper_league_id"]
        sleeper_user_id = user_data["sleeper_user_id"]
        sport = user_data.get("sport", "nfl")

        # Fetch league + roster
        league = await sleeper_service.get_league(league_id)
        if not league:
            return None

        roster = await sleeper_service.get_user_roster(league_id, sleeper_user_id)
        if not roster:
            return None

        # Enrich with player data
        all_players = await sleeper_service.get_all_players(sport)
        starters, bench = self._split_roster(roster, all_players)

        # Get matchup opponent
        matchups = await sleeper_service.get_league_matchups(league_id, week)
        opponent_name, opponent_projected = self._find_opponent(roster.roster_id, matchups)

        # Build scoring format string
        scoring = league.scoring_settings
        scoring_format = (
            "PPR"
            if scoring.get("rec", 0) >= 1
            else "Half-PPR"
            if scoring.get("rec", 0) >= 0.5
            else "Standard"
        )

        # Build context
        context = build_verdict_context(
            league_name=league.name,
            scoring_format=scoring_format,
            week=week,
            season=league.season,
            starters=starters,
            bench=bench,
            opponent_name=opponent_name,
            opponent_projected=opponent_projected,
        )

        # Call Claude
        verdict_data = await self._call_claude(context, risk_mode)
        if not verdict_data:
            return None

        # Build verdict model
        verdict = GoblinVerdict(
            team_name=user_data.get("team_name", "My Team"),
            week=week,
            season=int(league.season) if league.season.isdigit() else 2025,
            risk_mode=RiskMode(risk_mode),
            swaps=[SwapRecommendation(**s) for s in verdict_data.get("swaps", [])],
            verdict_headline=verdict_data.get("verdict_headline", "The Goblin has spoken."),
            overall_outlook=verdict_data.get("overall_outlook", ""),
            generated_at=datetime.now(UTC).isoformat(),
            cached=False,
        )

        # Cache in Redis
        if cache_key:
            await self._cache_verdict(cache_key, verdict)

        return verdict

    async def _get_user_league_data(self, user_id: str) -> dict | None:
        """Look up user's Sleeper league info from DB."""
        from services.database import db_service

        if not db_service.is_configured:
            return None

        try:
            from sqlalchemy import text

            async with db_service.session() as session:
                result = await session.execute(
                    text("""
                        SELECT google_id, sleeper_league_id, sleeper_user_id, name
                        FROM users
                        WHERE google_id = :uid
                          AND sleeper_league_id IS NOT NULL
                    """),
                    {"uid": user_id},
                )
                row = result.first()
                if row:
                    return {
                        "user_id": row[0],
                        "sleeper_league_id": row[1],
                        "sleeper_user_id": row[2],
                        "team_name": row[3] or "My Team",
                        "sport": "nfl",
                    }
        except Exception:
            logger.exception("Failed to fetch user league data for %s", user_id[:8])

        return None

    def _split_roster(
        self,
        roster,
        all_players: dict,
    ) -> tuple[list[dict], list[dict]]:
        """Split a Sleeper roster into enriched starter and bench dicts."""
        starter_ids = set(roster.starters or [])
        starters = []
        bench = []

        for pid in roster.players or []:
            pdata = all_players.get(pid, {})
            if not pdata:
                continue

            player_dict = {
                "name": pdata.get("full_name", f"Player {pid}"),
                "position": pdata.get("position", "?"),
                "team": pdata.get("team", "?"),
                "opponent": "",  # Would need schedule data to populate
                "projected_pts": 0,  # Would need projection source
                "goblin_score": 0,  # Would need scoring engine
                "injury_status": pdata.get("injury_status"),
            }

            if pid in starter_ids:
                starters.append(player_dict)
            else:
                bench.append(player_dict)

        return starters, bench

    def _find_opponent(
        self,
        roster_id: int,
        matchups: list,
    ) -> tuple[str, float]:
        """Find the opponent's name and projected score from matchup data."""
        # Sleeper matchups: two entries share same matchup_id
        my_matchup_id = None
        for m in matchups:
            if m.roster_id == roster_id:
                my_matchup_id = m.matchup_id
                break

        if my_matchup_id is not None:
            for m in matchups:
                if m.matchup_id == my_matchup_id and m.roster_id != roster_id:
                    return f"Roster #{m.roster_id}", m.points

        return "Unknown", 0.0

    async def _call_claude(self, context: str, risk_mode: str) -> dict | None:
        """Call Claude API with the verdict prompt. Returns parsed JSON or None."""
        from services.claude import claude_service

        if not claude_service.is_available:
            logger.warning("Claude not available for verdict generation")
            return None

        prompt = build_verdict_prompt(context, risk_mode)

        try:
            response = await claude_service.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()

            # Parse JSON — handle markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]

            return json.loads(text)

        except json.JSONDecodeError:
            logger.warning("Failed to parse Claude verdict response as JSON")
            return None
        except Exception:
            logger.exception("Claude verdict generation failed")
            return None

    async def _cache_verdict(self, cache_key: str, verdict: GoblinVerdict) -> None:
        """Store a verdict in Redis cache."""
        from services.redis import redis_service

        if not redis_service.is_connected:
            return

        try:
            data = verdict.model_dump()
            data["cached"] = True  # Mark as cached for future reads
            await redis_service._client.setex(
                cache_key, VERDICT_CACHE_TTL, json.dumps(data, default=str)
            )
        except Exception:
            logger.debug("Failed to cache verdict at %s", cache_key)

    async def pregenerate_all_verdicts(self, week: int | None = None) -> dict:
        """
        Pre-generate verdicts for ALL active users across all risk modes.

        Called by the pre-generation scheduler (Thursday AM for NFL).
        Returns summary dict with counts.
        """
        from services.database import db_service

        if week is None:
            week = self._current_week()

        if not db_service.is_configured:
            return {"error": "DB not configured", "generated": 0, "failed": 0}

        # Get all users with Sleeper leagues
        users = await self._get_all_league_users()
        generated = 0
        failed = 0

        for user_id in users:
            for risk_mode in ("floor", "median", "ceiling"):
                cache_key = f"goblin:verdict:{user_id}:{risk_mode}:week{week}"
                try:
                    result = await self.generate_verdict(user_id, risk_mode, week, cache_key)
                    if result:
                        generated += 1
                    else:
                        failed += 1
                except Exception:
                    logger.exception(
                        "Pre-gen failed for user=%s mode=%s",
                        user_id[:8],
                        risk_mode,
                    )
                    failed += 1

        logger.info(
            "Verdict pre-generation complete: %d generated, %d failed (%d users)",
            generated,
            failed,
            len(users),
        )
        return {
            "week": week,
            "users": len(users),
            "generated": generated,
            "failed": failed,
        }

    async def _get_all_league_users(self) -> list[str]:
        """Get all user IDs that have a Sleeper league connected."""
        from services.database import db_service

        if not db_service.is_configured:
            return []

        try:
            from sqlalchemy import text

            async with db_service.session() as session:
                result = await session.execute(
                    text("""
                        SELECT google_id FROM users
                        WHERE sleeper_league_id IS NOT NULL
                          AND sleeper_user_id IS NOT NULL
                    """)
                )
                return [row[0] for row in result.all()]
        except Exception:
            logger.exception("Failed to fetch league users for pre-gen")
            return []

    def _current_week(self) -> int:
        """Estimate the current NFL week based on date. Rough heuristic."""
        now = datetime.now(UTC)
        # NFL season typically starts first Thursday of September
        # Week 1 starts around Sep 5. Each week is 7 days.
        season_start = datetime(now.year, 9, 5, tzinfo=UTC)
        if now < season_start:
            return 1
        days_since = (now - season_start).days
        return min(18, max(1, (days_since // 7) + 1))


# Singleton
goblin_verdict_service = GoblinVerdictService()
