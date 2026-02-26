"""
Rivalry tracking service.

Syncs matchup data from Sleeper and computes head-to-head records
between league members.
"""

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import LeagueMatchup
from services.sleeper import SleeperMatchup, sleeper_service

logger = logging.getLogger(__name__)


async def sync_matchups(
    session: AsyncSession,
    league_id: int,
    sleeper_league_id: str,
    season: str,
    weeks: list[int],
) -> int:
    """
    Sync matchup results from Sleeper into league_matchups table.

    Uses upsert (ON CONFLICT DO UPDATE) so re-syncing is safe.

    Returns:
        Number of matchup records upserted.
    """
    # Fetch rosters to map roster_id → owner_id
    rosters = await sleeper_service.get_league_rosters(sleeper_league_id)
    roster_to_owner: dict[int, str] = {}
    for r in rosters:
        if r.owner_id:
            roster_to_owner[r.roster_id] = r.owner_id

    total_upserted = 0

    for week in weeks:
        matchups = await sleeper_service.get_league_matchups(sleeper_league_id, week)

        # Group by matchup_id to pair opponents
        groups: dict[int, list[SleeperMatchup]] = defaultdict(list)
        for m in matchups:
            if m.matchup_id:
                groups[m.matchup_id].append(m)

        for _, pair in groups.items():
            if len(pair) != 2:
                continue

            a, b = pair
            # Ensure consistent ordering (lower roster_id first)
            if a.roster_id > b.roster_id:
                a, b = b, a

            owner_a = roster_to_owner.get(a.roster_id, "")
            owner_b = roster_to_owner.get(b.roster_id, "")

            if not owner_a or not owner_b:
                continue

            # Determine winner
            winner = None
            if a.points > b.points:
                winner = owner_a
            elif b.points > a.points:
                winner = owner_b
            # Tie: winner stays None

            stmt = pg_insert(LeagueMatchup).values(
                league_id=league_id,
                season=season,
                week=week,
                roster_id_a=a.roster_id,
                roster_id_b=b.roster_id,
                owner_id_a=owner_a,
                owner_id_b=owner_b,
                points_a=Decimal(str(a.points)),
                points_b=Decimal(str(b.points)),
                winner_owner_id=winner,
            )

            stmt = stmt.on_conflict_do_update(
                constraint="uq_league_matchup",
                set_={
                    "points_a": stmt.excluded.points_a,
                    "points_b": stmt.excluded.points_b,
                    "winner_owner_id": stmt.excluded.winner_owner_id,
                    "owner_id_a": stmt.excluded.owner_id_a,
                    "owner_id_b": stmt.excluded.owner_id_b,
                    "synced_at": func.now(),
                },
            )

            await session.execute(stmt)
            total_upserted += 1

    await session.commit()
    return total_upserted


async def get_h2h_record(
    session: AsyncSession,
    league_id: int,
    owner_a: str,
    owner_b: str,
    season: str | None = None,
) -> dict:
    """
    Get head-to-head record between two owners in a league.

    Returns:
        Dict with wins_a, wins_b, ties, total_points_a, total_points_b, matchups.
    """
    conditions = [
        LeagueMatchup.league_id == league_id,
        or_(
            and_(
                LeagueMatchup.owner_id_a == owner_a,
                LeagueMatchup.owner_id_b == owner_b,
            ),
            and_(
                LeagueMatchup.owner_id_a == owner_b,
                LeagueMatchup.owner_id_b == owner_a,
            ),
        ),
    ]
    if season:
        conditions.append(LeagueMatchup.season == season)

    result = await session.execute(
        select(LeagueMatchup)
        .where(*conditions)
        .order_by(LeagueMatchup.season.desc(), LeagueMatchup.week.desc())
    )
    matchups = result.scalars().all()

    wins_a = 0
    wins_b = 0
    ties = 0
    total_points_a = Decimal("0")
    total_points_b = Decimal("0")
    history: list[dict] = []

    for m in matchups:
        # Normalize: figure out which side is owner_a
        if m.owner_id_a == owner_a:
            pa, pb = m.points_a or Decimal("0"), m.points_b or Decimal("0")
        else:
            pa, pb = m.points_b or Decimal("0"), m.points_a or Decimal("0")

        total_points_a += pa
        total_points_b += pb

        if m.winner_owner_id == owner_a:
            wins_a += 1
        elif m.winner_owner_id == owner_b:
            wins_b += 1
        else:
            ties += 1

        history.append(
            {
                "season": m.season,
                "week": m.week,
                "points_a": float(pa),
                "points_b": float(pb),
                "winner": m.winner_owner_id,
            }
        )

    return {
        "owner_a": owner_a,
        "owner_b": owner_b,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "total_points_a": float(total_points_a),
        "total_points_b": float(total_points_b),
        "matchups": history,
    }


