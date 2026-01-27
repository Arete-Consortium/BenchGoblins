#!/usr/bin/env python3
"""
Seed synthetic decision data with A/B variant labels.

Generates realistic-looking decisions across both prompt variants
so experiment endpoints return meaningful results.

Usage:
    python scripts/seed_experiment_data.py              # 200 decisions, print SQL
    python scripts/seed_experiment_data.py --count 500  # custom count
    python scripts/seed_experiment_data.py --execute     # run against DATABASE_URL
"""

import argparse
import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(src_path / "api"))

# --- Data pools ---

NBA_PLAYERS = [
    "LeBron James",
    "Kevin Durant",
    "Stephen Curry",
    "Giannis Antetokounmpo",
    "Luka Doncic",
    "Nikola Jokic",
    "Joel Embiid",
    "Jayson Tatum",
    "Anthony Davis",
    "Damian Lillard",
    "Devin Booker",
    "Trae Young",
    "Ja Morant",
    "Donovan Mitchell",
    "Bam Adebayo",
    "Jimmy Butler",
    "Paul George",
    "Tyrese Haliburton",
    "Jalen Brunson",
    "Tyrese Maxey",
]

NFL_PLAYERS = [
    "Patrick Mahomes",
    "Josh Allen",
    "Jalen Hurts",
    "Lamar Jackson",
    "Travis Kelce",
    "Tyreek Hill",
    "Justin Jefferson",
    "CeeDee Lamb",
    "Derrick Henry",
    "Saquon Barkley",
    "Breece Hall",
    "Jahmyr Gibbs",
    "Amon-Ra St. Brown",
    "Davante Adams",
    "Ja'Marr Chase",
    "A.J. Brown",
]

MLB_PLAYERS = [
    "Shohei Ohtani",
    "Mookie Betts",
    "Ronald Acuna Jr.",
    "Freddie Freeman",
    "Aaron Judge",
    "Julio Rodriguez",
    "Trea Turner",
    "Corey Seager",
]

NHL_PLAYERS = [
    "Connor McDavid",
    "Nathan MacKinnon",
    "Auston Matthews",
    "Leon Draisaitl",
    "Nikita Kucherov",
    "Cale Makar",
    "David Pastrnak",
    "Kirill Kaprizov",
]

SPORT_PLAYERS = {
    "nba": NBA_PLAYERS,
    "nfl": NFL_PLAYERS,
    "mlb": MLB_PLAYERS,
    "nhl": NHL_PLAYERS,
}

RISK_MODES = ["floor", "median", "ceiling"]
DECISION_TYPES = ["start_sit", "trade", "waiver"]
CONFIDENCES = ["low", "medium", "high"]
SOURCES = ["local", "claude"]
VARIANTS = ["control", "concise_v1"]

# Tuning: concise_v1 uses fewer tokens on average
TOKEN_PROFILES = {
    "control": {
        "input_mean": 850,
        "input_std": 120,
        "output_mean": 320,
        "output_std": 60,
    },
    "concise_v1": {
        "input_mean": 520,
        "input_std": 80,
        "output_mean": 280,
        "output_std": 50,
    },
}

# Confidence distribution differs slightly per variant (hypothesis)
CONFIDENCE_WEIGHTS = {
    "control": {"low": 20, "medium": 50, "high": 30},
    "concise_v1": {"low": 15, "medium": 45, "high": 40},
}


def _pick_pair(sport: str) -> tuple[str, str]:
    players = SPORT_PLAYERS[sport]
    a, b = random.sample(players, 2)
    return a, b


