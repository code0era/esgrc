"""
pipeline/scripts/seed_demo.py
Demo data seed script - populates the database with realistic demo data in <30 seconds.

Usage:
    DATABASE_URL=postgresql+psycopg://... python pipeline/scripts/seed_demo.py

Creates:
  - 1 demo organisation: Vigilant Lens Demo Corp
  - 5 users incl. admin@demo.com, analyst@demo.com, viewer@demo.com (password: Demo1234!)
    plus module-scoped esgrc.admin@ and apex.admin@
  - 14 ESG categories with all pipeline metric_codes
  - ESG metrics for 4 periods (2024-Q1 → 2024-Q4) with varied scores
  - 12 risks across all levels and statuses (3 in critical zone)
  - 2 compliance frameworks (GRI, ISO 14001) with 20 requirements each
  - 12 pipeline definitions: ESGRC, Customer, Shared, Business Partner, Enterprise,
    IT Processes, Product, Resource, Service, Brand Management, Market and Sales, Apex
  - 1 completed ESGRC pipeline run (all 7 steps, 1 Claude recommendation)
  - 1 completed Customer pipeline run (all 7 steps, 1 Claude recommendation)
  - 1 completed Apex pipeline run (all 8 steps, 2 Claude recommendations)
  - 3 agent run logs

Run once before the demo - idempotent (safe to run multiple times).
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Add ESGRC to path so we can use its models
ESGRC_PATH = os.environ.get("ESGRC_PATH", os.path.join(os.path.dirname(__file__), "../../ESGRC"))
sys.path.insert(0, ESGRC_PATH)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tbd2_demo.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def now() -> datetime:
    return datetime.now(timezone.utc)


def past(days: int) -> datetime:
    return now() - timedelta(days=days)


def run():
    print("🌱 Seeding demo data...")
    t0 = datetime.now()

    from app.models.models import (
        Organisation, User, ESGCategory, ESGMetric, ESGScoreBenchmark,
        Risk, ComplianceFramework, ComplianceRequirement, AgentRunLog,
        UserRole, ESGPillar, RiskStatus, RiskLevel,
        ComplianceStatus,
    )
    from app.services.auth import hash_password
    from pipeline.modules import MODULES
    from pipeline.models import (
        PipelineBase, PipelineDefinition, PipelineRun, PipelineStepResult,
        PipelineLLMOutput, PipelineTypeEnum, RunStatusEnum, StepStatusEnum,
        AnalysisTypeEnum,
    )
    from pipeline.prompt_models import PipelinePrompt
    from app.database import Base

    # Create all tables
    Base.metadata.create_all(bind=engine)
    PipelineBase.metadata.create_all(bind=engine)

    with Session(engine) as session:
        # ── Clean up existing demo data ────────────────────────────────────
        existing_org = session.query(Organisation).filter_by(slug="vigilant-lens-demo").first()
        if existing_org:
            print("   Demo org already exists - cleaning up first...")
            session.delete(existing_org)
            session.commit()

        # ── Organisation ───────────────────────────────────────────────────
        org = Organisation(
            name="Vigilant Lens Demo Corp",
            slug="vigilant-lens-demo",
            active=True,
        )
        session.add(org)
        session.flush()
        print(f"   ✓ Organisation: {org.name} (id={org.id})")

        # ── Users ──────────────────────────────────────────────────────────
        demo_password = hash_password("Demo1234!")
        users = [
            # Cross-module admin - sees every module built so far.
            User(organisation_id=org.id, email="admin@demo.com",
                 full_name="Demo Admin", hashed_password=demo_password,
                 role=UserRole.ADMIN, is_active=True,
                 module_access=["esgrc", "customer", "shared", "bspt", "enterprise",
                                 "ictm", "product", "resource", "service", "brand",
                                 "mkts", "integration", "apex"]),
            # ESGRC-module users.
            User(organisation_id=org.id, email="analyst@demo.com",
                 full_name="Demo Analyst", hashed_password=demo_password,
                 role=UserRole.ANALYST, is_active=True,
                 module_access=["esgrc"]),
            User(organisation_id=org.id, email="viewer@demo.com",
                 full_name="Demo Viewer", hashed_password=demo_password,
                 role=UserRole.VIEWER, is_active=True,
                 module_access=["esgrc"]),
            # Module-scoped admins - each sees ONLY its module.
            User(organisation_id=org.id, email="esgrc.admin@demo.com",
                 full_name="ESGRC Admin", hashed_password=demo_password,
                 role=UserRole.ADMIN, is_active=True,
                 module_access=["esgrc"]),
            User(organisation_id=org.id, email="apex.admin@demo.com",
                 full_name="Apex Admin", hashed_password=demo_password,
                 role=UserRole.ADMIN, is_active=True,
                 module_access=["apex"]),
            User(organisation_id=org.id, email="customer.admin@demo.com",
                 full_name="Customer Admin", hashed_password=demo_password,
                 role=UserRole.ADMIN, is_active=True,
                 module_access=["customer"]),
        ]
        for u in users:
            session.add(u)
        session.flush()
        admin_user = users[0]
        print(f"   ✓ Users (password Demo1234!): admin@demo.com [esgrc+apex+customer+shared+bspt], "
              f"analyst@/viewer@demo.com [esgrc], esgrc.admin@demo.com [esgrc], "
              f"apex.admin@demo.com [apex], customer.admin@demo.com [customer]")

        # ── ESG Categories (14 sub-modules) ───────────────────────────────
        category_defs = [
            ("Carbon Emissions",           "ESU10102", ESGPillar.ENVIRONMENTAL, "tonnes CO2e"),
            ("Energy Consumption",          "ESU10201", ESGPillar.ENVIRONMENTAL, "MWh"),
            ("Water Usage",                 "ESU10301", ESGPillar.ENVIRONMENTAL, "m³"),
            ("Employee Safety",             "SSU10101", ESGPillar.SOCIAL,        "incidents/1000"),
            ("Training Hours",              "SSU10201", ESGPillar.SOCIAL,        "hours/employee"),
            ("Diversity Index",             "SSU10301", ESGPillar.SOCIAL,        "%"),
            ("Board Independence",          "CGS10101", ESGPillar.GOVERNANCE,    "%"),
            ("Cybersecurity Score",         "CSU10101", ESGPillar.GOVERNANCE,    "score 0-100"),
            ("Policy Compliance Rate",      "POL10101", ESGPillar.GOVERNANCE,    "%"),
            ("Regulatory Filings OnTime",   "REG10101", ESGPillar.GOVERNANCE,    "%"),
            ("Ethics Violations",           "ETI10101", ESGPillar.GOVERNANCE,    "count"),
            ("Audit Findings",              "AUD10101", ESGPillar.GOVERNANCE,    "count"),
            ("GRC Framework Coverage",      "GRC10101", ESGPillar.GOVERNANCE,    "%"),
            ("Risk Register Completeness",  "ERM10101", ESGPillar.GOVERNANCE,    "%"),
        ]
        categories = []
        for name, code, pillar, unit in category_defs:
            cat = ESGCategory(
                org_id=org.id, name=name, metric_code=code,
                pillar=pillar, unit=unit,
                description=f"Demo category: {name}",
            )
            session.add(cat)
            categories.append(cat)
        session.flush()
        print(f"   ✓ ESG Categories: {len(categories)} created")

        # ── Benchmarks ─────────────────────────────────────────────────────
        from app.models.models import ScoringDirection
        benchmark_defs = {
            "ESU10102": (200.0, 500.0, ScoringDirection.LOWER_IS_BETTER),
            "ESU10201": (1000.0, 5000.0, ScoringDirection.LOWER_IS_BETTER),
            "ESU10301": (500.0, 2000.0, ScoringDirection.LOWER_IS_BETTER),
            "SSU10101": (0.5, 5.0, ScoringDirection.LOWER_IS_BETTER),
            "SSU10201": (40.0, 10.0, ScoringDirection.HIGHER_IS_BETTER),
            "SSU10301": (50.0, 20.0, ScoringDirection.HIGHER_IS_BETTER),
            "CGS10101": (75.0, 40.0, ScoringDirection.HIGHER_IS_BETTER),
            "CSU10101": (85.0, 40.0, ScoringDirection.HIGHER_IS_BETTER),
            "POL10101": (95.0, 60.0, ScoringDirection.HIGHER_IS_BETTER),
            "REG10101": (98.0, 70.0, ScoringDirection.HIGHER_IS_BETTER),
            "ETI10101": (0.0, 10.0, ScoringDirection.LOWER_IS_BETTER),
            "AUD10101": (1.0, 15.0, ScoringDirection.LOWER_IS_BETTER),
            "GRC10101": (90.0, 40.0, ScoringDirection.HIGHER_IS_BETTER),
            "ERM10101": (85.0, 30.0, ScoringDirection.HIGHER_IS_BETTER),
        }
        benchmarks_by_category = {}
        for cat in categories:
            if cat.metric_code in benchmark_defs:
                target, baseline, direction = benchmark_defs[cat.metric_code]
                bm = ESGScoreBenchmark(
                    category_id=cat.id,
                    target_value=target,
                    baseline_value=baseline,
                    direction=direction,
                )
                session.add(bm)
                benchmarks_by_category[cat.id] = bm
        session.flush()

        # ── ESG Metrics (4 periods, varied scores showing trend) ──────────
        periods = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
        metric_values = {
            "ESU10102": [420, 395, 370, 342],   # improving (lower = better)
            "ESU10201": [3800, 3600, 3400, 3100],
            "ESU10301": [1600, 1550, 1480, 1420],
            "SSU10101": [3.2, 2.8, 2.5, 2.1],
            "SSU10201": [28, 31, 35, 38],        # improving (higher = better)
            "SSU10301": [32, 35, 38, 41],
            "CGS10101": [55, 58, 62, 65],
            "CSU10101": [62, 65, 70, 74],
            "POL10101": [78, 82, 85, 88],
            "REG10101": [88, 90, 92, 94],
            "ETI10101": [4, 3, 2, 1],
            "AUD10101": [8, 7, 5, 3],
            "GRC10101": [55, 62, 68, 72],
            "ERM10101": [48, 55, 62, 70],
        }
        # Score each metric at seed time using the SAME derivation the app uses
        # (app/services/scoring.py, via crud.apply_score_to_metric and the agent's
        # score_unscored_metrics). These used to be left as score=None "to be scored
        # by the agent", but the demo runs with the LLM agent disabled, so they
        # stayed NULL forever. That silently zeroed the confidence score's
        # completeness component - pipeline/llm/confidence.py counts categories
        # having at least one non-null score - pinning EVERY run in the demo org at
        # 0.475 regardless of module. Seeding the derived score fixes that at source
        # without inventing numbers: value and benchmark are unchanged, the score is
        # just computed rather than deferred.
        from app.services.scoring import compute_score

        metric_count = 0
        scored_count = 0
        for cat in categories:
            vals = metric_values.get(cat.metric_code, [50, 55, 60, 65])
            benchmark = benchmarks_by_category.get(cat.id)
            for i, period in enumerate(periods):
                value = float(vals[i])
                score = compute_score(value, benchmark) if benchmark is not None else None
                m = ESGMetric(
                    category_id=cat.id,
                    organisation="Vigilant Lens Demo Corp",
                    value=value,
                    period=period,
                    score=score,
                )
                session.add(m)
                metric_count += 1
                if score is not None:
                    scored_count += 1
        session.flush()
        print(f"   ✓ ESG Metrics: {metric_count} data points across 4 periods "
              f"({scored_count} scored against their category benchmark)")

        # ── Risks ──────────────────────────────────────────────────────────
        risk_defs = [
            ("Climate regulatory non-compliance", RiskLevel.CRITICAL,
             RiskStatus.OPEN, 5, 5, -30),
            ("Cybersecurity breach - OT systems", RiskLevel.CRITICAL,
             RiskStatus.IN_PROGRESS, 4, 5, -15),
            ("Supply chain ESG violations", RiskLevel.CRITICAL,
             RiskStatus.OPEN, 4, 4, -45),
            ("Data privacy breach (PIPEDA)", RiskLevel.HIGH,
             RiskStatus.IN_PROGRESS, 3, 5, -20),
            ("GRC framework gaps", RiskLevel.HIGH,
             RiskStatus.OPEN, 4, 3, -10),
            ("Board diversity non-compliance", RiskLevel.HIGH,
             RiskStatus.IN_PROGRESS, 3, 4, -30),
            ("Employee safety incident increase", RiskLevel.MEDIUM,
             RiskStatus.MITIGATED, 2, 3, -60),
            ("Policy review backlog", RiskLevel.MEDIUM,
             RiskStatus.IN_PROGRESS, 3, 2, -5),
            ("Audit finding overdue resolution", RiskLevel.MEDIUM,
             RiskStatus.OPEN, 2, 3, 30),
            ("Carbon reporting inaccuracy", RiskLevel.MEDIUM,
             RiskStatus.IN_PROGRESS, 2, 2, -15),
            ("Water usage target miss", RiskLevel.LOW,
             RiskStatus.MITIGATED, 1, 2, -90),
            ("Training compliance gap", RiskLevel.LOW,
             RiskStatus.CLOSED, 1, 1, -120),
        ]
        for title, level, status, likelihood, impact, due_offset in risk_defs:
            r = Risk(
                org_id=org.id,
                title=title,
                level=level,
                status=status,
                likelihood=likelihood,
                impact=impact,
                # risk_score is a computed property (likelihood * impact) - not settable
                due_date=now() + timedelta(days=due_offset) if due_offset else None,
            )
            session.add(r)
        session.flush()
        print(f"   ✓ Risks: {len(risk_defs)} risks (3 critical, 3 high, 4 medium, 2 low)")

        # ── Compliance Frameworks ──────────────────────────────────────────
        gri = ComplianceFramework(
            org_id=org.id, name="GRI Standards", version="2021", active=True
        )
        iso = ComplianceFramework(
            org_id=org.id, name="ISO 14001", version="2015", active=True
        )
        session.add_all([gri, iso])
        session.flush()

        gri_requirements = [
            ("GRI 102-1", "Organisation Name", ComplianceStatus.COMPLIANT),
            ("GRI 102-2", "Activities and Brands", ComplianceStatus.COMPLIANT),
            ("GRI 302-1", "Energy Consumption", ComplianceStatus.PARTIAL),
            ("GRI 302-3", "Energy Intensity", ComplianceStatus.PARTIAL),
            ("GRI 303-1", "Water Withdrawal", ComplianceStatus.COMPLIANT),
            ("GRI 305-1", "Direct GHG Emissions", ComplianceStatus.PARTIAL),
            ("GRI 305-2", "Indirect GHG Emissions", ComplianceStatus.NON_COMPLIANT),
            ("GRI 306-1", "Waste Generation", ComplianceStatus.NOT_ASSESSED),
            ("GRI 401-1", "New Employee Hires", ComplianceStatus.COMPLIANT),
            ("GRI 403-1", "OHS Management System", ComplianceStatus.PARTIAL),
            ("GRI 404-1", "Training Hours", ComplianceStatus.COMPLIANT),
            ("GRI 405-1", "Diversity in Governance", ComplianceStatus.PARTIAL),
            ("GRI 406-1", "Discrimination Incidents", ComplianceStatus.COMPLIANT),
            ("GRI 407-1", "Freedom of Association", ComplianceStatus.NOT_ASSESSED),
            ("GRI 408-1", "Child Labour Risk", ComplianceStatus.COMPLIANT),
            ("GRI 409-1", "Forced Labour", ComplianceStatus.COMPLIANT),
            ("GRI 414-1", "Social Screening of Suppliers", ComplianceStatus.PARTIAL),
            ("GRI 415-1", "Political Contributions", ComplianceStatus.COMPLIANT),
            ("GRI 416-1", "Customer Health & Safety", ComplianceStatus.NOT_ASSESSED),
            ("GRI 418-1", "Customer Privacy", ComplianceStatus.NON_COMPLIANT),
        ]
        iso_requirements = [
            ("ISO 14001 4.1", "Understanding the Organisation", ComplianceStatus.COMPLIANT),
            ("ISO 14001 4.2", "Needs of Interested Parties", ComplianceStatus.COMPLIANT),
            ("ISO 14001 4.3", "Scope of EMS", ComplianceStatus.COMPLIANT),
            ("ISO 14001 5.1", "Leadership and Commitment", ComplianceStatus.PARTIAL),
            ("ISO 14001 5.2", "Environmental Policy", ComplianceStatus.COMPLIANT),
            ("ISO 14001 5.3", "Roles and Responsibilities", ComplianceStatus.COMPLIANT),
            ("ISO 14001 6.1", "Environmental Aspects", ComplianceStatus.PARTIAL),
            ("ISO 14001 6.2", "Environmental Objectives", ComplianceStatus.PARTIAL),
            ("ISO 14001 7.2", "Competence", ComplianceStatus.COMPLIANT),
            ("ISO 14001 7.4", "Communication", ComplianceStatus.PARTIAL),
            ("ISO 14001 7.5", "Documented Information", ComplianceStatus.COMPLIANT),
            ("ISO 14001 8.1", "Operational Planning and Control", ComplianceStatus.PARTIAL),
            ("ISO 14001 8.2", "Emergency Preparedness", ComplianceStatus.NON_COMPLIANT),
            ("ISO 14001 9.1", "Monitoring and Measurement", ComplianceStatus.COMPLIANT),
            ("ISO 14001 9.2", "Internal Audit", ComplianceStatus.PARTIAL),
            ("ISO 14001 9.3", "Management Review", ComplianceStatus.COMPLIANT),
            ("ISO 14001 10.1", "Nonconformity and Corrective Action", ComplianceStatus.PARTIAL),
            ("ISO 14001 10.2", "Continual Improvement", ComplianceStatus.PARTIAL),
            ("ISO 14001 A.6", "Life Cycle Perspective", ComplianceStatus.NOT_ASSESSED),
            ("ISO 14001 A.9", "Emergency Situations", ComplianceStatus.NON_COMPLIANT),
        ]
        req_count = 0
        for code, title, status in gri_requirements:
            r = ComplianceRequirement(
                framework_id=gri.id, code=code, title=title, status=status,
                evidence=f"Evidence for {code}" if status == ComplianceStatus.COMPLIANT else None,
                review_date=now() + timedelta(days=90),
            )
            session.add(r)
            req_count += 1
        for code, title, status in iso_requirements:
            r = ComplianceRequirement(
                framework_id=iso.id, code=code, title=title, status=status,
                review_date=now() + timedelta(days=60),
            )
            session.add(r)
            req_count += 1
        session.flush()
        print(f"   ✓ Compliance: GRI Standards + ISO 14001 ({req_count} requirements)")

        # ── Agent Run Logs ─────────────────────────────────────────────────
        import json as _json
        for i in range(3):
            log = AgentRunLog(
                status="success",
                started_at=past(i * 1 + 1),
                finished_at=past(i * 1 + 1) + timedelta(minutes=3),
                orgs_processed=1,
                metrics_scored=14,
                requirements_flagged=2,
                risks_escalated=1,
                details=_json.dumps({
                    "org_id": org.id,
                    "L1_ESRC_Risk_Assessment": {
                        "module": "ESGRC",
                        "risk_score": 6.5,
                        "confidence": 0.72,
                        "trend": "Improving",
                        "low_performing_submodules": ["GRC10101", "ERM10101"],
                        "recommendations": ["Review GRC framework coverage", "Complete ERM baseline"],
                    }
                }),
            )
            session.add(log)
        session.flush()
        print("   ✓ Agent Run Logs: 3 successful runs")

        # ── Pipeline Definitions ───────────────────────────────────────────
        esgrc_pipeline = PipelineDefinition(
            org_id=org.id,
            name="ESGRC Module Pipeline",
            pipeline_type=PipelineTypeEnum.ESGRC_MODULE,
            is_active=True,
            config_json={
                "required_input_files": [
                    f"org/{org.id}/reference/input_metric_values_esgrc.csv",
                    f"org/{org.id}/reference/esgrc_performance_json_file.json",
                ],
                # Analyst uploads the metric DATA; the performance JSON (module
                # hierarchy / names / weights) is backend-provided config.
                "user_input_files": [
                    f"org/{org.id}/reference/input_metric_values_esgrc.csv",
                ],
                "reference_files": [
                    f"org/{org.id}/reference/esgrc_performance_json_file.json",
                ],
                "steps": 7,
            },
        )
        apex_pipeline = PipelineDefinition(
            org_id=org.id,
            name="Apex Enterprise Pipeline",
            pipeline_type=PipelineTypeEnum.APEX_ENTERPRISE,
            is_active=True,
            config_json={
                "required_input_files": [
                    f"org/{org.id}/reference/module_mapping.csv",
                    f"org/{org.id}/reference/module_matrix.csv",
                ],
                # Apex needs no analyst upload: its data comes from the ESGRC run's
                # handoff (data_for_risk_assessment_*.csv), and the mapping/matrix
                # are backend-provided config.
                "user_input_files": [],
                "reference_files": [
                    f"org/{org.id}/reference/module_mapping.csv",
                    f"org/{org.id}/reference/module_matrix.csv",
                ],
                "steps": 8,
            },
        )
        # Every non-ESGRC module shares the same definition shape: the analyst
        # uploads the metric CSV, the backend owns the performance JSON. Built by
        # looping the module registry (pipeline/modules.py), so a new module needs
        # no edit here. ESGRC keeps its own block above because it is also the
        # anchor for the seeded demo run below.
        module_pipelines = {}
        for spec in MODULES:
            if spec.token == "esgrc":
                continue
            metrics_csv = f"org/{org.id}/reference/{spec.metrics_csv}"
            perf_json = f"org/{org.id}/reference/{spec.perf_json}"
            module_pipelines[spec.token] = PipelineDefinition(
                org_id=org.id,
                name=f"{spec.label} Module Pipeline",
                pipeline_type=PipelineTypeEnum(spec.pipeline_type),
                is_active=True,
                config_json={
                    "required_input_files": [metrics_csv, perf_json],
                    "user_input_files": [metrics_csv],
                    "reference_files": [perf_json],
                    "steps": spec.steps,
                },
            )
        customer_pipeline = module_pipelines["customer"]

        session.add_all([esgrc_pipeline, apex_pipeline, *module_pipelines.values()])
        session.flush()

        # ── Completed ESGRC Run ────────────────────────────────────────────
        esgrc_run = PipelineRun(
            pipeline_id=esgrc_pipeline.id,
            org_id=org.id,
            triggered_by=admin_user.id,
            status=RunStatusEnum.COMPLETED,
            is_current=True,
            progress_pct=100,
            confidence_score=0.74,
            started_at=past(1),
            completed_at=past(1) + timedelta(minutes=18),
        )
        session.add(esgrc_run)
        session.flush()

        esgrc_step_names = [
            "Data Preparation 1", "Data Preparation 2",
            "Correlation CHAID FT Analysis", "SPC RPN Analysis",
            "Regression Analysis", "Combine Reports",
            "AI Risk Assessment (Claude)",
        ]
        esgrc_steps = []
        for i, name in enumerate(esgrc_step_names, 1):
            step = PipelineStepResult(
                run_id=esgrc_run.id,
                step_number=i,
                step_name=name,
                status=StepStatusEnum.COMPLETED,
                started_at=past(1) + timedelta(minutes=(i-1)*2),
                completed_at=past(1) + timedelta(minutes=i*2),
                duration_ms=120000 + i * 5000,
                output_files_json=[f"org/{org.id}/runs/{esgrc_run.id}/step_{i}/output.txt"],
            )
            session.add(step)
            esgrc_steps.append(step)
        session.flush()

        esgrc_llm = PipelineLLMOutput(
            run_id=esgrc_run.id,
            step_result_id=esgrc_steps[-1].id,
            analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
            prompt_hash="demo_esgrc_hash_001",
            model_used="claude-haiku-4-5",
            input_tokens=8420,
            output_tokens=1240,
            response_text="""## Module Risk Assessment

