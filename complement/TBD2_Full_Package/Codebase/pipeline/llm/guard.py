"""
pipeline/llm/guard.py
Context window guard - token count pre-check before every Claude API call.

Thresholds (architecture decisions doc R2):
  Haiku  4.5: warn at 150K, hard stop at 190K (10K buffer under 200K limit)
  Sonnet 4.6: warn at 800K, hard stop at 950K (50K buffer under 1M limit)

Truncation: removes from the MIDDLE of the document - preserves the first
30% (headers, metadata) and last 70% (most recent / highest-severity data).

Performance: Anthropic client is a module-level singleton. Creating a new
client per call adds TLS handshake overhead on every guard invocation.
"""
import logging
import threading
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ── Singleton Anthropic client for token counting ─────────────────────────────
_anthropic_client: Optional[anthropic.Anthropic] = None
_anthropic_lock = threading.Lock()


def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        with _anthropic_lock:
            if _anthropic_client is None:
                _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def _reset_client_for_testing() -> None:
    """Test-only seam: clears the cached singleton so each test gets a fresh client."""
    global _anthropic_client
    with _anthropic_lock:
        _anthropic_client = None


# ── Thresholds ────────────────────────────────────────────────────────────────
# (warn, hard) token thresholds per model - MUST reflect the context window the
# API actually enforces.
#   claude-haiku-4-5  → 200K window. Guard at 150K/190K (10K buffer).
#   claude-sonnet-4-6 → 1M window, GA/native (verified vs the July-2026 Claude
#     catalog; NO beta header - the `context-1m` beta only ever applied to the
#     older Sonnet 4.5/4.0). Guard at 800K/950K (50K buffer under 1M).
# History: an earlier comment wrongly claimed Sonnet 4.6 needed a 1M-context beta
# header and capped these at 170K/190K, which silently truncated ~40K tokens out
# of the middle of large ESGRC reports routed to Sonnet. The real step-7 overflow
# bug was Haiku's 200K limit (the Haiku→Sonnet upgrade not firing), NOT Sonnet
# lacking a header - so Sonnet's guard is restored to its true window here.
# NOTE: `claude-sonnet-4-20250514` (Sonnet 4.0, deprecated) does NOT have a native
# 1M window, so it stays conservative at 170K/190K.
MODEL_THRESHOLDS: dict[str, tuple[int, int]] = {
    "claude-haiku-4-5":          (150_000, 190_000),
    "claude-haiku-4-5-20251001": (150_000, 190_000),
    "claude-sonnet-4-6":         (800_000, 950_000),
    # 1M-context models that pricing.py already anticipates as routing targets -
    # without these they would fall back to DEFAULT (150K) and silently truncate.
    "claude-sonnet-5":           (800_000, 950_000),
    "claude-opus-5":             (800_000, 950_000),
    "claude-opus-4-8":           (800_000, 950_000),
    "claude-sonnet-4-20250514":  (170_000, 190_000),
}
DEFAULT_THRESHOLDS = (150_000, 190_000)

# Bounded retries for check_token_count's shrink-and-recheck loop (see there).
MAX_SHRINK_ATTEMPTS = 3

# Char/token ratio used ONLY when the real Anthropic tokenizer call fails (see
# _count_tokens) - this used to be the ONLY path: anthropic==0.40.0 (pinned
# until 2026-07-31) never exposed messages.count_tokens at all, so every guard
# decision in this codebase's history ran on this estimate. Verified live
# 2026-07-31 against the Customer module's real 400 (guard passed a slice
# estimated at 855K tokens; Anthropic billed it at 1,094,393) that dense
# tabular/numeric-code report content (repeated short IDs, delimited floats -
# e.g. Customer's correlation-matrix and inconsistency dumps) runs close to
# 2.34 real chars/token, not the 3.0 previously assumed. Tightened to 2.2 for
# margin. The SDK now supports real counting (bumped 2026-07-31), so this only
# fires on a genuine API failure (network/rate-limit) - kept conservative
# rather than accurate, since under-counting here silently disables the guard.
CHARS_PER_TOKEN_FALLBACK = 2.2


class ContextWindowError(Exception):
    """Raised when text exceeds hard limit even after truncation."""


