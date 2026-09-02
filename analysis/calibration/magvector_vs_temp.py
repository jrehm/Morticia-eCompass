#!/usr/bin/env python3
"""
magvector_vs_temp.py — DC magnetometer drift vs. die temperature from live InfluxDB.

Pulls orientation.calibration.magfieldvector.{x,y,z}, die temperature, Kalman inclination,
and eCompass/fluxgate headings from the signalk bucket on HALPI2 (via `ssh halos
~/bin/fluxq`), then prints a half-hourly table and per-axis slopes dB/dT (uT/C).

Usage:
  python magvector_vs_temp.py                  # since 2026-09-02T00:00Z (vector publish start)
  python magvector_vs_temp.py 2026-09-03T00:00:00Z [stop_iso] [--window 30min]

Reading the output:
  - bx, by, bz  : calibrated field vector Bc in the sensor frame (uT). At the dock, +y carries
                  the horizontal field (~ toward the stern at heading 190), z is down.
  - Bh, mag     : hypot(bx,by) and |Bc|. Undisturbed expectations at Lake St. Clair with the
                  stored B = 48.09: Bh ~ 15.7, Bz ~ 45.5, mag = 48.09.
  - incl_vec    : atan2(bz, Bh) from the vector; incl is the Kalman's fDeltaPl. Nights ~71.
  - gap         : eCompass - fluxgate heading (deg). Fluxgate is the reference.
  - slopes      : linear fit of each axis against temperature; the axis with the big slope
                  is the thermal disturbance direction. Compare to the creep by looking at
                  the residual at a fixed temperature across days.
"""
import subprocess, sys, io
import numpy as np, pandas as pd

PATHS = {
    'bx': 'orientation.calibration.magfieldvector.x',
    'by': 'orientation.calibration.magfieldvector.y',
    'bz': 'orientation.calibration.magfieldvector.z',
    'temp': 'environment.inside.ecompass.temperature',
    'incl': 'orientation.calibration.maginclination',
    'hE': 'sensors.ecompass.headingMagnetic',
    'hF': 'sensors.fluxgate.headingMagnetic',
}

def fluxq(q):
    return subprocess.run(['ssh', 'halos', f'~/bin/fluxq {q!r}'], capture_output=True, text=True, check=True).stdout

def series(path, start, stop, every):
    q = (f'from(bucket:"signalk") |> range(start: {start}, stop: {stop}) '
         f'|> filter(fn: (r) => r._measurement == "{path}" and r._field == "value") '
         f'|> aggregateWindow(every: {every}, fn: mean, createEmpty:false) |> keep(columns:["_time","_value"])')
    raw = fluxq(q).replace('\r', '')
    rows = [l.split(',') for l in raw.splitlines() if 'T' in l and not l.startswith(',result')]
    t, v = [], []
    for r in rows:
        f = [c for c in r if c]
        if len(f) < 2: continue
        a, b = f[-2], f[-1]
        ts, val = (a, b) if 'T' in a else (b, a)
        t.append(ts); v.append(val)
    s = pd.Series(pd.to_numeric(v, errors='coerce').astype(float), index=pd.to_datetime(t, utc=True, errors='coerce')).dropna()
    return s.groupby(level=0).mean()

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    start = args[0] if args else '2026-09-02T00:00:00Z'
    stop = args[1] if len(args) > 1 else 'now()'
    window = '30min'
    if '--window' in sys.argv: window = sys.argv[sys.argv.index('--window') + 1]
    every = '5m'
    df = pd.DataFrame({k: series(p, start, stop, every) for k, p in PATHS.items()}).dropna(subset=['bx', 'by', 'bz', 'temp'])
    if df.empty:
        print('no vector data in range'); return
    df['temp'] -= 273.15
    df['incl'] = np.degrees(df.incl)
    df['gap'] = np.degrees(((df.hE - df.hF + np.pi) % (2 * np.pi)) - np.pi)
    df['Bh'] = np.hypot(df.bx, df.by)
    df['mag'] = np.sqrt(df.bx ** 2 + df.by ** 2 + df.bz ** 2)
    df['incl_vec'] = np.degrees(np.arctan2(df.bz, df.Bh))
    df = df.tz_convert('America/Detroit')
    pd.set_option('display.width', 200)
    print(f"vector data {df.index[0]:%m-%d %H:%M} -> {df.index[-1]:%m-%d %H:%M} local, n={len(df)} x {every}, "
          f"temp {df.temp.min():.1f}-{df.temp.max():.1f} C")
    print(df[['bx', 'by', 'bz', 'Bh', 'mag', 'incl_vec', 'incl', 'temp', 'gap']].resample(window).mean().round(2).to_string())
    rng = df.temp.max() - df.temp.min()
    if rng < 3:
        print(f"\ntemperature range only {rng:.1f} C - slopes not meaningful yet"); return
    print("\nper-axis linear fit vs temperature:")
    for c in ['bx', 'by', 'bz', 'Bh', 'mag']:
        m, b = np.polyfit(df.temp, df[c], 1)
        print(f"  {c:4s} slope {m:+.3f} uT/C   r={df[c].corr(df.temp):+.2f}   value at 21 C: {m * 21 + b:.2f}")
    m, b = np.polyfit(df.temp, df.gap, 1)
    print(f"  gap  slope {m:+.3f} deg/C  r={df.gap.corr(df.temp):+.2f}")

if __name__ == '__main__':
    main()
