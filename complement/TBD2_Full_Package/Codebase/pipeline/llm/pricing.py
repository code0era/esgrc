"""
pipeline/llm/pricing.py
Estimated per-run LLM cost, computed from the token counts we already store.

Rates are USD per **million** tokens, first-party Claude API, standard synchronous
pricing (global routing) - verified against Anthropic's current model catalog
(2026-09-10): https://platform.claude.com/docs/en/about-claude/models/overview

This is an ESTIMATE for internal telemetry only (a cost line in the logs / run
summary), not a billing source of truth. It deliberately ignores modifiers that
we do not use today: Batch API (-50%), prompt caching (reads 0.1x), and the
`inference_geo="us"` data-residency premium (1.1x). If we adopt any of those,
extend this table rather than hard-coding a multiplier at the call site.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# model id -> (input $/MTok, output $/MTok). Standard first-party rates.
# claude-sonnet-4-6 and claude-opus-4-8 are legacy models, kept here so cost
# estimates on old runs still tagged with those ids keep working; they are no
# longer what new runs are routed to (see client.py's DEFAULT_MODELS).
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":          (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6":         (3.00, 15.00),
    "claude-sonnet-5":           (2.00, 10.00),
    "claude-opus-5":             (5.00, 25.00),
    "claude-opus-4-8":           (5.00, 25.00),
}


def estimate_cost_usd(
    model: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> Optional[float]:
    """Estimated USD cost of one Claude call.

    Returns None (never raises) if the model is unknown or token counts are
    missing - telemetry must never break the pipeline.
    """
    rates = MODEL_PRICING_PER_MTOK.get(model)
    if rates is None:
        logger.debug("No pricing entry for model %r; skipping cost estimate", model)
        return None
    in_rate, out_rate = rates
    itok = input_tokens or 0
    otok = output_tokens or 0
    return (itok / 1_000_000) * in_rate + (otok / 1_000_000) * out_rate
