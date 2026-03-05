"""
Tests for the free-tier query limit enforcement.

Verifies that _check_and_increment_query_count correctly tracks,
limits, and resets the weekly query counter for free-tier users.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckAndIncrementQueryCount:
    """Tests for _check_and_increment_query_count."""

    def _make_user(
        self,
        queries_today: int = 0,
        tier: str = "free",
        reset_at: datetime | None = None,
    ) -> MagicMock:
        user = MagicMock()
        user.id = 1
        user.subscription_tier = tier
        user.queries_today = queries_today
        user.queries_reset_at = reset_at or datetime.now(UTC)
        user.stripe_customer_id = None
        return user

    def _patch_session(self, user: MagicMock | None):
        """Create a mock db_service.session() that returns the given user."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        return mock_session

    @pytest.mark.asyncio
    async def test_allows_first_query(self):
        """First query on fresh account should be allowed."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=0)
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 1
        assert limit == 5

    @pytest.mark.asyncio
    async def test_blocks_at_limit(self):
        """Should block when queries_today == weekly_limit."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=5)
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is False
        assert count == 5
        assert limit == 5

    @pytest.mark.asyncio
    async def test_allows_fifth_query(self):
        """Fifth query (index 4) should still be allowed."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=4)
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 5
        assert limit == 5

    @pytest.mark.asyncio
    async def test_resets_after_7_days(self):
        """Counter should reset to 0 after 7 days."""
        from main import _check_and_increment_query_count

        # Reset happened 8 days ago, counter at 5
        user = self._make_user(
            queries_today=5,
            reset_at=datetime.now(UTC) - timedelta(days=8),
        )
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 1  # Reset to 0, then incremented to 1

    @pytest.mark.asyncio
    async def test_handles_naive_timestamp(self):
        """Should handle timezone-naive timestamps from DB without crashing."""
        from main import _check_and_increment_query_count

        # Simulate TIMESTAMP (naive) from PostgreSQL — must be within 7 days
        naive_reset_at = (datetime.now(UTC) - timedelta(days=1)).replace(tzinfo=None)
        user = self._make_user(queries_today=3, reset_at=naive_reset_at)
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            # Should not raise TypeError: can't subtract offset-naive and offset-aware datetimes
            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 4

    @pytest.mark.asyncio
    async def test_handles_naive_timestamp_reset(self):
        """Naive timestamp from 8+ days ago should trigger reset."""
        from main import _check_and_increment_query_count

        # Simulate old naive TIMESTAMP from PostgreSQL (> 7 days ago)
        naive_reset_at = (datetime.now(UTC) - timedelta(days=10)).replace(tzinfo=None)
        user = self._make_user(queries_today=5, reset_at=naive_reset_at)
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 1  # Reset to 0, then incremented

    @pytest.mark.asyncio
    async def test_pro_unlimited(self):
        """Pro tier should always be allowed."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=100, tier="pro")
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert limit == -1

    @pytest.mark.asyncio
    async def test_db_not_configured_allows(self):
        """When DB is not configured, should allow all queries."""
        from main import _check_and_increment_query_count

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = False

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 0

    @pytest.mark.asyncio
    async def test_user_not_found_allows(self):
        """When user is not in DB, should allow (graceful degradation)."""
        from main import _check_and_increment_query_count

        mock_session = self._patch_session(None)  # No user found

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx

            allowed, count, limit = await _check_and_increment_query_count(999)

        assert allowed is True

    @pytest.mark.asyncio
    async def test_league_pro_inherits_unlimited(self):
        """User in a Pro league should get unlimited queries."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=10, tier="free")
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=True)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert limit == -1

    @pytest.mark.asyncio
    async def test_none_reset_at_triggers_reset(self):
        """None queries_reset_at should trigger counter reset."""
        from main import _check_and_increment_query_count

        user = self._make_user(queries_today=5, reset_at=None)
        user.queries_reset_at = None
        mock_session = self._patch_session(user)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("main.db_service") as mock_db,
            patch("main.stripe_billing") as mock_billing,
        ):
            mock_db.is_configured = True
            mock_db.session.return_value = mock_ctx
            mock_billing.is_league_pro = AsyncMock(return_value=False)

            allowed, count, limit = await _check_and_increment_query_count(1)

        assert allowed is True
        assert count == 1  # Reset to 0, then incremented
