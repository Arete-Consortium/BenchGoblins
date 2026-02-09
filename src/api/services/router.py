"""
Decision Router — Routes queries to local scoring or Claude API.

Simple A vs B comparisons → Local (fast, free)
Complex trades, explanations, edge cases → Claude (nuanced, costs money)
"""

import re
from enum import Enum


class QueryComplexity(str, Enum):
    SIMPLE = "simple"  # Route to local
    COMPLEX = "complex"  # Route to Claude


# Patterns that indicate complex queries requiring Claude
COMPLEX_PATTERNS = [
    # Trade questions
    r"\btrade\b",
    r"\bgive up\b",
    r"\breceive\b",
    r"\bfor\b.*\band\b",  # "X for Y and Z"
    # Explanation requests
    r"\bwhy\b",
    r"\bexplain\b",
    r"\bhow come\b",
    r"\breason\b",
    # Multi-player scenarios
    r"\bpick \d+\b",  # "pick 2 from"
    r"\bchoose \d+\b",
    r"\brank\b",
    # Context-heavy questions
    r"\binjur",  # injury, injured
    r"\breturn\b",  # returning from injury
    r"\bbackup\b",
    r"\bhandcuff\b",
    # Waiver/roster moves
    r"\bwaiver\b",
    r"\bdrop\b.*\bfor\b",
    r"\bpick up\b",
    r"\badd\b.*\bdrop\b",
    # Long-term questions
    r"\brest of season\b",
    r"\bROS\b",
    r"\bplayoffs\b",
    r"\bkeeper\b",
    r"\bdynasty\b",
    # Uncertainty expressions
    r"\bnot sure\b",
    r"\bconfused\b",
    r"\btricky\b",
    r"\btough\b",
]

# Patterns that indicate simple A vs B comparisons
SIMPLE_PATTERNS = [
    r"^should i start\b",
    r"\bstart\b.*\bor\b",
    r"\bsit\b.*\bor\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bbetter\b.*\bor\b",
    r"\bover\b",
]


def classify_query(
    query: str,
    decision_type: str,
    player_a: str | None = None,
    player_b: str | None = None,
) -> QueryComplexity:
    """
    Classify a query as simple or complex.

    Simple queries are routed to local scoring (fast, free).
    Complex queries are routed to Claude (nuanced, paid).
    """
    query_lower = query.lower()

    # Explicit decision types that require Claude
    if decision_type in ("trade", "waiver", "explain"):
        return QueryComplexity.COMPLEX

    # Check for complex patterns
    for pattern in COMPLEX_PATTERNS:
        if re.search(pattern, query_lower):
            return QueryComplexity.COMPLEX

    # Check if it's a simple A vs B comparison
    has_two_players = player_a and player_b
    is_start_sit = decision_type == "start_sit"

    if is_start_sit and has_two_players:
        # Even with two players, some queries are complex
        word_count = len(query.split())
        if word_count > 20:  # Long queries usually need more reasoning
            return QueryComplexity.COMPLEX
        return QueryComplexity.SIMPLE

    # Check for simple patterns
    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, query_lower):
            # Only simple if we can identify two players
            if has_two_players:
                return QueryComplexity.SIMPLE

    # Default to Claude for ambiguous cases
    return QueryComplexity.COMPLEX


def extract_players_from_query(query: str) -> tuple[str | None, str | None]:
    """
    Attempt to extract two player names from a query.

    This is a heuristic and won't catch everything.
    Returns (player_a, player_b) or (None, None).
    """
    query_lower = query.lower()

    # Pattern: "X or Y"
    or_match = re.search(
        r"(?:start|sit|between)\s+([\w\s\.\-']+?)\s+or\s+([\w\s\.\-']+?)(?:\?|$|\s+(?:this|in|for))",
        query_lower,
    )
    if or_match:
        return or_match.group(1).strip(), or_match.group(2).strip()

    # Pattern: "X vs Y"
    vs_match = re.search(
        r"([\w\s\.\-']+?)\s+(?:vs\.?|versus)\s+([\w\s\.\-']+?)(?:\?|$)",
        query_lower,
    )
    if vs_match:
        return vs_match.group(1).strip(), vs_match.group(2).strip()

    return None, None


# Keywords that make a trade query too complex for local scoring
_TRADE_COMPLEX_KEYWORDS = [
    r"\bdynasty\b",
    r"\bkeeper\b",
    r"\brest of season\b",
    r"\bros\b",
    r"\binjur",  # injury, injured
    r"\bexplain\b",
    r"\bwhy\b",
    r"\bplayoffs\b",
    r"\blong.?term\b",
]


def classify_trade_query(query: str, trade_players_found: bool) -> QueryComplexity:
    """
    Classify a trade query as simple or complex.

    Returns SIMPLE when trade_players_found is True and no complex keywords
    are present. Returns COMPLEX otherwise (falls back to Claude).
    """
    if not trade_players_found:
        return QueryComplexity.COMPLEX

    query_lower = query.lower()
    for pattern in _TRADE_COMPLEX_KEYWORDS:
        if re.search(pattern, query_lower):
            return QueryComplexity.COMPLEX

    return QueryComplexity.SIMPLE
