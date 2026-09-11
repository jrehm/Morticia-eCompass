"""
Addendum: (a) what magnetic moment would the outboard NEED to explain the
observed deviation difference, and (b) does heel explain the motoring/sailing
mode difference better than outboard position does?
"""
import numpy as np
import pandas as pd
from analyze_20260909_session import load, wrap180

MU0_4PI = 1e-7          # T*m/A
B_HORIZ = 15.6e-6       # T, horizontal component at 71 deg dip
R_SAIL, R_MOTOR = 4.0, 5.0   # m, outboard-to-eCompass per Jeff 2026-09-10

print('=' * 78)
print('A. REQUIRED MAGNETIC MOMENT OF THE OUTBOARD')
print('=' * 78)
# max (on-axis) dipole field: B = (mu0/4pi) * 2m / r^3
k = MU0_4PI * 2 * (1 / R_SAIL**3 - 1 / R_MOTOR**3)   # T per A*m^2, sail minus motor
print(f'  dB/dm between {R_SAIL} m and {R_MOTOR} m (on-axis, best case): {k:.3e} T per A*m^2')
for dev_deg in [70, 29, 10, 5, 1]:
    dB = B_HORIZ * np.tan(np.deg2rad(dev_deg))
    print(f'  to shift heading by {dev_deg:3d} deg  -> need dB = {dB*1e6:8.3f} uT '
          f'-> m = {dB/k:10.1f} A*m^2')
print()
for m in [1, 5, 20, 100]:
    dB = k * m
    print(f'  a {m:4d} A*m^2 source gives dB = {dB*1e6:9.5f} uT '
          f'-> {np.rad2deg(np.arctan(dB / B_HORIZ)):8.4f} deg of heading change')
print()
print('  Reference: a 10 kg strongly-magnetised steel object is order 1 A*m^2.')
print('  Cast aluminium and austenitic stainless are essentially non-magnetic.')
print()

print('=' * 78)
print('B. DOES HEEL EXPLAIN THE MODE DIFFERENCE?')
print('=' * 78)
df = load()
df['mode'] = df.seg.map({'1_motor_swing': 'motor', '2_prep': 'prep', '3_race': 'sail',
                         '4_sail': 'sail', '5_motor_home': 'motor'})
d = df[(df.SATS >= 6) & df['mode'].isin(['motor', 'sail'])].dropna(
    subset=['HDGmF', 'HDGmE', 'ROLL']).copy()
d['gapE'] = wrap180(d.HDGmE - d.HDGmF)
d['hbin'] = (d.HDGmF // 30 * 30).astype(int)

rows = []
for hb, g in d.groupby('hbin'):
    mo, sa = g[g['mode'] == 'motor'], g[g['mode'] == 'sail']
    if len(mo) < 30 or len(sa) < 30:
        continue
    # heel slope fitted WITHIN this heading bin, both modes pooled
    if g.ROLL.std() < 1.5:
        continue
    A = np.column_stack([np.ones(len(g)), g.ROLL.values])
    b, *_ = np.linalg.lstsq(A, g.gapE.values, rcond=None)
    obs = mo.gapE.mean() - sa.gapE.mean()
    d_roll = mo.ROLL.mean() - sa.ROLL.mean()
    pred = b[1] * d_roll
    rows.append(dict(hbin=hb, n_motor=len(mo), n_sail=len(sa),
                     roll_motor=mo.ROLL.mean(), roll_sail=sa.ROLL.mean(),
                     d_roll=d_roll, heel_slope=b[1],
                     obs_diff=obs, pred_from_heel=pred, residual=obs - pred))
t = pd.DataFrame(rows).set_index('hbin')
print(t.round(2).to_string())
print()
if len(t):
    print(f'  mean |observed mode difference|      : {t.obs_diff.abs().mean():.2f} deg')
    print(f'  mean |residual after heel term|      : {t.residual.abs().mean():.2f} deg')
    print(f'  variance explained by heel           : '
          f'{1 - t.residual.var()/t.obs_diff.var():.2f}')
