import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from flask import Flask, request, jsonify
import json # Import the json Module.

# Define function to load CSV file
def load_csv_file(file_path):
    return pd.read_csv(file_path, low_memory=False)

# Define function to load JSON file
def load_json_file(json_file_path):
    with open(json_file_path, 'r') as file:
        return json.load(file)

# Define function to extract IDs
def extract_ids(json_data):
    metric_ids, group_ids, sub_module_ids = [], [], []
    for sub_module in json_data['sub_modules']:
        sub_module_ids.append(sub_module['sub_module_id'])
        for group in sub_module['groups']:
            group_ids.append(group['group_id'])
            for performance in group['value']:
                metric_ids.append(performance['metric_id'])
    return metric_ids, group_ids, sub_module_ids

# Define function to extract ID names
def extract_id_names(json_data):
    id_name_mapping = {}
    for sub_module in json_data['sub_modules']:
        id_name_mapping[sub_module['sub_module_id']] = sub_module['sub_module_name']
        for group in sub_module['groups']:
            id_name_mapping[group['group_id']] = group['group_name']
            for performance in group['value']:
                id_name_mapping[performance['metric_id']] = performance['metric_name']
    return id_name_mapping

# Load metric and JSON files
metrics_file = 'input_metric_values_esgrc.csv'
json_file = 'esgrc_performance_json_file.json'
metric_data = load_csv_file(metrics_file)
json_data = load_json_file(json_file)

# Extract IDs and ID names
metric_ids, group_ids, sub_module_ids = extract_ids(json_data)
id_name_mapping = extract_id_names(json_data)
print("Data loaded, IDs extracted, and ID names extracted successfully.")

# Define function to get name from ID
def get_name_from_id(id_value):
    return id_name_mapping.get(id_value, "Unknown")

# Define function to calculate weighted averages
def calculate_weighted_average(values, weights):
    if sum(weights) == 0:
        return 0
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)

# Define function to calculate averages
def calculate_averages(json_data, metric_data):
    group_averages = {group.get("group_id"): [] for sub_module in json_data['sub_modules']
                      for group in sub_module['groups']}
    sub_module_averages = {sub_module['sub_module_id']: [] for sub_module in json_data['sub_modules']}
    module_averages = {json_data['module_id']: []}

    for row_index in range(len(metric_data)):
        row_module_values = []
        for sub_module in json_data['sub_modules']:
            sub_module_id = sub_module['sub_module_id']
            sub_module_weights, sub_module_values = [], []
            for group in sub_module['groups']:
                group_id = group['group_id']
                weights, values = [], []
                for performance in group['value']:
                    metric_id = performance['metric_id']
                    if metric_id in metric_data.columns:
                        weights.append(performance.get('weight', 1))
                        values.append(metric_data[metric_id].iloc[row_index])
                if weights and values:
                    weighted_avg = calculate_weighted_average(values, weights)
                    group_averages[group_id].append(weighted_avg)
                    sub_module_weights.append(1)
                    sub_module_values.append(weighted_avg)
#           if not sub_module_weights and not sub_module_values:
#               for performance in sub_module['value']:
            if not sub_module_weights and not sub_module_values and 'value' in sub_module:
                for performance in sub_module['value']:
                    metric_id = performance['metric_id']
                    if metric_id in metric_data.columns:
                        sub_module_weights.append(performance.get('weight', 1))
                        sub_module_values.append(metric_data[metric_id].iloc[row_index])
                    metric_id = performance['metric_id']
                    if metric_id in metric_data.columns:
                        sub_module_weights.append(performance.get('weight', 1))
                        sub_module_values.append(metric_data[metric_id].iloc[row_index])
            if sub_module_weights and sub_module_values:
                sub_module_avg = calculate_weighted_average(sub_module_values, sub_module_weights)
                sub_module_averages[sub_module_id].append(sub_module_avg)
                row_module_values.append(sub_module_avg)
        if row_module_values:
            row_module_avg = calculate_weighted_average(row_module_values, [1] * len(row_module_values))
            module_averages[json_data['module_id']].append(row_module_avg)
    return group_averages, sub_module_averages, module_averages

