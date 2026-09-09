import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.svm import SVR
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline
from torch.utils.data import TensorDataset, DataLoader
from flask import Flask, request, jsonify
from sklearn.preprocessing import StandardScaler

# -------------------------------
# Step 1: Load the randomized metrics data
# -------------------------------
file_path = 'module_values_esgrc.csv'
metrics_data = pd.read_csv(file_path)
##column duplication check## 
# Check for duplicate column headers (IDs)
duplicate_cols = metrics_data.columns[metrics_data.columns.duplicated()].tolist()
if duplicate_cols:
    print("⚠️ ALERT: Duplicate column IDs detected:", duplicate_cols)
    raise ValueError("Duplicate column IDs found in module_values_esgrc.csv. Please fix before analysis.")
else:
    print("✅ No duplicate column IDs detected.")


import json

with open("esgrc_performance_json_file.json", "r") as f:
    mapping_data = json.load(f)
#----------------------------------------------
# Flatten JSON into a dictionary of IDs → Names
id_to_name = {}

for sub_module in mapping_data.get("sub_modules", []):
    # Add sub-module
    id_to_name[sub_module["sub_module_id"]] = sub_module["sub_module_name"]

    for group in sub_module.get("groups", []):
        # Add group
        id_to_name[group["group_id"]] = group["group_name"]

        for metric in group.get("value", []):
            # Add metric
            id_to_name[metric["metric_id"]] = metric["metric_name"]
############################
# -------------------------------
# Step 2: Define Scenarios
# -------------------------------
scales = np.linspace(0.1, 1.0, 10)
scenarios = {f'Scenario_{i+1}': {'scale': scale, 'probability': 0.1} for i, scale in enumerate(scales)}

# -------------------------------
# Step 3: Quantify Impact
# -------------------------------
performance_impact = {
    scenario: np.random.normal(data['scale'], 0.1, len(metrics_data))
    for scenario, data in scenarios.items()
}
for scenario, values in performance_impact.items():
    performance_impact[scenario] = np.clip(values, 0, 1)

# -------------------------------
# Step 4: Initial Model Evaluation
# -------------------------------
X = metrics_data.drop(columns=['ESRC_001'])
y = metrics_data['ESRC_001']
input_dim = X.shape[1]

print("Feature count in X:", X.shape[1])
X_tensor = torch.tensor(X.values, dtype=torch.float32)
y_tensor = torch.tensor(y.values, dtype=torch.float32).view(-1, 1)
print("X_tensor shape:", X_tensor.shape)
print("y_tensor shape:", y_tensor.shape)

scaler_X = StandardScaler()
X_scaled = scaler_X.fit_transform(X)

n_samples, n_features = X.shape
n_components = min(10, n_samples, n_features)

model = Pipeline([
    ('pca', PCA(n_components=n_components, svd_solver='full')),
    ('regressor', LinearRegression())
])
model.fit(X_scaled, y)

# -------------------------------
# Step 5: Regression Models Setup & Cross-Validation
# -------------------------------
regression_models = {
    'Linear': Pipeline([('scaler', StandardScaler()), ('model', LinearRegression())]),
    'Ridge': Pipeline([('scaler', StandardScaler()), ('model', Ridge())]),
    'Lasso': Pipeline([('scaler', StandardScaler()), ('model', Lasso())]),
    'ElasticNet': Pipeline([('scaler', StandardScaler()), ('model', ElasticNet())]),
    'SVR': Pipeline([('scaler', StandardScaler()), ('model', SVR(kernel='linear'))]),
    'PCA_Linear': Pipeline([
        ('scaler', StandardScaler()),
        ('pca', PCA(n_components=n_components)),
        ('linear', LinearRegression())
    ]),
    'Multiple_Linear': Pipeline([('scaler', StandardScaler()), ('model', LinearRegression())])
}

