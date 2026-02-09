"""
User Engagement Metrics Service.

Computes session, query, retention, feature usage, and depth metrics
from pre-fetched Decision, Session, and User data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionMetrics:
    """Session activity metrics."""

    active_count: int = 0
    avg_duration_minutes: float = 0.0
    by_platform: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.by_platform.values()) if self.by_platform else self.active_count


@dataclass
class QueryPatternMetrics:
    """Query volume and pattern metrics."""

    by_date: dict[str, int] = field(default_factory=dict)
    popular_sports: dict[str, int] = field(default_factory=dict)
    popular_decision_types: dict[str, int] = field(default_factory=dict)
    popular_risk_modes: dict[str, int] = field(default_factory=dict)

    @property
    def total_queries(self) -> int:
        return sum(self.by_date.values())

    @property
    def avg_queries_per_day(self) -> float:
        if not self.by_date:
            return 0.0
        return round(self.total_queries / len(self.by_date), 1)


@dataclass
class RetentionMetrics:
    """User retention and active user metrics."""

    new_users: int = 0
    returning_users: int = 0
    dau: int = 0
    wau: int = 0
    mau: int = 0

    @property
    def total_users(self) -> int:
        return self.new_users + self.returning_users


@dataclass
class FeatureUsageMetrics:
    """Routing and cache feature usage."""

    local_routing_count: int = 0
    claude_routing_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def local_routing_pct(self) -> float:
        total = self.local_routing_count + self.claude_routing_count
        if total == 0:
            return 0.0
        return round(self.local_routing_count / total * 100, 1)

    @property
    def claude_routing_pct(self) -> float:
        total = self.local_routing_count + self.claude_routing_count
        if total == 0:
            return 0.0
        return round(self.claude_routing_count / total * 100, 1)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return round(self.cache_hits / total * 100, 1)


@dataclass
class EngagementDepthMetrics:
    """Per-session and per-user query depth."""

    avg_queries_per_session: float = 0.0
    avg_queries_per_user_per_day: float = 0.0
    active_users: int = 0
    active_sessions: int = 0


@dataclass
class EngagementMetrics:
    """Composite engagement metrics for a time period."""

    period_start: datetime | None = None
    period_end: datetime | None = None
    sessions: SessionMetrics = field(default_factory=SessionMetrics)
    queries: QueryPatternMetrics = field(default_factory=QueryPatternMetrics)
    retention: RetentionMetrics = field(default_factory=RetentionMetrics)
    features: FeatureUsageMetrics = field(default_factory=FeatureUsageMetrics)
    depth: EngagementDepthMetrics = field(default_factory=EngagementDepthMetrics)


class EngagementTracker:
    """
    Computes engagement metrics from pre-fetched data.

    All computation is pure Python — no DB calls inside.
    """

    def compute_metrics(
        self,
        decisions: list[dict],
        sessions: list[dict],
        users: list[dict],
        period_start: datetime,
        period_end: datetime,
    ) -> EngagementMetrics:
        metrics = EngagementMetrics(
            period_start=period_start,
            period_end=period_end,
        )
        metrics.sessions = self._compute_session_metrics(sessions)
        metrics.queries = self._compute_query_metrics(decisions)
        metrics.retention = self._compute_retention_metrics(decisions, users, period_start)
        metrics.features = self._compute_feature_metrics(decisions)
        metrics.depth = self._compute_depth_metrics(decisions, sessions)
        return metrics

    def _compute_session_metrics(self, sessions: list[dict]) -> SessionMetrics:
        m = SessionMetrics()
        if not sessions:
            return m

        active = [s for s in sessions if s.get("status") == "active"]
        m.active_count = len(active)

        # Avg duration from created_at to last_active_at
        durations: list[float] = []
        for s in sessions:
            created = s.get("created_at")
            last_active = s.get("last_active_at")
            if created and last_active and last_active > created:
                delta = (last_active - created).total_seconds() / 60.0
                durations.append(delta)
        m.avg_duration_minutes = round(sum(durations) / len(durations), 1) if durations else 0.0

        # By platform
        platforms = Counter(s.get("platform", "unknown") for s in sessions)
        m.by_platform = dict(platforms)

        return m

    def _compute_query_metrics(self, decisions: list[dict]) -> QueryPatternMetrics:
        m = QueryPatternMetrics()
        if not decisions:
            return m

        dates: Counter[str] = Counter()
        sports: Counter[str] = Counter()
        dtypes: Counter[str] = Counter()
        rmodes: Counter[str] = Counter()

        for d in decisions:
            created = d.get("created_at")
            if created:
                dates[created.strftime("%Y-%m-%d")] += 1
            sport = d.get("sport")
            if sport:
                sports[sport] += 1
            dtype = d.get("decision_type")
            if dtype:
                dtypes[dtype] += 1
            rmode = d.get("risk_mode")
            if rmode:
                rmodes[rmode] += 1

        m.by_date = dict(dates)
        m.popular_sports = dict(sports.most_common())
        m.popular_decision_types = dict(dtypes.most_common())
        m.popular_risk_modes = dict(rmodes.most_common())
        return m

    def _compute_retention_metrics(
        self, decisions: list[dict], users: list[dict], period_start: datetime
    ) -> RetentionMetrics:
        m = RetentionMetrics()
        if not users:
            return m

        new = 0
        returning = 0
        for u in users:
            created = u.get("created_at")
            if created and created >= period_start:
                new += 1
            else:
                returning += 1
        m.new_users = new
        m.returning_users = returning

        # DAU/WAU/MAU from unique user_ids in decisions
        user_ids_by_date: dict[str, set[str]] = {}
        for d in decisions:
            uid = d.get("user_id")
            created = d.get("created_at")
            if uid and created:
                date_key = created.strftime("%Y-%m-%d")
                user_ids_by_date.setdefault(date_key, set()).add(uid)

        if user_ids_by_date:
            # DAU = average unique users per day
            daily_counts = [len(uids) for uids in user_ids_by_date.values()]
            m.dau = round(sum(daily_counts) / len(daily_counts))
            # WAU = unique users in last 7 days of period
            sorted_dates = sorted(user_ids_by_date.keys(), reverse=True)
            week_dates = sorted_dates[:7]
            week_users: set[str] = set()
            for date_key in week_dates:
                week_users.update(user_ids_by_date[date_key])
            m.wau = len(week_users)
            # MAU = all unique users in period
            all_users: set[str] = set()
            for uids in user_ids_by_date.values():
                all_users.update(uids)
            m.mau = len(all_users)

        return m

    def _compute_feature_metrics(self, decisions: list[dict]) -> FeatureUsageMetrics:
        m = FeatureUsageMetrics()
        for d in decisions:
            source = d.get("source", "local")
            if source == "claude":
                m.claude_routing_count += 1
            else:
                m.local_routing_count += 1
            cache_hit = d.get("cache_hit", False)
            if cache_hit:
                m.cache_hits += 1
            else:
                m.cache_misses += 1
        return m

    def _compute_depth_metrics(
        self, decisions: list[dict], sessions: list[dict]
    ) -> EngagementDepthMetrics:
        m = EngagementDepthMetrics()
        if not decisions:
            return m

        # Queries per session
        session_ids = {s.get("session_id") or str(s.get("id", "")) for s in sessions if s}
        queries_per_session: Counter[str] = Counter()
        queries_per_user_day: Counter[str] = Counter()
        unique_users: set[str] = set()

        for d in decisions:
            sid = d.get("session_id")
            if sid:
                queries_per_session[sid] += 1
            uid = d.get("user_id")
            created = d.get("created_at")
            if uid:
                unique_users.add(uid)
                if created:
                    day_key = f"{uid}:{created.strftime('%Y-%m-%d')}"
                    queries_per_user_day[day_key] += 1

        m.active_sessions = len(queries_per_session) if queries_per_session else len(session_ids)
        m.active_users = len(unique_users)

        if queries_per_session:
            total_q = sum(queries_per_session.values())
            m.avg_queries_per_session = round(total_q / len(queries_per_session), 1)

        if queries_per_user_day:
            total_q = sum(queries_per_user_day.values())
            m.avg_queries_per_user_per_day = round(total_q / len(queries_per_user_day), 1)

        return m


# Global singleton
engagement_tracker = EngagementTracker()
