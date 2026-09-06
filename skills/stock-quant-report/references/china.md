# 中国市场参数与因子输入

支持沪深 A 股及场内 ETF，自动识别六位代码、SH/SZ 前缀和 .SH/.SZ/.SS 后缀。`000001` 表示深市平安银行；上证指数不接受作为股票代码。默认基准为 `510300.SH` 沪深300ETF。不同市场不能混合进同一回归/组合，港股、北交所尚不支持。

## 默认运行

```text
python "<skill-dir>/scripts/analyze.py" 600519
python "<skill-dir>/scripts/analyze.py" 000001 600519 --include-ml
```

自动调用 AKShare 腾讯前复权行情、新浪交易日历。未到上海时间 15:10 时不使用当日数据。图表与报告使用最近五年共同完整交易日；存在停牌缺口、非正价格或零成交量时中止，不填充为可交易价格。腾讯是明确配置的 A 股来源，下载失败不静默改用其他来源。

没有中国因子时，运行股票超额收益对国内基准超额收益的市场模型，默认 `--cn-rf-annual 0`，不能把它说成已校准的中国 Fama-French 模型。0 是明确的年化无风险假设，不是已获取的国债利率；可以显式改成其他值。Sharpe、组合预期超额收益与回归使用同一口径。

## 可选中国三/五因子

传入 `--cn-factors /path/china_factors.csv`，同时提供 `china_factors.json`。

CSV 必需列：`date,Mkt-RF,SMB,HML,RF`。若为五因子，另提供 `RMW,CMA`，两列必须同时存在。日期 ISO 格式、每日一行，完整覆盖所选区间。

JSON 示例（只是元数据格式，不是因子数据）：

```json
{
  "market": "CN",
  "frequency": "daily",
  "units": "decimal",
  "source": "填写真实数据提供者、版本和获取方式"
}
```

`units` 只接受 `decimal` 或 `percent`。代码不会根据数值大小猜测单位，也不接受声明为 US 的文件。输入因子的真实性与定义仍需用户核验；本功能只是载入并估计，不自动购买或绕过 CSMAR、RESSET 等数据源权限。若有中国因子，RF 使用该文件的日 RF。

完整离线复现需要：`--prices-dir`（每资产一个 `600519.SH.csv` 或 `600519.csv`，date/close 至少两列）、`--cn-calendar calendar.csv`（date 列）和可选的 `--cn-factors`。中国分支不访问美国因子网址。

## 成本与成交边界

单边比例成本默认 10 bp，涵盖手续费/滑点的粗略假设。股票卖出另按执行日加印花税：2008-09-19 至 2023-08-27 为 10 bp，2023-08-28 起为 5 bp。ETF 不加股票印花税；其他税费没有单独细分。

信号滞后和每日一次调仓意味着新买入仓位不会在同日卖出。模拟器仍使用连续权重和收盘成交近似，未建模整手、最低佣金、涨跌停排队和容量；不能因此宣称完整还原 A 股交易制度。

## 来源

- [AKShare 腾讯日频股票接口](https://akshare.akfamily.xyz/data/stock/stock.html)
- [证券交易印花税调整公告](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211343/content.html)
- [上海证券交易所股票投资说明](https://one.sse.com.cn/onething/gptz/)
