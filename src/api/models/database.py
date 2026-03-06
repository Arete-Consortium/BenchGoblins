"""
SQLAlchemy ORM Models for BenchGoblin.

Maps to the PostgreSQL schema in data/schema.sql.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account for authentication and subscription management."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    picture_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subscription_tier: Mapped[str] = mapped_column(String(50), default="free")  # free, pro
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queries_today: Mapped[int] = mapped_column(default=0)
    queries_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    verdicts_used: Mapped[int] = mapped_column(default=0)
    # Sleeper integration
    sleeper_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sleeper_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sleeper_league_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    roster_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sleeper_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ESPN Fantasy integration
    espn_swid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    espn_s2: Mapped[str | None] = mapped_column(Text, nullable=True)
    espn_league_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    espn_team_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    espn_sport: Mapped[str | None] = mapped_column(String(10), nullable=True)
    espn_roster_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    espn_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Yahoo Fantasy integration
    yahoo_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    yahoo_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    yahoo_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    yahoo_user_guid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    yahoo_league_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    yahoo_team_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    yahoo_sport: Mapped[str | None] = mapped_column(String(10), nullable=True)
    yahoo_roster_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    yahoo_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Referral system
    referral_code: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    referred_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    referral_pro_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    drip_emails_sent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("subscription_tier IN ('free', 'pro')", name="check_subscription_tier"),
        Index("idx_users_google_id", "google_id"),
        Index("idx_users_email", "email"),
        # Partial index for paid subscribers (skip majority 'free' rows)
        Index(
            "idx_users_subscription_tier",
            "subscription_tier",
            postgresql_where=text("subscription_tier != 'free'"),
        ),
    )


class Referral(Base):
    """Tracks referral relationships and reward status."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    referrer_reward_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    referred_reward_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("referrer_user_id", "referred_user_id"),)


