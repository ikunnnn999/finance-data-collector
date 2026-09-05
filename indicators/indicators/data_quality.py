import pandas as pd

df = pd.read_csv(
    "data/raw/AAPL.csv"
)

print(df.head())
print(df.columns)


# 查看收益统计
print("收益统计:")
print(df["return"].describe())


# 查看异常上涨
print("\n异常上涨:")
print(
    df[
        df["return"] > 0.2
    ]
)


# 查看异常下跌
print("\n异常下跌:")
print(
    df[
        df["return"] < -0.2
    ]
)