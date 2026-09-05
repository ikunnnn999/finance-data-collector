import pandas as pd

df = pd.read_csv("data/raw/AAPL.csv")

print(df.head())

print("\n数据规模:")
print(df.shape)

print("\n字段:")
print(df.columns)

print("\n缺失值:")
print(df.isnull().sum())