class Player(Base):
    """ESPN player cache."""

    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    espn_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team: Mapped[str | None] = mapped_column(String(50))
    team_abbrev: Mapped[str | None] = mapped_column(String(10))
    position: Mapped[str | None] = mapped_column(String(20))
    sport: Mapped[str] = mapped_column(String(10), nullable=False)
    jersey: Mapped[str | None] = mapped_column(String(10))
    height: Mapped[str | None] = mapped_column(String(20))
    weight: Mapped[str | None] = mapped_column(String(20))
    age: Mapped[int | None] = mapped_column(Integer)
    experience: Mapped[int | None] = mapped_column(Integer)
    headshot_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    stats: Mapped[list["PlayerStats"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    game_logs: Mapped[list["GameLog"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    indices: Mapped[list["PlayerIndex"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer')", name="check_sport"),
        Index("idx_players_espn_id", "espn_id"),
        Index("idx_players_sport", "sport"),
        Index("idx_players_name", "name"),
        Index("idx_players_team", "team_abbrev"),
    )


class PlayerStats(Base):
    """Current season averages."""

    __tablename__ = "player_stats"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)

    # Common stats
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_started: Mapped[int] = mapped_column(Integer, default=0)

    # NBA stats
    minutes_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    points_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rebounds_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    assists_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    steals_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    blocks_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    turnovers_per_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    usage_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    field_goal_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    three_point_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    free_throw_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # NFL stats
    pass_yards: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    pass_tds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    pass_ints: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rush_yards: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    rush_tds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    receptions: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    receiving_yards: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    receiving_tds: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    targets: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    snap_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # MLB stats
    batting_avg: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    home_runs: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rbis: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    stolen_bases: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ops: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    era: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    wins: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    whip: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    # NHL stats
    goals: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    assists_nhl: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    plus_minus: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shots: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    save_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    goals_against_avg: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))

    # Soccer stats
    soccer_goals: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_assists: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_minutes: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    soccer_shots: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_shots_on_target: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_key_passes: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_tackles: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_interceptions: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_clean_sheets: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_saves: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_goals_conceded: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    soccer_xg: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    soccer_xa: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="stats")

    __table_args__ = (
        UniqueConstraint("player_id", "season", name="uq_player_stats_player_season"),
        Index("idx_player_stats_player", "player_id"),
        Index("idx_player_stats_season", "season"),
    )


class GameLog(Base):
    """Game-by-game stats for trend analysis."""

    __tablename__ = "game_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    game_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    opponent: Mapped[str | None] = mapped_column(String(10))
    home_away: Mapped[str | None] = mapped_column(String(1))
    result: Mapped[str | None] = mapped_column(String(1))

    # NBA game stats
    minutes: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    rebounds: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    steals: Mapped[int | None] = mapped_column(Integer)
    blocks: Mapped[int | None] = mapped_column(Integer)
    turnovers: Mapped[int | None] = mapped_column(Integer)
    fg_made: Mapped[int | None] = mapped_column(Integer)
    fg_attempted: Mapped[int | None] = mapped_column(Integer)
    three_made: Mapped[int | None] = mapped_column(Integer)
    three_attempted: Mapped[int | None] = mapped_column(Integer)
    ft_made: Mapped[int | None] = mapped_column(Integer)
    ft_attempted: Mapped[int | None] = mapped_column(Integer)

    # NFL game stats
    pass_yards_game: Mapped[int | None] = mapped_column(Integer)
    pass_tds_game: Mapped[int | None] = mapped_column(Integer)
    pass_ints_game: Mapped[int | None] = mapped_column(Integer)
    rush_yards_game: Mapped[int | None] = mapped_column(Integer)
    rush_tds_game: Mapped[int | None] = mapped_column(Integer)
    receptions_game: Mapped[int | None] = mapped_column(Integer)
    receiving_yards_game: Mapped[int | None] = mapped_column(Integer)
    receiving_tds_game: Mapped[int | None] = mapped_column(Integer)
    targets_game: Mapped[int | None] = mapped_column(Integer)
    snaps: Mapped[int | None] = mapped_column(Integer)
    snap_pct_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # MLB game stats
    at_bats: Mapped[int | None] = mapped_column(Integer)
    hits: Mapped[int | None] = mapped_column(Integer)
    home_runs_game: Mapped[int | None] = mapped_column(Integer)
    rbis_game: Mapped[int | None] = mapped_column(Integer)
    stolen_bases_game: Mapped[int | None] = mapped_column(Integer)
    walks: Mapped[int | None] = mapped_column(Integer)
    strikeouts_game: Mapped[int | None] = mapped_column(Integer)
    innings_pitched: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    earned_runs: Mapped[int | None] = mapped_column(Integer)

    # NHL game stats
    goals_game: Mapped[int | None] = mapped_column(Integer)
    assists_game: Mapped[int | None] = mapped_column(Integer)
    plus_minus_game: Mapped[int | None] = mapped_column(Integer)
    shots_game: Mapped[int | None] = mapped_column(Integer)
    time_on_ice: Mapped[int | None] = mapped_column(Integer)  # in seconds
    saves: Mapped[int | None] = mapped_column(Integer)
    goals_against: Mapped[int | None] = mapped_column(Integer)

    # Soccer game stats
    soccer_goals_game: Mapped[int | None] = mapped_column(Integer)
    soccer_assists_game: Mapped[int | None] = mapped_column(Integer)
    soccer_minutes_game: Mapped[int | None] = mapped_column(Integer)
    soccer_shots_game: Mapped[int | None] = mapped_column(Integer)
    soccer_shots_on_target_game: Mapped[int | None] = mapped_column(Integer)
    soccer_key_passes_game: Mapped[int | None] = mapped_column(Integer)
    soccer_tackles_game: Mapped[int | None] = mapped_column(Integer)
    soccer_interceptions_game: Mapped[int | None] = mapped_column(Integer)
    soccer_clean_sheet: Mapped[bool | None] = mapped_column(Boolean)
    soccer_saves_game: Mapped[int | None] = mapped_column(Integer)
    soccer_goals_conceded_game: Mapped[int | None] = mapped_column(Integer)
    soccer_xg_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    soccer_xa_game: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))

    # Fantasy points (calculated)
    fantasy_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="game_logs")

    __table_args__ = (
        UniqueConstraint("player_id", "game_date", name="uq_game_logs_player_date"),
        CheckConstraint("home_away IN ('H', 'A')", name="check_home_away"),
        CheckConstraint("result IN ('W', 'L')", name="check_result"),
        Index("idx_game_logs_player", "player_id"),
        Index("idx_game_logs_date", "game_date"),
        Index("idx_game_logs_player_date", "player_id", "game_date"),
    )


class PlayerIndex(Base):
    """Cached SCI/RMI/GIS/OD/MSF calculations."""

    __tablename__ = "player_indices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # The five qualitative indices
    sci: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rmi: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    gis: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    od: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    msf: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    # Composite scores per risk mode
    floor_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    median_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    ceiling_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    # Context
    opponent: Mapped[str | None] = mapped_column(String(10))
    game_date: Mapped[datetime | None] = mapped_column(DateTime)

    # Metadata
    calculation_inputs: Mapped[dict | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="indices")

    __table_args__ = (
        Index("idx_player_indices_player", "player_id"),
        Index("idx_player_indices_expires", "expires_at"),
        Index("idx_player_indices_matchup", "player_id", "opponent", "game_date"),
    )


