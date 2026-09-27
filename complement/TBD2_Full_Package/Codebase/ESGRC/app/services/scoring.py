"""
ESG scoring service - pure scoring math, no FastAPI dependencies.

compute_score(value, benchmark) → float
  Applies linear interpolation between baseline_value (→ 0) and
  target_value (→ 100), clamped to [0, 100].

  LOWER_IS_BETTER (e.g. carbon emissions):
    score = clamp((baseline - value) / (baseline - target) * 100, 0, 100)

  HIGHER_IS_BETTER (e.g. renewable energy %):
    score = clamp((value - baseline) / (target - baseline) * 100, 0, 100)

This module is imported by:
  - app/crud/crud.py            (apply_score_to_metric)
  - app/agent/tasks.py          (score_unscored_metrics)
  - app/agent/tools.py (indirectly via tasks)
"""

import logging

from app.models.models import ESGScoreBenchmark, ScoringDirection

logger = logging.getLogger(__name__)


def compute_score(value: float, benchmark: ESGScoreBenchmark) -> float:
    """
    Compute a 0-100 score for the given value against the benchmark.

    Args:
        value:     The raw metric value to score.
        benchmark: The ESGScoreBenchmark ORM object with target_value,
                   baseline_value, and direction.

    Returns:
        A float in [0.0, 100.0] representing the normalised score.

    Raises:
        ValueError: If target_value == baseline_value (degenerate benchmark).
    """
    target = benchmark.target_value
    baseline = benchmark.baseline_value

    if abs(target - baseline) < 1e-9:
        logger.warning(
            "Degenerate benchmark id=%s: target_value == baseline_value == %.4f. "
            "Returning score 0.",
            benchmark.id, target,
        )
        return 0.0

    if benchmark.direction == ScoringDirection.LOWER_IS_BETTER:
        raw = (baseline - value) / (baseline - target) * 100.0
    else:  # HIGHER_IS_BETTER
        raw = (value - baseline) / (target - baseline) * 100.0

    score = max(0.0, min(100.0, raw))
    logger.debug(
        "compute_score: value=%.4f target=%.4f baseline=%.4f direction=%s → %.2f",
        value, target, baseline, benchmark.direction.value, score,
    )
    return round(score, 2)
