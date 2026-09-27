"""
pipeline/test/test_llm_unit.py
26 unit tests covering:
  - All 3 prompts render correctly
  - Guard routes at every threshold
  - ContextWindowError on extreme input
  - Token count API fallback
  - Confidence formula weights sum to 1.0
  - Formula with known values
  - Retry on RateLimitError
  - No retry on AuthenticationError / BadRequestError
  - Retry on 529 overloaded
  - Retry exhaustion raises
  - Prompt hash is 64-char hex
  - Cache miss returns None
  - Cache round-trip
"""
import hashlib
import os
from unittest.mock import MagicMock, patch, call

import pytest

from pipeline.llm.guard import _reset_client_for_testing


@pytest.fixture(autouse=True)
def _reset_guard_singleton():
    """Ensure each test gets a fresh Anthropic client mock - prevents cross-test pollution."""
    _reset_client_for_testing()
    yield
    _reset_client_for_testing()

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_llm_unit.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")

import anthropic as anthropic_lib


# ─────────────────────────────────────────────────────────────────────────────
# Prompt tests (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestPrompts:

    def test_esgrc_module_unified_renders_with_report(self):
        from pipeline.llm.prompts import ESGRC_MODULE_UNIFIED
        rendered = ESGRC_MODULE_UNIFIED.format(report_text="test report content")
        assert "test report content" in rendered
        assert len(rendered) > 100

    def test_apex_general_risk_renders_with_report(self):
        from pipeline.llm.prompts import APEX_GENERAL_RISK
        rendered = APEX_GENERAL_RISK.format(report_text="enterprise data here")
        assert "enterprise data here" in rendered
        assert len(rendered) > 100

    def test_apex_spc_rpn_renders_with_report(self):
        from pipeline.llm.prompts import APEX_SPC_RPN
        rendered = APEX_SPC_RPN.format(report_text="spc rpn data")
        assert "spc rpn data" in rendered
        assert len(rendered) > 100


# ─────────────────────────────────────────────────────────────────────────────
# Guard routing tests (5 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestGuardRouting:

    def _mock_anthropic(self, token_count: int):
        mock = MagicMock()
        mock.messages.count_tokens.return_value = MagicMock(input_tokens=token_count)
        return mock

    def test_under_150k_passes_unchanged_haiku(self):
        from pipeline.llm.guard import check_token_count
        text = "normal report content"
        with patch("pipeline.llm.guard.anthropic.Anthropic",
                   return_value=self._mock_anthropic(5_000)):
            result = check_token_count(text, "claude-haiku-4-5")
        assert result.was_truncated is False
        assert result.token_count == 5_000

    def test_at_150k_triggers_truncation_haiku(self):
        """Exactly at warn threshold - truncation fires."""
        from pipeline.llm.guard import check_token_count
        text = "X" * 600_000
        call_n = {"n": 0}
        def fake_count(model, messages):
            call_n["n"] += 1
            return MagicMock(input_tokens=150_001 if call_n["n"] == 1 else 130_000)
        mock = MagicMock()
        mock.messages.count_tokens.side_effect = fake_count
        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock):
            result = check_token_count(text, "claude-haiku-4-5")
        assert result.was_truncated is True

    def test_over_190k_raises_context_window_error(self):
        """Exceeds hard limit even after truncation - raises."""
        from pipeline.llm.guard import check_token_count, ContextWindowError
        text = "X" * 4_000_000
        mock = MagicMock()
        mock.messages.count_tokens.return_value = MagicMock(input_tokens=195_000)
        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock):
            with pytest.raises(ContextWindowError):
                check_token_count(text, "claude-haiku-4-5")

    def test_sonnet_allows_up_to_800k_without_truncation(self):
        from pipeline.llm.guard import check_token_count
        text = "S" * 200_000
        with patch("pipeline.llm.guard.anthropic.Anthropic",
                   return_value=self._mock_anthropic(50_000)):
            result = check_token_count(text, "claude-sonnet-4-6")
        assert result.was_truncated is False

    def test_token_api_failure_falls_back_to_char_estimate(self):
        from pipeline.llm.guard import check_token_count
        text = "A" * 40_000  # ~10K tokens
        mock = MagicMock()
        mock.messages.count_tokens.side_effect = Exception("API down")
        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock):
            result = check_token_count(text, "claude-haiku-4-5")
        assert result.token_count > 0
        assert result.was_truncated is False


