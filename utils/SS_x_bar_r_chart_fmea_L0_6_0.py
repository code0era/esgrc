import pandas as pd
# pyrefly: ignore [missing-import]
import matplotlib.pyplot as plt
# pyrefly: ignore [missing-import]
from matplotlib.backends.backend_pdf import PdfPages

ANALYSIS_DATE = "2026-01-07"
D2_APPROX = 1.128

# ---------- Helper functions ----------
def to_long(df_wide: pd.DataFrame) -> pd.DataFrame:
    df_wide = df_wide.copy()
    df_wide["timestamp"] = range(1, len(df_wide) + 1)

    metric_cols = [c for c in df_wide.columns if c != "timestamp"]

    long_df = df_wide.melt(id_vars=["timestamp"], value_vars=metric_cols,
                           var_name="metric_id", value_name="value")
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.sort_values(["metric_id", "timestamp"]).reset_index(drop=True)
    return long_df

def xmr_limits(series: pd.Series):
    xbar = series.mean()
    mr = series.diff().abs().dropna()
    mrbar = mr.mean()
    sigma = mrbar / D2_APPROX if pd.notnull(mrbar) and mrbar > 0 else 0.0
    ucl_x = xbar + 3 * sigma
    lcl_x = xbar - 3 * sigma
    ucl_mr = 3.268 * mrbar if pd.notnull(mrbar) else float("nan")
    lcl_mr = 0.0
    return dict(xbar=xbar, mrbar=mrbar, sigma=sigma,
                ucl_x=ucl_x, lcl_x=lcl_x, ucl_mr=ucl_mr, lcl_mr=lcl_mr)

def detect_signals_xmr(df_metric: pd.DataFrame, limits: dict) -> pd.DataFrame:
    out = df_metric.copy()
    out["signal_x"] = (out["value"] > limits["ucl_x"]) | (out["value"] < limits["lcl_x"])
    out["mr"] = out["value"].diff().abs()
    out["signal_mr"] = out["mr"] > limits["ucl_mr"]
    return out

def rpn_score(S: int, signals_count: int, D: int) -> int:
    # Make occurrence proportional to signals count
    O = max(1, signals_count)
    return S * O * D

# ---------- Analysis ----------
def analyze_wide(df_wide: pd.DataFrame, severity_default=7, detection_default=5):
    long_df = to_long(df_wide)
    metric_ids = sorted(long_df["metric_id"].unique())
    summary_rows = []

    for metric_id in metric_ids:
        df_m = long_df[long_df["metric_id"] == metric_id].sort_values("timestamp")
        limits = xmr_limits(df_m["value"])
        df_sig = detect_signals_xmr(df_m, limits)
        signals_count = int(df_sig["signal_x"].sum() + df_sig["signal_mr"].sum())
        rpn = rpn_score(severity_default, signals_count, detection_default)

        # Calculate Cpk and Sigma Level
        usl, lsl = limits["xbar"] + 3 * limits["sigma"], limits["xbar"] - 3 * limits["sigma"]
        cpk = round(min((usl - limits["xbar"]) / (3 * limits["sigma"]),
                        (limits["xbar"] - lsl) / (3 * limits["sigma"])), 2) if limits["sigma"] > 0 else 0
        sigma_level = round(3 * cpk, 2)

        summary_rows.append({
            "metric_id": metric_id,
            "mean": round(limits["xbar"], 2),
            "sigma": round(limits["sigma"], 2),
            "UCL": round(limits["ucl_x"], 2),
            "LCL": round(limits["lcl_x"], 2),
            "signals": signals_count,
            "RPN": rpn,
            "Cpk": cpk,
            "Sigma_Level": sigma_level,
            # keep MR chart parameters for technical traceability
            "MRBar": round(limits["mrbar"], 2),
            "UCL_MR": round(limits["ucl_mr"], 2),
            "LCL_MR": round(limits["lcl_mr"], 2)
        })

    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values(["RPN", "signals", "metric_id"], ascending=[False, False, True]).reset_index(drop=True)
    summary["analysis_date"] = ANALYSIS_DATE
    return long_df, summary, metric_ids