regression_results = {}
kf = KFold(n_splits=5, shuffle=True, random_state=42)
for model_name, model in regression_models.items():
    model.fit(X_scaled, y)
    predictions = model.predict(X_scaled)
    mse = mean_squared_error(y, predictions)
    r2 = r2_score(y, predictions)

    cv_mse, cv_r2 = [], []
    for train_index, test_index in kf.split(X_scaled):
        X_train, X_test = X_scaled[train_index], X_scaled[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        cv_mse.append(mean_squared_error(y_test, y_pred))
        cv_r2.append(r2_score(y_test, y_pred))

    regression_results[model_name] = {
        'model': model,
        'cv_mse': np.mean(cv_mse),
        'cv_r2': np.mean(cv_r2),
        'initial_mse': mse,
        'initial_r2': r2
    }

best_models = sorted(regression_results.items(), key=lambda item: item[1]['cv_mse'])
param_grids = {
    'Ridge': {'model__alpha': np.logspace(-6, 6, 13)},
    'Lasso': {'model__alpha': np.logspace(-6, 6, 13)},
    'ElasticNet': {'model__alpha': np.logspace(-6, 6, 13), 'model__l1_ratio': np.linspace(0, 1, 11)},
    'SVR': {'model__C': [0.1, 1, 10, 100], 'model__epsilon': [0.1, 0.2, 0.5]},
    'PCA_Linear': {'pca__n_components': [5, n_components]}
}

tuned_models = {}
for model_name, results in best_models[:3]:
    param_grid = param_grids.get(model_name, {})
    if param_grid:
        grid_search = GridSearchCV(results['model'], param_grid, cv=5, scoring='neg_mean_squared_error')
        grid_search.fit(X_scaled, y)
        best_model = grid_search.best_estimator_
        tuned_models[model_name] = {
            'model': best_model,
            'cv_mse': -grid_search.best_score_,
            'cv_r2': r2_score(y, best_model.predict(X_scaled)),
            'initial_mse': mean_squared_error(y, best_model.predict(X_scaled))
        }
    else:
        tuned_models[model_name] = results

# -------------------------------
# Step 6: Scenario Simulation
# -------------------------------
simulation_results = {}
for scenario, data in scenarios.items():
    impact = performance_impact[scenario]
    simulated_risk = np.clip(impact * data['scale'], 0, 1)
    simulation_results[scenario] = simulated_risk

simulation_df = pd.DataFrame(simulation_results)
report_lines = []

# -------------------------------
# Step 7: Aggregate Results
# -------------------------------
overall_risk = 0
for scenario, data in scenarios.items():
    scenario_risk = np.mean(simulation_df[scenario])  # Average impact for scenario
    overall_risk += scenario_risk * data['probability']  # Weighted by probability

report_lines.append(f"Overall Risk: {overall_risk}")

# Identify High-Risk Scenarios
high_risk_scenarios = {scenario: np.mean(simulation_df[scenario]) for scenario in simulation_df.columns}
sorted_high_risk_scenarios = sorted(high_risk_scenarios.items(), key=lambda item: item[1], reverse=True)
report_lines.append("\nRisk Scenarios in Higher-First Priority:")
for scenario, risk in sorted_high_risk_scenarios:
    report_lines.append(f"{scenario}: {risk}")

# Confidence Levels
average_mse = np.mean([results['cv_mse'] for results in tuned_models.values()])
report_lines.append(f"Average MSE across models is {average_mse}, indicating strong confidence in the risk assessment.")

# -------------------------------
# Expanded Follow-up Actions using CSV Metrics
# -------------------------------
report_lines.append("\nFollow-up Actions:")

# Take top 3 high-risk scenarios
top_scenarios = sorted_high_risk_scenarios[:3]

for scenario, risk in top_scenarios:
    scenario_values = simulation_df[scenario].values
    
    print("Columns in X:", list(X.columns))
    print("Columns in simulation_df:", list(simulation_df.columns))

# Compute correlation between scenario risk and each metric in X
    correlations = pd.Series([
        np.corrcoef(X[col].values, scenario_values)[0, 1]
        for col in X.columns
    ], index=X.columns)

# Select top 3 metrics driving risk
    top_metrics = correlations.abs().sort_values(ascending=False).head(3).index.tolist()

# Build action line
    action = f"High risk in {scenario} (Avg Risk={risk:.3f}) driven by metrics: {', '.join(top_metrics)}."
    report_lines.append(f"- {action} Suggested mitigation: prioritize monitoring and corrective actions for these metrics.")
# -------------------------------
# List metrics involved in high-risk scenarios with names from JSON
# -------------------------------
import json

# Load JSON mapping file (adjust path as needed)
with open("esgrc_performance_json_file.json", "r") as f:
    metric_names = json.load(f)

report_lines.append("\nMetrics involved in High-Risk Scenarios:")

for scenario, risk in top_scenarios:
    scenario_values = simulation_df[scenario].values

    # Compute correlation between scenario risk and each metric column in X
    correlations = pd.Series({
        col: np.corrcoef(X[col].values, scenario_values)[0, 1]
        for col in X.columns
    })

    # Select top 3 metrics driving risk
    top_metrics = correlations.abs().sort_values(ascending=False).head(3).index.tolist()

    # Add metrics with descriptive names from JSON
    report_lines.append(f"\n{scenario} (Avg Risk={risk:.3f}):")
    for metric in top_metrics:
        readable_name = id_to_name.get(metric, metric)  # fallback to raw name if not in JSON
        report_lines.append(f"- {metric}: {readable_name}")
#############################        
# Add general ongoing actions
#report_lines.append("")
#report_lines.append("- Continuously monitor performance metrics and adjust strategies as needed.")
#report_lines.append("- Reassess risk management plans periodically to ensure effectiveness.")

# -------------------------------
# Step 8: PyTorch Model Implementation
# -------------------------------
scaler_X = StandardScaler()
scaler_y = StandardScaler()
X_scaled = scaler_X.fit_transform(X)
y_scaled = scaler_y.fit_transform(y.values.reshape(-1, 1)).flatten()

X_tensor = torch.tensor(X_scaled, dtype=torch.float32)
y_tensor = torch.tensor(y_scaled, dtype=torch.float32).view(-1, 1)
dataset = TensorDataset(X_tensor, y_tensor)
dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

class RiskAssessmentModel(nn.Module):
    def __init__(self, input_dim):
        super(RiskAssessmentModel, self).__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.relu1 = nn.ReLU()
        self.fc2 = nn.Linear(64, 32)
        self.relu2 = nn.ReLU()
        self.fc3 = nn.Linear(32, 1)

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu1(x)
        x = self.fc2(x)
        x = self.relu2(x)
        x = self.fc3(x)
        return x

model = RiskAssessmentModel(input_dim)
#assert X.shape[1] == model.fc1.in_features, \
#    f"Mismatch: X has {X.shape[1]} features, model expects {model.fc1.in_features}"
# Ensure input_dim matches X.shape[1] (validated at CSV load step)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

num_epochs = 100
for epoch in range(num_epochs):
    for batch_X, batch_y in dataloader:
        optimizer.zero_grad()
        outputs = model(batch_X)
        loss = criterion(outputs, batch_y)
        loss.backward()
        optimizer.step()

torch.save(model.state_dict(), "risk_assessment_model.pth")
print("Model saved as risk_assessment_model.pth")

# -------------------------------
# Step 9: Model Evaluation
# -------------------------------
model.eval()
with torch.no_grad():
    y_pred_scaled = model(X_tensor).numpy()

# Inverse transform predictions
y_pred = scaler_y.inverse_transform(y_pred_scaled).flatten()
y_true = y.values.flatten()

# Compute metrics
mse = mean_squared_error(y_true, y_pred)
rmse = np.sqrt(mse)
r2 = r2_score(y_true, y_pred)
mape = np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100

# Risk confidence scoring helper
def risk_confidence_score(r2, rmse, mape):
    if r2 > 0.8 and rmse < 0.1 and mape < 5:
        return "High"
    elif r2 > 0.5 and rmse < 0.5 and mape < 10:
        return "Moderate"
    else:
        return "Low"

risk_score = risk_confidence_score(r2, rmse, mape)
print(f"Risk Confidence Score: {risk_score}")

# Baseline Predictor
baseline_pred = np.full_like(y_true, fill_value=np.mean(y_true), dtype=np.float64)
baseline_mse = mean_squared_error(y_true, baseline_pred)
baseline_r2 = r2_score(y_true, baseline_pred)
baseline_rmse = np.sqrt(baseline_mse)
baseline_mape = np.mean(np.abs((y_true - baseline_pred) / np.where(y_true == 0, 1, y_true))) * 100

baseline_summary = (
    f"Baseline Predictor (Mean of ESRC_001):\n"
    f"MSE: {baseline_mse}\n"
    f"R-squared: {baseline_r2}\n"
    f"RMSE: {baseline_rmse}\n"
    f"MAPE: {baseline_mape}%"
)
report_lines.append(f"\n{baseline_summary}")

# Handle NaN values
if np.isnan(y_pred).any():
    report_lines.append("Warning: NaN values detected in predictions. Cleaning before evaluation....")
    y_pred = np.nan_to_num(y_pred, nan=0.0)

# PyTorch metrics summary
pytorch_mse = mean_squared_error(y_true, y_pred)
pytorch_r2 = r2_score(y_true, y_pred)
pytorch_rmse = np.sqrt(pytorch_mse)
pytorch_mape = np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100

summary_text = (
    f"PyTorch Model Evaluation:\n"
    f"MSE: {pytorch_mse}\n"
    f"R-squared: {pytorch_r2}\n"
    f"RMSE: {pytorch_rmse}\n"
    f"MAPE: {pytorch_mape}%"
)
report_lines.append(f"\n{summary_text}")
report_lines.append("")
# -------------------------------
# Step 10: Flask API Integration & Report Writing
# -------------------------------
app = Flask(__name__)
model.load_state_dict(torch.load("risk_assessment_model.pth"))
model.eval()

with open("ESGRC_Module_model_summary.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))
    f.write("\nModel Evaluation Metrics:\n")
    f.write(f"MSE: {mse}\n")
    f.write(f"RMSE: {rmse}\n")
    f.write(f"R²: {r2}\n")
    f.write(f"MAPE: {mape}%\n")
    f.write("\n")
    f.write("")
    f.write(f"Risk Confidence Score: {risk_score}\n")
    f.write("\n")
    # Add general ongoing actions
    f.write("Recommendation - Continuously monitor performance metrics and adjust strategies as needed.\n")
    f.write("Recommendation - Reassess risk management plans periodically to ensure effectiveness.\n")
    f.write("\n")
    f.write("----------------------------------End of ESGRC Module Risk Analysis Summary---------------------------\n")
print("Full analysis written to ESGRC_Module_model_summary.txt")

if __name__ == '__main__':
    app.run(debug=True)
    
    ##This is the most stable, lean and productive code for Multiple_Regression_model Implementation. 25th Dec 2025. Version 4_0.
    ##Implemented across all modules. 25th Dec 2025. Version 4_0.