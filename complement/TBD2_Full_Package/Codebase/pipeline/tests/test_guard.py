"""
pipeline/test/test_guard.py
Unit tests for the context window guard.

Tests:
  - Normal text passes through unchanged
  - Overlong text is truncated and flagged
  - Extreme text raises ContextWindowError
  - Truncation preserves beginning and end
  - Model thresholds applied correctly per model
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from pipeline.llm.guard import _reset_client_for_testing


@pytest.fixture(autouse=True)
def _reset_guard_singleton():
    """Ensure each test gets a fresh Anthropic client mock - prevents cross-test pollution."""
    _reset_client_for_testing()
    yield
    _reset_client_for_testing()

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_guard.db")

from pipeline.llm.guard import (
    ContextWindowError,
    TokenCheckResult,
    MODEL_THRESHOLDS,
    check_token_count,
    _count_tokens,
    _truncate_to_tokens,
)


def _mock_anthropic(token_count: int):
    """Return a mock anthropic client that always reports token_count tokens."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.input_tokens = token_count
    mock_client.messages.count_tokens.return_value = mock_response
    return mock_client


class TestTokenThresholds:
    def test_haiku_warn_threshold_is_150k(self):
        warn, hard = MODEL_THRESHOLDS["claude-haiku-4-5"]
        assert warn == 150_000

    def test_haiku_hard_limit_is_190k(self):
        warn, hard = MODEL_THRESHOLDS["claude-haiku-4-5"]
        assert hard == 190_000

    def test_sonnet_warn_threshold(self):
        # claude-sonnet-4-6 has a native 1M context window (GA, no beta header),
        # so the guard warns at 800K, not the old (wrong) 170K.
        warn, hard = MODEL_THRESHOLDS["claude-sonnet-4-6"]
        assert warn == 800_000

    def test_sonnet_hard_limit(self):
        warn, hard = MODEL_THRESHOLDS["claude-sonnet-4-6"]
        assert hard == 950_000

    def test_deprecated_sonnet_4_0_stays_conservative(self):
        # Sonnet 4.0 (deprecated) has NO native 1M window - must stay at 170K/190K.
        warn, hard = MODEL_THRESHOLDS["claude-sonnet-4-20250514"]
        assert (warn, hard) == (170_000, 190_000)


class TestCheckTokenCount:
    def test_normal_text_passes_unchanged(self):
        """Text under the warn threshold passes through without truncation."""
        text = "This is a short report." * 100
        mock_client = _mock_anthropic(token_count=5_000)

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-haiku-4-5")

        assert result.was_truncated is False
        assert result.token_count == 5_000
        assert result.original_token_count == 5_000
        assert result.text == text

    def test_overlong_text_is_truncated(self):
        """Text over warn threshold triggers truncation."""
        text = "A" * 800_000  # ~200K tokens at ~4 chars/token

        # First call: 160_000 tokens (over warn 150K)
        # Second call (after truncation): 140_000 tokens (under hard limit)
        call_count = {"n": 0}
        def fake_count(model, messages):
            call_count["n"] += 1
            response = MagicMock()
            response.input_tokens = 160_000 if call_count["n"] == 1 else 140_000
            return response

        mock_client = MagicMock()
        mock_client.messages.count_tokens.side_effect = fake_count

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-haiku-4-5")

        assert result.was_truncated is True
        assert result.original_token_count == 160_000
        assert result.token_count == 140_000
        assert len(result.text) < len(text)

    def test_extreme_text_raises_context_window_error(self):
        """Text that exceeds hard limit even after truncation raises ContextWindowError."""
        text = "B" * 4_000_000  # far too large

        # Always report over hard limit
        mock_client = _mock_anthropic(token_count=195_000)

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            with pytest.raises(ContextWindowError, match="hard limit"):
                check_token_count(text, "claude-haiku-4-5")

    def test_truncation_preserves_beginning_and_end(self):
        """After truncation, text contains content from start and end of original."""
        # Build text with known markers at start and end
        start_marker = "START_MARKER_UNIQUE_12345 "
        end_marker = " END_MARKER_UNIQUE_67890"
        filler = "X" * 900_000
        text = start_marker + filler + end_marker

        call_count = {"n": 0}
        def fake_count(model, messages):
            call_count["n"] += 1
            r = MagicMock()
            r.input_tokens = 160_000 if call_count["n"] == 1 else 130_000
            return r

        mock_client = MagicMock()
        mock_client.messages.count_tokens.side_effect = fake_count

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-haiku-4-5")

        assert result.was_truncated is True
        assert start_marker.strip() in result.text
        assert end_marker.strip() in result.text
        assert "TRUNCATED" in result.text

    def test_sonnet_uses_higher_thresholds(self):
        """Sonnet allows up to 800K tokens before warning - 200K text passes unchanged."""
        text = "S" * 200_000
        mock_client = _mock_anthropic(token_count=50_000)  # well under 800K

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-sonnet-4-6")

        assert result.was_truncated is False

    def test_large_esgrc_report_not_truncated_on_sonnet(self):
        """Regression: a ~210K-token report routed to Sonnet must NOT be truncated.

        The old (wrong) 170K threshold silently truncated ~40K tokens out of the
        middle of large ESGRC risk reports. Sonnet 4.6's native 1M window means a
        210K-token report is well within budget and must pass through intact.
        """
        text = "R" * 630_000  # ~210K tokens by the len//3 fallback estimate
        mock_client = _mock_anthropic(token_count=210_000)  # over old 170K, under new 800K

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-sonnet-4-6")

        assert result.was_truncated is False
        assert result.token_count == 210_000
        assert result.text == text  # untouched - no middle cut

    def test_api_failure_falls_back_to_char_estimate(self):
        """If token count API fails, falls back to character-based estimate without raising."""
        text = "X" * 40_000  # ~10K tokens by char estimate (40K / 4)

        mock_client = MagicMock()
        mock_client.messages.count_tokens.side_effect = Exception("API unavailable")

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            result = check_token_count(text, "claude-haiku-4-5")

        # Should not raise - should fall back to estimate
        assert result.token_count > 0
        assert result.was_truncated is False  # 10K tokens << 150K warn threshold


class TestTruncateToTokens:
    def test_truncation_reduces_text_length(self):
        """_truncate_to_tokens returns shorter text than input."""
        text = "Hello world. " * 100_000
        target = 10_000

        result = _truncate_to_tokens(text, "claude-haiku-4-5", target)

        assert len(result) < len(text)

    def test_truncation_inserts_truncation_marker(self):
        """Truncated text always contains the TRUNCATED marker."""
        text = "A" * 800_000

        result = _truncate_to_tokens(text, "claude-haiku-4-5", 10_000)

        assert "TRUNCATED" in result

    def test_no_truncation_when_text_already_fits(self):
        """If text is already within target, returns it unchanged."""
        text = "Short text"

        result = _truncate_to_tokens(text, "claude-haiku-4-5", 1_000_000)

        assert result == text
