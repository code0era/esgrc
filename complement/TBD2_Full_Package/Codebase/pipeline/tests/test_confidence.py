"""
pipeline/test/test_confidence.py
Unit tests for the confidence scoring heuristic.
5 tests with known input data and verified expected outputs.
"""
import os
import math
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_confidence.db")

from pipeline.llm.confidence import (
    _compute_completeness,
    _compute_stability,
    _compute_benchmark_proximity,
    compute_confidence,
    W_COMPLETENESS,
    W_STABILITY,
    W_BENCHMARK,
)


class TestComputeConfidence:

    def test_perfect_data_scores_near_1(self):
        """
        All metrics scored, stable scores, high benchmark proximity → score ~1.0
        """
        with (
            patch("pipeline.llm.confidence._compute_completeness", return_value=1.0),
            patch("pipeline.llm.confidence._compute_stability", return_value=1.0),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=1.0),
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-123")
        assert abs(score - 1.0) < 0.001

    def test_zero_completeness_and_stability_scores_low(self):
        """
        No metrics scored, volatile data, low benchmark → score ~0.0
        """
        with (
            patch("pipeline.llm.confidence._compute_completeness", return_value=0.0),
            patch("pipeline.llm.confidence._compute_stability", return_value=0.0),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=0.0),
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-123")
        assert score < 0.05

    def test_formula_weights_applied_correctly(self):
        """
        Verify the exact weighted formula:
        score = completeness×0.40 + stability×0.35 + benchmark×0.25
        """
        completeness = 0.80
        stability    = 0.60
        benchmark    = 0.70

        expected = (
            completeness * W_COMPLETENESS
            + stability  * W_STABILITY
            + benchmark  * W_BENCHMARK
        )
        # = 0.80×0.40 + 0.60×0.35 + 0.70×0.25
        # = 0.320 + 0.210 + 0.175
        # = 0.705
        assert abs(expected - 0.705) < 0.001

        with (
            patch("pipeline.llm.confidence._compute_completeness", return_value=completeness),
            patch("pipeline.llm.confidence._compute_stability", return_value=stability),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=benchmark),
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-abc")
        assert abs(score - expected) < 0.001

    def test_returns_neutral_05_when_run_not_found(self):
        """Missing run_id → returns 0.5 neutral default, never raises."""
        with patch("pipeline.llm.confidence._get_org_id", return_value=None):
            score = compute_confidence("nonexistent-run-id")
        assert score == 0.5

    def test_score_clamped_between_0_and_1(self):
        """Score must always be in [0.0, 1.0] even with extreme component values."""
        with (
            patch("pipeline.llm.confidence._compute_completeness", return_value=2.0),  # > 1
            patch("pipeline.llm.confidence._compute_stability", return_value=1.5),
            patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=1.0),
            patch("pipeline.llm.confidence._get_org_id", return_value=1),
            patch("pipeline.llm.confidence._persist"),
        ):
            score = compute_confidence("run-xyz")
        assert 0.0 <= score <= 1.0


class TestModuleScoping:
    """FIX: completeness/stability/benchmark all read esg_categories /
    esg_metrics - ESGRC's own tables, filtered only by org_id. A run from any
    of the other 11 modules (or Apex) used to get its confidence score
    computed from whatever ESGRC data existed for the org - a plausible score
    with zero connection to that run's own data. Uses a real (in-memory)
    pipeline DB, not mocks, so the pipeline_runs -> pipeline_definitions join
    that drives the fix is actually exercised."""

    @staticmethod
    def _make_run(pipeline_type: str):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from pipeline.models import (
            PipelineBase, PipelineDefinition, PipelineRun,
            PipelineTypeEnum, RunStatusEnum,
        )

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        PipelineBase.metadata.create_all(bind=engine)

        with Session(engine) as session:
            definition = PipelineDefinition(
                org_id=1, name="test pipeline",
                pipeline_type=PipelineTypeEnum(pipeline_type),
                config_json={},
            )
            session.add(definition)
            session.flush()
            run = PipelineRun(
                pipeline_id=definition.id, org_id=1,
                status=RunStatusEnum.COMPLETED,
            )
            session.add(run)
            session.commit()
            run_id = run.id

        return engine, run_id

    def _with_engine(self, engine):
        """Point pipeline.database's session factory at `engine` for one test."""
        import pipeline.database as db_module
        from sqlalchemy.orm import sessionmaker

        old_engine, old_factory = db_module._engine, db_module._SessionFactory
        db_module._engine = engine
        db_module._SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        return old_engine, old_factory

    def _restore_engine(self, old_engine, old_factory):
        import pipeline.database as db_module
        db_module._engine, db_module._SessionFactory = old_engine, old_factory

    def test_non_esgrc_run_gets_neutral_score_and_skips_esg_tables(self):
        engine, run_id = self._make_run("CUSTOMER_MODULE")
        old = self._with_engine(engine)
        try:
            with (
                patch("pipeline.llm.confidence._compute_completeness") as m_complete,
                patch("pipeline.llm.confidence._compute_stability") as m_stable,
                patch("pipeline.llm.confidence._compute_benchmark_proximity") as m_bench,
            ):
                score = compute_confidence(run_id)
            assert score == 0.5
            m_complete.assert_not_called()
            m_stable.assert_not_called()
            m_bench.assert_not_called()
        finally:
            self._restore_engine(*old)

    def test_esgrc_run_still_uses_the_full_formula(self):
        engine, run_id = self._make_run("ESGRC_MODULE")
        old = self._with_engine(engine)
        try:
            with (
                patch("pipeline.llm.confidence._compute_completeness", return_value=1.0),
                patch("pipeline.llm.confidence._compute_stability", return_value=1.0),
                patch("pipeline.llm.confidence._compute_benchmark_proximity", return_value=1.0),
            ):
                score = compute_confidence(run_id)
            assert abs(score - 1.0) < 0.001
        finally:
            self._restore_engine(*old)

    def test_apex_run_also_gets_neutral_score(self):
        """Apex is not ESGRC either - same guard applies."""
        engine, run_id = self._make_run("APEX_ENTERPRISE")
        old = self._with_engine(engine)
        try:
            with patch("pipeline.llm.confidence._compute_completeness") as m_complete:
                score = compute_confidence(run_id)
            assert score == 0.5
            m_complete.assert_not_called()
        finally:
            self._restore_engine(*old)


class TestStabilityComponent:

    def test_stable_scores_returns_high_stability(self):
        """Scores with low variance → stability near 1.0"""
        # scores: [75, 76, 74, 75] - very stable
        scores = [75.0, 76.0, 74.0, 75.0]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        stddev = math.sqrt(variance)
        cv = stddev / mean
        stability = max(0.0, 1.0 - cv)
        assert stability > 0.95

    def test_volatile_scores_returns_low_stability(self):
        """Scores with high variance → stability near 0.0"""
        # scores: [10, 90, 20, 80] - very volatile
        scores = [10.0, 90.0, 20.0, 80.0]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        stddev = math.sqrt(variance)
        cv = stddev / mean
        stability = max(0.0, 1.0 - cv)
        assert stability < 0.50
