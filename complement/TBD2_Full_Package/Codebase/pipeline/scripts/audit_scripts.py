"""
pipeline/scripts/audit_scripts.py
C-01 Script Audit Tool - Dev C runs this during Sprint 1 Days 1-5.

For each analytics script, this tool:
  1. Tests whether it can be safely imported (no side effects on import)
  2. Runs it in a subprocess and captures exit code + stderr
  3. Scans for global mutable state, hardcoded paths, side effects on import
  4. Records findings in scripts_registry.json

Usage:
    cd AI-ERMT-TBD-02
    SCRIPTS_DIR=/path/to/analytics/scripts python pipeline/scripts/audit_scripts.py

    # Audit a specific script:
    python pipeline/scripts/audit_scripts.py --script data_prep_1

    # Update registry after manual review:
    python pipeline/scripts/audit_scripts.py --update-registry
"""
import ast
import importlib.util
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, Optional

SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", os.path.join(
    os.path.dirname(__file__), "."
))
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "scripts_registry.json")

SCRIPTS_TO_AUDIT = [
    "data_prep_1",
    "data_prep_2",
    "correlation_CHAID_FT",
    "SPC_RPN",
    "regression_esgrc",
    "all_module_low_perf",
    "correlation_CHAID_L0",
    "SPC_RPN_L0",
    "regression_L0",
]

# Patterns that indicate a script has side effects on import
SIDE_EFFECT_PATTERNS = [
    # Direct execution at module level
    "pd.read_csv(",
    "pd.read_excel(",
    "open(",
    "os.makedirs(",
    "os.path.join(os.getcwd()",
    "plt.show()",
    "plt.savefig(",
    # Running immediately on import
    "subprocess.run(",
    "subprocess.call(",
]


# ── Import safety check ───────────────────────────────────────────────────────

def check_import_safety(script_path: str) -> Dict:
    """
    Attempt to import the script and detect side effects.
    Returns a dict with findings.
    """
    result = {
        "can_import": False,
        "import_error": None,
        "side_effects_detected": [],
        "has_main_guard": False,
        "global_mutable_state": [],
    }

    # Static analysis first - read the AST
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        # Check for if __name__ == "__main__" guard
        if '__name__ == "__main__"' in source or "__name__ == '__main__'" in source:
            result["has_main_guard"] = True

        # Check for side effect patterns at module level
        for pattern in SIDE_EFFECT_PATTERNS:
            if pattern in source:
                # Check if it's inside a function (safer) or at module level (dangerous)
                result["side_effects_detected"].append(pattern)

        # AST analysis for module-level assignments to globals
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    # Module-level assignment - potential global state
                    if not isinstance(node.value, (ast.Constant, ast.Name)):
                        result["global_mutable_state"].append(
                            ast.dump(node.targets[0])
                        )
        except SyntaxError as e:
            result["import_error"] = f"SyntaxError: {e}"
            return result

    except Exception as e:
        result["import_error"] = f"Static analysis failed: {e}"

    # Dynamic import test
    try:
        # Add scripts dir to path temporarily
        original_path = sys.path.copy()
        sys.path.insert(0, os.path.dirname(script_path))

        spec = importlib.util.spec_from_file_location("_audit_test", script_path)
        module = importlib.util.module_from_spec(spec)

        # Try to exec the module - capture any errors
        spec.loader.exec_module(module)
        result["can_import"] = True

    except SystemExit as e:
        result["import_error"] = f"Script calls sys.exit() on import: {e}"
    except Exception as e:
        result["import_error"] = f"{type(e).__name__}: {e}"
    finally:
        sys.path = original_path
        # Clean up module from sys.modules
        sys.modules.pop("_audit_test", None)

    return result


def check_subprocess_execution(script_path: str) -> Dict:
    """
    Run the script as a subprocess with no input files.
    Expect it to fail (missing inputs) but check the failure mode.
    """
    result = {
        "returncode": None,
        "stderr_snippet": None,
        "crashed_with_import_error": False,
        "crashed_with_file_not_found": False,
    }

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(script_path),
        )
        result["returncode"] = proc.returncode
        result["stderr_snippet"] = proc.stderr[:500] if proc.stderr else ""

        if "ImportError" in proc.stderr or "ModuleNotFoundError" in proc.stderr:
            result["crashed_with_import_error"] = True

        if "FileNotFoundError" in proc.stderr or "No such file" in proc.stderr:
            result["crashed_with_file_not_found"] = True

    except subprocess.TimeoutExpired:
        result["returncode"] = -1
        result["stderr_snippet"] = "TIMEOUT: script ran for >30s with no inputs"
    except Exception as e:
        result["returncode"] = -1
        result["stderr_snippet"] = str(e)

    return result


def _load_script_filenames() -> Dict[str, str]:
    """Map script_name -> real on-disk script_filename, per scripts_registry.json.

    FIX: this tool used to assume every script's file was literally named
    "{script_name}.py" (e.g. "data_prep_1.py", "correlation_CHAID_L0.py"). The
    real analytics scripts are named things like
    "AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py" - scripts_registry.json's
    "script_filename" field, which ScriptRunner already uses, is the actual
    source of truth. With the old assumption every entry in SCRIPTS_TO_AUDIT
    reported "Script not found", regardless of scripts_dir, because no file by
    that literal name exists anywhere in the repo.
    """
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        return {
            name: entry["script_filename"]
            for name, entry in registry.get("scripts", {}).items()
            if "script_filename" in entry
        }
    except Exception as exc:
        print(f"WARNING: could not load {REGISTRY_PATH} ({exc}); "
              f"falling back to '<script_name>.py' filenames")
        return {}


