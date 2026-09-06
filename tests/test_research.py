import tempfile
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

from indicators.fama_french import read_factors, fit_models, significance
from quant.data import load_panel
from quant.metrics import performance
from quant.portfolio import optimize_portfolios
from quant.backtest import simulate, moving_average_targets
from quant.direction import walk_forward_direction


class ResearchTests(unittest.TestCase):
    def test_five_factor_units_and_known_loadings(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'f.csv'
            path.write_text(',Mkt-RF,SMB,HML,RMW,CMA,RF\n20200102,1,2,3,4,5,.01\n')
            f = read_factors(path)
            self.assertAlmostEqual(f.RMW.iloc[0], .04)
            self.assertAlmostEqual(f.RF.iloc[0], .0001)
            path.write_text(',Mkt-RF,HML,SMB,RMW,CMA,RF\n20200102,1,2,3,4,5,.01\n')
            with self.assertRaisesRegex(ValueError, 'column order'):
                read_factors(path)
        rng = np.random.default_rng(123)
        x = rng.normal(0, .01, (300, 5))
        sample = pd.DataFrame(x, columns=['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA'])
        sample['excess_stock'] = .0002 + x @ [1.1, -.2, .3, .4, -.5]
        models = fit_models(sample)
        np.testing.assert_allclose(models['FF5'].params, [.0002, 1.1, -.2, .3, .4, -.5], atol=1e-10)
        self.assertEqual(models['FF5'].nobs, models['FF3_restricted_FF5'].nobs)
        self.assertEqual([significance(p) for p in [.001, .03, .08, .2]], ['***', '**', '*', ''])

    def test_panel_rejects_missing_sessions(self):
        dates = pd.bdate_range('2020-01-01', periods=6)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'A.csv'
            pd.DataFrame({'date': dates, 'close': [100, 101, 102, 103, 104, 105]}).to_csv(path, index=False)
            _, r, _ = load_panel(d, ['A'], dates, dates[1], dates[-1])
            self.assertAlmostEqual(r.A.iloc[0], .01)
            frame = pd.read_csv(path).drop(index=3)
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'missing/invalid'):
                load_panel(d, ['A'], dates, dates[1], dates[-1])

    def test_drawdown_includes_initial_capital(self):
        scores = performance([-.2, .1], [0., 0.])
        self.assertAlmostEqual(scores['max_drawdown'], -.2)
        self.assertAlmostEqual(scores['total_return'], -.12)
        self.assertAlmostEqual(scores['geometric_annual_return'], .88 ** 126 - 1)

    def test_markowitz_against_analytic_and_grid(self):
        # Orthogonal periodic shocks create an exactly diagonal sample covariance.
        shocks = np.tile([[1, 1], [1, -1], [-1, 1], [-1, -1]], (100, 1))
        dates = pd.bdate_range('2020-01-01', periods=len(shocks))
        r = pd.DataFrame(shocks * [.01, .02] + [.0004, .0007], index=dates, columns=['A', 'B'])
        rf = pd.Series(.0001, index=dates)
        weights, frontier, estimates = optimize_portfolios(r, rf, 12)
        np.testing.assert_allclose(weights.loc['minimum_variance'], [.8, .2], atol=1e-5)
        self.assertTrue(np.allclose(weights.sum(axis=1), 1))
        self.assertTrue((frontier[['A', 'B']] >= -1e-8).all().all())
        self.assertTrue((frontier.annual_volatility.diff().dropna() >= -1e-7).all())
        grid = np.column_stack([np.linspace(0, 1, 10001), np.linspace(1, 0, 10001)])
        mu, cov = r.mean().to_numpy() * 252, r.cov().to_numpy() * 252
        scores = (grid @ mu - .0001 * 252) / np.sqrt(np.einsum('ij,jk,ik->i', grid, cov, grid))
        self.assertGreaterEqual(estimates.loc['maximum_sharpe', 'expected_sharpe'] + 1e-7, scores.max())

    def test_buy_hold_drift_and_entry_cost(self):
        dates = pd.bdate_range('2024-01-01', periods=3)
        r = pd.DataFrame({'A': [.1, -.1, .2], 'B': [0., .1, -.1]}, index=dates)
        rf = pd.Series(0., index=dates)
        targets = pd.DataFrame(.5, index=dates, columns=r.columns)
        result = simulate(r, rf, targets, 10, 'buy_and_hold')
        expected = (1 + r).cumprod().mean(axis=1) / 1.001
        np.testing.assert_allclose(result.wealth, expected)
        self.assertAlmostEqual(result.turnover.iloc[1], 0)
        self.assertAlmostEqual(result.cost_fraction.iloc[0], .001 / 1.001)

    def test_cash_and_exit_cost(self):
        dates = pd.bdate_range('2024-01-01', periods=3)
        r = pd.DataFrame({'A': [0., 0., 0.]}, index=dates)
        rf = pd.Series(.0001, index=dates)
        targets = pd.DataFrame({'A': [1., 0., 0.]}, index=dates)
        result = simulate(r, rf, targets, 10)
        self.assertAlmostEqual(result.wealth.iloc[-1], 1 / 1.001 * .999 * 1.0001 ** 2)
        self.assertAlmostEqual(result.turnover.iloc[1], 1)

    def test_monthly_rebalance_is_not_daily(self):
        dates = pd.to_datetime(['2024-01-30', '2024-01-31', '2024-02-01'])
        r = pd.DataFrame({'A': [.1, .1, .1], 'B': [0., 0., 0.]}, index=dates)
        result = simulate(r, pd.Series(0., index=dates), pd.DataFrame(.5, index=dates, columns=r.columns), 0, 'monthly')
        self.assertAlmostEqual(result.turnover.iloc[1], 0)
        self.assertGreater(result.turnover.iloc[2], 0)
        self.assertAlmostEqual(result.weight_A.iloc[2], .5)

    def test_signal_cannot_capture_same_day_jump(self):
        dates = pd.bdate_range('2024-01-01', periods=8)
        prices = pd.Series([100, 100, 100, 100, 200, 200, 200, 200], index=dates)
        targets = moving_average_targets(prices, dates[4:], 1, 3)
        self.assertEqual(targets.iloc[0], 0)
        self.assertEqual(targets.iloc[1], 0)
        self.assertEqual(targets.iloc[2], 1)

    def test_prediction_future_changes_do_not_change_past(self):
        rng = np.random.default_rng(22)
        dates = pd.bdate_range('2020-01-01', periods=420)
        r = pd.Series(rng.normal(.0001, .01, len(dates)), index=dates)
        prices = (1 + r).cumprod() * 100
        test = dates[330:]
        before, _, _ = walk_forward_direction(prices, r, test)
        altered = r.copy()
        altered.loc[dates[390:]] += .02
        after, _, _ = walk_forward_direction((1 + altered).cumprod() * 100, altered, test)
        np.testing.assert_allclose(before.loc[:dates[389], 'probability_up'], after.loc[:dates[389], 'probability_up'])
        self.assertTrue((before.training_end < before.index).all())


if __name__ == '__main__':
    unittest.main()
