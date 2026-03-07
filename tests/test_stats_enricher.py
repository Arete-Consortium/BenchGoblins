"""Tests for the advanced stats enricher service."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.reference import AdvancedNBAStats, AdvancedNFLStats
from services.stats_enricher import (
    _ENRICHMENT_TIMEOUT,
    format_nba_advanced,
    format_nfl_advanced,
    get_advanced_context,
)


# ---------- format_nba_advanced ----------


class TestFormatNBAAdvanced:
    """Tests for NBA advanced stats formatting."""

    def test_full_stats(self):
        stats = AdvancedNBAStats(
            player_name="jamesle01",
            season="2025",
            per=24.3,
            true_shooting_pct=0.612,
            win_shares=8.5,
            bpm=6.2,
            vorp=4.1,
        )
        result = format_nba_advanced(stats)
        assert result == "- Advanced: PER 24.3, TS% 0.612, WS 8.5, BPM +6.2, VORP 4.1"

    def test_partial_stats(self):
        stats = AdvancedNBAStats(
            player_name="test01",
            season="2025",
            per=15.0,
            true_shooting_pct=0.0,
            win_shares=0.0,
            bpm=-1.5,
            vorp=0.0,
        )
        result = format_nba_advanced(stats)
        assert result == "- Advanced: PER 15.0, BPM -1.5"

    def test_empty_stats_returns_empty(self):
        stats = AdvancedNBAStats(player_name="empty01", season="2025")
        result = format_nba_advanced(stats)
        assert result == ""


# ---------- format_nfl_advanced ----------


class TestFormatNFLAdvanced:
    """Tests for NFL advanced stats formatting."""

    def test_qb_stats(self):
        stats = AdvancedNFLStats(
            player_name="MahoPa00",
            season="2024",
            passer_rating=105.2,
            qbr=72.1,
            approximate_value=18,
        )
        result = format_nfl_advanced(stats)
        assert result == "- Advanced: RTG 105.2, QBR 72.1, AV 18"

    def test_receiver_stats(self):
        stats = AdvancedNFLStats(
            player_name="HillTy00",
            season="2024",
            catch_pct=68.3,
            yards_after_catch=412.0,
            approximate_value=12,
        )
        result = format_nfl_advanced(stats)
        assert result == "- Advanced: Catch% 68.3, YAC 412, AV 12"

    def test_empty_stats_returns_empty(self):
        stats = AdvancedNFLStats(player_name="empty01", season="2024")
        result = format_nfl_advanced(stats)
        assert result == ""


# ---------- get_advanced_context ----------


class TestGetAdvancedContext:
    """Tests for the main enrichment entry point."""

    @pytest.mark.asyncio
    async def test_nba_success(self):
        mock_stats = AdvancedNBAStats(
            player_name="jamesle01",
            season="2025",
            per=24.3,
            true_shooting_pct=0.612,
            bpm=6.2,
        )
        with (
            patch(
                "services.stats_enricher.bball_ref_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="jamesle01",
            ),
            patch(
                "services.stats_enricher.bball_ref_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ),
        ):
            result = await get_advanced_context("LeBron James", "nba")
        assert result is not None
        assert "PER 24.3" in result
        assert "BPM +6.2" in result

    @pytest.mark.asyncio
    async def test_nfl_success(self):
        mock_stats = AdvancedNFLStats(
            player_name="MahoPa00",
            season="2024",
            passer_rating=105.2,
            qbr=72.1,
        )
        with (
            patch(
                "services.stats_enricher.pfr_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="MahoPa00",
            ),
            patch(
                "services.stats_enricher.pfr_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ),
        ):
            result = await get_advanced_context("Patrick Mahomes", "nfl")
        assert result is not None
        assert "RTG 105.2" in result
        assert "QBR 72.1" in result

    @pytest.mark.asyncio
    async def test_unsupported_sport_returns_none(self):
        result = await get_advanced_context("Mike Trout", "mlb")
        assert result is None

    @pytest.mark.asyncio
    async def test_slug_not_found_returns_none(self):
        with patch(
            "services.stats_enricher.bball_ref_service.search_player_slug",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_advanced_context("Fake Player", "nba")
        assert result is None

    @pytest.mark.asyncio
    async def test_stats_not_found_returns_none(self):
        with (
            patch(
                "services.stats_enricher.pfr_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="FakePl00",
            ),
            patch(
                "services.stats_enricher.pfr_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await get_advanced_context("Fake Player", "nfl")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        with patch(
            "services.stats_enricher.bball_ref_service.search_player_slug",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network down"),
        ):
            result = await get_advanced_context("LeBron James", "nba")
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        async def slow_search(name):
            await asyncio.sleep(10)
            return "jamesle01"

        with patch(
            "services.stats_enricher.bball_ref_service.search_player_slug",
            side_effect=slow_search,
        ):
            result = await get_advanced_context("LeBron James", "nba")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_advanced_stats_returns_none(self):
        """When reference returns stats but all zeros, result is None."""
        empty_stats = AdvancedNBAStats(player_name="bench01", season="2025")
        with (
            patch(
                "services.stats_enricher.bball_ref_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="bench01",
            ),
            patch(
                "services.stats_enricher.bball_ref_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=empty_stats,
            ),
        ):
            result = await get_advanced_context("Bench Warmer", "nba")
        assert result is None

    @pytest.mark.asyncio
    async def test_nfl_empty_advanced_stats_returns_none(self):
        """NFL path: all-zero stats should also return None."""
        empty_stats = AdvancedNFLStats(player_name="bench01", season="2024")
        with (
            patch(
                "services.stats_enricher.pfr_service.search_player_slug",
                new_callable=AsyncMock,
                return_value="bench01",
            ),
            patch(
                "services.stats_enricher.pfr_service.get_advanced_stats",
                new_callable=AsyncMock,
                return_value=empty_stats,
            ),
        ):
            result = await get_advanced_context("Bench Warmer", "nfl")
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_constant_is_five_seconds(self):
        assert _ENRICHMENT_TIMEOUT == 5.0
