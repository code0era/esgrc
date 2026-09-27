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
from CHAID import Tree  # Assuming CHAID is installed
import graphviz  # For visualizing the CHAID tree

# -----------------------------
# Report-size guard for the L0 roll-up.
#
# The same top-N-at-write-time trim already applied to every module-level
# Correlation_CHAID_FT_Analysis_*.py, which was never applied here. It did not
# matter while Apex only had 3 modules to roll up: the 2026-08-04 live run sent
# 75,515 input tokens, comfortably under the 190,000 hard limit in
# pipeline/llm/guard.py.
#
# Measured 2026-08-07 against all 12 module handoffs, the payload is ~1,999,019
# characters, roughly 909,000 tokens, which is 4.8x the hard limit. The guard
# would silently truncate about four fifths of the enterprise report before
# Claude ever saw it. Two files were 98% of it: inconsistency_report_L0.txt at
# 1,343,162 bytes and correlation_analysis_L0.txt at 617,972.
#
# The cause is O(n^2): both reports scale with the square of the column count,
# and the column count grew with every module added. 3 modules to 11 in two days
# is what pushed it over.
#
# This changes ONLY what is written to the report files. The full correlation
# matrix and the full inconsistency dictionaries are still computed and are
# still passed to bin_features() unchanged, so CHAID segmentation is unaffected.
# -----------------------------
CORRELATION_THRESHOLD = 0.5  # matches detect_inconsistencies's corr_threshold
CORRELATION_TOP_N = 150
INCONSISTENCY_TOP_N = 30


def write_top_correlations(f, name, corr_matrix):
    """Write a top-N-by-|correlation| pair table instead of the full matrix."""
    cols = list(corr_matrix.columns)
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            corr = corr_matrix.loc[c1, c2]
            if pd.isna(corr):
                continue
            pairs.append((c1, c2, corr))

    total_pairs = len(pairs)
    above = [p for p in pairs if abs(p[2]) >= CORRELATION_THRESHOLD]
    mean_abs = (sum(abs(p[2]) for p in pairs) / total_pairs) if total_pairs else 0.0

    f.write(f"\n{name} Correlation Summary\n")
    f.write(f"Total pairs examined: {total_pairs}\n")
    f.write(f"Pairs with |correlation| >= {CORRELATION_THRESHOLD}: {len(above)}\n")
    f.write(f"Mean |correlation|: {mean_abs:.4f}\n")

    shown = sorted(above, key=lambda p: abs(p[2]), reverse=True)[:CORRELATION_TOP_N]
    if not shown:
        # Nothing cleared the threshold - show the strongest anyway, so a weakly
        # correlated enterprise is not reported as if it had no data at all.
        shown = sorted(pairs, key=lambda p: abs(p[2]), reverse=True)[:CORRELATION_TOP_N]
        f.write(f"\nNo pairs met the threshold - showing top {len(shown)} by |correlation| anyway:\n")
    else:
        f.write(f"\nTop {len(shown)} pairs by |correlation| (descending):\n")

    f.write("Entity 1 | Entity 2 | Correlation\n")
    f.write("-" * 60 + "\n")
    for c1, c2, corr in shown:
        f.write(f"{c1} | {c2} | {corr:.4f}\n")


def write_inconsistency_table(f, inc_dict):
    """Write up to INCONSISTENCY_TOP_N rows ranked by percentage (severity),
    instead of every pair the O(n^2) scan flagged."""
    if not inc_dict:
        f.write("None found.\n")
        return
    ranked = sorted(inc_dict.items(), key=lambda kv: kv[1]["percentage"], reverse=True)
    shown = ranked[:INCONSISTENCY_TOP_N]
    f.write(f"Total flagged: {len(inc_dict)}. Showing top {len(shown)} by severity.\n")
    f.write("Pair | Correlation | Count | Percentage | Points\n")
    f.write("-" * 76 + "\n")
    for pair, info in shown:
        f.write(
            f"{pair} | {info['correlation']:.2f} | {info['count']} | "
            f"{info['percentage']:.2f}% | {info['min_len']}\n"
        )


