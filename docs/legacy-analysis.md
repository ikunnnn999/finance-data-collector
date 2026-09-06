# Finance Data Collector

**基于 Python 的美股收益、风险与市场暴露分析**

以苹果（AAPL）为主要研究对象，以标普 500 ETF（SPY）为市场代理，结合微软（MSFT）开展组合研究实验。项目串联历史行情采集、收益处理、风险指标、回撤分析和 OLS 回归，回答“收益如何变化、承担了多大风险、与市场波动有什么关系”。

当前版本为金融数据分析研究原型，单资产分析与回归已实现。组合日期对齐和收益处理仍需改进；三因子模型已实现并完成本地诊断验证，不将这些实验表述为成熟策略业绩。

## 项目亮点

- 使用 AKShare 采集三只美股/ETF 的前复权行情，分层保存原始与处理后数据。
- 实现日收益、累计净值、年化指标和最大回撤计算及可视化。
- 使用 statsmodels OLS 估计市场敏感度，输出 Alpha、Beta、R² 与显著性摘要。
- 实现固定权重组合及 5,000 次随机权重模拟原型，探索收益与风险的关系。

## 功能与边界

| 模块 | 实际实现 | 当前限制 |
| --- | --- | --- |
| 行情采集 | AAPL、MSFT、SPY，前复权，CSV 保存 | 删除非正 close，同名文件会覆盖 |
| 数据检查 | 数据预览、规模、字段、缺失值 | 未实现完整自动校验 |
| 收益分析 | 排序、日收益、累计净值曲线 | 仅保留严格介于 −15% 与 +15% 的收益行 |
| 风险指标 | 年化收益、波动、收益/波动比 | 年化与 Sharpe 口径见下文 |
| 回撤 | 价格峰值、最大回撤、谷底日期 | 基于过滤后的价格样本 |
| CAPM | 带截距 OLS、摘要、散点与拟合线、CSV | 未扣除无风险收益，使用默认标准误 |
| fama_french.py | 官方日度 Mkt-RF、SMB、HML 与 RF，OLS + HAC，同样本 CAPM 比较 | 价格复权及异常收益仍需核查，结果仅用于诊断 |
| 组合分析 | AAPL/MSFT/SPY 权重 40%/30%/30% | 按行索引拼接收益，未按日期对齐 |
| 有效前沿实验 | 5,000 组非负且和为 1 的随机权重 | 随机可行组合云图，未求解严格有效前沿 |
| 绩效比较 | AAPL/SPY 日期合并、日收益差及其复利图 | 该图不是两条资产净值之差或 CAPM Alpha |

## 技术栈与结构

Python、pandas、NumPy、AKShare、Matplotlib、statsmodels。依赖文件还保留 yfinance、Jupyter，当前采集脚本实际使用 AKShare。

```text
finance-data-collector/
├── collector/
│   ├── stock_data.py             # 行情采集
│   └── check_data.py             # 数据概览
├── indicators/
│   ├── return_calculator.py      # 收益与累计净值
│   ├── risk_metrics.py           # 年化指标
│   ├── drawdown.py               # 回撤分析
│   ├── capm_model.py             # OLS 市场模型
│   ├── fama_french.py            # 日度三因子、HAC 与同样本 CAPM 比较
│   ├── portfolio_analysis.py     # 固定权重实验
│   ├── efficient_frontier.py     # 随机组合实验
│   ├── performance_compare.py    # 基准收益差
│   └── indicators/
│       └── data_quality.py       # 调试脚本，要求 raw 含 return
├── data/
│   ├── raw/                      # AAPL.csv、MSFT.csv、SPY.csv
│   └── processed/                # 收益、回撤、回归结果
├── requirements.txt
└── README.md
```

两个 data 子目录均被 Git 忽略，克隆后需自行采集或准备数据。所有脚本必须从仓库根目录运行。

## 快速开始

Windows PowerShell，在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force -Path data/raw, data/processed | Out-Null

# 已有行情时可跳过采集，避免覆盖本地快照
.\.venv\Scripts\python.exe collector/stock_data.py
.\.venv\Scripts\python.exe collector/check_data.py