**Overall Risk Score:** 6/10
**Confidence:** Medium - 4 periods of data, 2 SPC violations detected
**Trend:** Improving - scores increased 12% from Q1 to Q4 2024

### Top Risk Areas

**Risk 1: GRC Framework Coverage Gap**
- Description: GRC10101 scored 72/100 in Q4 - below the 90% target benchmark.
- Evidence: Correlation analysis shows GRC coverage strongly predicts overall ESG score (r=0.78).
- Recommended Action: Commission a GRC gap analysis within 30 days. Target 80% coverage by Q2 2025.

**Risk 2: GHG Indirect Emissions Non-Compliance**
- Description: Scope 2 emissions tracking (GRI 305-2) is non-compliant per latest assessment.
- Evidence: No measurement methodology documented for Q3-Q4 periods.
- Recommended Action: Engage emissions consultant for Scope 2 calculation. Target Q1 2025 completion.

**Risk 3: ERM Baseline Incomplete**
- Description: ERM10101 at 70/100 - enterprise risk management framework partially implemented.
- Evidence: Regression model shows ERM completeness drives 34% of overall risk score variance.
- Recommended Action: Complete ERM baseline assessment within 60 days.

### Low-Performing Sub-Modules
- GRC10101: 72/100 (target: 90)
- ERM10101: 70/100 (target: 85)

