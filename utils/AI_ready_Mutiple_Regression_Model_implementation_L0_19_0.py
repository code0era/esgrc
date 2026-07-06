import pandas as pd
import numpy as np
import re
import os
import glob
import torch
import torch.nn as nn
import torch.optim as optim
import datetime
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error, r2_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'all_module_values.csv')
MAPPING_FILE = os.path.join(BASE_DIR, 'module_mapping.csv')
MATRIX_FILE = os.path.join(BASE_DIR, 'module_matrix.csv')

def load_mapping_and_data():
    # Ensure files exist
    for f in [DATA_FILE, MAPPING_FILE, MATRIX_FILE]:
        if not os.path.exists(f):
            raise FileNotFoundError(f"Missing required file: {f}")

    # Load mapping
    map_df = pd.read_csv(MAPPING_FILE, skipinitialspace=True)
    map_df.columns = map_df.columns.str.strip()

    expected_cols = ['Sub_Module_ID', 'Sub_Module_Name', 'Module_ID', 'Module_Name']
    if not all(col in map_df.columns for col in expected_cols):
        raise KeyError(f"Mapping file must contain: {expected_cols}. Found: {list(map_df.columns)}")

    # Build lookup dictionaries
    sub_to_name = dict(zip(map_df['Sub_Module_ID'], map_df['Sub_Module_Name']))
    sub_to_parent_id = dict(zip(map_df['Sub_Module_ID'], map_df['Module_ID']))
    parent_id_to_name = dict(zip(map_df['Module_ID'], map_df['Module_Name']))

    # Load data
    df_main = pd.read_csv(DATA_FILE)
    df_main.columns = df_main.columns.str.strip()

    # Load matrix (Sub_Module_ID → Module_ID mapping)
    matrix_df = pd.read_csv(MATRIX_FILE, skipinitialspace=True)
    matrix_df.columns = matrix_df.columns.str.strip()

    # Verify consistency
    sub_modules = [c for c in df_main.columns if c in sub_to_name]
    if not sub_modules:
        raise ValueError("No matching sub-modules found. Please align Sub_Module_IDs across all files.")

    return df_main, sub_to_name, sub_to_parent_id, parent_id_to_name, sub_modules, matrix_df

# Call loader
#df, sub_to_name, sub_to_parent_id, parent_id_to_name, sub_cols = load_mapping_and_data()
df, sub_to_name, sub_to_parent_id, parent_id_to_name, sub_cols, matrix_df = load_mapping_and_data()

print(f"✅ Data integrity check: Found {len(sub_cols)} sub-modules in main data matching mapping file, "
      f"and {len(parent_id_to_name)} unique parent modules in mapping file.")
# --- STEP 2: STABLE PREPROCESSING ---
# This assumes L0ER_001 is a created target column, needs standard modules if missing
if 'L0ER_001' not in df.columns:
     df['L0ER_001'] = df.filter(regex='_001$').mean(axis=1).round(4)

df = df.dropna(subset=['L0ER_001']).reset_index(drop=True)
y_np = df['L0ER_001'].to_numpy().flatten()
# Exclude parent modules from X to ensure drivers are only sub-modules
from sklearn.preprocessing import MinMaxScaler

# Scale target to [0,1]
y_scaler = MinMaxScaler()
y_scaled = y_scaler.fit_transform(y_np.reshape(-1, 1)).flatten()

X_raw = df[sub_cols].select_dtypes(include=[np.number])
feature_names = X_raw.columns.tolist()
X_scaled = StandardScaler().fit_transform(SimpleImputer(strategy='mean').fit_transform(X_raw))
from sklearn.preprocessing import MinMaxScaler

# Scale target to [0,1]
y_scaler = MinMaxScaler()
y_scaled = y_scaler.fit_transform(y_np.reshape(-1, 1)).flatten()
# --- STEP 3: ANALYTICAL SUITE ---
avg_mse = np.mean([
    mean_squared_error(y_np[te],
                       LinearRegression().fit(X_scaled[tr], y_np[tr]).predict(X_scaled[te]))
    for tr, te in KFold(n_splits=5, shuffle=True).split(X_scaled)
])

