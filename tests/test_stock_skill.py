import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import pandas as pd

from stock_report import ticker, choose_dates
from tools.build_skill import ROOT, FILES


class StockSkillTests(unittest.TestCase):
    def test_tickers_and_market_boundary(self):
        self.assertEqual(ticker(' nvda '), 'NVDA')
        for value in ['../secrets', '600519', '0700.HK', 'AAPL;whoami', 'BRK/../B', 'CON']:
            with self.assertRaises(argparse.ArgumentTypeError):
                ticker(value)

    def test_dates_cap_to_factor_and_price_coverage(self):
        calendar = pd.bdate_range('2020-01-01', '2025-12-31')
        frames = {'NVDA': pd.DataFrame({'date': calendar[:-10]}), 'SPY': pd.DataFrame({'date': calendar})}
        dates, split, full = choose_dates(frames, calendar, end='2026-01-31')
        self.assertEqual(dates[-1], calendar[-11])
        self.assertTrue(full)
        self.assertTrue(dates[0] < split < dates[-1])

    def test_ipo_uses_partial_report_instead_of_fake_backtest(self):
        calendar = pd.bdate_range('2025-01-01', periods=120)
        frames = {'NEW': pd.DataFrame({'date': calendar[-90:]}), 'SPY': pd.DataFrame({'date': calendar})}
        dates, _, full = choose_dates(frames, calendar)
        self.assertEqual(len(dates), 89)
        self.assertFalse(full)
        with self.assertRaisesRegex(ValueError, 'preceding common price'):
            choose_dates(frames, calendar, start=str(calendar[0].date()))

    def test_portable_engine_is_current(self):
        engine = ROOT / 'skills/stock-quant-report/scripts/engine'
        manifest = json.loads((engine / 'bundle-manifest.json').read_text())
        for relative in FILES:
            content = (ROOT / relative).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
            self.assertEqual((engine / relative).read_text(encoding='utf-8'), content)
            self.assertEqual(manifest[relative], hashlib.sha256(content.encode('utf-8')).hexdigest())


if __name__ == '__main__':
    unittest.main()
