import pandas as pd
import re
import os

# --- STEP 1: DEFINE CORE FUNCTIONS ---

def consolidate_with_mapping(file_list, output_csv="all_module_values.csv"):
    """Appends columns, creates a Sub-Module map, and adds the final average column."""
    dataframes = []
    sub_to_module_map = {}
    
    # Regex Patterns for categorization
    module_pattern = re.compile(r'^[A-Z]{4}_001$')
    sub_module_pattern = re.compile(r'^[A-Z]{3}10000$')

    for filename in file_list:
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            dataframes.append(df)
            
            # Find the parent Module in this specific file
            current_file_modules = [c for c in df.columns if module_pattern.match(str(c))]
            # We use the first module found in the file as the parent reference
            parent_module = current_file_modules[0] if current_file_modules else "Unknown"
            
            # Map all Sub-Modules in this file to that parent Module
            for col in df.columns:
                if sub_module_pattern.match(str(col)):
                    sub_to_module_map[col] = parent_module
        else:
            print(f"Warning: File {filename} not found.")

    # 1. Combine all columns side-by-side
    combined_df = pd.concat(dataframes, axis=1)
    combined_df = combined_df.loc[:, ~combined_df.columns.duplicated()]

    # 2. Identify all Module columns for the final average
    module_cols = [c for c in combined_df.columns if module_pattern.match(str(c))]
    
    # 3. Add L0ER_001 column as the row-wise mean of all identified Module columns
    if module_cols:
        combined_df['L0ER_001'] = combined_df[module_cols].mean(axis=1).round(2)
    else:
        combined_df['L0ER_001'] = 0.0

    # 4. Save the master file with L0ER_001 as the last column
    combined_df.to_csv(output_csv, index=False)
    
    return combined_df, sub_to_module_map

def identify_low_performers(df, id_list, top_n=3):
    """Ranks performance based on the first row (index 0)."""
    valid_ids = [item for item in id_list if item in df.columns]
    # Check if the list is empty to prevent errors
    if not valid_ids: return []
    
    performance_map = {item: df[item].iloc[0] for item in valid_ids}
    sorted_performers = sorted(performance_map.items(), key=lambda x: x[1])
    return sorted_performers[:top_n]

# --- STEP 2: EXECUTION ---

# List your CSV files here
my_files = ['data_for_risk_assessment_brand.csv',
    'data_for_risk_assessment_bspt.csv',
    'data_for_risk_assessment_customer.csv', 
    'data_for_risk_assessment_enterprise.csv',
    'data_for_risk_assessment_esgrc.csv',
    'data_for_risk_assessment_integration.csv',
    'data_for_risk_assessment_mkts.csv',
    'data_for_risk_assessment_product.csv',
    'data_for_risk_assessment_resource.csv',
    'data_for_risk_assessment_service.csv',
    'data_for_risk_assessment_shared.csv',
    'data_for_risk_assessment_ictm.csv']

# 1. Process files, add L0ER_001, and build mapping
consolidated_df, mapping = consolidate_with_mapping(my_files)

# 2. Extract specific IDs for reporting
module_pattern = re.compile(r'^[A-Z]{4}_001$')
sub_module_pattern = re.compile(r'^[A-Z]{3}10000$')

all_ids = consolidated_df.columns.tolist()
module_ids = [i for i in all_ids if module_pattern.match(str(i))]
sub_module_ids = [i for i in all_ids if sub_module_pattern.match(str(i))]

# 3. Identify Low Performers
low_modules = identify_low_performers(consolidated_df, module_ids)
low_sub_modules = identify_low_performers(consolidated_df, sub_module_ids)

# --- STEP 3: OUTPUT REPORT ---

output_txt = "performance_report_2025.txt"
with open(output_txt, "w", encoding="utf-8") as f:
    def dual_print(text):
        print(text)
        f.write(text + "\n")

    dual_print("--- PERFORMANCE ANALYSIS REPORT (2025) ---")
    dual_print(f"Master CSV Saved: {os.path.abspath('all_module_values.csv')}")
    dual_print(f"Overall Average Column Created: L0ER_001")
    dual_print(f"Analyzed {len(module_ids)} Modules and {len(sub_module_ids)} Sub-Modules.\n")

    dual_print("--- 3 Low Performing Modules ---")
    for mid, val in low_modules:
        dual_print(f"Module ID: {mid} | Value: {val}")

    dual_print("\n--- 3 Low Performing Sub-Modules (with Module Alias) ---")
    for smid, val in low_sub_modules:
        parent = mapping.get(smid, "Unknown Module")
        dual_print(f"Sub-Module: {smid} | Parent Module: {parent} | Value: {val}")

print(f"\nFull report and consolidated CSV ready in your directory.")