async def get_league_rivalries(
    session: AsyncSession,
    league_id: int,
    season: str | None = None,
) -> list[dict]:
    """
    Get all rivalry records in a league, sorted by most games played.

    Returns list of H2H summaries between each pair of owners.
    """
    conditions = [LeagueMatchup.league_id == league_id]
    if season:
        conditions.append(LeagueMatchup.season == season)

    result = await session.execute(select(LeagueMatchup).where(*conditions))
    matchups = result.scalars().all()

    # Group by owner pairs (order-independent)
    pair_matchups: dict[tuple[str, str], list] = defaultdict(list)
    for m in matchups:
        key = tuple(sorted([m.owner_id_a, m.owner_id_b]))
        pair_matchups[key].append(m)

    rivalries = []
    for (oa, ob), ms in pair_matchups.items():
        wins_a = sum(1 for m in ms if m.winner_owner_id == oa)
        wins_b = sum(1 for m in ms if m.winner_owner_id == ob)
        ties = sum(1 for m in ms if m.winner_owner_id is None)
        total_a = sum(float(m.points_a if m.owner_id_a == oa else m.points_b or 0) for m in ms)
        total_b = sum(float(m.points_b if m.owner_id_a == oa else m.points_a or 0) for m in ms)

        rivalries.append(
            {
                "owner_a": oa,
                "owner_b": ob,
                "games_played": len(ms),
                "wins_a": wins_a,
                "wins_b": wins_b,
                "ties": ties,
                "avg_margin": round(abs(total_a - total_b) / len(ms), 2) if ms else 0,
                "total_points_a": round(total_a, 2),
                "total_points_b": round(total_b, 2),
            }
        )

    # Sort by most games played (most history = best rivalry)
    rivalries.sort(key=lambda r: r["games_played"], reverse=True)
    return rivalries


async def get_user_rivalries(
    session: AsyncSession,
    league_id: int,
    owner_id: str,
    season: str | None = None,
) -> list[dict]:
    """
    Get all rivalry records for a specific user in a league.
    """
    conditions = [
        LeagueMatchup.league_id == league_id,
        or_(
            LeagueMatchup.owner_id_a == owner_id,
            LeagueMatchup.owner_id_b == owner_id,
        ),
    ]
    if season:
        conditions.append(LeagueMatchup.season == season)

    result = await session.execute(select(LeagueMatchup).where(*conditions))
    matchups = result.scalars().all()

    # Group by opponent
    opponent_matchups: dict[str, list] = defaultdict(list)
    for m in matchups:
        opponent = m.owner_id_b if m.owner_id_a == owner_id else m.owner_id_a
        opponent_matchups[opponent].append(m)

    rivalries = []
    for opponent, ms in opponent_matchups.items():
        wins = sum(1 for m in ms if m.winner_owner_id == owner_id)
        losses = sum(1 for m in ms if m.winner_owner_id == opponent)
        ties = len(ms) - wins - losses

        rivalries.append(
            {
                "opponent": opponent,
                "games_played": len(ms),
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "win_pct": round(wins / len(ms) * 100, 1) if ms else 0,
            }
        )

    rivalries.sort(key=lambda r: r["games_played"], reverse=True)
    return rivalries