def _weighted_choice(weights: dict[str, int]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return random.choices(keys, weights=vals, k=1)[0]


def generate_decision(base_time: datetime, offset_minutes: int, variant: str) -> dict:
    sport = random.choice(list(SPORT_PLAYERS.keys()))
    player_a, player_b = _pick_pair(sport)
    risk_mode = random.choice(RISK_MODES)
    decision_type = random.choice(DECISION_TYPES)
    confidence = _weighted_choice(CONFIDENCE_WEIGHTS[variant])
    source = random.choices(SOURCES, weights=[30, 70], k=1)[0]

    # Token usage only for claude source
    input_tokens = None
    output_tokens = None
    cache_hit = False
    if source == "claude":
        profile = TOKEN_PROFILES[variant]
        input_tokens = max(
            100, int(random.gauss(profile["input_mean"], profile["input_std"]))
        )
        output_tokens = max(
            50, int(random.gauss(profile["output_mean"], profile["output_std"]))
        )
        cache_hit = random.random() < 0.15  # 15% cache hit rate

    winner = random.choice([player_a, player_b])
    action = (
        "Start"
        if decision_type == "start_sit"
        else ("Add" if decision_type == "waiver" else "Trade for")
    )
    decision_text = f"{action} {winner}"

    query_templates = [
        f"Should I start {player_a} or {player_b}?",
        f"{player_a} vs {player_b} this week?",
        f"Start/sit: {player_a} or {player_b}",
        f"Who should I play, {player_a} or {player_b}?",
    ]

    created_at = base_time + timedelta(minutes=offset_minutes + random.randint(0, 5))

    return {
        "id": str(uuid.uuid4()),
        "sport": sport,
        "risk_mode": risk_mode,
        "decision_type": decision_type,
        "query": random.choice(query_templates),
        "player_a_name": player_a,
        "player_b_name": player_b,
        "decision": decision_text,
        "confidence": confidence,
        "rationale": f"{winner} has better matchup fit and higher opportunity delta in {risk_mode} mode.",
        "source": source,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_hit": cache_hit,
        "prompt_variant": variant,
        "created_at": created_at,
    }


def generate_all(count: int) -> list[dict]:
    """Generate `count` decisions spread over the last 7 days."""
    now = datetime.now(UTC)
    base_time = now - timedelta(days=7)
    total_minutes = 7 * 24 * 60
    interval = total_minutes / count

    decisions = []
    for i in range(count):
        variant = VARIANTS[i % len(VARIANTS)]  # Alternating ensures balance
        d = generate_decision(base_time, int(i * interval), variant)
        decisions.append(d)

    return decisions


def to_sql(decisions: list[dict]) -> str:
    """Convert decisions to INSERT SQL."""
    lines = []
    for d in decisions:
        input_t = str(d["input_tokens"]) if d["input_tokens"] is not None else "NULL"
        output_t = str(d["output_tokens"]) if d["output_tokens"] is not None else "NULL"
        cache = "TRUE" if d["cache_hit"] else "FALSE"
        created = d["created_at"].strftime("%Y-%m-%d %H:%M:%S+00")

        # Escape single quotes
        query = d["query"].replace("'", "''")
        decision = d["decision"].replace("'", "''")
        rationale = d["rationale"].replace("'", "''")
        pa = d["player_a_name"].replace("'", "''")
        pb = d["player_b_name"].replace("'", "''")

        lines.append(
            f"INSERT INTO decisions (id, sport, risk_mode, decision_type, query, "
            f"player_a_name, player_b_name, decision, confidence, rationale, source, "
            f"input_tokens, output_tokens, cache_hit, prompt_variant, created_at) VALUES ("
            f"'{d['id']}', '{d['sport']}', '{d['risk_mode']}', '{d['decision_type']}', "
            f"'{query}', '{pa}', '{pb}', '{decision}', '{d['confidence']}', "
            f"'{rationale}', '{d['source']}', {input_t}, {output_t}, {cache}, "
            f"'{d['prompt_variant']}', '{created}');"
        )

    return "\n".join(lines)


async def execute_seed(decisions: list[dict]) -> None:
    """Insert decisions directly via SQLAlchemy."""
    from models.database import Decision as DecisionModel
    from services.database import db_service

    if not db_service.is_configured:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    await db_service.connect()

    try:
        async with db_service.session() as session:
            for d in decisions:
                row = DecisionModel(
                    id=uuid.UUID(d["id"]),
                    sport=d["sport"],
                    risk_mode=d["risk_mode"],
                    decision_type=d["decision_type"],
                    query=d["query"],
                    player_a_name=d["player_a_name"],
                    player_b_name=d["player_b_name"],
                    decision=d["decision"],
                    confidence=d["confidence"],
                    rationale=d["rationale"],
                    source=d["source"],
                    input_tokens=d["input_tokens"],
                    output_tokens=d["output_tokens"],
                    cache_hit=d["cache_hit"],
                    prompt_variant=d["prompt_variant"],
                    created_at=d["created_at"],
                )
                session.add(row)
        print(f"Inserted {len(decisions)} decisions")
    finally:
        await db_service.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Seed experiment decision data")
    parser.add_argument(
        "--count", type=int, default=200, help="Number of decisions to generate"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute against DATABASE_URL instead of printing SQL",
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Write SQL to file instead of stdout"
    )
    args = parser.parse_args()

    random.seed(42)  # Reproducible
    decisions = generate_all(args.count)

    # Summary
    from collections import Counter

    variant_counts = Counter(d["prompt_variant"] for d in decisions)
    source_counts = Counter(d["source"] for d in decisions)
    sport_counts = Counter(d["sport"] for d in decisions)

    print(f"Generated {len(decisions)} decisions:", file=sys.stderr)
    print(f"  Variants: {dict(variant_counts)}", file=sys.stderr)
    print(f"  Sources:  {dict(source_counts)}", file=sys.stderr)
    print(f"  Sports:   {dict(sport_counts)}", file=sys.stderr)

    if args.execute:
        asyncio.run(execute_seed(decisions))
    else:
        sql = to_sql(decisions)
        if args.output:
            Path(args.output).write_text(sql)
            print(f"Wrote SQL to {args.output}", file=sys.stderr)
        else:
            print(sql)


if __name__ == "__main__":
    main()
