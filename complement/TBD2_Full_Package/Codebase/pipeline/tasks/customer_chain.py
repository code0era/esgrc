"""
pipeline/tasks/customer_chain.py

Customer module pipeline. Built from pipeline/tasks/_module_chain_factory.py using
the ModuleSpec in pipeline/modules.py, so this file carries no step logic at all -
it exists to give the module a stable import path and its module-scoped names.

Analytics scripts live in Customer/analytics_scripts/ (see that dir's README for the deltas
applied to Praveen's Repo-01 upload) and are registered in
pipeline/scripts/scripts_registry.json under the customer_* keys.

Shape: 7 steps, identical to ESGRC. Step 2 writes the Apex handoff, so Apex picks
Customer up with no Apex-side change.
"""
from pipeline.modules import get_module
from pipeline.tasks._module_chain_factory import build_module_chain

SPEC = get_module("customer")
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

# Module-scoped public names. pipeline_router resolves these through the registry
# now, but they are kept as the stable per-module API and are what the tests import.
CUSTOMER_STEP_TASKS = STEP_TASKS
build_customer_chain = build_chain
customer_step7_claude = step7_claude
