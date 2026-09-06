#!/usr/bin/env python3
"""Cross-session HDGmE-HDGmF gap fit, v2.

Improvements over the 2026-09-05 first pass:
  - both sessions from raw exports (08-26 previously came from an Excel copy)
  - full underway windows, not narrow slices
  - GPS rows filtered on actual fix quality (SATS/HDOP) not a freeze heuristic
  - die temperature available, so the thermal term can be tested explicitly
"""
import pandas as pd, numpy as np, itertools
pd.set_option('display.width', 240)
D = '/Users/jrehm/Documents/GitHub/Morticia-eCompass/analysis/calibration/'
FILES = {'08-26': 'sailing_20260826_180000_to_20260826_203000.csv',
         '09-02': 'sailing_20260902_180000_to_20260902_203000.csv'}
TREF = 30.4          # TCO model reference temperature, deg C
MIN_SATS, MAX_HDOP = 6, 5.0

def wrap(x): return ((x + 180) % 360) - 180

def load(f):
    d = pd.read_csv(D + f)
    d['t'] = pd.to_datetime(d.timestamp)
    for c in ['HDGmE','HDGmF','SOG','COGt','LAT','LON','ETEMP','SATS','HDOP',
              'TWA','TWD','TWS','ROLL','MROT']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['ETEMP'] = d.ETEMP.ffill().bfill()          # ~0.25 Hz vs 1 Hz elsewhere
    # SATS/HDOP publish at ~1 Hz but drop the odd tick: null runs are median 1 s,
    # max 3 s. Those are transport gaps, not fix loss -- satellite count does not
    # change meaningfully in 1-3 s. Without this they are silently discarded,
    # because `NaN >= MIN_SATS` is False, costing ~15% of each session for no
    # reason. Limit of 3 covers every observed run without bridging a real outage.
    d['SATS'] = d.SATS.ffill(limit=3)
    d['HDOP'] = d.HDOP.ffill(limit=3)
    lat0, lon0 = d.LAT.iloc[:60].median(), d.LON.iloc[:60].median()
    d['disp_m'] = np.sqrt(((d.LAT-lat0)*60)**2 +
                          ((d.LON-lon0)*60*np.cos(np.deg2rad(lat0)))**2) * 1852
    return d

def clean(d):
    n0 = len(d)
    steps = [('all rows', d)]
    d = d[d.disp_m > 500];                       steps.append(('underway', d))
    d = d[d.HDGmE.notna() & d.HDGmF.notna()];    steps.append(('both compasses', d))
    # Explicit about nulls: after the short ffill, any remaining NaN is a real
    # gap, not a fix report of zero. Drop it deliberately rather than letting
    # the >= comparison do it silently.
    d = d[d.SATS.notna()];                       steps.append(('SATS present', d))
    d = d[d.SATS >= MIN_SATS];                   steps.append(('SATS>=%d' % MIN_SATS, d))
    d = d[(d.HDOP > 0) & (d.HDOP <= MAX_HDOP)];  steps.append(('0<HDOP<=%.1f' % MAX_HDOP, d))
    return d.copy(), steps, n0

def design(H, T, k=2, thermal=False):
    r = np.deg2rad(H); X = [np.ones(len(H))]
    for i in range(1, k+1):
        X += [np.sin(i*r), np.cos(i*r)]
    if thermal:
        dT = T - TREF
        X += [dT, dT*np.sin(r), dT*np.cos(r)]
    return np.column_stack(X)

def fit(X, y):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b, y - X @ b

S = {}
print("=" * 78); print("CLEANING")
for lab, f in FILES.items():
    d = load(f); c, steps, n0 = clean(d)
    c['H'] = c.HDGmF % 360
    c['gap'] = wrap(c.HDGmE - c.HDGmF)
    S[lab] = c
    print("\n%s" % lab)
    for name, sub in steps:
        print("   %-18s %5d  (%.0f%% of raw)" % (name, len(sub), 100*len(sub)/n0))
    print("   ETEMP %.1f-%.1f C (median %.1f)   TWD circmean %.0f deg" % (
        c.ETEMP.min(), c.ETEMP.max(), c.ETEMP.median(),
        np.rad2deg(np.arctan2(np.sin(np.deg2rad(c.TWD)).mean(),
                              np.cos(np.deg2rad(c.TWD)).mean())) % 360))

