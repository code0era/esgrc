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

    # Save correlation report
    with open(correlation_report_file, 'w') as f:
        f.write("Consolidated Enterprise Correlation Matrix (All 12 Domains - L0)\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        corr_matrix_all.to_csv(f)
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

    # Calculate inconsistencies
    dep_inc, ind_inc = detect_inconsistencies(corr_matrix_all, df_all)

    # Save inconsistencies report (your existing code here, unchanged)
    # ... (keep your original inconsistencies saving block)
##----------------------------
    # Calculate inconsistencies
    dep_inc, ind_inc = detect_inconsistencies(corr_matrix_all, df_all_clean)  # Use cleaned data for consistency

    # Save inconsistencies report
    has_any_inconsistencies = False
    with open(inconsistencies_file, 'w') as f:
        f.write("Inconsistencies Analysis Report (All 12 Domains - L0)\n")
        f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if corr_matrix_all.empty or df_all_clean.empty:
            f.write("No data available for analysis.\n")
        else:
            f.write("\nDependent Inconsistencies:\n")
            if not dep_inc:
                f.write("None found.\n")
            else:
                has_any_inconsistencies = True
                for pair, info in dep_inc.items():
                    f.write(f"{pair}: Correlation={info['correlation']:.2f}, Count={info['count']}, Percentage={info['percentage']:.2f}% (over {info['min_len']} points)\n")
            
            f.write("\nIndependent Inconsistencies:\n")
            if not ind_inc:
                f.write("None found.\n")
            else:
                has_any_inconsistencies = True
                for pair, info in ind_inc.items():
                    f.write(f"{pair}: Correlation={info['correlation']:.2f}, Count={info['count']}, Percentage={info['percentage']:.2f}% (over {info['min_len']} points)\n")
        
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
    app.run(debug=True)
    
    ## AI_Ready_Correlation_Analysis_L0_05.py was upgraded with CHAID analysis to do segmentation of Risk at L0 level.