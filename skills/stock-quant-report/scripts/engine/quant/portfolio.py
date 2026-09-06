"""Long-only fully-invested Markowitz optimization, with checked constraints."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize


def optimize_portfolios(returns, rf, points=40):
    if len(returns) < 60 or points < 2 or not returns.index.equals(rf.index):
        raise ValueError('Need 60 aligned training observations and >=2 frontier points')
    if not np.isfinite(returns).all().all() or not np.isfinite(rf).all():
        raise ValueError('Invalid training data')
    mu, cov = returns.mean().to_numpy() * 252, returns.cov().to_numpy() * 252
    if np.linalg.eigvalsh(cov).min() <= 1e-12:
        raise ValueError('Covariance is singular or not positive definite')
    n, risk_free = len(mu), float(rf.mean() * 252)
    bounds = [(0., 1.)] * n
    constraints = [{'type': 'eq', 'fun': lambda w: w.sum() - 1}]

    def solve(objective, initial, extra=()):
        result = minimize(objective, initial, method='SLSQP', bounds=bounds,
                          constraints=constraints + list(extra), options={'ftol': 1e-12, 'maxiter': 2000})
        if not result.success or not np.isfinite(result.x).all():
            raise RuntimeError(f'Portfolio optimization failed: {result.message}')
        w = result.x
        if abs(w.sum() - 1) > 1e-7 or w.min() < -1e-7 or w.max() > 1 + 1e-7:
            raise RuntimeError('Optimizer violated weight constraints')
        return w

    variance = lambda w: float(w @ cov @ w)
    minimum = solve(variance, np.ones(n) / n)
    # Positive-excess Sharpe has a convex transformed minimum-variance problem:
    # min z'Cov z subject to excess'z=1, z>=0, then normalize z to weights.
    excess = mu - risk_free
    if excess.max() > 0:
        initial = np.zeros(n)
        initial[np.argmax(excess)] = 1 / excess.max()
        res = minimize(variance, initial, method='SLSQP', bounds=[(0, None)] * n,
                       constraints=[{'type': 'eq', 'fun': lambda z: z @ excess - 1}],
                       options={'ftol': 1e-12, 'maxiter': 2000})
        if not res.success or abs(res.x @ excess - 1) > 1e-7 or res.x.min() < -1e-7:
            raise RuntimeError(f'Maximum Sharpe optimization failed: {res.message}')
        maximum = res.x / res.x.sum()
    else:
        # For all nonpositive excess means the best ratio is at a simplex vertex.
        maximum = np.eye(n)[np.argmax(excess / np.sqrt(np.diag(cov)))]

    def row(w):
        volatility = np.sqrt(variance(w))
        return dict(expected_annual_return=float(w @ mu), annual_volatility=float(volatility),
                    expected_sharpe=float((w @ mu - risk_free) / volatility),
                    **dict(zip(returns.columns, w)))

    rows = []
    for target in np.linspace(minimum @ mu, mu.max(), points):
        if np.ptp(mu) < 1e-10:
            w = minimum
        else:
            w = solve(variance, minimum, [{'type': 'eq', 'fun': lambda w, target=target: w @ mu - target}])
        if abs(w @ mu - target) > 1e-7:
            raise RuntimeError('Frontier expected-return constraint failed')
        rows.append(row(w))
    weights = pd.DataFrame([minimum, maximum, np.ones(n) / n],
                           index=['minimum_variance', 'maximum_sharpe', 'equal_weight'], columns=returns.columns)
    estimates = pd.DataFrame([row(w) for w in weights.to_numpy()], index=weights.index)
    return weights, pd.DataFrame(rows), estimates
