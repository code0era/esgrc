import pandas as pd
import json

def load_json_file(json_file_path):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    return data

def load_csv_file(csv_file_path):
    return pd.read_csv(csv_file_path, low_memory=False)

def create_mappings(data):
    metric_columns = []
    group_columns = []
    sub_module_columns = []
    
    for sub_module in data['sub_modules']:
        sub_module_id = sub_module['sub_module_id']
        sub_module_columns.append(sub_module_id)
        
        if 'groups' in sub_module:
            for group in sub_module['groups']:
                group_id = group['group_id']
                group_columns.append(group_id)
                
                for metric in group['value']:
                    metric_id = metric['metric_id']
                    metric_columns.append(metric_id)

    mappings = {
        "metric_columns": metric_columns,
        "group_columns": group_columns,
        "sub_module_columns": sub_module_columns
    }

    return mappings

def split_data(source_file, json_file_path, metrics_output_file, groups_output_file, sub_modules_output_file, risk_assessment_output_file):
    # Load JSON data
    data = load_json_file(json_file_path)
    
    # Load the combined CSV file
    df = load_csv_file(source_file)
    
    # Create mappings
    mappings = create_mappings(data)
    
    metric_columns = mappings['metric_columns']
    group_columns = mappings['group_columns']
    sub_module_columns = mappings['sub_module_columns']
    
    # Add the module column to the sub_module_columns list for risk assessment
    module_column = 'ESRC_001'
    risk_assessment_columns = sub_module_columns + [module_column]
    
    # Split the data based on the mappings
    df_metrics = df[metric_columns]
    df_groups = df[group_columns]
    df_sub_modules = df[sub_module_columns]
    df_risk_assessment = df[risk_assessment_columns]
    
    # Save the split data to separate CSV files
    df_metrics.to_csv(metrics_output_file, index=False)
    df_groups.to_csv(groups_output_file, index=False)
    df_sub_modules.to_csv(sub_modules_output_file, index=False)
    df_risk_assessment.to_csv(risk_assessment_output_file, index=False)
    
    print(f"Metrics data saved to {metrics_output_file}")
    print(f"Groups data saved to {groups_output_file}")
    print(f"Sub-modules data saved to {sub_modules_output_file}")
    print(f"Risk assessment data saved to {risk_assessment_output_file}")

if __name__ == "__main__":
    source_file = 'module_values_esgrc.csv'
    json_file_path = 'esgrc_performance_json_file.json'
    metrics_output_file = 'filtered_metrics_data_esgrc.csv'
    groups_output_file = 'filtered_groups_data_esgrc.csv'
    sub_modules_output_file = 'filtered_sub_modules_data_esgrc.csv'
    risk_assessment_output_file = 'data_for_risk_assessment_esgrc.csv'
    
    split_data(source_file, json_file_path, metrics_output_file, groups_output_file, sub_modules_output_file, risk_assessment_output_file)


    # This is the code for Splitting the columns into Metrics, Groups, Sub-Modules, and Risk Assessment CSV files, for correlation analysis.
    # Code updated to include generation of "data_for_risk_assessment_<module>.csv" file along with the three filtered files.
    # "data_for_risk_assessment_<module>.csv" is required for the Multi Variate Risk Assessment for L0.
