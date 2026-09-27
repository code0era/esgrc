"""
pipeline/llm/preflight.py
Pre-flight token + cost check on a report before a Claude call.

Log-only telemetry / early warning. It counts the report's tokens (real
count_tokens when the SDK exposes it, else guard's char estimate), estimates
the USD input cost, and warns when the report approaches the model's context
window - BEFORE the call is made. It does NOT truncate: guard.check_token_count
still owns truncation inside the LLM call. This layer just makes an over-budget
report visible in the logs early and records per-run size/cost.

Scaffold notes for Shubham:
  * The one real TODO is a first-class count_tokens once we move off
    anthropic==0.40.0 (which lacks messages.count_tokens). Until then,
    guard._count_tokens transparently falls back to the len//3 char estimate -
    no change needed here.
  * `guard` is imported as a MODULE (not `from guard import _count_tokens`) so
    the token counter stays patchable in tests - see pipeline/tests/test_preflight.py.
  * Wiring lives in pipeline/tasks/claude_tasks.py; it is wrapped so a preflight
    failure can never break a run.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from pipeline.llm import guard
from pipeline.llm.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)

# Conservative fallback if a model has no explicit guard threshold.
_FALLBACK_THRESHOLDS = (150_000, 190_000)

# FLOOR guard (mirror of the ceiling). A report below this many tokens is almost
# certainly a skeleton - section headers/methodology but no populated data - the
# failure mode that ships a client an empty report. Set well under the smallest
# legitimate report we've measured (the Apex SPC/RPN input was ~1,355 tokens), so
# a real small report never trips it. Reliable per-section detection lives in the
# combiner (text_report_combiner); this is just the last-chance backstop.
_MIN_TOKENS_FLOOR = 500


@dataclass
class PreflightResult:
    model: str
    input_tokens: int
    warn_threshold: int
    hard_threshold: int
    over_warn: bool
    over_hard: bool
    est_input_cost_usd: Optional[float]
    under_floor: bool = False


def preflight_report(text: str, model: str) -> PreflightResult:
    """Count + price a report before the Claude call. Never truncates, never raises."""
    warn, hard = guard.MODEL_THRESHOLDS.get(model, _FALLBACK_THRESHOLDS)
    tokens = guard._count_tokens(text, model)  # real API if available, else len//3
    return PreflightResult(
        model=model,
        input_tokens=tokens,
        warn_threshold=warn,
        hard_threshold=hard,
        over_warn=tokens > warn,
        over_hard=tokens > hard,
        est_input_cost_usd=estimate_cost_usd(model, tokens, 0),
        under_floor=tokens < _MIN_TOKENS_FLOOR,
    )


def log_preflight(run_id: str, step: int, result: PreflightResult) -> None:
    """Emit the preflight line + a warning if the report is near/over budget."""
    cost = result.est_input_cost_usd
    cost_str = f"${cost:.4f}" if cost is not None else "n/a"
    logger.info(
        "Preflight run=%s step=%d model=%s input_tokens=%d est_input_cost=%s (warn=%d hard=%d)",
        run_id, step, result.model, result.input_tokens, cost_str,
        result.warn_threshold, result.hard_threshold,
    )
    if result.over_hard:
        logger.warning(
            "Preflight run=%s step=%d: report %d tokens EXCEEDS hard limit %d for %s - "
            "guard will truncate; trim the report at the combiner/script level.",
            run_id, step, result.input_tokens, result.hard_threshold, result.model,
        )
    elif result.over_warn:
        logger.warning(
            "Preflight run=%s step=%d: report %d tokens over warn threshold %d for %s - "
            "nearing the model's budget.",
            run_id, step, result.input_tokens, result.warn_threshold, result.model,
        )
    if result.under_floor:
        logger.warning(
            "Preflight run=%s step=%d: report is only %d tokens (floor %d) - likely a "
            "SKELETON with no populated data; check the upstream analytics inputs before "
            "this reaches the client.",
            run_id, step, result.input_tokens, _MIN_TOKENS_FLOOR,
        )