print("\n" + "=" * 78); print("HEADING COVERAGE (30 deg bins, cleaned)")
cov = {lab: pd.cut(c.H, bins=np.arange(0, 361, 30)).value_counts().sort_index()
       for lab, c in S.items()}
print(pd.DataFrame(cov).fillna(0).astype(int).to_string())

print("\n" + "=" * 78); print("MODEL SELECTION (RMS residual, deg)")
rows = []
for k, th in itertools.product((1, 2, 3), (False, True)):
    r = {'k': k, 'thermal': th}
    for lab, c in S.items():
        _, res = fit(design(c.H.values, c.ETEMP.values, k, th), c.gap.values)
        r[lab] = round(np.sqrt((res**2).mean()), 2)
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))

print("\n" + "=" * 78); print("COEFFICIENTS (k=2)")
names_p = ['A','sin H','cos H','sin2H','cos2H']
names_t = names_p + ['dT','dT*sinH','dT*cosH']
for th, nm in ((False, names_p), (True, names_t)):
    tab = {}
    for lab, c in S.items():
        b, _ = fit(design(c.H.values, c.ETEMP.values, 2, th), c.gap.values)
        tab[lab] = np.round(b, 2)
    print("\n  thermal=%s" % th)
    print(pd.DataFrame(tab, index=nm).to_string())

print("\n" + "=" * 78); print("OUT-OF-SAMPLE CROSS-VALIDATION (fit one session, predict the other)")
rows = []
for th in (False, True):
    for src, dst in (('08-26','09-02'), ('09-02','08-26')):
        b, _ = fit(design(S[src].H.values, S[src].ETEMP.values, 2, th), S[src].gap.values)
        Xd = design(S[dst].H.values, S[dst].ETEMP.values, 2, th)
        e = wrap(S[dst].gap.values - Xd @ b)
        rows.append({'thermal': th, 'fit on': src, 'predict': dst,
                     'bias': round(e.mean(), 2), 'RMS': round(np.sqrt((e**2).mean()), 2)})
print(pd.DataFrame(rows).to_string(index=False))

print("\n" + "=" * 78); print("POOLED FIT")
both = pd.concat([S['08-26'].assign(sess='08-26'), S['09-02'].assign(sess='09-02')])
for th, nm in ((False, names_p), (True, names_t)):
    b, res = fit(design(both.H.values, both.ETEMP.values, 2, th), both.gap.values)
    print("\n  thermal=%s   RMS=%.2f   n=%d" % (th, np.sqrt((res**2).mean()), len(both)))
    print("   " + "  ".join("%s=%.2f" % (n, v) for n, v in zip(nm, b)))
    if th:
        both = both.copy(); both['resid'] = res

print("\n" + "=" * 78); print("RESIDUAL DIAGNOSTICS (pooled, thermal k=2)")
print("  corr(resid, TWA)=%+.3f   corr(resid, ROLL)=%+.3f   corr(resid, ETEMP)=%+.3f   corr(resid, MROT)=%+.3f"
      % (both.resid.corr(both.TWA), both.resid.corr(both.ROLL),
         both.resid.corr(both.ETEMP), both.resid.corr(both.MROT)))
print("\n  by session:")
print(both.groupby('sess').resid.agg(['count','mean','std']).round(2).to_string())
print("\n  by TWA band:")
print(both.groupby(pd.cut(both.TWA, [-180,-120,-60,-20,20,60,120,180]),
                   observed=True).resid.agg(['count','mean','std']).round(2).to_string())
print("\n  by heading (30 deg):")
print(both.groupby(pd.cut(both.H, np.arange(0,361,30)),
                   observed=True).resid.agg(['count','mean','std']).round(2).to_string())
