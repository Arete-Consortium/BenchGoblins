"""
Tests for the referral service.

Covers: code generation, apply referral, self-referral prevention,
duplicate prevention, referral cap, stats, and pro expiry extension.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.referral import (
    MAX_REFERRALS_PER_USER,
    REWARD_DAYS,
    apply_referral,
    generate_referral_code,
    get_or_create_referral_code,
    get_referral_stats,
)

_DB = "services.referral.db_service"


def _mock_db_session():
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _make_user(id_=1, code="ABC12345", pro_expires=None, name="Test"):
    user = MagicMock()
    user.id = id_
    user.name = name
    user.referral_code = code
    user.referral_pro_expires_at = pro_expires
    return user


# =============================================================================
# CODE GENERATION
# =============================================================================


class TestGenerateCode:
    def test_generates_8_char_code(self):
        code = generate_referral_code()
        assert len(code) == 8
        assert code.isalnum()
        assert code.isupper() or code.isdigit()

    def test_generates_unique_codes(self):
        codes = {generate_referral_code() for _ in range(100)}
        assert len(codes) == 100


class TestGetOrCreateCode:
    @pytest.mark.asyncio
    async def test_returns_existing_code(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            # First query returns existing code
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = "EXISTING"
            mock_session.execute = AsyncMock(return_value=mock_result)

            code = await get_or_create_referral_code(1)
            assert code == "EXISTING"

    @pytest.mark.asyncio
    async def test_creates_new_code(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            # First query: no existing code, second: no collision
            mock_result_none = MagicMock()
            mock_result_none.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result_none)

            code = await get_or_create_referral_code(1)
            assert len(code) == 8
            mock_session.execute.assert_called()


# =============================================================================
# APPLY REFERRAL
# =============================================================================


class TestApplyReferral:
    @pytest.mark.asyncio
    async def test_invalid_code_returns_error(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            result = await apply_referral(2, "BADCODE1")
            assert result["success"] is False
            assert "Invalid" in result["error"]

    @pytest.mark.asyncio
    async def test_self_referral_blocked(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            referrer = _make_user(id_=1, code="SELF1234")
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = referrer
            mock_session.execute = AsyncMock(return_value=mock_result)

            result = await apply_referral(1, "SELF1234")
            assert result["success"] is False
            assert "yourself" in result["error"]

    @pytest.mark.asyncio
    async def test_duplicate_referral_blocked(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            referrer = _make_user(id_=1)
            existing_referral = MagicMock()

            # First call: find referrer, second: find existing referral
            call_count = 0

            async def mock_execute(query):
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                if call_count == 1:
                    result.scalar_one_or_none.return_value = referrer
                elif call_count == 2:
                    result.scalar_one_or_none.return_value = existing_referral
                return result

            mock_session.execute = mock_execute

            result = await apply_referral(2, "ABC12345")
            assert result["success"] is False
            assert "already" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_referral(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            referrer = _make_user(id_=1, name="Referrer", pro_expires=None)
            call_count = 0

            async def mock_execute(query):
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                if call_count == 1:
                    # Find referrer
                    result.scalar_one_or_none.return_value = referrer
                elif call_count == 2:
                    # No existing referral
                    result.scalar_one_or_none.return_value = None
                elif call_count == 3:
                    # Referral count (below cap)
                    result.scalars.return_value.all.return_value = []
                else:
                    # Updates
                    result = MagicMock()
                return result

            mock_session.execute = mock_execute

            result = await apply_referral(2, "ABC12345")
            assert result["success"] is True
            assert result["pro_days"] == REWARD_DAYS
            assert result["referrer_name"] == "Referrer"

    @pytest.mark.asyncio
    async def test_referral_cap_enforced(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            referrer = _make_user(id_=1)
            call_count = 0

            async def mock_execute(query):
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                if call_count == 1:
                    result.scalar_one_or_none.return_value = referrer
                elif call_count == 2:
                    result.scalar_one_or_none.return_value = None
                elif call_count == 3:
                    # At cap
                    result.scalars.return_value.all.return_value = [
                        MagicMock() for _ in range(MAX_REFERRALS_PER_USER)
                    ]
                return result

            mock_session.execute = mock_execute

            result = await apply_referral(2, "ABC12345")
            assert result["success"] is False
            assert "maximum" in result["error"]


# =============================================================================
# STATS
# =============================================================================


class TestReferralStats:
    @pytest.mark.asyncio
    async def test_no_user(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            mock_result = MagicMock()
            mock_result.one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            stats = await get_referral_stats(999)
            assert stats["referral_code"] is None
            assert stats["total_referrals"] == 0

    @pytest.mark.asyncio
    async def test_with_active_pro(self):
        with patch(_DB) as mock_db:
            mock_ctx, mock_session = _mock_db_session()
            mock_db.session.return_value = mock_ctx

            future = datetime.now(UTC) + timedelta(days=5)
            call_count = 0

            async def mock_execute(query):
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                if call_count == 1:
                    result.one_or_none.return_value = ("MYCODE12", future)
                elif call_count == 2:
                    result.scalars.return_value.all.return_value = [
                        MagicMock(),
                        MagicMock(),
                        MagicMock(),
                    ]
                return result

            mock_session.execute = mock_execute

            stats = await get_referral_stats(1)
            assert stats["referral_code"] == "MYCODE12"
            assert stats["total_referrals"] == 3
            assert stats["pro_days_remaining"] >= 4


# =============================================================================
# CONSTANTS
# =============================================================================


class TestConstants:
    def test_reward_days(self):
        assert REWARD_DAYS == 7

    def test_max_referrals(self):
        assert MAX_REFERRALS_PER_USER == 50
