"""Which eCompass heading path is actually right in absolute terms?

The swing gives COG-magnetic as a reference. Fit each heading source the same
way (Fourier + turn-rate covariate) and compare the CONSTANT term.

Key point: a uniform current contaminates the SEMICIRCULAR term, not the
constant, so the constant is comparatively robust here -- it is limited mainly
by the variation figure (-7.68) rather than by the current degeneracy that
blocks the deviation amplitude.
"""
import numpy as np
from fit_fluxgate_swing_20260909 import load, find_swings, fit, curve
import pandas as pd

df = load()
m, swings = find_swings(df)
pool = pd.concat([s for _, s, _ in swings])

print(f'pooled swing rows: {len(pool)}')
print()
print(f'{"source":28s} {"n":>5s} {"const":>9s} {"semicirc":>9s} {"quadr":>8s} '
      f'{"g_turn":>8s} {"RMS":>7s}')
print('-' * 80)
for col, lab in [('hdgF', 'fluxgate raw (HDGmF)'),
                 ('hdgE', 'eCompass fusion (HDGmE)'),
                 ('hdgT', 'eCompass TC (HDGmT)')]:
    if col not in pool or pool[col].notna().sum() < 50:
        print(f'{lab:28s}  (insufficient data)')
        continue
    coef, rms, n = fit(pool, col, k=3, with_w=True)
    semi = np.hypot(coef['sin1'], coef['cos1'])
    quad = np.hypot(coef['sin2'], coef['cos2'])
    print(f'{lab:28s} {n:5d} {coef["const"]:+9.2f} {semi:9.2f} {quad:8.2f} '
          f'{coef["g_turn"]:+8.3f} {rms:7.2f}')

print()
print('Interpretation of the constant: it is (source reading - magnetic heading),')
print('so a positive constant means the source reads HIGH and the config offset')
print('for that path should be reduced by that amount.')
print()
d = pool.dropna(subset=['hdgE', 'hdgT'])
if len(d):
    from fit_fluxgate_swing_20260909 import wrap180
    print(f'cross-check, HDGmT - HDGmE over the swings: '
          f'{np.mean(wrap180(d.hdgT - d.hdgE)):+.2f} deg (n={len(d)})')
