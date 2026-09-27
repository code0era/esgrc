"""
pipeline/tasks/script_runner.py
ScriptRunner - executes analytics scripts via import or subprocess,
handles dated output filenames via glob, validates all expected outputs.

Dev C fills scripts_registry.json during C-01 audit.
ScriptRunner reads that file at runtime to decide import vs subprocess.
"""
import glob
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "scripts_registry.json"
)
SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", os.path.join(
    os.path.dirname(__file__), "..", "scripts"
))
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"
DEMO_DELAY = float(os.environ.get("DEMO_SCRIPT_DELAY", "2"))

# ── Subprocess environment allowlist ──────────────────────────────────────────
# subprocess.run() without env= hands the child the Celery worker's ENTIRE
# environment, which includes ANTHROPIC_API_KEY, CLOUDFLARE_R2_SECRET_KEY,
# SECRET_KEY and DATABASE_URL. The analytics scripts need none of those: a grep
# across all 25 of them finds exactly one variable they read, ANALYTICS_SEED.
# They are also the least-reviewed code in the system and are re-uploaded by an
# outside contributor, so they are precisely what should not hold credentials.
#
# The child now gets an explicit allowlist. Add a name to SCRIPT_ENV_PASSTHROUGH
# (comma-separated) if a script ever needs one, rather than reverting to
# inheritance.
_SCRIPT_ENV_ALLOWLIST = frozenset({
    # OS essentials. On Windows a child process fails to start without
    # SYSTEMROOT; PATH is needed for DLL and helper-binary resolution.
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "TMPDIR",
    # Locale and encoding. Without PYTHONIOENCODING the scripts raise
    # UnicodeEncodeError writing report text on a cp1252 Windows console.
    "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONIOENCODING",
    # matplotlib and fontconfig resolve their cache directory from HOME.
    "HOME", "USERPROFILE", "MPLCONFIGDIR", "MPLBACKEND",
    # The only variable the analytics scripts themselves read.
    "ANALYTICS_SEED",
})


def _build_script_env() -> Dict[str, str]:
    """Build the environment for an analytics subprocess from the allowlist."""
    extra = {
        name.strip().upper()
        for name in os.environ.get("SCRIPT_ENV_PASSTHROUGH", "").split(",")
        if name.strip()
    }
    allowed = _SCRIPT_ENV_ALLOWLIST | extra

    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}

    # The worker is headless, so force a non-interactive matplotlib backend
    # rather than letting it probe for a display. The SPC scripts import pyplot
    # at module level and would otherwise depend on whatever the image provides.
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env

# ── Module-level singleton - registry.json read ONCE per worker process ───────
# Celery tasks call get_runner() instead of ScriptRunner() to avoid re-reading
# the JSON file on every task invocation.
_runner_instance: Optional["ScriptRunner"] = None


def get_runner() -> "ScriptRunner":
    """Return the module-level ScriptRunner singleton."""
    global _runner_instance
    if _runner_instance is None:
        _runner_instance = ScriptRunner()
    return _runner_instance


class ScriptExecutionError(Exception):
    """Raised when a subprocess script exits with non-zero return code."""
    def __init__(self, script_name: str, returncode: int, stderr: str):
        self.script_name = script_name
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"Script '{script_name}' exited with code {returncode}.\nStderr: {stderr[:2000]}"
        )


class ScriptOutputMissingError(Exception):
    """Raised when expected output files are not found after script execution."""
    def __init__(self, script_name: str, missing_files: list):
        self.script_name = script_name
        self.missing_files = missing_files
        super().__init__(
            f"Script '{script_name}' completed but expected outputs are missing: {missing_files}"
        )


