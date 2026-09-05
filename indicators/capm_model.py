import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import statsmodels.api as sm


# ==========================
# 1.读取数据
# ==========================

aapl = pd.read_csv(
    "data/processed/AAPL_processed.csv"
)

spy = pd.read_csv(
    "data/raw/SPY.csv"
)


# ==========================
# 2.日期处理
# ==========================

aapl["date"] = pd.to_datetime(
    aapl["date"]
)

spy["date"] = pd.to_datetime(
    spy["date"]
)


# ==========================
# 3.计算收益率
# ==========================

aapl["AAPL_return"] = (
    aapl["close"]
    .pct_change()
)


spy["Market_return"] = (
    spy["close"]
    .pct_change()
)


# ==========================
# 4.合并数据
# ==========================

data = pd.merge(
    aapl[["date","AAPL_return"]],
    spy[["date","Market_return"]],
    on="date"
)


# 删除空值

data = data.dropna()


print(data.head())


# ==========================
# 5. CAPM回归
# ==========================

X = data["Market_return"]

y = data["AAPL_return"]


# 加常数项 alpha

X = sm.add_constant(X)


model = sm.OLS(
    y,
    X
).fit()


print("====================")
print("CAPM Regression")
print("====================")

print(model.summary())


# ==========================
# 6.提取指标
# ==========================


alpha = model.params["const"]

beta = model.params["Market_return"]

r_squared = model.rsquared


annual_alpha = alpha * 252



print("====================")

print(
    "Beta:",
    beta
)


print(
    "Daily Alpha:",
    alpha
)


print(
    "Annual Alpha:",
    annual_alpha
)


print(
    "R squared:",
    r_squared
)



# ==========================
# 7.绘制CAPM关系图
# ==========================


plt.figure(
    figsize=(8,5)
)


plt.scatter(
    data["Market_return"],
    data["AAPL_return"],
    alpha=0.3
)


# 回归线

x = np.linspace(
    data["Market_return"].min(),
    data["Market_return"].max(),
    100
)


y = alpha + beta*x


plt.plot(
    x,
    y
)


plt.xlabel(
    "Market Return"
)


plt.ylabel(
    "AAPL Return"
)


plt.title(
    "CAPM Model: AAPL vs SPY"
)


plt.grid()


plt.show()



# ==========================
# 8.保存结果
# ==========================


result = pd.DataFrame({

    "Beta":[beta],

    "Daily Alpha":[alpha],

    "Annual Alpha":[annual_alpha],

    "R_squared":[r_squared]

})


result.to_csv(
    "data/processed/AAPL_CAPM_result.csv",
    index=False
)


print(
    "CAPM结果已保存"
)