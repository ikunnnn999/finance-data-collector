import pandas as pd
import statsmodels.api as sm


# 股票收益

stock = pd.read_csv(
    "data/raw/AAPL.csv"
)


stock["date"] = pd.to_datetime(
    stock["date"]
)


stock["return"] = (
    stock["close"]
    .pct_change()
)


stock = stock.dropna()



# 市场收益

market = pd.read_csv(
    "data/raw/SPY.csv"
)


market["return"] = (
    market["close"]
    .pct_change()
)


market = market.dropna()



# 日期统一格式

stock["date"] = pd.to_datetime(
    stock["date"]
)

market["date"] = pd.to_datetime(
    market["date"]
)


# 合并

data = pd.merge(
    stock[["date","return"]],
    market[["date","return"]],
    on="date",
    suffixes=("_stock","_market")
)


data = data.dropna()


# 超额收益

data["excess_stock"] = (
    data["return_stock"]
    -
    0.03/252
)



data["excess_market"] = (
    data["return_market"]
    -
    0.03/252
)



# 回归

X = data[
    ["excess_market"]
]


X = sm.add_constant(X)


y=data["excess_stock"]



model = sm.OLS(
    y,
    X
).fit()



print(
    model.summary()
)