.\.venv\Scripts\python.exe indicators/return_calculator.py
.\.venv\Scripts\python.exe indicators/risk_metrics.py
.\.venv\Scripts\python.exe indicators/drawdown.py
.\.venv\Scripts\python.exe indicators/capm_model.py
```

采集调用 `ak.stock_us_daily(symbol=stock, adjust="qfq")`，每次尝试后等待 5 秒；单个资产失败会打印错误并继续，请检查三个文件是否实际生成。输入至少需小写 `date`、数值型 `close`，应按日期升序排列且每天一行。

绘图使用 `plt.show()`；关闭图窗后脚本继续。CAPM CSV 在图窗关闭后保存。当前不自动导出图片，可通过图窗保存。

可选实验入口：

```powershell
.\.venv\Scripts\python.exe indicators/performance_compare.py
.\.venv\Scripts\python.exe indicators/fama_french.py
.\.venv\Scripts\python.exe indicators/portfolio_analysis.py
.\.venv\Scripts\python.exe indicators/efficient_frontier.py
```

解释实验结果前需阅读功能边界。嵌套目录中的 `data_quality.py` 读取原始文件的 `return` 列，而采集不生成此列，因此不属于正常运行流程。

## 输出说明

| 输出 | 内容 |
| --- | --- |
| data/raw/*.csv | 三只资产的行情 |
| data/processed/AAPL_processed.csv | 保留行的原始字段与 return |
| data/processed/AAPL_drawdown.csv | 处理后字段及 peak、drawdown |
| data/processed/AAPL_CAPM_result.csv | Beta、Daily Alpha、Annual Alpha、R_squared |
| 终端回归摘要 | 样本量、系数、标准误、t 值、p 值、置信区间等 |
| 图窗 | 累计净值、回撤、CAPM 散点与拟合线及实验图 |

`cum_return` 在 CSV 保存后才计算，因此不在处理结果文件中。显著性统计目前只在终端摘要中，未写入 CAPM CSV。

## 方法与计算口径

以收盘价 $P_t$ 计算简单收益 $r_t=P_t/P_{t-1}-1$，每年取 252 个交易日。

### 收益和风险

收益曲线使用 $V_t=\prod_{s\leq t}(1+r_s)$，但计算基于阈值过滤后保留的收益，不能视为完整历史持有净值。

风险脚本从过滤后的价格重新计算收益，使用：

$$R_{ann}=(1+\bar r)^{252}-1,\qquad \sigma_{ann}=s(r)\sqrt{252},\qquad Sharpe_{code}=R_{ann}/\sigma_{ann}$$

其中 $s$ 为样本标准差。当前年化收益是日均收益的复利年化，不是 CAGR；收益/波动比也不同于常用日超额收益 Sharpe。后续应统一为几何年化收益及同频超额收益 Sharpe，而不是混用不同定义。

### 回撤

回撤脚本对处理后收盘价计算 $H_t=\max_{s\leq t}P_s$、$DD_t=P_t/H_t-1$、$MDD=\min_t DD_t$。回撤以负值报告，日期为谷底日期，未计算恢复时间。由于价格样本已删行，其路径与过滤收益复利曲线可能不一致。

### 市场模型

CAPM 脚本按日期内连接 AAPL 与 SPY 收益，估计：

$$r_{AAPL,t}=\alpha+\beta r_{SPY,t}+\varepsilon_t$$

这是原始收益市场模型，或零无风险利率假设下的 CAPM。Beta 为市场敏感度，Alpha 为日度截距，代码使用 $252\alpha$ 做线性年化。R² 是样本内解释比例，不是预测准确率。显著性采用默认 OLS 标准误，未做 HAC 稳健修正。

`fama_french.py` 现使用 Kenneth French 官方日度 RF 和三个因子，估计股票超额收益对 Mkt-RF、SMB、HML 的回归，并在相同样本上重新估计单因子 CAPM。此处 CAPM 使用官方市场因子，与旧 `capm_model.py` 的 SPY 原始收益回归不同，不能直接比较截距。

### 组合实验

固定权重组合采用 $r_{p,t}=\sum_iw_ir_{i,t}$、$252\bar r_p$ 年化收益及零无风险利率假设。固定日权重隐含持续再平衡，未计交易成本。

随机组合从 5,000 次采样中选取 Sharpe 最高的样本，未设置随机种子，也未求解全局最优组合或完整最小方差边界。两个组合脚本需先修复日期对齐，才能解释计算结果。

## 本地验证与结果展示

2026-09-05 使用本地 Python 3.14.7，在隔离副本上用现有数据执行检查、收益、风险、回撤、CAPM、单因子、组合、随机模拟和基准比较，共 9 个入口均正常退出；绘图使用 Agg 后端。未重新联网下载行情，未验证全新虚拟环境安装或交互图窗。依赖版本尚未锁定。

本地数据快照如下（非完整交易日覆盖声明）：

| 资产 | 行数 | 最早日期 | 最晚日期 |
| --- | ---: | --- | --- |
| AAPL | 4,680 | 1984-09-07 | 2026-09-04 |
| MSFT | 4,450 | 1986-03-13 | 2026-09-04 |
| SPY | 6,448 | 2001-01-02 | 2026-09-04 |

三个文件均按日期升序且无重复日期。但 AAPL、MSFT 行数相对日历跨度明显偏少，采集脚本会删除非正复权价格，仍需核查历史覆盖、复权价格和缺失交易日，不能仅凭日期范围认定数据完整。

诊断运行得到最大回撤约 −73.56%（2013-04-19），CAPM Beta 约 1.0846、R² 约 0.1087。它们用于核对当前代码输出，**不是已通过数据质量与频率校验的投资结论**。当前不将年化收益或 Alpha 包装成策略业绩。

作品集展示建议按“累计净值—回撤—市场回归”顺序导出图表，并附共同样本区间、有效日数、价格口径和数据处理说明。先修复下述问题，再形成正式结果比较。

## 已知问题与改进计划

1. **收益频率**：删去绝对收益大于等于 15% 的行后，风险和 CAPM 重新计算价格变化，可能将多日收益作为单日收益。应保留完整时间轴，核查异常原因并记录处理方式。
2. **组合对齐**：目前按行索引拼接，不同资产历史长度不同，会错配交易日。应分别计算收益，再按共同日期合并。
3. **统一指标**：统一年化、无风险收益及样本口径，增加空样本、缺失值、重复日期、零波动检查。
4. **基准比较**：分别构建资产与基准净值，再比较相对净值或累计收益差；避免把日收益差复利称为标准 Alpha。
5. **因子与优化**：接入市场、SMB、HML、无风险利率，增加稳健统计检验、约束优化和样本外评价。
6. **可复现性**：锁定依赖、配置参数、固定随机种子，导出图表与完整回归表，记录数据下载时间及快照。

前复权参数已在源码确认，但公司行动和分红口径尚未独立核查，不能直接称为含分红总收益。项目尚无交易执行、交易成本建模及样本外策略回测。

## 简历项目描述

**项目名称：基于 Python 的美股收益与风险分析**

- 使用 AKShare、pandas 和 NumPy 搭建 AAPL、MSFT、SPY 历史行情采集与处理流程，实现原始行情和分析数据分层保存。
- 实现收益率、波动率、最大回撤分析与可视化，梳理异常收益处理和年化口径对风险评价的影响。
- 使用 statsmodels 构建 AAPL 对 SPY 的 OLS 市场模型，输出 Alpha、Beta、R² 与显著性摘要，并导出回归结果。

以上表述应对应本人实际参与并能解释的工作。三因子已实现，但须说明数据质量限制；组合优化完成后再列为成果；面试可围绕研究问题、数据质量、指标含义、回归解释及改进思路展开。


## Fama-French 三因子（2026-09-06）

模型：`AAPL_return - RF = alpha + beta_m * (Mkt-RF) + beta_s * SMB + beta_h * HML + error`。
因子来源：[Kenneth French 官方美国三因子说明](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html)。
官方日度 CSV 中四项收益均除以 100 转为小数；Mkt-RF 已扣除 RF，不重复扣减。
默认联网获取 ZIP 并保存快照，下载失败则报错，不使用虚构或替代因子。

```powershell
python indicators/fama_french.py
# 离线复现已有快照；使用新输出目录保留首次下载记录
python indicators/fama_french.py --factors data/processed/fama_french/F-F_Research_Data_Factors_daily_CSV.zip --output-dir data/processed/ff3_offline
# 可选 --stock、--start 2020-01-01、--end 2026-07-31、--hac-lags 5
python -m unittest discover -s tests -v
```

脚本使用原始 close，排序并拒绝重复日期、非正或非有限价格。收益计算后核对前一价格日期是否等于官方因子日历的前一交易日，排除跨缺失交易日收益；不按收益幅度删行，不填充价格。日期限制在计算收益后应用，保留区间起点需要的前一日价格。官方文件作为交易日日历，离线输入须为完整官方日度文件。

默认输出到 `data/processed/fama_french/`（重复运行覆盖同名结果）：

- `coefficients.csv`：两模型系数、HAC 标准误、t、p、95% 置信区间。
- `model_comparison.csv`：相同样本下的 R²、调整后 R²、日 Alpha 和线性年化 Alpha。
- `regression_sample.csv`：实际输入、拟合值和残差。
- `date_audit.csv`：每条原始价格的纳入或排除原因。
- `summary.txt`：完整 statsmodels 摘要。
- `metadata.json`：来源、下载与运行时间、SHA256、区间、样本数、排除计数、SMB/HML 联合 Wald 检验。

HAC 默认 5 阶并采用小样本修正与 t 推断。阶数按保留观测计数，跨缺失区间的稳健推断仍有限制。Alpha 年化采用 252 倍日截距，不是策略年化收益。旧收益、组合和 CAPM 脚本的已知问题未在本次修改中全面修复。

本次官方快照截至 2026-07-31。原始 AAPL 4,680 行中，4,648 个收益被纳入，5 行跨缺失交易日、26 行不在因子日历、首行无收益。共同样本为 1984-09-10 至 2026-07-31，跨度不代表连续完整覆盖。CAPM R² = 0.032327，FF3 R² = 0.032878；调整后 R² 分别为 0.032119 和 0.032253。样本保留 52 个绝对收益达到或超过 15% 的观测，前复权价格与分红口径仍需核查，不能据此宣称投资能力或策略绩效。

验证：真实数据联网执行成功；3 项 unittest 覆盖百分数转换、缺失交易日排除、异常幅度保留、重复日期拒绝、已知系数恢复、同样本比较、HAC 和样本不足/共线性拒绝。
