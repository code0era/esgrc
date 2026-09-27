"""
pipeline/modules.py

Single source of truth for which business modules exist and what is
module-specific about each one.

Before this file, adding a module meant hand-editing 12 places (the pipeline-type
enum, SSE step counts, the router's builder map and its single-step elif chain,
celery imports, auth module scoping, a Dockerfile COPY line, labeling's perf-JSON
tuple, five registry keys, the frontend step labels and its PipelineType union)
plus copying a ~365-line chain file of which only ~24 lines actually differed.
Measured on 2026-08-04 across ESGRC, Customer, Shared and Business Partner.

Now: add one ``ModuleSpec`` below, drop the module's analytics scripts and perf
JSON in place, and the loops that consume this registry pick it up.

WHAT THIS DOES NOT COVER (genuinely cannot be data-driven):
  - ``PipelineTypeEnum`` in models.py. Python enum members are class attributes
    and SQLAlchemy resolves them statically; generating them would break static
    analysis and the SAEnum values_callable contract. Kept literal, with
    test_modules_registry.py asserting the enum and this registry never diverge.
  - The PostgreSQL enum type. New values need ``ALTER TYPE ... ADD VALUE``, which
    is DDL, so each new module still ships an alembic migration.
  - The frontend ``PipelineType`` union, which is compile-time TypeScript.
  - The Dockerfile COPY lines. Docker's build context cannot iterate a Python list.

Everything else in the list above is now derived from ``MODULES``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class ModuleSpec:
    """One business module. ``token`` is the identity; everything else follows."""

    token: str            # routing/file token: "shared". Matches APEX_MODULE_NAMES,
                          # the scripts_registry key prefix, and every output filename.
    label: str            # display name: "Business Partner". Used in step names and UI.
    pipeline_type: str    # PipelineTypeEnum value: "BSPT_MODULE".
    steps: int = 7        # module chains are 7 steps; Apex is the 8-step odd one out.

    # False only for ESGRC, whose chain predates the template and is hand-written
    # (569 lines vs the template's 366, 570 differing lines). It is the canonical
    # reference implementation and the backend is extend-only, so it is described
    # here for the wiring loops but its chain is NOT factory-built.
    factory_built: bool = True

    @property
    def chain_module(self) -> str:
        return f"pipeline.tasks.{self.token}_chain"

    @property
    def perf_json(self) -> str:
        return f"{self.token}_performance_json_file.json"

    @property
    def metrics_csv(self) -> str:
        return f"input_metric_values_{self.token}.csv"

    @property
    def handoff_csv(self) -> str:
        return f"data_for_risk_assessment_{self.token}.csv"

    def script_key(self, step: str) -> str:
        """scripts_registry.json key, e.g. ("data_prep_1") -> "shared_data_prep_1"."""
        return f"{self.token}_{step}"


# ── The registry ─────────────────────────────────────────────────────────────
# Order is display order. Adding a module here is step 1 of 4; see the module
# docstring for the three things that still need a manual edit.

MODULES: Tuple[ModuleSpec, ...] = (
    ModuleSpec("esgrc",      "ESGRC",            "ESGRC_MODULE",      factory_built=False),
    ModuleSpec("customer",   "Customer",         "CUSTOMER_MODULE"),
    ModuleSpec("shared",     "Shared",           "SHARED_MODULE"),
    ModuleSpec("bspt",       "Business Partner", "BSPT_MODULE"),
    # Added 2026-08-06 once Praveen supplied input_metric_values_*.csv +
    # *_performance_json_file.json for each. Their analytics scripts are
    # generated from Shared by pipeline/scripts/generate_module_scripts.py, so
    # an upstream fix reaches all of them with one command.
    ModuleSpec("enterprise", "Enterprise",       "ENTERPRISE_MODULE"),
    ModuleSpec("ictm",       "IT Processes",     "ICTM_MODULE"),
    ModuleSpec("product",    "Product",          "PRODUCT_MODULE"),
    ModuleSpec("resource",   "Resource",         "RESOURCE_MODULE"),
    ModuleSpec("service",    "Service",          "SERVICE_MODULE"),
    # Added 2026-08-07. Both needed a correction from the analytics owner first:
    # brand's module_id was "EBM" (Praveen replaced it with BRDM_001 to match the
    # 4-alpha + underscore + 3-numeric convention), and mkts shipped as
    # Input_metric_values_mkts.csv, which fails on case-sensitive filesystems.
    ModuleSpec("brand",      "Brand Management", "BRAND_MODULE"),
    ModuleSpec("mkts",       "Market and Sales", "MKTS_MODULE"),
    # Added 2026-08-22. Data (input_metric_values_integration.csv +
    # integration_performance_json_file.json) supplied by Praveen via Repo-01.
    # Analytics scripts generated from the Shared template, not hand-vendored
    # from his upload - see modules/integration/analytics_scripts/README.md.
    ModuleSpec("integration", "Integration",     "INTEGRATION_MODULE"),
)

# Apex is not a module: it consumes the modules' handoffs and has its own 8-step
# chord. It appears here only where the two must be listed together (SSE step
# counts, auth scoping), never in the module loops.
APEX_PIPELINE_TYPE = "APEX_ENTERPRISE"
APEX_STEPS = 8


# ── Accessors ────────────────────────────────────────────────────────────────

_BY_TOKEN: Dict[str, ModuleSpec] = {m.token: m for m in MODULES}
_BY_PIPELINE_TYPE: Dict[str, ModuleSpec] = {m.pipeline_type: m for m in MODULES}


def get_module(token: str) -> ModuleSpec:
    return _BY_TOKEN[token]


def module_for_pipeline_type(pipeline_type: str) -> ModuleSpec | None:
    """None for APEX_ENTERPRISE or any non-module type - callers branch on that."""
    return _BY_PIPELINE_TYPE.get(pipeline_type)


def module_tokens() -> Tuple[str, ...]:
    return tuple(m.token for m in MODULES)


def factory_built_modules() -> Tuple[ModuleSpec, ...]:
    return tuple(m for m in MODULES if m.factory_built)


def perf_json_filenames() -> Tuple[str, ...]:
    """Feeds labeling._PERF_JSONS - one bundled perf JSON per module."""
    return tuple(m.perf_json for m in MODULES)


def chain_module_paths() -> Tuple[str, ...]:
    """Feeds celery_app's imports list, so a new module's tasks register."""
    return tuple(m.chain_module for m in MODULES)


def step_counts() -> Dict[str, int]:
    """Feeds sse.PIPELINE_STEP_COUNTS - modules plus Apex."""
    counts = {m.pipeline_type: m.steps for m in MODULES}
    counts[APEX_PIPELINE_TYPE] = APEX_STEPS
    return counts


def module_scope_map() -> Dict[str, set]:
    """Feeds auth.MODULE_PIPELINE_TYPES - per-module login scoping, plus apex."""
    scope: Dict[str, set] = {m.token: {m.pipeline_type} for m in MODULES}
    scope["apex"] = {APEX_PIPELINE_TYPE}
    return scope