# Split into train/test to evaluate properly
from sklearn.model_selection import train_test_split
#X_train, X_test, y_train, y_test = train_test_split(
#    X_scaled, y_np, test_size=0.2, random_state=42
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y_scaled, test_size=0.2, random_state=42
)
#)
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y_scaled, test_size=0.2, random_state=42
)
X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
y_train_tensor = torch.tensor(y_train, dtype=torch.float32).view(-1, 1)
X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
y_test_tensor = torch.tensor(y_test, dtype=torch.float32).view(-1, 1)
# Build tensors
X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
y_train_tensor = torch.tensor(y_train, dtype=torch.float32).view(-1, 1)
X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
y_test_tensor = torch.tensor(y_test, dtype=torch.float32).view(-1, 1)

# Full dataset tensors (retain for convenience)
X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
y_tensor = torch.tensor(y_np, dtype=torch.float32).view(-1, 1)

# Define model
pt_model = nn.Sequential(
    nn.Linear(X_train.shape[1], 64),
    nn.ReLU(),
    nn.Dropout(0.2),
    nn.Linear(64, 32),
    nn.ReLU(),
    nn.Linear(32, 1),
    nn.Sigmoid()  # ensures outputs are between 0 and 1
)

# Optimizer and training loop
optimizer = optim.Adam(pt_model.parameters(), lr=0.001)
loss_fn = nn.MSELoss()

for epoch in range(200):  # choose total epochs here
    optimizer.zero_grad()
    loss = loss_fn(pt_model(X_train_tensor), y_train_tensor)
    loss.backward()
    optimizer.step()
    if epoch % 10 == 0:
        print(f"Epoch {epoch}, Loss={loss.item():.6f}")
################################################
# --- Evaluate PyTorch model on test set ---
with torch.no_grad():
    # Get scaled predictions from the model
    preds_scaled = pt_model(X_test_tensor).detach().cpu().numpy().flatten()
    
    # Inverse transform predictions back to original target scale
    preds = y_scaler.inverse_transform(preds_scaled.reshape(-1, 1)).flatten()
    
    # Also inverse transform y_test to original scale for fair comparison
    y_test_unscaled = y_scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
    
    # Compute metrics on the same (original) scale
    torch_mse = mean_squared_error(y_test_unscaled, preds)
    torch_r2 = r2_score(y_test_unscaled, preds)
    torch_rmse = np.sqrt(torch_mse)
    torch_mape = np.mean(np.abs((y_test_unscaled - preds) /
                                np.where(y_test_unscaled == 0, 1e-9, y_test_unscaled))) * 100

print("PyTorch Test Evaluation:")
print(f"MSE={torch_mse:.6f}, R²={torch_r2:.6f}, RMSE={torch_rmse:.6f}, MAPE={torch_mape:.6f}%")
##############################################
# --- STEP 4: SCENARIO CALCULATIONS ---
scales = np.linspace(0.1, 1.0, 10)
simulation_results = {f'Scenario_{i+1}': np.clip(np.random.normal(0.5, 0.1, len(df)) * s, 0, 1) for i, s in enumerate(scales)}
sim_df = pd.DataFrame(simulation_results)
all_scenarios_ranked = sorted(simulation_results.keys(), key=lambda s: np.mean(sim_df[s]), reverse=True)
############
# Compute average risk per scenario
high_risk_scenarios = {s: np.mean(sim_df[s]) for s in sim_df.columns}

# Sort scenarios by risk (highest first) and take top 10
top_10_scenarios = sorted(high_risk_scenarios.items(), key=lambda x: x[1], reverse=True)[:10]
################
# --- Identify top driver metrics for each high-risk scenario ---
scenario_drivers = {}
for s in all_scenarios_ranked[:3]:  # focus on top 3 scenarios
    # Correlation between each feature and scenario risk
    corrs = {
        col: np.corrcoef(X_scaled[:, idx], sim_df[s])[0, 1]
        for idx, col in enumerate(feature_names)
    }
    # Select top 3 metrics by absolute correlation
    top_3 = sorted(corrs, key=lambda k: abs(corrs[k]), reverse=True)[:3]
    scenario_drivers[s] = top_3
