"""
A/B prompt testing for BenchGoblin.

Defines prompt variants, manages experiment lifecycle, and assigns users
to variants deterministically based on session_id hash.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

# =============================================================================
# Prompt Variants
# =============================================================================

CONTROL_PROMPT = """You are BenchGoblin, a fantasy sports decision engine.

<core_function>
You evaluate start/sit, waiver, and trade decisions under uncertainty. You are NOT a prediction model — you produce probabilistic decisions, never guarantees.

You use role stability, spatial opportunity, and matchup context to compare options relatively. You never evaluate players in isolation.
</core_function>

<scope>
You answer ALL fantasy sports questions: start/sit, trades, waivers, streaming, add/drop, captaincy, differentials, transfers, chip strategy, player stats, matchups, injuries, and general fantasy advice.

If the Sport in request_context doesn't match the players mentioned, still answer using the correct sport — prioritize the actual players.

NEVER refuse a fantasy sports question. Always provide your best analysis.
</scope>

<supported_sports>
- NBA (primary)
- NFL
- MLB (beta)
- NHL (beta)
- Soccer (FPL, La Liga Fantasy, UCL Fantasy, MLS Fantasy, Bundesliga Fantasy, Cartola FC)

You do NOT provide: betting picks, gambling odds, or deterministic predictions.
</supported_sports>

<qualitative_indices>
You assess players using five qualitative proxies:

1. SPACE CREATION INDEX (SCI) - How a player generates usable space independent of volume.
2. ROLE MOTION INDEX (RMI) - Dependence on motion, scheme, or teammates. High = fragile.
3. GRAVITY IMPACT SCORE (GIS) - Defensive attention drawn, not box-score output.
4. OPPORTUNITY DELTA (OD) - Change in role, not raw role size. Positive = expanding.
5. MATCHUP SPACE FIT (MSF) - Whether the opponent allows the space this player exploits.

For soccer, adapt these indices:
- SCI → Space Creation: carries into final third, progressive passes, chance creation, xG/xA
- RMI → Role Fluidity: positional versatility, set piece involvement, rotation risk
- GIS → Defensive Gravity: press resistance, aerial duels, tackles won, clean sheet probability
- OD → Fixture Swing: opponent defensive rating, home/away split, FDR (fixture difficulty rating)
- MSF → Formation Fit: player style vs opponent weakness, expected minutes, formation role
</qualitative_indices>

<multilingual>
You can respond in any of these languages when the user writes in that language: English, Spanish, Portuguese, French, German, Japanese, Korean, Chinese, Arabic. Match the user's language in your response. Always keep the JSON structure keys in English.
</multilingual>

<risk_modes>
FLOOR: Minimize downside. Prioritize role stability and guaranteed volume.
MEDIAN: Maximize expected value. Balance all factors. (Default)
CEILING: Maximize upside. Emphasize spike-week potential. Accept volatility.

The same inputs produce different recommendations depending on mode.
</risk_modes>

