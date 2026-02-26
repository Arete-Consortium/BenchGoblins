"""
Query Classifier — Smart sports query detection for fantasy sports API.

Uses multiple signals to classify queries:
- Keyword density (sports terms / total words)
- Question patterns (start/sit, trade, waiver)
- Off-topic patterns (expanded blocklist)
- Player name detection (capitalized names, common patterns)
- Sport-specific phrases
"""

import re
from dataclasses import dataclass
from enum import Enum


class QueryCategory(str, Enum):
    """Classification categories for incoming queries."""

    SPORTS = "sports"  # Allow - clearly fantasy sports related
    OFF_TOPIC = "off_topic"  # Reject - clearly not sports
    AMBIGUOUS = "ambiguous"  # Allow with logging - unclear intent


@dataclass
class ClassificationResult:
    """Result of query classification."""

    category: QueryCategory
    confidence: float  # 0.0 to 1.0
    reason: str


# ---------------------------------------------------------------------------
# Sports Keywords (expanded and categorized)
# ---------------------------------------------------------------------------

# Fantasy action verbs
FANTASY_ACTIONS = {
    "start",
    "sit",
    "trade",
    "trades",
    "waiver",
    "waivers",
    "add",
    "drop",
    "bench",
    "lineup",
    "lineups",
    "roster",
    "rosters",
    "pick",
    "picks",
    "draft",
    "stash",
    "stream",
    "streaming",
    "hold",
    "sell",
    "buy",
    "flex",
    "pickup",
    "pickups",
    "claim",
    "sleeper",
    "rankings",
    "ranking",
}

# Fantasy question patterns
FANTASY_PATTERNS = {
    "should i start",
    "who should i start",
    "who do i start",
    "should i pick",
    "who should i pick",
    "who should i draft",
    "trade x for y",
    "trade value",
    "waiver wire",
    "pick up",
    "start or sit",
    "rest of season",
    "ros",
    "keeper league",
    "dynasty",
    "redraft",
    "playoff push",
    "must start",
    "boom or bust",
    "sit this week",
    "this week",
    "this matchup",
    "line up",
    "best lineup",
    "premium picks",
    "top picks",
    "best picks",
    "going into",
}

# Sport and league terms
SPORT_TERMS = {
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "basketball",
    "football",
    "baseball",
    "hockey",
    "fantasy",
    "player",
    "players",
    "team",
    "matchup",
    "season",
    "playoff",
    "playoffs",
    "game",
    "week",
    "wnba",
    "mls",
    "soccer",
    "premier league",
    "epl",
    "fpl",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
    "ucl",
}

# Position terms
POSITIONS = {
    # NFL
    "qb",
    "rb",
    "wr",
    "te",
    "flex",
    "dst",
    "defense",
    "kicker",
    "superflex",
    # NBA
    "pg",
    "sg",
    "sf",
    "pf",
    "center",
    "guard",
    "forward",
    "utility",
    # MLB
    "pitcher",
    "catcher",
    "outfield",
    "infield",
    "dh",
    "sp",
    "rp",
    "closer",
    # NHL
    "goalie",
    "winger",
    "defenseman",
    # Soccer
    "goalkeeper",
    "striker",
    "midfielder",
    "defender",
    "fullback",
    "winger",
    "attacker",
    "keeper",
}

# Stat terms
STAT_TERMS = {
    "points",
    "rebounds",
    "assists",
    "touchdowns",
    "yards",
    "receptions",
    "targets",
    "carries",
    "rushing",
    "passing",
    "receiving",
    "scoring",
    "ppg",
    "rpg",
    "apg",
    "ppr",
    "half-ppr",
    "standard",
    "steals",
    "blocks",
    "turnovers",
    "completions",
    "interceptions",
    "fumbles",
    "sacks",
    "saves",
    "strikeouts",
    "era",
    "whip",
    "batting",
    "home runs",
    "rbi",
    "obp",
    "ops",
    "goals",
    "fpts",
    "fantasy points",
    "xg",
    "xa",
    "clean sheet",
    "clean sheets",
    "key passes",
    "tackles",
    "interceptions",
    "shots on target",
    "minutes played",
    "appearances",
}

# Injury/status terms
INJURY_TERMS = {
    "injury",
    "injured",
    "questionable",
    "doubtful",
    "out",
    "gtd",
    "game-time decision",
    "ir",
    "dnp",
    "limited",
    "probable",
    "healthy",
    "return",
    "returning",
    "back from",
    "cleared",
}

