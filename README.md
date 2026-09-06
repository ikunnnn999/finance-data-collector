# 量化投资与资产定价分析框架

以 AAPL、MSFT、SPY 为研究样本，串联数据校验、资产定价回归、Markowitz 组合优化和样本外策略回测。可选运行逻辑回归方向预测基线。

这是已通过本地运行验证的研究原型。所选区间覆盖检查不等于价格真实性核验：AKShare 前复权价格与分红口径尚未独立验证，不能将诊断结果描述为可实现的投资业绩。

## 作为可分享的 Skill 使用

项目现已封装为自带分析引擎的 [stock-quant-report 技能](skills/stock-quant-report/SKILL.md)。支持美股股票与 ETF；输入代码后自动下载行情、官方因子、运行量化分析并输出独立 HTML 报告。

**安装到 Codex：** 将下面这句话发给 Codex：

> 请安装这个 GitHub skill：https://github.com/ikunnnn999/finance-data-collector/tree/main/skills/stock-quant-report

也可以把 `skills/stock-quant-report` 整个文件夹复制到自己的 `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`）。其他兼容 Agent Skills 的工具可按其安装规则放置该文件夹。安装后下一轮输入：

```text
使用 $stock-quant-report 分析 NVDA
使用 $stock-quant-report 分析 AAPL MSFT，并加入机器学习基线
```

无需手动提供数据或作者电脑路径。技能运行时需要 Python 3.11+ 与网络，会在当前工作目录创建独立虚拟环境。默认最近五年、SPY 基准、70%/30% 时间划分和 10 bp 单边成本；可指定日期与成本。代码触发依赖宿主的技能选择，显式 `$stock-quant-report` 调用最明确。

不使用技能宿主也可以直接运行：

```powershell
python skills/stock-quant-report/scripts/analyze.py NVDA
```

默认结果在当前工作目录 `outputs/<代码>-quant-<时间>/report.html`，另有 Markdown、PNG、CSV 和数据快照。每次生成新的目录。所选市场暂为美股；不会用美国因子分析 A 股/港股。价格与因子可能有发布日期差，实际共同截止日会写进报告。

技能发布目录自带分析引擎，完整文件夹安装即可运行。维护者修改项目引擎后执行 `python tools/build_skill.py` 同步发布副本，测试会检测不同步。原始下载数据、虚拟环境和用户报告不放进 skill，也不提交到 Git。

已在 Windows / Python 3.14 的全新独立环境中验证 NVDA 联网下载到完整报告的流程；技能格式校验和 16 项测试通过。其他系统使用可移植路径实现，尚未实机验证。

## 运行

从项目根目录执行，Python 环境需安装依赖：

```powershell
python -m pip install -r requirements.txt
# 已有 data/raw/AAPL.csv、MSFT.csv、SPY.csv 时，无需重新采集
python run_research.py
# 可选：加入样本外方向预测实验
python run_research.py --include-ml
python -m unittest discover -s tests -v
```

默认训练区间从 2020 年开始，2024 年起样本外评价；结束日期取两份官方因子数据的共同末日。为避免在获知收盘价的同时假定成交，最后一个训练期交易日留作执行日，组合参数只估计到它的前一交易日。

默认输出 `data/processed/research/`，同名文件会覆盖；需要保留不同实验时指定不同 `--output-dir`。正式比较前先固定样本期与参数，避免按测试期表现反复选择策略。

```powershell
python run_research.py --start 2020-01-01 --train-end 2023-12-31 --end 2026-07-31 --cost-bps 10 --fast 20 --slow 60 --include-ml --output-dir data/processed/research_v1
```

首次联网获取官方三因子、五因子 ZIP。离线复现时使用已保存的两份原始 ZIP，输入必须为完整官方日度文件，数值单位为百分数：

```powershell
python run_research.py --ff3 data/processed/research/F-F_Research_Data_Factors_daily_CSV.zip --ff5 data/processed/research/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip --include-ml --output-dir data/processed/research_offline
```

