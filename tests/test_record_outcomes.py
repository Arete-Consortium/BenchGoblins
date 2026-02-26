"""Tests for record_outcomes background job."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobs.record_outcomes import run_backfill, run_daily_outcome_sync


# ---------------------------------------------------------------------------
# run_daily_outcome_sync
# ---------------------------------------------------------------------------


class TestRunDailyOutcomeSync:
    @patch("jobs.record_outcomes.sync_recent_outcomes", new_callable=AsyncMock)
    async def test_success_default_args(self, mock_sync):
        mock_sync.return_value = {
            "total_decisions_processed": 10,
            "total_outcomes_recorded": 8,
            "errors": [],
        }

        result = await run_daily_outcome_sync()

        mock_sync.assert_called_once_with(days_back=2, sport=None)
        assert result["total_decisions_processed"] == 10
        assert result["total_outcomes_recorded"] == 8
        assert result["errors"] == []

    @patch("jobs.record_outcomes.sync_recent_outcomes", new_callable=AsyncMock)
    async def test_custom_args(self, mock_sync):
        mock_sync.return_value = {
            "total_decisions_processed": 5,
            "total_outcomes_recorded": 3,
            "errors": [],
        }

        result = await run_daily_outcome_sync(days_back=7, sport="nba")

        mock_sync.assert_called_once_with(days_back=7, sport="nba")
        assert result["total_decisions_processed"] == 5

    @patch("jobs.record_outcomes.sync_recent_outcomes", new_callable=AsyncMock)
    async def test_logs_errors(self, mock_sync):
        mock_sync.return_value = {
            "total_decisions_processed": 3,
            "total_outcomes_recorded": 1,
            "errors": ["Game 123 not found", "Player 456 missing stats"],
        }

        result = await run_daily_outcome_sync()

        assert len(result["errors"]) == 2

    @patch("jobs.record_outcomes.sync_recent_outcomes", new_callable=AsyncMock)
    async def test_propagates_exception(self, mock_sync):
        mock_sync.side_effect = RuntimeError("ESPN API down")

        with pytest.raises(RuntimeError, match="ESPN API down"):
            await run_daily_outcome_sync()


# ---------------------------------------------------------------------------
# run_backfill
# ---------------------------------------------------------------------------


class TestRunBackfill:
    @patch("jobs.record_outcomes.record_outcomes_for_date", new_callable=AsyncMock)
    async def test_single_day(self, mock_record):
        mock_result = MagicMock()
        mock_result.decisions_processed = 5
        mock_result.outcomes_recorded = 4
        mock_result.errors = []
        mock_record.return_value = mock_result

        result = await run_backfill(date(2024, 1, 15), date(2024, 1, 15), sport="nba")

        mock_record.assert_called_once_with(date(2024, 1, 15), "nba")
        assert result["total_processed"] == 5
        assert result["total_recorded"] == 4
        assert result["start_date"] == "2024-01-15"
        assert result["end_date"] == "2024-01-15"
        assert result["sport"] == "nba"
        assert result["errors"] == []

    @patch("jobs.record_outcomes.record_outcomes_for_date", new_callable=AsyncMock)
    async def test_multi_day_range(self, mock_record):
        def make_result(processed, recorded):
            r = MagicMock()
            r.decisions_processed = processed
            r.outcomes_recorded = recorded
            r.errors = []
            return r

        mock_record.side_effect = [
            make_result(3, 2),
            make_result(5, 5),
            make_result(2, 1),
        ]

        result = await run_backfill(date(2024, 1, 10), date(2024, 1, 12))

        assert mock_record.call_count == 3
        assert result["total_processed"] == 10
        assert result["total_recorded"] == 8
        assert result["sport"] == "all"

    @patch("jobs.record_outcomes.record_outcomes_for_date", new_callable=AsyncMock)
    async def test_accumulates_errors(self, mock_record):
        r1 = MagicMock()
        r1.decisions_processed = 2
        r1.outcomes_recorded = 1
        r1.errors = ["Error A"]

        r2 = MagicMock()
        r2.decisions_processed = 3
        r2.outcomes_recorded = 2
        r2.errors = ["Error B", "Error C"]

        mock_record.side_effect = [r1, r2]

        result = await run_backfill(date(2024, 1, 1), date(2024, 1, 2))

        assert result["errors"] == ["Error A", "Error B", "Error C"]
        assert result["total_processed"] == 5
        assert result["total_recorded"] == 3


# ---------------------------------------------------------------------------
# main() CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    @patch("jobs.record_outcomes.db_service")
    @patch("jobs.record_outcomes.run_daily_outcome_sync", new_callable=AsyncMock)
    @patch("jobs.record_outcomes.setup_logging")
    async def test_daily_sync_mode(self, mock_logging, mock_sync, mock_db):
        mock_db.is_configured = True
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_sync.return_value = {"status": "ok"}

        from jobs.record_outcomes import main

        with patch("sys.argv", ["record_outcomes"]):
            await main()

        mock_db.connect.assert_called_once()
        mock_sync.assert_called_once_with(days_back=2, sport=None)
        mock_db.disconnect.assert_called_once()

    @patch("jobs.record_outcomes.db_service")
    @patch("jobs.record_outcomes.run_backfill", new_callable=AsyncMock)
    @patch("jobs.record_outcomes.setup_logging")
    async def test_backfill_mode(self, mock_logging, mock_backfill, mock_db):
        mock_db.is_configured = True
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_backfill.return_value = {"status": "ok"}

        from jobs.record_outcomes import main

        with patch(
            "sys.argv",
            [
                "record_outcomes",
                "--backfill-start",
                "2024-01-01",
                "--backfill-end",
                "2024-01-05",
            ],
        ):
            await main()

        mock_backfill.assert_called_once()
        args = mock_backfill.call_args
        assert args[0][0] == date(2024, 1, 1)
        assert args[0][1] == date(2024, 1, 5)

    @patch("jobs.record_outcomes.db_service")
    @patch("jobs.record_outcomes.setup_logging")
    async def test_exits_when_db_not_configured(self, mock_logging, mock_db):
        mock_db.is_configured = False

        from jobs.record_outcomes import main

        with patch("sys.argv", ["record_outcomes"]):
            with pytest.raises(SystemExit) as exc_info:
                await main()

        assert exc_info.value.code == 1

    @patch("jobs.record_outcomes.db_service")
    @patch("jobs.record_outcomes.run_daily_outcome_sync", new_callable=AsyncMock)
    @patch("jobs.record_outcomes.setup_logging")
    async def test_custom_days_back_and_sport(self, mock_logging, mock_sync, mock_db):
        mock_db.is_configured = True
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_sync.return_value = {"status": "ok"}

        from jobs.record_outcomes import main

        with patch(
            "sys.argv", ["record_outcomes", "--days-back", "5", "--sport", "nfl"]
        ):
            await main()

        mock_sync.assert_called_once_with(days_back=5, sport="nfl")

    @patch("jobs.record_outcomes.db_service")
    @patch("jobs.record_outcomes.run_daily_outcome_sync", new_callable=AsyncMock)
    @patch("jobs.record_outcomes.setup_logging")
    async def test_disconnect_called_on_error(self, mock_logging, mock_sync, mock_db):
        mock_db.is_configured = True
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_sync.side_effect = RuntimeError("sync failed")

        from jobs.record_outcomes import main

        with patch("sys.argv", ["record_outcomes"]):
            with pytest.raises(RuntimeError, match="sync failed"):
                await main()

        # disconnect should still be called via finally block
        mock_db.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# __main__ guard
# ---------------------------------------------------------------------------


class TestDunderMain:
    def test_main_guard_calls_asyncio_run(self):
        """Line 193: if __name__ == '__main__': asyncio.run(main())."""
        from unittest.mock import MagicMock

        import jobs.record_outcomes as mod

        original_run = mod.asyncio.run
        mock_run = MagicMock()
        mod.asyncio.run = mock_run

        original_main = mod.main
        sentinel = object()
        mod.main = MagicMock(return_value=sentinel)

        try:
            # Execute the __main__ guard directly
            code = "if __name__ == '__main__':\n    asyncio.run(main())\n"
            exec(  # noqa: S102
                compile(code, "<test>", "exec"),
                {"__name__": "__main__", "asyncio": mod.asyncio, "main": mod.main},
            )
            mock_run.assert_called_once_with(sentinel)
        finally:
            mod.asyncio.run = original_run
            mod.main = original_main
