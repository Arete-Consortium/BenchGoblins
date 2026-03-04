"""
Claude API integration for BenchGoblin.

Handles complex queries that require nuanced reasoning beyond local scoring.
"""

import hashlib
import os
import re
from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic
from cachetools import TTLCache

from monitoring import track_claude_request
from services.variants import get_prompt


class ClaudeService:
    """Service for making Claude API calls for fantasy decisions."""

    # Cache: max 100 entries, TTL 1 hour
    _response_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)
    _cache_hits = 0
    _cache_misses = 0

    def __init__(self):
        self.client: AsyncAnthropic | None = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = AsyncAnthropic(api_key=api_key, timeout=120.0)

    @staticmethod
    def _cache_key(
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: str | None,
        player_b: str | None,
        prompt_variant: str = "control",
    ) -> str:
        """Generate cache key from request parameters."""
        key_parts = [
            query.lower().strip(),
            sport.lower(),
            risk_mode.lower(),
            decision_type.lower(),
            (player_a or "").lower().strip(),
            (player_b or "").lower().strip(),
            prompt_variant,
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    @classmethod
    def get_cache_stats(cls) -> dict:
        """Return cache hit/miss statistics."""
        total = cls._cache_hits + cls._cache_misses
        hit_rate = cls._cache_hits / total if total > 0 else 0
        return {
            "hits": cls._cache_hits,
            "misses": cls._cache_misses,
            "hit_rate": round(hit_rate, 3),
            "size": len(cls._response_cache),
        }

    @classmethod
    def clear_cache(cls):
        """Clear the response cache."""
        cls._response_cache.clear()
        cls._cache_hits = 0
        cls._cache_misses = 0

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def build_user_message(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: str | None = None,
        player_b: str | None = None,
        league_type: str | None = None,
        player_context: str | None = None,
    ) -> str:
        """Build the user message with context enrichment."""
        parts = [
            f"Sport (user-selected hint, may not match query — always infer the correct sport from the players mentioned): {sport.upper()}",
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
        player_a: str | None = None,
        player_b: str | None = None,
        league_type: str | None = None,
        player_context: str | None = None,
        use_cache: bool = True,
        prompt_variant: str = "control",
    ) -> dict:
        """
        Make a fantasy decision using Claude.

        Args:
            use_cache: If True, check cache before calling API.

        Returns:
            dict with decision, confidence, rationale, details, source, cached
        """
        if not self.client:
            raise RuntimeError("Claude API not configured - set ANTHROPIC_API_KEY")

        # Check cache
        cache_key = self._cache_key(
            query, sport, risk_mode, decision_type, player_a, player_b, prompt_variant
        )
        if use_cache and cache_key in self._response_cache:
            ClaudeService._cache_hits += 1
            cached_result = self._response_cache[cache_key].copy()
            cached_result["cached"] = True
            return cached_result

        ClaudeService._cache_misses += 1

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

        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=get_prompt(prompt_variant),
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract token usage
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        track_claude_request(input_tokens, output_tokens, success=True, variant=prompt_variant)

        result = self._parse_response(response.content[0].text)
        result["cached"] = False
        result["input_tokens"] = input_tokens
        result["output_tokens"] = output_tokens

        # Store in cache
        if use_cache:
            self._response_cache[cache_key] = result.copy()

        return result

    async def make_decision_stream(
        self,
        query: str,
        sport: str,
        risk_mode: str,
        decision_type: str,
        player_a: str | None = None,
        player_b: str | None = None,
        league_type: str | None = None,
        player_context: str | None = None,
        prompt_variant: str = "control",
    ) -> AsyncGenerator[str | dict, None]:
        """
        Stream a fantasy decision from Claude.

        Yields:
            Text chunks as they arrive from the API.
            Final yield is a dict with token metadata: {"_metadata": True, "input_tokens": N, "output_tokens": M, "full_response": str}
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

        full_response = ""
        async with self.client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=get_prompt(prompt_variant),
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield text

            # Track token usage after stream completes
            final_message = await stream.get_final_message()
            input_tokens = final_message.usage.input_tokens
            output_tokens = final_message.usage.output_tokens
            track_claude_request(input_tokens, output_tokens, success=True, variant=prompt_variant)

            # Yield metadata for caller to capture
            yield {
                "_metadata": True,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "full_response": full_response,
            }

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