class TeamDefense(Base):
    """Team defensive rankings for MSF calculation."""

    __tablename__ = "team_defense"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_abbrev: Mapped[str] = mapped_column(String(10), nullable=False)
    sport: Mapped[str] = mapped_column(String(10), nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)

    # General defensive metrics
    defensive_rating: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    points_allowed: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    pace: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # NBA position-specific
    vs_pg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_sg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_sf: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_pf: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # NFL position-specific
    vs_qb: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_rb: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_wr: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_te: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # Soccer position-specific
    vs_fwd: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_mid: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_def: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vs_gk: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    # Additional metrics
    turnovers_forced: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    sacks: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("team_abbrev", "sport", "season", name="uq_team_defense"),
        CheckConstraint(
            "sport IN ('nba', 'nfl', 'mlb', 'nhl', 'soccer')", name="check_defense_sport"
        ),
        Index("idx_team_defense_team", "team_abbrev"),
        Index("idx_team_defense_sport", "sport"),
    )


class Decision(Base):
    """Decision history for analytics."""

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Request context
    user_id: Mapped[str | None] = mapped_column(String(100))
    session_id: Mapped[str | None] = mapped_column(String(100))
    sport: Mapped[str] = mapped_column(String(10), nullable=False)
    risk_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(20), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # Players involved
    player_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id")
    )
    player_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id")
    )
    player_a_name: Mapped[str | None] = mapped_column(String(100))
    player_b_name: Mapped[str | None] = mapped_column(String(100))

    # Decision result
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), nullable=False)

    # Scores and indices
    score_a: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    score_b: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    margin: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    indices_a: Mapped[dict | None] = mapped_column(JSON)
    indices_b: Mapped[dict | None] = mapped_column(JSON)

    # Token usage tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)

    # A/B prompt testing
    prompt_variant: Mapped[str | None] = mapped_column(String(50))

    # Context
    league_type: Mapped[str | None] = mapped_column(String(50))
    player_context: Mapped[str | None] = mapped_column(Text)

    # Outcome tracking
    actual_outcome: Mapped[str | None] = mapped_column(String(20))
    actual_points_a: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    actual_points_b: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    player_a: Mapped[Optional["Player"]] = relationship(foreign_keys=[player_a_id])
    player_b: Mapped[Optional["Player"]] = relationship(foreign_keys=[player_b_id])

    __table_args__ = (
        CheckConstraint("risk_mode IN ('floor', 'median', 'ceiling')", name="check_risk_mode"),
        CheckConstraint("confidence IN ('low', 'medium', 'high')", name="check_confidence"),
        CheckConstraint("source IN ('local', 'claude')", name="check_source"),
        Index("idx_decisions_user", "user_id"),
        Index("idx_decisions_created", "created_at"),
        Index("idx_decisions_sport", "sport"),
        # Composite indexes for hot query paths
        Index("idx_decisions_sport_created", "sport", created_at.desc()),
        Index("idx_decisions_type_created", "decision_type", created_at.desc()),
        Index(
            "idx_decisions_variant",
            "prompt_variant",
            created_at.desc(),
            postgresql_where=text("prompt_variant IS NOT NULL"),
        ),
    )


class BudgetConfig(Base):
    """Budget configuration for Claude API spending limits."""

    __tablename__ = "budget_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monthly_limit_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text)
    discord_webhook_url: Mapped[str | None] = mapped_column(Text)
    last_alert_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_alert_percent: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("monthly_limit_usd >= 0", name="check_monthly_limit_positive"),
        CheckConstraint(
            "alert_threshold_pct >= 0 AND alert_threshold_pct <= 100",
            name="check_alert_threshold_range",
        ),
    )


