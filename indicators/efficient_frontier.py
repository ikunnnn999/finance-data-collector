import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# 读取收益数据

aapl = pd.read_csv(
    "data/raw/AAPL.csv"
)

msft = pd.read_csv(
    "data/raw/MSFT.csv"
)

spy = pd.read_csv(
    "data/raw/SPY.csv"
)


# 日期处理

for df in [aapl, msft, spy]:
    df["date"] = pd.to_datetime(df["date"])


# 计算收益

aapl["return"] = aapl["close"].pct_change()
msft["return"] = msft["close"].pct_change()
spy["return"] = spy["close"].pct_change()


data = pd.DataFrame({
    "AAPL": aapl["return"],
    "MSFT": msft["return"],
    "SPY": spy["return"]
})


data = data.dropna()


# 年化收益

mean_returns = data.mean() * 252


# 协方差矩阵

cov_matrix = data.cov() * 252


# 随机生成组合

results = []


for i in range(5000):

    weights = np.random.random(3)

    weights = weights / np.sum(weights)


    portfolio_return = np.dot(
        weights,
        mean_returns
    )


    portfolio_volatility = np.sqrt(
        np.dot(
            weights.T,
            np.dot(
                cov_matrix,
                weights
            )
        )
    )


    sharpe = portfolio_return / portfolio_volatility


    results.append(
        [
            portfolio_return,
            portfolio_volatility,
            sharpe,
            weights[0],
            weights[1],
            weights[2]
        ]
    )


results = pd.DataFrame(
    results,
    columns=[
        "return",
        "volatility",
        "sharpe",
        "AAPL",
        "MSFT",
        "SPY"
    ]
)


# 最大Sharpe组合

best = results.loc[
    results["sharpe"].idxmax()
]


print("最优组合:")
print(best)


# 绘图

plt.figure(figsize=(10,6))


plt.scatter(
    results["volatility"],
    results["return"],
    c=results["sharpe"]
)


plt.xlabel(
    "Volatility"
)

plt.ylabel(
    "Return"
)

plt.title(
    "Efficient Frontier"
)


plt.colorbar(
    label="Sharpe Ratio"
)


plt.scatter(
    best["volatility"],
    best["return"],
    marker="*",
    s=300
)


plt.show()