"""Extended tests for reference.py — async scraper methods with mocked HTTP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.reference import (
    BasketballReferenceService,
    ProFootballReferenceService,
    _rate_limited_get,
)


def mock_response(text="", url="http://test", status=200):
    resp = MagicMock()
    resp.text = text
    resp.url = url
    resp.status_code = status
    resp.raise_for_status.return_value = None
    return resp


# =========================================================================
# _rate_limited_get
# =========================================================================


class TestRateLimitedGet:
    @pytest.mark.asyncio
    async def test_success(self):
        client = AsyncMock()
        resp = mock_response(text="<html>ok</html>")
        client.get = AsyncMock(return_value=resp)

        import services.reference as ref

        ref._last_request_time = 0.0

        result = await _rate_limited_get(client, "http://example.com")
        assert result is not None
        assert result.text == "<html>ok</html>"

    @pytest.mark.asyncio
    async def test_error(self):
        client = AsyncMock()
        client.get = AsyncMock(side_effect=Exception("network error"))

        import services.reference as ref

        ref._last_request_time = 0.0

        result = await _rate_limited_get(client, "http://example.com")
        assert result is None


# =========================================================================
# BasketballReferenceService
# =========================================================================


class TestBBallRefGetAdvancedStats:
    @pytest.mark.asyncio
    async def test_success_with_season_row(self):
        svc = BasketballReferenceService()
        html = (
            '<table><tr id="advanced.2025" class="full">'
            '<td data-stat="per">25.1</td>'
            '<td data-stat="ts_pct">.625</td>'
            '<td data-stat="ws">12.3</td>'
            '<td data-stat="bpm">8.5</td>'
            '<td data-stat="vorp">6.2</td>'
            '<td data-stat="off_rtg">115.0</td>'
            '<td data-stat="def_rtg">108.0</td>'
            "</tr></table>"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("jamesle01", "2025")
            assert result is not None
            assert result.per == 25.1
            assert result.true_shooting_pct == 0.625
            assert result.win_shares == 12.3
            assert result.bpm == 8.5
            assert result.vorp == 6.2

    @pytest.mark.asyncio
    async def test_season_not_found(self):
        svc = BasketballReferenceService()
        html = "<html><body>No matching season</body></html>"

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("jamesle01", "2025")
            assert result is not None
            assert result.per == 0.0  # Empty stats returned

    @pytest.mark.asyncio
    async def test_request_failed(self):
        svc = BasketballReferenceService()

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await svc.get_advanced_stats("jamesle01", "2025")
            assert result is None


class TestBBallRefSearchPlayerSlug:
    @pytest.mark.asyncio
    async def test_redirect_to_player(self):
        svc = BasketballReferenceService()
        resp = mock_response(
            url="https://www.basketball-reference.com/players/j/jamesle01.html"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("LeBron James")
            assert result == "jamesle01"

    @pytest.mark.asyncio
    async def test_search_results_page(self):
        svc = BasketballReferenceService()
        resp = mock_response(
            text='<a href="/players/j/jamesle01.html">LeBron James</a>',
            url="https://www.basketball-reference.com/search/search.fcgi",
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("LeBron James")
            assert result == "jamesle01"

    @pytest.mark.asyncio
    async def test_no_results(self):
        svc = BasketballReferenceService()
        resp = mock_response(
            text="<html>No results</html>",
            url="https://www.basketball-reference.com/search/search.fcgi",
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("Nobody")
            assert result is None

    @pytest.mark.asyncio
    async def test_request_failed(self):
        svc = BasketballReferenceService()

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await svc.search_player_slug("test")
            assert result is None

    @pytest.mark.asyncio
    async def test_close(self):
        svc = BasketballReferenceService()
        with patch.object(svc.client, "aclose", new_callable=AsyncMock) as m:
            await svc.close()
            m.assert_called_once()


# =========================================================================
# ProFootballReferenceService
# =========================================================================


class TestPFRGetAdvancedStats:
    @pytest.mark.asyncio
    async def test_passing_stats(self):
        svc = ProFootballReferenceService()
        html = (
            '<table><tr id="passing.2024" class="full">'
            '<td data-stat="pass_rating">105.2</td>'
            '<td data-stat="qbr">72.5</td>'
            '<td data-stat="pass_adj_net_yds_per_att">7.8</td>'
            '<td data-stat="av">18</td>'
            "</tr></table>"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("MahoPa00", "2024")
            assert result is not None
            assert result.passer_rating == 105.2
            assert result.qbr == 72.5
            assert result.any_a == 7.8
            assert result.approximate_value == 18

    @pytest.mark.asyncio
    async def test_rushing_receiving_stats(self):
        svc = ProFootballReferenceService()
        html = (
            '<table><tr id="rushing_and_receiving.2024" class="full">'
            '<td data-stat="catch_pct">68.5</td>'
            '<td data-stat="rec_yac">320</td>'
            '<td data-stat="av">12</td>'
            "</tr></table>"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("HenrDe00", "2024")
            assert result is not None
            assert result.catch_pct == 68.5
            assert result.yards_after_catch == 320
            assert result.approximate_value == 12

    @pytest.mark.asyncio
    async def test_receiving_and_rushing_fallback(self):
        svc = ProFootballReferenceService()
        html = (
            '<table><tr id="receiving_and_rushing.2024" class="full">'
            '<td data-stat="catch_pct">75.0</td>'
            '<td data-stat="rec_yac">500</td>'
            '<td data-stat="av">15</td>'
            "</tr></table>"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("KelcTr00", "2024")
            assert result is not None
            assert result.catch_pct == 75.0

    @pytest.mark.asyncio
    async def test_no_matching_table(self):
        svc = ProFootballReferenceService()
        html = "<html><body>No matching tables</body></html>"

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=mock_response(text=html),
        ):
            result = await svc.get_advanced_stats("NobodyXX", "2024")
            assert result is not None
            assert result.passer_rating == 0.0  # Empty stats

    @pytest.mark.asyncio
    async def test_request_failed(self):
        svc = ProFootballReferenceService()

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await svc.get_advanced_stats("MahoPa00", "2024")
            assert result is None


class TestPFRSearchPlayerSlug:
    @pytest.mark.asyncio
    async def test_redirect_to_player(self):
        svc = ProFootballReferenceService()
        resp = mock_response(
            url="https://www.pro-football-reference.com/players/M/MahoPa00.htm"
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("Patrick Mahomes")
            assert result == "MahoPa00"

    @pytest.mark.asyncio
    async def test_search_results_page(self):
        svc = ProFootballReferenceService()
        resp = mock_response(
            text='<a href="/players/M/MahoPa00.htm">Patrick Mahomes</a>',
            url="https://www.pro-football-reference.com/search/search.fcgi",
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("Patrick Mahomes")
            assert result == "MahoPa00"

    @pytest.mark.asyncio
    async def test_no_results(self):
        svc = ProFootballReferenceService()
        resp = mock_response(
            text="<html>No results</html>",
            url="https://www.pro-football-reference.com/search/search.fcgi",
        )

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=resp,
        ):
            result = await svc.search_player_slug("Nobody")
            assert result is None

    @pytest.mark.asyncio
    async def test_request_failed(self):
        svc = ProFootballReferenceService()

        with patch(
            "services.reference._rate_limited_get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await svc.search_player_slug("test")
            assert result is None

    @pytest.mark.asyncio
    async def test_close(self):
        svc = ProFootballReferenceService()
        with patch.object(svc.client, "aclose", new_callable=AsyncMock) as m:
            await svc.close()
            m.assert_called_once()
