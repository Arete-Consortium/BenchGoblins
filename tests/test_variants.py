"""
Tests for A/B prompt variant system.
"""

from collections import Counter

import pytest

from services.variants import (
    ACTIVE_EXPERIMENT,
    PROMPT_VARIANTS,
    ExperimentRegistry,
    assign_variant,
    get_experiment_config,
    get_experiment_history,
    get_prompt,
)


class TestAssignVariant:
    """Tests for variant assignment."""

    def test_deterministic_same_session(self):
        """Same session_id always gets the same variant."""
        session_id = "test-session-abc"
        results = {assign_variant(session_id) for _ in range(100)}
        assert len(results) == 1

    def test_deterministic_different_sessions(self):
        """Different session_ids can get different variants."""
        variants = {assign_variant(f"session-{i}") for i in range(200)}
        # With 50/50 split, 200 sessions should hit both variants
        assert len(variants) == 2

    def test_distribution_balance(self):
        """Over 1000 assignments, each variant gets roughly 50%."""
        counts = Counter(assign_variant(f"sess-{i}") for i in range(1000))
        for variant in ACTIVE_EXPERIMENT:
            ratio = counts[variant] / 1000
            # Allow 10% tolerance
            expected = ACTIVE_EXPERIMENT[variant] / sum(ACTIVE_EXPERIMENT.values())
            assert abs(ratio - expected) < 0.10, (
                f"{variant}: {ratio} vs expected {expected}"
            )

    def test_none_session_returns_valid_variant(self):
        """None session_id returns a valid variant (non-deterministic)."""
        result = assign_variant(None)
        assert result in PROMPT_VARIANTS

    def test_returns_known_variant(self):
        """Assigned variant is always a known variant."""
        for i in range(50):
            v = assign_variant(f"test-{i}")
            assert v in PROMPT_VARIANTS


class TestGetPrompt:
    """Tests for prompt retrieval."""

    def test_control_returns_string(self):
        """Control variant returns a non-empty string."""
        prompt = get_prompt("control")
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_concise_v1_returns_string(self):
        """Concise variant returns a non-empty string."""
        prompt = get_prompt("concise_v1")
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_unknown_variant_falls_back_to_control(self):
        """Unknown variant name falls back to control prompt."""
        prompt = get_prompt("nonexistent_variant")
        assert prompt == PROMPT_VARIANTS["control"]

    def test_concise_shorter_than_control(self):
        """Concise variant should be shorter than control."""
        assert len(get_prompt("concise_v1")) < len(get_prompt("control"))


class TestGetExperimentConfig:
    """Tests for experiment config endpoint."""

    def test_returns_config(self):
        """Config returns expected structure."""
        config = get_experiment_config()
        assert "variants" in config
        assert "weights" in config
        assert "total_variants" in config
        assert config["total_variants"] == len(ACTIVE_EXPERIMENT)
        assert set(config["variants"]) == set(ACTIVE_EXPERIMENT.keys())

    def test_includes_experiment_metadata(self):
        """Config includes experiment name and timestamps."""
        config = get_experiment_config()
        assert "experiment" in config
        assert config["experiment"]["name"] == "concise_prompt_v1"
        assert config["experiment"]["is_active"] is True
        assert config["experiment"]["started_at"] is not None


class TestExperimentLifecycle:
    """Tests for experiment start/stop/history."""

    def test_start_and_end(self):
        """Can start and end an experiment."""
        reg = ExperimentRegistry()
        exp = reg.start_experiment("test_exp", {"control": 50, "concise_v1": 50})
        assert reg.active is not None
        assert exp.is_active

        ended = reg.end_experiment()
        assert ended is not None
        assert not ended.is_active
        assert ended.ended_at is not None
        assert reg.active is None

    def test_history_populated(self):
        """Ended experiments appear in history."""
        reg = ExperimentRegistry()
        reg.start_experiment("exp1", {"control": 100})
        reg.end_experiment()
        reg.start_experiment("exp2", {"control": 50, "concise_v1": 50})
        reg.end_experiment()

        assert len(reg.history) == 2
        assert reg.history[0].name == "exp1"
        assert reg.history[1].name == "exp2"

    def test_start_auto_ends_previous(self):
        """Starting a new experiment auto-ends the current one."""
        reg = ExperimentRegistry()
        reg.start_experiment("exp1", {"control": 100})
        reg.start_experiment("exp2", {"control": 50, "concise_v1": 50})

        assert reg.active.name == "exp2"
        assert len(reg.history) == 1
        assert reg.history[0].name == "exp1"

    def test_end_no_active_returns_none(self):
        """Ending when nothing active returns None."""
        reg = ExperimentRegistry()
        assert reg.end_experiment() is None

    def test_fallback_weights_when_no_experiment(self):
        """When no experiment active, falls back to control-only."""
        reg = ExperimentRegistry()
        assert reg.get_active_weights() == {"control": 100}

    def test_unknown_variant_raises(self):
        """Starting with unknown variant raises ValueError."""
        reg = ExperimentRegistry()
        with pytest.raises(ValueError, match="Unknown variant"):
            reg.start_experiment("bad", {"control": 50, "nonexistent": 50})

    def test_duration_hours(self):
        """Duration is calculated correctly."""
        reg = ExperimentRegistry()
        exp = reg.start_experiment("test", {"control": 100})
        # Active experiment has non-None duration
        assert exp.duration_hours is not None
        assert exp.duration_hours >= 0

    def test_get_experiment_history_format(self):
        """get_experiment_history returns proper dicts."""
        # Uses the global registry, which has the default experiment running
        history = get_experiment_history()
        assert isinstance(history, list)
        # May be empty if default hasn't been ended, which is expected


class TestAssignVariantFallback:
    def test_fallback_return_variants_zero(self):
        """Line 260: fallback return variants[0] when loop completes without match."""
        from unittest.mock import patch

        # Create a custom dict subclass where iteration yields keys but
        # __getitem__ returns 0, so cumulative stays at 0 and bucket is always >= cumulative.
        # However total_weight must be > 0 to avoid ZeroDivisionError.
        # Trick: sum(values()) returns 1, but iterating weights[variant] returns 0.
        class _TrickyWeights(dict):
            """Weights dict that reports total=1 via values() but yields 0 per key."""

            def values(self):
                return [1]

            def keys(self):
                return ["control"]

            def __iter__(self):
                return iter(["control"])

            def __getitem__(self, key):
                return 0  # cumulative stays 0, bucket (>= 0) never < 0

        with patch(
            "services.variants.experiment_registry.get_active_weights",
            return_value=_TrickyWeights({"control": 0}),
        ):
            result = assign_variant("test-session")
            assert result == "control"
