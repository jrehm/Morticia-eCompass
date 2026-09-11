"""
Direct test on the magnetic field vector itself (InfluxDB, 1 Hz).

The decisive measurement: fit the hard-iron offset SEPARATELY for the motoring
and sailing portions and compare the centres. If moving the outboard changes the
field at the sensor, the fitted hard-iron centre must move by exactly that amount.

Physics prediction (test_outboard_addendum): the 4 m -> 5 m move is worth
~0.008 uT for a plausible ~5 A*m^2 source. The deviation-difference hypothesis
requires ~7-43 uT. These differ by >3 orders of magnitude, so the fit decides it.

Also: step test on |B| at matched heading across the 19:52 EDT transition.
"""
import numpy as np
import pandas as pd

RAW = ['orientation.calibration.magfieldvector.x',
       'orientation.calibration.magfieldvector.y',
       'orientation.calibration.magfieldvector.z']
TC = ['orientation.calibration.magfieldvectortc.x',
      'orientation.calibration.magfieldvectortc.y',
      'orientation.calibration.magfieldvectortc.z']

df = pd.read_csv('/tmp/magvec_20260909.csv', skiprows=0)
df = df[[c for c in df.columns if c not in ('', 'result', 'table')]]
df['_time'] = pd.to_datetime(df['_time'])
df = df.set_index('_time').sort_index()
df = df.resample('1s').mean().ffill(limit=5)
df['hdgE'] = np.degrees(df['sensors.ecompass.headingMagnetic']) % 360
df['hdgF'] = np.degrees(df['sensors.fluxgate.headingMagnetic']) % 360
df['roll'] = np.degrees(df['navigation.attitude.roll'])
df['Braw'] = np.sqrt((df[RAW] ** 2).sum(axis=1))
df['Btc'] = np.sqrt((df[TC] ** 2).sum(axis=1))

# segments, in UTC (EDT + 4)
edges = [('22:00', '22:35', 'motor'), ('22:35', '23:00', 'prep'),
         ('23:00', '23:43', 'sail'), ('23:43', '23:52', 'sail'),
         ('23:52', '00:05', 'motor')]
df['mode'] = None
d0 = pd.Timestamp('2026-09-09', tz='UTC')
for a, b, m in edges:
    day = d0 if a >= '22:00' else d0 + pd.Timedelta(days=1)
    ta = pd.Timestamp(f'2026-09-{"09" if a >= "22:00" else "10"} {a}', tz='UTC')
    tb = pd.Timestamp(f'2026-09-{"09" if b > "22:00" else "10"} {b}', tz='UTC')
    df.loc[(df.index >= ta) & (df.index < tb), 'mode'] = m

v = df.dropna(subset=RAW + ['hdgF']).copy()
print(f'rows with full raw vector + heading: {len(v)}')
print(v.groupby('mode').agg(n=('Braw', 'size'), Braw_mean=('Braw', 'mean'),
                            Braw_sd=('Braw', 'std'), roll_sd=('roll', 'std')).round(3).to_string())
print()


def sphere_fit(B):
    """Least-squares hard-iron centre: |B-c|^2 = r^2, linear in (c, k)."""
    A = np.column_stack([2 * B[:, 0], 2 * B[:, 1], 2 * B[:, 2], np.ones(len(B))])
    y = (B ** 2).sum(axis=1)
    x, *_ = np.linalg.lstsq(A, y, rcond=None)
    c = x[:3]
    r = np.sqrt(max(x[3] + c @ c, 0))
    resid = np.sqrt(((B - c) ** 2).sum(axis=1)) - r
    return c, r, float(np.sqrt(np.mean(resid ** 2)))


def boot_centre(B, n=200, frac=0.5, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        idx = rng.choice(len(B), int(len(B) * frac), replace=False)
        try:
            out.append(sphere_fit(B[idx])[0])
        except Exception:
            pass
    return np.array(out)


print('=' * 78)
print('HARD-IRON CENTRE FITTED SEPARATELY BY MODE (raw vector)')
print('=' * 78)
res = {}
for m in ['motor', 'sail']:
    s = v[v['mode'] == m]
    B = s[RAW].to_numpy()
    c, r, rms = sphere_fit(B)
    bs = boot_centre(B)
    se = bs.std(axis=0)
    res[m] = (c, se, r, rms, len(B), s.hdgF)
    occ = len(np.unique((s.hdgF // 30 * 30).astype(int)))
    print(f'{m:6s} n={len(B):5d}  heading bins {occ}/12  radius {r:7.3f} uT  fit RMS {rms:.3f} uT')
    print(f'        centre = [{c[0]:+7.3f} {c[1]:+7.3f} {c[2]:+7.3f}] uT'
          f'   bootstrap se [{se[0]:.3f} {se[1]:.3f} {se[2]:.3f}]')
print()
cm, sem = res['motor'][0], res['motor'][1]
cs, ses = res['sail'][0], res['sail'][1]
dc = cm - cs
dse = np.hypot(sem, ses)
print(f'  motor - sail centre difference = [{dc[0]:+.3f} {dc[1]:+.3f} {dc[2]:+.3f}] uT')
print(f'                          +/- 2se  [{2*dse[0]:.3f} {2*dse[1]:.3f} {2*dse[2]:.3f}]')
print(f'  magnitude of difference = {np.linalg.norm(dc):.3f} uT')
print()
print('  Required by the outboard hypothesis, to explain the deviation gap:')
print('    ~8.6 uT for 29 deg,  ~43 uT for 70 deg')
print('  Predicted by dipole physics for a ~5 A*m^2 source at 4 m vs 5 m: 0.008 uT')
print()

print('=' * 78)
print('STEP TEST ON |B| AT MATCHED HEADING ACROSS THE 19:52 EDT TRANSITION')
print('=' * 78)
w = v[(v.index >= '2026-09-09 23:48:00+00:00') & (v.index <= '2026-09-10 00:00:00+00:00')].copy()
w = w[(w.hdgF >= 235) & (w.hdgF <= 260)]
w['side'] = np.where(w.index < pd.Timestamp('2026-09-09 23:52:00', tz='UTC'), 'before', 'after')
print(f'  rows in the 235-260 deg heading band: {len(w)}')
t = w.groupby('side').agg(n=('Braw', 'size'), hdg=('hdgF', 'mean'),
                          Braw=('Braw', 'mean'), Braw_sd=('Braw', 'std'),
                          Btc=('Btc', 'mean'), roll=('roll', 'mean'))
print(t.round(3).to_string())
if len(t) == 2:
    a, b = t.loc['before'], t.loc['after']
    se = np.hypot(a.Braw_sd / np.sqrt(a.n), b.Braw_sd / np.sqrt(b.n))
    print(f'\n  |B| after - before = {b.Braw - a.Braw:+.3f} uT  +/- {2*se:.3f} (2se)')
print()
print('  per-axis, same band:')
for ax in RAW:
    a = w[w.side == 'before'][ax]
    b = w[w.side == 'after'][ax]
    se = np.hypot(a.std() / np.sqrt(len(a)), b.std() / np.sqrt(len(b)))
    print(f'    {ax.split(".")[-1]}: before {a.mean():+8.3f}  after {b.mean():+8.3f}  '
          f'delta {b.mean()-a.mean():+7.3f} +/- {2*se:.3f}')
