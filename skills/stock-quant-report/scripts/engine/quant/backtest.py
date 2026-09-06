"""Close-to-close accounting with explicit positions, drift and one-way costs."""
import numpy as np
import pandas as pd
from scipy.optimize import brentq


def simulate(returns, rf, targets, cost_bps=10., rebalance='daily'):
    """Targets are pre-decided holdings for each return interval; NaN means hold.

    Trades occur at the previous close. Caller must supply causally available
    targets. Costs are solved against post-cost target wealth, including entry.
    Terminal value is marked to market without a forced liquidation.
    """
    if rebalance not in ('daily', 'monthly', 'buy_and_hold') or not 0 <= cost_bps < 1000:
        raise ValueError('Invalid rebalance mode or cost')
    if not returns.index.equals(rf.index) or not returns.index.equals(targets.index) or not returns.columns.equals(targets.columns):
        raise ValueError('Dates and asset columns must match exactly')
    if not returns.index.is_monotonic_increasing or returns.index.has_duplicates:
        raise ValueError('Backtest dates must be unique and increasing')
    if returns.empty or not np.isfinite(returns).all().all() or not np.isfinite(rf).all() or (returns <= -1).any().any() or (rf <= -1).any():
        raise ValueError('Invalid backtest returns')
    drift = np.zeros(returns.shape[1])
    cost_rate, wealth, records, prior_month = cost_bps / 10000, 1., [], None
    for i, (date, r) in enumerate(returns.iterrows()):
        target = targets.loc[date].to_numpy(float)
        trade = i == 0 or rebalance == 'daily' or (rebalance == 'monthly' and date.to_period('M') != prior_month)
        if np.isnan(target).all() or not trade:
            target = drift.copy()
        if not np.isfinite(target).all() or target.min() < -1e-10 or target.sum() > 1 + 1e-8:
            raise ValueError('Targets must be nonnegative, finite, with total <=1')
        cost = brentq(lambda c: c - cost_rate * np.abs((1 - c) * target - drift).sum(), 0, 2 * cost_rate + 1e-12) if cost_rate else 0.
        turnover = float(np.abs((1 - cost) * target - drift).sum())
        gross = 1 + float(target @ r) + (1 - target.sum()) * rf.loc[date]
        net = (1 - cost) * gross - 1
        wealth *= 1 + net
        drift = target * (1 + r.to_numpy()) / gross
        records.append(dict(date=date, gross_return=gross - 1, net_return=net, wealth=wealth,
                            cost_fraction=cost, turnover=turnover, exposure=target.sum(),
                            **{f'weight_{s}': w for s, w in zip(returns.columns, target)}))
        prior_month = date.to_period('M')
    result = pd.DataFrame(records).set_index('date')
    result['drawdown'] = result.wealth / np.maximum.accumulate(np.r_[1., result.wealth])[1:] - 1
    return result


def moving_average_targets(prices, return_dates, fast=20, slow=60):
    if not 1 <= fast < slow:
        raise ValueError('Require 1 <= fast < slow')
    # Close s forms signal; execute at close s+1; first earned return ends s+2.
    signal = (prices.rolling(fast).mean() > prices.rolling(slow).mean()).astype(float)
    signal[prices.rolling(slow).mean().isna()] = np.nan
    target = signal.shift(2).reindex(return_dates)
    if target.isna().any():
        raise ValueError('Insufficient moving-average warm-up history')
    return target
