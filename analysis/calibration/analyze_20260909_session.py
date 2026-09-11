"""
Analysis of the 2026-09-09 sailing session — first post-TC-flash sailing data.

Questions (from TODO / handoffs/2026-09-09-boat-visit.md):
  Q1. Does the +0.25 deg/C residual thermal coefficient hold away from 183 deg?
  Q2. Is the +14 deg constant TC bias a genuine offset or a heading-dependent artifact?
  Q3. What do the two motoring heading swings (18:00-18:35) give us for coverage?

Method notes honoured (analysis/calibration/README.md):
  - SATS ffill(limit=3) then filter >= 6
  - ETEMP ffill before joining (~0.25 Hz vs 1 Hz)
  - HDGmE / HDGmF are RAW; HDGmF excludes the fluxgate's +10 deg derived-data offset
  - HDGmT is the TC-corrected eCompass heading
"""
import numpy as np
import pandas as pd

CSV = 'sailing_20260909_180000_to_20260909_200000.csv'
VARIATION = -7.68  # deg, per the 09-04 absolute reference


def wrap180(x):
    return (np.asarray(x, dtype=float) + 180.0) % 360.0 - 180.0


def circmean_deg(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan
    r = np.deg2rad(x)
    return np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean()))


def circstd_deg(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan
    r = np.deg2rad(x)
    R = np.hypot(np.sin(r).mean(), np.cos(r).mean())
    return np.rad2deg(np.sqrt(-2.0 * np.log(max(R, 1e-12))))


def segment(t):
    m = t.hour * 60 + t.minute
    if m < 18 * 60 + 35:
        return '1_motor_swing'
    if m < 19 * 60:
        return '2_prep'
    if m < 19 * 60 + 43:
        return '3_race'
    if m < 19 * 60 + 52:
        return '4_sail'
    return '5_motor_home'


def load():
    df = pd.read_csv(CSV)
    # NOTE: this export's timestamps are Excel-mangled to minute resolution
    # ("9/9/26 18:00"); the 09-02 raw export is ISO with seconds. Rows remain
    # in order at ~1 Hz, so seconds are reconstructed by within-minute rank.
    df['ts'] = pd.to_datetime(df['timestamp'], format='%m/%d/%y %H:%M')
    df['t'] = df['ts'] + pd.to_timedelta(df.groupby('ts').cumcount(), unit='s')

    num = ['LAT', 'LON', 'SOG', 'COGt', 'HDGt', 'ROLL', 'PITCH', 'SATS', 'HDOP',
           'HDGmE', 'HDGmT', 'HDGmF', 'ETEMP', 'MFIT', 'MFITT', 'MSOLV', 'MNOIS',
           'MAGB', 'MAGBT', 'MINCL', 'AWA', 'AWS', 'TWA', 'TWD', 'TWS', 'LEE', 'MROT']
    for c in num:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    df['SATS'] = df['SATS'].ffill(limit=3)
    df['ETEMPf'] = df['ETEMP'].ffill()
    df['seg'] = df['t'].map(segment)
    return df


def s1_overview(df):
    print('=' * 78)
    print('1. SESSION OVERVIEW / DATA QUALITY')
    print('=' * 78)
    g = df.groupby('seg').agg(
        n=('t', 'size'),
        sats_min=('SATS', 'min'),
        pct_sats_ge6=('SATS', lambda s: 100 * (s >= 6).mean()),
        n_HDGmE=('HDGmE', 'count'),
        n_HDGmT=('HDGmT', 'count'),
        n_HDGmF=('HDGmF', 'count'),
        etemp_lo=('ETEMPf', 'min'),
        etemp_hi=('ETEMPf', 'max'),
        sog_med=('SOG', 'median'),
        sog_max=('SOG', 'max'),
        roll_absmax=('ROLL', lambda s: s.abs().max()),
    )
    print(g.round(2).to_string())
    print()
    print('magnetometer state over session:')
    for c in ['MAGB', 'MFIT', 'MFITT', 'MSOLV', 'MINCL', 'MNOIS']:
        s = df[c].dropna()
        if len(s):
            print(f'  {c:6s} n={len(s):5d}  min={s.min():9.4f}  max={s.max():9.4f}  '
                  f'first={s.iloc[0]:9.4f}  last={s.iloc[-1]:9.4f}')
    print()


def s2_tc_delta(df):
    """Q2: is HDGmT - HDGmE a constant offset or heading-dependent?"""
    print('=' * 78)
    print('2. TC CORRECTION MAGNITUDE  (HDGmT - HDGmE)')
    print('=' * 78)
    d = df.dropna(subset=['HDGmE', 'HDGmT']).copy()
    d['dTC'] = wrap180(d['HDGmT'] - d['HDGmE'])
    print(f'paired samples: {len(d)}')
    print(f'  mean {d.dTC.mean():+.3f}  median {d.dTC.median():+.3f}  '
          f'sd {d.dTC.std():.3f}  min {d.dTC.min():+.2f}  max {d.dTC.max():+.2f}')
    print()
    print('by heading bin (HDGmE, 30 deg bins):')
    d['hbin'] = (d['HDGmE'] // 30 * 30).astype(int)
    t = d.groupby('hbin').agg(n=('dTC', 'size'), dTC_mean=('dTC', 'mean'),
                              dTC_sd=('dTC', 'std'), etemp=('ETEMPf', 'mean'))
    print(t.round(2).to_string())
    print()
    print('by temperature (0.5 C bins):')
    d['tbin'] = (d['ETEMPf'] * 2).round() / 2
    t2 = d.groupby('tbin').agg(n=('dTC', 'size'), dTC_mean=('dTC', 'mean'),
                               dTC_sd=('dTC', 'std'), hdg=('HDGmE', circmean_deg))
    print(t2.round(2).to_string())
    print()
    # regress dTC on temperature and on heading harmonics
    sub = d.dropna(subset=['ETEMPf'])
    X = np.column_stack([np.ones(len(sub)), sub.ETEMPf,
                         np.sin(np.deg2rad(sub.HDGmE)), np.cos(np.deg2rad(sub.HDGmE)),
                         np.sin(np.deg2rad(2 * sub.HDGmE)), np.cos(np.deg2rad(2 * sub.HDGmE))])
    b, *_ = np.linalg.lstsq(X, sub.dTC.values, rcond=None)
    pred = X @ b
    ss = 1 - np.var(sub.dTC.values - pred) / np.var(sub.dTC.values)
    print('dTC ~ 1 + T + sinH + cosH + sin2H + cos2H')
    print(f'  const {b[0]:+.3f}   T {b[1]:+.4f} deg/C   sinH {b[2]:+.3f}  cosH {b[3]:+.3f}'
          f'  sin2H {b[4]:+.3f}  cos2H {b[5]:+.3f}   R2={ss:.3f}')
    # temperature-only
    Xt = np.column_stack([np.ones(len(sub)), sub.ETEMPf])
    bt, *_ = np.linalg.lstsq(Xt, sub.dTC.values, rcond=None)
    r2t = 1 - np.var(sub.dTC.values - Xt @ bt) / np.var(sub.dTC.values)
    print(f'  temp-only: const {bt[0]:+.3f}  T {bt[1]:+.4f} deg/C  R2={r2t:.3f}')
    print()
    return d


def s3_gap(df):
    """eCompass (raw and TC) vs fluxgate, by heading — the cross-session gap curve."""
    print('=' * 78)
    print('3. eCOMPASS - FLUXGATE GAP, RAW vs TC-CORRECTED')
    print('=' * 78)
    d = df[df.SATS >= 6].dropna(subset=['HDGmF']).copy()
    d['gapE'] = wrap180(d['HDGmE'] - d['HDGmF'])
    d['gapT'] = wrap180(d['HDGmT'] - d['HDGmF'])
    for seg in sorted(d.seg.unique()):
        s = d[d.seg == seg]
        ge, gt = s.gapE.dropna(), s.gapT.dropna()
        print(f'{seg:14s} n={len(s):5d}  gapE mean {ge.mean():+7.2f} sd {ge.std():6.2f} (n={len(ge)})'
              f'   gapT mean {gt.mean():+7.2f} sd {gt.std():6.2f} (n={len(gt)})')
    print()
    print('gap by heading bin (HDGmF, 30 deg bins), whole session, SATS>=6:')
    d['hbin'] = (d['HDGmF'] // 30 * 30).astype(int)
    t = d.groupby('hbin').agg(n=('gapE', 'size'),
                              gapE=('gapE', 'mean'), gapE_sd=('gapE', 'std'),
                              gapT=('gapT', 'mean'), gapT_sd=('gapT', 'std'),
                              etemp=('ETEMPf', 'mean'))
    print(t.round(2).to_string())
    print()
    return d


def fit_fourier(h, y, k=2, extra=None, names=None):
    h = np.deg2rad(np.asarray(h, dtype=float))
    cols = [np.ones(len(h))]
    nm = ['const']
    for i in range(1, k + 1):
        cols += [np.sin(i * h), np.cos(i * h)]
        nm += [f'sin{i}H', f'cos{i}H']
    if extra is not None:
        for e, n in zip(extra, names):
            cols.append(np.asarray(e, dtype=float))
            nm.append(n)
    X = np.column_stack(cols)
    b, *_ = np.linalg.lstsq(X, np.asarray(y, dtype=float), rcond=None)
    resid = y - X @ b
    return dict(zip(nm, b)), float(np.sqrt(np.mean(resid ** 2))), resid


def s4_swings(df):
    """Q3: the two motoring heading swings — coverage and an absolute check vs COG."""
    print('=' * 78)
    print('4. MOTORING SWINGS (18:00-18:35) — COVERAGE AND COG REFERENCE')
    print('=' * 78)
    m = df[(df.seg == '1_motor_swing') & (df.SATS >= 6)].copy()
    m = m.dropna(subset=['COGt', 'SOG'])
    print(f'motoring rows with SATS>=6: {len(m)}, SOG median {m.SOG.median():.2f} '
          f'max {m.SOG.max():.2f}')
    # heading coverage
    for col in ['HDGmE', 'HDGmT', 'HDGmF']:
        s = m[col].dropna()
        if len(s):
            occ = np.unique((s // 30 * 30).astype(int))
            print(f'  {col}: n={len(s):5d}  30-deg bins occupied: {len(occ)}/12  {list(occ)}')
    print()
    # steady, moving segments only: COG is a usable reference when actually making way
    mm = m[(m.SOG > 1.5)].copy()
    mm['cogm'] = wrap180(mm.COGt - VARIATION)  # COG true -> magnetic
    for col, lab in [('HDGmF', 'fluxgate raw'), ('HDGmE', 'eCompass raw'), ('HDGmT', 'eCompass TC')]:
        s = mm.dropna(subset=[col]).copy()
        if not len(s):
            continue
        s['dev'] = wrap180(s[col] - s['cogm'])
        print(f'{lab:14s} n={len(s):5d}  dev mean {s.dev.mean():+7.2f}  sd {s.dev.std():6.2f}  '
              f'pk-pk {s.dev.max() - s.dev.min():7.2f}')
    print()
    print('NOTE: during a turn COG lags heading, so raw dev stats here mix real')
    print('deviation with turn dynamics. Bin table below restricted to low-ROT rows.')
    print()
    # low rate-of-turn rows only
    mm = mm.sort_values('t')
    for col in ['HDGmF', 'HDGmE', 'HDGmT']:
        mm[col + '_rate'] = wrap180(mm[col].diff()) / mm['t'].diff().dt.total_seconds()
    steady = mm[(mm.HDGmF_rate.abs() < 1.0)].copy()
    steady['cogm'] = wrap180(steady.COGt - VARIATION)
    steady['hbin'] = (steady.HDGmF // 30 * 30).astype(int)
    for col, lab in [('HDGmF', 'fluxgate raw'), ('HDGmE', 'eCompass raw'), ('HDGmT', 'eCompass TC')]:
        s = steady.dropna(subset=[col]).copy()
        if not len(s):
            continue
        s['dev'] = wrap180(s[col] - s['cogm'])
        t = s.groupby('hbin').agg(n=('dev', 'size'), dev=('dev', 'mean'), sd=('dev', 'std'))
        print(f'--- {lab} deviation vs COG-magnetic, steady (|dHDG/dt|<1 deg/s) ---')
        print(t.round(2).to_string())
        print(f'    overall mean {s.dev.mean():+.2f}  sd {s.dev.std():.2f}  '
              f'pk-pk of bin means {t.dev.max() - t.dev.min():.2f}')
        print()
    return m, steady


def s5_thermal(df):
    """Q1: residual thermal coefficient of the TC path across real headings."""
    print('=' * 78)
    print('5. RESIDUAL THERMAL COEFFICIENT ACROSS HEADINGS')
    print('=' * 78)
    d = df[df.SATS >= 6].dropna(subset=['HDGmF', 'ETEMPf']).copy()
    d['gapE'] = wrap180(d['HDGmE'] - d['HDGmF'])
    d['gapT'] = wrap180(d['HDGmT'] - d['HDGmF'])
    print(f'ETEMP range this session: {d.ETEMPf.min():.2f} - {d.ETEMPf.max():.2f} C '
          f'(span {d.ETEMPf.max() - d.ETEMPf.min():.2f} C)')
    print()
    for col in ['gapE', 'gapT']:
        s = d.dropna(subset=[col])
        if len(s) < 50:
            continue
        # temp only
        X = np.column_stack([np.ones(len(s)), s.ETEMPf])
        b, *_ = np.linalg.lstsq(X, s[col].values, rcond=None)
        r2 = 1 - np.var(s[col].values - X @ b) / np.var(s[col].values)
        # with heading harmonics to separate thermal from deviation
        coef, rms, _ = fit_fourier(s.HDGmF.values, s[col].values, k=2,
                                   extra=[s.ETEMPf.values], names=['T'])
        print(f'{col}: n={len(s)}')
        print(f'   temp-only:  const {b[0]:+8.3f}  T {b[1]:+7.4f} deg/C  R2 {r2:.4f}')
        print(f'   k=2 Fourier + T: T {coef["T"]:+7.4f} deg/C  '
              f'sinH {coef["sin1H"]:+7.3f}  cosH {coef["cos1H"]:+7.3f}  '
              f'sin2H {coef["sin2H"]:+7.3f}  cos2H {coef["cos2H"]:+7.3f}  RMS {rms:.3f}')
        print()
    # heading coverage overall
    print('heading coverage (HDGmF, 30 deg bins) by segment:')
    d['hbin'] = (d.HDGmF // 30 * 30).astype(int)
    print(pd.crosstab(d.seg, d.hbin).to_string())
    print()


if __name__ == '__main__':
    df = load()
    s1_overview(df)
    s2_tc_delta(df)
    s3_gap(df)
    s4_swings(df)
    s5_thermal(df)
