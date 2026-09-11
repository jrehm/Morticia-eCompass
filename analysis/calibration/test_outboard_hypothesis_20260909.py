"""
Test the outboard-position hypothesis for the motoring/sailing deviation difference.

Jeff's falsifiable prediction (2026-09-10): if the outboard is the source, the
magnetic data should step at the motor up/down transitions. Geometry he supplied:
outboard ~4 m from the eCompass when sailing (up/forward), ~5 m when motoring
(down/aft), no alternator, cast aluminium + stainless. Dipole 1/r^3 => the field
at the sensor is ~(5/4)^3 = 1.95x WEAKER while motoring. So the hypothesis also
has to explain a sign: motoring deviation is the LARGER one.

Three tests, none needing an absolute reference:

  T1. Matched-heading, matched-temperature mode comparison.
      seg 4 (sail, 19:43-19:52) vs seg 5 (motor home, 19:52+) are adjacent in
      time, both at ETEMP 24.0-24.96 C, and both occupy the 240 deg bin.
  T2. Step test across the 19:52 transition: gap and per-sensor residual vs time.
  T3. Whole-session: gap curve (HDGmE - HDGmF) by heading, motoring vs sailing.
      Needs no GPS. If the outboard moves, it sits at different distances from
      two differently-placed sensors, so the GAP should move too.
"""
import numpy as np
import pandas as pd
from analyze_20260909_session import load, wrap180, VARIATION

pd.set_option('display.width', 220)
df = load()
df['mode'] = df.seg.map({'1_motor_swing': 'motor', '2_prep': 'prep',
                         '3_race': 'sail', '4_sail': 'sail',
                         '5_motor_home': 'motor'})
d = df[df.SATS >= 6].dropna(subset=['HDGmF']).copy()
d['gapE'] = wrap180(d.HDGmE - d.HDGmF)
d['gapT'] = wrap180(d.HDGmT - d.HDGmF)
d['cogm'] = wrap180(d.COGt - VARIATION)
d['LEEf'] = pd.to_numeric(d.LEE, errors='coerce').fillna(0.0)
# leeway pushes COG to leeward of heading; under power it is ~0
d['devF'] = wrap180(d.HDGmF - d.cogm + d.LEEf)
d['devE'] = wrap180(d.HDGmE - d.cogm + d.LEEf)
d['hbin'] = (d.HDGmF // 30 * 30).astype(int)

print('=' * 80)
print('T1. MATCHED HEADING + MATCHED TEMPERATURE: seg4 (sail) vs seg5 (motor home)')
print('=' * 80)
sub = d[d.seg.isin(['4_sail', '5_motor_home'])]
t = sub.groupby(['hbin', 'seg']).agg(
    n=('gapE', 'size'), etemp=('ETEMPf', 'mean'),
    gapE=('gapE', 'mean'), gapE_sd=('gapE', 'std'),
    gapT=('gapT', 'mean'),
    devF=('devF', 'mean'), devF_sd=('devF', 'std'),
    devE=('devE', 'mean'),
    sog=('SOG', 'mean'), roll=('ROLL', 'mean'))
print(t.round(2).to_string())
print()
both = t.reset_index().pivot(index='hbin', columns='seg')
for hb in sorted(set(sub[sub.seg == '4_sail'].hbin) & set(sub[sub.seg == '5_motor_home'].hbin)):
    a = sub[(sub.hbin == hb) & (sub.seg == '4_sail')]
    b = sub[(sub.hbin == hb) & (sub.seg == '5_motor_home')]
    if len(a) < 20 or len(b) < 20:
        continue
    print(f'  bin {hb}: sail n={len(a)} vs motor n={len(b)}')
    for col in ['gapE', 'gapT', 'devF', 'devE']:
        va, vb = a[col].dropna(), b[col].dropna()
        if len(va) < 10 or len(vb) < 10:
            continue
        diff = vb.mean() - va.mean()
        se = np.hypot(va.std() / np.sqrt(len(va)), vb.std() / np.sqrt(len(vb)))
        print(f'    {col:5s} sail {va.mean():+7.2f} (sd {va.std():5.2f})   '
              f'motor {vb.mean():+7.2f} (sd {vb.std():5.2f})   '
              f'motor-sail {diff:+7.2f}  +/- {2*se:.2f} (2se)')
    print()

print('=' * 80)
print('T2. STEP TEST ACROSS THE 19:52 TRANSITION (30 s bins, 19:40-20:00)')
print('=' * 80)
w = d[(d.t >= '2026-09-09 19:40:00')].copy()
w['b30'] = w.t.dt.floor('30s')
t2 = w.groupby('b30').agg(n=('gapE', 'size'), hdg=('HDGmF', 'mean'),
                          gapE=('gapE', 'mean'), gapT=('gapT', 'mean'),
                          devF=('devF', 'mean'), devE=('devE', 'mean'),
                          MINCL=('MINCL', 'mean'), MNOIS=('MNOIS', 'mean'),
                          MFIT=('MFIT', 'mean'), sog=('SOG', 'mean'),
                          roll=('ROLL', 'mean'), etemp=('ETEMPf', 'mean'))
print(t2.round(2).to_string())
print()

print('=' * 80)
print('T3. GAP CURVE BY HEADING: MOTORING vs SAILING (no GPS reference needed)')
print('=' * 80)
g = d[d['mode'].isin(['motor', 'sail'])]
piv = g.pivot_table(index='hbin', columns='mode', values='gapE', aggfunc='mean')
cnt = g.pivot_table(index='hbin', columns='mode', values='gapE', aggfunc='size')
sd = g.pivot_table(index='hbin', columns='mode', values='gapE', aggfunc='std')
tp = g.pivot_table(index='hbin', columns='mode', values='ETEMPf', aggfunc='mean')
out = pd.concat([cnt.add_suffix('_n'), piv.add_suffix('_gapE'),
                 sd.add_suffix('_sd'), tp.add_suffix('_T')], axis=1)
out['diff'] = piv['motor'] - piv['sail']
print(out.round(2).to_string())
print()
ok = out.dropna(subset=['diff'])
ok = ok[(ok.motor_n >= 30) & (ok.sail_n >= 30)]
print(f'bins with >=30 samples in both modes: {len(ok)}')
if len(ok):
    print(f'  mean |motor-sail| gap difference: {ok["diff"].abs().mean():.2f} deg')
    print(f'  range: {ok["diff"].min():+.2f} to {ok["diff"].max():+.2f} deg')
    print(f'  mean within-bin sd (motor {ok.motor_sd.mean():.2f}, sail {ok.sail_sd.mean():.2f})')
    print(f'  mean temperature difference motor-sail: {(ok.motor_T-ok.sail_T).mean():+.2f} C')
print()

print('=' * 80)
print('T3b. SAME, USING THE TC PATH (gapT)')
print('=' * 80)
piv2 = g.pivot_table(index='hbin', columns='mode', values='gapT', aggfunc='mean')
cnt2 = g.pivot_table(index='hbin', columns='mode', values='gapT', aggfunc='size')
o2 = pd.concat([cnt2.add_suffix('_n'), piv2.add_suffix('_gapT')], axis=1)
o2['diff'] = piv2['motor'] - piv2['sail']
print(o2.round(2).to_string())
