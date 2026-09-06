"""Optional expanding-window, regularized logistic direction baseline."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit


def walk_forward_direction(prices, returns, test_dates, min_train=252, step=63, penalty=.01):
    if min_train < 30 or step < 1 or penalty <= 0:
        raise ValueError('Invalid prediction settings')
    # Predict return ending t from information through t-2; execute at t-1 close.
    features = pd.DataFrame({'return_1': returns, 'momentum_5': prices.pct_change(5),
                             'momentum_20': prices.pct_change(20),
                             'volatility_20': returns.rolling(20).std(),
                             'ma_ratio': prices / prices.rolling(20).mean() - 1}).shift(2)
    features = features.reindex(returns.index)
    labels = (returns > 0).astype(int)
    if len(test_dates) == 0 or not pd.DatetimeIndex(test_dates).isin(returns.index).all():
        raise ValueError('Invalid prediction dates')
    outputs, folds = [], []
    for begin in range(0, len(test_dates), step):
        dates = test_dates[begin:begin + step]
        first_pos = returns.index.get_loc(dates[0])
        if first_pos < 2:
            raise ValueError('Insufficient causal training history')
        cutoff = returns.index[first_pos - 2]
        train = features.loc[:cutoff].dropna()
        test = features.loc[dates]
        if len(train) < min_train or test.isna().any().any():
            raise ValueError('Insufficient training or feature history')
        mean, scale = train.mean(), train.std().replace(0, 1)
        x = np.column_stack([np.ones(len(train)), ((train - mean) / scale).to_numpy()])
        xt = np.column_stack([np.ones(len(test)), ((test - mean) / scale).to_numpy()])
        y = labels.loc[train.index].to_numpy()

        def objective(b):
            z = x @ b
            loss = np.mean(np.logaddexp(0, z) - y * z) + penalty * (b[1:] @ b[1:]) / 2
            gradient = x.T @ (expit(z) - y) / len(y) + penalty * np.r_[0., b[1:]]
            return loss, gradient

        result = minimize(objective, np.zeros(x.shape[1]), jac=True, method='BFGS', options={'gtol': 1e-7})
        if not result.success:
            raise RuntimeError(f'Logistic optimization failed: {result.message}')
        probabilities = expit(xt @ result.x)
        majority = int(y.mean() >= .5)
        for date, probability in zip(dates, probabilities):
            outputs.append(dict(date=date, probability_up=probability, predicted_up=int(probability >= .5),
                                actual_up=int(labels.loc[date]), majority_prediction=majority,
                                training_end=cutoff, training_rows=len(train)))
        folds.append(dict(test_start=str(dates[0].date()), test_end=str(dates[-1].date()),
                          training_end=str(cutoff.date()), training_rows=len(train),
                          scaler_mean=mean.to_dict(), scaler_std=scale.to_dict(), coefficients=result.x.tolist()))
    predictions = pd.DataFrame(outputs).set_index('date')
    y, p, label = predictions.actual_up, predictions.probability_up, predictions.predicted_up
    recalls = [float((label[y == c] == c).mean()) for c in (0, 1) if (y == c).any()]
    scores = dict(accuracy=float((y == label).mean()), balanced_accuracy=float(np.mean(recalls)),
                  majority_baseline_accuracy=float((y == predictions.majority_prediction).mean()),
                  always_up_accuracy=float(y.mean()), brier_score=float(((p - y) ** 2).mean()),
                  observations=len(y), threshold=.5, penalty=penalty, refit_sessions=step)
    return predictions, scores, folds
