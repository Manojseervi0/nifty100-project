import pandas as pd

df = pd.read_excel("data/financial_ratios.xlsx", header=None)

print(df.head(10))