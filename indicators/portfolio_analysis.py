import pandas as pd
import numpy as np


# 读取三个股票

aapl = pd.read_csv(
    "data/raw/AAPL.csv"
)

msft = pd.read_csv(
    "data/raw/MSFT.csv"
)

spy = pd.read_csv(
    "data/raw/SPY.csv"
)


# 日期

for df in [aapl, msft, spy]:

    df["date"] = pd.to_datetime(
        df["date"]
    )



# 计算收益

aapl["return"] = aapl["close"].pct_change()

msft["return"] = msft["close"].pct_change()

spy["return"] = spy["close"].pct_change()



# 合并

data = pd.DataFrame({

    "AAPL": aapl["return"],

    "MSFT": msft["return"],

    "SPY": spy["return"]

})


# 删除空值

data = data.dropna()



print(data.head())


# 设置投资比例

weights = np.array(
    [
        0.4,
        0.3,
        0.3
    ]
)


# 组合收益

portfolio_return = (
    data * weights
).sum(axis=1)



# 年化收益

annual_return = (
    portfolio_return.mean()
    *
    252
)


# 年化波动

annual_volatility = (
    portfolio_return.std()
    *
    np.sqrt(252)
)


# Sharpe

sharpe = (
    annual_return /
    annual_volatility
)


print(
    "组合年化收益:",
    annual_return
)


print(
    "组合波动:",
    annual_volatility
)


print(
    "组合Sharpe:",
    sharpe
)