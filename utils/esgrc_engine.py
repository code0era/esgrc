"""
ESGRC Report Generation Engine
Faithfully ported from: AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py
Computes weighted averages and identifies low-performing metrics/groups/sub-modules.
"""

import pandas as pd
import numpy as np
import io
from datetime import datetime
from typing import Dict, List, Tuple, Generator


# ─────────────────────────────────────────────────────────────────────────────
# DATA EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_ids(json_data: dict) -> Tuple[List[str], List[str], List[str]]:
    """Extract metric_ids, group_ids, sub_module_ids from the ESGRC JSON config."""
    metric_ids, group_ids, sub_module_ids = [], [], []
    for sub_module in json_data.get("sub_modules", []):
        sub_module_ids.append(sub_module["sub_module_id"])
        for group in sub_module.get("groups", []):
            group_ids.append(group["group_id"])
            for perf in group.get("value", []):
                metric_ids.append(perf["metric_id"])
    return metric_ids, group_ids, sub_module_ids


def extract_id_names(json_data: dict) -> Dict[str, str]:
    """Build a flat {id: display_name} mapping from the ESGRC JSON config."""
    mapping = {}
    for sm in json_data.get("sub_modules", []):
        mapping[sm["sub_module_id"]] = sm["sub_module_name"]
        for g in sm.get("groups", []):
            mapping[g["group_id"]] = g["group_name"]
            for p in g.get("value", []):
                mapping[p["metric_id"]] = p["metric_name"]
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def calculate_weighted_average(values: List[float], weights: List[float]) -> float:
    """Return the weighted mean; returns 0.0 when total weight is zero."""
    total = sum(weights)
    if total == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total


def calculate_averages(
    json_data: dict,
    metric_data: pd.DataFrame,
) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], Dict[str, List[float]]]:
    """
    Replicate the exact averaging logic from the original Python script.
    Returns (group_averages, sub_module_averages, module_averages).
    """
    group_averages: Dict[str, List[float]] = {
        g["group_id"]: []
        for sm in json_data.get("sub_modules", [])
        for g in sm.get("groups", [])
    }
    sub_module_averages: Dict[str, List[float]] = {
        sm["sub_module_id"]: [] for sm in json_data.get("sub_modules", [])
    }
    module_averages: Dict[str, List[float]] = {json_data["module_id"]: []}

    for row_idx in range(len(metric_data)):
        row_module_values: List[float] = []

        for sm in json_data.get("sub_modules", []):
            sm_id = sm["sub_module_id"]
            sm_weights: List[float] = []
            sm_values: List[float] = []

            for g in sm.get("groups", []):
                g_id = g["group_id"]
                g_weights: List[float] = []
                g_values: List[float] = []

                for perf in g.get("value", []):
                    mid = perf["metric_id"]
                    if mid in metric_data.columns:
                        g_weights.append(float(perf.get("weight", 1)))
                        g_values.append(float(metric_data[mid].iloc[row_idx]))

                if g_weights and g_values:
                    wavg = calculate_weighted_average(g_values, g_weights)
                    group_averages[g_id].append(wavg)
                    sm_weights.append(1.0)
                    sm_values.append(wavg)

            # Fallback: sub-module has direct metrics (no groups)
            if not sm_weights and not sm_values and "value" in sm:
                for perf in sm.get("value", []):
                    mid = perf["metric_id"]
                    if mid in metric_data.columns:
                        sm_weights.append(float(perf.get("weight", 1)))
                        sm_values.append(float(metric_data[mid].iloc[row_idx]))

            if sm_weights and sm_values:
                sm_avg = calculate_weighted_average(sm_values, sm_weights)
                sub_module_averages[sm_id].append(sm_avg)
                row_module_values.append(sm_avg)

        if row_module_values:
            mod_avg = calculate_weighted_average(
                row_module_values, [1.0] * len(row_module_values)
            )
            module_averages[json_data["module_id"]].append(mod_avg)

    return group_averages, sub_module_averages, module_averages


def build_enriched_dataframe(
    metric_data: pd.DataFrame,
    group_averages: Dict[str, List[float]],
    sub_module_averages: Dict[str, List[float]],
    module_averages: Dict[str, List[float]],
    module_id: str,
) -> pd.DataFrame:
    """
    Append computed group/sub-module/module average columns to the original
    metric DataFrame (mirrors save_averages_to_csv from the original script).
    """
    n = len(metric_data)
    new_cols: Dict[str, list] = {}

    for gid, avgs in group_averages.items():
        padded = avgs + [np.nan] * max(0, n - len(avgs))
        new_cols[gid] = [round(v, 2) for v in padded[:n]]

    for smid, avgs in sub_module_averages.items():
        padded = avgs + [np.nan] * max(0, n - len(avgs))
        new_cols[smid] = [round(v, 2) for v in padded[:n]]

    mod_avgs = module_averages.get(module_id, [])
    padded_mod = mod_avgs + [np.nan] * max(0, n - len(mod_avgs))
    new_cols["ESRC_001"] = [round(v, 2) for v in padded_mod[:n]]

    enriched = pd.concat([metric_data, pd.DataFrame(new_cols)], axis=1)
    return enriched


