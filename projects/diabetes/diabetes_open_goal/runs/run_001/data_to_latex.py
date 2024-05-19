
# IMPORT
import pandas as pd
from my_utils import to_latex_with_note, is_str_in_df, split_mapping, AbbrToNameDef

# PREPARATION FOR ALL TABLES
shared_mapping: AbbrToNameDef = {
    'Diabetes_binary': ('Diabetes', 'Diabetes (0=no, 1=yes)'),
    'PhysActivity': ('Physical Activity', 'Physical Activity in past 30 days (0=no, 1=yes)'),
    'DiffWalk': ('Difficulty Walking', 'Serious difficulty walking or climbing stairs (0=no, 1=yes)'),
    'Sex_1': ('Male', 'Sex (0=female, 1=male)'),
    'Age': ('Age Category', '13-level age category in intervals of 5 years (1=18-24, ...,13=80 or older)'),
    'mean': ('Mean', None),
    'std_dev': ('Standard Deviation', None)
}

# TABLE 0:
df0 = pd.read_pickle('table_0.pkl')

# RENAME ROWS AND COLUMNS
mapping0 = { k:v for k, v in shared_mapping.items() if is_str_in_df(df0, k) }
abbrs_to_names0, legend0 = split_mapping(mapping0)
df0.rename(index=abbrs_to_names0, columns=abbrs_to_names0, inplace=True)

# SAVE AS LATEX:
to_latex_with_note( 
    df0, 'table_0.tex',
    caption="Mean and Standard Deviation of Diabetes Diagnosis and Physical Activity, Stratified by Difficulty in Walking", 
    label='table:diabetes_activity_diff_walk',
    legend=legend0)

# TABLE 1:
df1 = pd.read_pickle('table_1.pkl')

# RENAME ROWS AND COLUMNS
mapping1 = { k:v for k, v in shared_mapping.items() if is_str_in_df(df1, k) }
mapping1 |= {
    'PhysActivity:DiffWalk': ('Physical Activity * Difficulty Walking', 
                              'Interaction term between Physical Activity and Difficulty Walking'),
    'parameter': ('Parameter Estimate', None),
    'p-value': ('P-value', None)
}
abbrs_to_names1, legend1 = split_mapping(mapping1)
df1.rename(index=abbrs_to_names1, columns=abbrs_to_names1, inplace=True)


# SAVE AS LATEX:
to_latex_with_note( 
    df1, 'table_1.tex',
    caption="Logistic Regression Analysis Testing Association Between Physical Activity and Diabetes, Moderated by Difficulty in Walking", 
    label='table:logistic_reg_diff_walk',
    legend=legend1)

# TABLE 2:
df2 = pd.read_pickle('table_2.pkl')

# RENAME ROWS AND COLUMNS
mapping2 = { k:v for k, v in shared_mapping.items() if is_str_in_df(df2, k) }
mapping2 |= {
    'PhysActivity:Sex_1[T.True]': ('Physical Activity * Male', 
                           'Interaction term between Physical Activity and Male'),
    'Sex_1[T.True]': ('Male (Boolean Value)', 'Male (1=True, 0=False)')
}
abbrs_to_names2, legend2 = split_mapping(mapping2)
df2.rename(index=abbrs_to_names2, columns=abbrs_to_names2, inplace=True)

# SAVE AS LATEX:
to_latex_with_note( 
    df2, 'table_2.tex',
    caption="Logistic Regression Analysis Testing Association Between Physical Activity and Diabetes, Moderated by Sex", 
    label='table:logistic_reg_sex',
    legend=legend2)

# TABLE 3:
df3 = pd.read_pickle('table_3.pkl')

# RENAME ROWS AND COLUMNS
mapping3 = { k:v for k, v in shared_mapping.items() if is_str_in_df(df3, k) }
mapping3 |= {
    'PhysActivity:Age': ('Physical Activity * Age Category', 
                         'Interaction term between Physical Activity and Age Category')
}
abbrs_to_names3, legend3 = split_mapping(mapping3)
df3.rename(index=abbrs_to_names3, columns=abbrs_to_names3, inplace=True)

# SAVE AS LATEX:
to_latex_with_note(
    df3, 'table_3.tex',
    caption="Logistic Regression Analysis Testing Association Between Physical Activity and Diabetes, Moderated by Age", 
    label='table:logistic_reg_age',
    legend=legend3)
