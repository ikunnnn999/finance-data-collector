"""China-only report path; never downloads or substitutes US pricing factors."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from quant.data import load_panel
from quant.metrics import performance
from quant.portfolio import optimize_portfolios
from quant.backtest import simulate, moving_average_targets
from quant.direction import walk_forward_direction
from quant.china import read_cn_factors, stamp_duty, regressions


def acquire_worker(symbol, path, start, end):
    import akshare as ak
    if symbol == 'calendar':
        frame = ak.tool_trade_date_hist_sina().rename(columns={'trade_date': 'date'})
    else:
        code, exchange = symbol.split('.')
        frame = ak.stock_zh_a_hist_tx(symbol=exchange.lower() + code, start_date=start, end_date=end, adjust='qfq', timeout=20)
    if frame.empty or 'date' not in frame or (symbol != 'calendar' and 'close' not in frame):
        raise ValueError(f'{symbol}: provider returned no usable data')
    frame.to_csv(path, index=False)


def run(args):
    from stock_report import choose_dates, html_report, dump
    from run_research import markdown_table
    root = Path(__file__).resolve().parent
    symbols = list(dict.fromkeys([*args.symbols, args.benchmark]))
    if len(symbols) > 8 or not np.isfinite(args.cn_rf_annual) or args.cn_rf_annual <= -1:
        raise ValueError('Use <=8 assets and a finite RF assumption greater than -100%')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = (args.output_dir or Path.cwd() / 'outputs' / f'{symbols[0]}-quant-{stamp}').resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty')
    out.mkdir(parents=True, exist_ok=True)
    metadata = dict(market='CN', currency='CNY', run_utc=datetime.now(timezone.utc).isoformat(), symbols=symbols,
                    requested_start=args.start, requested_end=args.end, cost_bps=args.cost_bps, inputs=[],
                    price_source='User-supplied Chinese price CSV' if args.prices_dir else 'AKShare / Tencent qfq',
                    factor_note='未提供可靠中国市场因子，本次只运行国内基准市场模型，跳过三/五因子；不套用美国因子。',
                    factor_end='未接入', modules_skipped=[],
                    market_notes='基准默认 510300 沪深300ETF（不是指数总收益）。每天最多一次调仓，保持至少一个交易日；未模拟涨跌停成交、停牌成交、整手、最低佣金与冲击成本。股票卖出另加历史印花税，ETF 不加股票印花税。',
                    versions={n: importlib.metadata.version(n) for n in ['akshare', 'pandas', 'numpy', 'scipy', 'statsmodels', 'matplotlib']})
    try:
        source = out / 'inputs/source_prices'
        prices_dir = out / 'inputs/prices'
        analysis = out / 'analysis'
        for path in [source, prices_dir, analysis]:
            path.mkdir(parents=True)
        now = datetime.now(ZoneInfo('Asia/Shanghai'))
        completed_day = pd.Timestamp(now.date())
        if now.hour < 15 or (now.hour == 15 and now.minute < 10):
            completed_day -= pd.Timedelta(days=1)
        download_start = (pd.Timestamp(args.start) if args.start else completed_day - pd.DateOffset(years=5)) - pd.Timedelta(days=14)
        download_end = min(pd.Timestamp(args.end), completed_day) if args.end else completed_day

        def acquire(symbol, target, supplied=None):
            print(f'Loading CN {symbol}...', flush=True)
            if supplied:
                shutil.copyfile(supplied, target)
            else:
                result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'stock_report.py'), '_download_cn', symbol,
                    str(target), download_start.strftime('%Y%m%d'), download_end.strftime('%Y%m%d')],
                    capture_output=True, encoding='utf-8', timeout=180)
                if result.returncode:
                    raise RuntimeError(f'{symbol}: data download failed: {result.stderr[-1000:]}')
            metadata['inputs'].append(dict(name=symbol, path=str(target), downloaded=not bool(supplied),
                source=('User-supplied CSV' if supplied else 'AKShare / Sina calendar' if symbol == 'calendar' else 'AKShare / Tencent qfq'),
                acquired_utc=datetime.now(timezone.utc).isoformat(), sha256=hashlib.sha256(target.read_bytes()).hexdigest()))

        calendar_path = out / 'inputs/calendar.csv'
        acquire('calendar', calendar_path, args.cn_calendar)
        calendar_frame = pd.read_csv(calendar_path).rename(columns={'trade_date': 'date'})
        calendar = pd.DatetimeIndex(pd.to_datetime(calendar_frame.date, errors='raise')).sort_values()
        if calendar.has_duplicates or calendar.hasnans:
            raise ValueError('Invalid mainland trading calendar')
        frames = {}
        for symbol in symbols:
            supplied = args.prices_dir / f'{symbol}.csv' if args.prices_dir else None
            if supplied and not supplied.exists():
                supplied = args.prices_dir / f'{symbol.split(".")[0]}.csv'
            target = source / f'{symbol}.csv'
            acquire(symbol, target, supplied)
            frame = pd.read_csv(target)
            frame['date'] = pd.to_datetime(frame.date, errors='raise')
            if frame.date.hasnans or frame.date.duplicated().any():
                raise ValueError(f'{symbol}: missing/duplicate dates')
            frames[symbol] = frame.sort_values('date')
        cn_factors, factor_info = None, None
        if args.cn_factors:
            cn_factors, factor_info = read_cn_factors(args.cn_factors)
            metadata.update(factor_note='使用用户提供并声明为中国市场的因子，来源及定义尚未独立核验；同文件三项模型属于该文件的约束模型。',
                            factor_end=str(cn_factors.index.max().date()), factor_metadata=factor_info)
            shutil.copyfile(args.cn_factors, out / 'inputs/cn_factors.csv')
            shutil.copyfile(args.cn_factors.with_suffix('.json'), out / 'inputs/cn_factors.json')
            metadata['inputs'].append(dict(name='CN factors', source=factor_info['source'], sha256=hashlib.sha256(args.cn_factors.read_bytes()).hexdigest()))
            calendar = calendar[calendar <= cn_factors.index.max()]
        else:
            metadata['modules_skipped'].append('China FF3/FF5: no verified Chinese factor dataset supplied')
        dates, split, full = choose_dates(frames, calendar, args.start, str(download_end.date()), args.train_end)
        position = calendar.get_loc(dates[0])
        if position == 0:
            raise ValueError('Calendar lacks the preceding trading session')
        previous = calendar[position - 1]
        for symbol, frame in frames.items():
            selected = frame.loc[frame.date.between(previous, dates[-1])]
            if 'volume' in selected and (pd.to_numeric(selected.volume, errors='raise') <= 0).any():
                raise ValueError(f'{symbol}: zero-volume/suspended sessions require verified tradability data')
            selected.to_csv(prices_dir / f'{symbol}.csv', index=False)
        prices, returns, audit = load_panel(prices_dir, symbols, calendar, dates[0], dates[-1])
        audit.to_csv(out / 'data_quality.csv', index=False)
        returns.to_csv(analysis / 'daily_returns.csv')
        if cn_factors is None:
            rf = pd.Series((1 + args.cn_rf_annual) ** (1 / 252) - 1, index=returns.index)
            metadata['rf_note'] = f'无风险收益使用固定年化 {args.cn_rf_annual:.2%} 的显式假设，不是已下载的国债收益率。'
        else:
            cn_factors = cn_factors.reindex(returns.index)
            if cn_factors.isna().any().any():
                raise ValueError('Chinese factor data do not cover every selected trading session')
            rf = cn_factors.RF
            metadata['rf_note'] = '无风险日收益来自所提供中国因子文件的 RF。'
        rf.rename('RF').to_csv(analysis / 'risk_free.csv')
        primary = symbols[0]
        coefs, comparison, summary = regressions(returns[primary], returns[args.benchmark], rf, cn_factors)
        coefs.to_csv(analysis / 'coefficients.csv', index=False)
        comparison.to_csv(analysis / 'model_comparison.csv', index=False)
        (analysis / 'summary.txt').write_text(summary, encoding='utf-8')
        assets = pd.DataFrame([dict(symbol=s, **performance(returns[s], rf)) for s in symbols])
        assets.to_csv(out / 'asset_metrics.csv', index=False)
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, layout='constrained')
        for symbol in symbols:
            wealth = (1 + returns[symbol]).cumprod()
            axes[0].plot(wealth.index, wealth, label=symbol)
            axes[1].plot(wealth.index, wealth / wealth.cummax().clip(lower=1) - 1)
        axes[0].set(title='China adjusted price returns', ylabel='Growth of 1')
        axes[0].legend()
        axes[1].set(ylabel='Drawdown', xlabel='Date')
        for ax in axes:
            ax.grid(alpha=.2)
        fig.savefig(out / 'asset_overview.png', dpi=160)
        plt.close(fig)
        pretest = returns.loc[:split]
        train, test = pretest.iloc[:-1], returns.loc[returns.index > split]
        partial_reason = ''
        if full:
            weights, frontier, estimates = optimize_portfolios(train, rf.loc[train.index])
            weights.to_csv(analysis / 'portfolio_weights.csv')
            frontier.to_csv(analysis / 'efficient_frontier.csv', index=False)
            estimates.to_csv(analysis / 'portfolio_training_estimates.csv')
            tax_rates = stamp_duty(test.index, symbols, calendar)
            tax_rates.to_csv(analysis / 'execution_sell_tax_bps.csv')
            results = {}
            def backtest(name, targets, rebalance='daily'):
                results[name] = simulate(test, rf.loc[test.index], targets, args.cost_bps, rebalance, tax_rates)
            for name, w in weights.iterrows():
                targets = pd.DataFrame(np.tile(w, (len(test), 1)), index=test.index, columns=symbols)
                backtest(name, targets, 'monthly')
            for symbol in dict.fromkeys([primary, args.benchmark]):
                targets = pd.DataFrame(0., index=test.index, columns=symbols)
                targets[symbol] = 1.
                backtest(symbol + '_buy_hold', targets, 'buy_and_hold')
            targets = pd.DataFrame(0., index=test.index, columns=symbols)
            targets[primary] = moving_average_targets(prices[primary], test.index)
            backtest(primary + '_moving_average', targets)
            if args.include_ml and len(train) >= 275:
                predictions, scores, folds = walk_forward_direction(prices[primary], returns[primary], test.index)
                predictions.to_csv(analysis / 'direction_predictions.csv')
                dump(analysis / 'direction_scores.json', scores)
                dump(analysis / 'direction_folds.json', folds)
                targets = pd.DataFrame(0., index=test.index, columns=symbols)
                targets[primary] = predictions.predicted_up
                backtest(primary + '_logistic', targets)
            elif args.include_ml:
                metadata['ml_skipped_reason'] = '特征预热后训练样本不足，未运行方向预测。'
            metrics = []
            for name, result in results.items():
                result.to_csv(analysis / f'backtest_{name}.csv')
                metrics.append(dict(strategy=name, **performance(result.net_return, rf.loc[test.index]), aggregate_turnover=float(result.turnover.sum())))
            pd.DataFrame(metrics).to_csv(analysis / 'strategy_metrics.csv', index=False)
            fig, ax = plt.subplots(figsize=(9, 5), layout='constrained')
            ax.plot(frontier.annual_volatility, frontier.expected_annual_return)
            for name, row in estimates.iterrows():
                ax.scatter(row.annual_volatility, row.expected_annual_return, label=name)
            ax.set(title='China training-sample efficient frontier', xlabel='Annual volatility', ylabel='Expected annual return')
            ax.legend()
            fig.savefig(analysis / 'efficient_frontier.png', dpi=160)
            plt.close(fig)
            fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, layout='constrained')
            for name, result in results.items():
                axes[0].plot(result.index, result.wealth, label=name)
                axes[1].plot(result.index, result.drawdown)
            axes[0].set(title='China out-of-sample strategy comparison', ylabel='Net wealth')
            axes[0].legend(fontsize=8, ncol=2)
            axes[1].set(ylabel='Drawdown', xlabel='Date')
            fig.savefig(analysis / 'strategy_comparison.png', dpi=160)
            plt.close(fig)
        else:
            partial_reason = '训练或测试样本不足，本次仅完成风险与中国市场模型，未运行组合、策略回测或预测。'
        metadata.update(analysis_start=str(dates[0].date()), analysis_end=str(dates[-1].date()), observations=len(dates),
            training_start=str(train.index[0].date()) if len(train) else None, training_end=str(train.index[-1].date()) if len(train) else None,
            test_start=str(test.index[0].date()), test_end=str(test.index[-1].date()), mode='full' if full else 'partial',
            initial_execution_close=str(pretest.index[-1].date()),
            stamp_duty='Stock sells: 10 bp before 2023-08-28, 5 bp from that execution date; ETF 0; schedule from 2008-09-19',
            code_hashes={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), root / 'stock_report.py', *sorted((root / 'quant').glob('*.py'))]})
        dump(out / 'acquisition.json', metadata)
        dump(analysis / 'manifest.json', metadata)
        html_report(out, symbols, metadata, assets, analysis, partial_reason)
        text = [f'# {primary} A股量化分析报告', '', f'区间：{metadata["analysis_start"]} 至 {metadata["analysis_end"]}；人民币价格收益。', '',
                metadata['factor_note'], '', metadata['rf_note'], '', '[查看完整 HTML 报告](report.html)', '',
                '![资产净值与回撤](asset_overview.png)', '', '## 中国市场模型', '', markdown_table(comparison.round(5)), '',
                '## 收益与风险', '', markdown_table(assets.round(5)), '', metadata['market_notes'], '',
                '股票印花税按实际执行日计算：2023-08-28 起卖出 5 bp，此前 10 bp；ETF 不加股票印花税。',
                '因子数据与价格复权均未独立核验；市场模型不是完整的 Fama-French 模型。年化采用 252 个交易日近似。']
        if partial_reason:
            text += ['', partial_reason]
        if full:
            text += ['', '## 样本外策略', '', markdown_table(pd.DataFrame(metrics).round(5)), '',
                     '![策略回测](analysis/strategy_comparison.png)']
        (out / 'report.md').write_text('\n'.join(text), encoding='utf-8')
        print(json.dumps(dict(status='complete' if full else 'partial', market='CN', report_html=str(out / 'report.html'),
            report_markdown=str(out / 'report.md'), primary=primary, analysis_end=metadata['analysis_end'], modules_skipped=metadata['modules_skipped']), ensure_ascii=False), flush=True)
        return 0
    except Exception as error:
        metadata.update(status='failed', error=str(error))
        dump(out / 'failure.json', metadata)
        print(f'FAILED: {error}\nDetails: {out / "failure.json"}', file=sys.stderr)
        return 2
