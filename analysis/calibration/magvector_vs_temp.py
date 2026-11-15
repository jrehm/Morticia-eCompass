#!/usr/bin/env python3
"""
magvector_vs_temp.py — DC magnetometer drift vs. die temperature from live QuestDB.

Pulls orientation.calibration.magfieldvector.{x,y,z}, die temperature, Kalman inclination,
and eCompass/fluxgate headings from the QuestDB `signalk` table on HALPI2 (via analysis/skdata.py: ssh, or QUESTDB_URL),
then prints a half-hourly table and per-axis slopes dB/dT (uT/C).

Usage:
  python magvector_vs_temp.py                  # last 7 days
  python magvector_vs_temp.py 2026-09-03T00:00:00Z [stop_iso] [--window 30min]

QuestDB history starts 2026-11-14; earlier ranges need the Influx-era data (not ported).

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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skdata

PATHS = {
    'bx': 'orientation.calibration.magfieldvector.x',
    'by': 'orientation.calibration.magfieldvector.y',
    'bz': 'orientation.calibration.magfieldvector.z',
    'temp': 'environment.inside.ecompass.temperature',
    'incl': 'orientation.calibration.maginclination',
    'hE': 'sensors.ecompass.headingMagnetic',
    'hF': 'sensors.fluxgate.headingMagnetic',
}

def main():
    argv = sys.argv[1:]
    window = '30min'
    if '--window' in argv:
        i = argv.index('--window'); window = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith('--')]
    start = args[0] if args else (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    stop = args[1] if len(args) > 1 else 'now'
    every = '5m'
    df = skdata.fetch_frame(PATHS, start, stop, every).dropna(subset=['bx', 'by', 'bz', 'temp'])
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