### Summary
The ESGRC module shows positive trajectory across all 14 sub-modules with particularly strong improvement in Environmental and Safety metrics. Priority actions focus on GRC framework completion and Scope 2 emissions measurement to address the two non-compliant GRI requirements.
""",
            output_file_r2_path=f"org/{org.id}/runs/{esgrc_run.id}/step_7/recommendation_module_unified.txt",
        )
        session.add(esgrc_llm)

        # ── Completed Customer Run ─────────────────────────────────────────
        # The figures below are NOT invented: they are the real outputs of the
        # Customer analytics scripts run against Customer/reference_data/ on
        # 31 Jul 2026 (module average 59.48, the low-performing sub-modules and
        # metrics, 0 SPC signals across 348 metrics, CHAID all-Moderate, and the
        # regression overall risk 0.3797 / Scenario_10 0.960). Only the Claude
        # prose wrapping them is written for the demo.
        customer_run = PipelineRun(
            pipeline_id=customer_pipeline.id,
            org_id=org.id,
            triggered_by=admin_user.id,
            status=RunStatusEnum.COMPLETED,
            is_current=True,
            progress_pct=100,
            confidence_score=0.68,
            started_at=past(1) + timedelta(hours=3),
            completed_at=past(1) + timedelta(hours=3, minutes=26),
        )
        session.add(customer_run)
        session.flush()

        # Must match STEP_NAMES in pipeline/tasks/customer_chain.py, so a seeded
        # run and a real run render identically in the timeline.
        customer_step_names = [
            "Customer Data Preparation 1 (low-performing)",
            "Customer Data Preparation 2 (hierarchy split + handoff)",
            "Customer Correlation / CHAID Analysis",
            "Customer SPC / RPN Analysis",
            "Customer Regression Analysis",
            "Customer Combine Reports",
            "Customer AI Module Assessment (Claude)",
        ]
        customer_steps = []
        for i, name in enumerate(customer_step_names, 1):
            step = PipelineStepResult(
                run_id=customer_run.id,
                step_number=i,
                step_name=name,
                status=StepStatusEnum.COMPLETED,
                started_at=past(1) + timedelta(hours=3, minutes=(i-1)*3),
                completed_at=past(1) + timedelta(hours=3, minutes=i*3),
                # Customer is 348 metrics vs ESGRC's 84, so its steps are slower.
                duration_ms=180000 + i * 9000,
                output_files_json=[f"org/{org.id}/runs/{customer_run.id}/step_{i}/output.txt"],
            )
            session.add(step)
            customer_steps.append(step)
        session.flush()

        customer_llm = PipelineLLMOutput(
            run_id=customer_run.id,
            step_result_id=customer_steps[-1].id,
            analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
            prompt_hash="demo_customer_hash_001",
            model_used="claude-haiku-4-5",
            input_tokens=14680,
            output_tokens=1310,
            response_text="""## Module Risk Assessment

