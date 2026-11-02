"""Resolve the 10-degree contradiction using the Oct 3 / Oct 18 motoring legs.

The conflict (unresolved since 2026-10-02):
  dock geometry        dev(HDGmF~190) ~ -9     (dock bears 106.7/286.7 T, boat
                                                 low-190s T, fluxgate reads ~190 M)
  under way vs COG     dev(HDGmF~190) ~ -19    (41k samples, 3 sessions)
  Ruled out: current/leeway (dev flat across 2.5-25 kn), variation sign,
             COG path mapping, eCompass arbitration.

Jeff's segmentation (2026-10-31):
  Oct 3  06:35-07:20 motor to start; first ~15-20 min was Detroit River -> drop
         08:30-20:46 racing;  12:20-18:30 in a river with 2+ kt current
         20:46-21:45 motor home
         "with the exception of the first 15-20 min, motoring was generally N/S
          with near zero LATERAL current"
  Oct 18 10:38-11:19 down, 12:34-13:09 back -- motoring only, N/S, IN THE
         DIRECTION of the current (so the lateral component is ~0)

Why this settles it: with zero lateral set, COG must equal heading under power.
Any residual set reverses between reciprocal legs, so averaging a down/back pair
cancels it. If dev still reads ~-19 there, the deviation is real and the slip is
anomalous. If it collapses toward -9, the COG reference is what is broken.
"""
import numpy as np
import pandas as pd

VARIATION = -7.68

WINDOWS = [
    ('Oct03 motor-out (post-river)', 'sailing_20261003_063000_to_20261003_214500.csv',
     '2026-10-03 06:55', '2026-10-03 07:20'),
    ('Oct03 motor-home',             'sailing_20261003_063000_to_20261003_214500.csv',
     '2026-10-03 20:46', '2026-10-03 21:45'),
    ('Oct18 down',                   'sailing_20261018_103000_to_20261018_131500.csv',
     '2026-10-18 10:38', '2026-10-18 11:19'),
    ('Oct18 back',                   'sailing_20261018_103000_to_20261018_131500.csv',
     '2026-10-18 12:34', '2026-10-18 13:09'),
]

# previous pooled model (09-09/12/19), for comparison
PREV = [-3.37775, 15.74661, 7.58289, -0.73300, 0.88178, -1.32417, -0.90716]


def wrap180(x):
    return (np.asarray(x, float) + 180.0) % 360.0 - 180.0


def prev_model(H):
    h = np.radians(np.asarray(H, float))
    return (PREV[0] + PREV[1] * np.cos(h) + PREV[2] * np.sin(h)
            + PREV[3] * np.cos(2 * h) + PREV[4] * np.sin(2 * h)
            + PREV[5] * np.cos(3 * h) + PREV[6] * np.sin(3 * h))


_cache = {}


def load(f):
    if f in _cache:
        return _cache[f]
    d = pd.read_csv(f)
    d['t'] = pd.to_datetime(d.timestamp, format='mixed')
    d = d.set_index('t').sort_index()
    for c in ['SOG', 'COGt', 'HDGmF', 'HDGmT', 'HDGmE', 'ROLL', 'SATS']:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    d['SATS'] = d['SATS'].ffill(limit=3)
    d['cogm'] = wrap180(d['COGt'] - VARIATION)
    d['dev'] = wrap180(d['HDGmF'] - d['cogm'])
    _cache[f] = d
    return d


print('=' * 94)
print('MOTORING LEGS — measured deviation vs COG-magnetic')
print('=' * 94)
segs = {}
for name, f, a, b in WINDOWS:
    d = load(f).loc[a:b]
    d = d[(d.SOG > 2.5) & ((d.SATS >= 6) | d.SATS.isna())].dropna(subset=['HDGmF', 'cogm'])
    segs[name] = d
    hd = d.HDGmF.dropna()
    print(f'{name:30s} n={len(d):5d}  SOG {d.SOG.median():5.1f}  '
          f'hdg {hd.min():5.1f}-{hd.max():5.1f}  '
          f'dev mean {d.dev.mean():+7.2f}  median {d.dev.median():+7.2f}  sd {d.dev.std():5.2f}')
print()

print('=' * 94)
print('BY 30-DEG HEADING BIN, per leg  (prev = the 09-09/12/19 pooled model)')
print('=' * 94)
for name, d in segs.items():
    if not len(d):
        continue
    x = d.copy()
    x['bin'] = (x.HDGmF // 30 * 30).astype(int)
    t = x.groupby('bin').agg(n=('dev', 'size'), dev=('dev', 'mean'), sd=('dev', 'std'))
    t = t[t.n >= 30]
    if not len(t):
        continue
    t['prev'] = prev_model(t.index.values + 15)
    t['diff'] = t.dev - t.prev
    print(f'--- {name}')
    print(t.round(2).to_string())
    print()

print('=' * 94)
print('RECIPROCAL PAIRING — Oct 18 down vs back (cancels any earth-fixed set)')
print('=' * 94)
dn, bk = segs['Oct18 down'], segs['Oct18 back']
for lab, s in [('down', dn), ('back', bk)]:
    h = s.HDGmF.dropna()
    r = np.deg2rad(h)
    cm = np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360
    print(f'  {lab:5s} mean heading {cm:6.1f}   dev {s.dev.mean():+7.2f}  '
          f'sd {s.dev.std():5.2f}  n={len(s)}')
print(f'  --> mean of the two legs: {(dn.dev.mean() + bk.dev.mean()) / 2:+.2f} deg')
print('      (any uniform set contributes equally and oppositely; the deviation')
print('       curve does NOT cancel unless the two headings are exact reciprocals,')
print('       so read this alongside the per-bin table above.)')
print()

print('=' * 94)
print('THE DECISIVE COMPARISON  — what is dev near the mooring heading (~190)?')
print('=' * 94)
allm = pd.concat(segs.values())
band = allm[(allm.HDGmF >= 170) & (allm.HDGmF <= 210)]
print(f'  Oct 3 + Oct 18 motoring, HDGmF 170-210:  n={len(band)}  '
      f'dev mean {band.dev.mean():+.2f}  median {band.dev.median():+.2f}  sd {band.dev.std():.2f}')
print(f'  dock geometry says ....................  about  -9')
print(f'  Sep sessions said .....................  about -19')
print()
for name, d in segs.items():
    s = d[(d.HDGmF >= 170) & (d.HDGmF <= 210)]
    if len(s) >= 20:
        print(f'    {name:30s} n={len(s):5d}  dev {s.dev.mean():+7.2f}  sd {s.dev.std():5.2f}')
