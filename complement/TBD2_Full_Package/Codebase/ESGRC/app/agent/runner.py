"""
Agent runner - orchestrates one full batch cycle across all organisations.

Called by the scheduler (scheduler.py) on the configured cron schedule.
Can also be triggered manually via POST /agent/run (for testing/admin use).

Architecture:
  runner.run_batch()
    ├── opens a single DB session for the whole run
    ├── creates an AgentRunLog row with status=RUNNING
    ├── loads all active organisations
    ├── for each org:
    │     ├── task 1: score_unscored_metrics
    │     ├── task 2: flag_overdue_requirements
    │     └── task 3: escalate_critical_risks
    ├── updates AgentRunLog with totals and status=SUCCESS / PARTIAL
    └── closes the session

Error handling:
  - Per-org errors are caught, logged, and recorded in the run details.
    The run continues for remaining orgs (PARTIAL status, not FAILED).
  - A top-level exception that prevents any processing sets status=FAILED.
  - The session is always closed in the finally block.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tasks import (
    escalate_critical_risks,
    flag_overdue_requirements,
    score_unscored_metrics,
)
from app.database import SessionLocal
from app.models.models import AgentRunLog, AgentRunStatus, Organisation
from app.config import settings

logger = logging.getLogger(__name__)


def run_batch(session_factory=None) -> AgentRunLog:
    """
    Execute one full agent batch cycle.

    Opens its own DB session using session_factory (defaults to the
    production SessionLocal). Tests can inject a custom factory that
    returns the in-memory test session.

    Returns the completed AgentRunLog record.
    """
    factory = session_factory or SessionLocal
    db: Session = factory()
    run_log: AgentRunLog | None = None

    try:
        # ── Create the run log entry ──────────────────────────────────────────
        run_log = AgentRunLog(status=AgentRunStatus.RUNNING)
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        logger.info("Agent batch run started - log id=%s", run_log.id)

        # ── Load all active organisations ─────────────────────────────────────
        orgs = list(
            db.scalars(
                select(Organisation).where(Organisation.active.is_(True))
            ).all()
        )
        logger.info("Processing %s active organisations", len(orgs))

        # ── Per-org totals ────────────────────────────────────────────────────
        total_scored = 0
        total_flagged = 0
        total_escalated = 0
        org_details = []
        had_errors = False

        for org in orgs:
            org_result = {
                "org_id": org.id,
                "org_name": org.name,
                "metrics_scored": 0,
                "requirements_flagged": 0,
                "risks_escalated": 0,
                "error": None,
            }

            try:
                # Task 1 - Score unscored ESG metrics
                score_result = score_unscored_metrics(db, org.id)
                org_result["metrics_scored"] = score_result["scored"]
                total_scored += score_result["scored"]

                # Task 2 - Flag overdue compliance requirements
                flag_result = flag_overdue_requirements(db, org.id)
                org_result["requirements_flagged"] = flag_result["flagged"]
                total_flagged += flag_result["flagged"]

                # Task 3 - Escalate critical overdue risks
                esc_result = escalate_critical_risks(db, org.id)
                org_result["risks_escalated"] = esc_result["escalated"]
                total_escalated += esc_result["escalated"]

                logger.info(
                    "org_id=%s (%s): scored=%s flagged=%s escalated=%s",
                    org.id, org.name,
                    score_result["scored"],
                    flag_result["flagged"],
                    esc_result["escalated"],
                )

            except Exception as exc:
                had_errors = True
                org_result["error"] = str(exc)
                logger.exception(
                    "Error processing org_id=%s (%s): %s", org.id, org.name, exc
                )
                # Roll back any partial writes for this org
                db.rollback()

            org_details.append(org_result)

        # ── Finalise the run log ──────────────────────────────────────────────
        run_log.finished_at = datetime.now(timezone.utc)
        run_log.status = AgentRunStatus.PARTIAL if had_errors else AgentRunStatus.SUCCESS
        run_log.orgs_processed = len(orgs)
        run_log.metrics_scored = total_scored
        run_log.risks_escalated = total_escalated
        run_log.requirements_flagged = total_flagged
        run_log.details = json.dumps(org_details)
        db.commit()
        db.refresh(run_log)

        logger.info(
            "Agent batch run complete - id=%s status=%s "
            "orgs=%s scored=%s flagged=%s escalated=%s",
            run_log.id, run_log.status.value,
            len(orgs), total_scored, total_flagged, total_escalated,
        )
        return run_log

    except Exception as exc:
        # Top-level failure - could not even start processing orgs
        logger.exception("Agent batch run FAILED: %s", exc)
        db.rollback()
        if run_log is not None:
            try:
                run_log.finished_at = datetime.now(timezone.utc)
                run_log.status = AgentRunStatus.FAILED
                run_log.error_message = str(exc)
                db.commit()
            except Exception:
                pass  # best-effort - don't mask the original error
        raise

    finally:
        db.close()


# ─── LLM-powered batch runner ─────────────────────────────────────────────────

def run_llm_batch(session_factory=None) -> AgentRunLog:
    """
    Execute one full LLM-powered analysis cycle across all organisations.

    Follows the same pattern as run_batch() but calls the LLM orchestrator
    for each org instead of the rule-based tasks.

    The LLM agent:
    1. Reads the org snapshot
    2. Identifies unscored metrics, overdue requirements, critical risks
    3. Delegates to specialist agent for scoring and classification
    4. Writes results back to the database
    5. Records findings in the run log

    Requires ANTHROPIC_API_KEY to be configured.
    """
    from app.agent.llm_agent import run_llm_batch_for_org
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Configure it in .env to use the LLM agent."
        )

    factory = session_factory or SessionLocal
    db: Session = factory()
    run_log: AgentRunLog | None = None

    try:
        run_log = AgentRunLog(status=AgentRunStatus.RUNNING)
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        logger.info("LLM agent batch run started - log id=%s", run_log.id)

        orgs = list(
            db.scalars(
                select(Organisation).where(Organisation.active.is_(True))
            ).all()
        )
        logger.info("LLM agent processing %s active organisations", len(orgs))

        total_scored = 0
        total_classified = 0
        total_escalated = 0
        org_details = []
        had_errors = False

        for org in orgs:
            org_result = {
                "org_id": org.id,
                "org_name": org.name,
                "metrics_scored": 0,
                "requirements_classified": 0,
                "risks_escalated": 0,
                "findings_summary": None,
                "error": None,
            }

            try:
                result = run_llm_batch_for_org(db, org.id, org.name)
                org_result["metrics_scored"] = result["metrics_scored"]
                org_result["requirements_classified"] = result["requirements_classified"]
                org_result["risks_escalated"] = result["risks_escalated"]
                # Store the full structured L1_ESRC_Risk_Assessment JSON, not just a text summary
                findings = result.get("findings", {})
                org_result["l1_risk_assessment"] = findings if findings else None
                org_result["iterations"] = result.get("iterations", 0)

                total_scored += result["metrics_scored"]
                total_classified += result["requirements_classified"]
                total_escalated += result["risks_escalated"]

                logger.info(
                    "LLM agent org_id=%s (%s): scored=%s classified=%s escalated=%s iterations=%s",
                    org.id, org.name,
                    result["metrics_scored"],
                    result["requirements_classified"],
                    result["risks_escalated"],
                    result.get("iterations", 0),
                )

            except Exception as exc:
                had_errors = True
                org_result["error"] = str(exc)
                logger.exception(
                    "LLM agent error for org_id=%s (%s): %s", org.id, org.name, exc
                )
                db.rollback()

            org_details.append(org_result)

        run_log.finished_at = datetime.now(timezone.utc)
        run_log.status = AgentRunStatus.PARTIAL if had_errors else AgentRunStatus.SUCCESS
        run_log.orgs_processed = len(orgs)
        run_log.metrics_scored = total_scored
        run_log.risks_escalated = total_escalated
        # Store classified requirements in requirements_flagged field
        run_log.requirements_flagged = total_classified
        run_log.details = json.dumps(org_details)
        db.commit()
        db.refresh(run_log)

        logger.info(
            "LLM agent batch complete - id=%s status=%s "
            "orgs=%s scored=%s classified=%s escalated=%s",
            run_log.id, run_log.status.value,
            len(orgs), total_scored, total_classified, total_escalated,
        )
        return run_log

    except Exception as exc:
        logger.exception("LLM agent batch FAILED: %s", exc)
        db.rollback()
        if run_log is not None:
            try:
                run_log.finished_at = datetime.now(timezone.utc)
                run_log.status = AgentRunStatus.FAILED
                run_log.error_message = str(exc)
                db.commit()
            except Exception:
                pass
        raise

    finally:
        db.close()


# ─── Split runners: daily ESG/Risk + periodic Compliance ──────────────────────

def run_batch_esg_risk(session_factory=None) -> AgentRunLog:
    """
    Daily batch: score unscored ESG metrics + escalate critical risks.
    Compliance flagging is intentionally excluded - it runs every
    COMPLIANCE_CHECK_DAYS days via run_batch_compliance() instead.

    This is the function called by the daily APScheduler job.
    """
    from app.agent.tasks import score_unscored_metrics, escalate_critical_risks

    factory = session_factory or SessionLocal
    db: Session = factory()
    run_log: AgentRunLog | None = None

    try:
        run_log = AgentRunLog(status=AgentRunStatus.RUNNING)
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        logger.info("Daily ESG/Risk batch started - log id=%s", run_log.id)

        orgs = list(db.scalars(select(Organisation).where(Organisation.active.is_(True))).all())
        total_scored = 0
        total_escalated = 0
        org_details = []
        had_errors = False

        for org in orgs:
            org_result = {"org_id": org.id, "org_name": org.name,
                          "metrics_scored": 0, "risks_escalated": 0, "error": None}
            try:
                s = score_unscored_metrics(db, org.id)
                e = escalate_critical_risks(db, org.id)
                org_result["metrics_scored"] = s["scored"]
                org_result["risks_escalated"] = e["escalated"]
                total_scored += s["scored"]
                total_escalated += e["escalated"]
            except Exception as exc:
                had_errors = True
                org_result["error"] = str(exc)
                logger.exception("ESG/Risk batch error for org_id=%s: %s", org.id, exc)
                db.rollback()
            org_details.append(org_result)

        run_log.finished_at = datetime.now(timezone.utc)
        run_log.status = AgentRunStatus.PARTIAL if had_errors else AgentRunStatus.SUCCESS
        run_log.orgs_processed = len(orgs)
        run_log.metrics_scored = total_scored
        run_log.risks_escalated = total_escalated
        run_log.requirements_flagged = 0
        run_log.details = json.dumps(org_details)
        db.commit()
        db.refresh(run_log)
        logger.info("Daily ESG/Risk batch complete - id=%s status=%s scored=%s escalated=%s",
                    run_log.id, run_log.status.value, total_scored, total_escalated)
        return run_log

    except Exception as exc:
        logger.exception("Daily ESG/Risk batch FAILED: %s", exc)
        db.rollback()
        if run_log is not None:
            try:
                run_log.finished_at = datetime.now(timezone.utc)
                run_log.status = AgentRunStatus.FAILED
                run_log.error_message = str(exc)
                db.commit()
            except Exception:
                pass
        raise
    finally:
        db.close()


def run_batch_compliance(session_factory=None) -> AgentRunLog:
    """
    Compliance batch (every COMPLIANCE_CHECK_DAYS days, default 15):
    flags requirements whose review_date has passed for re-review.

    Separated from the daily batch on Praveen's recommendation - daily
    compliance alerts cause noise; a 15-day cadence matches real-world
    compliance review cycles.
    """
    from app.agent.tasks import flag_overdue_requirements

    factory = session_factory or SessionLocal
    db: Session = factory()
    run_log: AgentRunLog | None = None

    try:
        run_log = AgentRunLog(status=AgentRunStatus.RUNNING)
        db.add(run_log)
        db.commit()
        db.refresh(run_log)
        logger.info("Compliance batch started - log id=%s", run_log.id)

        orgs = list(db.scalars(select(Organisation).where(Organisation.active.is_(True))).all())
        total_flagged = 0
        org_details = []
        had_errors = False

        for org in orgs:
            org_result = {"org_id": org.id, "org_name": org.name,
                          "requirements_flagged": 0, "error": None}
            try:
                f = flag_overdue_requirements(db, org.id)
                org_result["requirements_flagged"] = f["flagged"]
                total_flagged += f["flagged"]
            except Exception as exc:
                had_errors = True
                org_result["error"] = str(exc)
                logger.exception("Compliance batch error for org_id=%s: %s", org.id, exc)
                db.rollback()
            org_details.append(org_result)

        run_log.finished_at = datetime.now(timezone.utc)
        run_log.status = AgentRunStatus.PARTIAL if had_errors else AgentRunStatus.SUCCESS
        run_log.orgs_processed = len(orgs)
        run_log.metrics_scored = 0
        run_log.risks_escalated = 0
        run_log.requirements_flagged = total_flagged
        run_log.details = json.dumps(org_details)
        db.commit()
        db.refresh(run_log)
        logger.info("Compliance batch complete - id=%s status=%s flagged=%s",
                    run_log.id, run_log.status.value, total_flagged)
        return run_log

    except Exception as exc:
        logger.exception("Compliance batch FAILED: %s", exc)
        db.rollback()
        if run_log is not None:
            try:
                run_log.finished_at = datetime.now(timezone.utc)
                run_log.status = AgentRunStatus.FAILED
                run_log.error_message = str(exc)
                db.commit()
            except Exception:
                pass
        raise
    finally:
        db.close()
