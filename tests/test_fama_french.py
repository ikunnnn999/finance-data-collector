import tempfile
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from indicators.fama_french import read_factors, prepare_sample, fit_models


class FamaFrenchTests(unittest.TestCase):
    def test_percent_conversion_and_footer(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ff.csv'
            p.write_text('Preamble\n,Mkt-RF,SMB,HML,RF\n20200102,1,-2,3,0.01\nCopyright\n')
            f = read_factors(p)
            np.testing.assert_allclose(f.iloc[0, 1:].astype(float), [.01, -.02, .03, .0001])

    def test_missing_session_not_multiday_return(self):
        f = pd.DataFrame({'date': pd.to_datetime(['2020-01-02', '2020-01-03', '2020-01-06', '2020-01-07']),
                          'Mkt-RF': .01, 'SMB': .02, 'HML': .03, 'RF': .0001})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'stock.csv'
            pd.DataFrame({'date': ['2020-01-07', '2020-01-02', '2020-01-06'], 'close': [132, 100, 110]}).to_csv(p, index=False)
            sample, audit = prepare_sample(p, f)
            self.assertEqual(len(sample), 1)
            self.assertAlmostEqual(sample.iloc[0]['return'], .2)
            self.assertAlmostEqual(sample.iloc[0]['excess_stock'], .1999)
            self.assertEqual(audit.iloc[1].reason, 'nonconsecutive_session')
            pd.DataFrame({'date': ['2020-01-02'] * 2, 'close': [100, 101]}).to_csv(p, index=False)
            with self.assertRaises(ValueError):
                prepare_sample(p, f)

    def test_recovers_known_coefficients_and_same_sample(self):
        rng = np.random.default_rng(42)
        x = rng.normal(0, .01, (300, 3))
        sample = pd.DataFrame(x, columns=['Mkt-RF', 'SMB', 'HML'])
        sample['excess_stock'] = .001 + x @ np.array([1.2, -.3, .5])
        models = fit_models(sample)
        np.testing.assert_allclose(models['FF3'].params, [.001, 1.2, -.3, .5], atol=1e-10)
        self.assertEqual(models['FF3'].nobs, models['CAPM'].nobs)
        self.assertEqual(models['FF3'].cov_type, 'HAC')
        with self.assertRaises(ValueError):
            fit_models(sample.head(4))
        sample['HML'] = sample['SMB']
        with self.assertRaises(ValueError):
            fit_models(sample)


if __name__ == '__main__':
    unittest.main()
