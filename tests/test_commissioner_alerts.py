"""
Tests for the commissioner alerts service.

Covers: alert generation for injured starters, empty slots,
roster imbalance, inactive members, and summary counts.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.commissioner_alerts import (
    AlertCategory,
    AlertSeverity,
    CommissionerAlert,
    CommissionerAlertService,
    LeagueAlertsSummary,
)

_SLEEPER = "services.sleeper.sleeper_service"
_DB = "services.database.db_service"


def _make_roster(
    roster_id=1,
    owner_id="user1",
    starters=None,
    players=None,
):
    """Build a mock Sleeper roster."""
    r = MagicMock()
    r.roster_id = roster_id
    r.owner_id = owner_id
    r.starters = starters or []
    r.players = players or []
    return r


# =============================================================================
# MODELS
# =============================================================================


class TestAlertModels:
    """Test Pydantic models."""

    def test_commissioner_alert_defaults(self):
        alert = CommissionerAlert(
            category=AlertCategory.INJURED_STARTER,
            severity=AlertSeverity.WARNING,
            title="Test",
            message="Test message",
        )
        assert alert.affected_team is None
        assert alert.action_url is None
        assert alert.generated_at is not None

    def test_league_alerts_summary_defaults(self):
        summary = LeagueAlertsSummary(
            league_id=1,
            league_name="Test League",
        )
        assert summary.alerts == []
        assert summary.total_alerts == 0
        assert summary.critical_count == 0


# =============================================================================
# INJURED STARTERS
# =============================================================================


class TestInjuredStarters:
    """Test injured starter detection."""

    def test_detects_injured_starter(self):
        service = CommissionerAlertService()
        players = {
            "123": {"full_name": "Joe Hurt", "injury_status": "Out"},
            "456": {"full_name": "Sam Fine", "injury_status": None},
        }
        result = service._check_injured_starters(["123", "456"], players)
        assert len(result) == 1
        assert result[0] == ("Joe Hurt", "Out")

    def test_ignores_healthy_players(self):
        service = CommissionerAlertService()
        players = {
            "123": {"full_name": "Sam Fine", "injury_status": None},
        }
        result = service._check_injured_starters(["123"], players)
        assert result == []

    def test_ignores_questionable(self):
        service = CommissionerAlertService()
        players = {
            "123": {"full_name": "Maybe Guy", "injury_status": "Questionable"},
        }
        result = service._check_injured_starters(["123"], players)
        assert result == []

    def test_skips_empty_slot_id(self):
        service = CommissionerAlertService()
        players = {"123": {"full_name": "Test", "injury_status": "Out"}}
        result = service._check_injured_starters(["0", "123"], players)
        assert len(result) == 1

    def test_handles_missing_player(self):
        service = CommissionerAlertService()
        result = service._check_injured_starters(["999"], {})
        assert result == []

    def test_detects_multiple_designations(self):
        service = CommissionerAlertService()
        players = {
            "1": {"full_name": "A", "injury_status": "Out"},
            "2": {"full_name": "B", "injury_status": "Doubtful"},
            "3": {"full_name": "C", "injury_status": "IR"},
            "4": {"full_name": "D", "injury_status": "PUP"},
            "5": {"full_name": "E", "injury_status": "Suspended"},
        }
        result = service._check_injured_starters(["1", "2", "3", "4", "5"], players)
        assert len(result) == 5


# =============================================================================
# GENERATE ALERTS
# =============================================================================


class TestGenerateAlerts:
    """Test full alert generation."""

    @pytest.mark.asyncio
    async def test_empty_league_no_alerts(self):
        service = CommissionerAlertService()

        with (
            patch(_SLEEPER) as mock_sleeper,
            patch.object(
                service,
                "_check_inactive_members",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_sleeper.get_league = AsyncMock(return_value=None)
            mock_sleeper.get_league_rosters = AsyncMock(return_value=[])
            mock_sleeper.get_all_players = AsyncMock(return_value={})

            summary = await service.generate_alerts(1, "ext123")

        assert summary.total_alerts == 0

    @pytest.mark.asyncio
    async def test_detects_empty_starter_slots(self):
        service = CommissionerAlertService()
        roster = _make_roster(starters=["123", "0", "0"], players=["123"])

        with (
            patch(_SLEEPER) as mock_sleeper,
            patch.object(
                service,
                "_check_inactive_members",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_sleeper.get_league = AsyncMock(return_value=None)
            mock_sleeper.get_league_rosters = AsyncMock(return_value=[roster])
            mock_sleeper.get_all_players = AsyncMock(return_value={})

            summary = await service.generate_alerts(1, "ext123")

        empty_alerts = [
            a for a in summary.alerts if a.category == AlertCategory.EMPTY_SLOT
        ]
        assert len(empty_alerts) == 1
        assert summary.critical_count == 1

    @pytest.mark.asyncio
    async def test_detects_thin_roster(self):
        service = CommissionerAlertService()
        roster = _make_roster(starters=["1", "2"], players=["1", "2", "3"])

        with (
            patch(_SLEEPER) as mock_sleeper,
            patch.object(
                service,
                "_check_inactive_members",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_sleeper.get_league = AsyncMock(return_value=None)
            mock_sleeper.get_league_rosters = AsyncMock(return_value=[roster])
            mock_sleeper.get_all_players = AsyncMock(return_value={})

            summary = await service.generate_alerts(1, "ext123")

        imbalance_alerts = [
            a for a in summary.alerts if a.category == AlertCategory.ROSTER_IMBALANCE
        ]
        assert len(imbalance_alerts) == 1

    @pytest.mark.asyncio
    async def test_includes_inactive_members(self):
        service = CommissionerAlertService()
        inactive_alert = CommissionerAlert(
            category=AlertCategory.INACTIVE_MEMBER,
            severity=AlertSeverity.INFO,
            title="Inactive: Bob",
            message="Bob hasn't used BenchGoblins in 7+ days.",
        )

        with (
            patch(_SLEEPER) as mock_sleeper,
            patch.object(
                service,
                "_check_inactive_members",
                new_callable=AsyncMock,
                return_value=[inactive_alert],
            ),
        ):
            mock_sleeper.get_league = AsyncMock(return_value=None)
            mock_sleeper.get_league_rosters = AsyncMock(return_value=[])
            mock_sleeper.get_all_players = AsyncMock(return_value={})

            summary = await service.generate_alerts(1, "ext123")

        assert summary.info_count == 1
        assert summary.total_alerts == 1

    @pytest.mark.asyncio
    async def test_severity_counts(self):
        service = CommissionerAlertService()
        roster = _make_roster(
            starters=["123", "0"],
            players=["123", "456"],
        )
        players = {"123": {"full_name": "Hurt Guy", "injury_status": "Out"}}

        with (
            patch(_SLEEPER) as mock_sleeper,
            patch.object(
                service,
                "_check_inactive_members",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_sleeper.get_league = AsyncMock(return_value=None)
            mock_sleeper.get_league_rosters = AsyncMock(return_value=[roster])
            mock_sleeper.get_all_players = AsyncMock(return_value=players)

            summary = await service.generate_alerts(1, "ext123")

        # 1 empty slot (critical) + 1 injured starter (warning) + 1 thin roster (warning)
        assert summary.critical_count >= 1
        assert summary.warning_count >= 1


# =============================================================================
# INACTIVE MEMBERS
# =============================================================================


class TestInactiveMembers:
    """Test inactive member detection."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_not_configured(self):
        service = CommissionerAlertService()
        with patch(_DB) as mock_db:
            mock_db.is_configured = False
            result = await service._check_inactive_members(1)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_db_error(self, caplog):
        service = CommissionerAlertService()
        with patch(_DB) as mock_db:
            mock_db.is_configured = True
            mock_session = AsyncMock()
            mock_session.execute.side_effect = RuntimeError("DB error")
            mock_db.session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_db.session.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await service._check_inactive_members(1)
        assert result == []
        assert "Failed to check inactive members" in caplog.text
