"""
Tests for the require_pro FastAPI dependency.

Covers: pro tier pass-through, free tier rejection, league-inherited pro,
stripe exception fallback, DB not configured, and user not found.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes.auth import require_pro


def _make_user(tier="pro"):
    user = MagicMock()
    user.id = 1
    user.subscription_tier = tier
    return user


def _mock_db_session():
    mock_session = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


_AUTH_USER = {"user_id": 1, "email": "test@example.com", "name": "Test"}


class TestRequirePro:
    """Test the require_pro dependency."""

    @pytest.mark.asyncio
    async def test_pro_user_passes(self):
        with (
            patch("routes.auth.db_service") as mock_db,
            patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = _make_user("pro")

            result = await require_pro(current_user=_AUTH_USER)
            assert result == _AUTH_USER

    @pytest.mark.asyncio
    async def test_free_user_blocked(self):
        with (
            patch("routes.auth.db_service") as mock_db,
            patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get,
            patch("services.stripe_billing.is_league_pro", new_callable=AsyncMock) as mock_lp,
        ):
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = _make_user("free")
            mock_lp.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await require_pro(current_user=_AUTH_USER)
            assert exc_info.value.status_code == 403
            assert "Pro feature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_league_inherited_pro_passes(self):
        with (
            patch("routes.auth.db_service") as mock_db,
            patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get,
            patch("services.stripe_billing.is_league_pro", new_callable=AsyncMock) as mock_lp,
        ):
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = _make_user("free")
            mock_lp.return_value = True

            result = await require_pro(current_user=_AUTH_USER)
            assert result == _AUTH_USER

    @pytest.mark.asyncio
    async def test_stripe_exception_falls_back_to_free(self):
        with (
            patch("routes.auth.db_service") as mock_db,
            patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get,
            patch("services.stripe_billing.is_league_pro", new_callable=AsyncMock) as mock_lp,
        ):
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = _make_user("free")
            mock_lp.side_effect = RuntimeError("stripe down")

            with pytest.raises(HTTPException) as exc_info:
                await require_pro(current_user=_AUTH_USER)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_db_not_configured(self):
        with patch("routes.auth.db_service") as mock_db:
            mock_db.is_configured = False

            with pytest.raises(HTTPException) as exc_info:
                await require_pro(current_user=_AUTH_USER)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        with (
            patch("routes.auth.db_service") as mock_db,
            patch("routes.auth.get_user_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_db.is_configured = True
            mock_ctx, _ = _mock_db_session()
            mock_db.session.return_value = mock_ctx
            mock_get.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await require_pro(current_user=_AUTH_USER)
            assert exc_info.value.status_code == 404
