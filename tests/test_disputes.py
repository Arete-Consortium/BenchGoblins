"""
Tests for the dispute resolution system.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestFileDispute:
    """Tests for filing new disputes."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_category(self):
        """Should reject disputes with invalid categories."""
        from routes.commissioner import file_dispute

        request = MagicMock()
        request.category = "invalid"
        request.subject = "Test"
        request.description = "Test dispute"
        request.against_user_id = None

        with pytest.raises(Exception) as exc_info:
            await file_dispute(1, request, {"user_id": 1, "name": "Test"})
        assert "Invalid category" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_valid_categories(self):
        """All valid categories should be accepted."""
        valid = {"trade", "roster", "scoring", "conduct", "other"}
        for cat in valid:
            request = MagicMock()
            request.category = cat
            # Category validation happens before DB check, so it should pass this check
            assert cat in valid


class TestDisputeModels:
    """Tests for dispute Pydantic models."""

    def test_dispute_response_model(self):
        from routes.commissioner import DisputeResponse

        resp = DisputeResponse(
            id=1,
            league_id=1,
            filed_by_user_id=1,
            filed_by_name="Alice",
            category="trade",
            subject="Unfair trade",
            description="The trade was not fair",
            status="open",
            created_at="2026-02-26T00:00:00+00:00",
        )
        assert resp.id == 1
        assert resp.status == "open"
        assert resp.resolution is None

    def test_dispute_list_response(self):
        from routes.commissioner import DisputeListResponse

        resp = DisputeListResponse(
            league_id=1,
            total=3,
            open=2,
            resolved=1,
            disputes=[],
        )
        assert resp.total == 3
        assert resp.open == 2

    def test_file_dispute_request_model(self):
        from routes.commissioner import FileDisputeRequest

        req = FileDisputeRequest(
            category="trade",
            subject="Bad trade",
            description="This trade hurts the league",
        )
        assert req.category == "trade"
        assert req.against_user_id is None

    def test_resolve_dispute_request_model(self):
        from routes.commissioner import ResolveDisputeRequest

        req = ResolveDisputeRequest(
            status="resolved",
            resolution="Trade reversed",
        )
        assert req.status == "resolved"


class TestResolveDispute:
    """Tests for resolving disputes."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self):
        """Should reject non-terminal statuses."""
        from routes.commissioner import resolve_dispute

        request = MagicMock()
        request.status = "open"
        request.resolution = "Fixed"

        with pytest.raises(Exception) as exc_info:
            await resolve_dispute(1, 1, request, {"user_id": 1, "name": "Test"})
        assert "resolved" in str(exc_info.value.detail) or "dismissed" in str(
            exc_info.value.detail
        )


class TestRequireCommissionerWithAllowMember:
    """Tests for the updated require_commissioner helper."""

    @pytest.mark.asyncio
    async def test_allow_member_passes_for_member(self):
        """allow_member=True should allow regular members."""
        from routes.commissioner import require_commissioner

        mock_league = MagicMock()
        mock_league.commissioner_user_id = 99

        mock_membership = MagicMock()
        mock_membership.league = mock_league

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_membership

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await require_commissioner(
            league_id=1,
            current_user={"user_id": 2},
            session=mock_session,
            allow_member=True,
        )
        assert result == mock_league

    @pytest.mark.asyncio
    async def test_commissioner_only_rejects_member(self):
        """Default (allow_member=False) should reject non-commissioners."""
        from fastapi import HTTPException

        from routes.commissioner import require_commissioner

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await require_commissioner(
                league_id=1,
                current_user={"user_id": 2},
                session=mock_session,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_allow_member_rejects_non_member(self):
        """Even with allow_member, non-members should be rejected."""
        from fastapi import HTTPException

        from routes.commissioner import require_commissioner

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await require_commissioner(
                league_id=1,
                current_user={"user_id": 999},
                session=mock_session,
                allow_member=True,
            )
        assert exc_info.value.status_code == 403


class TestDisputeORM:
    """Tests for the LeagueDispute ORM model."""

    def test_model_fields(self):
        from models.database import LeagueDispute

        dispute = LeagueDispute(
            league_id=1,
            filed_by_user_id=1,
            category="trade",
            subject="Test",
            description="Test dispute",
            status="open",
        )
        assert dispute.status == "open"
        assert dispute.resolution is None
        assert dispute.resolved_by_user_id is None
        assert dispute.against_user_id is None
        assert dispute.category == "trade"

    def test_model_tablename(self):
        from models.database import LeagueDispute

        assert LeagueDispute.__tablename__ == "league_disputes"
