"""Provisional fluxgate deviation table -- pooled across 09-09, 09-12, 09-19.

Model, indexed by RAW fluxgate heading (conventional; no iteration needed):

    dev(H) = a0 + sum_{k=1..3} [ a_k cos(kH) + b_k sin(kH) ]
    corrected = H - dev(H) + mountingOffsetDeg

Fitted as:  dev_obs = dev(H) + g * turn_rate     (turn-rate absorbs sensor lag)

dev_obs = HDGmF - COG_magnetic. Valid because, per Jeff 2026-10-02, the outboard
has near-zero magnetic effect, and the 09-19 motoring-vs-race comparison showed
leeway's net effect on the fitted curve is negligible (constants agreed to 0.07
deg, amplitudes to 0.2 deg) -- it cancels across tacks.

Per-session intercepts are fitted as a DIAGNOSTIC only, to expose disagreement.
The deployed table uses the single pooled a0.
"""
import numpy as np
import pandas as pd

VARIATION = -7.68
K = 3

SESSIONS = [
    ('09-09', 'sailing_20260909_180000_to_20260909_200000.csv', True),
    ('09-12', 'sailing_20260912_133000_to_20260912_163000.csv', False),
    ('09-19', 'sailing_20260919_140000_to_20260919_231500.csv', False),
]


def wrap180(x):
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def load(f, mangled):
    d = pd.read_csv(f)
    ts = pd.to_datetime(d.timestamp, format='mixed')
    if ts.dt.second.eq(0).all() and ts.duplicated().any():
        ts = ts + pd.to_timedelta(d.groupby(ts).cumcount(), unit='s')
    d['t'] = ts
    d = d.set_index('t').sort_index()
    for c in ['SOG', 'COGt', 'HDGmF', 'ROLL', 'SATS']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['SATS'] = d['SATS'].ffill(limit=3)
    d['cogm'] = wrap180(d['COGt'] - VARIATION)
    h = d['HDGmF'].to_numpy(float)
    ok = ~np.isnan(h)
    hu = np.full(len(h), np.nan)
    hu[ok] = np.degrees(np.unwrap(np.radians(h[ok])))
    d['w'] = pd.Series(hu, index=d.index).diff().rolling(5, center=True, min_periods=3).mean()
    d = d[(d.SOG > 2.0) & ((d.SATS >= 6) | d.SATS.isna())]
    return d.dropna(subset=['HDGmF', 'cogm', 'w'])


def design(h_deg, w, k=K):
    h = np.radians(np.asarray(h_deg, float))
    cols = [np.ones(len(h))]
    names = ['a0']
    for i in range(1, k + 1):
        cols += [np.cos(i * h), np.sin(i * h)]
        names += [f'a{i}', f'b{i}']
    cols.append(np.asarray(w, float))
    names.append('g')
    return np.column_stack(cols), names


def curve(coef, H, k=K):
    h = np.radians(np.asarray(H, float))
    y = np.full(len(h), coef['a0'], dtype=float)
    for i in range(1, k + 1):
        y += coef[f'a{i}'] * np.cos(i * h) + coef[f'b{i}'] * np.sin(i * h)
    return y


frames = {}
print('=' * 76)
print('PER-SESSION FITS (diagnostic -- do these agree?)')
print('=' * 76)
for lab, f, mangled in SESSIONS:
    d = load(f, mangled)
    frames[lab] = d
    X, names = design(d.HDGmF, d.w)
    dev = wrap180(d.HDGmF - d.cogm)
    b, *_ = np.linalg.lstsq(X, dev, rcond=None)
    c = dict(zip(names, b))
    rms = float(np.sqrt(np.mean((dev - X @ b) ** 2)))
    bins = len(set((d.HDGmF // 30 * 30).astype(int)))
    print(f'{lab}  n={len(d):6d}  bins={bins:2d}/12  a0 {c["a0"]:+7.2f}  '
          f'semi {np.hypot(c["a1"], c["b1"]):6.2f}  quad {np.hypot(c["a2"], c["b2"]):5.2f}  '
          f'3rd {np.hypot(c["a3"], c["b3"]):5.2f}  g {c["g"]:+6.3f}  RMS {rms:5.2f}')
print()

pool = pd.concat([frames[l].assign(sess=l) for l, _, _ in SESSIONS])
X, names = design(pool.HDGmF, pool.w)
dev = wrap180(pool.HDGmF - pool.cogm)
b, *_ = np.linalg.lstsq(X, dev, rcond=None)
COEF = dict(zip(names, b))
resid = dev - X @ b
rms = float(np.sqrt(np.mean(resid ** 2)))

print('=' * 76)
print(f'POOLED FIT   n={len(pool)}   RMS {rms:.2f} deg')
print('=' * 76)
for k_ in names:
    print(f'   {k_:3s} {COEF[k_]:+10.5f}')
print(f'   semicircular {np.hypot(COEF["a1"], COEF["b1"]):.2f}   '
      f'quadrantal {np.hypot(COEF["a2"], COEF["b2"]):.2f}   '
      f'3rd {np.hypot(COEF["a3"], COEF["b3"]):.2f}')
print()

pool = pool.assign(resid=resid)
print('residual sd by session:', {l: round(float(pool[pool.sess == l].resid.std()), 2)
                                  for l, _, _ in SESSIONS})
print('residual mean by session:', {l: round(float(pool[pool.sess == l].resid.mean()), 2)
                                    for l, _, _ in SESSIONS})
print()
pool['bin'] = (pool.HDGmF // 30 * 30).astype(int)
t = pool.groupby('bin').agg(n=('resid', 'size'), resid_mean=('resid', 'mean'),
                            resid_sd=('resid', 'std'))
print('residual by heading bin:')
print(t.round(2).to_string())
print()

H = np.arange(0, 360, 30, dtype=float)
dev12 = curve(COEF, H)
print('=' * 76)
print('DEVIATION TABLE  (correction = -dev; mountingOffsetDeg = 0)')
print('=' * 76)
print('  raw HDGmF    dev     corrected')
for h, v in zip(H, dev12):
    print(f'  {h:8.0f}  {v:+7.2f}   {(h - v) % 360:9.2f}')
print()
print('JS coefficients for headingMagneticCorrection.js:')
print('  deviation: {')
print(f'    a0: {COEF["a0"]:.5f},')
for i in range(1, K + 1):
    print(f'    a{i}: {COEF[f"a{i}"]:.5f}, b{i}: {COEF[f"b{i}"]:.5f},')
print('  },')
print()
print(f'max |dev| over the circle: {np.abs(curve(COEF, np.arange(0,360,1.0))).max():.2f} deg')
print(f'pk-pk: {curve(COEF, np.arange(0,360,1.0)).max() - curve(COEF, np.arange(0,360,1.0)).min():.2f} deg')