class Session(Base):
    """Client session for credential and state management."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session identification
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(100))
    device_name: Mapped[str | None] = mapped_column(String(100))
    platform: Mapped[str] = mapped_column(String(20), nullable=False)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Security
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    # Future: User association
    user_id: Mapped[str | None] = mapped_column(String(100))

    # Relationships
    credentials: Mapped[list["SessionCredential"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("platform IN ('ios', 'android', 'web')", name="check_platform"),
        CheckConstraint("status IN ('active', 'expired', 'revoked')", name="check_session_status"),
        Index("idx_sessions_token", "session_token"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_expires", "expires_at"),
        # Composite index for session listing queries
        Index("idx_sessions_created_status", created_at.desc(), "status"),
    )


class SessionCredential(Base):
    """Encrypted credential storage per session."""

    __tablename__ = "session_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )

    # Credential identification
    provider: Mapped[str] = mapped_column(String(20), nullable=False)

    # Encrypted data (AES-256-GCM)
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_iv: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    session: Mapped["Session"] = relationship(back_populates="credentials")

    __table_args__ = (
        CheckConstraint("provider IN ('espn', 'yahoo', 'sleeper')", name="check_provider"),
        UniqueConstraint("session_id", "provider", name="uq_session_credentials"),
        Index("idx_session_credentials_session", "session_id"),
        Index("idx_session_credentials_provider", "provider"),
    )


class NewsletterSubscriber(Base):
    """Email list subscriber for marketing and pre-launch campaigns."""

    __tablename__ = "newsletter_subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sport_interest: Mapped[str | None] = mapped_column(String(50), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    __table_args__ = (
        Index("idx_newsletter_email", "email"),
        Index(
            "idx_newsletter_subscribed",
            subscribed_at.desc(),
            postgresql_where=text("unsubscribed_at IS NULL"),
        ),
    )


class DeviceToken(Base):
    """Registered device token for push notifications."""

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_device_tokens_token", "token"),
        Index(
            "idx_device_tokens_user",
            "user_id",
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )


class League(Base):
    """Managed league for commissioner/manager features."""

    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_league_id: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sport: Mapped[str] = mapped_column(String(20), nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    commissioner_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invite_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    # Relationships
    commissioner: Mapped[Optional["User"]] = relationship(foreign_keys=[commissioner_user_id])
    memberships: Mapped[list["LeagueMembership"]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("external_league_id", "platform", "season", name="uq_leagues_external"),
        CheckConstraint("platform IN ('sleeper', 'espn', 'yahoo')", name="check_league_platform"),
        CheckConstraint(
            "sport IN ('nfl', 'nba', 'mlb', 'nhl', 'soccer')", name="check_league_sport"
        ),
        Index("idx_leagues_commissioner", "commissioner_user_id"),
        Index(
            "idx_leagues_invite_code",
            "invite_code",
            postgresql_where=text("invite_code IS NOT NULL"),
        ),
        Index("idx_leagues_platform_season", "platform", "season"),
    )


class LeagueMatchup(Base):
    """Cached weekly matchup results from Sleeper for rivalry tracking."""

    __tablename__ = "league_matchups"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_id_a: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_id_b: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id_a: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id_b: Mapped[str] = mapped_column(String(100), nullable=False)
    points_a: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    points_b: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    winner_owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    league: Mapped["League"] = relationship(foreign_keys=[league_id])

    __table_args__ = (
        UniqueConstraint(
            "league_id",
            "season",
            "week",
            "roster_id_a",
            "roster_id_b",
            name="uq_league_matchup",
        ),
        Index("idx_league_matchups_league", "league_id", "season"),
        Index("idx_league_matchups_owners", "owner_id_a", "owner_id_b"),
    )


class LeagueMembership(Base):
    """User membership in a managed league."""

    __tablename__ = "league_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    external_team_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    # Relationships
    league: Mapped["League"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("league_id", "user_id", name="uq_league_memberships"),
        CheckConstraint("role IN ('commissioner', 'member')", name="check_membership_role"),
        CheckConstraint(
            "status IN ('active', 'invited', 'removed')", name="check_membership_status"
        ),
        Index("idx_league_memberships_league", "league_id"),
        Index("idx_league_memberships_user", "user_id"),
        Index(
            "idx_league_memberships_status",
            "status",
            postgresql_where=text("status = 'active'"),
        ),
    )


class LeagueDispute(Base):
    """Commissioner dispute resolution record."""

    __tablename__ = "league_disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leagues.id", ondelete="CASCADE"), nullable=False
    )
    filed_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    against_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    league: Mapped["League"] = relationship(foreign_keys=[league_id])
    filed_by: Mapped["User"] = relationship(foreign_keys=[filed_by_user_id])
    against: Mapped["User"] = relationship(foreign_keys=[against_user_id])
    resolved_by: Mapped["User"] = relationship(foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "category IN ('trade', 'roster', 'scoring', 'conduct', 'other')",
            name="check_dispute_category",
        ),
        CheckConstraint(
            "status IN ('open', 'under_review', 'resolved', 'dismissed')",
            name="check_dispute_status",
        ),
        Index("idx_league_disputes_league", "league_id", "status"),
        Index("idx_league_disputes_user", "filed_by_user_id"),
    )


class WeeklyRecap(Base):
    """AI-generated weekly recap for a user."""

    __tablename__ = "weekly_recaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sport: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Aggregated stats
    total_decisions: Mapped[int] = mapped_column(Integer, default=0)
    correct_decisions: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_decisions: Mapped[int] = mapped_column(Integer, default=0)
    pending_decisions: Mapped[int] = mapped_column(Integer, default=0)
    accuracy_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    avg_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    most_asked_sport: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # AI-generated content
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "sport", name="uq_weekly_recaps_user_week"),
        Index("idx_weekly_recaps_user", "user_id", week_start.desc()),
        Index("idx_weekly_recaps_created", created_at.desc()),
    )


class NotificationLog(Base):
    """Log of sent notifications for dedup and cooldown tracking."""

    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        Index("idx_notification_log_user_type", "user_id", "notification_type", "sent_at"),
    )
