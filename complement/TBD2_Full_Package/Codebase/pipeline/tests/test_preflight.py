"""pipeline/test/test_preflight.py - pre-flight token/cost check (log-only)."""
from unittest.mock import patch

import pytest

from pipeline.llm import preflight as pf
from pipeline.llm.guard import CHARS_PER_TOKEN_FALLBACK


class TestPreflightReport:
    def test_under_warn_no_flags(self):
        with patch("pipeline.llm.guard._count_tokens", return_value=50_000):
            r = pf.preflight_report("x", "claude-sonnet-4-6")
        assert not r.over_warn and not r.over_hard
        assert r.est_input_cost_usd == pytest.approx(50_000 / 1e6 * 3)

    def test_sonnet_289k_report_within_1m_budget(self):
        # The real report is 289,418 tokens; Sonnet's guard is now 800K/950K.
        with patch("pipeline.llm.guard._count_tokens", return_value=289_418):
            r = pf.preflight_report("x", "claude-sonnet-4-6")
        assert not r.over_warn and not r.over_hard

    def test_same_report_would_overflow_haiku(self):
        # 289K tokens on Haiku (200K window, guard 150K/190K) → over hard.
        with patch("pipeline.llm.guard._count_tokens", return_value=289_418):
            r = pf.preflight_report("x", "claude-haiku-4-5")
        assert r.over_warn and r.over_hard

    def test_fallback_char_estimate_when_count_api_unavailable(self):
        # If the real tokenizer call fails, guard falls back to a char-ratio
        # estimate (CHARS_PER_TOKEN_FALLBACK) - only exercised on a genuine API
        # failure now that the SDK supports count_tokens (bumped 2026-07-31).
        text = "R" * 600_000
        with patch("pipeline.llm.guard._get_client", side_effect=Exception("no count_tokens")):
            r = pf.preflight_report(text, "claude-sonnet-4-6")
        assert r.input_tokens == int(600_000 / CHARS_PER_TOKEN_FALLBACK)

    def test_unknown_model_uses_fallback_thresholds_and_no_cost(self):
        with patch("pipeline.llm.guard._count_tokens", return_value=10_000):
            r = pf.preflight_report("x", "some-future-model")
        assert (r.warn_threshold, r.hard_threshold) == (150_000, 190_000)
        assert r.est_input_cost_usd is None  # unknown model → pricing.py returns None


class TestLogPreflight:
    def test_never_raises(self):
        r = pf.PreflightResult("claude-sonnet-4-6", 300_000, 800_000, 950_000, False, False, 0.9)
        pf.log_preflight("run-1", 7, r)  # must not raise

    def test_over_hard_logs_warning(self, caplog):
        import logging
        r = pf.PreflightResult("claude-haiku-4-5", 210_000, 150_000, 190_000, True, True, 0.21)
        with caplog.at_level(logging.WARNING, logger="pipeline.llm.preflight"):
            pf.log_preflight("run-2", 8, r)
        assert any("EXCEEDS hard limit" in rec.message for rec in caplog.records)


class TestFloorGuard:
    def test_tiny_report_flagged_under_floor(self):
        # A ~100-token skeleton is under the 500-token floor.
        with patch("pipeline.llm.guard._count_tokens", return_value=100):
            r = pf.preflight_report("skeleton", "claude-sonnet-4-6")
        assert r.under_floor is True

    def test_small_legit_report_not_flagged(self):
        # The Apex SPC/RPN input (~1,355 tokens) is legitimate - must NOT trip the floor.
        with patch("pipeline.llm.guard._count_tokens", return_value=1_355):
            r = pf.preflight_report("x", "claude-sonnet-4-6")
        assert r.under_floor is False

    def test_under_floor_logs_skeleton_warning(self, caplog):
        import logging
        r = pf.PreflightResult("claude-sonnet-4-6", 120, 800_000, 950_000, False, False, 0.0004, True)
        with caplog.at_level(logging.WARNING, logger="pipeline.llm.preflight"):
            pf.log_preflight("run-3", 7, r)
        assert any("SKELETON" in rec.message for rec in caplog.records)