**Overall Risk Score:** 5/10
**Confidence:** Medium - 348 metrics scored, but SPC found no control violations
**Trend:** Flat - module average CUST_001 at 59.48 across all 19 sub-modules

### Top Risk Areas

**Risk 1: Customer Communication Management is the weakest sub-module**
- Description: CCM10000 scored 50.53, the lowest of all 19 sub-modules and 9 points below the module average.
- Evidence: Its two worst metrics are CCM10104 (Net Promoter Score) at 21 and CCM10110 (Escalation Rate) at 21.
- Recommended Action: Review communication channel coverage and escalation routing within 30 days.

**Risk 2: Customer Insight and Intelligence under-performing**
- Description: CII10000 at 50.95, driven by CII10108 (Predictive Analytics Accuracy) scoring 20.
- Evidence: Predictive analytics accuracy is the joint-lowest metric in the entire module.
- Recommended Action: Audit the underlying model inputs before relying on CII outputs for targeting.

**Risk 3: Interaction handling and relationship metrics cluster low**
- Description: ITM10000 (52.79) and CRM10000 (53.63) both sit well below average.
- Evidence: ITM10102 (Average Handling Time) and CRM10104 (Net Promoter Score) both scored 20, the module floor.
- Recommended Action: Treat AHT and NPS as a single remediation workstream - they share root causes in first-contact resolution.

