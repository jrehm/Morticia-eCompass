"""Can race data substitute for dedicated circles?

Jeff, 2026-10-02: a separate thread concluded the outboard (up/down/running) has
near-zero magnetic impact. So motoring and sailing data differ ONLY by leeway.
Leeway is modellable, so the race may supply the heading coverage that has been
the binding constraint -- without dedicated circles.

Authoritative 09-19 segmentation (Jeff): race 15:30-21:19 is 100% sailing;
everything outside it is motoring.

Test: fit the same deviation model three ways and compare.
    A. motoring only          dev = const + Fourier(H) + g*w
    B. sailing only           dev = const + Fourier(H) + g*w + c*LEE
    C. everything pooled      dev = const + Fourier(H) + g*w + c*LEE   (LEE=0 under power)

If A and B agree, the leeway model holds and C is the best estimate we can make
without circles. If they disagree, leeway (or heading/TWA collinearity within the
race) is not being absorbed, and circles remain necessary.

    dev = indicated heading - COG_magnetic
COG_m = H + lambda  (lambda = signed leeway), so dev carries -lambda;
expect the fitted LEE coefficient near -1 if LEE is signed leeway in degrees.
"""
import numpy as np
import pandas as pd

VARIATION = -7.68
F19 = 'sailing_20260919_140000_to_20260919_231500.csv'
RACE = ('2026-09-19 15:30', '2026-09-19 21:19')


def wrap180(x):
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def load(f):
    d = pd.read_csv(f)
    d['t'] = pd.to_datetime(d.timestamp)
    d = d.set_index('t').sort_index()
    for c in ['SOG', 'COGt', 'HDGmE', 'HDGmT', 'HDGmF', 'ROLL', 'SATS', 'TWA', 'LEE', 'TWS']:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    d['SATS'] = d['SATS'].ffill(limit=3)
    d['cogm'] = wrap180(d['COGt'] - VARIATION)
    h = d['HDGmF'].to_numpy(float)
    ok = ~np.isnan(h)
    hu = np.full(len(h), np.nan)
    hu[ok] = np.degrees(np.unwrap(np.radians(h[ok])))
    d['w'] = pd.Series(hu, index=d.index).diff().rolling(5, center=True, min_periods=3).mean()
    d['LEEf'] = d['LEE'].fillna(0.0)
    return d


def fit(sub, col, k=3, use_lee=True):
    need = [col, 'cogm', 'w'] + (['LEEf'] if use_lee else [])
    s = sub.dropna(subset=need)
    if len(s) < 200:
        return None
    dev = wrap180(s[col] - s['cogm'])
    h = np.radians(s[col].to_numpy(float))
    cols, names = [np.ones(len(s))], ['const']
    for i in range(1, k + 1):
        cols += [np.sin(i * h), np.cos(i * h)]
        names += [f'sin{i}', f'cos{i}']
    cols.append(s.w.to_numpy(float)); names.append('g_turn')
    if use_lee:
        cols.append(s.LEEf.to_numpy(float)); names.append('c_lee')
    X = np.column_stack(cols)
    b, *_ = np.linalg.lstsq(X, dev, rcond=None)
    resid = dev - X @ b
    coef = dict(zip(names, b))
    return coef, float(np.sqrt(np.mean(resid ** 2))), len(s), s


def describe(tag, col, r):
    if r is None:
        print(f'  {tag:14s} {col:6s}  (insufficient)')
        return None
    coef, rms, n, s = r
    semi = np.hypot(coef['sin1'], coef['cos1'])
    quad = np.hypot(coef['sin2'], coef['cos2'])
    lee = f" c_lee {coef['c_lee']:+6.3f}" if 'c_lee' in coef else '  c_lee     --'
    bins = len(set((s[col].dropna() // 30 * 30).astype(int)))
    print(f'  {tag:14s} {col:6s} n={n:6d} bins={bins:2d}/12  const {coef["const"]:+7.2f}  '
          f'semi {semi:6.2f}  quad {quad:5.2f}  g {coef["g_turn"]:+6.3f}{lee}  RMS {rms:5.2f}')
    return coef


d = load(F19)
race = d.loc[RACE[0]:RACE[1]]
motor = d[(d.index < pd.Timestamp(RACE[0])) | (d.index > pd.Timestamp(RACE[1]))]
for name, s in [('motor', motor), ('race', race)]:
    s2 = s[(s.SOG > 2.0)]
    print(f'{name}: n={len(s2)}  SOG med {s2.SOG.median():.1f}  |roll| {s2.ROLL.abs().mean():.1f}  '
          f'LEE mean {s2.LEE.abs().mean():.2f} max {s2.LEE.abs().max():.2f}  '
          f'bins={sorted(set((s2.HDGmF.dropna()//30*30).astype(int)))}')
print()

motor = motor[motor.SOG > 2.0]
race = race[race.SOG > 2.0]
allp = pd.concat([motor, race]).sort_index()

for col in ['HDGmF', 'HDGmT', 'HDGmE']:
    print(f'=== {col} ===')
    describe('A motor only', col, fit(motor, col, use_lee=False))
    describe('B race +lee', col, fit(race, col, use_lee=True))
    describe('B race NOlee', col, fit(race, col, use_lee=False))
    describe('C pooled+lee', col, fit(allp, col, use_lee=True))
    print()

print('=== deviation curve from C (pooled + leeway), every 30 deg ===')
r = fit(allp, 'HDGmF', use_lee=True)
if r:
    coef = r[0]
    H = np.arange(0, 360, 30, dtype=float)
    hr = np.radians(H)
    dev = coef['const'] + sum(coef[f'sin{i}'] * np.sin(i * hr) + coef[f'cos{i}'] * np.cos(i * hr)
                              for i in range(1, 4))
    print('  hdg   dev    | 09-09 circles for comparison')
    ref = {0: 23.12, 30: 21.64, 60: 13.75, 90: 2.36, 120: -9.41, 150: -18.98,
           180: -24.66, 210: -25.42, 240: -20.39, 270: -9.63, 300: 4.38, 330: 16.81}
    for h, v in zip(H, dev):
        print(f'  {h:5.0f} {v:+7.2f}  | {ref[int(h)]:+7.2f}   diff {v-ref[int(h)]:+6.2f}')
