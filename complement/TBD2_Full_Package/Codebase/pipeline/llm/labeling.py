"""
pipeline/llm/labeling.py

Contextual-labeling layer for served LLM reports.

Design (locked - see docs/analytics/DRIFT_TEST_RESULTS.md, docs/analytics/CONTEXTUAL_LABELING_PROPOSAL.md):
Claude reasons on internal CODES (e.g. ``ESU10102``), which the drift test proved
is the most grounded representation - supplying business names in the prompt makes
the model fabricate causal *mechanisms*. So names are applied AFTER the LLM step,
deterministically, at display/serve time, with a validation gate that falls back to
the code-centric text if substitution ever corrupts the report.

This module is pure/stateless: it loads a static, product-level code->name map
(bundled under ``data/``) and substitutes names into report text. It never touches
the stored ``response_text`` (codes stay the source of truth); it only produces the
labelled *view* served to the frontend.

Sources of truth (bundled copies of backend config, not per-client data):
  - ``module_mapping.csv``                  - Apex modules + sub-modules (all 12).
  - ``esgrc_performance_json_file.json``    - ESGRC sub-modules / groups / metrics.
  - ``customer_performance_json_file.json`` - Customer sub-modules / groups / metrics.
  - ``shared_performance_json_file.json``   - Shared sub-modules / groups / metrics.
  - ``bspt_performance_json_file.json``     - Business Partner sub-modules / groups / metrics.

Add a module's perf JSON to ``_PERF_JSONS`` as it comes online; until then its
metric-level codes pass through unlabelled (reported as ``unmapped_codes``).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

from pipeline.modules import perf_json_filenames

logger = logging.getLogger(__name__)

# Bundled data dir (overridable for tests / future per-env config).
_DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
# One bundled perf JSON per module, derived from the module registry
# (pipeline/modules.py) so a new module's names resolve as soon as its JSON is
# dropped into data/. A missing file is logged and skipped, not fatal.
_PERF_JSONS = perf_json_filenames()
_MODULE_MAPPING = "module_mapping.csv"

# Code token shapes:
#   - ESGRC granular:  3 letters + 5 digits, e.g. ESU10102, GRC10101 (allow 2-4/4-6 for safety)
#   - Apex module id:  3-4 letters + '_' + 3 digits, e.g. ESRC_001, PRCY_001
#
# The module-id branch tolerates a BACKSLASH before the underscore. Claude writes
# module ids as ``BSPT\_001`` in markdown (escaping ``_`` so it does not start an
# italic run), and without the ``\\?`` those ids matched nothing at all: they were
# neither substituted NOR reported in ``unmapped_codes``, so a report came back
# ``status="ok"`` with ``unmapped=0`` while raw codes were still visible in the
# served text. Observed on a real Apex run 2026-08-04 ("Modules Analysed: 3
# (BSPT\_001, SHRD\_001, ESRC\_001)" - all three left unlabelled). The granular
# branch has no underscore and was never affected.
#
# Anything matched here must go through _canonical_code() before being looked up
# in the label map, since the map is keyed on the unescaped form.
CODE_RE = re.compile(r"\b(?:[A-Z]{2,4}\d{4,6}|[A-Z]{3,4}\\?_\d{3})\b")


def _canonical_code(token: str) -> str:
    """Map a matched code token to its label-map key (drops markdown escaping)."""
    return token.replace("\\", "")

# Number tokens used by the numeric-integrity gate. Business names must never
# contain digits, so stripping codes leaves data numbers comparable between the
# code text and the labelled text. Re-check this when a new module's perf JSON is
# added - test_no_business_name_contains_a_digit pins it.
_NUM_RE = re.compile(r"\d[\d.,]*")

# Ordinal prefix some perf JSONs put on group names ("1. Partner Recruitment").
# It is display sequencing, not part of the name, and it is NOT harmless here: a
# digit inside a business name breaks the numeric-integrity gate above, because
# substituting the code injects a number the code text never had, so gate B fails
# and the whole labelled report is discarded in favour of raw codes. Shared (96
# groups) and Business Partner (124 groups) prefix every single group name this
# way; ESGRC and Customer prefix none. Stripped at load so both styles resolve.
_ORDINAL_PREFIX_RE = re.compile(r"^\d+[.)]\s+")


def _clean_name(raw: str) -> str:
    """Normalise a business name from a perf JSON (see _ORDINAL_PREFIX_RE)."""
    return _ORDINAL_PREFIX_RE.sub("", raw.strip())


@dataclass(frozen=True)
class LabelEntry:
    name: str
    level: str  # "module" | "sub_module" | "group" | "metric"


@dataclass
class LabelingResult:
    """Outcome of labelling one report body."""
    labeled_text: str
    labels: List[Dict[str, str]] = field(default_factory=list)   # [{code,name,level}] in order of appearance
    unmapped_codes: List[str] = field(default_factory=list)      # code-like tokens with no known name
    status: str = "skipped"                                      # "ok" | "failed" | "skipped"
    issues: List[str] = field(default_factory=list)


def _data_dir() -> Path:
    override = os.getenv("LABELING_DATA_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR


@lru_cache(maxsize=1)
def load_label_map() -> Dict[str, LabelEntry]:
    """
    Build the flat ``{code: LabelEntry}`` resolver from the bundled reference files.

    ESGRC codes (139: 14 sub-modules / 41 groups / 84 metrics) come from the perf
    JSON; the 12 Apex modules + their sub-modules come from the mapping CSV. The two
    ID namespaces do not overlap; where a code appears in both, the perf JSON (the
    authoritative ESGRC source) wins because it is applied last.

    Cached for the process lifetime - the data is static, read-only config. Returns
    an empty map (never raises) if the files are missing, so a packaging slip
    degrades to serving codes rather than 500-ing the report endpoint.
    """
    data_dir = _data_dir()
    mapping: Dict[str, LabelEntry] = {}

    # 1) Apex modules + sub-modules from module_mapping.csv
    csv_path = data_dir / _MODULE_MAPPING
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sm_id = (row.get("Sub_Module_ID") or "").strip()
                sm_name = (row.get("Sub_Module_Name") or "").strip()
                mod_id = (row.get("Module_ID") or "").strip()
                mod_name = (row.get("Module_Name") or "").strip()
                if mod_id and mod_name:
                    mapping[mod_id] = LabelEntry(mod_name, "module")
                if sm_id and sm_name:
                    mapping[sm_id] = LabelEntry(sm_name, "sub_module")
    except FileNotFoundError:
        logger.warning("labeling: %s not found; Apex module names unavailable", csv_path)
    except Exception:  # pragma: no cover - defensive
        logger.exception("labeling: failed to parse %s", csv_path)

    # 2) Per-module granular sub-modules / groups / metrics from each perf JSON
    # (authoritative). A missing file is logged and skipped, so adding a module
    # here before its JSON ships degrades to codes rather than breaking the map.
    for perf_json in _PERF_JSONS:
        json_path = data_dir / perf_json
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mod_id = (data.get("module_id") or "").strip()
            mod_name = (data.get("module_name") or "").strip()
            if mod_id and mod_name:
                mapping[mod_id] = LabelEntry(_clean_name(mod_name), "module")
            for sub in data.get("sub_modules", []):
                sid, sname = sub.get("sub_module_id"), sub.get("sub_module_name")
                if sid and sname:
                    mapping[sid.strip()] = LabelEntry(_clean_name(sname), "sub_module")
                for grp in sub.get("groups", []):
                    gid, gname = grp.get("group_id"), grp.get("group_name")
                    if gid and gname:
                        mapping[gid.strip()] = LabelEntry(_clean_name(gname), "group")
                    for met in grp.get("value", []):
                        mid, mname = met.get("metric_id"), met.get("metric_name")
                        if mid and mname:
                            mapping[mid.strip()] = LabelEntry(_clean_name(mname), "metric")
        except FileNotFoundError:
            logger.warning("labeling: %s not found; its metric names unavailable", json_path)
        except Exception:  # pragma: no cover - defensive
            logger.exception("labeling: failed to parse %s", json_path)

    logger.info("labeling: loaded %d code->name entries", len(mapping))
    return mapping


def _strip_codes(text: str) -> str:
    """Remove all code-like tokens so only prose + data numbers remain."""
    return CODE_RE.sub(" ", text)


def _numbers(text: str) -> List[str]:
    """Ordered list of data-number tokens after codes are stripped."""
    return _NUM_RE.findall(_strip_codes(text))


def validate_labeling(original: str, labeled: str, label_map: Dict[str, LabelEntry]) -> Tuple[bool, List[str]]:
    """
    Validation gate. Returns (ok, issues).

    Hard gates (failure => caller must fall back to the code text):
      A. No *known* code survives in the labelled text (substitution was complete).
      B. Numeric integrity: the data numbers (correlations, scores, p-values, counts)
         are byte-identical between the code text and the labelled text. Substitution
         only rewrites code spans, so any change here means a real corruption bug.
    """
    issues: List[str] = []

    # Gate A - no known code left behind. Canonicalise first, or a markdown-escaped
    # leftover (BSPT\_001) would slip past the membership test unnoticed.
    leftover = sorted(
        {c for c in map(_canonical_code, CODE_RE.findall(labeled)) if c in label_map}
    )
    if leftover:
        issues.append(f"unsubstituted known codes remain: {leftover[:10]}")

    # Gate B - numeric integrity
    if _numbers(original) != _numbers(labeled):
        issues.append("numeric integrity check failed: data numbers changed during substitution")

    return (len(issues) == 0), issues


def label_output(text: str | None) -> LabelingResult:
    """
    Produce the labelled view of a report body.

    Deterministically replaces every *known* code with its business name, collects
    the code->name legend actually used, records any unmapped code-like tokens, and
    runs the validation gate. On gate failure (or empty input) the result carries the
    original text and a non-"ok" status so callers serve codes rather than a corrupt
    report.
    """
    if not text or not text.strip():
        return LabelingResult(labeled_text=text or "", status="skipped")

    label_map = load_label_map()
    if not label_map:
        return LabelingResult(labeled_text=text, status="skipped",
                              issues=["label map empty (reference data missing)"])

    seen: Dict[str, None] = {}       # preserve first-appearance order of mapped codes
    unmapped: Dict[str, None] = {}

    def _repl(m: re.Match) -> str:
        # The matched span may carry markdown escaping (BSPT\_001); the label map
        # is keyed on the plain form, and the legend should report the plain form
        # too, so callers never see the escaping as part of the code.
        code = _canonical_code(m.group(0))
        entry = label_map.get(code)
        if entry is None:
            unmapped.setdefault(code, None)
            return m.group(0)  # leave the original span untouched, escaping and all
        seen.setdefault(code, None)
        return entry.name

    labeled = CODE_RE.sub(_repl, text)

    labels = [
        {"code": c, "name": label_map[c].name, "level": label_map[c].level}
        for c in seen
    ]

    ok, issues = validate_labeling(text, labeled, label_map)
    if unmapped:
        issues.append(f"unmapped code-like tokens (left as-is): {sorted(unmapped)[:10]}")

    if not ok:
        # Fail safe: never serve a corrupted report - fall back to the code text.
        logger.warning("labeling: validation failed, serving code text. issues=%s", issues)
        return LabelingResult(labeled_text=text, labels=labels,
                              unmapped_codes=sorted(unmapped), status="failed", issues=issues)

    return LabelingResult(labeled_text=labeled, labels=labels,
                          unmapped_codes=sorted(unmapped), status="ok", issues=issues)