### Low-Performing Sub-Modules
- CCM10000: 50.53
- CII10000: 50.95
- ITM10000: 52.79
- CSR10000: 52.93
- CRM10000: 53.63

### Statistical Notes
- SPC: 0 out-of-control signals across all 348 metrics; RPN is a uniform 35, so the FMEA inputs are not currently discriminating between metrics.
- CHAID: all 348 metrics segmented as Moderate risk - no Critical or High segment emerged.
- Regression: overall risk 0.3797. The highest scenario (Scenario_10, 0.960) is driven by CRM10103, CFS10101 and ITM10111.

### Summary
The Customer module is stable but uniformly mediocre: no metric is in statistical alarm, yet the module average of 59.48 leaves little headroom. Priority is the communication and insight sub-modules, where NPS and predictive-analytics accuracy are at the module floor. The absence of SPC signals combined with a flat RPN suggests the control-chart inputs need review before they can drive prioritisation.
""",
            output_file_r2_path=f"org/{org.id}/runs/{customer_run.id}/step_7/recommendation_module_unified.txt",
        )
        session.add(customer_llm)

        # ── Completed Apex Run ─────────────────────────────────────────────
        apex_run_obj = PipelineRun(
            pipeline_id=apex_pipeline.id,
            org_id=org.id,
            triggered_by=admin_user.id,
            status=RunStatusEnum.COMPLETED,
            is_current=True,
            progress_pct=100,
            confidence_score=0.81,
            started_at=past(2),
            completed_at=past(2) + timedelta(minutes=35),
        )
        session.add(apex_run_obj)
        session.flush()

        # FIX: steps 5 and 7 were swapped versus APEX_STEP_NAMES in
        # pipeline/tasks/apex_chord.py. Per that file (and the requirements
        # doc): step 5 combines the GENERAL RISK reports and feeds step 6
        # (General Risk Claude call); step 7 combines the STATISTICAL/SPC-RPN
        # reports and feeds step 8 (SPC/RPN Claude call). A seeded demo run
        # must show the same step names a real run produces, or the two look
        # different in the Pipeline Monitor timeline.
        apex_step_names = [
            "All Module Low Performance Analysis",
            "Correlation CHAID L0 Analysis",
            "SPC RPN L0 Analysis",
            "Regression L0 Analysis",
            "Combine General Risk Reports",
            "AI General Risk Assessment (Claude)",
            "Combine Statistical Reports",
            "AI SPC RPN Assessment (Claude)",
        ]
        apex_steps = []
        for i, name in enumerate(apex_step_names, 1):
            step = PipelineStepResult(
                run_id=apex_run_obj.id,
                step_number=i,
                step_name=name,
                status=StepStatusEnum.COMPLETED,
                started_at=past(2) + timedelta(minutes=(i-1)*4),
                completed_at=past(2) + timedelta(minutes=i*4),
                duration_ms=240000 + i * 8000,
                output_files_json=[f"org/{org.id}/runs/{apex_run_obj.id}/step_{i}/output.txt"],
            )
            session.add(step)
            apex_steps.append(step)
        session.flush()

        apex_llm_general = PipelineLLMOutput(
            run_id=apex_run_obj.id,
            step_result_id=apex_steps[5].id,
            analysis_type=AnalysisTypeEnum.GENERAL_RISK,
            prompt_hash="demo_apex_general_001",
            model_used="claude-sonnet-5",
            input_tokens=24600,
            output_tokens=2180,
            response_text="""## Enterprise Risk Assessment - Apex Analysis

