"""Mainland security routing, explicitly sourced factor inputs, and sell taxes."""
import argparse
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd
import statsmodels.api as sm
from indicators.fama_french import significance


def cn_ticker(value):
    value = value.strip().upper()
    match = re.fullmatch(r'(?:(SH|SZ))?(\d{6})(?:\.(SH|SZ|SS))?', value)
    if not match:
        return None
    prefix, code, suffix = match.groups()
    exchange = 'SH' if code[0] in '56' else 'SZ' if code[0] in '013' else None
    if exchange is None:
        raise argparse.ArgumentTypeError('Currently supports Shanghai/Shenzhen stocks and ETFs, not Beijing shares')
    suffix = 'SH' if suffix == 'SS' else suffix
    if (prefix and prefix != exchange) or (suffix and suffix != exchange):
        raise argparse.ArgumentTypeError('Exchange suffix conflicts with the stock/ETF code; indices are not supported as tickers')
    return f'{code}.{exchange}'


def read_cn_factors(path):
    """Require a CN/daily/source/units JSON sidecar; never assume US factors are CN."""
    path = Path(path)
    info = json.loads(path.with_suffix('.json').read_text(encoding='utf-8-sig'))
    if info.get('market') != 'CN' or info.get('frequency') != 'daily' or not str(info.get('source', '')).strip():
        raise ValueError('Factor metadata must declare market=CN, frequency=daily and a source')
    if info.get('units') not in ('decimal', 'percent'):
        raise ValueError('Declare factor units as decimal or percent in JSON')
    data = pd.read_csv(path)
    cols = ['Mkt-RF', 'SMB', 'HML', 'RF']
    if 'RMW' in data or 'CMA' in data:
        cols = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'RF']
    data = data[['date', *cols]].copy()
    data['date'] = pd.to_datetime(data.date, errors='raise')
    if data.date.hasnans or data.date.duplicated().any():
        raise ValueError('Invalid Chinese factor dates')
    data[cols] = data[cols].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(data[cols]).all().all() or data[cols].isin([-99.99, -999]).any().any():
        raise ValueError('Invalid Chinese factor values')
    if info['units'] == 'percent':
        data[cols] /= 100
    return data.sort_values('date').set_index('date'), info


def stamp_duty(return_dates, symbols, calendar):
    """Rates attached to the previous close, when these positions are traded."""
    previous = pd.Series(pd.DatetimeIndex(calendar), index=pd.DatetimeIndex(calendar)).shift().reindex(return_dates)
    if previous.isna().any() or (previous < pd.Timestamp('2008-09-19')).any():
        raise ValueError('Stamp-duty schedule requires execution dates from 2008-09-19 onward')
    rates = np.where(previous >= pd.Timestamp('2023-08-28'), 5., 10.)
    result = pd.DataFrame(0., index=return_dates, columns=symbols)
    for symbol in symbols:
        if symbol[0] in '036':
            result[symbol] = rates
    return result


def regressions(stock_returns, benchmark_returns, rf, factors=None, lags=5):
    if len(stock_returns) < 30:
        raise ValueError('Need at least 30 daily observations')
    y = stock_returns - rf
    specs = [('CN_market_model', pd.DataFrame({'benchmark_excess': benchmark_returns - rf}))]
    if factors is not None:
        subset_name = 'CN3_restricted_CN5' if 'RMW' in factors else 'CN3'
        specs.append((subset_name, factors[['Mkt-RF', 'SMB', 'HML']]))
        if 'RMW' in factors:
            specs.append(('CN5', factors[['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']]))
    coefficient_rows, comparisons, summaries = [], [], []
    for name, data in specs:
        if not data.index.equals(y.index) or not np.isfinite(data).all().all() or not np.isfinite(y).all():
            raise ValueError('Chinese regression inputs must have identical complete dates')
        x = sm.add_constant(data, has_constant='add')
        if np.linalg.matrix_rank(x) != x.shape[1]:
            raise ValueError('Rank-deficient Chinese regression design')
        fit = sm.OLS(y, x).fit(cov_type='HAC', cov_kwds={'maxlags': lags, 'use_correction': True}, use_t=True)
        ci = fit.conf_int()
        for term in fit.params.index:
            coefficient_rows.append(dict(model=name, term=term, coefficient=fit.params[term], t=fit.tvalues[term],
                                         p=fit.pvalues[term], std_error=fit.bse[term], ci_low=ci.loc[term, 0], ci_high=ci.loc[term, 1],
                                         significance=significance(fit.pvalues[term])))
        comparisons.append(dict(model=name, n=int(fit.nobs), r_squared=fit.rsquared, adjusted_r_squared=fit.rsquared_adj,
                                daily_alpha=fit.params['const'], annual_alpha_linear=252 * fit.params['const']))
        summaries.append(name + '\n' + fit.summary().as_text())
    return pd.DataFrame(coefficient_rows), pd.DataFrame(comparisons), '\n\n'.join(summaries)
