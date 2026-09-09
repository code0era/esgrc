import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from flask import Flask, request, jsonify
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
import os
from CHAID import Tree  # This imports the CHAID Tree class
import json  # For loading JSON lookup

# -----------------------------
# NEW: Load metric/group/sub-module names from JSON
# -----------------------------
def build_metric_lookup(json_file_path='enterprise_performance_json_file.json'):
    """
    Loads the JSON hierarchy and creates lookup dictionaries:
    metric_id → metric_name
    group_id   → group_name
    sub_module_id → sub_module_name
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load JSON lookup: {e}. Using IDs only.")
        return {}, {}, {}

    metric_to_name = {}
    group_to_name = {}
    sub_module_to_name = {}

    for sub_mod in data.get('sub_modules', []):
        sub_id = sub_mod.get('sub_module_id')
        sub_name = sub_mod.get('sub_module_name')
        if sub_id and sub_name:
            sub_module_to_name[sub_id] = sub_name

        for grp in sub_mod.get('groups', []):
            grp_id = grp.get('group_id')
            grp_name = grp.get('group_name')
            if grp_id and grp_name:
                group_to_name[grp_id] = grp_name

            for met in grp.get('value', []):
                met_id = met.get('metric_id')
                met_name = met.get('metric_name')
                if met_id and met_name:
                    metric_to_name[met_id] = met_name

    print("Metric name lookup loaded from JSON.")
    return metric_to_name, group_to_name, sub_module_to_name

# -----------------------------
# Report-size guard: write top-N by significance instead of the full O(n^2)
# dump. Enterprise has 372 metrics (vs ESGRC's 84) and the correlation matrix dump
# and inconsistency table both scale with the SQUARE of the metric count, so the
# untrimmed outputs are far larger. Customer (348 metrics) hit this first on
# 2026-07-31: a 9.1MB combined step-6 report that overflowed Claude's context
# window (guard.py's fallback char/token estimate also undercounted the dense
# tabular content - see guard.py's CHARS_PER_TOKEN_FALLBACK comment for that
# half of the fix). Applied here preemptively rather than on a live 400. This
# only changes what gets WRITTEN to the report files below; the full
# correlation matrices and full inconsistency dicts are still computed and
# used unchanged for CHAID risk binning (bin_features).
# -----------------------------
CORRELATION_THRESHOLD = 0.5  # matches detect_inconsistencies's corr_threshold
CORRELATION_TOP_N = 150
INCONSISTENCY_TOP_N = 30

def write_top_correlations(f, name, corr_matrix, lookup):
    """Write a top-N-by-|correlation| pair table instead of the full matrix."""
    cols = corr_matrix.columns
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            corr = corr_matrix.loc[c1, c2]
            if pd.isna(corr):
                continue
            pairs.append((c1, c2, corr))

    total_pairs = len(pairs)
    above_threshold = [p for p in pairs if abs(p[2]) >= CORRELATION_THRESHOLD]
    mean_abs_corr = (sum(abs(p[2]) for p in pairs) / total_pairs) if total_pairs else 0.0

    f.write(f"\n{name} Correlation Summary\n")
    f.write(f"Total pairs examined: {total_pairs}\n")
    f.write(f"Pairs with |correlation| >= {CORRELATION_THRESHOLD}: {len(above_threshold)}\n")
    f.write(f"Mean |correlation|: {mean_abs_corr:.4f}\n")

    shown = sorted(above_threshold, key=lambda p: abs(p[2]), reverse=True)[:CORRELATION_TOP_N]
    if not shown:
        # Nothing cleared the threshold - show the strongest pairs anyway so a
        # weakly-correlated dataset isn't reported as if it had no data.
        shown = sorted(pairs, key=lambda p: abs(p[2]), reverse=True)[:CORRELATION_TOP_N]
        f.write(f"\nNo pairs met the threshold - showing top {len(shown)} by |correlation| anyway:\n")
    else:
        f.write(f"\nTop {len(shown)} pairs by |correlation| (descending):\n")

    f.write("Metric 1 ID | Metric 1 Name | Metric 2 ID | Metric 2 Name | Correlation\n")
    f.write("-" * 100 + "\n")
    for c1, c2, corr in shown:
        c1_name = lookup.get(c1, c1)
        c2_name = lookup.get(c2, c2)
        f.write(f"{c1} | {c1_name} | {c2} | {c2_name} | {corr:.4f}\n")


def write_inconsistency_table(f, inc_dict, lookup):
    """Write up to INCONSISTENCY_TOP_N rows ranked by percentage (severity),
    instead of every pair the O(n^2) scan flagged."""
    if not inc_dict:
        f.write("None found.\n")
        return
    ranked = sorted(inc_dict.items(), key=lambda kv: kv[1]['percentage'], reverse=True)
    shown = ranked[:INCONSISTENCY_TOP_N]
    f.write(f"{len(inc_dict)} pair(s) found; showing top {len(shown)} by percentage:\n")
    f.write("Metric 1 ID | Metric 1 Name | Metric 2 ID | Metric 2 Name | Correlation | Count | Percentage | Over Points\n")
    f.write("-" * 100 + "\n")
    for (c1, c2), info in shown:
        c1_name = lookup.get(c1, c1)
        c2_name = lookup.get(c2, c2)
        f.write(f"{c1} | {c1_name} | {c2} | {c2_name} | {info['correlation']:.2f} | "
                f"{info['count']} | {info['percentage']:.2f}% | {info['min_len']}\n")

# -----------------------------
# 1. Define ALL other functions FIRST (unchanged)
# -----------------------------
def correlation_loss(pred, target):
    pred_mean = pred - pred.mean(dim=0, keepdim=True)
    target_mean = target - target.mean(dim=0, keepdim=True)
    numerator = (pred_mean * target_mean).sum(dim=0)
    denominator = torch.sqrt((pred_mean**2).sum(dim=0) * (target_mean**2).sum(dim=0) + 1e-8)
    corr = numerator / denominator
    return 1 - corr.mean()

class CombinedLoss(nn.Module):
    def __init__(self, alpha=0.5):
        super(CombinedLoss, self).__init__()
        self.mse = nn.MSELoss()
        self.alpha = alpha

    def forward(self, pred, target):
        mse_loss = self.mse(pred, target)
        corr_loss = correlation_loss(pred, target)
        return self.alpha * mse_loss + (1 - self.alpha) * corr_loss

def load_csv_file(csv_file_path):
    return pd.read_csv(csv_file_path, low_memory=False)

def extract_metrics_from_data(data):
    metric_columns = data.columns
    return {col: pd.to_numeric(data[col], errors='coerce') for col in metric_columns}

def normalize_data(df):
    return (df - df.mean()) / df.std().replace(0, 1)

class CorrelationNN(nn.Module):
    def __init__(self, input_dim):
        super(CorrelationNN, self).__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, input_dim)

    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x)

def train_nn_model(X, input_dim):
    model = CorrelationNN(input_dim)
    criterion = CombinedLoss(alpha=0.5)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    X_tensor = torch.tensor(X.values, dtype=torch.float32)
    dataset = torch.utils.data.TensorDataset(X_tensor, X_tensor)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)
    num_epochs = 100
    for epoch in range(num_epochs):
        for batch_X, _ in dataloader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_X)
            loss.backward()
            optimizer.step()
    return model

def identify_trends(df):
    trends = {}
    time = np.arange(len(df))
    for col in df.columns:
        y = df[col].dropna().values
        if len(y) < 2:
            trends[col] = "Insufficient data"
            continue
        x = time[:len(y)].reshape(-1, 1)
        model = LinearRegression().fit(x, y)
        slope = model.coef_[0]
        if abs(slope) < 1e-5:
            trends[col] = "Stable"
        elif slope > 0:
            trends[col] = "Increasing"
        else:
            trends[col] = "Decreasing"
    return trends

def assess_repetition_with_fourier(df, sampling_rate=1):
    repetitions = {}
    for col in df.columns:
        y = df[col].dropna().values
        if len(y) < 2:
            repetitions[col] = "Insufficient data"
            continue
        N = len(y)
        yf = fft(y)
        xf = fftfreq(N, 1 / sampling_rate)[:N//2]
        magnitudes = 2.0 / N * np.abs(yf[:N//2])
        peaks, _ = find_peaks(magnitudes, height=0.1)
        if len(peaks) > 0:
            dominant_freq = xf[peaks[0]]
            if dominant_freq > 0:
                period = 1 / dominant_freq
                repetitions[col] = f"Dominant period: {period:.2f} units (repetitive)"
            else:
                repetitions[col] = "No clear repetition (potential instability)"
        else:
            repetitions[col] = "No clear repetition (potential instability)"
    return repetitions

def detect_inconsistencies(corr_matrix, df, corr_threshold=0.5, z_threshold=2.0):
    dependent_inconsistencies = {}
    independent_inconsistencies = {}
    cols = corr_matrix.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            col1, col2 = cols[i], cols[j]
            corr = corr_matrix.loc[col1, col2]
            if pd.isna(corr):
                continue
            series1 = df[col1].dropna()
            series2 = df[col2].dropna()
            min_len = min(len(series1), len(series2))
            if min_len < 2:
                continue
            series1 = series1[:min_len]
            series2 = series2[:min_len]
            z1 = (series1 - series1.mean()) / (series1.std() + 1e-8)
            z2 = (series2 - series2.mean()) / (series2.std() + 1e-8)
            diff = np.abs(z1 - z2)
            if abs(corr) > corr_threshold:
                inconsistent_points = np.where(diff > z_threshold)[0]
                count = len(inconsistent_points)
                if count > 0:
                    dependent_inconsistencies[(col1, col2)] = {
                        'correlation': corr, 'count': count,
                        'percentage': (count / min_len) * 100, 'min_len': min_len
                    }
            else:
                sync_points = np.where(diff < 0.5)[0]
                count = len(sync_points)
                if count > min_len * 0.1:
                    independent_inconsistencies[(col1, col2)] = {
                        'correlation': corr, 'count': count,
                        'percentage': (count / min_len) * 100, 'min_len': min_len
                    }
    return dependent_inconsistencies, independent_inconsistencies

def bin_features(trends, repetitions, dep_inc, ind_inc, corr_matrix):
    metrics = list(corr_matrix.columns)
    data = []
    for metric in metrics:
        trend = trends.get(metric, "Unknown")
        trend_bin = trend
       
        rep = repetitions.get(metric, "Unknown")
        if "repetitive" in str(rep).lower():
            rep_bin = "Repetitive"
        elif "instability" in str(rep).lower():
            rep_bin = "Irregular"
        else:
            rep_bin = "Insufficient"
       
        corr_series = corr_matrix[metric].dropna().abs()
        avg_corr = corr_series.mean() if not corr_series.empty else 0.0
        if avg_corr > 0.6:
            corr_bin = "Very High"
        elif avg_corr > 0.4:
            corr_bin = "High"
        elif avg_corr > 0.2:
            corr_bin = "Medium"
        else:
            corr_bin = "Low"
       
        dep_count = sum(1 for pair in dep_inc if metric in pair)
        ind_count = sum(1 for pair in ind_inc if metric in pair)
        total_inc = dep_count + ind_count
        if total_inc > 15:
            inc_bin = "Very High"
        elif total_inc > 8:
            inc_bin = "High"
        elif total_inc > 3:
            inc_bin = "Medium"
        else:
            inc_bin = "Low"
       
        if inc_bin in ["Very High", "High"] and rep_bin == "Irregular":
            risk_level = "Critical"
        elif inc_bin in ["Very High", "High"] or rep_bin == "Irregular":
            risk_level = "High"
        elif inc_bin == "Medium" or corr_bin in ["Very High", "High"] or trend == "Decreasing":
            risk_level = "Elevated"
        elif trend == "Stable" and rep_bin == "Repetitive" and inc_bin == "Low":
            risk_level = "Low"
        else:
            risk_level = "Moderate"
       
        data.append({
            'Metric': metric,
            'Trend': trend_bin,
            'Repetition': rep_bin,
            'Avg_Correlation': corr_bin,
            'Inconsistency_Level': inc_bin,
            'Risk_Level': risk_level
        })
   
    df_chaid = pd.DataFrame(data)
   
    df_chaid = df_chaid.fillna({
        'Trend': 'Unknown',
        'Repetition': 'Insufficient',
        'Avg_Correlation': 'Low',
        'Inconsistency_Level': 'Low',
        'Risk_Level': 'Moderate'
    })
   
    print("\nCHAID Risk Level Distribution:")
    print(df_chaid['Risk_Level'].value_counts())
   
    return df_chaid

# Flask app
app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json['data']
    data_tensor = torch.tensor([data], dtype=torch.float32)
    with torch.no_grad():
        prediction = model(data_tensor).numpy()
    return jsonify({'prediction': prediction.tolist()})

# -----------------------------
# 2. Complete main() function
# -----------------------------
def main(metrics_csv_file_path, group_csv_file_path, sub_module_csv_file_path):
    # Load the JSON lookup once at the beginning
    json_path = 'enterprise_performance_json_file.json'  # Adjust path if needed
    metric_lookup, group_lookup, sub_lookup = build_metric_lookup(json_path)

    # Load the data
    metrics_data = load_csv_file(metrics_csv_file_path)
    group_data = load_csv_file(group_csv_file_path)
    sub_module_data = load_csv_file(sub_module_csv_file_path)

    # Extract metrics
    metrics = extract_metrics_from_data(metrics_data)
    groups = extract_metrics_from_data(group_data)
    sub_modules = extract_metrics_from_data(sub_module_data)

    # Create and clean DataFrames
    df_metrics = pd.DataFrame(metrics).dropna(axis=1, how='all')
    df_groups = pd.DataFrame(groups).dropna(axis=1, how='all')
    df_sub_modules = pd.DataFrame(sub_modules).dropna(axis=1, how='all')

    # Normalize
    df_metrics = normalize_data(df_metrics)
    df_groups = normalize_data(df_groups)
    df_sub_modules = normalize_data(df_sub_modules)

    # Train model
    input_dim = df_metrics.shape[1]
    global model
    model = train_nn_model(df_metrics, input_dim)
    torch.save(model.state_dict(), 'correlation_model.pth')

    # File names
    output_report_file = 'M_G_SM_correlation_report_enterprise.txt'
    trends_file = 'trends_and_repetitions_report_enterprise.txt'
    inconsistencies_file = 'inconsistencies_report_enterprise.txt'
    chaid_report_file = 'chaid_risk_segmentation_report_enterprise.txt'

    # Model evaluation example
    model.eval()
    with torch.no_grad():
        X_tensor = torch.tensor(df_metrics.values, dtype=torch.float32)
        y_pred = model(X_tensor).numpy()
        print("Sample Predictions:")
        print(y_pred[:5])

    # Correlation matrices
    metric_corr_matrix = df_metrics.corr()
    groups_corr_matrix = df_groups.corr()
    sub_modules_corr_matrix = df_sub_modules.corr()

    print("Metrics Correlation Matrix:")
    print(metric_corr_matrix)
    print("Groups Correlation Matrix:")
    print(groups_corr_matrix)
    print("Sub_modules Correlation Matrix:")
    print(sub_modules_corr_matrix)

    # Save correlation report - top-N by |correlation| instead of the full
    # matrix dump (see write_top_correlations's module-level comment).
    with open(output_report_file, 'w') as f:
        f.write("Correlation Report (top pairs by |correlation|; full matrices are still\n")
        f.write("used internally for CHAID risk binning - see chaid_risk_segmentation_report)\n")
        write_top_correlations(f, "Metrics", metric_corr_matrix, metric_lookup)
        write_top_correlations(f, "Groups", groups_corr_matrix, group_lookup)
        write_top_correlations(f, "Sub_Modules", sub_modules_corr_matrix, sub_lookup)
    print(f"Correlation report saved to {output_report_file}")

    # Datasets dictionary
    datasets = {
        'Metrics': df_metrics,
        'Groups': df_groups,
        'Sub_Modules': df_sub_modules
    }
    corr_matrices = {
        'Metrics': (metric_corr_matrix, df_metrics),
        'Groups': (groups_corr_matrix, df_groups),
        'Sub_Modules': (sub_modules_corr_matrix, df_sub_modules)
    }

    # Trends & Fourier
    # Captured per dataset: the CHAID step below needs the Metrics entries
    # specifically, not whichever iteration finished last.
    trends_by_dataset = {}
    repetitions_by_dataset = {}
    with open(trends_file, 'w') as f:
        for name, df in datasets.items():
            f.write(f"\n{name} Trends:\n")
            trends = identify_trends(df)
            trends_by_dataset[name] = trends
            for var, trend in trends.items():
                f.write(f"{var}: {trend}\n")
            f.write(f"\n{name} Repetitions (Fourier Analysis):\n")
            repetitions = assess_repetition_with_fourier(df)
            repetitions_by_dataset[name] = repetitions
            for var, rep in repetitions.items():
                f.write(f"{var}: {rep}\n")
    print(f"Trends and repetitions report saved to {trends_file}")

    # Inconsistencies - with names and table format
    has_any_inconsistencies = False
    inconsistencies_by_dataset = {}
    with open(inconsistencies_file, 'w') as f:
        f.write("Inconsistencies Analysis Report\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for name, (corr_matrix, df) in corr_matrices.items():
            if corr_matrix.empty or df.empty:
                f.write(f"\n{name}: No data available for analysis.\n")
                continue
            dep_inc, ind_inc = detect_inconsistencies(corr_matrix, df)
            inconsistencies_by_dataset[name] = (dep_inc, ind_inc)

            # Dependent Inconsistencies Table
            f.write(f"\n{name} Dependent Inconsistencies:\n")
            if dep_inc:
                has_any_inconsistencies = True
            write_inconsistency_table(f, dep_inc, metric_lookup)

            # Independent Inconsistencies Table
            f.write(f"\n{name} Independent Inconsistencies:\n")
            if ind_inc:
                has_any_inconsistencies = True
            write_inconsistency_table(f, ind_inc, metric_lookup)

        if not has_any_inconsistencies:
            f.write("\nSummary: No inconsistencies found across all datasets. Data parsing and analysis completed successfully.\n")

    file_size = os.path.getsize(inconsistencies_file) / 1024
    print(f"Inconsistencies report saved to {inconsistencies_file} (size: {file_size:.2f} KB)")

    # CHAID Analysis with high-risk summary table including names
    chaid_report_file = 'chaid_risk_segmentation_report_enterprise.txt'
    # CHAID bins metrics against metric_corr_matrix, so it must be fed the
    # METRIC-level trend/repetition/inconsistency results. These names used to be
    # whatever the two loops above happened to leave behind - the Sub_Modules
    # iteration - so every trends.get(metric) lookup missed, and each metric was
    # binned from defaults ("Unknown" / "Insufficient" / zero inconsistencies).
    # The segmentation was therefore computed from placeholders, not analysis.
    metric_trends = trends_by_dataset.get('Metrics', {})
    metric_repetitions = repetitions_by_dataset.get('Metrics', {})
    metric_dep_inc, metric_ind_inc = inconsistencies_by_dataset.get('Metrics', ({}, {}))
    chaid_df = bin_features(metric_trends, metric_repetitions, metric_dep_inc, metric_ind_inc, metric_corr_matrix)
    indep_vars = ['Trend', 'Repetition', 'Avg_Correlation', 'Inconsistency_Level']
    dep_var = 'Risk_Level'

    try:
        tree = Tree.from_pandas_df(
            chaid_df,
            dict(zip(indep_vars, ['nominal'] * len(indep_vars))),
            dep_var,
            min_child_node_size=5,
            max_depth=3
        )
        with open(chaid_report_file, 'w') as f:
            f.write("CHAID Risk Segmentation Report\n")
            f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("CHAID Tree Summary:\n")
            f.write(str(tree))
            f.write("\n\n")

            # High-Risk Metrics Summary Table with IDs + Names
            f.write("High-Risk Metrics Summary (Critical + High):\n")
            high_risk = chaid_df[chaid_df['Risk_Level'].isin(['Critical', 'High'])]
            if high_risk.empty:
                f.write("None found.\n")
            else:
                f.write("Metric ID | Metric Name | Risk Level | Trend | Repetition | Avg Correlation | Inconsistency Level\n")
                f.write("-" * 100 + "\n")
                for _, row in high_risk.iterrows():
                    met_id = row['Metric']
                    met_name = metric_lookup.get(met_id, met_id)
                    f.write(f"{met_id} | {met_name} | {row['Risk_Level']} | {row['Trend']} | "
                            f"{row['Repetition']} | {row['Avg_Correlation']} | {row['Inconsistency_Level']}\n")

        print(f"CHAID report saved to {chaid_report_file}")

    except Exception as e:
        print(f"CHAID analysis skipped due to error: {e}")
        with open(chaid_report_file, 'w') as f:
            f.write("CHAID Risk Segmentation Report\n")
            f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"CHAID analysis could not be performed: {e}\n")

# -----------------------------
# 3. Run the script
# -----------------------------
if __name__ == "__main__":
    metrics_csv_file_path = 'filtered_metrics_data_enterprise.csv'
    group_csv_file_path = 'filtered_groups_data_enterprise.csv'
    sub_module_csv_file_path = 'filtered_sub_modules_data_enterprise.csv'
   
    main(metrics_csv_file_path, group_csv_file_path, sub_module_csv_file_path)
    # app.run(debug=True)  # DISABLED: Flask dev server blocked batch runs (never exits). All outputs are written above this line.

    ## This is the baseline version of the code updated with FT, CHAID analysis. 24/01/2026
    ## After L0 this is updated for 'Enterprise' module in version 8.0 and adapted for all other modules from hereon. 24/01/2026
    ## Supercedes all versions of AI_Ready_Correlation_Analysis_Enterprise.py files.