class ScriptRunner:
    """
    Executes analytics scripts and returns a dict of {stable_output_name: local_path}.

    Handles:
    - import vs subprocess (per scripts_registry.json)
    - dated output filenames via glob patterns
    - DEMO_MODE (returns fixture outputs without running scripts)
    """

    def __init__(self, registry_path: str = REGISTRY_PATH):
        self._registry = self._load_registry(registry_path)

    @staticmethod
    def _load_registry(path: str) -> dict:
        resolved = os.path.realpath(path)
        with open(resolved, "r") as f:
            data = json.load(f)
        return data.get("scripts", {})

    def run(
        self,
        script_name: str,
        input_paths: Dict[str, str],
        output_dir: str,
    ) -> Dict[str, str]:
        """
        Execute a script and return {stable_output_name: local_path}.

        Args:
            script_name:  Key in scripts_registry.json (e.g. "data_prep_1")
            input_paths:  {filename: local_absolute_path} for all inputs
            output_dir:   Directory where the script writes its outputs

        Returns:
            {stable_output_name: absolute_local_path}

        Raises:
            ScriptExecutionError: subprocess exited non-zero
            ScriptOutputMissingError: expected output file not produced
            KeyError: script_name not in registry
        """
        if script_name not in self._registry:
            raise KeyError(
                f"Script '{script_name}' not found in scripts_registry.json. "
                f"Available: {list(self._registry.keys())}"
            )

        config = self._registry[script_name]
        os.makedirs(output_dir, exist_ok=True)

        if DEMO_MODE:
            return self._demo_run(script_name, config, output_dir)

        # Copy input files to output_dir so scripts can reference them by filename.
        # Callers build src_path with a mix of os.path.join and plain "/" joins
        # (see _module_chain_factory.py), so on Windows the same file can have two
        # different-looking path strings - normalize before comparing, otherwise
        # this tries to shutil.copy2() a file onto itself and Windows rejects that
        # as "used by another process" (POSIX just silently permits it).
        for filename, src_path in input_paths.items():
            dst = os.path.join(output_dir, filename)
            if os.path.normcase(os.path.normpath(src_path)) != os.path.normcase(os.path.normpath(dst)) \
                    and os.path.exists(src_path):
                shutil.copy2(src_path, dst)

        execution_mode = config.get("execution_mode", "subprocess")

        if execution_mode == "import":
            self._run_via_import(script_name, config, output_dir, input_paths)
        else:
            self._run_via_subprocess(script_name, config, output_dir)

        return self._collect_outputs(script_name, config, output_dir)

    # ── Execution modes ───────────────────────────────────────────────────────

    def _run_via_subprocess(self, script_name: str, config: dict, output_dir: str) -> None:
        """Run script as a subprocess in output_dir."""
        script_path = os.path.join(SCRIPTS_DIR, os.path.basename(config["script_filename"]))

        if not os.path.exists(script_path):
            raise FileNotFoundError(
                f"Script file not found: {script_path}. "
                f"Check SCRIPTS_DIR env var (currently: {SCRIPTS_DIR})"
            )

        cmd = [sys.executable, script_path]
        logger.info("Running script: %s in %s", " ".join(cmd), output_dir)

        t0 = time.time()
        result = subprocess.run(
            cmd,
            cwd=output_dir,           # scripts find their inputs by filename in CWD
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("SCRIPT_TIMEOUT", "3600")),  # 1 hour default
            env=_build_script_env(),  # allowlist, NOT the worker's full environment
        )
        elapsed = time.time() - t0

        logger.info(
            "Script '%s' finished in %.1fs - exit code %d",
            script_name, elapsed, result.returncode,
        )

        if result.returncode != 0:
            logger.error("Script stderr:\n%s", result.stderr[:3000])
            raise ScriptExecutionError(script_name, result.returncode, result.stderr)

        if result.stdout:
            logger.debug("Script stdout:\n%s", result.stdout[:1000])

    def _run_via_import(
        self,
        script_name: str,
        config: dict,
        output_dir: str,
        input_paths: Dict[str, str],
    ) -> None:
        """
        Run script via direct Python import.
        Only used for scripts proven clean in C-01 audit (no global side effects).
        Calls the entry_function defined in the registry config.
        """
        entry_function = config.get("entry_function")
        if not entry_function:
            raise ValueError(
                f"Script '{script_name}' has execution_mode=import but no "
                f"entry_function defined in scripts_registry.json"
            )

        script_path = os.path.join(SCRIPTS_DIR, os.path.basename(config["script_filename"]))
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        module = importlib.util.module_from_spec(spec)

        # Run in output_dir so relative file paths in the script resolve correctly
        original_dir = os.getcwd()
        try:
            os.chdir(output_dir)
            spec.loader.exec_module(module)
            fn = getattr(module, entry_function)
            fn(**{k: v for k, v in input_paths.items()})
        finally:
            os.chdir(original_dir)

        # Remove from sys.modules to prevent state leaking to the next run
        sys.modules.pop(script_name, None)

    # ── Output collection ─────────────────────────────────────────────────────

    def _collect_outputs(
        self,
        script_name: str,
        config: dict,
        output_dir: str,
    ) -> Dict[str, str]:
        """
        Discover output files, resolve any dated glob patterns, validate all present.
        Returns {stable_name: absolute_path}.
        """
        expected_outputs: list = config.get("output_files", [])
        # Files that are collected+uploaded when present but must NOT fail the
        # step if the script didn't produce them (e.g. user-download-only PDFs -
        # Claude never consumes them, so a chart-rendering hiccup shouldn't sink
        # an otherwise-good analytical run). Absent key ⇒ empty ⇒ old behaviour.
        optional_outputs: list = config.get("optional_output_files", [])
        glob_patterns: dict = config.get("output_file_patterns", {})
        found: Dict[str, str] = {}
        missing: list = []

        def _resolve(stable_name: str) -> str | None:
            """Return the stable path for an output, moving a dated glob match into
            place, or None if the script didn't produce it."""
            pattern = glob_patterns.get(stable_name)
            if pattern:
                matches = glob.glob(os.path.join(output_dir, pattern))
                if not matches:
                    return None
                newest = max(matches, key=os.path.getmtime)  # newest by mtime
                stable_path = os.path.join(output_dir, stable_name)
                shutil.move(newest, stable_path)
                logger.info(
                    "Glob resolved '%s' → '%s' (stable: '%s')",
                    pattern, os.path.basename(newest), stable_name,
                )
                return stable_path
            expected_path = os.path.join(output_dir, stable_name)
            return expected_path if os.path.exists(expected_path) else None

        for stable_name in expected_outputs:
            path = _resolve(stable_name)
            if path:
                found[stable_name] = path
            else:
                missing.append(stable_name)

        for stable_name in optional_outputs:
            path = _resolve(stable_name)
            if path:
                found[stable_name] = path
            else:
                logger.warning(
                    "Optional output '%s' not produced by '%s' - skipping "
                    "(user-download-only deliverable).",
                    stable_name, script_name,
                )

        if missing:
            raise ScriptOutputMissingError(script_name, missing)

        return found

    # ── Demo mode ─────────────────────────────────────────────────────────────

    def _demo_run(self, script_name: str, config: dict, output_dir: str) -> Dict[str, str]:
        """
        DEMO_MODE: create placeholder output files instantly.
        Never ship DEMO_MODE=true to the real client.
        """
        logger.info("DEMO_MODE: simulating script '%s'", script_name)
        time.sleep(DEMO_DELAY)

        found = {}
        for stable_name in config.get("output_files", []):
            output_path = os.path.join(output_dir, stable_name)
            if stable_name.endswith(".txt"):
                content = (
                    f"=== DEMO OUTPUT: {script_name} ===\n"
                    f"This is a placeholder report generated in DEMO_MODE.\n"
                    f"Output file: {stable_name}\n"
                )
            elif stable_name.endswith(".csv"):
                content = "metric_code,value,period\nESU10102,42.0,2024-Q4\n"
            else:
                content = f"DEMO: {script_name} output\n"

            with open(output_path, "w") as f:
                f.write(content)

            found[stable_name] = output_path

        return found
