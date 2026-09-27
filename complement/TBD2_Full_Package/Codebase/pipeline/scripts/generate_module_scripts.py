"""
pipeline/scripts/generate_module_scripts.py

Generate a new module's analytics scripts by retokenising an existing module's
copies. This replaces the hand-edit that produced Shared and BSPT.

WHY THIS EXISTS AS A SCRIPT AND NOT A ONE-OFF EDIT
--------------------------------------------------
The analytics scripts are authored upstream and are still being validated. Any
fix found upstream has to reach every generated module. If generation is a hand
edit, that is 5 scripts x N modules of manual re-application. If it is this
script, it is one command:

    python pipeline/scripts/generate_module_scripts.py --module enterprise

Source of truth is always OUR fixed copy, never the upstream repo, because ours
carry the corrections (the .iloc[0] ranking fix, the CHAID bin_features wiring,
the ANALYTICS_SEED seeding, the top-N report trim, and the removal of the Flask
app.run that blocks batch runs). Re-syncing from upstream silently reverts them.

WHY IT IS NOT A BLIND FIND/REPLACE
-----------------------------------
"shared" also occurs as an ordinary English word ("columns ... shared by the
.txt"), and comments carry module-specific FACTS ("Shared has 288 metrics") that
are wrong once copied. So substitution is anchored to token shapes only, and
known factual comments are rewritten from the target module's own JSON.

Every run prints a diff summary and refuses to write if a substitution produced
a line still containing the source token, which is the signal that a new context
appeared that these rules do not cover.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Source module to clone from. Shared is factory-built and carries every fix.
SOURCE = {
    "token": "shared",
    "code": "SHRD_001",
    "camel": "Shared",
    "dir": "Shared",
}

# Filename patterns, keyed by the source filename with the token spelled out.
SCRIPTS = {
    "M_G_Sub_M_split_{Camel}_1_0.py": "M_G_Sub_M_split_Shared_1_0.py",
    "AI_ready_Low_Performing_M_G_SM_{Camel}_3_0.py": "AI_ready_Low_Performing_M_G_SM_Shared_3_0.py",
    "Correlation_CHAID_FT_Analysis_{Camel}_8_0.py": "Correlation_CHAID_FT_Analysis_Shared_8_0.py",
    "x_bar_r_chart_fmea_{token}_5_0.py": "x_bar_r_chart_fmea_shared_5_0.py",
    "AI_ready_Mutiple_Regression_Model_implementation_{Camel}_4_0.py": "AI_ready_Mutiple_Regression_Model_implementation_Shared_4_0.py",
}


def substitutions(token: str, code: str, camel: str) -> list[tuple[str, str]]:
    """
    Anchored rules only. Each pattern requires a token-shaped neighbour (_ . ' " /
    or a word boundary inside an identifier), so the bare English word "shared"
    is never touched.

    Order matters: the module code goes first so SHRD_001 is never partially
    rewritten by a later rule.
    """
    return [
        # 1. Module code, exact.
        (re.escape(SOURCE["code"]), code),
        # 2. Filenames: shared_performance_json_file.json
        # No trailing \b: the next character is '_' which is a word character,
        # so \b would never match and the rule would silently do nothing. The
        # leftover-token guard below is what caught that.
        (r"\bshared_performance", f"{token}_performance"),
        # 3. Filenames: *_shared.csv / *_shared.txt / *_shared.pdf / *_shared.json
        (r"_shared(?=\.(csv|txt|pdf|json)\b)", f"_{token}"),
        # 4. Filenames with a date suffix: *_shared_{ANALYSIS_DATE}
        (r"_shared_(?=\{)", f"_{token}_"),
        # 5. input_metric_values_shared / module_values_shared / filtered_*_shared
        (r"_shared\b", f"_{token}"),
        # 6. CamelCase identifiers: Shared_Module_model_summary.txt
        (r"\bShared_", f"{camel}_"),
        # 7. Prose in headers we control: "End of Shared Module Risk Analysis"
        (r"\bShared Module\b", f"{camel} Module"),
        # 8. Quoted module name: 'Shared'
        (r"'Shared'", f"'{camel}'"),
        # 9. Referenced source filenames in comments
        (r"_Shared\.py", f"_{camel}.py"),
    ]


def load_module_facts(token: str) -> dict:
    """Read the target module's own JSON so copied factual comments are corrected."""
    path = REPO / "pipeline" / "llm" / "data" / f"{token}_performance_json_file.json"
    if not path.exists():
        path = REPO / "modules" / token.upper() / "reference_data" / f"{token}_performance_json_file.json"
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    metrics = sum(
        len(g.get("value") or [])
        for sm in doc.get("sub_modules", [])
        for g in sm.get("groups", [])
    )
    return {
        "module_id": doc.get("module_id"),
        "module_name": doc.get("module_name"),
        "metrics": metrics,
        "sub_modules": len(doc.get("sub_modules", [])),
    }