# Context terms
CONTEXT_TERMS = {
    "vs",
    "versus",
    "against",
    "tonight",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "monday night",
    "sunday night",
    "thursday night",
    "primetime",
    "away",
    "home",
    "matchup",
}

# All sports keywords combined
ALL_SPORTS_KEYWORDS = (
    FANTASY_ACTIONS | SPORT_TERMS | POSITIONS | STAT_TERMS | INJURY_TERMS | CONTEXT_TERMS
)

# ---------------------------------------------------------------------------
# Off-Topic Patterns (blocklist)
# ---------------------------------------------------------------------------

# Personal advice / relationship
PERSONAL_PATTERNS = [
    r"\bhow do i look\b",
    r"\bwhat should i say\b",
    r"\bhow to talk to\b",
    r"\bdating\b",
    r"\bgirlfriend\b",
    r"\bboyfriend\b",
    r"\brelationship\b",
    r"\bbreakup\b",
    r"\bmarriage\b",
    r"\bdivorce\b",
    r"\bfamily\b.*\badvice\b",
    r"\bself.?help\b",
    r"\bmental health\b",
    r"\bdepression\b",
    r"\banxiety\b",
]

# Code / programming
CODE_PATTERNS = [
    r"\bwrite me\b.*\bcode\b",
    r"\bwrite a\b.*\bscript\b",
    r"\bcode\b.*\bfor\b.*\bme\b",
    r"\bprogramming\b",
    r"\bpython\b",
    r"\bjavascript\b",
    r"\bjava\b(?!.*(jaguars|jacksonville))",  # Java but not Jaguars
    r"\brust\b(?!.*(ing|y|belt))",  # Rust language, not rusty
    r"\btypescript\b",
    r"\bhtml\b",
    r"\bcss\b",
    r"\bsql\b",
    r"\bapi\b.*\bimplementation\b",
    r"\bbug\b.*\bfix\b",
    r"\bdebug\b",
    r"\bfunction\b.*\breturn\b",
    r"\bclass\b.*\bmethod\b",
]

# General knowledge / trivia
KNOWLEDGE_PATTERNS = [
    r"\bexplain how\b.*\bworks\b",
    r"\bwhat is the meaning\b",
    r"\btell me a joke\b",
    r"\bwho is the president\b",
    r"\bcapital of\b",
    r"\bwhat is\b.*\bdefinition\b",
    r"\bhistory of\b",
    r"\bhow was\b.*\binvented\b",
    r"\bwhy is the sky\b",
    r"\bexplain\b.*\bscience\b",
    r"\bmath\b.*\bproblem\b",
    r"\bsolve\b.*\bequation\b",
    r"\bphysics\b",
    r"\bchemistry\b",
    r"\bbiology\b",
]

# Creative writing
CREATIVE_PATTERNS = [
    r"\bwrite me\b",
    r"\bwrite a\b.*\bstory\b",
    r"\bwrite a\b.*\bpoem\b",
    r"\bwrite a\b.*\bsong\b",
    r"\bwrite a\b.*\bessay\b",
    r"\bcreative writing\b",
    r"\bfiction\b",
    r"\bnovel\b",
    r"\bshort story\b",
    r"\bscreenplay\b",
    r"\bhaiku\b",
]

# Business / professional (non-sports)
BUSINESS_PATTERNS = [
    r"\bresume\b",
    r"\bcover letter\b",
    r"\bjob interview\b",
    r"\bsalary\b.*\bnegotiation\b",
    r"\bstock\b.*\bmarket\b",
    r"\bcrypto\b",
    r"\bbitcoin\b",
    r"\binvest\b(?!.*(start|sit|roster))",  # invest but not in fantasy context
    r"\b401k\b",
    r"\bmortgage\b",
    r"\btaxes\b",
]

# Health / medical (non-sports injury)
MEDICAL_PATTERNS = [
    r"\bdiagnosis\b",
    r"\bsymptoms\b",
    r"\bmedication\b",
    r"\bprescription\b",
    r"\bdoctor\b",
    r"\bhospital\b",
    r"\bdisease\b",
    r"\btreatment\b(?!.*(table|injured reserve))",  # not IR/treatment table
]

# Recipe / cooking
COOKING_PATTERNS = [
    r"\brecipe\b",
    r"\bcooking\b",
    r"\bbaking\b",
    r"\bingredients\b",
    r"\bhow to make\b.*\bfood\b",
    r"\bcalories\b",
    r"\bnutrition\b(?!.*(athlete|player))",
]

# Travel / geography
TRAVEL_PATTERNS = [
    r"\btravel\b(?!.*(team|roster))",  # travel but not team travel
    r"\bvacation\b",
    r"\btourist\b",
    r"\bhotel\b",
    r"\bflight\b(?!.*(path|trajectory))",
    r"\bdestination\b",
]