# Calculate averages
group_averages, sub_module_averages, module_averages = calculate_averages(json_data, metric_data)
print("Averages calculated successfully.")

# Function to normalize data
def normalize_data(df):
    return (df - df.mean()) / df.std()

# Define function to save averages to CSV
def save_averages_to_csv(metric_data, group_averages, sub_module_averages, module_averages, output_csv_file):
    new_columns = {}

    for group_id, averages in group_averages.items():
        if len(averages) < len(metric_data.index):
            averages.extend([np.nan] * (len(metric_data.index) - len(averages)))
        new_columns[group_id] = [round(avg, 2) for avg in averages]

    for sub_module_id, averages in sub_module_averages.items():
        if len(averages) < len(metric_data.index):
            averages.extend([np.nan] * (len(metric_data.index) - len(averages)))
        new_columns[sub_module_id] = [round(avg, 2) for avg in averages]
    
    module_id = next(iter(module_averages.keys()), None)
    if module_id:
        module_avg_series = pd.Series([round(avg, 2) for avg in module_averages[module_id]])
        module_avg_series = module_avg_series.reindex(metric_data.index, fill_value=np.nan)
        new_columns['ESRC_001'] = module_avg_series

    new_columns_df = pd.DataFrame(new_columns)
    metric_data = pd.concat([metric_data, new_columns_df], axis=1)
    metric_data = metric_data.apply(lambda x: x.round(2) if x.dtype.kind in 'fc' else x)
    metric_data.to_csv(output_csv_file, index=False)
    print("Output file created with consolidated values and ESRC_001 column.")

# Define the output CSV file name
output_csv_file = 'module_values_esgrc.csv'
save_averages_to_csv(metric_data, group_averages, sub_module_averages, module_averages, output_csv_file)
print("Averages saved to CSV.")

# Reload metric data from the saved CSV file
metric_data = pd.read_csv(output_csv_file)

# Ensure the dependent variable column name is correct
dependent_variable = 'ESRC_001'
if dependent_variable not in metric_data.columns:
    raise KeyError(f"'{dependent_variable}' not found in the DataFrame columns.")

# Define function to identify low-performing metrics
def identify_low_performing_metrics(metric_ids, metric_data):
    metric_values = {metric: metric_data[metric].iloc[0] for metric in metric_ids if metric in metric_data.columns}
    sorted_metrics = sorted(metric_values.items(), key=lambda item: item[1])[:10]
    return [metric for metric, value in sorted_metrics], [value for metric, value in sorted_metrics]

low_performing_metrics, low_performing_values = identify_low_performing_metrics(metric_ids, metric_data)

# Define function to identify low-performing groups
def identify_low_performing_groups(group_ids, metric_data):
    group_values = {group: metric_data[group].iloc[0] for group in group_ids if group in metric_data.columns}
    sorted_groups = sorted(group_values.items(), key=lambda item: item[1])[:10]
    return [group for group, value in sorted_groups], [value for group, value in sorted_groups]

low_performing_groups, low_performing_group_values = identify_low_performing_groups(group_ids, metric_data)

# Define function to identify low-performing sub-modules
def identify_low_performing_sub_modules(sub_module_ids, metric_data):
    sub_module_values = {sub_module: metric_data[sub_module].iloc[0] for sub_module in sub_module_ids if sub_module in metric_data.columns}
    sorted_sub_modules = sorted(sub_module_values.items(), key=lambda item: item[1])[:10]
    return [sub_module for sub_module, value in sorted_sub_modules], [value for sub_module, value in sorted_sub_modules]

low_performing_sub_modules, low_performing_sub_module_values = identify_low_performing_sub_modules(sub_module_ids, metric_data)

