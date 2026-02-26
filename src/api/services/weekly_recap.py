"""
Weekly recap generation service.

Aggregates a user's decision history for the past week and generates
an AI narrative via Claude.
"""

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Decision as DecisionModel
from models.database import WeeklyRecap
from monitoring import track_claude_request
from services.claude import claude_service

logger = logging.getLogger(__name__)

# System prompt for recap generation
_RECAP_SYSTEM_PROMPT = """You are a witty, knowledgeable fantasy sports analyst writing a personalized weekly recap.

Write in second person ("you"). Be concise but entertaining — like a sports column, not a data dump.
Use the stats provided to create a narrative that:
1. Opens with a headline-worthy summary of the week (one sentence)
2. Highlights the user's best and worst decisions
3. Comments on accuracy trends and confidence calibration
4. Gives one actionable tip for next week based on patterns
5. Closes with a motivational or humorous sign-off

Keep it under 300 words. Use markdown formatting (bold, bullet points) sparingly.
Do NOT invent stats — only reference data provided in the context."""

# Confidence rank for averaging
_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
_RANK_TO_CONFIDENCE = {1: "low", 2: "medium", 3: "high"}


def _compute_week_range(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Sunday 23:59:59) for the week containing `reference`."""
    now = reference or datetime.now(UTC)
    # Go back to most recent Monday
    monday = now - timedelta(days=now.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return week_start, week_end


async def _gather_week_stats(
    session: AsyncSession,
    user_id: int,
    week_start: datetime,
    week_end: datetime,
) -> dict:
    """Query decisions for the given user and week, return aggregated stats."""
    query = (
        select(DecisionModel)
        .where(
            DecisionModel.user_id == str(user_id),
            DecisionModel.created_at >= week_start,
            DecisionModel.created_at <= week_end,
        )
        .order_by(DecisionModel.created_at.desc())
    )
    result = await session.execute(query)
    decisions = result.scalars().all()

    if not decisions:
        return {"total": 0, "decisions": []}

    # Aggregate
    sport_counter: Counter[str] = Counter()
    confidence_values: list[int] = []
    correct = 0
    incorrect = 0
    pending = 0
    decision_summaries: list[dict] = []

    for d in decisions:
        sport_counter[d.sport] += 1
        conf_rank = _CONFIDENCE_RANK.get(d.confidence, 2)
        confidence_values.append(conf_rank)

        outcome = d.actual_outcome
        if outcome == "correct":
            correct += 1
        elif outcome == "incorrect":
            incorrect += 1
        else:
            pending += 1

        decision_summaries.append(
            {
                "sport": d.sport,
                "type": d.decision_type,
                "query": d.query[:120],
                "decision": d.decision[:120],
                "confidence": d.confidence,
                "source": d.source,
                "outcome": outcome or "pending",
                "player_a": d.player_a_name,
                "player_b": d.player_b_name,
            }
        )

    total = len(decisions)
    decided = correct + incorrect
    accuracy = round(correct / decided * 100, 1) if decided > 0 else None

    avg_conf_rank = round(sum(confidence_values) / len(confidence_values))
    avg_confidence = _RANK_TO_CONFIDENCE.get(avg_conf_rank, "medium")

    most_asked = sport_counter.most_common(1)[0][0] if sport_counter else None

    # Sport breakdown
    sport_breakdown = {sport: count for sport, count in sport_counter.most_common()}

    return {
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "pending": pending,
        "accuracy_pct": accuracy,
        "avg_confidence": avg_confidence,
        "most_asked_sport": most_asked,
        "sport_breakdown": sport_breakdown,
        "decisions": decision_summaries,
    }


def _build_recap_prompt(stats: dict, user_name: str, week_label: str) -> str:
    """Build the user message for Claude recap generation."""
    parts = [
        f"Generate a weekly fantasy recap for {user_name} ({week_label}).",
        "",
        f"Total decisions: {stats['total']}",
        f"Correct: {stats['correct']} | Incorrect: {stats['incorrect']} | Pending: {stats['pending']}",
    ]

    if stats["accuracy_pct"] is not None:
        parts.append(f"Accuracy: {stats['accuracy_pct']}%")

    parts.append(f"Average confidence: {stats['avg_confidence']}")
    parts.append(f"Most asked sport: {stats.get('most_asked_sport', 'N/A')}")

    if stats.get("sport_breakdown"):
        breakdown = ", ".join(
            f"{sport}: {count}" for sport, count in stats["sport_breakdown"].items()
        )
        parts.append(f"Sport breakdown: {breakdown}")

    # Include up to 10 decision summaries for narrative material
    sample = stats["decisions"][:10]
    if sample:
        parts.append("")
        parts.append("Recent decisions:")
        for d in sample:
            line = f"- [{d['sport'].upper()}] {d['type']}: {d['query']}"
            line += f" → {d['decision']} ({d['confidence']} conf, {d['outcome']})"
            if d.get("player_a"):
                line += f" [Players: {d['player_a']}"
                if d.get("player_b"):
                    line += f" vs {d['player_b']}"
                line += "]"
            parts.append(line)

    return "\n".join(parts)


async def generate_weekly_recap(
    session: AsyncSession,
    user_id: int,
    user_name: str,
    week_start: datetime | None = None,
    week_end: datetime | None = None,
) -> WeeklyRecap | None:
    """
    Generate and store a weekly recap for the given user.

    Returns the WeeklyRecap model if generated, None if no decisions found.
    """
    if week_start is None or week_end is None:
        week_start, week_end = _compute_week_range()

    # Check if recap already exists
    existing = await session.execute(
        select(WeeklyRecap).where(
            WeeklyRecap.user_id == user_id,
            WeeklyRecap.week_start == week_start,
            WeeklyRecap.sport.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        # Return cached recap
        return existing.scalar_one_or_none()

    # Re-query for the existing recap properly
    existing_result = await session.execute(
        select(WeeklyRecap).where(
            WeeklyRecap.user_id == user_id,
            WeeklyRecap.week_start == week_start,
            WeeklyRecap.sport.is_(None),
        )
    )
    cached = existing_result.scalar_one_or_none()
    if cached:
        return cached

    stats = await _gather_week_stats(session, user_id, week_start, week_end)

    if stats["total"] == 0:
        return None

    week_label = f"Week of {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
    prompt = _build_recap_prompt(stats, user_name, week_label)

    # Generate narrative via Claude
    input_tokens = 0
    output_tokens = 0
    narrative = ""

    if claude_service.is_available:
        try:
            response = claude_service.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=_RECAP_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            narrative = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            track_claude_request(input_tokens, output_tokens, success=True, variant="recap")
        except Exception as e:
            logger.error("Claude recap generation failed: %s", e)
            narrative = _fallback_narrative(stats, week_label)
    else:
        narrative = _fallback_narrative(stats, week_label)

    # Extract highlights (first decision outcomes)
    highlights = None
    best = [d for d in stats["decisions"] if d["outcome"] == "correct"]
    worst = [d for d in stats["decisions"] if d["outcome"] == "incorrect"]
    if best or worst:
        parts = []
        if best:
            parts.append(f"Best call: {best[0]['decision']}")
        if worst:
            parts.append(f"Missed call: {worst[0]['decision']}")
        highlights = " | ".join(parts)

    recap = WeeklyRecap(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        sport=None,  # All-sport recap
        total_decisions=stats["total"],
        correct_decisions=stats["correct"],
        incorrect_decisions=stats["incorrect"],
        pending_decisions=stats["pending"],
        accuracy_pct=stats["accuracy_pct"],
        avg_confidence=stats["avg_confidence"],
        most_asked_sport=stats["most_asked_sport"],
        narrative=narrative,
        highlights=highlights,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    session.add(recap)
    await session.commit()
    await session.refresh(recap)

    return recap


def _fallback_narrative(stats: dict, week_label: str) -> str:
    """Generate a simple narrative when Claude is unavailable."""
    parts = [f"**{week_label}**", ""]
    parts.append(
        f"You made **{stats['total']} decisions** this week"
        f" across {len(stats.get('sport_breakdown', {}))} sport(s)."
    )

    decided = stats["correct"] + stats["incorrect"]
    if decided > 0:
        parts.append(
            f"Your accuracy was **{stats['accuracy_pct']}%**"
            f" ({stats['correct']}/{decided} correct)."
        )
    else:
        parts.append("No outcomes tracked yet — check back after games finish.")

    if stats.get("most_asked_sport"):
        parts.append(f"Most active sport: **{stats['most_asked_sport'].upper()}**.")

    parts.append("")
    parts.append("Keep making smart calls!")

    return "\n".join(parts)


async def get_user_recaps(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[WeeklyRecap]:
    """Fetch stored recaps for a user, most recent first."""
    result = await session.execute(
        select(WeeklyRecap)
        .where(WeeklyRecap.user_id == user_id)
        .order_by(WeeklyRecap.week_start.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
