"""Consistent daily metrics for complete, equally spaced trading-session returns."""
import numpy as np
import pandas as pd


def performance(returns, rf):
    r, risk_free = np.asarray(returns, float), np.asarray(rf, float)
    if r.ndim != 1 or len(r) < 2 or r.shape != risk_free.shape:
        raise ValueError('Need aligned daily returns and RF with at least two rows')
    if not np.isfinite(r).all() or not np.isfinite(risk_free).all() or (r <= -1).any():
        raise ValueError('Invalid returns')
    if isinstance(returns, pd.Series) and isinstance(rf, pd.Series) and not returns.index.equals(rf.index):
        raise ValueError('Return and RF dates differ')
    wealth = np.cumprod(1 + r)
    peaks = np.maximum.accumulate(np.r_[1., wealth])[1:]
    excess = r - risk_free
    vol, excess_vol = np.std(r, ddof=1), np.std(excess, ddof=1)
    return dict(observations=len(r), total_return=float(wealth[-1] - 1),
                geometric_annual_return=float(np.expm1(np.log1p(r).sum() * 252 / len(r))),
                annual_volatility=float(vol * np.sqrt(252)),
                sharpe=float(excess.mean() / excess_vol * np.sqrt(252)) if excess_vol > 1e-12 else None,
                max_drawdown=float(np.min(wealth / peaks - 1)))
