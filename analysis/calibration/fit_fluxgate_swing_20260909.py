"""
Provisional fluxgate deviation table from the 2026-09-09 motoring swings.

Method (revised per Jeff, 2026-09-10): a slow constant-rate circle IS the swing.
Do not filter to steady headings. Instead model the turn-induced error in the
COG reference, which is systematic and ~proportional to turn rate:

    dev(H, w) = A0 + sum_k [ Ak sin(kH) + Bk cos(kH) ] + g * w

  where w = d(heading)/dt. The g*w term absorbs, to first order:
    - GPS velocity-filter lag (COG reflects heading at t - tau)
    - GPS19 lever arm about the pivot point (tangential velocity w x r)
    - hull sideslip in the turn
  All three scale with w at fixed speed, so one coefficient carries them.

  If the two swings run in OPPOSITE directions, g*w changes sign between them
  while the deviation curve does not -- so agreement between separately-fitted
  curves is a real cross-check, and pooling cancels the term to first order.

Reference: COG true -> magnetic via variation, on the motoring legs only
(leeway ~0 under power; Great Lakes current small but not corrected here --
this is why the table is PROVISIONAL).
"""
import numpy as np
import pandas as pd

VARIATION = -7.68
# The swing measures deviation of the RAW instrument (HDGmF) against a magnetic
# reference, so raw - deviation IS the complete correction. The existing
# derived-data headingMagneticOffsetDeg = 10 was an approximation of part of
# this same deviation. ADR-015 says fold, do not stack: the table carries
# everything and the separate offset must be set to ZERO at the same time,
# otherwise the correction is applied twice.
FLUX_OFFSET_DEG = 0.0

C = {'sensors.fluxgate.headingMagnetic': 'hdgF',
     'sensors.ecompass.headingMagnetic': 'hdgE',
     'sensors.ecompass.headingMagneticTC': 'hdgT',
     'navigation.courseOverGroundTrue': 'cog',
     'navigation.speedOverGround': 'sog',
     'navigation.gnss.satellites': 'sats',
     'navigation.attitude.roll': 'roll'}


def wrap180(x):
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def load():
    df = pd.read_csv('/tmp/swing_20260909.csv')
    df = df[[c for c in df.columns if c in C or c == '_time']].rename(columns=C)
    df['_time'] = pd.to_datetime(df['_time'])
    df = df.set_index('_time').sort_index().resample('1s').mean()
    df[['hdgF', 'hdgE', 'hdgT', 'cog', 'roll']] = df[['hdgF', 'hdgE', 'hdgT', 'cog', 'roll']].ffill(limit=3)
    df[['sog', 'sats']] = df[['sog', 'sats']].ffill(limit=3)
    for c in ['hdgF', 'hdgE', 'hdgT', 'cog']:
        df[c] = np.degrees(df[c]) % 360
    df['roll'] = np.degrees(df['roll'])
    df['sog_kn'] = df['sog'] * 1.94384
    # turn rate from unwrapped fluxgate heading, smoothed over 5 s
    h = df['hdgF'].to_numpy(float)
    ok = ~np.isnan(h)
    hu = np.full(len(h), np.nan)
    hu[ok] = np.degrees(np.unwrap(np.radians(h[ok])))
    df['hdg_u'] = hu
    df['w'] = pd.Series(hu, index=df.index).diff().rolling(5, center=True, min_periods=3).mean()
    df['cogm'] = wrap180(df['cog'] - VARIATION)
    return df


def find_swings(df):
    m = df[(df.index < pd.Timestamp('2026-09-09 22:38:00', tz='UTC')) &
           (df.sats >= 6) & (df.sog_kn > 2.0)].copy()
    m = m.dropna(subset=['hdgF', 'cog', 'w'])
    # a swing = a run of same-signed sustained turn covering >300 deg
    sign = np.sign(m.w.rolling(15, center=True, min_periods=8).mean())
    m['sgn'] = sign
    m['grp'] = (m.sgn != m.sgn.shift()).cumsum()
    out = []
    for g, s in m.groupby('grp'):
        if len(s) < 60 or s.sgn.iloc[0] == 0:
            continue
        span = s.hdg_u.iloc[-1] - s.hdg_u.iloc[0]
        if abs(span) < 300:
            continue
        out.append((g, s, span))
    return m, out


df = load()
m, swings = find_swings(df)
print('=' * 78)
print('SWINGS FOUND IN THE 18:00-18:38 EDT MOTORING WINDOW')
print('=' * 78)
for g, s, span in swings:
    print(f'  group {g}: {s.index[0].strftime("%H:%M:%S")}Z -> {s.index[-1].strftime("%H:%M:%S")}Z  '
          f'{len(s):4d} s   heading span {span:+8.1f} deg  '
          f'({"CW / starboard" if span > 0 else "CCW / port"})  '
          f'mean rate {span/len(s):+.2f} deg/s  SOG {s.sog_kn.mean():.1f} kn')
print()
if len(swings) < 1:
    raise SystemExit('no full swings detected')


