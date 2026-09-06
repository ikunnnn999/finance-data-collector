# 参数、数据与复现

## 输入参数

| 参数 | 含义 |
| --- | --- |
| 一个或多个股票代码 | 美股股票/ETF；第一只做因子回归和择时策略；加上基准后最多 8 只 |
| `--benchmark SPY` | 默认比较基准，自动加入资产池 |
| `--start YYYY-MM-DD` | 收益区间起点；必须有前一交易日价格 |
| `--end YYYY-MM-DD` | 期望终点；实际截至行情与官方因子共同可用的完整交易日 |
| `--train-end YYYY-MM-DD` | 自定时间划分；最后一个训练期收盘预留用于执行 |
| `--cost-bps 10` | 单边比例成本，含首次建仓，期末不强制清仓 |
| `--include-ml` | 可选扩展窗口 L2 逻辑回归；默认不运行 |
| `--output-dir PATH` | 空目录，避免覆盖既有报告 |
| `--runtime-dir PATH` | 隔离 Python 环境位置 |
| `--use-current-python` | 复用已有依赖，不自动安装 |
| `--prices-dir PATH` | 显式使用每代码一个 date/close CSV，不下载行情 |
| `--ff3 FILE --ff5 FILE` | 官方日度 CSV/ZIP 快照；均指定且有 prices-dir 时完全离线 |

只指定代码时，分析范围默认为最新共同因子日期向前五年；若上市历史较短，默认起点随实际历史调整并记录。显式要求的过早起点会报错，不能悄悄缩短。明确的缺口不会通过截取表现较好的区间来绕开。

## 方法

- 行情由 `akshare.stock_us_daily(symbol=..., adjust="qfq")` 获取，保留供应商快照，独立截取所选区间。异常收益不删行，缺失或无效交易日会阻止回测。
- 因子来自 Kenneth French 美国日度 FF3/FF5，百分数转换为小数；Mkt-RF 已是超额收益。五因子解释 RMW 盈利、CMA 投资暴露。
- 无足够完整历史建立至少 252 个训练观测和 30 个测试观测时，只运行风险和因子回归；少于 30 个共同收益日则报错。
- 波动为日收益样本标准差乘 sqrt(252)；几何年化按实际观测日数；Sharpe 使用同频日超额收益；最大回撤包含初始资本 1。
- Markowitz 非负权重、和为 1；训练期均值/协方差，最小方差与最大 Sharpe 采用约束优化。单一资产池的组合会退化为该资产。
- 优化组合按月恢复训练期固定权重；均线默认 20/60，t 日信号于 t+1 收盘执行，收益从 t+2 日计入。现金按 RF 计息，交易成本按交易金额计入。
- 逻辑回归特征含历史收益、动量、波动和均线比，均滞后两日；每 63 日扩展训练窗，标准化只用训练集，固定 L2=0.01、阈值=0.5。比较多数类和恒上涨基线。

这些是研究原型结果。股票池选择、数据修订、复权方法、成本近似和单一测试区间均会影响结论。

## 排错

读取 `failure.json` 或 `analysis.log` 的具体错误。网络失败只作一次有限重试；供应商限流时停止批量请求。输入有缺口时让用户提供修复后的 date/close 数据，或由用户明确选择另一个区间。不要删除异常行后重新把多日价格变化当作日收益。

首次环境安装失败时保留 pip 的实际错误；不修改用户的系统代理或全局 Python。可使用已安装依赖的 Python 加 `--use-current-python`。Python 环境、行情下载和分析都在用户工作目录中，安装的技能目录只读即可运行。

## 来源

- [AKShare 美股行情说明](https://akshare.akfamily.xyz/data/stock/stock.html)
- [Kenneth French 数据库](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [美国五因子构造](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html)