ALL_OFF_TOPIC_PATTERNS = (
    PERSONAL_PATTERNS
    + CODE_PATTERNS
    + KNOWLEDGE_PATTERNS
    + CREATIVE_PATTERNS
    + BUSINESS_PATTERNS
    + MEDICAL_PATTERNS
    + COOKING_PATTERNS
    + TRAVEL_PATTERNS
)

# ---------------------------------------------------------------------------
# Player Name Detection
# ---------------------------------------------------------------------------

# Common first names that appear in queries (sample)
COMMON_PLAYER_FIRST_NAMES = {
    "lebron",
    "steph",
    "stephen",
    "kevin",
    "james",
    "anthony",
    "tyrese",
    "jalen",
    "jayson",
    "luka",
    "giannis",
    "joel",
    "nikola",
    "devin",
    "kyrie",
    "patrick",
    "josh",
    "travis",
    "ceedee",
    "cd",
    "jamarr",
    "justin",
    "tyreek",
    "davante",
    "cooper",
    "saquon",
    "christian",
    "austin",
    "derrick",
    "bijan",
    "breece",
    "isiah",
    "lamar",
    "jared",
    "dak",
    "tua",
    "burrow",
    "hurts",
    "allen",
    "mahomes",
    "shohei",
    "ohtani",
    "mookie",
    "aaron",
    "mike",
    "trout",
    "connor",
    "mcdavid",
    "auston",
    "matthews",
    # Soccer
    "haaland",
    "erling",
    "salah",
    "mohamed",
    "mbappé",
    "mbappe",
    "vinicius",
    "bellingham",
    "jude",
    "saka",
    "bukayo",
    "palmer",
    "cole",
    "foden",
    "phil",
    "messi",
    "ronaldo",
}

# Patterns that suggest player names (Firstname Lastname)
PLAYER_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+(?:'[A-Z]?[a-z]+)?)\b")

# "X or Y" pattern common in start/sit questions
PLAYER_COMPARISON_PATTERN = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:or|vs\.?|versus)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.IGNORECASE,
)


def _detect_player_names(query: str) -> list[str]:
    """Detect potential player names in the query."""
    names = []

    # Check for "Firstname Lastname" patterns
    for match in PLAYER_NAME_PATTERN.finditer(query):
        full_name = match.group(0)
        first_name = match.group(1).lower()
        # Skip common non-name capitalized words
        if first_name not in {"should", "will", "can", "the", "who", "what", "how"}:
            names.append(full_name)

    # Check for known first names
    query_lower = query.lower()
    for name in COMMON_PLAYER_FIRST_NAMES:
        if name in query_lower:
            names.append(name)

    return names


def _check_player_comparison(query: str) -> bool:
    """Check if query has a player comparison pattern (X or Y, X vs Y)."""
    return bool(PLAYER_COMPARISON_PATTERN.search(query))


# ---------------------------------------------------------------------------
# Fantasy Question Patterns
# ---------------------------------------------------------------------------

FANTASY_QUESTION_PATTERNS = [
    r"^should i start\b",
    r"^who should i\b",
    r"^who do i start\b",
    r"\bstart\b.*\bor\b.*\b(sit|bench)\b",
    r"\bstart\b.*\bover\b",
    r"\bsit\b.*\bor\b.*\bstart\b",
    r"\bpick up\b.*\bfrom waiver\b",
    r"\bwaiver wire\b",
    r"\bdrop\b.*\bfor\b",
    r"\btrade\b.*\bfor\b",
    r"\baccept\b.*\btrade\b",
    r"\bwho wins\b.*\btrade\b",
    r"\b(player|guy)\b.*\b(better|worse)\b",
    r"\bwho.*(better|worse)\b.*\b(ros|rest of season|playoffs)\b",
    r"\bppr\b.*\b(value|rankings?)\b",
    r"\bstandard\b.*\b(value|rankings?)\b",
    r"\bflex\b.*\b(play|start)\b",
    r"\bkeeper\b.*\b(league|value)\b",
    r"\bdynasty\b.*\b(value|trade|rankings?)\b",
]


def _check_fantasy_question_patterns(query: str) -> bool:
    """Check if query matches fantasy question patterns."""
    query_lower = query.lower()
    for pattern in FANTASY_QUESTION_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    return False


def _check_fantasy_phrase_patterns(query: str) -> bool:
    """Check for multi-word fantasy phrases."""
    query_lower = query.lower()
    for phrase in FANTASY_PATTERNS:
        if phrase in query_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Classification Logic
