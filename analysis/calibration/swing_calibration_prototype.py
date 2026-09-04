#!/usr/bin/env python3
"""
swing_calibration_prototype.py — 2D (yaw-swing) hard-iron calibration for the eCompass.

WHY THIS EXISTS
---------------
The fusion library's auto-calibration bins magnetometer samples by the *direction* of the
field vector in the sensor frame (14x28 = 392 bins over the sphere) and refuses to run a
solver below 110 populated bins (330 for the 10-element solver it currently uses). At Lake
St. Clair the dip is ~71 deg, so the field sits ~19 deg off the sensor's down axis; yawing
the boat sweeps a narrow cone rather than tumbling the sensor. Measured on the 2026-09-02
sail: the field direction stayed within 5-35 deg of +z, visiting ~25 distinct direction
bins. The onboard auto-calibration therefore CANNOT run on the boat, and nothing tracks the
~4 uT/day hard-iron walk.

This script prototypes the alternative: the classic marine compass swing. We cannot solve
the full 3D ellipsoid, but heading only needs the *horizontal* projection, and the boat
rotates freely in yaw. Fitting a circle to the tilt-compensated horizontal components over a
yaw sweep recovers the horizontal hard-iron offset in 3 well-conditioned parameters.

Vertical offset (Vz) is left alone: it is unobservable from yaw-only motion and does not
affect heading once the vector is tilt-compensated.

FRAMES
------
Published Bc is (x=starboard, y=astern, z=down)  [see README "Local Library Patches"].
Body frame used here is the usual (forward, right, down) = (-by, bx, bz).
Tilt compensation uses navigation.attitude.roll/pitch, then
    heading = atan2(-Yh, Xh).
Sign conventions are verified empirically against the fluxgate; the script reports the
residual so a convention error shows up as a large scatter rather than passing silently.

USAGE
-----
    python swing_calibration_prototype.py [csv_dir]
Expects r_{bx,by,bz,roll,pitch,hF,temp}.csv (time,value) as pulled from InfluxDB.
"""
import sys
import numpy as np
import pandas as pd

CSV_DIR = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hourly'
# TCO coefficients in the PUBLISHED frame, uT/degC, from the 2026-09-03 two-excursion fit
TCO = np.array([-0.478, -0.540, -0.240])
T_REF = 23.0


def load(name):
    s = pd.read_csv(f'{CSV_DIR}/r_{name}.csv', header=None, names=['a', 'b'], dtype=str)
    isd = s.a.str.contains('T', na=False)
    t = np.where(isd, s.a, s.b)
    v = np.where(isd, s.b, s.a)
    out = pd.DataFrame({'t': pd.to_datetime(t, utc=True, errors='coerce'),
                        'v': pd.to_numeric(v, errors='coerce')}).dropna()
    return out.set_index('t').v.resample('1s').mean()


def circle_fit(x, y):
    """Algebraic (Kasa) circle fit. Returns (cx, cy, R)."""
    A = np.column_stack([x, y, np.ones(len(x))])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    R = np.sqrt(sol[2] + cx ** 2 + cy ** 2)
    return cx, cy, R


def tilt_compensate(bf, br, bd, roll, pitch):
    """Standard tilt-compensated horizontal components."""
    sr, cr = np.sin(roll), np.cos(roll)
    sp, cp = np.sin(pitch), np.cos(pitch)
    Xh = bf * cp + br * sp * sr + bd * sp * cr
    Yh = br * cr - bd * sr
    return Xh, Yh


def circ_stats(deg):
    """Circular mean and std of an angle array in degrees."""
    r = np.radians(deg)
    C, S = np.cos(r).mean(), np.sin(r).mean()
    mean = np.degrees(np.arctan2(S, C)) % 360
    Rbar = np.hypot(C, S)
    std = np.degrees(np.sqrt(-2 * np.log(max(Rbar, 1e-12))))
    return mean, std


def wrap180(d):
    return (d + 180) % 360 - 180


def main():
    cols = ['bx', 'by', 'bz', 'roll', 'pitch', 'hF', 'temp']
    D = pd.DataFrame({c: load(c) for c in cols}).interpolate().dropna()
    D = D.tz_convert('America/Detroit')
    D['temp'] -= 273.15
    hF = np.degrees(D.hF) % 360

    print(f"window {D.index[0]:%m-%d %H:%M} -> {D.index[-1]:%H:%M} local, n={len(D)} s")
    yaw_span = circ_stats(hF)[1]
    print(f"fluxgate heading: circular sd {yaw_span:.0f} deg, "
          f"5th-95th pct {np.percentile(hF,5):.0f}-{np.percentile(hF,95):.0f}")
    print(f"roll {np.degrees(D.roll).min():+.1f}..{np.degrees(D.roll).max():+.1f} deg, "
          f"temp {D.temp.min():.1f}-{D.temp.max():.1f} C")

    for label, tc in [('raw Bc', False), ('Bc with TCO correction', True)]:
        B = D[['bx', 'by', 'bz']].values.copy()
        if tc:
            B = B - TCO * (D.temp.values[:, None] - T_REF)
        bf, br, bd = -B[:, 1], B[:, 0], B[:, 2]
        Xh, Yh = tilt_compensate(bf, br, bd, D.roll.values, D.pitch.values)

        cx, cy, R = circle_fit(Xh, Yh)
        # residual of the circle fit itself: how well does a circle describe the swing?
        rad = np.hypot(Xh - cx, Yh - cy)

        hdg_before = np.degrees(np.arctan2(-Yh, Xh)) % 360
        hdg_after = np.degrees(np.arctan2(-(Yh - cy), Xh - cx)) % 360

        print(f"\n=== {label}")
        print(f"  circle fit: centre ({cx:+.2f}, {cy:+.2f}) uT  |offset| {np.hypot(cx,cy):.2f} uT"
              f"   R = {R:.2f} uT   radial residual sd {rad.std():.2f} uT")
        for nm, h in [('uncorrected', hdg_before), ('swing-corrected', hdg_after)]:
            d = wrap180(h - hF.values)
            m, s = circ_stats(d)
            print(f"    {nm:16s} vs fluxgate: mean offset {wrap180(m):+7.1f} deg, "
                  f"scatter (1 sd) {s:5.1f} deg")

    print("\nNotes:")
    print(" - A constant mean offset is expected and harmless: it is the mounting/deviation")
    print("   constant, absorbed by the existing mounting-offset ConfigItem.")
    print(" - The number that matters is the SCATTER. It measures how well a single hard-iron")
    print("   solution explains heading across the whole yaw sweep.")
    print(" - R should land near the true horizontal field (~16 uT here). A badly wrong R")
    print("   means the arc was too short to constrain the circle.")


if __name__ == '__main__':
    main()
