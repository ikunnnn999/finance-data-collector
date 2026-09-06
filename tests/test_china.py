import argparse
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from stock_report import ticker
from quant.china import read_cn_factors, stamp_duty, regressions
from quant.backtest import simulate


class ChinaTests(unittest.TestCase):
    def test_stock_code_exchange_and_us_separation(self):
        for value in ['600519', 'sh600519', '600519.SH', '600519.SS']:
            self.assertEqual(ticker(value), '600519.SH')
        self.assertEqual(ticker('000001'), '000001.SZ')
        self.assertEqual(ticker('510300'), '510300.SH')
        self.assertEqual(ticker('NVDA'), 'NVDA')
        for value in ['000001.SH', '600519.SZ', '920001', '0700.HK']:
            with self.assertRaises(argparse.ArgumentTypeError):
                ticker(value)

    def test_tax_change_uses_execution_date_and_exempts_etf(self):
        calendar = pd.to_datetime(['2023-08-24', '2023-08-25', '2023-08-28', '2023-08-29'])
        dates = calendar[1:]
        rates = stamp_duty(dates, ['600519.SH', '510300.SH'], calendar)
        np.testing.assert_allclose(rates['600519.SH'], [10., 10., 5.])
        np.testing.assert_allclose(rates['510300.SH'], [0., 0., 0.])

    def test_stock_tax_only_applies_to_sales(self):
        dates = pd.bdate_range('2024-01-01', periods=3)
        r = pd.DataFrame({'600519.SH': [0., 0., 0.]}, index=dates)
        targets = pd.DataFrame({'600519.SH': [1., 0., 0.]}, index=dates)
        rates = pd.DataFrame(5., index=dates, columns=r.columns)
        result = simulate(r, pd.Series(0., index=dates), targets, 0., sell_cost_bps=rates)
        self.assertEqual(result.sell_cost_fraction.iloc[0], 0.)
        self.assertAlmostEqual(result.sell_cost_fraction.iloc[1], .0005)
        self.assertAlmostEqual(result.wealth.iloc[-1], .9995)

    def test_us_factor_sidecar_rejected_and_cn_units_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'factors.csv'
            path.write_text('date,Mkt-RF,SMB,HML,RF\n2024-01-02,1,2,3,0.01\n')
            meta = {'market': 'US', 'frequency': 'daily', 'units': 'percent', 'source': 'test fixture'}
            path.with_suffix('.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):
                read_cn_factors(path)
            meta['market'] = 'CN'
            path.with_suffix('.json').write_text(json.dumps(meta))
            frame, _ = read_cn_factors(path)
            self.assertAlmostEqual(frame['Mkt-RF'].iloc[0], .01)
            self.assertAlmostEqual(frame.RF.iloc[0], .0001)

    def test_market_model_does_not_invent_smb_or_hml(self):
        dates = pd.bdate_range('2024-01-01', periods=120)
        rng = np.random.default_rng(19)
        market = pd.Series(rng.normal(0, .01, len(dates)), index=dates)
        rf = pd.Series(.0001, index=dates)
        stock = rf + .0003 + 1.2 * (market - rf)
        coefficients, comparison, _ = regressions(stock, market, rf)
        self.assertEqual(comparison.model.tolist(), ['CN_market_model'])
        np.testing.assert_allclose(coefficients.coefficient, [.0003, 1.2], atol=1e-10)


if __name__ == '__main__':
    unittest.main()
