"""
pipeline/test/test_script_runner.py
Unit tests for ScriptRunner.

Tests:
  - subprocess execution path
  - glob resolves dated filenames
  - stable name used for upload
  - missing output raises ScriptOutputMissingError
  - demo mode creates placeholder files
  - unknown script raises KeyError
  - subprocess non-zero exit raises ScriptExecutionError
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_runner.db")


MINIMAL_REGISTRY = {
    "scripts": {
        "clean_script": {
            "execution_mode": "subprocess",
            "command": "python clean_script.py",
            "script_filename": "clean_script.py",
            "can_import": False,
            "input_files": ["input.csv"],
            "output_files": ["output.txt"],
            "output_file_patterns": {},
        },
        "dated_script": {
            "execution_mode": "subprocess",
            "command": "python dated_script.py",
            "script_filename": "dated_script.py",
            "can_import": False,
            "input_files": ["input.csv"],
            "output_files": ["spc_summary_L0.txt"],
            "output_file_patterns": {
                "spc_summary_L0.txt": "spc_summary_L0_*.txt",
            },
        },
        "multi_output": {
            "execution_mode": "subprocess",
            "command": "python multi.py",
            "script_filename": "multi.py",
            "can_import": False,
            "input_files": ["input.csv"],
            "output_files": ["report.txt", "data.csv"],
            "output_file_patterns": {},
        },
    }
}


@pytest.fixture
def registry_file(tmp_path):
    """Write minimal registry to a temp file and return its path."""
    path = tmp_path / "scripts_registry.json"
    path.write_text(json.dumps(MINIMAL_REGISTRY))
    return str(path)


@pytest.fixture
def work_dir(tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    return str(d)


class TestScriptRunnerSubprocess:

    def test_subprocess_success_returns_output_dict(self, registry_file, work_dir):
        """Successful subprocess run returns {filename: path} dict."""
        from pipeline.tasks.script_runner import ScriptRunner

        runner = ScriptRunner(registry_path=registry_file)

        def fake_run(script_name, input_paths, output_dir):
            # Simulate script creating output.txt
            out = os.path.join(output_dir, "output.txt")
            with open(out, "w") as f:
                f.write("script output")
            return {"output.txt": out}

        with patch.object(runner, "_run_via_subprocess"):
            # After "subprocess" runs, manually create the output file
            def fake_collect(script_name, config, output_dir):
                out = os.path.join(output_dir, "output.txt")
                with open(out, "w") as f:
                    f.write("script output")
                return {"output.txt": out}

            with patch.object(runner, "_collect_outputs", side_effect=fake_collect):
                result = runner.run("clean_script", {"input.csv": "/tmp/x.csv"}, work_dir)

        assert "output.txt" in result
        assert os.path.exists(result["output.txt"])

    def test_nonzero_exit_raises_script_execution_error(self, registry_file, work_dir, tmp_path):
        """Script exiting with non-zero code raises ScriptExecutionError."""
        from pipeline.tasks.script_runner import ScriptRunner, ScriptExecutionError

        # Write a real script that exits non-zero
        script_path = tmp_path / "clean_script.py"
        script_path.write_text("import sys; sys.exit(1)\n")

        runner = ScriptRunner(registry_path=registry_file)

        # Override SCRIPTS_DIR to point at our tmp script
        with patch("pipeline.tasks.script_runner.SCRIPTS_DIR", str(tmp_path)):
            with pytest.raises(ScriptExecutionError) as exc_info:
                runner._run_via_subprocess("clean_script", MINIMAL_REGISTRY["scripts"]["clean_script"], work_dir)

        assert exc_info.value.returncode == 1

    def test_missing_output_raises_script_output_missing_error(self, registry_file, work_dir):
        """Script that doesn't produce expected output raises ScriptOutputMissingError."""
        from pipeline.tasks.script_runner import ScriptRunner, ScriptOutputMissingError

        runner = ScriptRunner(registry_path=registry_file)

        # Don't create any output files
        with patch.object(runner, "_run_via_subprocess"):
            with pytest.raises(ScriptOutputMissingError) as exc_info:
                runner.run("clean_script", {}, work_dir)

        assert "output.txt" in exc_info.value.missing_files

    def test_unknown_script_raises_key_error(self, registry_file, work_dir):
        """Script name not in registry raises KeyError."""
        from pipeline.tasks.script_runner import ScriptRunner

        runner = ScriptRunner(registry_path=registry_file)
        with pytest.raises(KeyError, match="not_a_real_script"):
            runner.run("not_a_real_script", {}, work_dir)


