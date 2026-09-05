import pandas as pd
import numpy as np


# 读取AAPL

df = pd.read_csv(
    "data/processed/AAPL_processed.csv"
)


# 日期排序

df["date"] = pd.to_datetime(df["date"])

df = df.sort_values(
    "date"
)


# 日收益率

df["return"] = (
    df["close"]
    .pct_change()
)


df = df.dropna()


# 年化收益率

annual_return = (
    (1 + df["return"].mean()) ** 252
    - 1
)


# 年化波动率

annual_volatility = (
    df["return"].std()
    *
    np.sqrt(252)
)


# 夏普比率

sharpe_ratio = (
    annual_return
    /
    annual_volatility
)


print(
    "年化收益率:",
    annual_return
)


print(
    "年化波动率:",
    annual_volatility
)


print(
    "夏普比率:",
    sharpe_ratio
)