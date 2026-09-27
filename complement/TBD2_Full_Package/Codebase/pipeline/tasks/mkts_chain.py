"""
pipeline/tasks/mkts_chain.py

Market and Sales module pipeline. Built from pipeline/tasks/_module_chain_factory.py using
the ModuleSpec in pipeline/modules.py, so this file carries no step logic at all -
it exists to give the module a stable import path and its module-scoped names.

Analytics scripts live in MKTS/analytics_scripts/ and are GENERATED from the
Shared copies by pipeline/scripts/generate_module_scripts.py rather than hand
edited, so an upstream analytics fix reaches this module with one command. See
that directory's README for the corrections applied to the upstream data. They
are registered in pipeline/scripts/scripts_registry.json under the mkts_* keys.

Shape: 7 steps, identical to ESGRC. Step 2 writes the Apex handoff, so Apex picks
Market and Sales up with no Apex-side change.
"""
from pipeline.modules import get_module
from pipeline.tasks._module_chain_factory import build_module_chain

SPEC = get_module("mkts")
_ns = build_module_chain(SPEC)

MODULE = _ns["MODULE"]
STEP_NAMES = _ns["STEP_NAMES"]
STEP_TASKS = _ns["STEP_TASKS"]
step1 = _ns["step1"]
step2 = _ns["step2"]
step3 = _ns["step3"]
step4 = _ns["step4"]
step5 = _ns["step5"]
step6 = _ns["step6"]
step7_claude = _ns["step7_claude"]
chord_error_handler = _ns["chord_error_handler"]
build_chain = _ns["build_chain"]

# Module-scoped public names, kept as the stable per-module API.
MKTS_STEP_TASKS = STEP_TASKS
build_mkts_chain = build_chain
mkts_step7_claude = step7_claude
