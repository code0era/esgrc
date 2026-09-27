"""
pipeline/test/test_failure_modes.py

Deliberately break each part of the system and assert it fails LOUDLY.

This codebase's characteristic defect is not a crash, it is a plausible-looking
result. Every analytics bug found in August produced a complete report with wrong
content: CHAID binned everything to "Unknown", L0 weights silently defaulted to
1.0, low performers came from one arbitrary row, the enterprise report was
truncated by 79%, and seven modules were one step away from dying because a
registry key said "shared".

So these tests do not check that things work. They check that when things break,
somebody finds out.

Anything asserted here as "currently silent" is documented as such rather than
quietly accepted, so the gap is visible in the test output instead of only in a
report a client is reading.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.modules import MODULES

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "pipeline" / "llm" / "data"


# ── Reference data corruption ────────────────────────────────────────────────
# load_label_map() catches every exception PER FILE and continues, by design, so
# a packaging slip degrades to codes rather than 500-ing the report endpoint.
# The cost is that a single corrupt file silently removes that module's group and
# metric names, and the API still reports labeling_status "ok". Measured: one BOM
# on enterprise_performance_json_file.json removed 491 of 3,721 codes.
#
# The design is not being changed here; Shubham's frontend depends on that
# contract. Instead the corruption is caught at CI time, before it can ship.

@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_bundled_perf_json_parses_without_a_bom(spec):
    """A BOM makes json.load fail on character 0 and the module loses its names.

    This is not hypothetical: a PowerShell `Set-Content -Encoding utf8` edit
    introduced exactly this on 7 Aug.
    """
    path = DATA / spec.perf_json
    assert path.exists(), f"{spec.token}: {spec.perf_json} not bundled in pipeline/llm/data/"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), (
        f"{spec.token}: {spec.perf_json} has a UTF-8 BOM. labeling loads it with "
        f"open(path, encoding='utf-8'), so it will be skipped and this module's "
        f"group and metric names will silently disappear from every report."
    )
    json.loads(raw.decode("utf-8"))  # raises on any other malformation


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_every_module_actually_contributes_names_to_the_label_map(spec):
    """Proves the file was not merely present but was successfully consumed.

    A file that fails to parse is logged and skipped, so presence alone proves
    nothing. Asserting a real metric resolves is what catches a skipped file.
    """
    from pipeline.llm.labeling import load_label_map

    doc = json.loads((DATA / spec.perf_json).read_text(encoding="utf-8"))
    metric = next(
        (
            m
            for sm in doc.get("sub_modules", [])
            for g in sm.get("groups", [])
            for m in (g.get("value") or [])
        ),
        None,
    )
    if metric is None:
        pytest.skip(f"{spec.token}: JSON declares no metrics yet")

    mapping = load_label_map()
    code = metric["metric_id"]
    assert code in mapping, (
        f"{spec.token}: metric {code} is in its perf JSON but absent from the label "
        f"map, so that JSON was skipped at load time. Reports will show raw codes."
    )
    assert mapping[code].level == "metric"


def test_corrupt_perf_json_surfaces_unmapped_codes(tmp_path, monkeypatch):
    """Documents the actual degradation contract, so it cannot change unnoticed.

    Current behaviour, verified: a corrupt file yields labeling_status "ok" with
    the affected codes listed in unmapped_codes. It is NOT fully silent, but a
    caller checking only `status` sees success while the report shows raw codes.
    Nothing currently monitors unmapped_codes.
    """
    from pipeline.llm import labeling

    target = DATA / "enterprise_performance_json_file.json"
    if not target.exists():
        pytest.skip("enterprise perf JSON not bundled")

    doc = json.loads(target.read_text(encoding="utf-8"))
    code = doc["sub_modules"][0]["groups"][0]["value"][0]["metric_id"]
    text = f"The main driver is {code}."

    raw = target.read_bytes()
    try:
        target.write_bytes(b"\xef\xbb\xbf" + raw)
        labeling.load_label_map.cache_clear()
        result = labeling.label_output(text)

        assert code in result.unmapped_codes, (
            "a corrupt perf JSON must at minimum surface its codes as unmapped"
        )
        assert code in result.labeled_text, "must fall back to the raw code, not drop it"
        # Recorded, not endorsed: status stays "ok" even though names were lost.
        assert result.status == "ok", (
            "behaviour changed: status is no longer 'ok' on partial label loss. "
            "If that was deliberate, update this test and tell the frontend, which "
            "branches on status."
        )
    finally:
        target.write_bytes(raw)
        labeling.load_label_map.cache_clear()


# ── Script execution failures ────────────────────────────────────────────────

def test_script_exiting_nonzero_raises_rather_than_continuing(tmp_path):
    """A failing analytics script must stop the step, not leave a partial run."""
    from pipeline.tasks.script_runner import ScriptRunner, ScriptExecutionError

    script = tmp_path / "boom.py"
    script.write_text("import sys; sys.stderr.write('exploded'); sys.exit(3)\n")
    work = tmp_path / "work"
    work.mkdir()

    runner = ScriptRunner.__new__(ScriptRunner)
    cfg = {"script_filename": "boom.py", "execution_mode": "subprocess"}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("pipeline.tasks.script_runner.SCRIPTS_DIR", str(tmp_path))
        with pytest.raises(ScriptExecutionError) as exc:
            runner._run_via_subprocess("boom", cfg, str(work))
    assert exc.value.returncode == 3


def test_script_exiting_zero_but_writing_nothing_is_caught(tmp_path):
    """The dangerous case: success exit code, no output.

    Without this the chain would carry on to the next step with nothing to read,
    and the failure would surface somewhere unrelated.
    """
    from pipeline.tasks.script_runner import ScriptRunner, ScriptOutputMissingError

    work = tmp_path / "work"
    work.mkdir()
    runner = ScriptRunner.__new__(ScriptRunner)
    cfg = {"script_filename": "quiet.py", "output_files": ["expected_report.txt"]}

    with pytest.raises(ScriptOutputMissingError) as exc:
        runner._collect_outputs("quiet", cfg, str(work))
    assert "expected_report.txt" in str(exc.value)


def test_analytics_subprocess_cannot_see_platform_credentials():
    """Regression guard on the credential allowlist."""
    from pipeline.tasks.script_runner import _build_script_env

    secrets = {
        "ANTHROPIC_API_KEY": "sk-ant-leak",
        "CLOUDFLARE_R2_SECRET_KEY": "r2-leak",
        "SECRET_KEY": "jwt-leak",
        "DATABASE_URL": "postgresql://u:p@h/db",
    }
    with pytest.MonkeyPatch.context() as mp:
        for k, v in secrets.items():
            mp.setenv(k, v)
        env = _build_script_env()
    for name in secrets:
        assert name not in env, f"{name} reached the analytics subprocess"


# ── LLM payload guard ────────────────────────────────────────────────────────

def test_every_correlation_script_bounds_its_report():
    """The L0 roll-up shipped without the trim and reached 4.8x the hard limit.

    Any correlation script missing the bound can do the same, and the symptom is
    a complete-looking report that the model only partly read.
    """
    missing = []
    for path in REPO.glob("modules/*/analytics_scripts/*Correlation*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        if "write_top_correlations" not in src:
            missing.append(str(path.relative_to(REPO)))
    assert not missing, (
        "correlation scripts with no report-size bound:\n  " + "\n  ".join(missing)
    )


def test_guard_thresholds_are_below_the_model_limit():
    """A warn threshold above the hard limit would never fire."""
    from pipeline.llm.guard import DEFAULT_THRESHOLDS

    warn, hard = DEFAULT_THRESHOLDS
    assert warn < hard, f"warn threshold {warn} is not below the hard limit {hard}"