# Comments that state a fact about the SOURCE module and would be false once
# copied. Matched on the source text, rewritten from the target's own JSON.
FACTUAL_COMMENTS = [
    (
        re.compile(r"Shared has 288 metrics \(vs ESGRC"),
        lambda f, camel: f"{camel} has {f['metrics']} metrics (vs ESGRC",
    ),
]


def generate(token: str, code: str, camel: str, out_dir: Path, dry_run: bool) -> int:
    facts = load_module_facts(token)
    if facts["module_id"] != code:
        print(
            f"  WARNING: JSON module_id is {facts['module_id']!r} but --code is {code!r}."
            " Using --code; check which is right."
        )

    src_dir = REPO / "modules" / SOURCE["dir"] / "analytics_scripts"
    rules = substitutions(token, code, camel)
    out_dir.mkdir(parents=True, exist_ok=True)
    problems = 0

    for target_tpl, source_name in SCRIPTS.items():
        src = src_dir / source_name
        if not src.exists():
            print(f"  MISSING SOURCE: {src}")
            problems += 1
            continue

        text = src.read_text(encoding="utf-8")
        original = text
        for pattern, repl in rules:
            text = re.sub(pattern, repl, text)
        for pattern, fn in FACTUAL_COMMENTS:
            text = pattern.sub(lambda _m: fn(facts, camel), text)

        # Refuse to emit a file that still names the source module in a token
        # position. That means a context appeared these rules do not cover.
        leftovers = [
            (i, line)
            for i, line in enumerate(text.splitlines(), 1)
            if re.search(r"_shared\b|\bSHRD_001\b|\bShared_|shared_performance", line)
        ]
        if leftovers:
            print(f"  LEFTOVER SOURCE TOKEN in {target_tpl.format(Camel=camel, token=token)}:")
            for i, line in leftovers[:5]:
                print(f"      line {i}: {line.strip()[:90]}")
            problems += 1
            continue

        changed = sum(
            1 for a, b in zip(original.splitlines(), text.splitlines()) if a != b
        )
        target_name = target_tpl.format(Camel=camel, token=token)
        if dry_run:
            print(f"  would write {target_name:<62} ({changed} lines changed)")
        else:
            (out_dir / target_name).write_text(text, encoding="utf-8", newline="\n")
            print(f"  wrote {target_name:<62} ({changed} lines changed)")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", required=True, help="lowercase token, e.g. enterprise")
    ap.add_argument("--code", help="module id, e.g. ETPR_001 (default: read from JSON)")
    ap.add_argument("--camel", help="Name used inside filenames, e.g. Enterprise or ICTM")
    ap.add_argument("--dir", help="Module directory name (default: --camel)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = args.module.lower()
    facts = load_module_facts(token)
    code = args.code or facts["module_id"]
    camel = args.camel or token.capitalize()

    print(f"{token}: code={code} camel={camel} "
          f"metrics={facts['metrics']} sub_modules={facts['sub_modules']}")
    # Explicit, never inferred from the filesystem: Path.exists() is
    # case-insensitive on Windows, so probing for CAMEL.upper() happily matched
    # the CamelCase directory and wrote to a differently-cased path that git
    # would then see as a second directory on Linux.
    out_dir = REPO / "modules" / (args.dir or camel) / "analytics_scripts"

    problems = generate(token, code, camel, out_dir, args.dry_run)
    if problems:
        print(f"\n{problems} problem(s); nothing usable was produced for those files.")
        return 1
    print(f"\nOK -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
