"""Daily US Fama-French three-factor regression with auditable date alignment."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
import zipfile
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip'
FACTORS = ['Mkt-RF', 'SMB', 'HML']
URL5 = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip'


def significance(p):
    return '***' if p < .01 else '**' if p < .05 else '*' if p < .10 else ''


def read_factors(path):
    """Official daily CSV/ZIP in percent units; return decimals."""
    raw = Path(path).read_bytes()
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = [n for n in z.namelist() if n.lower().endswith('.csv')]
            if len(names) != 1:
                raise ValueError('Expected one CSV in factor ZIP')
            raw = z.read(names[0])
    lines = raw.decode('utf-8-sig').splitlines()
    rows = [s for s in lines if re.match(r'^\s*\d{8}\s*,', s)]
    if not rows or not any('Mkt-RF' in s and 'SMB' in s and 'HML' in s for s in lines):
        raise ValueError('Expected official daily three-factor CSV in percent units')
    df = pd.read_csv(io.StringIO('\n'.join(rows)), header=None)
    if df.shape[1] not in (5, 7):
        raise ValueError('Expected exactly three or five factors plus RF')
    cols = [*FACTORS, 'RMW', 'CMA', 'RF'] if df.shape[1] == 7 else [*FACTORS, 'RF']
    headers = [[c.strip() for c in s.split(',')][1:] for s in lines if s.lstrip().startswith(',')]
    if cols not in headers:
        raise ValueError('Unexpected factor column order')
    df.columns = ['date', *cols]
    df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d')
    if df['date'].duplicated().any():
        raise ValueError('Duplicate factor dates')
    df[cols] = df[cols].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(df[cols]).all().all() or df[cols].isin([-99.99, -999]).any().any():
        raise ValueError('Invalid factor values')
    df[cols] /= 100
    return df.sort_values('date').reset_index(drop=True)


def prepare_sample(path, factors, start=None, end=None):
    p = pd.read_csv(path)[['date', 'close']].copy()
    p['date'] = pd.to_datetime(p['date'], errors='raise')
    p['close'] = pd.to_numeric(p['close'], errors='raise')
    if p['date'].isna().any() or p['date'].duplicated().any():
        raise ValueError('Missing or duplicate price dates')
    if not np.isfinite(p['close']).all() or (p['close'] <= 0).any():
        raise ValueError('Prices must be finite and positive; investigate invalid rows')
    p = p.sort_values('date')
    p['previous_price_date'] = p['date'].shift()
    p['return'] = p['close'].pct_change(fill_method=None)
    f = factors.copy()
    f['previous_factor_date'] = f['date'].shift()
    audit = p.merge(f, on='date', how='left', validate='one_to_one')
    audit['reason'] = 'included'
    audit.loc[audit.previous_price_date != audit.previous_factor_date, 'reason'] = 'nonconsecutive_session'
    audit.loc[audit['Mkt-RF'].isna(), 'reason'] = 'outside_factor_calendar'
    audit.loc[audit.previous_price_date.isna(), 'reason'] = 'first_price'
    if start:
        audit.loc[audit.date < pd.Timestamp(start), 'reason'] = 'outside_requested_range'
    if end:
        audit.loc[audit.date > pd.Timestamp(end), 'reason'] = 'outside_requested_range'
    sample = audit.loc[audit.reason == 'included'].copy()
    sample['excess_stock'] = sample['return'] - sample['RF']
    return sample, audit


def fit_models(sample, lags=5):
    if lags < 0 or len(sample) < max(30, lags + 5):
        raise ValueError('Need max(30, HAC lags + 5) valid rows and nonnegative lags')
    if not np.isfinite(sample[['excess_stock', *FACTORS]]).all().all():
        raise ValueError('Nonfinite regression input')
    models = {}
    specifications = [('CAPM', ['Mkt-RF']), ('FF3', FACTORS)]
    if {'RMW', 'CMA'}.issubset(sample.columns):
        # Five-factor SMB has a different construction from official FF3 SMB.
        specifications = [('CAPM', ['Mkt-RF']), ('FF3_restricted_FF5', FACTORS),
                          ('FF5', [*FACTORS, 'RMW', 'CMA'])]
    for name, cols in specifications:
        if not np.isfinite(sample[cols]).all().all():
            raise ValueError('Nonfinite factor input')
        x = sm.add_constant(sample[cols], has_constant='add')
        if np.linalg.matrix_rank(x) != x.shape[1]:
            raise ValueError('Rank-deficient factor design')
        models[name] = sm.OLS(sample.excess_stock, x).fit(
            cov_type='HAC', cov_kwds={'maxlags': lags, 'use_correction': True}, use_t=True)
    return models


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', type=Path, default=ROOT / 'data/raw/AAPL.csv')
    parser.add_argument('--factors', type=Path, help='Official daily CSV/ZIP in percent; skips download')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/fama_french')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--hac-lags', type=int, default=5)
    parser.add_argument('--five-factor', action='store_true', help='Download the US daily five-factor dataset')
    args = parser.parse_args()
    if args.start and args.end and pd.Timestamp(args.start) > pd.Timestamp(args.end):
        parser.error('--start must not exceed --end')
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    path, downloaded = args.factors, None
    if path is None:
        source = URL5 if args.five_factor else URL
        with urllib.request.urlopen(source, timeout=60) as response:
            raw = response.read()
        path = out / source.rsplit('/', 1)[-1]
        path.write_bytes(raw)
        downloaded = datetime.now(timezone.utc).isoformat()
    factors = read_factors(path)
    if args.five_factor and 'RMW' not in factors:
        raise ValueError('--five-factor requires a five-factor file')
    sample, audit = prepare_sample(args.stock, factors, args.start, args.end)
    audit.to_csv(out / 'date_audit.csv', index=False)
    models = fit_models(sample, args.hac_lags)
    coefficients, comparison, summaries = [], [], []
    for name, model in models.items():
        ci = model.conf_int()
        for term in model.params.index:
            coefficients.append(dict(model=name, term=term, coefficient=model.params[term],
                std_error=model.bse[term], t=model.tvalues[term], p=model.pvalues[term],
                ci_low=ci.loc[term, 0], ci_high=ci.loc[term, 1],
                significance=significance(model.pvalues[term])))
        comparison.append(dict(model=name, n=int(model.nobs), r_squared=model.rsquared,
            adjusted_r_squared=model.rsquared_adj, daily_alpha=model.params['const'],
            annual_alpha_linear=252 * model.params['const']))
        sample[name + '_fitted_excess'] = model.fittedvalues
        sample[name + '_residual'] = model.resid
        summaries.append(name + '\n' + model.summary().as_text())
    full_name = 'FF5' if 'FF5' in models else 'FF3'
    restriction = 'RMW = 0, CMA = 0' if full_name == 'FF5' else 'SMB = 0, HML = 0'
    joint = models[full_name].wald_test(restriction, scalar=True)
    metadata = dict(source=URL5 if full_name == 'FF5' else URL, stock=str(args.stock.resolve()), factors=str(path.resolve()),
        downloaded_utc=downloaded, run_utc=datetime.now(timezone.utc).isoformat(),
        stock_sha256=hashlib.sha256(args.stock.read_bytes()).hexdigest(),
        factors_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        factor_end=str(factors.date.max().date()), sample_start=str(sample.date.min().date()),
        sample_end=str(sample.date.max().date()), sample_rows=len(sample), hac_lags=args.hac_lags,
        audit_counts=audit.reason.value_counts().to_dict(),
        large_absolute_return_rows=int((sample['return'].abs() >= .15).sum()),
        joint_restriction=restriction, joint_distribution=joint.distribution,
        joint_stat=float(joint.statistic), joint_p=float(joint.pvalue),
        notes=['Price adjustment and dividend treatment not independently verified.',
               'No magnitude filtering; exclude returns spanning missing factor sessions.',
               'HAC lags count retained observations; gaps limit inference.',
               'Annual alpha = 252 * daily intercept, not investment performance.'])
    sample.to_csv(out / 'regression_sample.csv', index=False)
    pd.DataFrame(coefficients).to_csv(out / 'coefficients.csv', index=False)
    pd.DataFrame(comparison).to_csv(out / 'model_comparison.csv', index=False)
    (out / 'summary.txt').write_text('\n\n'.join(summaries), encoding='utf-8')
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    table = pd.DataFrame(coefficients)
    report = ['# Factor regression interpretation', '',
              'HAC t/p and 95% intervals. *** p<0.01, ** p<0.05, * p<0.10; unadjusted for multiple testing.',
              'Statistical significance does not establish causality, predictive power, or economic value.',
              'FF3_restricted_FF5 uses five-factor SMB, not the official three-factor SMB.', '',
              '```text', pd.DataFrame(comparison).to_string(index=False), '```', '']
    for row in table.itertuples():
        conclusion = 'different from zero at 5%' if row.p < .05 else 'insufficient evidence of a nonzero coefficient at 5%'
        report.append(f'- {row.model} {row.term}: {row.coefficient:.6g}{row.significance}; t={row.t:.3f}, p={row.p:.6g}; {conclusion}.')
    report += ['', f'Joint HAC Wald test ({restriction}): p={float(joint.pvalue):.6g}.',
               'Price data remain unverified; these are diagnostic, in-sample results.']
    (out / 'interpretation.md').write_text('\n'.join(report), encoding='utf-8')
    print(pd.DataFrame(comparison).to_string(index=False))
    print(json.dumps(metadata, indent=2))
    print('Outputs:', out.resolve())


if __name__ == '__main__':
    main()