def fit(sub, col, k=3, with_w=True):
    s = sub.dropna(subset=[col, 'cogm', 'w'])
    dev = wrap180(s[col] - s['cogm'])
    h = np.radians(s[col].to_numpy(float))
    cols, names = [np.ones(len(s))], ['const']
    for i in range(1, k + 1):
        cols += [np.sin(i * h), np.cos(i * h)]
        names += [f'sin{i}', f'cos{i}']
    if with_w:
        cols.append(s.w.to_numpy(float))
        names.append('g_turn')
    X = np.column_stack(cols)
    dev = np.asarray(dev, dtype=float)
    b, *_ = np.linalg.lstsq(X, dev, rcond=None)
    resid = dev - X @ b
    return dict(zip(names, b)), float(np.sqrt(np.mean(resid ** 2))), len(s)


def curve(coef, H, k=3):
    h = np.radians(H)
    y = np.full_like(H, coef['const'], dtype=float)
    for i in range(1, k + 1):
        y = y + coef[f'sin{i}'] * np.sin(i * h) + coef[f'cos{i}'] * np.cos(i * h)
    return y


print('=' * 78)
print('TURN-RATE TERM: FITTED PER SWING (opposite directions => sign check)')
print('=' * 78)
H = np.arange(0, 360, 30, dtype=float)
percurve = []
for g, s, span in swings:
    for withw in (False, True):
        coef, rms, n = fit(s, 'hdgF', with_w=withw)
        tag = 'with turn term' if withw else 'no turn term  '
        gt = f"  g_turn {coef['g_turn']:+.3f} deg per deg/s" if withw else ''
        print(f'  swing {g} ({"CW" if span>0 else "CCW"}) {tag}: n={n:4d}  RMS {rms:5.2f} deg{gt}')
    coef, rms, n = fit(s, 'hdgF', with_w=True)
    percurve.append((g, span, coef, curve(coef, H)))
print()

if len(percurve) >= 2:
    print('  per-swing deviation curves (turn term removed), deg:')
    hdr = '   hdg  ' + ''.join([f'  swing{g}({"CW" if sp>0 else "CCW"})' for g, sp, _, _ in percurve]) + '   spread'
    print(hdr)
    for i, h in enumerate(H):
        vals = [c[i] for _, _, _, c in percurve]
        print(f'   {h:5.0f}  ' + ''.join([f'{v:14.2f}' for v in vals]) +
              f'{max(vals)-min(vals):9.2f}')
    allv = np.array([c for _, _, _, c in percurve])
    print(f'\n  mean absolute between-swing spread: {np.abs(allv.max(0)-allv.min(0)).mean():.2f} deg')
    print()

print('=' * 78)
print('POOLED PROVISIONAL FLUXGATE DEVIATION TABLE')
print('=' * 78)
pool = pd.concat([s for _, s, _ in swings])
coef, rms, n = fit(pool, 'hdgF', k=3, with_w=True)
print(f'  pooled n={n}, fit RMS {rms:.2f} deg, turn term {coef["g_turn"]:+.3f} deg per deg/s')
print(f'  harmonics: const {coef["const"]:+.2f}  '
      f'semicircular amp {np.hypot(coef["sin1"], coef["cos1"]):.2f}  '
      f'quadrantal amp {np.hypot(coef["sin2"], coef["cos2"]):.2f}  '
      f'3rd {np.hypot(coef["sin3"], coef["cos3"]):.2f}')
dev12 = curve(coef, H)
print()
print('  Deviation = HDGmF(raw) - magnetic heading. Correction = -deviation.')
print('  Folding in the existing derived-data offset of +%.1f deg (ADR-015: fold,' % FLUX_OFFSET_DEG)
print('  do not stack). Plugin wants input/output in RADIANS.')
print()
print('   raw HDGmF   deviation   corrected mag hdg   plugin input(rad)  output(rad)')
rows = []
for h, d in zip(H, dev12):
    corrected = (h - d + FLUX_OFFSET_DEG) % 360
    rows.append((h, d, corrected))
    print(f'   {h:8.1f}   {d:+9.2f}   {corrected:15.2f}   {np.radians(h):16.5f}  {np.radians(corrected):10.5f}')
print()
print('  as JSON for @signalk/calibration (period 2*pi, equal at 0 and 2*pi):')
js = ', '.join([f'{{"input": {np.radians(h):.5f}, "output": {np.radians(c):.5f}}}'
                for h, d, c in rows])
print('  [' + js + f', {{"input": {2*np.pi:.5f}, "output": {np.radians(rows[0][2]):.5f}}}]')
print()

print('=' * 78)
print('COVERAGE AND RESIDUAL BY HEADING BIN (pooled)')
print('=' * 78)
p = pool.dropna(subset=['hdgF', 'cogm', 'w']).copy()
p['dev'] = wrap180(p.hdgF - p.cogm)
p['pred'] = curve(coef, p.hdgF.to_numpy(float)) + coef['g_turn'] * p.w
p['resid'] = p.dev - p.pred
p['bin'] = (p.hdgF // 30 * 30).astype(int)
t = p.groupby('bin').agg(n=('dev', 'size'), dev_mean=('dev', 'mean'),
                         resid_sd=('resid', 'std'), w=('w', 'mean'),
                         sog=('sog_kn', 'mean'))
print(t.round(2).to_string())
print(f'\n  bins occupied: {len(t)}/12   min bin count: {t.n.min()}   '
      f'overall residual sd {p.resid.std():.2f} deg')