如果首次用 `--ff3` 或 `--ff5` 指定已有快照，该快照保持在原位置；离线参数应使用 manifest.json 记录的实际路径。下载失败会报错，不以模拟数据替代。

## 模块

| 模块 | 实现 | 主要边界 |
| --- | --- | --- |
| `quant/data.py` | 共同交易日面板、缺失/重复/无效价格拒绝、异常收益计数 | 使用官方因子日期作为交易日日历，不验证公司行动 |
| `indicators/fama_french.py` | CAPM、FF3、FF5、HAC t/p、95% CI、显著性、调整后 R²、联合检验 | 样本内解释；p 值未作多重检验修正 |
| `quant/portfolio.py` | 非负权重、权重和为 1、最小方差、最大 Sharpe、目标收益有效前沿 | 样本均值/协方差敏感，未加入参数收缩或权重上限 |
| `quant/backtest.py` | 权重漂移、月末再平衡、现金 RF、按交易额计成本、逐日账本 | 收盘成交近似；未建模税费、容量与市场冲击 |
| `quant/metrics.py` | 几何年化、日超额 Sharpe、波动、初始资本起算回撤 | 只接受连续交易日的同频收益 |
| `quant/direction.py` | L2 逻辑回归、训练集标准化、扩展窗口预测、朴素基线 | 可选实验，无测试集调参和实盘预测能力声明 |
| `run_research.py` | 统一运行、CSV、报告、PNG、参数/数据/代码指纹和版本 | 原始数据质量仍决定结果有效性 |

旧的 `indicators/portfolio_analysis.py` 与 `indicators/efficient_frontier.py` 已转为统一框架的兼容入口，接受与 `run_research.py` 相同的参数。随机组合云图已替换为约束优化求得的有效前沿。

## 资产定价口径

三因子：

`R_AAPL - RF = alpha + beta_m*(Mkt-RF) + beta_s*SMB + beta_h*HML + error`

五因子再加入 `beta_r*RMW + beta_c*CMA`。RMW 是盈利因子，CMA 是投资因子；四项/六项官方收益读入后除以 100。Mkt-RF 已扣除 RF，不再重复扣减。

[官方三因子说明](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html) · [官方五因子说明](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html)

五因子版 SMB 将价值、盈利、投资分组的规模因子综合起来，与官方三因子 SMB 不同。因此五因子文件中的三项约束回归命名为 `FF3_restricted_FF5`；RMW/CMA 联合检验相对于它进行。官方 FF3 与 FF5 的调整后 R² 可以在同样本下对照，但不能当作仅增加两列的简单嵌套模型。

回归含截距，HAC 默认 5 阶、小样本修正、t 推断。结果输出 t、p、95% 置信区间及 `*** p<0.01 / ** p<0.05 / * p<0.10`。不显著意味着证据不足，不代表真实效应必定为零；显著不等于因果关系或可交易收益。线性年化 Alpha 为 `252*日截距`。

```powershell
python indicators/fama_french.py
python indicators/fama_french.py --five-factor --start 2020-01-01 --output-dir data/processed/ff5
```

独立回归入口可对有缺口的较长历史进行诊断，但只纳入前后价格对应相邻因子交易日的收益，并导出逐行排除原因。统一框架对指定区间更严格：任何资产有缺失交易日就中止，不填充、不截尾、不靠删行修复数据。

## 投资组合与回测口径

