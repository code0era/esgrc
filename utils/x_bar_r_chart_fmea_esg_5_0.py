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

    # Treat ALL columns except timestamp as metrics
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
    O = min(10, max(1, signals_count))
    return S * O * D

def plot_xmr(df_metric, limits, metric_id):
    fig = plt.figure(figsize=(11, 8))
    plt.subplots_adjust(top=0.85, bottom=0.15, left=0.1, right=0.95)

    plt.plot(df_metric["timestamp"], df_metric["value"], marker="o", label="Values")
    plt.axhline(limits["xbar"], color="green", linestyle="--", label="Center Line")
    plt.axhline(limits["ucl_x"], color="red", linestyle="--", label="UCL")
    plt.axhline(limits["lcl_x"], color="red", linestyle="--", label="LCL")
    plt.title(f"Individuals Chart for {metric_id} ({ANALYSIS_DATE})", pad=30)
    plt.xlabel("Timestamp")
    plt.ylabel("Performance (%)")
    plt.legend()
    plt.tight_layout()
    return plt

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

        summary_rows.append({
            "metric_id": metric_id,
            "mean": round(limits["xbar"], 2),
            "sigma": round(limits["sigma"], 2),
            "UCL": round(limits["ucl_x"], 2),
            "LCL": round(limits["lcl_x"], 2),
            "signals": signals_count,
            "RPN": rpn
        })

    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values(["RPN", "signals", "metric_id"], ascending=[False, False, True]).reset_index(drop=True)
    summary["analysis_date"] = ANALYSIS_DATE
    return long_df, summary, metric_ids

# ---------- PDF Generators with formatting ----------
def save_rpn_summary_pdf(summary: pd.DataFrame, filename: str, rows_per_page=30):
    cols = ["metric_id", "mean", "sigma", "UCL", "LCL", "signals", "RPN", "analysis_date"]
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
    df_wide = pd.read_csv("input_metric_values_esgrc.csv", sep=",")
    long_df, summary, metric_ids = analyze_wide(df_wide)

    # Save TXT summary
    summary.to_csv(f"metrics_summary_{ANALYSIS_DATE}.txt", sep="\t", index=False)

    # Save RPN summary PDF
    save_rpn_summary_pdf(summary, f"RPN_summary_report_{ANALYSIS_DATE}.pdf")

    # Save SPC charts PDF
    save_spc_charts_pdf(long_df, metric_ids, f"SPC_charts_report_{ANALYSIS_DATE}.pdf")

    # Console output
    print(summary.to_string(index=False))