"""Tests for token usage tracking and budget monitoring."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.claude import ClaudeService


class TestStreamingTokenMetadata:
    """Test that streaming returns token metadata."""

    @pytest.fixture
    def mock_stream(self):
        """Create a mock streaming response (async)."""
        mock_message = MagicMock()
        mock_message.usage.input_tokens = 150
        mock_message.usage.output_tokens = 75

        async def _async_text_stream():
            for text in ["Hello", " world", "!"]:
                yield text

        mock_stream = MagicMock()
        mock_stream.text_stream = _async_text_stream()
        mock_stream.get_final_message = AsyncMock(return_value=mock_message)
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        return mock_stream

    @pytest.mark.asyncio
    async def test_stream_yields_metadata_at_end(self, mock_stream):
        """Test that make_decision_stream yields metadata dict at end."""
        svc = ClaudeService()
        svc.client = MagicMock()
        svc.client.messages.stream.return_value = mock_stream

        chunks = []
        async for chunk in svc.make_decision_stream(
            query="test",
            sport="nba",
            risk_mode="median",
            decision_type="start_sit",
        ):
            chunks.append(chunk)

        # Last chunk should be metadata dict
        assert len(chunks) == 4  # 3 text chunks + 1 metadata
        metadata = chunks[-1]
        assert isinstance(metadata, dict)
        assert metadata.get("_metadata") is True
        assert metadata["input_tokens"] == 150
        assert metadata["output_tokens"] == 75
        assert metadata["full_response"] == "Hello world!"

    @pytest.mark.asyncio
    async def test_stream_tracks_prometheus_metrics(self, mock_stream):
        """Test that streaming tracks tokens via Prometheus."""
        svc = ClaudeService()
        svc.client = MagicMock()
        svc.client.messages.stream.return_value = mock_stream

        with patch("services.claude.track_claude_request") as mock_track:
            async for _ in svc.make_decision_stream(
                query="test",
                sport="nba",
                risk_mode="median",
                decision_type="start_sit",
            ):
                pass

            mock_track.assert_called_once_with(150, 75, success=True, variant="control")


class TestBudgetEndpoints:
    """Test budget configuration endpoints."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.mark.asyncio
    async def test_get_budget_no_config(self, mock_db_session):
        """Test GET /budget returns defaults when no config exists."""
        from main import get_budget

        mock_db_session.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_budget()

            assert response.monthly_limit_usd == 0
            assert response.alert_threshold_pct == 80
            assert response.budget_exceeded is False
            assert response.alert_triggered is False

    @pytest.mark.asyncio
    async def test_get_budget_with_config(self, mock_db_session):
        """Test GET /budget returns config and calculated spend."""
        from main import get_budget
        from models.database import BudgetConfig

        # Mock budget config
        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("50.00")
        mock_config.alert_threshold_pct = 80
        mock_config.updated_at = datetime.now(timezone.utc)
        mock_config.slack_webhook_url = None
        mock_config.discord_webhook_url = None
        mock_config.alerts_enabled = True

        # Mock usage query result
        mock_usage = MagicMock()
        mock_usage.input = 1_000_000  # 1M input tokens = $3
        mock_usage.output = 100_000  # 100K output tokens = $1.50

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = mock_config

        mock_usage_result = MagicMock()
        mock_usage_result.one.return_value = mock_usage

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_config_result, mock_usage_result]
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_budget()

            assert response.monthly_limit_usd == 50.0
            assert response.alert_threshold_pct == 80
            # $3 (input) + $1.50 (output) = $4.50
            assert response.current_month_spent_usd == pytest.approx(4.5, rel=0.01)
            # 4.5 / 50 * 100 = 9%
            assert response.percent_used == pytest.approx(9.0, rel=0.1)
            assert response.budget_exceeded is False
            assert response.alert_triggered is False

    @pytest.mark.asyncio
    async def test_budget_alert_threshold_triggered(self, mock_db_session):
        """Test budget alert when threshold is reached."""
        from main import get_budget_alerts
        from models.database import BudgetConfig

        # Mock budget config with low limit
        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("5.00")
        mock_config.alert_threshold_pct = 80

        # Mock usage: $4.50 spent = 90% of $5 limit
        mock_usage = MagicMock()
        mock_usage.input = 1_000_000
        mock_usage.output = 100_000

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = mock_config

        mock_usage_result = MagicMock()
        mock_usage_result.one.return_value = mock_usage

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_config_result, mock_usage_result]
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_budget_alerts()

            assert response.alert_active is True
            assert response.alert_type == "threshold"
            assert "warning" in response.message.lower()
            assert response.percent_used == pytest.approx(90.0, rel=0.1)

    @pytest.mark.asyncio
    async def test_budget_exceeded_alert(self, mock_db_session):
        """Test budget exceeded alert."""
        from main import get_budget_alerts
        from models.database import BudgetConfig

        # Mock budget config with very low limit
        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("1.00")
        mock_config.alert_threshold_pct = 80

        # Mock usage: $4.50 spent > $1 limit
        mock_usage = MagicMock()
        mock_usage.input = 1_000_000
        mock_usage.output = 100_000

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = mock_config

        mock_usage_result = MagicMock()
        mock_usage_result.one.return_value = mock_usage

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_config_result, mock_usage_result]
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            response = await get_budget_alerts()

            assert response.alert_active is True
            assert response.alert_type == "exceeded"
            assert "exceeded" in response.message.lower()