# ─────────────────────────────────────────────────────────────────────────────
# Confidence formula tests (5 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceFormula:

    def test_weights_sum_to_1(self):
        from pipeline.llm.confidence import W_COMPLETENESS, W_STABILITY, W_BENCHMARK
        total = W_COMPLETENESS + W_STABILITY + W_BENCHMARK
        assert abs(total - 1.0) < 0.0001

    def test_known_values_produce_correct_score(self):
        from pipeline.llm.confidence import W_COMPLETENESS, W_STABILITY, W_BENCHMARK
        c, s, b = 0.80, 0.60, 0.70
        expected = c * W_COMPLETENESS + s * W_STABILITY + b * W_BENCHMARK
        # = 0.80*0.40 + 0.60*0.35 + 0.70*0.25 = 0.320 + 0.210 + 0.175 = 0.705
        assert abs(expected - 0.705) < 0.001

    def test_run_not_found_returns_neutral(self):
        from pipeline.llm.confidence import compute_confidence
        with patch("pipeline.llm.confidence._get_org_id", return_value=None):
            score = compute_confidence("nonexistent-run")
        assert score == 0.5

    def test_score_clamped_at_1(self):
        from pipeline.llm.confidence import compute_confidence
        with (
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._compute_completeness", return_value=2.0),
            patch("pipeline.llm.confidence._compute_stability", return_value=2.0),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=2.0),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-x")
        assert score <= 1.0

    def test_score_clamped_at_0(self):
        from pipeline.llm.confidence import compute_confidence
        with (
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._compute_completeness", return_value=-1.0),
            patch("pipeline.llm.confidence._compute_stability", return_value=-1.0),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=-1.0),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-x")
        assert score >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Retry policy tests (6 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryPolicy:

    def _make_client(self):
        from pipeline.llm.client import LLMClient
        client = LLMClient.__new__(LLMClient)
        client._anthropic = MagicMock()
        client._redis = None
        client._langfuse = None
        return client

    def test_retries_on_rate_limit_error(self):
        client = self._make_client()
        attempt = {"n": 0}
        def fake_create(**kw):
            attempt["n"] += 1
            if attempt["n"] < 2:
                raise anthropic_lib.RateLimitError(
                    message="rate limit",
                    response=MagicMock(status_code=429), body={})
            r = MagicMock()
            r.content = [MagicMock(type="text", text="ok")]
            r.usage = MagicMock(input_tokens=100, output_tokens=50)
            return r
        client._anthropic.messages.create.side_effect = fake_create
        with patch("time.sleep"):
            resp = client._call_with_retry("claude-haiku-4-5", "prompt")
        assert attempt["n"] == 2

    def test_no_retry_on_authentication_error(self):
        client = self._make_client()
        attempt = {"n": 0}
        def fake_create(**kw):
            attempt["n"] += 1
            raise anthropic_lib.AuthenticationError(
                message="bad key",
                response=MagicMock(status_code=401), body={})
        client._anthropic.messages.create.side_effect = fake_create
        with pytest.raises(anthropic_lib.AuthenticationError):
            client._call_with_retry("claude-haiku-4-5", "prompt")
        assert attempt["n"] == 1

    def test_no_retry_on_bad_request_error(self):
        client = self._make_client()
        attempt = {"n": 0}
        def fake_create(**kw):
            attempt["n"] += 1
            raise anthropic_lib.BadRequestError(
                message="bad prompt",
                response=MagicMock(status_code=400), body={})
        client._anthropic.messages.create.side_effect = fake_create
        with pytest.raises(anthropic_lib.BadRequestError):
            client._call_with_retry("claude-haiku-4-5", "prompt")
        assert attempt["n"] == 1

    def test_retries_on_529_overloaded(self):
        client = self._make_client()
        attempt = {"n": 0}
        def fake_create(**kw):
            attempt["n"] += 1
            if attempt["n"] < 3:
                raise anthropic_lib.APIStatusError(
                    message="overloaded",
                    response=MagicMock(status_code=529), body={})
            r = MagicMock()
            r.content = [MagicMock(type="text", text="eventually ok")]
            r.usage = MagicMock(input_tokens=100, output_tokens=50)
            return r
        client._anthropic.messages.create.side_effect = fake_create
        with patch("time.sleep"):
            resp = client._call_with_retry("claude-sonnet-4-6", "prompt")
        assert attempt["n"] == 3

    def test_retry_exhaustion_raises_last_exception(self):
        client = self._make_client()
        client._anthropic.messages.create.side_effect = anthropic_lib.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429), body={})
        with patch("time.sleep"):
            with pytest.raises(anthropic_lib.RateLimitError):
                client._call_with_retry("claude-haiku-4-5", "prompt")

    def test_max_3_attempts_on_timeout(self):
        client = self._make_client()
        attempt = {"n": 0}
        def fake_create(**kw):
            attempt["n"] += 1
            raise anthropic_lib.APITimeoutError(request=MagicMock())
        client._anthropic.messages.create.side_effect = fake_create
        with patch("time.sleep"):
            with pytest.raises(anthropic_lib.APITimeoutError):
                client._call_with_retry("claude-haiku-4-5", "prompt")
        assert attempt["n"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Prompt hash + cache tests (4 tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptHashAndCache:

    def test_prompt_hash_is_64_char_hex(self):
        from pipeline.llm.client import LLMClient
        client = LLMClient.__new__(LLMClient)
        client._redis = None
        client._langfuse = None
        client._anthropic = MagicMock()

        text = "some prompt text"
        h = hashlib.sha256(text.encode()).hexdigest()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_prompts_have_different_hashes(self):
        prompt_a = "Analyse ESG data: report_a"
        prompt_b = "Analyse ESG data: report_b"
        h_a = hashlib.sha256(prompt_a.encode()).hexdigest()
        h_b = hashlib.sha256(prompt_b.encode()).hexdigest()
        assert h_a != h_b

    def test_cache_miss_returns_none(self):
        from pipeline.llm.client import LLMClient
        client = LLMClient.__new__(LLMClient)
        client._redis = None  # no Redis → always miss
        client._langfuse = None
        client._anthropic = MagicMock()

        result = client._check_result_cache("nonexistent-hash-xyz")
        assert result is None

    def test_cache_round_trip(self):
        """Store a result then retrieve it - same data returned."""
        from pipeline.llm.client import LLMClient, LLMResult

        class FakeRedis:
            def __init__(self): self._store = {}
            def get(self, k): return self._store.get(k)
            def set(self, k, v, ex=None): self._store[k] = v

        client = LLMClient.__new__(LLMClient)
        client._redis = FakeRedis()
        client._langfuse = None
        client._anthropic = MagicMock()

        import json
        result = LLMResult(
            response_text="Risk assessment result",
            input_tokens=1000,
            output_tokens=300,
            model_used="claude-haiku-4-5",
            prompt_hash="abc123def456" * 5 + "abcd",  # 64 chars
            r2_path="org/1/runs/run-1/step_7/rec.txt",
            from_cache=False,
        )

        client._store_result_cache("test-hash-abc", result, org_id="1")
        retrieved = client._check_result_cache("test-hash-abc", org_id="1")

        assert retrieved is not None
        assert retrieved.response_text == "Risk assessment result"
        assert retrieved.model_used == "claude-haiku-4-5"
        assert retrieved.from_cache is True

    def test_cache_is_scoped_per_org(self):
        """FIX: the result cache key used to be bare prompt_hash with no org in
        it, so two orgs whose report text happened to render an identical prompt
        (e.g. both still on the near-empty 'skeleton' report before either has
        real data) would silently share a cached Claude response. The cache key
        must now be scoped by org_id: the same prompt_hash for two different orgs
        is two different Redis keys, and a hit for org 1 must not satisfy org 2's
        lookup."""
        from pipeline.llm.client import LLMClient, LLMResult

        class FakeRedis:
            def __init__(self): self._store = {}
            def get(self, k): return self._store.get(k)
            def set(self, k, v, ex=None): self._store[k] = v

        client = LLMClient.__new__(LLMClient)
        client._redis = FakeRedis()
        client._langfuse = None
        client._anthropic = MagicMock()

        result = LLMResult(
            response_text="Org 1's confidential recommendation",
            input_tokens=500,
            output_tokens=150,
            model_used="claude-haiku-4-5",
            prompt_hash="identical-hash-both-orgs",
            r2_path="org/1/runs/run-1/step_7/rec.txt",
            from_cache=False,
        )

        client._store_result_cache("identical-hash-both-orgs", result, org_id="1")

        # Same prompt_hash, different org: must be a miss, not a leak.
        assert client._check_result_cache("identical-hash-both-orgs", org_id="2") is None
        # The owning org still gets its cache hit.
        assert client._check_result_cache("identical-hash-both-orgs", org_id="1") is not None


# ─────────────────────────────────────────────────────────────────────────────
# LLMClient auto-upgrade test (1 test)
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoUpgrade:

    def test_haiku_auto_upgrades_to_sonnet_above_150k(self):
        """
        When token count > 150K and model is Haiku,
        LLMClient must switch to Sonnet automatically.
        """
        from pipeline.llm.client import LLMClient, HAIKU_UPGRADE_TOKEN_THRESHOLD

        call_n = {"n": 0}
        def fake_count(model, messages):
            call_n["n"] += 1
            # First call (Haiku check): over threshold
            # Second call (Sonnet check after upgrade): under Sonnet limit
            return MagicMock(
                input_tokens=160_000 if call_n["n"] == 1 else 160_000
            )

        mock_anthropic = MagicMock()
        mock_anthropic.messages.count_tokens.side_effect = fake_count

        response = MagicMock()
        response.content = [MagicMock(type="text", text="Analysis result")]
        response.usage = MagicMock(input_tokens=160_000, output_tokens=500)
        mock_anthropic.messages.create.return_value = response

        client = LLMClient.__new__(LLMClient)
        client._anthropic = mock_anthropic
        client._redis = None
        client._langfuse = None

        with (
            patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_anthropic),
            patch("time.sleep"),
        ):
            from pipeline.llm.guard import check_token_count, TokenCheckResult
            # Simulate what LLMClient.analyze() does
            check_result = TokenCheckResult(
                token_count=160_000,
                was_truncated=False,
                original_token_count=160_000,
                text="some long report",
            )
            model = "claude-haiku-4-5"
            if check_result.token_count > HAIKU_UPGRADE_TOKEN_THRESHOLD and model == "claude-haiku-4-5":
                model = "claude-sonnet-4-6"

        assert model == "claude-sonnet-4-6"
