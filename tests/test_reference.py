"""Tests for Basketball Reference and Pro Football Reference scrapers."""

from services.reference import (
    AdvancedNBAStats,
    AdvancedNFLStats,
    _extract_stat,
    _parse_float,
    _parse_int,
)


class TestParseHelpers:
    def test_parse_float_valid(self):
        assert _parse_float("25.3") == 25.3
        assert _parse_float(" 0.585 ") == 0.585

    def test_parse_float_invalid(self):
        assert _parse_float("") == 0.0
        assert _parse_float("N/A") == 0.0

    def test_parse_int_valid(self):
        assert _parse_int("42") == 42
        assert _parse_int(" 7 ") == 7

    def test_parse_int_invalid(self):
        assert _parse_int("") == 0
        assert _parse_int("abc") == 0


class TestExtractStat:
    def test_extract_existing_stat(self):
        html = '<td data-stat="per" class="right">24.5</td>'
        assert _extract_stat(html, "per") == "24.5"

    def test_extract_missing_stat(self):
        html = '<td data-stat="per" class="right">24.5</td>'
        assert _extract_stat(html, "bpm") == ""

    def test_extract_from_row(self):
        html = (
            '<td data-stat="per">25.1</td>'
            '<td data-stat="ts_pct">.625</td>'
            '<td data-stat="ws">12.3</td>'
        )
        assert _extract_stat(html, "per") == "25.1"
        assert _extract_stat(html, "ts_pct") == ".625"
        assert _extract_stat(html, "ws") == "12.3"


class TestAdvancedNBAStats:
    def test_defaults(self):
        stats = AdvancedNBAStats(player_name="test", season="2025")
        assert stats.per == 0.0
        assert stats.true_shooting_pct == 0.0
        assert stats.bpm == 0.0
        assert stats.vorp == 0.0

    def test_populated(self):
        stats = AdvancedNBAStats(
            player_name="jamesle01",
            season="2025",
            per=25.1,
            true_shooting_pct=0.625,
            win_shares=12.3,
            bpm=8.5,
            vorp=6.2,
        )
        assert stats.per == 25.1
        assert stats.bpm == 8.5


class TestAdvancedNFLStats:
    def test_defaults(self):
        stats = AdvancedNFLStats(player_name="test", season="2024")
        assert stats.passer_rating == 0.0
        assert stats.qbr == 0.0
        assert stats.approximate_value == 0

    def test_populated(self):
        stats = AdvancedNFLStats(
            player_name="MahoPa00",
            season="2024",
            passer_rating=105.2,
            any_a=7.8,
            approximate_value=18,
        )
        assert stats.passer_rating == 105.2
        assert stats.approximate_value == 18
