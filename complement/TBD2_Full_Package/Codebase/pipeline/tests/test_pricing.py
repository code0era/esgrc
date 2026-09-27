"""pipeline/test/test_pricing.py - LLM cost-estimate helper."""
import pytest

from pipeline.llm.pricing import estimate_cost_usd, MODEL_PRICING_PER_MTOK


class TestEstimateCostUsd:
    def test_sonnet_full_scale_report(self):
        # The real MASTER_CONSOLIDATED_REPORT measured 289,418 input tokens.
        cost = estimate_cost_usd("claude-sonnet-4-6", 289_418, 6_600)
        # 289418/1e6*3 + 6600/1e6*15 = 0.868254 + 0.099 = 0.967254
        assert cost == pytest.approx(0.967254, abs=1e-6)

    def test_haiku_rates(self):
        # 100k in, 4k out: 0.1*1 + 0.004*5 = 0.12
        assert estimate_cost_usd("claude-haiku-4-5", 100_000, 4_000) == pytest.approx(0.12)

    def test_dated_haiku_alias_priced(self):
        assert estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0) == pytest.approx(1.00)

    def test_unknown_model_returns_none(self):
        assert estimate_cost_usd("gpt-4", 1000, 1000) is None

    def test_missing_token_counts_treated_as_zero(self):
        assert estimate_cost_usd("claude-sonnet-4-6", None, None) == 0.0

    def test_never_raises_on_bad_input(self):
        # Telemetry must not break the pipeline.
        assert estimate_cost_usd("claude-sonnet-4-6", None, 500) == pytest.approx(0.0075)

    def test_pricing_table_shape(self):
        for model, rates in MODEL_PRICING_PER_MTOK.items():
            assert len(rates) == 2
            assert rates[0] > 0 and rates[1] > 0