def identify_low_performers(
    ids: List[str],
    enriched_df: pd.DataFrame,
    top_n: int = 10,
) -> List[Tuple[str, float]]:
    """Return the top_n lowest-scoring IDs with their values (row 0)."""
    scores = {
        id_: float(enriched_df[id_].iloc[0])
        for id_ in ids
        if id_ in enriched_df.columns
    }
    return sorted(scores.items(), key=lambda x: x[1])[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# REPORT GENERATION  (streaming-aware)
# ─────────────────────────────────────────────────────────────────────────────

def build_report_sections(
    json_data: dict,
    low_metrics: List[Tuple[str, float]],
    low_groups: List[Tuple[str, float]],
    low_sub_modules: List[Tuple[str, float]],
    overall_avg: float,
    id_names: Dict[str, str],
) -> List[str]:
    """
    Returns a list of text chunks that together form the full report.
    Each chunk is emitted progressively for streaming.
    """
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    module_name = json_data.get("module_name", json_data["module_id"])

    chunks: List[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    header = (
        f"{'═' * 66}\n"
        f"   ESGRC MODULE PERFORMANCE REPORT\n"
        f"{'═' * 66}\n"
        f"   Module  : {module_name}\n"
        f"   Report  : Low-Performing Entity Analysis\n"
        f"   Generated: {now}\n"
        f"{'═' * 66}\n"
    )
    chunks.append(header)

    # ── Section 1: Metrics ────────────────────────────────────────────────────
    sec1 = (
        f"\n{'─' * 66}\n"
        f"  📊  LOW-PERFORMING METRICS  (Bottom 10)\n"
        f"{'─' * 66}\n"
        f"  {'#':<4} {'Metric ID':<14} {'Metric Name':<38} {'Score':>6}\n"
        f"{'─' * 66}\n"
    )
    for i, (mid, val) in enumerate(low_metrics, 1):
        name = id_names.get(mid, "Unknown")
        sec1 += f"  {i:<4} {mid:<14} {name:<38} {val:>6.2f}\n"
    chunks.append(sec1)

    # ── Section 2: Groups ─────────────────────────────────────────────────────
    sec2 = (
        f"\n{'─' * 66}\n"
        f"  📊  LOW-PERFORMING GROUPS  (Bottom 10)\n"
        f"{'─' * 66}\n"
        f"  {'#':<4} {'Group ID':<14} {'Group Name':<38} {'Score':>6}\n"
        f"{'─' * 66}\n"
    )
    for i, (gid, val) in enumerate(low_groups, 1):
        name = id_names.get(gid, "Unknown")
        sec2 += f"  {i:<4} {gid:<14} {name:<38} {val:>6.2f}\n"
    chunks.append(sec2)

    # ── Section 3: Sub-Modules ────────────────────────────────────────────────
    sec3 = (
        f"\n{'─' * 66}\n"
        f"  📊  LOW-PERFORMING SUB-MODULES  (Bottom 10)\n"
        f"{'─' * 66}\n"
        f"  {'#':<4} {'Sub-Module ID':<14} {'Sub-Module Name':<38} {'Score':>6}\n"
        f"{'─' * 66}\n"
    )
    for i, (smid, val) in enumerate(low_sub_modules, 1):
        name = id_names.get(smid, "Unknown")
        sec3 += f"  {i:<4} {smid:<14} {name:<38} {val:>6.2f}\n"
    chunks.append(sec3)

    # ── Summary ────────────────────────────────────────────────────────────────
    summary = (
        f"\n{'═' * 66}\n"
        f"  📈  OVERALL MODULE PERFORMANCE\n"
        f"{'═' * 66}\n"
        f"  Module ID    : {json_data['module_id']}\n"
        f"  Module Score : {overall_avg:.2f}\n"
        f"{'═' * 66}\n"
    )
    chunks.append(summary)

    return chunks


def generate_report(
    json_data: dict,
    csv_bytes: bytes,
) -> Tuple[List[str], str, dict]:
    """
    Run the full ESGRC report pipeline.

    Returns:
        chunks       – list of text sections for progressive streaming
        full_report  – the complete report as a single string
        context      – dict with structured data for AI chat context
    """
    # 1. Load & enrich data
    metric_data = pd.read_csv(io.BytesIO(csv_bytes), low_memory=False)
    metric_ids, group_ids, sub_module_ids = extract_ids(json_data)
    id_names = extract_id_names(json_data)

    group_avgs, sm_avgs, mod_avgs = calculate_averages(json_data, metric_data)
    enriched_df = build_enriched_dataframe(
        metric_data, group_avgs, sm_avgs, mod_avgs, json_data["module_id"]
    )

    # 2. Identify low performers
    low_metrics = identify_low_performers(metric_ids, enriched_df)
    low_groups = identify_low_performers(group_ids, enriched_df)
    low_sub_modules = identify_low_performers(sub_module_ids, enriched_df)

    mod_avg_list = mod_avgs.get(json_data["module_id"], [0.0])
    overall_avg = calculate_weighted_average(mod_avg_list, [1.0] * len(mod_avg_list))

    # 3. Build text chunks
    chunks = build_report_sections(
        json_data, low_metrics, low_groups, low_sub_modules, overall_avg, id_names
    )
    full_report = "".join(chunks)

    # 4. Build AI context dict (for Claude chat system prompt)
    context = {
        "module_id": json_data["module_id"],
        "module_name": json_data.get("module_name", ""),
        "overall_score": round(overall_avg, 2),
        "total_metrics": len(metric_ids),
        "total_groups": len(group_ids),
        "total_sub_modules": len(sub_module_ids),
        "low_metrics": [
            {"id": mid, "name": id_names.get(mid, mid), "score": round(val, 2)}
            for mid, val in low_metrics
        ],
        "low_groups": [
            {"id": gid, "name": id_names.get(gid, gid), "score": round(val, 2)}
            for gid, val in low_groups
        ],
        "low_sub_modules": [
            {"id": smid, "name": id_names.get(smid, smid), "score": round(val, 2)}
            for smid, val in low_sub_modules
        ],
        "report_text": full_report,
    }

    return chunks, full_report, context
