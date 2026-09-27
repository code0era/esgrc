"""
pipeline/llm/confidence.py
Confidence scoring heuristic for pipeline runs.

Formula (architecture decisions doc):
  score = completeness × 0.40 + stability × 0.35 + benchmark_proximity × 0.25

All DB queries use raw SQL via pipeline.database.session_ctx - same pattern
as shared.py. This avoids ESGRC FK resolution issues AND avoids the sys.path
manipulation that the previous version used to import ESGRC models.

Components:
  completeness:        categories with at least 1 non-null metric / total categories
  stability:           1 - (stddev of last 4 period avg scores / mean)
  benchmark_proximity: mean of most-recent score per category / 100
"""
import logging
import math
from typing import Optional

from sqlalchemy import text

from pipeline.database import session_ctx

logger = logging.getLogger(__name__)

W_COMPLETENESS = 0.40
W_STABILITY    = 0.35
W_BENCHMARK    = 0.25


def compute_confidence(run_id: str) -> float:
    """
    Compute confidence score (0.0–1.0) for a pipeline run.
    Persists result to pipeline_runs.confidence_score.
    Returns 0.5 on any error (neutral default - never crashes the pipeline).
    """
    try:
        org_id = _get_org_id(run_id)
        if org_id is None:
            logger.warning("compute_confidence: run %s not found", run_id)
            return 0.5

        # FIX: completeness/stability/benchmark below all read esg_categories /
        # esg_metrics - ESGRC's own tables, filtered only by org_id. Every other
        # module's run (Customer, Brand, Apex, ...) has no equivalent per-metric
        # DB rows of its own; its data lives only in that run's R2 artifacts.
        # Before this guard, a non-ESGRC run silently got a score computed from
        # whatever ESGRC data happened to exist for the org - a plausible-
        # looking number with zero connection to that run's actual data. Fail
        # OPEN (keep the ESGRC-style computation) when the pipeline type can't
        # be determined, so a run whose definition row is missing for unrelated
        # reasons doesn't regress - this only actively short-circuits runs
        # positively identified as non-ESGRC.
        pipeline_type = _get_pipeline_type(run_id)
        if pipeline_type is not None and pipeline_type != "ESGRC_MODULE":
            logger.info(
                "compute_confidence: run=%s pipeline_type=%s has no ESG metric "
                "data source in the DB - using neutral 0.5 instead of ESGRC's",
                run_id, pipeline_type,
            )
            _persist(run_id, 0.5)
            return 0.5

        completeness = _compute_completeness(org_id)
        stability    = _compute_stability(org_id)
        benchmark    = _compute_benchmark_proximity(org_id)

        score = (
            completeness * W_COMPLETENESS
            + stability  * W_STABILITY
            + benchmark  * W_BENCHMARK
        )
        score = max(0.0, min(1.0, score))

        _persist(run_id, score)

        logger.info(
            "Confidence run=%s score=%.3f (c=%.3f s=%.3f b=%.3f)",
            run_id, score, completeness, stability, benchmark,
        )
        return score

    except Exception as exc:
        logger.error("compute_confidence failed for run %s: %s", run_id, exc)
        return 0.5


def _get_org_id(run_id: str) -> Optional[int]:
    try:
        with session_ctx() as s:
            row = s.execute(
                text("SELECT org_id FROM pipeline_runs WHERE id = :r"),
                {"r": run_id},
            ).fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


def _get_pipeline_type(run_id: str) -> Optional[str]:
    """Pipeline type ('ESGRC_MODULE', 'APEX_ENTERPRISE', 'CUSTOMER_MODULE', ...)
    for a run, joining to its pipeline_definitions row. None if it can't be
    determined (missing row, DB error, etc.) - callers treat that as "unknown"
    rather than "definitely ESGRC" or "definitely not"."""
    try:
        with session_ctx() as s:
            row = s.execute(
                text("""
                    SELECT d.pipeline_type
                    FROM pipeline_runs r
                    JOIN pipeline_definitions d ON d.id = r.pipeline_id
                    WHERE r.id = :r
                """),
                {"r": run_id},
            ).fetchone()
            return str(row[0]) if row else None
    except Exception:
        return None


