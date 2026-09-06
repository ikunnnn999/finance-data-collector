"""Download US tickers and generate a portable HTML quantitative report."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from html import escape
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from indicators.fama_french import ROOT, URL, URL5, read_factors
from quant.data import load_panel
from quant.metrics import performance


def ticker(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,4})?', value) or value.endswith(('.HK', '.SS', '.SZ', '.L', '.TO')):
        raise argparse.ArgumentTypeError('Use a US stock/ETF ticker such as AAPL or NVDA; other markets are not supported')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{i}' for prefix in ['COM', 'LPT'] for i in range(1, 10)}
    if value.split('.')[0] in reserved:
        raise argparse.ArgumentTypeError('Ticker conflicts with a reserved filesystem name')
    return value


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def acquire_stock(symbol, path):
    import akshare as ak
    frame = ak.stock_us_daily(symbol=symbol, adjust='qfq')
    if frame.empty or not {'date', 'close'}.issubset(frame.columns):
        raise ValueError(f'{symbol}: provider returned no usable prices')
    # Preserve the provider snapshot, including invalid historical rows for audit.
    frame.to_csv(path, index=False)


def choose_dates(frames, calendar, start=None, end=None, train_end=None):
    calendar = pd.DatetimeIndex(calendar)
    requested_end = pd.Timestamp(end) if end else calendar.max()
    last_price = min(frame.date.max() for frame in frames.values())
    cutoff = min(requested_end, calendar.max(), last_price, pd.Timestamp(datetime.now(timezone.utc).date()))
    eligible = calendar[calendar <= cutoff]
    if eligible.empty:
        raise ValueError('No common completed trading sessions')
    effective_end = eligible[-1]
    desired_start = pd.Timestamp(start) if start else effective_end - pd.DateOffset(years=5)
    first_common_price = max(frame.date.min() for frame in frames.values())
    if start and desired_start <= first_common_price:
        raise ValueError('Requested start lacks a preceding common price; choose a later start')
    earliest_return = max(desired_start, first_common_price + pd.Timedelta(days=1))
    dates = calendar[(calendar >= earliest_return) & (calendar <= effective_end)]
    if len(dates) < 30:
        raise ValueError('Fewer than 30 common sessions; cannot estimate the requested factor regressions reliably')
    split = pd.Timestamp(train_end) if train_end else dates[max(1, int(len(dates) * .7)) - 1]
    if not dates[0] < split < dates[-1]:
        raise ValueError('Training cutoff must lie inside the analysis period')
    train_rows = int((dates <= split).sum()) - 1
    test_rows = int((dates > split).sum())
    full = train_rows >= 252 and test_rows >= 30
    return dates, split, full


def html_report(out, symbols, metadata, asset_metrics, analysis, partial_reason):
    primary = symbols[0]
    def table(frame):
        return '<div class="table-wrap">' + frame.to_html(index=False, border=0, float_format=lambda v: f'{v:.5g}', escape=True) + '</div>'
    def picture(path, title):
        if not path.exists():
            return ''
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        return f'<figure><img src="data:image/png;base64,{encoded}" alt="{escape(title)}"><figcaption>{escape(title)}</figcaption></figure>'
    first = asset_metrics.iloc[0]
    cards = ''.join(f'<div class="card"><span>{label}</span><strong>{value}</strong></div>' for label, value in [
        ('累计价格收益', f'{first.total_return:.2%}'), ('几何年化', f'{first.geometric_annual_return:.2%}'),
        ('年化波动', f'{first.annual_volatility:.2%}'), ('最大回撤', f'{first.max_drawdown:.2%}')])
    sections = [f'<section><h2>价格收益与风险</h2><p>全分析区间；未扣交易成本。复权与分红口径未独立核验。</p>{table(asset_metrics)}{picture(out / "asset_overview.png", "完整分析区间的价格净值与回撤")}</section>']
    comparisons = []
    for name in ['ff3', 'ff5']:
        comparison = pd.read_csv(analysis / name / 'model_comparison.csv')
        comparison.insert(0, 'factor_file', name)
        comparisons.append(comparison)
    combined = pd.concat(comparisons, ignore_index=True)
    coefs = pd.read_csv(analysis / 'ff5/coefficients.csv').fillna('')
    alpha = coefs[(coefs.model == 'FF5') & (coefs.term == 'const')].iloc[0]
    interpretation = 'Alpha 在 5% 水平不显著，尚不足以认定存在非零超额收益。' if float(alpha.p) >= .05 else 'Alpha 在 5% 水平显著；这不证明因果关系或可实现的交易收益。'
    sections += [f'<section><h2>资产定价回归</h2>{table(combined)}<h3>五因子系数与显著性</h3>{table(coefs[coefs.model == "FF5"])}<p>{interpretation}</p><p>HAC 稳健统计；*** p&lt;0.01，** p&lt;0.05，* p&lt;0.10。五因子版 SMB 与官方三因子 SMB 不同，约束模型标记为 FF3_restricted_FF5。R² 是样本内解释度；annual_alpha_linear 为 252 倍日截距，不是策略年化收益。</p></section>']
    if (analysis / 'strategy_metrics.csv').exists():
        run = json.loads((analysis / 'manifest.json').read_text(encoding='utf-8'))
        strategies = pd.read_csv(analysis / 'strategy_metrics.csv')
        weights = pd.read_csv(analysis / 'portfolio_weights.csv').rename(columns={'Unnamed: 0': 'portfolio'})
        sections += [f'<section><h2>训练期组合优化</h2>{table(weights)}{picture(analysis / "efficient_frontier.png", "非负权重且权重和为 1 的 Markowitz 有效前沿")}</section>',
                     f'<section><h2>样本外策略回测</h2><p>训练：{run["training_start"]} 至 {run["training_end"]}；样本外：{run["test_start"]} 至 {run["test_end"]}。</p><p>单边成本 {metadata["cost_bps"]:g} bp，含首次建仓；训练期末保留一个收盘日用于执行。均线信号产生后的下一个收盘成交，收益再从下一交易日计入。现金按 RF 计息，期末不强制清仓。</p>{table(strategies)}{picture(analysis / "strategy_comparison.png", "样本外扣费净值与最大回撤路径")}</section>']
    elif partial_reason:
        sections += [f'<section class="notice"><h2>本次未运行的模块</h2><p>{escape(partial_reason)}</p></section>']
    if (analysis / 'direction_scores.json').exists():
        scores = json.loads((analysis / 'direction_scores.json').read_text(encoding='utf-8'))
        conclusion = '方向准确率未超过多数类基线，目前未显示预测优势。' if scores['accuracy'] <= scores['majority_baseline_accuracy'] else '本样本准确率超过多数类基线，仍需更多独立样本验证。'
        sections += [f'<section><h2>可选方向预测</h2>{table(pd.DataFrame([scores]))}<p>{conclusion}扩展训练窗口、训练集标准化、特征滞后两日；没有测试集调参。</p></section>']
    elif metadata.get('ml_skipped_reason'):
        sections += [f'<section class="notice"><h2>未运行方向预测</h2><p>{escape(metadata["ml_skipped_reason"])}</p></section>']
    document = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TITLE</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#192b40;font:16px/1.7 system-ui,-apple-system,"Microsoft YaHei",sans-serif}main{max-width:1120px;margin:auto;padding:40px 24px}header{padding:32px;background:#142d4e;border-radius:18px;color:white}h1{font-size:34px;margin:8px 0}header p{color:#d2dcec}small{color:#97c6d3;letter-spacing:.1em}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card,section{background:white;border:1px solid #e1e7ef;border-radius:14px;padding:24px}.card span{display:block;color:#5c6d7e;font-size:14px}.card strong{font-size:26px}section{margin:20px 0}h2{margin:0 0 12px;font-size:23px}h3{font-size:18px}p{color:#4d6074}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:right;padding:10px 12px;border-bottom:1px solid #e8edf3;white-space:nowrap}th{background:#eef3f8}th:first-child,td:first-child{text-align:left}img{max-width:100%;height:auto}figure{margin:20px 0}figcaption{color:#65778b;font-size:13px}.notice{border-left:4px solid #bf8532}a{color:#176c91}footer{font-size:13px;color:#65778b}@media(max-width:650px){main{padding:16px}.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:27px}header,section{padding:20px}}@media print{body{background:white}main{max-width:none;padding:0}section,header{break-inside:avoid}.table-wrap{overflow:visible}table{font-size:10px}.cards{grid-template-columns:repeat(4,1fr)}}
    </style></head><body><main>CONTENT</main></body></html>'''
    heading = f'<header><small>STOCK QUANT REPORT · US EQUITIES</small><h1>{escape(primary)} 量化分析报告</h1><p>资产池：{escape(", ".join(symbols))}<br>分析：{metadata["analysis_start"]} — {metadata["analysis_end"]} · {metadata["observations"]} 个交易日<br>因子截止：{metadata["factor_end"]} · 生成时间：{escape(metadata["run_utc"])}</p></header><div class="cards">{cards}</div>'
    notice = f'<section class="notice"><h2>数据说明</h2><p>来源：{escape(metadata["price_source"])}。没有删去异常收益，也没有填充缺失交易日；无效价格或缺口会使分析停止。复权与分红口径未独立验证，结果是研究诊断，不能等同于可实现的投资业绩。美国因子只用于当前美股范围。</p></section>'
    footer = '<footer>数据来源：<a href="https://akshare.akfamily.xyz/data/stock/stock.html">AKShare</a> · <a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html">Kenneth French Data Library</a>。输入快照、日期审计及 SHA256 见同目录 acquisition.json 和 analysis/manifest.json（完整模式）。</footer>'
    (out / 'report.html').write_text(document.replace('TITLE', escape(primary + ' 量化分析报告')).replace('CONTENT', heading + notice + ''.join(sections) + footer), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('symbols', nargs='+', type=ticker)
    parser.add_argument('--benchmark', type=ticker, default='SPY')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--train-end')
    parser.add_argument('--cost-bps', type=float, default=10)
    parser.add_argument('--include-ml', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--prices-dir', type=Path, help='Explicit offline provider snapshots, date/close CSV per ticker')
    parser.add_argument('--ff3', type=Path)
    parser.add_argument('--ff5', type=Path)
    args = parser.parse_args()
    if not 0 <= args.cost_bps < 1000:
        parser.error('--cost-bps must be between 0 and 1000 (exclusive)')
    symbols = list(dict.fromkeys([*args.symbols, args.benchmark]))
    if len(symbols) > 8:
        parser.error('Limit each report to 8 tickers including the benchmark')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = args.output_dir or Path.cwd() / 'outputs' / f'{args.symbols[0]}-quant-{stamp}'
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Output directory is not empty; choose a fresh path to preserve earlier reports')
    out.mkdir(parents=True, exist_ok=True)
    metadata = dict(run_utc=datetime.now(timezone.utc).isoformat(), symbols=symbols, cost_bps=args.cost_bps,
                    requested_start=args.start, requested_end=args.end, price_source='AKShare stock_us_daily / Sina qfq' if not args.prices_dir else 'User-supplied date/close CSV snapshots',
                    inputs=[], versions={name: importlib.metadata.version(name) for name in ['pandas', 'numpy', 'scipy', 'statsmodels', 'matplotlib', 'akshare']})
    try:
        price_dir = out / 'inputs/prices'
        source_dir = out / 'inputs/source_prices'
        factor_dir = out / 'inputs/factors'
        for directory in [price_dir, source_dir, factor_dir]:
            directory.mkdir(parents=True)
        factors = {}
        for name, url, supplied in [('ff3', URL, args.ff3), ('ff5', URL5, args.ff5)]:
            print(f'Loading {name} factors...', flush=True)
            path = factor_dir / url.rsplit('/', 1)[-1]
            if supplied:
                shutil.copyfile(supplied, path)
            else:
                with urllib.request.urlopen(url, timeout=60) as response:
                    path.write_bytes(response.read())
            frame = read_factors(path)
            if ('RMW' in frame) != (name == 'ff5'):
                raise ValueError(f'{name}: wrong factor file')
            factors[name] = (path, frame)
            metadata['inputs'].append(dict(name=name, source=url, downloaded=not bool(supplied), acquired_utc=datetime.now(timezone.utc).isoformat(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        frames = {}
        for symbol in symbols:
            print(f'Loading {symbol} daily prices...', flush=True)
            path = source_dir / f'{symbol}.csv'
            if args.prices_dir:
                shutil.copyfile(args.prices_dir / f'{symbol}.csv', path)
            else:
                worker = subprocess.run([sys.executable, str(Path(__file__).resolve()), '_download', symbol, str(path)], capture_output=True, text=True, timeout=120)
                if worker.returncode:
                    raise RuntimeError(f'{symbol}: download failed; {worker.stderr[-1200:]}')
            frame = pd.read_csv(path)
            frame['date'] = pd.to_datetime(frame['date'], errors='raise')
            if frame.date.hasnans or frame.date.duplicated().any():
                raise ValueError(f'{symbol}: duplicate or invalid dates')
            frame = frame.sort_values('date')
            frames[symbol] = frame
            metadata['inputs'].append(dict(name=symbol, source=metadata['price_source'], acquired_utc=datetime.now(timezone.utc).isoformat(),
                downloaded=not bool(args.prices_dir), rows=len(frame), first_date=str(frame.date.min().date()), last_date=str(frame.date.max().date()), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        common_end = min(frame.date.max() for _, frame in factors.values())
        calendar = pd.DatetimeIndex(factors['ff3'][1].date)
        calendar = calendar[calendar <= common_end]
        dates, split, full = choose_dates(frames, calendar, args.start, args.end, args.train_end)
        metadata.update(analysis_start=str(dates[0].date()), analysis_end=str(dates[-1].date()),
                        train_cutoff=str(split.date()), factor_end=str(common_end.date()), observations=len(dates), mode='full' if full else 'partial')
        position = calendar.get_loc(dates[0])
        if position == 0:
            raise ValueError('Factor calendar lacks the preceding session')
        previous = calendar[position - 1]
        for symbol, frame in frames.items():
            # Select an interval, never delete observations based on price/return magnitude.
            frame.loc[frame.date.between(previous, dates[-1])].to_csv(price_dir / f'{symbol}.csv', index=False)
        prices, returns, audit = load_panel(price_dir, symbols, calendar, dates[0], dates[-1])
        rf = factors['ff3'][1].set_index('date').RF.reindex(returns.index)
        audit.to_csv(out / 'data_quality.csv', index=False)
        asset_metrics = pd.DataFrame([dict(symbol=s, **performance(returns[s], rf)) for s in symbols])
        asset_metrics.to_csv(out / 'asset_metrics.csv', index=False)
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, layout='constrained')
        for symbol in symbols:
            wealth = (1 + returns[symbol]).cumprod()
            drawdown = wealth / wealth.cummax().clip(lower=1) - 1
            axes[0].plot(wealth.index, wealth, label=symbol)
            axes[1].plot(drawdown.index, drawdown)
        axes[0].set(title='Adjusted price return overview', ylabel='Growth of 1')
        axes[0].legend()
        axes[1].set(ylabel='Drawdown', xlabel='Date')
        for ax in axes:
            ax.grid(alpha=.2)
        fig.savefig(out / 'asset_overview.png', dpi=160)
        plt.close(fig)
        analysis = out / 'analysis'
        partial_reason = ''
        if full:
            print('Running factor, portfolio and out-of-sample strategy research...', flush=True)
            command = [sys.executable, str(ROOT / 'run_research.py'), '--symbols', *symbols, '--primary', symbols[0], '--benchmark', args.benchmark,
                       '--raw-dir', str(price_dir), '--output-dir', str(analysis), '--start', str(dates[0].date()), '--end', str(dates[-1].date()),
                       '--train-end', str(split.date()), '--cost-bps', str(args.cost_bps), '--ff3', str(factors['ff3'][0]), '--ff5', str(factors['ff5'][0])]
            ml_history = int((dates <= split).sum()) - 1 >= 275
            if args.include_ml and ml_history:
                command.append('--include-ml')
            elif args.include_ml:
                metadata['ml_skipped_reason'] = '训练区间不足以在特征预热后保留 252 个预测训练观测；未运行机器学习。'
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            (out / 'analysis.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'Analysis failed; see analysis.log: {result.stderr[-1200:]}')
        else:
            partial_reason = '历史或指定训练区间不足 252 个训练观测与 30 个测试观测；本次仅提供风险分析和因子回归，不生成组合回测或机器学习结论。'
            print(partial_reason, flush=True)
            for name, (path, _) in factors.items():
                command = [sys.executable, str(ROOT / 'indicators/fama_french.py'), '--stock', str(price_dir / f'{symbols[0]}.csv'), '--factors', str(path), '--output-dir', str(analysis / name)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                (out / f'{name}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
                if result.returncode:
                    raise RuntimeError(f'{name} regression failed: {result.stderr[-1200:]}')
        dump(out / 'acquisition.json', metadata)
        html_report(out, symbols, metadata, asset_metrics, analysis, partial_reason)
        intro = f'# {symbols[0]} 自动量化分析报告\n\n数据源：{metadata["price_source"]}。分析区间 {metadata["analysis_start"]} 至 {metadata["analysis_end"]}，因子截至 {metadata["factor_end"]}。\n\n[打开完整 HTML 报告](report.html)\n\n![价格净值与回撤](asset_overview.png)\n\n'
        if metadata.get('ml_skipped_reason'):
            intro += metadata['ml_skipped_reason'] + '\n\n'
        if (analysis / 'report.md').exists():
            body = (analysis / 'report.md').read_text(encoding='utf-8').replace('](efficient_frontier.png)', '](analysis/efficient_frontier.png)').replace('](strategy_comparison.png)', '](analysis/strategy_comparison.png)')
        else:
            body = partial_reason + '\n\n因子明细见 analysis/ff3/ 和 analysis/ff5/。'
        (out / 'report.md').write_text(intro + body, encoding='utf-8')
        print(json.dumps(dict(status='complete' if full else 'partial', report_html=str(out / 'report.html'), report_markdown=str(out / 'report.md'), primary=symbols[0], analysis_end=metadata['analysis_end']), ensure_ascii=False), flush=True)
    except Exception as error:
        metadata['error'] = str(error)
        metadata['status'] = 'failed'
        dump(out / 'failure.json', metadata)
        print(f'FAILED: {error}\nDetails: {out / "failure.json"}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '_download':
        acquire_stock(ticker(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(main())