# Print performance averages and save them to CSV
def print_and_save_performance_averages(low_performing_metrics, low_performing_values, low_performing_groups, low_performing_group_values, low_performing_sub_modules, low_performing_sub_module_values, module_averages, json_data, output_report_file):
    df_low_metrics = pd.DataFrame({
        'S.No': range(1, len(low_performing_metrics) + 1),
        'Metric Id': low_performing_metrics,
        'Metric Name': [get_name_from_id(metric) for metric in low_performing_metrics],
        'Metric Value': low_performing_values
    })
    print("\nLow-Performing Metrics:")
    print(df_low_metrics.to_string(index=False))

    df_low_groups = pd.DataFrame({
        'S.No': range(1, len(low_performing_groups) + 1),
        'Group Id': low_performing_groups,
        'Group Name': [get_name_from_id(group) for group in low_performing_groups],
        'Group Value': low_performing_group_values
    })
    print("\nLow-Performing Groups:")
    print(df_low_groups.to_string(index=False))

    df_low_sub_modules = pd.DataFrame({
        'S.No': range(1, len(low_performing_sub_modules) + 1),
        'Sub-Module Id': low_performing_sub_modules,
        'Sub-Module Name': [get_name_from_id(sub_module) for sub_module in low_performing_sub_modules],
        'Sub-Module Value': low_performing_sub_module_values
    })
    print("\nLow-Performing Sub-Modules:")
    print(df_low_sub_modules.to_string(index=False))

    module_average = calculate_weighted_average(module_averages[json_data['module_id']], [1] * len(module_averages[json_data['module_id']]))
    print(f"\nOverall Module Average (ESRC_001): {module_average:.2f}")

    # Save the report to CSV
    with open(output_report_file, 'w', encoding='utf-8') as f:
        f.write("Low-Performing Metrics\n")
        df_low_metrics.to_csv(f, index=False)
        f.write("\nLow-Performing Groups\n")
        df_low_groups.to_csv(f, index=False)
        f.write("\nLow-Performing Sub-Modules\n")
        df_low_sub_modules.to_csv(f, index=False)
        f.write(f"\nOverall Module Average,ESRC_001,{module_average:.2f}\n")
    print(f"Low-performing entities report saved to {output_report_file}")

# Define the output report file name
output_report_file = 'low_performing_entities_report_esgrc.txt'

# Print performance averages and save them to CSV
print_and_save_performance_averages(low_performing_metrics, low_performing_values, low_performing_groups, low_performing_group_values, low_performing_sub_modules, low_performing_sub_module_values, module_averages, json_data, output_report_file)

# Flask API for Real-Time Predictions
app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json['data']
    data_tensor = torch.tensor(data, dtype=torch.float32)
    with torch.no_grad():
        prediction = model(data_tensor).numpy()
    return jsonify({'prediction': prediction.tolist()})

# Define PyTorch Model
class LowPerformanceNN(nn.Module):
    def __init__(self, input_dim):
        super(LowPerformanceNN, self).__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 1)
    
    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x)

# Train PyTorch Model
def train_nn_model(X, y, input_dim):
    model = LowPerformanceNN(input_dim)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    X_tensor = torch.tensor(X.values, dtype=torch.float32)
    y_tensor = torch.tensor(y.values, dtype=torch.float32).view(-1, 1)
    dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)
    
    num_epochs = 100
    for epoch in range(num_epochs):
        for batch_X, batch_y in dataloader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
    
    return model

# Main Function
if __name__ == "__main__":
    input_dim = metric_data.shape[1] - 1  # Excluding the dependent variable
    X = metric_data.drop(columns=[dependent_variable])
    y = metric_data[dependent_variable]
    model = train_nn_model(X, y, input_dim)

    # Save the trained model
    torch.save(model.state_dict(), 'low_performance_model.pth')
    
    # Start Flask API
    app.run(debug=True)
##module_values_esgrc.csv is retained as the output file in place of data_for_risk_assessment.csv. version_4_0
##updated on 22Dec2025 to change the output filename from modules_values_entp.csv to data_for_risk_assessment.csv, the input file for the pipeline ahead.
##Also the low performing report is changed from .csv with a .txt file. 
##This is updated across all modules as version 02.