# -----------------------------
# 1. Define ALL functions FIRST
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
        # Trend bin
        trend = trends.get(metric, "Unknown")
        trend_bin = trend
        
        # Repetition bin
        rep = repetitions.get(metric, "Unknown")
        if "repetitive" in str(rep).lower():
            rep_bin = "Repetitive"
        elif "instability" in str(rep).lower():
            rep_bin = "Irregular"
        else:
            rep_bin = "Insufficient"
        
        # Average absolute correlation
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
        
        # Inconsistencies count
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
        
        # More granular Risk Level logic to create variation
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
        
        domain = metric[:3] if len(metric) > 3 else "Unknown"
        
        data.append({
            'Metric': metric,
            'Domain': domain,
            'Trend': trend_bin,
            'Repetition': rep_bin,
            'Avg_Correlation': corr_bin,
            'Inconsistency_Level': inc_bin,
            'Risk_Level': risk_level
        })
    
    df_chaid = pd.DataFrame(data)
    
    # Fill NaNs
    df_chaid = df_chaid.fillna({
        'Trend': 'Unknown',
        'Repetition': 'Insufficient',
        'Avg_Correlation': 'Low',
        'Inconsistency_Level': 'Low',
        'Risk_Level': 'Moderate'
    })
    
    # Debug print
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
# 2. Complete main() function - CONSOLIDATED (L0) VERSION with CHAID
# -----------------------------
###------------------
def main(all_modules_csv_path):
    # Seed torch before any weight init / DataLoader shuffling so
    # train_nn_model's CorrelationNN weights and batch order are
    # reproducible run-to-run on identical input (mirrors the
    # ANALYTICS_SEED convention used for the numpy draws elsewhere in
    # Apex's ML scripts).
    torch.manual_seed(int(os.environ.get("ANALYTICS_SEED", "42")))

    # Load the single consolidated file
    all_data = load_csv_file(all_modules_csv_path)
    
    # Extract numeric metrics
    metrics = extract_metrics_from_data(all_data)
    
    # Create and clean the unified DataFrame
    df_all = pd.DataFrame(metrics).dropna(axis=1, how='all')
    
    # Normalize
    df_all = normalize_data(df_all)
    
    # === NEW: Clean df_all to avoid NaNs in predictions ===
    df_all_clean = df_all.dropna(axis=1, how='all')                 # Remove fully NaN columns
    df_all_clean = df_all_clean.fillna(0)                           # Fill remaining NaNs with 0 (or use df_all_clean.mean() for mean imputation)
    
    # === Define all file names here (this fixes the NameError) ===
    correlation_report_file = 'correlation_analysis_L0.txt'
    trends_file = 'trends_and_repetitions_report_L0.txt'
    inconsistencies_file = 'inconsistency_report_L0.txt'
    chaid_report_file = 'chaid_risk_segmentation_L0.txt'
    
    # Train model on cleaned data
    input_dim = df_all_clean.shape[1]
    global model
    model = train_nn_model(df_all_clean, input_dim)
    torch.save(model.state_dict(), 'correlation_model_L0.pth')
    
    # Model evaluation
    model.eval()
    with torch.no_grad():
        X_tensor = torch.tensor(df_all_clean.values, dtype=torch.float32)
        y_pred = model(X_tensor).numpy()
        print("Sample Predictions (L0 - cleaned):")
        print(y_pred[:5])
    
    # ... (rest of your code: correlation matrix calculation, saving reports, trends, repetitions, inconsistencies, CHAID)