class TestGlobDateFilenames:

    def test_glob_discovers_dated_file_and_renames_to_stable(self, registry_file, work_dir):
        """
        Script produces spc_summary_L0_2026-06-20.txt
        ScriptRunner must glob it and rename to spc_summary_L0.txt
        """
        from pipeline.tasks.script_runner import ScriptRunner

        runner = ScriptRunner(registry_path=registry_file)

        # Create the dated file in work_dir
        dated_file = os.path.join(work_dir, "spc_summary_L0_2026-06-20.txt")
        with open(dated_file, "w") as f:
            f.write("spc content for 2026-06-20")

        with patch.object(runner, "_run_via_subprocess"):
            result = runner.run("dated_script", {}, work_dir)

        assert "spc_summary_L0.txt" in result
        stable_path = result["spc_summary_L0.txt"]
        assert os.path.exists(stable_path)
        assert os.path.basename(stable_path) == "spc_summary_L0.txt"
        # Original dated file should be gone (renamed)
        assert not os.path.exists(dated_file)

    def test_glob_picks_newest_when_multiple_dated_files(self, registry_file, work_dir):
        """When multiple dated files match, the newest (by mtime) is picked."""
        import time
        from pipeline.tasks.script_runner import ScriptRunner

        runner = ScriptRunner(registry_path=registry_file)

        older = os.path.join(work_dir, "spc_summary_L0_2026-06-18.txt")
        newer = os.path.join(work_dir, "spc_summary_L0_2026-06-20.txt")

        with open(older, "w") as f:
            f.write("older content")
        time.sleep(0.05)  # ensure different mtime
        with open(newer, "w") as f:
            f.write("newer content - this should win")

        with patch.object(runner, "_run_via_subprocess"):
            result = runner.run("dated_script", {}, work_dir)

        stable_path = result["spc_summary_L0.txt"]
        with open(stable_path) as f:
            content = f.read()
        assert "newer content" in content

    def test_glob_no_match_raises_script_output_missing(self, registry_file, work_dir):
        """No files matching the glob pattern → ScriptOutputMissingError."""
        from pipeline.tasks.script_runner import ScriptRunner, ScriptOutputMissingError

        runner = ScriptRunner(registry_path=registry_file)

        with patch.object(runner, "_run_via_subprocess"):
            with pytest.raises(ScriptOutputMissingError) as exc_info:
                runner.run("dated_script", {}, work_dir)

        assert "spc_summary_L0.txt" in exc_info.value.missing_files


class TestDemoMode:

    def test_demo_mode_creates_placeholder_files(self, registry_file, work_dir):
        """DEMO_MODE=true creates output files without running the script."""
        from pipeline.tasks.script_runner import ScriptRunner
        import pipeline.tasks.script_runner as sr_module

        runner = ScriptRunner(registry_path=registry_file)

        with patch.object(sr_module, "DEMO_MODE", True), \
             patch.object(sr_module, "DEMO_DELAY", 0):
            result = runner.run("clean_script", {}, work_dir)

        assert "output.txt" in result
        with open(result["output.txt"]) as f:
            content = f.read()
        assert "DEMO" in content

    def test_demo_mode_multi_output_creates_all_files(self, registry_file, work_dir):
        """DEMO_MODE creates all expected output files for multi-output scripts."""
        from pipeline.tasks.script_runner import ScriptRunner
        import pipeline.tasks.script_runner as sr_module

        runner = ScriptRunner(registry_path=registry_file)

        with patch.object(sr_module, "DEMO_MODE", True), \
             patch.object(sr_module, "DEMO_DELAY", 0):
            result = runner.run("multi_output", {}, work_dir)

        assert "report.txt" in result
        assert "data.csv" in result