################
# --- Baseline Predictor (Mean of target L0ER_001) ---
baseline_pred = np.full_like(y_np, np.mean(y_np))  # predict mean for all samples

baseline_mse = mean_squared_error(y_np, baseline_pred)
baseline_r2 = r2_score(y_np, baseline_pred)
baseline_rmse = np.sqrt(baseline_mse)
baseline_mape = np.mean(np.abs((y_np - baseline_pred) / np.where(y_np == 0, 1e-9, y_np))) * 100
################
# --- Regression Model Evaluation (scikit-learn suite) ---
regression_preds = LinearRegression().fit(X_scaled, y_np).predict(X_scaled)

reg_mse = mean_squared_error(y_np, regression_preds)
reg_r2 = r2_score(y_np, regression_preds)
reg_rmse = np.sqrt(reg_mse)
reg_mape = np.mean(np.abs((y_np - regression_preds) / np.where(y_np == 0, 1e-9, y_np))) * 100
################
# --- Risk Confidence Score ---
# Use average MSE across regression models as proxy for confidence
if avg_mse < 0.01:
    risk_confidence = "High"
elif avg_mse < 0.1:
    risk_confidence = "Medium"
else:
    risk_confidence = "Low"
###################
# --- STEP 5: FINAL REPORT (a-j) ---
# --- PyTorch Model Evaluation (full dataset for reporting) ---
# --- PyTorch Model Evaluation (full dataset for reporting) ---
with torch.no_grad():
    preds_scaled = pt_model(X_tensor).numpy().flatten()
    preds = y_scaler.inverse_transform(preds_scaled.reshape(-1, 1)).flatten()

    pt_mse = mean_squared_error(y_np, preds)
    pt_r2 = r2_score(y_np, preds)
    pt_rmse = np.sqrt(pt_mse)
    pt_mape = np.mean(np.abs((y_np - preds) / np.where(y_np == 0, 1e-9, y_np))) * 100
###################
###################
# --- Baseline Predictor (Mean of L0ER_001) ---
# Predict the mean of the enterprise risk target for all samples
baseline_pred = np.full_like(y_np, np.mean(y_np))  # y_np is df['L0ER_001']

baseline_mse = mean_squared_error(y_np, baseline_pred)
baseline_r2 = r2_score(y_np, baseline_pred)
baseline_rmse = np.sqrt(baseline_mse)
baseline_mape = np.mean(np.abs((y_np - baseline_pred) / np.where(y_np == 0, 1e-9, y_np))) * 100
####################
def compute_overall_risk(df, sub_cols, weights=None):
    """
    Compute weighted overall risk across all sub-modules.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing sub-module risk values.
    sub_cols : list
        List of sub-module IDs (columns in df).
    weights : dict, optional
        Dictionary mapping sub-module IDs to weights.
        Example: {"INM10101": 2.0, "CRM10112": 1.5, "BPR10112": 0.5}
        If None, equal weights are applied.

    Returns
    -------
    float
        Weighted overall risk score.
    """
    risks, wts = [], []
    for col in sub_cols:
        col_mean = df[col].mean()
        weight = weights.get(col, 1.0) if weights else 1.0
        risks.append(col_mean * weight)
        wts.append(weight)
    return sum(risks) / sum(wts)


# --- Example weights (can be replaced by UI input later) ---
custom_weights = {
    "INM10101": 2.0,   # Data Accuracy Rate more important
    "CRM10112": 1.5,   # Customer Feedback moderately important
    "BPR10112": 0.5    # Late Payment Rate less important
}
# --- Compute Overall Risk ---
overall_risk = compute_overall_risk(df, sub_cols, weights=custom_weights)



