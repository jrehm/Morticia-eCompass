"""
Follow-up checks on the 2026-09-09 session. Run after analyze_20260909_session.py.

  A. Is the TC delta (HDGmT-HDGmE) sinusoidal in heading? Fit amplitude/phase.
  B. Is temperature identifiable this session, or confounded with time and heading?
  C. When did the trial solver (MFITT) fire, and what did it propose?
  D. Steady-state swing with a stricter detector (rolling-std, matching clean_data.py).
  E. Does the eCompass-fluxgate gap depend on roll/heel?
"""
import numpy as np
import pandas as pd
from analyze_20260909_session import load, wrap180, VARIATION

pd.set_option('display.width', 200)
df = load()

print('=' * 78)
print('A. IS THE TC DELTA SINUSOIDAL IN HEADING?')
print('=' * 78)
d = df.dropna(subset=['HDGmE', 'HDGmT']).copy()
d['dTC'] = wrap180(d.HDGmT - d.HDGmE)
h = np.deg2rad(d.HDGmE.values)
X = np.column_stack([np.ones(len(d)), np.sin(h), np.cos(h), np.sin(2 * h), np.cos(2 * h)])
b, *_ = np.linalg.lstsq(X, d.dTC.values, rcond=None)
amp1 = np.hypot(b[1], b[2])
ph1 = np.rad2deg(np.arctan2(b[2], b[1])) % 360
amp2 = np.hypot(b[3], b[4])
r2 = 1 - np.var(d.dTC.values - X @ b) / np.var(d.dTC.values)
print(f'  dTC = {b[0]:+.2f} + {amp1:.2f}*sin(H + {ph1:.1f}deg) + {amp2:.2f}*2H-term   R2={r2:.3f}')
print(f'  constant term  : {b[0]:+.2f} deg')
print(f'  semicircular   : {amp1:.2f} deg amplitude ({2*amp1:.1f} deg pk-pk)')
print(f'  quadrantal     : {amp2:.2f} deg amplitude')
print()
print('  -> An offset-vector correction MUST produce a semicircular (1-cycle)')
print('     heading change. A constant term is NOT predicted by that mechanism.')
print()

print('=' * 78)
print('B. IS TEMPERATURE IDENTIFIABLE THIS SESSION?')
print('=' * 78)
e = df.dropna(subset=['ETEMPf']).copy()
e['mins'] = (e.t - e.t.min()).dt.total_seconds() / 60
print(f'  ETEMP span      : {e.ETEMPf.min():.2f} - {e.ETEMPf.max():.2f} C  '
      f'({e.ETEMPf.max()-e.ETEMPf.min():.2f} C total)')
print(f'  distinct values : {sorted(e.ETEMPf.unique())}')
print(f'  corr(ETEMP, elapsed minutes) = {np.corrcoef(e.ETEMPf, e.mins)[0,1]:+.3f}')
hh = e.dropna(subset=['HDGmF'])
print(f'  corr(ETEMP, sin H) = {np.corrcoef(hh.ETEMPf, np.sin(np.deg2rad(hh.HDGmF)))[0,1]:+.3f}'
      f'   corr(ETEMP, cos H) = {np.corrcoef(hh.ETEMPf, np.cos(np.deg2rad(hh.HDGmF)))[0,1]:+.3f}')
print()
print('  mean heading (circular) within each ETEMP level:')
for v, g in hh.groupby('ETEMPf'):
    r = np.deg2rad(g.HDGmF.values)
    cm = np.rad2deg(np.arctan2(np.sin(r).mean(), np.cos(r).mean())) % 360
    print(f'    {v:6.2f} C  n={len(g):5d}  mean HDGmF {cm:6.1f} deg  '
          f'segments: {sorted(g.seg.unique())}')
print()

print('=' * 78)
print('C. TRIAL SOLVER (MFITT) ACTIVITY')
print('=' * 78)
m = df.dropna(subset=['MFITT']).copy()
nz = m[m.MFITT > 0]
print(f'  MFITT samples: {len(m)}, non-zero: {len(nz)} ({100*len(nz)/len(m):.1f}%)')
if len(nz):
    print(f'  first non-zero at {nz.t.iloc[0]}  (segment {nz.seg.iloc[0]})')
    print(f'  MFITT range while active: {nz.MFITT.min():.3f} - {nz.MFITT.max():.3f}')
print(f'  incumbent MFIT over session: {m.MFIT.iloc[0]:.4f} -> {m.MFIT.iloc[-1]:.4f} '
      f'(delta {m.MFIT.iloc[-1]-m.MFIT.iloc[0]:+.4f})')
