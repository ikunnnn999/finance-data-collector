import pandas as pd
import matplotlib.pyplot as plt


# 读取数据
aapl = pd.read_csv(
    "data/raw/AAPL.csv"
)

spy = pd.read_csv(
    "data/raw/SPY.csv"
)


# 日期处理
aapl["date"] = pd.to_datetime(aapl["date"])
spy["date"] = pd.to_datetime(spy["date"])


# 排序
aapl = aapl.sort_values("date")
spy = spy.sort_values("date")


# 计算每日收益率
aapl["return"] = aapl["close"].pct_change()
spy["return"] = spy["close"].pct_change()


# 删除空值
aapl = aapl.dropna()
spy = spy.dropna()


# 合并
df = pd.merge(
    aapl[["date","return"]],
    spy[["date","return"]],
    on="date",
    suffixes=("_aapl","_spy")
)


# 超额收益
df["alpha"] = (
    df["return_aapl"]
    -
    df["return_spy"]
)


print(df.head())


print("\n平均每日超额收益:")
print(df["alpha"].mean())


# 累计超额收益
df["cumulative_alpha"] = (
    1 + df["alpha"]
).cumprod()


# 绘图

plt.figure(figsize=(12,5))

plt.plot(
    df["date"],
    df["cumulative_alpha"]
)

plt.title(
    "AAPL Excess Return vs SPY"
)

plt.xlabel(
    "Date"
)

plt.ylabel(
    "Growth of $1"
)

plt.grid()

plt.show()