"""Reproducible asset-pricing, portfolio and out-of-sample strategy research."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from indicators.fama_french import ROOT, URL, URL5, read_factors
from quant.data import load_panel
from quant.metrics import performance
from quant.portfolio import optimize_portfolios
from quant.backtest import simulate, moving_average_targets
from quant.direction import walk_forward_direction


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def markdown_table(frame):
    header = '| ' + ' | '.join(map(str, frame.columns)) + ' |'
    separator = '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |'
    rows = ['| ' + ' | '.join(map(str, row)) + ' |' for row in frame.itertuples(index=False, name=None)]
    return '\n'.join([header, separator, *rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/research')
    parser.add_argument('--start', default='2020-01-01')
    parser.add_argument('--end', help='Default: last common factor date')
    parser.add_argument('--train-end', default='2023-12-31')
    parser.add_argument('--cost-bps', type=float, default=10.)
    parser.add_argument('--fast', type=int, default=20)
    parser.add_argument('--slow', type=int, default=60)
    parser.add_argument('--hac-lags', type=int, default=5)
    parser.add_argument('--ff3', type=Path, help='Official daily three-factor snapshot for offline execution')
    parser.add_argument('--ff5', type=Path, help='Official daily five-factor snapshot for offline execution')
    parser.add_argument('--include-ml', action='store_true', help='Expanding-window logistic baseline; fixed hyperparameters')
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    sources = []
    snapshots = {}
    for name, supplied, url in [('ff3', args.ff3, URL), ('ff5', args.ff5, URL5)]:
        downloaded = None
        path = supplied
        if path is None:
            path = out / url.rsplit('/', 1)[-1]
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
            downloaded = datetime.now(timezone.utc).isoformat()
        factors = read_factors(path)
        if ('RMW' in factors) != (name == 'ff5'):
            raise ValueError(f'{name}: wrong factor dataset supplied')
        snapshots[name] = (path, factors)
        sources.append(dict(name=name, path=str(path.resolve()), source=url, downloaded_utc=downloaded,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    calendar = snapshots['ff3'][1].date
    end = args.end or str(min(f.date.max() for _, f in snapshots.values()).date())
    if not pd.Timestamp(args.start) < pd.Timestamp(args.train_end) < pd.Timestamp(end):
        raise ValueError('Require start < train-end < end')
    symbols = ['AAPL', 'MSFT', 'SPY']
    prices, returns, audit = load_panel(args.raw_dir, symbols, calendar, args.start, end)
    rf = snapshots['ff3'][1].set_index('date').RF.reindex(returns.index)
    audit.to_csv(out / 'data_quality.csv', index=False)
    returns.to_csv(out / 'daily_returns.csv')
    for name, (path, factors) in snapshots.items():
        if not returns.index.isin(factors.date).all():
            raise ValueError('Factor datasets do not cover the same requested sessions')
        command = [sys.executable, str(ROOT / 'indicators/fama_french.py'), '--stock', str(args.raw_dir / 'AAPL.csv'),
                   '--factors', str(path), '--start', args.start, '--end', end,
                   '--hac-lags', str(args.hac_lags), '--output-dir', str(out / name)]
        if name == 'ff5':
            command.append('--five-factor')
        result = subprocess.run(command, capture_output=True, text=True)
        (out / f'{name}_run.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'{name} regression failed; see {name}_run.log: {result.stderr}')
        regression_dates = pd.DatetimeIndex(pd.read_csv(out / name / 'regression_sample.csv', parse_dates=['date']).date)
        if not regression_dates.equals(returns.index):
            raise ValueError('Regression samples differ from the complete research date panel')
    # Reserve the last pre-test close for execution; weights use earlier data only.
    pretest = returns.loc[:args.train_end]
    train = pretest.iloc[:-1]
    test = returns.loc[returns.index > pd.Timestamp(args.train_end)]
    if len(train) < max(252, args.slow + 2) or len(test) < 30:
        raise ValueError('Need >=252 training and >=30 test observations')
    weights, frontier, estimates = optimize_portfolios(train, rf.loc[train.index])
    weights.to_csv(out / 'portfolio_weights.csv')
    estimates.to_csv(out / 'portfolio_training_estimates.csv')
    frontier.to_csv(out / 'efficient_frontier.csv', index=False)
    train.cov().mul(252).to_csv(out / 'training_covariance.csv')
    results = {}
    for name, w in weights.iterrows():
        target = pd.DataFrame(np.tile(w, (len(test), 1)), index=test.index, columns=symbols)
        results[name] = simulate(test, rf.loc[test.index], target, args.cost_bps, 'monthly')
    for symbol in ['AAPL', 'SPY']:
        target = pd.DataFrame(0., index=test.index, columns=symbols)
        target[symbol] = 1.
        results[symbol + '_buy_hold'] = simulate(test, rf.loc[test.index], target, args.cost_bps, 'buy_and_hold')
    target = pd.DataFrame(0., index=test.index, columns=symbols)
    target['AAPL'] = moving_average_targets(prices.AAPL, test.index, args.fast, args.slow)
    results['AAPL_moving_average'] = simulate(test, rf.loc[test.index], target, args.cost_bps)
    prediction_scores = None
    if args.include_ml:
        predictions, prediction_scores, folds = walk_forward_direction(prices.AAPL, returns.AAPL, test.index)
        predictions.to_csv(out / 'direction_predictions.csv')
        save_json(out / 'direction_scores.json', prediction_scores)
        save_json(out / 'direction_folds.json', folds)
        target = pd.DataFrame(0., index=test.index, columns=symbols)
        target['AAPL'] = predictions.predicted_up
        results['AAPL_logistic'] = simulate(test, rf.loc[test.index], target, args.cost_bps)
    metrics = []
    for name, result in results.items():
        result.to_csv(out / f'backtest_{name}.csv')
        stats = performance(result.net_return, rf.loc[test.index])
        gross = performance(result.gross_return, rf.loc[test.index])
        metrics.append(dict(strategy=name, **stats, gross_total_return=gross['total_return'],
                            aggregate_turnover=float(result.turnover.sum()),
                            trade_sessions=int((result.turnover > 1e-9).sum())))
    metrics = pd.DataFrame(metrics).set_index('strategy')
    metrics.to_csv(out / 'strategy_metrics.csv')
    fig, ax = plt.subplots(figsize=(9, 5), layout='constrained')
    ax.plot(frontier.annual_volatility, frontier.expected_annual_return, label='Constrained efficient frontier')
    for name, row in estimates.iterrows():
        ax.scatter(row.annual_volatility, row.expected_annual_return, s=60, label=name.replace('_', ' '))
    ax.set(xlabel='Annual volatility', ylabel='Expected annual arithmetic return', title='Training-sample Markowitz frontier')
    ax.legend(fontsize=8)
    ax.grid(alpha=.25)
    fig.savefig(out / 'efficient_frontier.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, layout='constrained')
    for name, result in results.items():
        axes[0].plot(result.index, result.wealth, label=name.replace('_', ' '))
        axes[1].plot(result.index, result.drawdown)
    axes[0].set(ylabel='Net wealth (initial = 1)', title='Out-of-sample comparison (unverified price data)')
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].set(ylabel='Drawdown', xlabel='Date')
    for ax in axes:
        ax.grid(alpha=.25)
    fig.savefig(out / 'strategy_comparison.png', dpi=160)
    plt.close(fig)
    manifest = dict(run_utc=datetime.now(timezone.utc).isoformat(), parameters={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                    sources=sources, training_start=str(train.index[0].date()), training_end=str(train.index[-1].date()),
                    initial_execution_close=str(pretest.index[-1].date()), test_start=str(test.index[0].date()),
                    test_end=str(test.index[-1].date()), training_rows=len(train), test_rows=len(test),
                    versions={name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'statsmodels', 'matplotlib']},
                    python=sys.version, price_hashes={s: hashlib.sha256((args.raw_dir / f'{s}.csv').read_bytes()).hexdigest() for s in symbols},
                    code_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), ROOT / 'indicators/fama_french.py', *sorted((ROOT / 'quant').glob('*.py'))]})
    save_json(out / 'manifest.json', manifest)
    comparisons = []
    for name in ['ff3', 'ff5']:
        frame = pd.read_csv(out / name / 'model_comparison.csv')
        frame.insert(0, 'factor_file', name)
        comparisons.append(frame)
    combined = pd.concat(comparisons, ignore_index=True)
    combined.to_csv(out / 'factor_model_comparison.csv', index=False)
    final_coefficients = pd.read_csv(out / 'ff5/coefficients.csv').query("model == 'FF5'")
    coefficient_display = final_coefficients[['term', 'coefficient', 't', 'p', 'significance']].copy().fillna('')
    for col in ['coefficient', 't']:
        coefficient_display[col] = coefficient_display[col].map(lambda v: f'{v:.4f}')
    coefficient_display['p'] = coefficient_display['p'].map(lambda v: f'{v:.4g}')
    alpha_p = float(final_coefficients.loc[final_coefficients.term == 'const', 'p'].iloc[0])
    alpha_conclusion = '截距在 5% 水平显著，但不能直接解释为可实现超额收益。' if alpha_p < .05 else '截距在 5% 水平不显著，尚不足以认定存在非零 Alpha。'
    factor_display = combined[['factor_file', 'model', 'n', 'r_squared', 'adjusted_r_squared']].copy()
    factor_display[['r_squared', 'adjusted_r_squared']] = factor_display[['r_squared', 'adjusted_r_squared']].map(lambda v: f'{v:.4f}')
    weight_display = weights.map(lambda v: f'{v:.2%}').rename_axis('组合').reset_index()
    metric_display = metrics[['total_return', 'geometric_annual_return', 'annual_volatility', 'sharpe', 'max_drawdown']].copy()
    for col in metric_display.columns:
        metric_display[col] = metric_display[col].map(lambda v, col=col: f'{v:.3f}' if col == 'sharpe' else f'{v:.2%}')
    metric_display = metric_display.rename(columns={'total_return': '累计净收益', 'geometric_annual_return': '几何年化',
                                'annual_volatility': '年化波动', 'sharpe': 'Sharpe', 'max_drawdown': '最大回撤'}).reset_index()
    report = ['# 量化投资与资产定价研究报告', '',
              f'训练样本：{manifest["training_start"]} 至 {manifest["training_end"]}；样本外：{manifest["test_start"]} 至 {manifest["test_end"]}。',
              '因子回归使用完整所选区间，属于样本内解释；组合权重只使用训练期估计。', '',
              '## 数据与解释边界', '',
              '本地价格的复权与分红口径未独立验证。完整所选交易日内不填充、不截尾、不按收益幅度删行；异常只记录。',
              '预先选择的三只现存资产存在选择偏差。结果为研究原型诊断，不代表可实现的投资业绩。', '',
              '## 因子回归', '', markdown_table(factor_display), '',
              '五因子系数（const 为日度 Alpha；*** p<0.01，** p<0.05，* p<0.10）：', '',
              markdown_table(coefficient_display), '', alpha_conclusion, '',
              '各模型 t、p、95% 置信区间、显著性星号及解释见 ff3/ 和 ff5/。HAC 默认 5 阶。',
              'FF3_restricted_FF5 使用五因子版 SMB；RMW/CMA 的联合检验相对于该约束模型。官方 FF3 与 FF5 不是简单嵌套比较。',
              '显著性不等于经济价值、因果关系或预测能力；多个检验的 p 值未作多重比较修正。', '',
              '## 组合优化', '', markdown_table(weight_display), '',
              '非负权重、和为 1；训练期样本均值/协方差，年化 252。有效前沿是目标收益约束下的最小方差解。',
              '最大 Sharpe 使用训练期平均 RF。正超额收益情形用凸变换求解，非正情形比较顶点。',
              '![训练期有效前沿](efficient_frontier.png)', '',
              '## 样本外策略比较', '', markdown_table(metric_display), '',
              f'单边成本 {args.cost_bps:g} bp，包含首次建仓；成本按交易额计入，期末按市值结算，不强制清仓。',
              '优化组合和等权组合在月末收盘恢复训练期固定目标权重，于下一月首交易日收益生效；非再平衡日允许权重漂移。买入持有不再平衡。',
              f'均线参数 {args.fast}/{args.slow}：t 日收盘形成信号，t+1 收盘执行，收益从 t+1 至 t+2 计入。',
              '空仓现金按每日 RF 计息；无杠杆、无卖空。滑点与手续费合并为固定比例成本，未模拟税费和市场冲击。',
              '几何年化按实际观测日数；Sharpe 为日超额均值/日超额标准差乘 sqrt(252)；回撤包含初始净值 1。',
              '![样本外净值与回撤](strategy_comparison.png)', '']
    if prediction_scores:
        report += ['## 可选方向预测基线', '', '```json', json.dumps(prediction_scores, indent=2), '```',
                   'L2 逻辑回归，历史收益/动量/波动/均线特征；特征滞后两日，每 63 个交易日扩展窗口重估。',
                   '标准化只用训练集，训练标签截止首个预测日之前两个交易日；未随机划分、未用测试期调参。',
                   '与训练集多数类及恒预测上涨比较。方向准确率不等同于扣费后的策略盈利。', '']
        if prediction_scores['accuracy'] <= prediction_scores['majority_baseline_accuracy']:
            report += ['本次方向准确率未超过多数类基线，当前实验未显示预测优势。', '']
    report += ['## 来源与复现', '',
               '[官方三因子数据](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library/f-f_factors.html) · '
               '[官方五因子构造](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html) · '
               '[SciPy 约束优化](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize.html)', '',
               '配置、输入与代码 SHA256、运行时间和版本见 manifest.json；原始因子 ZIP 可用于离线复现。']
    (out / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print(metrics.to_string())
    print('Report:', (out / 'report.md').resolve())


if __name__ == '__main__':
    main()