**Enterprise Risk Posture:** 7/10
**Assessment Date:** 2024-Q4
**Modules Analysed:** 12 (all active modules)

### Cross-Module Risk Patterns

**Pattern 1: Governance Framework Maturity Gap**
- Affected Modules: GRC, ERM, AUD, POL, REG
- Risk Category: Operational / Compliance
- Enterprise Impact: Regulatory exposure estimated CAD $2.1M if GRI non-compliance persists through 2025 filing deadline.
- Mitigation Strategy: Establish a cross-functional Governance Maturity Working Group. Monthly reporting to board risk committee.

**Pattern 2: Climate Transition Risk Concentration**
- Affected Modules: ESU, CGS, REG
- Risk Category: Strategic / Reputational
- Enterprise Impact: Potential exclusion from 3 ESG-screened investment indices if Scope 2 emissions not addressed.
- Mitigation Strategy: Accelerate net-zero roadmap development. Engage TCFD reporting consultant Q1 2025.

### Priority Enterprise Risks (Ranked)

1. **GHG Scope 2 Reporting Gap** - Likelihood: H × Impact: H = 20
   Non-compliant GRI 305-2. No Scope 2 methodology documented.

2. **Cybersecurity Framework Coverage** - Likelihood: M × Impact: H = 15
   CSU score 74/100. Three critical controls partially implemented.