# ---------------------------------------------------------------------------


def _calculate_keyword_density(query: str) -> tuple[float, int, int]:
    """
    Calculate sports keyword density.

    Returns (density, sports_word_count, total_word_count).
    """
    # Normalize query
    query_lower = query.lower()
    # Remove punctuation for word splitting
    words = re.findall(r"\b\w+\b", query_lower)
    total_words = len(words)

    if total_words == 0:
        return 0.0, 0, 0

    sports_words = sum(1 for w in words if w in ALL_SPORTS_KEYWORDS)
    density = sports_words / total_words

    return density, sports_words, total_words


def _check_off_topic_patterns(query: str) -> tuple[bool, str | None]:
    """
    Check if query matches any off-topic patterns.

    Returns (is_off_topic, matched_pattern).
    """
    query_lower = query.lower()
    for pattern in ALL_OFF_TOPIC_PATTERNS:
        if re.search(pattern, query_lower):
            return True, pattern
    return False, None


def classify_query(query: str) -> ClassificationResult:
    """
    Classify a query as SPORTS, OFF_TOPIC, or AMBIGUOUS.

    Uses multiple signals:
    1. Off-topic pattern blocklist (explicit rejection)
    2. Fantasy question patterns (high confidence sports)
    3. Player name detection (suggests sports context)
    4. Keyword density (sports terms / total words)

    Returns ClassificationResult with category, confidence, and reason.
    """
    if not query or not query.strip():
        return ClassificationResult(
            category=QueryCategory.OFF_TOPIC,
            confidence=1.0,
            reason="Empty query",
        )

    query = query.strip()

    # 1. Check explicit off-topic patterns first (blocklist)
    is_off_topic, matched_pattern = _check_off_topic_patterns(query)
    if is_off_topic:
        return ClassificationResult(
            category=QueryCategory.OFF_TOPIC,
            confidence=0.95,
            reason=f"Matched off-topic pattern: {matched_pattern}",
        )

    # 2. Check fantasy question patterns (strong sports signal)
    if _check_fantasy_question_patterns(query):
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.95,
            reason="Matched fantasy question pattern",
        )

    # 3. Check for fantasy phrases
    if _check_fantasy_phrase_patterns(query):
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.90,
            reason="Contains fantasy phrase",
        )

    # 4. Calculate keyword density
    density, sports_words, total_words = _calculate_keyword_density(query)

    # 5. Detect player names
    player_names = _detect_player_names(query)
    has_player_comparison = _check_player_comparison(query)

    # Decision logic based on signals
    # High density + player names = definitely sports
    if density >= 0.3 and len(player_names) >= 1:
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.90,
            reason=f"High keyword density ({density:.2f}) with player names",
        )

    # Player comparison pattern = likely sports
    if has_player_comparison:
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.85,
            reason="Contains player comparison pattern (X or/vs Y)",
        )

    # Multiple player names = likely sports
    if len(player_names) >= 2:
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.80,
            reason=f"Contains multiple player names: {player_names[:2]}",
        )

    # Medium density = sports
    if density >= 0.2:
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.75,
            reason=f"Medium keyword density ({density:.2f})",
        )

    # Low density with at least some sports keywords + player name
    if density >= 0.1 and len(player_names) >= 1:
        return ClassificationResult(
            category=QueryCategory.SPORTS,
            confidence=0.70,
            reason=f"Low keyword density ({density:.2f}) but has player name",
        )

    # Some sports keywords present
    if sports_words >= 2:
        return ClassificationResult(
            category=QueryCategory.AMBIGUOUS,
            confidence=0.50,
            reason=f"Found {sports_words} sports keywords but low density",
        )

    # Single sports keyword
    if sports_words == 1:
        return ClassificationResult(
            category=QueryCategory.AMBIGUOUS,
            confidence=0.40,
            reason="Only 1 sports keyword found",
        )

    # No sports signals
    return ClassificationResult(
        category=QueryCategory.OFF_TOPIC,
        confidence=0.70,
        reason="No sports keywords or patterns detected",
    )


def is_sports_query(query: str) -> tuple[bool, str]:
    """
    Simplified interface for main.py compatibility.

    Returns (is_allowed, reason).
    - SPORTS: (True, reason)
    - AMBIGUOUS: (True, reason) - allowed but should be logged
    - OFF_TOPIC: (False, reason)
    """
    result = classify_query(query)

    if result.category == QueryCategory.OFF_TOPIC:
        return False, result.reason

    # Both SPORTS and AMBIGUOUS are allowed
    return True, result.reason