###------------------

    # Correlation matrix (single consolidated)
    corr_matrix_all = df_all.corr()
    print("Consolidated Correlation Matrix (L0):")
    print(corr_matrix_all)

    # Save correlation report. Was `corr_matrix_all.to_csv(f)`, the full n x n
    # matrix, which reached 617,972 bytes at 12 modules. The matrix itself is
    # unchanged and still feeds bin_features below.
    with open(correlation_report_file, 'w') as f:
        f.write("Consolidated Enterprise Correlation Matrix (All 12 Domains - L0)\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        write_top_correlations(f, "Enterprise (L0)", corr_matrix_all)
    print(f"Correlation report saved to {correlation_report_file}")
##-----------------------------------------------------------------------
    # Calculate trends and repetitions FIRST
    trends = identify_trends(df_all)
    repetitions = assess_repetition_with_fourier(df_all)

    # Save trends & repetitions report
    with open(trends_file, 'w') as f:
        f.write("Consolidated Enterprise Trends & Repetitions (All 12 Domains - L0)\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("\nTrends:\n")
        for var, trend in trends.items():
            f.write(f"{var}: {trend}\n")

        f.write("\nRepetitions (Fourier Analysis):\n")
        for var, rep in repetitions.items():
            f.write(f"{var}: {rep}\n")
    print(f"Trends and repetitions report saved to {trends_file}")

    # Calculate inconsistencies. Was called twice here (once against df_all,
    # immediately discarded and recomputed against df_all_clean) - only the
    # df_all_clean result was ever used below, so the first call was wasted
    # compute (an O(n^2) scan over the correlation matrix).
    dep_inc, ind_inc = detect_inconsistencies(corr_matrix_all, df_all_clean)  # Use cleaned data for consistency

    # Save inconsistencies report
    has_any_inconsistencies = False
    with open(inconsistencies_file, 'w') as f:
        f.write("Inconsistencies Analysis Report (All 12 Domains - L0)\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if corr_matrix_all.empty or df_all_clean.empty:
            f.write("No data available for analysis.\n")
        else:
            # Was a full dump of every flagged pair, which reached 1,343,162
            # bytes at 12 modules. Now top-N by severity. dep_inc / ind_inc
            # themselves are untouched and still feed bin_features below.
            f.write("\nDependent Inconsistencies:\n")
            if dep_inc:
                has_any_inconsistencies = True
            write_inconsistency_table(f, dep_inc)

            f.write("\nIndependent Inconsistencies:\n")
            if ind_inc:
                has_any_inconsistencies = True
            write_inconsistency_table(f, ind_inc)
        
        if not has_any_inconsistencies:
            f.write("\nSummary: No inconsistencies found across all domains. Analysis completed successfully.\n")

    file_size = os.path.getsize(inconsistencies_file) / 1024
    print(f"Inconsistency report saved to {inconsistencies_file} (size: {file_size:.2f} KB)")
##----------------------------
    # Now CHAID
    chaid_df = bin_features(trends, repetitions, dep_inc, ind_inc, corr_matrix_all)

    indep_vars = ['Domain', 'Trend', 'Repetition', 'Avg_Correlation', 'Inconsistency_Level']
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
            f.write("CHAID Risk Segmentation Report (All 12 Domains - L0)\n")
            f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("CHAID Tree Summary:\n")
            f.write(str(tree))

        print(f"CHAID report saved to {chaid_report_file}")

    except Exception as e:
        print(f"CHAID analysis skipped due to error: {e}")
        with open(chaid_report_file, 'w') as f:
            f.write("CHAID Risk Segmentation Report (All 12 Domains - L0)\n")
            f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"CHAID analysis could not be performed: {e}\n")
##-----------------------------------------------------------
# -----------------------------
# 3. Run the script
# -----------------------------
if __name__ == "__main__":
    all_modules_csv_path = 'all_module_values.csv'  # Your single consolidated input file
    
    main(all_modules_csv_path)
    # app.run(debug=True)  # DISABLED: Flask dev server blocked batch runs (never exits). All outputs are written above this line.
    
    ## AI_Ready_Correlation_Analysis_L0_05.py was upgraded with CHAID analysis to do segmentation of Risk at L0 level.