class TestSubprocessEnvironmentIsolation:
    """
    The analytics scripts used to inherit the Celery worker's entire environment,
    including ANTHROPIC_API_KEY, CLOUDFLARE_R2_SECRET_KEY, SECRET_KEY and
    DATABASE_URL. They read exactly one variable (ANALYTICS_SEED) and are the
    least-reviewed code in the system, re-uploaded by an outside contributor.
    """

    SECRETS = {
        "ANTHROPIC_API_KEY": "sk-ant-should-not-leak",
        "CLOUDFLARE_R2_SECRET_KEY": "r2-secret-should-not-leak",
        "CLOUDFLARE_R2_ACCESS_KEY": "r2-access-should-not-leak",
        "SECRET_KEY": "jwt-signing-should-not-leak",
        "DATABASE_URL": "postgresql://user:password@host/db",
        "LANGFUSE_SECRET_KEY": "lf-should-not-leak",
    }

    def test_secrets_are_not_passed_to_scripts(self):
        from pipeline.tasks.script_runner import _build_script_env

        with patch.dict(os.environ, self.SECRETS, clear=False):
            env = _build_script_env()

        for name in self.SECRETS:
            assert name not in env, f"{name} leaked into the analytics subprocess env"

    def test_analytics_seed_is_passed_through(self):
        from pipeline.tasks.script_runner import _build_script_env

        with patch.dict(os.environ, {"ANALYTICS_SEED": "1234"}, clear=False):
            env = _build_script_env()

        assert env["ANALYTICS_SEED"] == "1234"

    def test_os_essentials_survive_so_the_child_can_start(self):
        from pipeline.tasks.script_runner import _build_script_env

        env = _build_script_env()
        # PATH must always survive; SYSTEMROOT only exists on Windows.
        assert "PATH" in env
        if os.name == "nt":
            assert "SYSTEMROOT" in {k.upper() for k in env}

    def test_headless_matplotlib_backend_is_forced(self):
        from pipeline.tasks.script_runner import _build_script_env

        env = _build_script_env()
        assert env["MPLBACKEND"] == "Agg"
        # setdefault, so an inherited value like "utf-8:surrogateescape" wins.
        assert env["PYTHONIOENCODING"].lower().startswith("utf-8")

    def test_passthrough_var_can_be_opted_in(self):
        from pipeline.tasks.script_runner import _build_script_env

        with patch.dict(
            os.environ,
            {"SCRIPT_ENV_PASSTHROUGH": "MY_CUSTOM_FLAG", "MY_CUSTOM_FLAG": "on"},
            clear=False,
        ):
            env = _build_script_env()

        assert env["MY_CUSTOM_FLAG"] == "on"

    def test_subprocess_run_is_actually_given_the_filtered_env(
        self, registry_file, work_dir, tmp_path
    ):
        """The allowlist is worthless if _run_via_subprocess forgets to pass it."""
        from pipeline.tasks.script_runner import ScriptRunner

        script_path = tmp_path / "clean_script.py"
        script_path.write_text("print('ok')\n")
        runner = ScriptRunner(registry_path=registry_file)

        completed = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch.dict(os.environ, self.SECRETS, clear=False):
            with patch("pipeline.tasks.script_runner.SCRIPTS_DIR", str(tmp_path)):
                with patch(
                    "pipeline.tasks.script_runner.subprocess.run", return_value=completed
                ) as mock_run:
                    runner._run_via_subprocess(
                        "clean_script",
                        MINIMAL_REGISTRY["scripts"]["clean_script"],
                        work_dir,
                    )

        passed_env = mock_run.call_args.kwargs.get("env")
        assert passed_env is not None, "subprocess.run was called without env="
        for name in self.SECRETS:
            assert name not in passed_env


class TestAuditScriptsFilenameResolution:
    """FIX: pipeline/scripts/audit_scripts.py assumed every script's file was
    literally named "{script_name}.py" (e.g. "data_prep_1.py"). The real
    analytics scripts are named like "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py"
    - scripts_registry.json's "script_filename" field (the same field
    ScriptRunner already reads) is the real source of truth. Before this fix,
    every entry in SCRIPTS_TO_AUDIT reported "Script not found", regardless of
    scripts_dir, because no file with the naive name exists anywhere in the repo.
    """

    def test_load_script_filenames_reads_real_filenames_from_registry(self, tmp_path):
        from pipeline.scripts import audit_scripts

        registry_path = tmp_path / "scripts_registry.json"
        registry_path.write_text(json.dumps({
            "scripts": {
                "data_prep_1": {"script_filename": "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py"},
                "SPC_RPN": {"script_filename": "x_bar_r_chart_fmea_esg_5_0.py"},
            }
        }))

        with patch.object(audit_scripts, "REGISTRY_PATH", str(registry_path)):
            mapping = audit_scripts._load_script_filenames()

        assert mapping["data_prep_1"] == "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py"
        assert mapping["SPC_RPN"] == "x_bar_r_chart_fmea_esg_5_0.py"

    def test_audit_finds_the_script_under_its_real_filename(self, tmp_path):
        """The actual bug: under the old '{script_name}.py' assumption this
        script would be reported "not found" even though it sits right there
        on disk, just under its real name."""
        from pipeline.scripts import audit_scripts

        registry_path = tmp_path / "scripts_registry.json"
        registry_path.write_text(json.dumps({
            "scripts": {
                "data_prep_1": {"script_filename": "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py"},
            }
        }))
        (tmp_path / "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py").write_text(
            "if __name__ == '__main__':\n    pass\n"
        )

        with (
            patch.object(audit_scripts, "REGISTRY_PATH", str(registry_path)),
            patch.object(audit_scripts, "SCRIPTS_TO_AUDIT", ["data_prep_1"]),
        ):
            findings = audit_scripts.audit_all_scripts(str(tmp_path))

        assert findings["data_prep_1"]["found"] is True

    def test_falls_back_to_naive_name_when_registry_unreadable(self, tmp_path):
        """No registry present must not crash - it degrades to the old
        "{script_name}.py" assumption rather than raising."""
        from pipeline.scripts import audit_scripts

        with patch.object(audit_scripts, "REGISTRY_PATH", str(tmp_path / "missing.json")):
            mapping = audit_scripts._load_script_filenames()

        assert mapping == {}