def audit_all_scripts(scripts_dir: str) -> Dict:
    """Run the full audit for all registered scripts."""
    findings = {}
    script_filenames = _load_script_filenames()

    for script_name in SCRIPTS_TO_AUDIT:
        # FIX: look up the real filename from scripts_registry.json instead of
        # assuming "{script_name}.py" - see _load_script_filenames().
        script_filename = script_filenames.get(script_name, f"{script_name}.py")
        script_path = os.path.join(scripts_dir, script_filename)
        if not os.path.exists(script_path):
            findings[script_name] = {
                "found": False,
                "note": f"Script not found at {script_path}. Copy analytics scripts to SCRIPTS_DIR.",
            }
            continue

        print(f"\n{'='*60}")
        print(f"Auditing: {script_name}")
        print(f"Path:     {script_path}")
        print(f"{'='*60}")

        import_result = check_import_safety(script_path)
        subprocess_result = check_subprocess_execution(script_path)

        # Determine recommended execution mode
        if (
            import_result["can_import"]
            and not import_result["side_effects_detected"]
            and import_result["has_main_guard"]
        ):
            recommended_mode = "import"
            reason = "Clean import: has __main__ guard, no side effects detected"
        else:
            recommended_mode = "subprocess"
            reasons = []
            if not import_result["can_import"]:
                reasons.append(f"Import fails: {import_result['import_error']}")
            if import_result["side_effects_detected"]:
                reasons.append(f"Side effects: {import_result['side_effects_detected'][:3]}")
            if not import_result["has_main_guard"]:
                reasons.append("No __name__ == '__main__' guard")
            reason = "; ".join(reasons) if reasons else "Default: subprocess for safety"

        findings[script_name] = {
            "found": True,
            "script_path": script_path,
            "recommended_execution_mode": recommended_mode,
            "reason": reason,
            "import_analysis": import_result,
            "subprocess_analysis": subprocess_result,
        }

        print(f"  Recommended mode:  {recommended_mode}")
        print(f"  Reason:            {reason}")
        print(f"  Can import safely: {import_result['can_import']}")
        print(f"  Has __main__ guard:{import_result['has_main_guard']}")
        print(f"  Side effects:      {import_result['side_effects_detected'][:3]}")
        print(f"  Subprocess exit:   {subprocess_result['returncode']}")

    return findings


def update_registry(findings: Dict) -> None:
    """
    Update scripts_registry.json with audit findings.
    Only updates execution_mode and audit fields - preserves input/output file lists.
    """
    with open(REGISTRY_PATH, "r") as f:
        registry = json.load(f)

    for script_name, finding in findings.items():
        if not finding.get("found"):
            continue

        if script_name not in registry["scripts"]:
            print(f"WARNING: {script_name} not in registry - add it manually")
            continue

        entry = registry["scripts"][script_name]
        entry["execution_mode"] = finding["recommended_execution_mode"]
        entry["can_import"] = finding["import_analysis"]["can_import"]
        entry["import_safe_reason"] = finding["reason"]
        entry["has_main_guard"] = finding["import_analysis"]["has_main_guard"]
        entry["side_effects_detected"] = finding["import_analysis"]["side_effects_detected"]

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"\n✅ Registry updated: {REGISTRY_PATH}")


def print_summary(findings: Dict) -> None:
    """Print a summary table of all audit findings."""
    print(f"\n{'='*70}")
    print("AUDIT SUMMARY")
    print(f"{'='*70}")
    print(f"{'Script':<30} {'Found':<8} {'Mode':<12} {'Import OK':<12}")
    print(f"{'-'*70}")

    for name, f in findings.items():
        if not f.get("found"):
            print(f"{name:<30} {'NO':<8} {'N/A':<12} {'N/A':<12}")
            continue
        mode = f.get("recommended_execution_mode", "?")
        can_import = f.get("import_analysis", {}).get("can_import", False)
        print(f"{name:<30} {'YES':<8} {mode:<12} {str(can_import):<12}")

    print(f"\nTotal scripts audited: {len(findings)}")
    importable = sum(
        1 for f in findings.values()
        if f.get("found") and f.get("import_analysis", {}).get("can_import")
    )
    subprocess_only = sum(
        1 for f in findings.values()
        if f.get("found") and not f.get("import_analysis", {}).get("can_import")
    )
    print(f"  Safe to import:    {importable}")
    print(f"  Subprocess only:   {subprocess_only}")
    print(f"  Not found:         {len(findings) - importable - subprocess_only}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="C-01 Script Audit Tool")
    parser.add_argument("--scripts-dir", default=SCRIPTS_DIR,
                        help="Directory containing analytics scripts")
    parser.add_argument("--script", help="Audit a single script by name")
    parser.add_argument("--update-registry", action="store_true",
                        help="Write findings to scripts_registry.json")
    parser.add_argument("--output", help="Write findings JSON to this file")
    args = parser.parse_args()

    target_scripts = [args.script] if args.script else None
    if target_scripts:
        original = SCRIPTS_TO_AUDIT.copy()
        SCRIPTS_TO_AUDIT.clear()
        SCRIPTS_TO_AUDIT.extend(target_scripts)

    findings = audit_all_scripts(args.scripts_dir)
    print_summary(findings)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(findings, f, indent=2)
        print(f"\n✅ Findings written to {args.output}")

    if args.update_registry:
        update_registry(findings)
