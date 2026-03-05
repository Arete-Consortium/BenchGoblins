"""
Goblin API Routes — Weekly lineup verdicts, trash talk, and analysis.

The Goblin is the core personality of BenchGoblins: a brutally honest
fantasy analyst that gives weekly lineup verdicts with swap recommendations.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routes.auth import require_admin_key, require_pro
from services.goblin_verdict import (
    GoblinVerdict,
    RiskMode,
    goblin_verdict_service,
)
from services.verdict_scheduler import verdict_pregen_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goblin", tags=["Goblin"])


# -------------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------------


class VerdictStatusResponse(BaseModel):
    """Status response for pre-generation jobs."""

    queued: int
    message: str


class TrashTalkRequest(BaseModel):
    """Request for Goblin trash talk generation."""

    opponent_name: str = Field(
        ..., max_length=100, description="Opponent's team name or manager name"
    )
    context: str = Field(
        default="",
        max_length=500,
        description="Optional context: matchup details, rivalry history, etc.",
    )
    spice_level: int = Field(default=2, ge=1, le=3, description="1=mild, 2=medium, 3=extra spicy")


class TrashTalkResponse(BaseModel):
    """Generated trash talk from the Goblin."""

    lines: list[str] = Field(description="3-5 trash talk lines")
    gif_search_term: str = Field(default="", description="Suggested GIF search term")
    spice_level: int


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.get("/verdict", response_model=GoblinVerdict)
async def get_my_verdict(
    risk_mode: RiskMode = Query(default=RiskMode.MEDIAN, description="Risk mode for analysis"),
    week: int | None = Query(default=None, description="NFL week (auto-detected if omitted)"),
    current_user: dict = Depends(require_pro),
):
    """
    Get the Goblin's verdict for the authenticated user's lineup.

    Returns a cached pre-generated verdict if available (instant),
    or generates on-demand (slower, 5-10s).
    """
    user_id = str(current_user["user_id"])

    verdict = await goblin_verdict_service.get_verdict(
        user_id=user_id,
        risk_mode=risk_mode.value,
        week=week,
    )

    if not verdict:
        raise HTTPException(
            status_code=404,
            detail=(
                "No verdict available. Make sure you have a Sleeper league connected. "
                "Connect at /integrations/sleeper."
            ),
        )

    return verdict


@router.post("/verdict/generate", response_model=GoblinVerdict)
async def generate_verdict(
    risk_mode: RiskMode = Query(default=RiskMode.MEDIAN),
    week: int | None = Query(default=None),
    current_user: dict = Depends(require_pro),
):
    """
    Force-generate a fresh Goblin verdict (bypasses cache).

    Use this when the user changes their lineup and wants an updated verdict.
    """
    user_id = str(current_user["user_id"])

    verdict = await goblin_verdict_service.generate_verdict(
        user_id=user_id,
        risk_mode=risk_mode.value,
        week=week or goblin_verdict_service._current_week(),
    )

    if not verdict:
        raise HTTPException(
            status_code=404,
            detail="Could not generate verdict. Check your Sleeper league connection.",
        )

    return verdict


@router.post("/verdict/pregenerate")
async def pregenerate_verdicts(
    week: int | None = Query(default=None),
    _admin: None = Depends(require_admin_key),
):
    """
    Manually trigger verdict pre-generation for all active users.

    Admin-only. Generates verdicts for all 3 risk modes per user.
    """
    result = await goblin_verdict_service.pregenerate_all_verdicts(week=week)
    return result


@router.get("/verdict/pregen-status")
async def pregen_status(
    _admin: None = Depends(require_admin_key),
):
    """Get the status of the verdict pre-generation scheduler."""
    return {
        "is_running": verdict_pregen_scheduler.is_running,
        "last_pregen_at": (
            verdict_pregen_scheduler._last_pregen_at.isoformat()
            if verdict_pregen_scheduler._last_pregen_at
            else None
        ),
        "should_run_now": verdict_pregen_scheduler.should_run_now(),
    }


# -------------------------------------------------------------------------
# Trash Talk
# -------------------------------------------------------------------------

TRASH_TALK_PROMPT = """You are the Goblin — a ruthless fantasy sports trash talk generator.
Your job: generate savage but fun trash talk for fantasy matchups.

Rules:
- Keep it fantasy-sports specific, not personal
- Be creative and funny, not mean-spirited
- Reference common fantasy tropes (bye weeks, injuries, waiver wire, etc.)
- Each line should stand alone as a sendable message
- Suggest a GIF search term that matches the vibe

SPICE LEVELS:
1 = Friendly banter, safe for work group chats
2 = Medium heat, confident swagger
3 = Maximum roast, no mercy (still fantasy-focused, never personal attacks)

Return ONLY valid JSON:
{{
  "lines": ["line1", "line2", "line3"],
  "gif_search_term": "search term for a matching reaction GIF"
}}"""


@router.post("/trash-talk", response_model=TrashTalkResponse)
async def generate_trash_talk(
    request: TrashTalkRequest,
    current_user: dict = Depends(require_pro),
):
    """
    Generate Goblin-voiced trash talk for a fantasy matchup.

    Perfect for sending to your league group chat before game day.
    """
    from services.claude import claude_service

    if not claude_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="The Goblin is sleeping (Claude unavailable)",
        )

    spice_labels = {1: "MILD", 2: "MEDIUM", 3: "EXTRA SPICY"}
    user_msg = (
        f"Generate {spice_labels[request.spice_level]} trash talk for my matchup "
        f"against {request.opponent_name}."
    )
    if request.context:
        user_msg += f"\nContext: {request.context}"

    try:
        response = await claude_service.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=TRASH_TALK_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()

        # Parse JSON — handle markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        data = json.loads(text)
        lines = data.get("lines", [])[:5]  # Cap at 5 lines
        gif_term = data.get("gif_search_term", "")

        return TrashTalkResponse(
            lines=lines,
            gif_search_term=gif_term,
            spice_level=request.spice_level,
        )

    except json.JSONDecodeError:
        logger.warning("Failed to parse trash talk response as JSON")
        raise HTTPException(
            status_code=500,
            detail="The Goblin mumbled something incoherent. Try again.",
        )
    except Exception:
        logger.exception("Trash talk generation failed")
        raise HTTPException(
            status_code=500,
            detail="The Goblin choked on his words. Try again.",
        )