def _compute_completeness(org_id: int) -> float:
    """
    Fraction of ESG categories (for this org) that have at least one
    non-null scored metric. Returns 1.0 if no categories exist.
    """
    try:
        with session_ctx() as s:
            total = s.execute(
                text("SELECT COUNT(*) FROM esg_categories WHERE org_id = :o"),
                {"o": org_id},
            ).scalar() or 0

            if total == 0:
                return 1.0

            scored = s.execute(
                text("""
                    SELECT COUNT(DISTINCT ec.id)
                    FROM esg_categories ec
                    JOIN esg_metrics em ON em.category_id = ec.id
                    WHERE ec.org_id = :o AND em.score IS NOT NULL
                """),
                {"o": org_id},
            ).scalar() or 0

        return min(1.0, scored / total)
    except Exception as exc:
        logger.warning("_compute_completeness failed: %s", exc)
        return 0.5


def _compute_stability(org_id: int) -> float:
    """
    1 - CV of average scores across the last 4 periods.
    CV = stddev / mean (coefficient of variation).
    Returns 1.0 if fewer than 2 periods of scored data exist.
    """
    try:
        with session_ctx() as s:
            rows = s.execute(
                text("""
                    SELECT em.period, AVG(em.score) AS avg_score
                    FROM esg_metrics em
                    JOIN esg_categories ec ON em.category_id = ec.id
                    WHERE ec.org_id = :o AND em.score IS NOT NULL
                    GROUP BY em.period
                    ORDER BY em.period DESC
                    LIMIT 4
                """),
                {"o": org_id},
            ).fetchall()

        if len(rows) < 2:
            return 1.0

        scores = [float(r[1]) for r in rows if r[1] is not None]
        if len(scores) < 2:
            return 1.0

        mean = sum(scores) / len(scores)
        if mean == 0:
            return 1.0

        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        stddev = math.sqrt(variance)
        cv = stddev / mean
        return max(0.0, 1.0 - cv)

    except Exception as exc:
        logger.warning("_compute_stability failed: %s", exc)
        return 0.5


def _compute_benchmark_proximity(org_id: int) -> float:
    """
    Mean of most-recent ESG score per category / 100.
    Returns 0.5 if no scored metrics exist.
    """
    try:
        with session_ctx() as s:
            # Portable "latest score per category" - avoids Postgres-only
            # DISTINCT ON so the benchmark term works on SQLite too (previously
            # it raised on SQLite and the broad except silently returned 0.5,
            # quietly degrading the confidence score). Averages the scores of
            # each category's most-recent period.
            avg = s.execute(
                text("""
                    SELECT AVG(em.score)
                    FROM esg_metrics em
                    JOIN esg_categories ec ON em.category_id = ec.id
                    WHERE ec.org_id = :o AND em.score IS NOT NULL
                      AND em.period = (
                          SELECT MAX(em2.period)
                          FROM esg_metrics em2
                          WHERE em2.category_id = em.category_id
                            AND em2.score IS NOT NULL
                      )
                """),
                {"o": org_id},
            ).scalar()

        if avg is None:
            return 0.5
        return max(0.0, min(1.0, float(avg) / 100.0))

    except Exception as exc:
        logger.warning("_compute_benchmark_proximity failed: %s", exc)
        return 0.5


def _persist(run_id: str, score: float) -> None:
    try:
        with session_ctx() as s:
            s.execute(
                text("UPDATE pipeline_runs SET confidence_score = :score WHERE id = :r"),
                {"score": score, "r": run_id},
            )
    except Exception as exc:
        logger.error("_persist confidence score failed: %s", exc)