- 组合参数只用训练数据，均值和协方差按 252 年化。最小方差和有效前沿通过 SLSQP 约束优化求解，并检查求解状态、权重和目标收益约束。
- 最大 Sharpe 使用训练期平均 RF；有正超额收益时采用凸变换求解，所有超额收益非正时比较单资产顶点。均值、协方差与有效前沿只是训练期估计，不是未来保证。
- 优化组合与等权组合在月末收盘恢复固定目标权重，使其在下月首个交易日收益中生效。买入持有允许自然漂移，不持续恢复固定权重。
- 均线默认 20/60：t 日收盘形成信号，t+1 日收盘成交，t+2 日的收盘到收盘收益才使用该仓位。空仓现金按每日 RF 计息。
- 单边成本默认 10 bp，包含首次建仓与退出，按实际交易金额/交易前净值计算；以扣费后目标净值解成本方程。期末标记市值，不假定清仓。
- 几何年化 = `(累计净值)^(252/有效日数)-1`；波动为样本日收益标准差乘 `sqrt(252)`；Sharpe 为日超额收益均值/标准差乘 `sqrt(252)`；最大回撤包含初始净值 1。

净收益与毛收益、换手和交易日数一起导出，比较包括最小方差组合、训练期最大 Sharpe 组合、等权组合、AAPL/SPY 买入持有、AAPL 均线策略。

## 可选机器学习基线

使用 1 日收益、5/20 日动量、20 日波动和价格/均线比预测收益正负。特征滞后两日以留出成交时点，按时间顺序扩展训练窗口，每 63 个交易日重估；训练标签截止首个预测日前两个交易日。每次标准化仅用训练集，L2 系数固定 0.01、分类阈值固定 0.5，不用测试集调参。

输出方向准确率、平衡准确率、Brier 分数、训练集多数类基线、恒预测上涨基线，以及长仓/现金转换后的扣费回测。方向预测结果和策略盈利分开解释。当前基线不是经过验证的预测优势。

## 结果文件

| 文件 | 内容 |
| --- | --- |
| `report.md` | 中文研究报告与图表 |
| `ff3/`、`ff5/` | 回归系数、比较、解释、样本、审计、完整摘要 |
| `factor_model_comparison.csv` | 同区间各模型比较 |
| `portfolio_weights.csv`、`efficient_frontier.csv` | 组合权重和真正的有效前沿 |
| `portfolio_training_estimates.csv` | 训练期预期收益、风险、Sharpe |
| `strategy_metrics.csv`、`backtest_*.csv` | 样本外绩效与逐日持仓/成本账本 |
| `data_quality.csv`、`daily_returns.csv` | 覆盖与异常计数、日期对齐收益 |
| `direction_*.csv/json` | 可选预测、评分、每折标准化与模型参数 |
| `manifest.json` | 参数、训练/测试日期、输入与代码 SHA256、版本 |
| `*.png` | 有效前沿、样本外净值及回撤图 |

2026-09-06 本地全流程验证：2020-01-02 至 2026-07-31 共 1,653 个连续收益日；训练估计截至 2023-12-28，2023-12-29 收盘用于首次执行；样本外 647 日。FF3 调整后 R² 约 0.6154，FF5 约 0.6644，FF5 Alpha p≈0.314。逻辑回归方向准确率约 53.63%，低于恒预测上涨的 53.94%。这与此前全历史诊断样本不同，不能直接比较 R² 的变化。

关键测试覆盖单位转换、因子系数恢复、缺失交易日拒绝、解析列顺序、优化解与解析/网格解比较、交易成本和权重漂移、初始回撤、信号延迟以及修改未来数据不会改变过去预测。测试与本地真实数据运行不等于完成分红复权核验、第三方数据核对或全新环境安装验证。

## 早期代码与下一步

早期采集、收益、风险、回撤、SPY 市场模型等脚本仍保留；它们的旧口径与局限见 [历史分析说明](docs/legacy-analysis.md)。统一框架直接读取 raw 数据，不依赖旧脚本过滤后的 processed 价格。历史说明中的旧结果和未完成事项只描述当时版本。

下一步优先核验价格与分红、加入多窗口稳定性及成本敏感性分析，再考虑参数收缩、扩大资产池与更严格的样本外评价。不要仅因模型更多或某一回测表现较好就宣称框架达到发表或实盘标准。
