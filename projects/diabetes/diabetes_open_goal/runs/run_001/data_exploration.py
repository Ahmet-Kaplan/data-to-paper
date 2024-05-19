
# Importing required libraries
import pandas as pd
import numpy as np

# Load Dataset
data = pd.read_csv("diabetes_binary_health_indicators_BRFSS2015.csv")

# Create an output file
with open("data_exploration.txt", "w") as output_file:
    
    # Data Size
    output_file.write("# Data Size\n")
    output_file.write(f"Number of Rows: {data.shape[0]}\nNumber of Columns: {data.shape[1]}\n\n")
    
    # Summary Statistics
    output_file.write("# Summary Statistics\n")
    output_file.write(data.describe().to_string()+"\n\n")

    # Categorical Variables
    output_file.write("# Categorical Variables\n")
    categorical_variables = data.select_dtypes(include='int').columns.to_list()
    
    for variable in categorical_variables:
        try:
            mode = data[variable].mode()[0]
            output_file.write(f"Categorical Variable: {variable}, Most Common Value: {mode}\n")
        except:
            continue

    output_file.write("\n")

    # Missing Values
    output_file.write("# Missing Values\n")
    missing_counts = data.isnull().sum()
    output_file.write(f"Missing Values Count:\n {missing_counts.to_string()}\n\n")
    
    # Checking for special numeric values that stand for unknown/undefined
    for column in data.columns:
        if ((data[column] == 99).any()) | ((data[column] == 88).any()):
            unknown_count = (data[column] == 99).sum() + (data[column] == 88).sum()
            output_file.write(f"Column '{column}' has {unknown_count} special numeric values that stand for unknown/undefined.\n")

    output_file.write("\n")
