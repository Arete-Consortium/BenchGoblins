"""
Commissioner Alerts Service — Proactive league health monitoring.

Generates alerts for commissioners about their league:
- Inactive members (no queries in 7+ days)
- Injured starters (starters with injury designations)
- Empty roster slots
- Trade deadline reminders
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    INACTIVE_MEMBER = "inactive_member"
    INJURED_STARTER = "injured_starter"
    EMPTY_SLOT = "empty_slot"
    ROSTER_IMBALANCE = "roster_imbalance"
    TRADE_DEADLINE = "trade_deadline"


class CommissionerAlert(BaseModel):
    """A single proactive alert for a commissioner."""

    category: AlertCategory
    severity: AlertSeverity
    title: str
    message: str
    affected_team: str | None = None
    action_url: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class LeagueAlertsSummary(BaseModel):
    """Summary of all alerts for a league."""

    league_id: int
    league_name: str
    alerts: list[CommissionerAlert] = Field(default_factory=list)
    total_alerts: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class CommissionerAlertService:
    """Generates proactive alerts for league commissioners."""

    async def generate_alerts(
        self,
        league_id: int,
        external_league_id: str,
    ) -> LeagueAlertsSummary:
        """
        Generate all alert types for a league.

        Fetches roster data from Sleeper and member activity from DB.
        """
        from services.sleeper import sleeper_service

        alerts: list[CommissionerAlert] = []
        league_name = f"League #{league_id}"

        # Fetch league info
        try:
            league = await sleeper_service.get_league(external_league_id)
            if league:
                league_name = league.name
        except Exception:
            logger.debug("Could not fetch league info for %s", external_league_id)

        # Fetch rosters
        rosters = []
        try:
            rosters = await sleeper_service.get_league_rosters(external_league_id) or []
        except Exception:
            logger.debug("Could not fetch rosters for %s", external_league_id)

        # Check roster health
        all_players = {}
        try:
            all_players = await sleeper_service.get_all_players("nfl")
        except Exception:
            logger.debug("Could not fetch player data")

        for roster in rosters:
            team_label = f"Roster #{roster.roster_id}"

            # Check injured starters
            if roster.starters and all_players:
                injured = self._check_injured_starters(roster.starters, all_players)
                for player_name, status in injured:
                    alerts.append(
                        CommissionerAlert(
                            category=AlertCategory.INJURED_STARTER,
                            severity=AlertSeverity.WARNING,
                            title=f"Injured starter: {player_name}",
                            message=f"{player_name} ({status}) is in {team_label}'s starting lineup.",
                            affected_team=team_label,
                        )
                    )

            # Check empty roster slots
            if roster.starters:
                empty_count = sum(1 for s in roster.starters if s == "0")
                if empty_count > 0:
                    alerts.append(
                        CommissionerAlert(
                            category=AlertCategory.EMPTY_SLOT,
                            severity=AlertSeverity.CRITICAL,
                            title=f"{empty_count} empty starter slot(s)",
                            message=f"{team_label} has {empty_count} empty starting position(s).",
                            affected_team=team_label,
                        )
                    )

            # Check roster imbalance (too few players)
            player_count = len(roster.players) if roster.players else 0
            if player_count < 8:
                alerts.append(
                    CommissionerAlert(
                        category=AlertCategory.ROSTER_IMBALANCE,
                        severity=AlertSeverity.WARNING,
                        title="Thin roster",
                        message=f"{team_label} only has {player_count} players. May need waiver attention.",
                        affected_team=team_label,
                    )
                )

        # Check inactive members
        inactive_alerts = await self._check_inactive_members(league_id)
        alerts.extend(inactive_alerts)

        # Count by severity
        critical = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
        warning = sum(1 for a in alerts if a.severity == AlertSeverity.WARNING)
        info = sum(1 for a in alerts if a.severity == AlertSeverity.INFO)

        return LeagueAlertsSummary(
            league_id=league_id,
            league_name=league_name,
            alerts=alerts,
            total_alerts=len(alerts),
            critical_count=critical,
            warning_count=warning,
            info_count=info,
        )

    def _check_injured_starters(
        self,
        starter_ids: list[str],
        all_players: dict,
    ) -> list[tuple[str, str]]:
        """Return list of (player_name, injury_status) for injured starters."""
        injured = []
        injury_designations = {"Out", "Doubtful", "IR", "PUP", "Suspended"}

        for pid in starter_ids:
            if pid == "0":
                continue
            pdata = all_players.get(pid, {})
            injury = pdata.get("injury_status")
            if injury and injury in injury_designations:
                name = pdata.get("full_name", f"Player {pid}")
                injured.append((name, injury))

        return injured

    async def _check_inactive_members(
        self,
        league_id: int,
    ) -> list[CommissionerAlert]:
        """Check for league members who haven't been active in 7+ days."""
        from services.database import db_service

        if not db_service.is_configured:
            return []

        alerts = []
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            from models.database import LeagueMembership

            async with db_service.session() as session:
                result = await session.execute(
                    select(LeagueMembership)
                    .options(selectinload(LeagueMembership.user))
                    .where(
                        LeagueMembership.league_id == league_id,
                        LeagueMembership.status == "active",
                    )
                )
                memberships = result.scalars().all()

                cutoff = datetime.now(UTC) - timedelta(days=7)
                for m in memberships:
                    user = m.user
                    if not user:
                        continue
                    if user.updated_at is None or user.updated_at < cutoff:
                        alerts.append(
                            CommissionerAlert(
                                category=AlertCategory.INACTIVE_MEMBER,
                                severity=AlertSeverity.INFO,
                                title=f"Inactive member: {user.name}",
                                message=f"{user.name} hasn't used BenchGoblins in 7+ days.",
                                affected_team=user.name,
                            )
                        )
        except Exception:
            logger.exception("Failed to check inactive members for league %s", league_id)

        return alerts


# Singleton
commissioner_alert_service = CommissionerAlertService()