print(f'  MSOLV (solver id) unique: {sorted(m.MSOLV.unique())}')
print(f'  MAGB unique values: {sorted(m.MAGB.unique())}   <- calibration parameter, not a measurement')
print()
print('  MFITT by segment:')
print(m.groupby('seg').agg(n=('MFITT', 'size'), pct_active=('MFITT', lambda s: 100*(s > 0).mean()),
                           mfitt_max=('MFITT', 'max'), mfit=('MFIT', 'mean')).round(2).to_string())
print()
print('  MINCL (magnetic inclination) — true dip is ~71 deg:')
print(m.groupby('seg').agg(n=('MINCL', 'size'), lo=('MINCL', 'min'), hi=('MINCL', 'max'),
                           mean=('MINCL', 'mean'), sd=('MINCL', 'std')).round(2).to_string())
print()

print('=' * 78)
print('D. SWING WITH STRICT STEADY-STATE DETECTOR')
print('=' * 78)
s = df[(df.seg == '1_motor_swing') & (df.SATS >= 6)].sort_values('t').copy()
s = s.dropna(subset=['COGt', 'SOG', 'HDGmF'])
# rolling std of heading over 10 s (unwrapped), plus steady SOG
s['hdg_u'] = np.rad2deg(np.unwrap(np.deg2rad(s.HDGmF.values)))
s['hstd'] = s.hdg_u.rolling(10, min_periods=8).std()
s['sogstd'] = s.SOG.rolling(10, min_periods=8).std()
st = s[(s.hstd < 2.0) & (s.sogstd < 0.5) & (s.SOG > 3.0)].copy()
st['cogm'] = wrap180(st.COGt - VARIATION)
print(f'  strict-steady rows: {len(st)} of {len(s)} motoring rows '
      f'({100*len(st)/len(s):.1f}%)')
st['hbin'] = (st.HDGmF // 30 * 30).astype(int)
for col, lab in [('HDGmF', 'fluxgate raw'), ('HDGmE', 'eCompass raw'), ('HDGmT', 'eCompass TC')]:
    x = st.dropna(subset=[col]).copy()
    if len(x) < 20:
        continue
    x['dev'] = wrap180(x[col] - x.cogm)
    t = x.groupby('hbin').agg(n=('dev', 'size'), dev=('dev', 'mean'), sd=('dev', 'std'))
    t = t[t.n >= 5]
    hb = np.deg2rad(t.index.values.astype(float) + 15)
    Xf = np.column_stack([np.ones(len(t)), np.sin(hb), np.cos(hb), np.sin(2*hb), np.cos(2*hb)])
    if len(t) >= 6:
        bb, *_ = np.linalg.lstsq(Xf, t.dev.values, rcond=None)
        A = np.hypot(bb[1], bb[2])
        rms = np.sqrt(np.mean((t.dev.values - Xf @ bb) ** 2))
        extra = (f'  | fit: const {bb[0]:+6.2f}  semicirc amp {A:5.2f}  '
                 f'quadr amp {np.hypot(bb[3], bb[4]):5.2f}  RMS {rms:.2f}')
    else:
        extra = ''
    print(f'--- {lab}: bins {len(t)}/12  pk-pk of bin means '
          f'{t.dev.max()-t.dev.min():.2f}  within-bin sd median {t.sd.median():.2f}{extra}')
    print(t.round(2).to_string())
    print()

print('=' * 78)
print('E. GAP vs ROLL / HEEL')
print('=' * 78)
r = df[(df.SATS >= 6)].dropna(subset=['HDGmF', 'HDGmT', 'ROLL']).copy()
r['gapT'] = wrap180(r.HDGmT - r.HDGmF)
r['hbin'] = (r.HDGmF // 30 * 30).astype(int)
r['rbin'] = pd.cut(r.ROLL, [-25, -10, -3, 3, 10, 25])
print('  gapT mean by (heading bin x roll bin) — look for row-wise trend:')
piv = r.pivot_table(index='hbin', columns='rbin', values='gapT', aggfunc='mean', observed=False)
cnt = r.pivot_table(index='hbin', columns='rbin', values='gapT', aggfunc='size', observed=False)
print(piv.round(1).to_string())
print('  counts:')
print(cnt.fillna(0).astype(int).to_string())
print()
print('  within-heading-bin regression of gapT on ROLL (bins with both signs of heel):')
for hb, g in r.groupby('hbin'):
    if len(g) < 100 or g.ROLL.std() < 3:
        continue
    A = np.column_stack([np.ones(len(g)), g.ROLL.values])
    bb, *_ = np.linalg.lstsq(A, g.gapT.values, rcond=None)
    rr = np.corrcoef(g.ROLL.values, g.gapT.values)[0, 1]
    print(f'    hbin {hb:3d}  n={len(g):5d}  roll sd {g.ROLL.std():5.2f}  '
          f'slope {bb[1]:+6.3f} deg gap per deg heel   r={rr:+.3f}')