<output_format>
Always respond with this exact JSON structure:
{
  "decision": "Start [Player Name]" or "Sit [Player Name]" or "Add [Player Name]" or "Drop [Player Name]" or "Captain [Player Name]",
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

CONCISE_V1_PROMPT = """You are BenchGoblin, a fantasy sports decision engine.

You evaluate start/sit, waiver, and trade decisions under uncertainty using five qualitative indices: SCI (space creation), RMI (role fragility), GIS (gravity), OD (opportunity delta), MSF (matchup fit).

Risk modes: FLOOR (minimize downside), MEDIAN (expected value, default), CEILING (maximize upside).

Sports: NBA, NFL, MLB (beta), NHL (beta), Soccer (FPL, La Liga, UCL, MLS, Bundesliga, Cartola FC). No betting picks or deterministic predictions. For soccer, adapt indices: SCI→Space Creation (xG/xA, progressive passes), RMI→Role Fluidity, GIS→Defensive Gravity, OD→Fixture Swing (FDR), MSF→Formation Fit. Respond in the user's language (EN, ES, PT, FR, DE, JA, KO, ZH, AR) but keep JSON keys in English.

Answer ALL fantasy sports questions: start/sit, trades, waivers, streaming, captaincy, differentials, transfers, budget picks, chip strategy, player stats, matchups, injuries, general advice. NEVER refuse a fantasy sports question. If Sport doesn't match players mentioned, answer using the correct sport.

Respond ONLY with JSON, no preamble:
{
  "decision": "Start [Player Name]" or "Sit [Player Name]" or "Add [Player Name]" or "Drop [Player Name]" or "Captain [Player Name]",
  "confidence": "low" or "medium" or "high",
  "rationale": "One sentence summary of why",
  "details": {
    "why": ["Bullet 1", "Bullet 2", "Bullet 3"],
    "risk_note": "One sentence about the main risk"
  }
}

Confidence reflects role clarity and data agreement, NOT likelihood of success."""

PROMPT_VARIANTS: dict[str, str] = {
    "control": CONTROL_PROMPT,
    "concise_v1": CONCISE_V1_PROMPT,
}

# =============================================================================
# Experiment Lifecycle
# =============================================================================


@dataclass
class Experiment:
    """A single A/B experiment definition."""

    name: str
    variants: dict[str, int]  # variant_name -> weight
    started_at: datetime
    ended_at: datetime | None = None
    description: str = ""

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration_hours(self) -> float | None:
        end = self.ended_at or datetime.now(UTC)
        delta = end - self.started_at
        return round(delta.total_seconds() / 3600, 1)


@dataclass
class ExperimentRegistry:
    """Manages experiment lifecycle — start, stop, history."""

    _active: Experiment | None = None
    _history: list[Experiment] = field(default_factory=list)

    @property
    def active(self) -> Experiment | None:
        return self._active

    @property
    def history(self) -> list[Experiment]:
        return list(self._history)

    def start_experiment(
        self,
        name: str,
        variants: dict[str, int],
        description: str = "",
    ) -> Experiment:
        """Start a new experiment. Ends the current one if active."""
        if self._active is not None:
            self.end_experiment()

        # Validate all variants have prompts
        for v in variants:
            if v not in PROMPT_VARIANTS:
                raise ValueError(f"Unknown variant: {v}. Register it in PROMPT_VARIANTS first.")

        experiment = Experiment(
            name=name,
            variants=variants,
            started_at=datetime.now(UTC),
            description=description,
        )
        self._active = experiment
        return experiment

    def end_experiment(self) -> Experiment | None:
        """End the active experiment and archive it."""
        if self._active is None:
            return None

        self._active.ended_at = datetime.now(UTC)
        ended = self._active
        self._history.append(ended)
        self._active = None
        return ended

    def get_active_weights(self) -> dict[str, int]:
        """Return active experiment weights, or fallback to control-only."""
        if self._active is not None:
            return self._active.variants
        return {"control": 100}


# Singleton registry — initialized with the default experiment
experiment_registry = ExperimentRegistry()
experiment_registry.start_experiment(
    name="concise_prompt_v1",
    variants={"control": 50, "concise_v1": 50},
    description="Test whether a shorter system prompt improves JSON compliance and reduces token usage.",
)

# Keep module-level alias for backward compat
ACTIVE_EXPERIMENT = experiment_registry.get_active_weights()


# =============================================================================
# Variant Assignment
# =============================================================================


def assign_variant(session_id: str | None) -> str:
    """Assign a prompt variant deterministically based on session_id.

    Same session_id always gets the same variant. If no session_id,
    a random one is generated (non-deterministic).

    Uses the active experiment's weights.
    """
    if not session_id:
        session_id = uuid.uuid4().hex

    weights = experiment_registry.get_active_weights()
    variants = list(weights.keys())
    total_weight = sum(weights.values())

    # Hash session_id to a stable integer
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) % total_weight

    cumulative = 0
    for variant in variants:
        cumulative += weights[variant]
        if bucket < cumulative:
            return variant

    return variants[0]


def get_prompt(variant: str) -> str:
    """Return the system prompt for a variant. Falls back to control."""
    return PROMPT_VARIANTS.get(variant, PROMPT_VARIANTS["control"])


def get_experiment_config() -> dict:
    """Return active experiment configuration."""
    active = experiment_registry.active
    weights = experiment_registry.get_active_weights()

    config: dict = {
        "variants": list(weights.keys()),
        "weights": weights,
        "total_variants": len(weights),
        "prompts": {name: prompt[:100] + "..." for name, prompt in PROMPT_VARIANTS.items()},
    }

    if active:
        config["experiment"] = {
            "name": active.name,
            "description": active.description,
            "started_at": active.started_at.isoformat(),
            "ended_at": active.ended_at.isoformat() if active.ended_at else None,
            "is_active": active.is_active,
            "duration_hours": active.duration_hours,
        }

    return config


def get_experiment_history() -> list[dict]:
    """Return all past experiments."""
    return [
        {
            "name": exp.name,
            "description": exp.description,
            "variants": exp.variants,
            "started_at": exp.started_at.isoformat(),
            "ended_at": exp.ended_at.isoformat() if exp.ended_at else None,
            "duration_hours": exp.duration_hours,
        }
        for exp in experiment_registry.history
    ]
