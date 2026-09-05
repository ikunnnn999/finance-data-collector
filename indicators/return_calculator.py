import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os


df = pd.read_csv(
    "data/raw/AAPL.csv"
)


# 统一列名
df.columns = df.columns.str.lower()

print(df.columns)


# 日期处理
df["date"] = pd.to_datetime(df["date"])


# 排序
df = df.sort_values("date")


# 计算收益率

df["return"] = df["close"].pct_change()


# 删除异常收益
df = df[
    (df["return"] < 0.15) &
    (df["return"] > -0.15)
]


# 删除第一行空值

df = df.dropna()


print(df.head())


print("\n收益率统计:")
print(df["return"].describe())


# 删除第一行空值
df = df.dropna()


# 保存
df.to_csv(
    "data/processed/AAPL_processed.csv",
    index=False
)


# ==========================
# 累计收益曲线
# ==========================

df["cum_return"] = (
    1 + df["return"]
).cumprod()


plt.figure(figsize=(10,5))

plt.plot(
    df["date"],
    df["cum_return"]
)

plt.title(
    "AAPL Cumulative Return"
)

plt.xlabel(
    "Date"
)

plt.ylabel(
    "Growth of $1"
)



plt.gca().xaxis.set_major_locator(
    mdates.YearLocator(5)
)

plt.gca().xaxis.set_major_formatter(
    mdates.DateFormatter("%Y")
)

plt.xticks(rotation=45)

plt.grid()

plt.show()