import pandas as pd
import matplotlib.pyplot as plt


# =========================
# 1. 读取处理后的数据
# =========================

df = pd.read_csv(
    "data/processed/AAPL_processed.csv"
)


# =========================
# 2. 日期处理
# =========================

df["date"] = pd.to_datetime(
    df["date"]
)

# 按日期排序

df = df.sort_values(
    "date"
)


# =========================
# 3. 计算累计最高价格
# =========================

# 历史最高收盘价

df["peak"] = (
    df["close"]
    .cummax()
)


# =========================
# 4. 计算每日回撤
# =========================

df["drawdown"] = (
    df["close"] - df["peak"]
) / df["peak"]


# =========================
# 5. 最大回撤
# =========================

max_drawdown = (
    df["drawdown"]
    .min()
)


print("===================")
print("AAPL 最大回撤分析")
print("===================")

print(
    f"最大回撤: {max_drawdown:.2%}"
)


# 最大回撤发生日期

max_dd_date = df.loc[
    df["drawdown"].idxmin(),
    "date"
]


print(
    f"最大回撤日期: {max_dd_date.date()}"
)


# =========================
# 6. 保存结果
# =========================

df.to_csv(
    "data/processed/AAPL_drawdown.csv",
    index=False
)


print(
    "结果已保存: data/processed/AAPL_drawdown.csv"
)


# =========================
# 7. 绘制回撤曲线
# =========================

plt.figure(
    figsize=(12,5)
)


plt.plot(
    df["date"],
    df["drawdown"]
)


plt.title(
    "AAPL Historical Drawdown"
)


plt.xlabel(
    "Date"
)


plt.ylabel(
    "Drawdown"
)


plt.grid()


plt.show()