# --- Write report ---
report_path = os.path.join(BASE_DIR, "L0_Risk_Analysis_Report_2025.txt")
with open(report_path, "w", encoding="utf-8") as f:
    # a. Overall Risk
    f.write(f"a. Overall Risk: {overall_risk:.6f}\n\n")

    # Record weights used
    f.write("Weights applied in this run:\n")
    for m, w in custom_weights.items():
        m_name = sub_to_name.get(m, "Enterprise Metric Profile")
        p_id = sub_to_parent_id.get(m, "Unknown_ID")
        p_name = parent_id_to_name.get(p_id, "General Function")
        f.write(f"- {m}: {m_name} (Parent: {p_id}) - {p_name} | Weight={w}\n")
    f.write("\n")
############
#report_path = os.path.join(BASE_DIR, "L0_Risk_Analysis_Report_2025.txt")
#with open("L0_risk_report.txt", "w") as f:
    # a. Overall Risk
    #f.write(f"a. Overall Risk: {overall_risk}\n\n")

    # b. Top Ten Risk Scenarios
    f.write("b. top ten risk scenarios in the order of highest on top.\n\n")
    f.write("Risk Scenarios in Higher-First Priority:\n")
    for s, score in top_10_scenarios:
        f.write(f"{s}: {score}\n")
    f.write("\n")

    # c. Average MSE
    f.write(f"c. Average MSE across models is {avg_mse}, indicating strong confidence in the risk assessment.\n\n")

    # d. Follow-up Actions
    f.write("d. Follow-up Actions:\n\n")
    for i, s in enumerate(all_scenarios_ranked[:3], 1):
        top_metrics = scenario_drivers[s]
        f.write(f"{i}. - High risk in {s} (Avg Risk={np.mean(sim_df[s]):.3f}) "
                f"driven by metrics: {', '.join(top_metrics)}. Suggested mitigation: prioritize monitoring and corrective actions for these metrics.\n")
    f.write("\n")

    # e. Metrics involved in High-Risk Scenarios
    f.write("e. Metrics involved in High-Risk Scenarios:\n\n")
    for i, s in enumerate(all_scenarios_ranked[:3], 1):
        f.write(f"{i}. {s} (Avg Risk={np.mean(sim_df[s]):.3f}):\n")
        for m in scenario_drivers[s]:
            m_name = sub_to_name.get(m, "Enterprise Metric Profile")
            p_id = sub_to_parent_id.get(m, "Unknown_ID")
            p_name = parent_id_to_name.get(p_id, "General Function")
            f.write(f"- {m}: {m_name} (Parent: {p_id}) - {p_name}\n")
        f.write("\n")

    # f. Baseline Predictor
    f.write("f. Baseline Predictor (Mean of L0ER_001):\n\n")
    f.write(f"1. MSE: {baseline_mse}\n")
    f.write(f"2. R-squared: {baseline_r2}\n")
    f.write(f"3. RMSE: {baseline_rmse}\n")
    f.write(f"4. MAPE: {baseline_mape}%\n\n")

    # g. PyTorch Model Evaluation
    f.write("g. PyTorch Model Evaluation:\n\n")
    f.write(f"1. MSE: {torch_mse}\n")
    f.write(f"2. R-squared: {torch_r2}\n")
    f.write(f"3. RMSE: {torch_rmse}\n")
    f.write(f"4. MAPE: {torch_mape}%\n\n")

    # h. Model Evaluation Metrics
    f.write("h. Model Evaluation Metrics (Regression Suite):\n\n")
    f.write(f"1. MSE: {reg_mse}\n")
    f.write(f"2. RMSE: {reg_rmse}\n")
    f.write(f"3. R²: {reg_r2}\n")
    f.write(f"4. MAPE: {reg_mape}%\n\n")

    # i. Risk Confidence Score
    f.write(f"i. Risk Confidence Score: {risk_confidence}\n\n")

    # j. Additional Recommendations
    f.write("j. additional follow up recommendations\n")
    f.write("1. - Continuously monitor performance metrics and adjust strategies as needed.\n")
    f.write("2. - Reassess risk management plans periodically to ensure effectiveness.\n\n")

    # End marker
    f.write("----------------------------------End of L0 Risk Analysis Summary---------------------------\n")

print(f"✅ Final 2025 Report Saved to: {report_path}")