3. **Supply Chain ESG Screening** - Likelihood: H × Impact: M = 12
   GRI 414-1 partial. 34% of tier-1 suppliers not ESG-screened.

### Strategic Recommendations
1. Establish a Chief Sustainability Officer role with board-level reporting authority.
2. Commission TCFD-aligned climate scenario analysis within 90 days.
3. Implement automated ESG data collection to eliminate manual reporting errors.
""",
            output_file_r2_path=f"org/{org.id}/runs/{apex_run_obj.id}/step_6/recommendation_general_risk.txt",
        )
        apex_llm_spc = PipelineLLMOutput(
            run_id=apex_run_obj.id,
            step_result_id=apex_steps[7].id,
            analysis_type=AnalysisTypeEnum.SPC_RPN,
            prompt_hash="demo_apex_spc_001",
            model_used="claude-sonnet-5",
            input_tokens=18200,
            output_tokens=1640,
            response_text="""## SPC-RPN Risk Assessment

### Statistical Process Control Findings

**Out-of-Control Processes:**
- GRC10101: Run of 8 consecutive points below centre line (Q2-Q4 2024) - systematic downward drift
- CSU10101: Western Electric Rule 2 violation - 2 of 3 points in Zone A (σ > 2) in Q3-Q4

**Processes Trending Toward Instability:**
- ERM10101: Upward trend (positive) - approaching upper control limit by Q2 2025 if growth continues (good trend)
- SSU10101: Downward trend (positive - lower is better) - on track but approaching target faster than model predicted