@dataclass
class TokenCheckResult:
    token_count: int
    was_truncated: bool
    original_token_count: int
    text: str


def check_token_count(text: str, model: str) -> TokenCheckResult:
    """
    Count tokens. Truncate if over warn threshold. Raise if over hard limit.

    Args:
        text:  Full prompt text (system + user combined).
        model: Anthropic model string.

    Returns:
        TokenCheckResult - may contain truncated text.

    Raises:
        ContextWindowError: if text exceeds hard limit even after retrying
        truncation MAX_SHRINK_ATTEMPTS times.
    """
    warn_limit, hard_limit = MODEL_THRESHOLDS.get(model, DEFAULT_THRESHOLDS)

    token_count = _count_tokens(text, model)
    original_count = token_count

    if token_count <= warn_limit:
        return TokenCheckResult(
            token_count=token_count,
            was_truncated=False,
            original_token_count=original_count,
            text=text,
        )

    logger.warning(
        "Token count %d exceeds warn threshold %d for model %s - truncating",
        token_count, warn_limit, model,
    )

    target_tokens = int(hard_limit * 0.90)
    text = _truncate_to_tokens(text, model, target_tokens)
    token_count = _count_tokens(text, model)

    # _truncate_to_tokens's char-based target is a starting guess, not a
    # guarantee - real Claude token density varies by content (dense tabular/
    # numeric-code reports run far denser than the assumed CHARS_PER_TOKEN
    # ratio; see Customer module's 2026-07-31 overflow: guessed ~2.34 real
    # chars/token vs the ~3.0 assumed). Rather than fail on one bad guess,
    # shrink proportionally to the actual overage and recheck against the
    # REAL count, bounded so a persistently-wrong estimator still terminates.
    attempts = 0
    while token_count > hard_limit and attempts < MAX_SHRINK_ATTEMPTS:
        attempts += 1
        # Aim comfortably under hard_limit (85%) so the next real count has
        # margin even if this content is denser than the previous guess too.
        shrink_ratio = (hard_limit * 0.85) / token_count
        target_tokens = max(1, int(target_tokens * shrink_ratio))
        text = _truncate_to_tokens(text, model, target_tokens)
        token_count = _count_tokens(text, model)
        logger.info(
            "Shrink attempt %d/%d: %d tokens (target %d)",
            attempts, MAX_SHRINK_ATTEMPTS, token_count, target_tokens,
        )

    logger.info("After truncation: %d tokens (target was %d)", token_count, target_tokens)

    if token_count > hard_limit:
        raise ContextWindowError(
            f"Text exceeds hard limit of {hard_limit} tokens for model {model} "
            f"even after {attempts} truncation retries (got {token_count}). "
            f"Reports are too verbose - trim at the script level."
        )

    return TokenCheckResult(
        token_count=token_count,
        was_truncated=True,
        original_token_count=original_count,
        text=text,
    )


def _count_tokens(text: str, model: str) -> int:
    """Count tokens using the Anthropic API. Falls back to char estimate on failure."""
    try:
        response = _get_client().messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return response.input_tokens
    except Exception as exc:
        logger.warning("Token count API failed (%s) - using character estimate", exc)
        # See CHARS_PER_TOKEN_FALLBACK's comment - must over-count rather than
        # under-count. Under-counting silently disables the truncation guard
        # and the API 400s ("prompt is too long").
        return int(len(text) / CHARS_PER_TOKEN_FALLBACK)


def _truncate_to_tokens(text: str, model: str, target_tokens: int) -> str:
    """
    Truncate text to approximately target_tokens.
    Preserves first 30% and last 70% of target length.
    Inserts a TRUNCATED marker at the cut point.
    """
    chars = len(text)
    target_chars = int(target_tokens * CHARS_PER_TOKEN_FALLBACK)

    if target_chars >= chars:
        return text

    keep_start = int(target_chars * 0.30)
    keep_end = int(target_chars * 0.70)

    return (
        text[:keep_start]
        + "\n\n[... CONTENT TRUNCATED - CONTEXT WINDOW LIMIT REACHED ...]\n\n"
        + text[-keep_end:]
    )
