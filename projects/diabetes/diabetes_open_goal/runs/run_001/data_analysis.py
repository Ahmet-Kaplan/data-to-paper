
# IMPORT
import pandas as pd
import pickle
import numpy as np
import statsmodels.formula.api as smf
from sklearn.impute import SimpleImputer

# LOAD DATA
data = pd.read_csv("diabetes_binary_health_indicators_BRFSS2015.csv")

# DATASET PREPARATIONS
data['BMI_nan'] = data['BMI'].replace({98: np.nan})
imputer = SimpleImputer(strategy="median")
data['BMI_imputed'] = imputer.fit_transform(data[['BMI_nan']])

# DESCRIPTIVE STATISTICS
## Table 0: "Mean and standard deviation of diabetes diagnosis and physical activity, stratified by difficulty in walking"
mean = data.groupby('DiffWalk')[['Diabetes_binary', 'PhysActivity']].mean()
std_dev = data.groupby('DiffWalk')[['Diabetes_binary', 'PhysActivity']].std()
df0 = pd.concat([mean, std_dev], axis=1)
df0.columns = pd.MultiIndex.from_product([['Diabetes_binary', 'PhysActivity'], ['mean', 'std_dev']], names=['Variable', 'Statistic'])
df0.index = ['No Difficulty Walking', 'Difficulty Walking']
df0.to_pickle('table_0.pkl')


# PREPROCESSING 
data_sex_dummy = pd.get_dummies(data['Sex'], prefix='Sex')
data = pd.concat([data, data_sex_dummy], axis=1)

# ANALYSIS
## Table 1: "Logistic regression analysis testing association between physical activity and diabetes, moderated by difficulty in walking"
model1 = smf.logit(formula = "Diabetes_binary ~ PhysActivity * DiffWalk + BMI_imputed + HighBP + HighChol + Stroke + HeartDiseaseorAttack + Smoker + HvyAlcoholConsump", data=data).fit()
params1 = model1.params.filter(regex = 'PhysActivity|DiffWalk')
df1 = pd.DataFrame({
    'parameter': params1.values,
    'p-value': model1.pvalues.filter(regex = 'PhysActivity|DiffWalk').values,
}, index=params1.index)
df1.to_pickle('table_1.pkl')

## Table 2: "Logistic regression analysis testing association between physical activity and diabetes, moderated by sex"
model2 = smf.logit(formula = "Diabetes_binary ~ PhysActivity * Sex_1 + BMI_imputed + HighBP + HighChol + Stroke + HeartDiseaseorAttack + Smoker + HvyAlcoholConsump", data=data).fit()
params2 = model2.params.filter(regex = 'PhysActivity|Sex_1')
df2 = pd.DataFrame({
    'parameter': params2.values,
    'p-value': model2.pvalues.filter(regex = 'PhysActivity|Sex_1').values,
}, index=params2.index)
df2.to_pickle('table_2.pkl')

## Table 3: "Logistic regression analysis testing association between physical activity and diabetes, moderated by Age"
model3 = smf.logit(formula = "Diabetes_binary ~ PhysActivity * Age + BMI_imputed + HighBP + HighChol + Stroke + HeartDiseaseorAttack + Smoker + HvyAlcoholConsump", data=data).fit()
params3 = model3.params.filter(regex='PhysActivity|Age')
df3 = pd.DataFrame({
    'parameter': params3.values,
    'p-value': model3.pvalues.filter(regex='PhysActivity|Age').values,
}, index=params3.index)
df3.to_pickle('table_3.pkl')

# SAVE ADDITIONAL RESULTS
additional_results = {
    'Total number of observations': len(data),         
    'AIC of model testing for interaction between physical activity and mobility difficulties': model1.aic,
    'AIC of model testing for interaction between physical activity and Gender': model2.aic,
    'AIC of model testing for interaction between physical activity and Age': model3.aic
}
with open('additional_results.pkl', 'wb') as f:
    pickle.dump(additional_results, f)