# ---------- PDF Generators ----------
def save_rpn_summary_pdf(summary: pd.DataFrame, filename: str, rows_per_page=30):
    # Streamlined stakeholder view
    cols = ["metric_id", "mean", "UCL", "LCL", "Sigma_Level", "RPN", "analysis_date"]
    table_df = summary[cols].copy()
    num_pages = (len(table_df) + rows_per_page - 1) // rows_per_page

    with PdfPages(filename) as pdf:
        for page in range(num_pages):
            start = page * rows_per_page
            end = min((page + 1) * rows_per_page, len(table_df))
            chunk = table_df.iloc[start:end]

            fig, ax = plt.subplots(figsize=(11, 8))
            plt.subplots_adjust(top=0.85, bottom=0.15, left=0.1, right=0.95)
            ax.axis("off")

            ax.set_title(f"RPN Summary Report ({ANALYSIS_DATE}) - Page {page+1}/{num_pages}",
                         fontsize=14, weight="bold", pad=30)

            table = ax.table(cellText=chunk.to_numpy(),
                             colLabels=chunk.columns.tolist(),
                             loc="center")
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(0.9, 1.2)
            table.auto_set_column_width(col=list(range(len(chunk.columns))))

            ax.text(0.5, -0.12,
                    f"Analysis generated on {ANALYSIS_DATE} | Total metrics: {len(table_df)}",
                    ha="center", va="top", fontsize=10, transform=ax.transAxes)

            pdf.savefig(fig)
            plt.close(fig)

def save_spc_charts_pdf(long_df: pd.DataFrame, metric_ids, filename: str):
    with PdfPages(filename) as pdf:
        for metric_id in metric_ids:
            df_m = long_df[long_df["metric_id"] == metric_id].sort_values("timestamp")
            limits = xmr_limits(df_m["value"])
            df_sig = detect_signals_xmr(df_m, limits)

            fig = plt.figure(figsize=(11, 8))
            plt.subplots_adjust(top=0.85, bottom=0.15, left=0.1, right=0.95)

            plt.plot(df_sig["timestamp"], df_sig["value"], marker="o", label="Values")
            plt.axhline(limits["xbar"], color="green", linestyle="--", label="Center Line")
            plt.axhline(limits["ucl_x"], color="red", linestyle="--", label="UCL")
            plt.axhline(limits["lcl_x"], color="red", linestyle="--", label="LCL")
            plt.title(f"Individuals Chart for {metric_id} ({ANALYSIS_DATE})", pad=30)
            plt.xlabel("Timestamp")
            plt.ylabel("Performance (%)")
            plt.legend()
            pdf.savefig(fig)
            plt.close(fig)

# ---------- Main ----------
if __name__ == "__main__":
    df_wide = pd.read_csv("all_module_values.csv", sep=",")
    long_df, summary, metric_ids = analyze_wide(df_wide)

    # Save full TXT summary (technical view with all parameters)
    summary.to_csv(f"SPC_summary_L0_{ANALYSIS_DATE}.txt", sep="\t", index=False)

    # Save streamlined stakeholder PDF summary
    save_rpn_summary_pdf(summary, f"RPN_summary_L0_{ANALYSIS_DATE}.pdf")

    # Save SPC charts PDF
    save_spc_charts_pdf(long_df, metric_ids, f"SPC_charts_L0_{ANALYSIS_DATE}.pdf")

    # Console output (stakeholder view)
    print(summary[["metric_id", "mean", "UCL", "LCL", "Sigma_Level", "RPN", "analysis_date"]].to_string(index=False))
    
##    What’s New - 16th Jan 2026
##- Cpk and Sigma_Level added to summary.
##- MRBar, UCL_MR, LCL_MR included for Moving Range chart parameters.
##- TXT summary now includes all SPC parameters.
##- PDF summary table expanded with new columns.
##- SPC charts PDF still shows Individuals charts with UCL/LCL.

##This script now gives you a complete SPC package:
##- TXT file for machine parsing.
##- RPN summary PDF for stakeholders.
##- SPC charts PDF for visual diagnostics.
