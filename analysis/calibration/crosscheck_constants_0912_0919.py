"""Cross-session check of the heading constants found on 2026-09-09.

09-09 (two dedicated motoring circles, full heading coverage) gave, vs COG-magnetic:
    HDGmF  -2.20    HDGmE  -14.82    HDGmT  +2.16

No circles were run on 09-12 / 09-19, but both sessions contain motoring legs
(flat, fast, and in places at TWA too tight to be sailing). Under power leeway
is ~0, so COG is a usable magnetic-heading reference.

LIMITATION: a delivery leg covers few headings, so the constant and the
semicircular deviation term are only partly separable. Two legs on roughly
opposite headings help, because a semicircular term largely cancels when
reciprocal headings are averaged. Treat the constants as corroboration of
09-09, not as independent absolute measurements.

eCompass config verified unchanged 2026-10-02: /sensors/hdg/offset = -15.0 deg,
/sensors/hdg/tc_offset = 0, thermal slope -0.17 @ tref 30.4 -- so these numbers
are directly comparable to 09-09.
"""
import numpy as np
import pandas as pd

VARIATION = -7.68

SEGMENTS = {
    '09-12': ('sailing_20260912_133000_to_20260912_163000.csv', [
        ('M1 out',  '2026-09-12 13:30', '2026-09-12 14:50'),
        ('M2 home', '2026-09-12 16:00', '2026-09-12 16:30'),
    ]),
    '09-19': ('sailing_20260919_140000_to_20260919_231500.csv', [
        ('M1 out',  '2026-09-19 14:00', '2026-09-19 15:00'),
        ('M2 home', '2026-09-19 21:40', '2026-09-19 23:15'),
    ]),
}


def wrap180(x):
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def load(f):
    d = pd.read_csv(f)
    d['t'] = pd.to_datetime(d.timestamp)
    d = d.set_index('t').sort_index()
    for c in ['SOG', 'COGt', 'HDGmE', 'HDGmT', 'HDGmF', 'ROLL', 'SATS', 'TWA', 'LEE']:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    d['SATS'] = d['SATS'].ffill(limit=3)
    d['cogm'] = wrap180(d['COGt'] - VARIATION)
    h = d['HDGmF'].to_numpy(float)
    ok = ~np.isnan(h)
    hu = np.full(len(h), np.nan)
    hu[ok] = np.degrees(np.unwrap(np.radians(h[ok])))
    d['w'] = pd.Series(hu, index=d.index).diff().rolling(5, center=True, min_periods=3).mean()
    return d


def fit(sub, col, k=2):
    s = sub.dropna(subset=[col, 'cogm', 'w'])
    if len(s) < 60:
        return None
    dev = wrap180(s[col] - s['cogm'])
    h = np.radians(s[col].to_numpy(float))
    cols = [np.ones(len(s))]
    names = ['const']
    for i in range(1, k + 1):
        cols += [np.sin(i * h), np.cos(i * h)]
        names += [f'sin{i}', f'cos{i}']
    cols.append(s.w.to_numpy(float))
    names.append('g_turn')
    X = np.column_stack(cols)
    b, *_ = np.linalg.lstsq(X, dev, rcond=None)
    resid = dev - X @ b
    return dict(zip(names, b)), float(np.sqrt(np.mean(resid ** 2))), len(s), dev.mean()


print('=' * 92)
print('MOTORING SEGMENT PROFILE (confirm these boundaries)')
print('=' * 92)
frames = {}
for lab, (f, segs) in SEGMENTS.items():
    d = load(f)
    for name, a, b in segs:
        s = d.loc[a:b]
        s = s[(s.SOG > 3.0)]
        if 'SATS' in s:
            s = s[(s.SATS >= 6) | s.SATS.isna()]
        frames[f'{lab} {name}'] = s
        hdgs = s.HDGmF.dropna()
        occ = sorted(set((hdgs // 30 * 30).astype(int))) if len(hdgs) else []
        print(f'{lab} {name:8s} n={len(s):5d}  SOG {s.SOG.median():5.1f} kn  '
              f'|roll| {s.ROLL.abs().mean():4.1f}  |TWA| {s.TWA.abs().median():5.1f}  '
              f'LEE {s.LEE.abs().mean():4.2f}  30deg-bins {occ}')
print()

print('=' * 92)
print('CONSTANTS vs COG-MAGNETIC   (09-09 reference: HDGmF -2.20, HDGmE -14.82, HDGmT +2.16)')
print('=' * 92)
print(f'{"segment":22s} {"source":7s} {"n":>6s} {"const":>8s} {"raw mean":>9s} '
      f'{"semicirc":>9s} {"g_turn":>8s} {"RMS":>7s}')
print('-' * 92)
rows = []
for key, s in frames.items():
    for col in ['HDGmF', 'HDGmE', 'HDGmT']:
        r = fit(s, col)
        if r is None:
            print(f'{key:22s} {col:7s}  (insufficient)')
            continue
        coef, rms, n, rawmean = r
        semi = np.hypot(coef['sin1'], coef['cos1'])
        print(f'{key:22s} {col:7s} {n:6d} {coef["const"]:+8.2f} {rawmean:+9.2f} '
              f'{semi:9.2f} {coef["g_turn"]:+8.3f} {rms:7.2f}')
        rows.append((key, col, coef['const'], rawmean, n))
    print()

print('=' * 92)
print('POOLED PER SESSION (both legs together -- reciprocal headings cancel semicircular)')
print('=' * 92)
for lab in SEGMENTS:
    pool = pd.concat([v for k, v in frames.items() if k.startswith(lab)])
    print(f'--- {lab}  n={len(pool)}')
    for col in ['HDGmF', 'HDGmE', 'HDGmT']:
        r = fit(pool, col)
        if r is None:
            continue
        coef, rms, n, rawmean = r
        print(f'    {col:7s} const {coef["const"]:+7.2f}   raw mean dev {rawmean:+7.2f}   '
              f'semicirc {np.hypot(coef["sin1"],coef["cos1"]):6.2f}   RMS {rms:5.2f}   n={n}')
    print()

print('=' * 92)
print('DIFFERENCES BETWEEN PATHS (robust -- independent of variation and of COG bias)')
print('=' * 92)
for lab in SEGMENTS:
    pool = pd.concat([v for k, v in frames.items() if k.startswith(lab)])
    d = pool.dropna(subset=['HDGmE', 'HDGmT'])
    if len(d):
        print(f'{lab}: HDGmT - HDGmE = {np.mean(wrap180(d.HDGmT - d.HDGmE)):+7.2f} '
              f'(sd {np.std(wrap180(d.HDGmT - d.HDGmE)):5.2f}, n={len(d)})   '
              f'[09-09 motoring: +16.70]')
    d2 = pool.dropna(subset=['HDGmE', 'HDGmF'])
    if len(d2):
        print(f'{lab}: HDGmE - HDGmF = {np.mean(wrap180(d2.HDGmE - d2.HDGmF)):+7.2f} '
              f'(sd {np.std(wrap180(d2.HDGmE - d2.HDGmF)):5.2f}, n={len(d2)})')
