"""Build every Celery canvas the router can dispatch.

Nothing else in the suite does this. The "e2e" tests call step functions in
sequence and hand-write the orchestration outcome, so build_apex_pipeline,
build_esgrc_chain and the factory's build_chain were never executed by a test at
all - the one part of the pipeline most likely to break against a real broker.

That matters specifically because the codebase documents (esgrc_chain.py, from a
live-broker incident) that a chord whose header group contains a chain raises
"Cannot add link to group" when chained after a task, and build_apex_pipeline's
tail chord has exactly that shape: group(chain(5,6), chain(7,8)).

Composition, not dispatch, is what these assert: the `|` operator and chord
construction are where that error surfaces, and they need no broker. Task ids are
checked too, because emergency_stop revokes by the deterministic
"{run_id}_step{n}" ids and silently no-ops if they drift.
"""
import pytest
from celery.canvas import Signature

from pipeline.modules import MODULES
from pipeline.routers.pipeline_router import _module_chain_builder
from pipeline.tasks.apex_chord import build_apex_pipeline

RUN_ID = "11111111-2222-3333-4444-555555555555"
ORG_ID = "1"


def _task_ids(sig) -> set:
    """Every task_id anywhere in a canvas, walked recursively."""
    found = set()

    def walk(node):
        if node is None:
            return
        opts = getattr(node, "options", None) or {}
        if opts.get("task_id"):
            found.add(opts["task_id"])
        for attr in ("tasks", "body", "header"):
            child = getattr(node, attr, None)
            if child is None and isinstance(node, dict):
                child = node.get(attr)
            if child is None:
                continue
            if isinstance(child, (list, tuple)):
                for c in child:
                    walk(c)
            else:
                walk(child)

    walk(sig)
    return found


# ── Module chains ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_module_chain_composes_exactly_as_the_router_dispatches_it(spec):
    """build_chain(...) | step7 - the composition _enqueue_pipeline performs."""
    builder = _module_chain_builder(spec.pipeline_type)
    assert builder is not None, f"registry has no chain builder for {spec.token}"
    build_fn, step7_task = builder

    chain = build_fn(RUN_ID, ORG_ID, {})
    full_chain = chain | step7_task.si(RUN_ID, ORG_ID, {}).set(
        task_id=f"{RUN_ID}_step7"
    )

    assert isinstance(full_chain, Signature)


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_module_chain_sets_revocable_step_task_ids(spec):
    """emergency_stop revokes '{run_id}_step{n}'; those ids must really be set."""
    build_fn, step7_task = _module_chain_builder(spec.pipeline_type)
    full_chain = build_fn(RUN_ID, ORG_ID, {}) | step7_task.si(
        RUN_ID, ORG_ID, {}
    ).set(task_id=f"{RUN_ID}_step7")

    ids = _task_ids(full_chain)
    assert f"{RUN_ID}_step7" in ids
    missing = [n for n in range(1, spec.steps + 1) if f"{RUN_ID}_step{n}" not in ids]
    assert not missing, (
        f"{spec.token}: steps {missing} carry no deterministic task_id, so "
        "emergency_stop cannot revoke them"
    )


def test_every_module_builds_a_distinct_canvas():
    """Guards against a copy-paste that points two modules at one chain."""
    reprs = {}
    for spec in MODULES:
        build_fn, _ = _module_chain_builder(spec.pipeline_type)
        reprs[spec.token] = repr(build_fn(RUN_ID, ORG_ID, {}))
    assert len(set(reprs.values())) == len(reprs), (
        f"two modules produced an identical canvas: {reprs.keys()}"
    )


# ── Apex ──────────────────────────────────────────────────────────────────────

def test_apex_nested_chord_composes():
    """The shape the code comments flag as broker-hostile: chord over chains."""
    pipeline = build_apex_pipeline(RUN_ID, ORG_ID, {})
    assert isinstance(pipeline, Signature)


def test_apex_sets_revocable_step_task_ids():
    ids = _task_ids(build_apex_pipeline(RUN_ID, ORG_ID, {}))
    missing = [n for n in range(1, 9) if f"{RUN_ID}_step{n}" not in ids]
    assert not missing, (
        f"apex steps {missing} carry no deterministic task_id, so emergency_stop "
        "cannot revoke them"
    )


def test_apex_and_module_canvases_are_not_the_same_shape():
    apex = repr(build_apex_pipeline(RUN_ID, ORG_ID, {}))
    build_fn, _ = _module_chain_builder(MODULES[0].pipeline_type)
    assert apex != repr(build_fn(RUN_ID, ORG_ID, {}))


def test_overrides_are_accepted_by_every_builder():
    """Overrides flow from the trigger endpoint; a builder that ignores the
    kwarg entirely would only fail at dispatch time in production."""
    overrides = {"skip_llm": True}
    build_apex_pipeline(RUN_ID, ORG_ID, overrides)
    for spec in MODULES:
        build_fn, _ = _module_chain_builder(spec.pipeline_type)
        build_fn(RUN_ID, ORG_ID, overrides)
