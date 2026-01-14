"""
Claude API integration for GameSpace.

Handles complex queries that require nuanced reasoning beyond local scoring.
"""

import os
import re
from typing import Optional

from anthropic import Anthropic

SYSTEM_PROMPT = """You are GameSpace, a fantasy sports decision engine.

<core_function>
You evaluate start/sit, waiver, and trade decisions under uncertainty. You are NOT a prediction model — you produce probabilistic decisions, never guarantees.

You use role stability, spatial opportunity, and matchup context to compare options relatively. You never evaluate players in isolation.
</core_function>

<supported_sports>
- NBA (primary)
- NFL
- MLB (beta)
- NHL (beta)

You do NOT provide: betting picks, gambling odds, or deterministic predictions.
</supported_sports>

<qualitative_indices>
You assess players using five qualitative proxies:

1. SPACE CREATION INDEX (SCI) - How a player generates usable space independent of volume.
2. ROLE MOTION INDEX (RMI) - Dependence on motion, scheme, or teammates. High = fragile.
3. GRAVITY IMPACT SCORE (GIS) - Defensive attention drawn, not box-score output.
4. OPPORTUNITY DELTA (OD) - Change in role, not raw role size. Positive = expanding.
5. MATCHUP SPACE FIT (MSF) - Whether the opponent allows the space this player exploits.
</qualitative_indices>

<risk_modes>
FLOOR: Minimize downside. Prioritize role stability and guaranteed volume.
MEDIAN: Maximize expected value. Balance all factors. (Default)
CEILING: Maximize upside. Emphasize spike-week potential. Accept volatility.

The same inputs produce different recommendations depending on mode.
</risk_modes>

<output_format>
Always respond with this exact JSON structure:
{
  "decision": "Start [Player Name]" or "Sit [Player Name]" or "Add [Player Name]" or "Drop [Player Name]",
  "confidence": "low" or "medium" or "high",
  "rationale": "One sentence summary of why",
  "details": {
    "why": ["Bullet 1", "Bullet 2", "Bullet 3"],
    "risk_note": "One sentence about the main risk"
  }
}

Confidence reflects role clarity and data agreement — NOT likelihood of success.
</output_format>

<philosophy>
- Fantasy is a decision problem, not a prediction problem
- Volume ≠ safety
- Matchups are skill-specific, not opponent-wide
- Upside and downside must be explicitly separated
- Transparency > false precision
</philosophy>"""


class ClaudeService:
    """Service for making Claude API calls for fantasy decisions."""

    def __init__(self):
        self.client: Optional[Anthropic] = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = Anthropic(api_key=api_key)

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def build_user_message(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: Optional[str] = None,
        player_b: Optional[str] = None,
        league_type: Optional[str] = None,
        player_context: Optional[str] = None,
    ) -> str:
        """Build the user message with context enrichment."""
        parts = [
            f"Sport: {sport.upper()}",
            f"Risk Mode: {risk_mode.upper()}",
            f"Decision Type: {decision_type.replace('_', '/')}",
        ]

        if league_type:
            parts.append(f"League Type: {league_type}")

        if player_a:
            parts.append(f"Player A: {player_a}")
        if player_b:
            parts.append(f"Player B: {player_b}")

        context_block = "\n".join(parts)

        message = f"""<request_context>
{context_block}
</request_context>

<user_query>
{query}
</user_query>"""

        if player_context:
            message += f"""

<player_data>
{player_context}
</player_data>"""

        return message

    async def make_decision(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: Optional[str] = None,
        player_b: Optional[str] = None,
        league_type: Optional[str] = None,
        player_context: Optional[str] = None,
    ) -> dict:
        """
        Make a fantasy decision using Claude.

        Returns:
            dict with decision, confidence, rationale, details, source
        """
        if not self.client:
            raise RuntimeError("Claude API not configured - set ANTHROPIC_API_KEY")

        user_message = self.build_user_message(
            query=query,
            sport=sport,
            risk_mode=risk_mode,
            decision_type=decision_type,
            player_a=player_a,
            player_b=player_b,
            league_type=league_type,
            player_context=player_context,
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        return self._parse_response(response.content[0].text)

    def _parse_response(self, response_text: str) -> dict:
        """Parse Claude's response into structured data."""
        import json

        # Try to extract JSON from the response
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {
                    "decision": data.get("decision", "Unable to determine"),
                    "confidence": data.get("confidence", "medium"),
                    "rationale": data.get("rationale", response_text[:200]),
                    "details": data.get("details"),
                    "source": "claude",
                }
            except json.JSONDecodeError:
                pass

        # Fallback: parse freeform response
        return self._parse_freeform_response(response_text)

    def _parse_freeform_response(self, text: str) -> dict:
        """Parse a freeform response when JSON extraction fails."""
        # Extract decision
        decision = "See details"
        decision_patterns = [
            r"(?:Start|Sit|Add|Drop)\s+[\w\s\.\-']+",
            r"→\s*(.*?)(?:\s*—|$)",
        ]
        for pattern in decision_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                decision = match.group().strip()
                break

        # Extract confidence
        confidence = "medium"
        conf_match = re.search(r"confidence[:\s]*(low|medium|high)", text, re.IGNORECASE)
        if conf_match:
            confidence = conf_match.group(1).lower()

        # Get first meaningful sentence as rationale
        sentences = re.split(r"[.!?]+", text)
        rationale = sentences[0].strip() if sentences else text[:200]

        return {
            "decision": decision,
            "confidence": confidence,
            "rationale": rationale,
            "details": {"raw_response": text},
            "source": "claude",
        }


# Singleton instance
claude_service = ClaudeService()
