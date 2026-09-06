"""Strict daily price panel: never silently fill, clip, or drop trading sessions."""
from pathlib import Path
import numpy as np
import pandas as pd


def load_panel(raw_dir, symbols, calendar, start, end):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start > end or len(set(symbols)) != len(symbols) or not symbols:
        raise ValueError('Invalid date range or symbols')
    calendar = pd.DatetimeIndex(calendar).sort_values()
    if calendar.has_duplicates or calendar.hasnans:
        raise ValueError('Invalid session calendar')
    sessions = calendar[(calendar >= start) & (calendar <= end)]
    if len(sessions) < 2 or end > calendar.max():
        raise ValueError('Requested range is empty or exceeds factor coverage')
    position = calendar.get_loc(sessions[0])
    if position == 0:
        raise ValueError('Need the preceding session to calculate the first return')
    dates = calendar[position - 1:calendar.get_loc(sessions[-1]) + 1]
    prices, audit = {}, []
    for symbol in symbols:
        frame = pd.read_csv(Path(raw_dir) / f'{symbol}.csv')
        frame['date'] = pd.to_datetime(frame['date'], errors='raise')
        if frame.date.hasnans or frame.date.duplicated().any():
            raise ValueError(f'{symbol}: missing/duplicate price dates')
        in_range = frame.date.between(dates[0], dates[-1])
        if (in_range & ~frame.date.isin(dates)).any():
            raise ValueError(f'{symbol}: price dates outside the official session calendar')
        series = pd.to_numeric(frame.set_index('date')['close'], errors='raise').reindex(dates)
        bad = series.isna() | ~np.isfinite(series) | (series <= 0)
        if bad.any():
            examples = ', '.join(str(d.date()) for d in dates[bad][:5])
            raise ValueError(f'{symbol}: {bad.sum()} missing/invalid sessions ({examples}); repair data or choose a complete interval')
        prices[symbol] = series
        audit.append(dict(symbol=symbol, observations=len(series), start=str(dates[0].date()),
                          end=str(dates[-1].date()), large_return_days=int((series.pct_change().abs() >= .15).sum())))
    prices = pd.DataFrame(prices)
    prices.index.name = 'date'
    returns = prices.pct_change(fill_method=None).iloc[1:]
    return prices, returns, pd.DataFrame(audit)