### Risk Priority Number Analysis

| Failure Mode | Module | Severity | Occurrence | Detection | RPN | Action Required |
|---|---|---|---|---|---|---|
| Scope 2 data not collected | ESU | 9 | 7 | 8 | 504 | Immediate |
| GRC controls undocumented | GRC | 8 | 6 | 6 | 288 | 30 days |
| Cybersecurity patching gap | CSU | 8 | 4 | 5 | 160 | 60 days |
| Supply chain screening gap | SSU | 6 | 5 | 5 | 150 | 90 days |
| Audit findings backlog | AUD | 5 | 4 | 3 | 60 | 90 days |

### Critical Corrective Actions (Ranked by RPN)

1. **Scope 2 Emissions Data Collection** - RPN: 504 - Due: 30 days
   - Root Cause: No energy procurement tracking system integrated with ESG platform
   - Corrective Action: Deploy automated meter data integration with ESG platform
   - Verification: Monthly Scope 2 data present in system by end of Q1 2025

2. **GRC Controls Documentation** - RPN: 288 - Due: 60 days
   - Root Cause: GRC framework adopted but control library not fully documented
   - Corrective Action: Complete control documentation sprint (2 weeks)
   - Verification: 100% of GRC controls have documented owner and evidence

### Process Stability Summary
Overall enterprise process stability is moderate (7 of 14 processes within control limits). Two processes show SPC violations requiring immediate corrective action. Five processes show positive improvement trends indicating the Q1-Q4 2024 ESG programme is having measurable effect.
""",
            output_file_r2_path=f"org/{org.id}/runs/{apex_run_obj.id}/step_8/recommendation_spc_rpn.txt",
        )
        session.add_all([apex_llm_general, apex_llm_spc])
        session.commit()

        # The pipeline block had no progress line, so a seed run looked like it
        # stopped after the agent logs. Report what it actually created.
        print(f"   ✓ Pipelines: {len(MODULES) + 1} definitions "
              f"({', '.join(m.label for m in MODULES)}, Apex)")
        print("   ✓ Pipeline Runs: 3 completed (7 + 7 + 8 steps, 4 Claude outputs)")

        elapsed = (datetime.now() - t0).total_seconds()
        print(f"\n✅ Demo seed complete in {elapsed:.1f}s")
        print(f"\n   Login credentials:")
        print(f"   admin@demo.com    / Demo1234!  (Admin role)")
        print(f"   analyst@demo.com  / Demo1234!  (Analyst role)")
        print(f"   viewer@demo.com   / Demo1234!  (Viewer role)")
        print(f"\n   Organisation slug: vigilant-lens-demo")


if __name__ == "__main__":
    run()