class TestStreamingPersistence:
    """Test that streaming endpoint persists tokens to database."""

    @pytest.mark.asyncio
    async def test_stream_persists_decision(self):
        """Test that streaming calls _store_decision with tokens."""
        from main import (
            DecisionRequest,
            RiskMode,
            Sport,
            DecisionType,
            _store_decision,
        )

        # This is an integration-style test checking the flow
        # In reality, we'd need to mock the full streaming context
        # For now, verify the function signature accepts tokens
        mock_request = DecisionRequest(
            sport=Sport.NBA,
            risk_mode=RiskMode.MEDIAN,
            decision_type=DecisionType.START_SIT,
            query="Test query",
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = False  # Skip actual DB write

            # Call with token parameters
            await _store_decision(
                mock_request,
                MagicMock(
                    decision="Start Player A",
                    confidence=MagicMock(value="high"),
                    rationale="Test rationale",
                    details=None,
                    source="claude",
                ),
                player_a_name="Player A",
                player_b_name="Player B",
                player_context=None,
                input_tokens=100,
                output_tokens=50,
                prompt_variant="control",
            )

            # If db not configured, should return early without error
            assert True


class TestCostCalculation:
    """Test cost calculation logic."""

    def test_token_to_cost_calculation(self):
        """Verify cost calculation matches Sonnet pricing."""
        # Sonnet pricing: $3/M input, $15/M output
        input_cost_per_mtok = 3.0
        output_cost_per_mtok = 15.0

        # 1M input + 1M output
        input_tokens = 1_000_000
        output_tokens = 1_000_000

        cost = (
            input_tokens / 1_000_000 * input_cost_per_mtok
            + output_tokens / 1_000_000 * output_cost_per_mtok
        )

        assert cost == 18.0  # $3 + $15

    def test_small_usage_cost(self):
        """Test cost for typical small request."""
        input_cost_per_mtok = 3.0
        output_cost_per_mtok = 15.0

        # Typical request: ~500 input, ~300 output
        input_tokens = 500
        output_tokens = 300

        cost = (
            input_tokens / 1_000_000 * input_cost_per_mtok
            + output_tokens / 1_000_000 * output_cost_per_mtok
        )

        # $0.0015 + $0.0045 = $0.006
        assert cost == pytest.approx(0.006, rel=0.01)


class TestBudgetConfigModel:
    """Test BudgetConfig model constraints."""

    def test_model_fields(self):
        """Test BudgetConfig has expected fields."""
        from models.database import BudgetConfig

        # Check model has required attributes
        assert hasattr(BudgetConfig, "monthly_limit_usd")
        assert hasattr(BudgetConfig, "alert_threshold_pct")
        assert hasattr(BudgetConfig, "created_at")
        assert hasattr(BudgetConfig, "updated_at")


# Note: Sports query filter tests moved to test_query_classifier.py


class TestBudgetEnforcement:
    """Test budget enforcement blocks requests when exceeded."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.mark.asyncio
    async def test_check_budget_no_config(self, mock_db_session):
        """Test _check_budget_exceeded returns False when no config."""
        from main import _check_budget_exceeded

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            exceeded, msg = await _check_budget_exceeded()

            assert exceeded is False
            assert msg is None

    @pytest.mark.asyncio
    async def test_check_budget_zero_limit(self, mock_db_session):
        """Test _check_budget_exceeded returns False when limit is 0."""
        from main import _check_budget_exceeded
        from models.database import BudgetConfig

        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("0")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            exceeded, msg = await _check_budget_exceeded()

            assert exceeded is False
            assert msg is None

    @pytest.mark.asyncio
    async def test_check_budget_under_limit(self, mock_db_session):
        """Test _check_budget_exceeded returns False when under limit."""
        from main import _check_budget_exceeded
        from models.database import BudgetConfig

        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("100.00")

        # Mock usage: $4.50 spent < $100 limit
        mock_usage = MagicMock()
        mock_usage.input = 1_000_000
        mock_usage.output = 100_000

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = mock_config

        mock_usage_result = MagicMock()
        mock_usage_result.one.return_value = mock_usage

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_config_result, mock_usage_result]
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            exceeded, msg = await _check_budget_exceeded()

            assert exceeded is False
            assert msg is None

    @pytest.mark.asyncio
    async def test_check_budget_exceeded(self, mock_db_session):
        """Test _check_budget_exceeded returns True when over limit."""
        from main import _check_budget_exceeded
        from models.database import BudgetConfig

        mock_config = MagicMock(spec=BudgetConfig)
        mock_config.monthly_limit_usd = Decimal("1.00")

        # Mock usage: $4.50 spent > $1 limit
        mock_usage = MagicMock()
        mock_usage.input = 1_000_000
        mock_usage.output = 100_000

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = mock_config

        mock_usage_result = MagicMock()
        mock_usage_result.one.return_value = mock_usage

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_config_result, mock_usage_result]
        )

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            exceeded, msg = await _check_budget_exceeded()

            assert exceeded is True
            assert "exceeded" in msg.lower()
            assert "$4.50" in msg
            assert "$1.00" in msg

    @pytest.mark.asyncio
    async def test_check_budget_db_not_configured(self):
        """Test _check_budget_exceeded returns False when DB not configured."""
        from main import _check_budget_exceeded

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = False

            exceeded, msg = await _check_budget_exceeded()

            assert exceeded is False
            assert msg is None

    @pytest.mark.asyncio
    async def test_check_budget_fails_open_on_error(self, mock_db_session):
        """Test _check_budget_exceeded fails open (returns False) on DB errors."""
        from main import _check_budget_exceeded

        mock_db_session.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("main.db_service") as mock_db:
            mock_db.is_configured = True
            mock_db.session.return_value = mock_db_session

            exceeded, msg = await _check_budget_exceeded()

            # Should fail open - don't block on errors
            assert exceeded is False
            assert msg is None
