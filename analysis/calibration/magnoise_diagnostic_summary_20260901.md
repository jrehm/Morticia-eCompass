# Mag Noise (`orientation.calibration.magnoise`) — Diagnostic Characterization

**Status (2026-09-01):** the disturbance is characterized (an intermittent AC-like magnetic
field of ~4–8 µT amplitude at the sensor, on a schedule that tracks nothing onboard) but
its source is not yet identified. Next step is a firmware instrument, not more InfluxDB
mining — see "Next steps".

**Source:** live InfluxDB `signalk` bucket on HALPI2, 2026-08-26 → 2026-09-01 (dock, no
sailing; SOG < 0.3 kn every hour). Query helper: `~/bin/fluxq "<flux>"` on `halos` (reads
the token from the `signalk-to-influxdb2` plugin config). Hourly pivots were done on the Mac
in the calibration `.venv`; no CSVs saved.

## What the field actually is

`magnoise` = `SV_9DOF_GBY_KALMAN.fQv6x1[3]`, computed in
`OrientationSensorFusion-ESP/src/fusion/fusion.c` (lines ~1106–1110, 1220):

```
ftmp     = |Bc| - B            // one calibrated magnetometer sample vs. stored field magnitude
fQvBQd   = max(3·ftmp², 5.0)   // 5 µT² floor (FQVB_9DOF_GBY_KALMAN)
magnoise = fQvBQd / (12·B²)    // + ~3e-6 gyro term, negligible
```

So **`magnoise = (ΔB/B)²/4`**, i.e. **|ΔB| = 2·B·√magnoise** (B = 48.09 µT here):

| magnoise | ΔB | note |
|---|---|---|
| 0.000183 | < 1.3 µT | floor: 5/(12·48.09²), exactly the observed baseline |
| 0.00056 | 2.3 µT | firmware "unreliable" threshold |
| 0.0018 | 4.1 µT | |
| 0.0043 | 6.3 µT | 08-26 race peak |
| 0.008 | 8.6 µT | |

Properties that matter for interpretation:

- **Single sample, no memory.** `Bc` is one raw 6-byte register read per 40 Hz fusion
  cycle (`kLoopsPerMagRead = 1`, FXOS8700 has no magnetometer FIFO). The 4-s Signal K
  value is a snapshot of the latest cycle. Nothing is filtered or accumulated, so the
  metric cannot "decay" — an elevated value means the field was off at that instant.
- **It is a magnitude error, not a variance.** A static iron object or a DC current loop
  gives a *steady* elevated value; an AC field gives a random value on every sample.
- The Kalman filter uses it adaptively (higher `magnoise` → less weight on the
  magnetometer), so heading is partly protected, but heading jitter still rises.

## What the data shows

**1. Sample-level structure: uncorrelated, continuous, mode away from zero.**
Consecutive 4-s samples are independent (floor, 3.5 µT, floor, 1 µT, 4 µT ...). Every
20-min window all week, day or night, contains samples at the floor *and* samples at
3–5 µT; the hourly mean rises only because the upper tail thickens. Distribution of
individual samples:

| window | at floor | p50 | p90 | p99 | max |
|---|---|---|---|---|---|
| quiet night (09-01 00–04 EDT) | 73% | 1.3 | 1.9 | 2.9 | 5.1 µT |
| elevated night (08-29 02–06 EDT) | 11% | 2.8 | 4.2 | 5.4 | 7.4 µT |
| elevated day (09-01 12–14 EDT) | 1% | 3.9 | 5.5 | 6.7 | 8.3 µT |

Zero-mean Gaussian noise would peak at zero; I2C bit corruption would be sparse and
discrete. A **periodic (AC) field sampled at random phase** piles up near its amplitude
(|A·sin φ|), which is what the elevated histograms look like. Working model: an AC magnetic
field of ~4–8 µT amplitude at the sensor, switching on/off on a schedule.

**2. Schedule (hourly mean, expressed as ΔB µT; floor ≈ 1.5 after averaging):**

| local day | 0–9 AM | 10 AM–8 PM | 9–11 PM |
|---|---|---|---|
| 08-27 (Thu) | 2.9–3.2 | 1.5–1.9 | 1.7–2.1 |
| 08-28 (Fri) | 2.3–3.6 | 1.5–2.2 | 2.2–2.7 |
| 08-29 (Sat) | 2.6–3.1 | 1.6–2.9 | 1.9–2.8 |
| 08-30 (Sun) | 2.5–3.1 | 1.7–2.4 | 1.9–2.1 |
| 08-31 (Mon) | 1.6–1.7 | 1.5–2.6 (bump 1–5 PM) | 1.5 |
| 09-01 (Tue) | 1.5 | 2.0 → **4.4** at 2 PM | — |

Nights elevated Thu→Sun (rising from ~8 PM, peak 2–5 AM, gone by ~10 AM); regime ends over
~20 min around **midnight Sun 08-30/31**; then daytime elevation on Mon/Tue. The post-race
"13-hour decay" in the earlier draft was night #1 of this pattern, not a decay.

**3. Ruled out with data (hourly, dock days):**

| candidate | evidence |
|---|---|
| heel / motion | roll σ ≈ 0.03° all week; no correlation |
| wind / mast shake | 13 kn at 08-31 00–03 was quiet; 3 kn at 08-30 03–05 was elevated |
| mast rotation | `navigation.mast.rotation` σ = 0 except when moved (08-29 noon) |
| solar current | sunnier days (08-27..29, 20–23 W) quieter than 09-01 (19 W) |
| shore charger | elevated nights with charger off (08-29/30) and on (08-27/28); 08-31 charge cycle quiet; ΔB *fell* during 08-29 06–10 charge |
| any onboard DC load | battery current flat −1.23 A ± 0.05 A through an entire 8 PM → 3 AM ramp |
| sensor temperature | 08-31 rise with die temp flat; hotter days quieter |
| N2K bus / fluxgate drive | fluxgate, rudder, mast sensor logged 24/7 all week |
| eCompass reboot / recal | one reboot (08-27 06:00 EDT), no calibration adopted all week (B = 48.092, solver = 10 constant) |
| Morticia's 120 V shore cord | draped on outside stbd cabin side, ~0.8–1 m from sensor; carries only the charger's ~3 A → nT-scale for a paired cord, ≤0.6 µT even single-conductor; and see charger row |
| solar/geomagnetic activity | Sq ~20–30 nT, storms ≤1 µT — orders of magnitude too small |

Note: masthead wind data stops 08-31 08:00 EDT — almost certainly the solar-charged wireless
sensor's battery after the overcast 08-30 (solar flat ~0 W that day). Unrelated.

**4. Interpretation.** An AC source close enough to induce several µT, whose on/off
schedule follows human occupancy (weekend nights, then a hot weekday afternoon) rather than
anything on Morticia — most plausibly a **neighboring boat's AC loads (A/C, heater,
charger, inverter) or dock pedestal wiring**. 5 µT from a paired cable needs the conductors
within ~1–2 m, so the eCompass's position relative to the adjacent slip and the pedestal is
the relevant geometry. Not provable from onboard data.

## `magfit` is not drifting — it is float32 absorption

`magfit` = `MagCal.fFitErrorpc`, which only changes when a calibration is *adopted* (none
was, all week). Between adoptions the library ages it by `+1/(40·86400)` = 2.9e-7 per
fusion cycle (`magnetic.c` ~line 476, `FITERRORAGINGSECS = 86400`), nominally +1 %/day.
Observed: +0.82 %/day while 2.86 → 3.99, +1.65 %/day while 4.05 → 7.97, then **stuck at
8.000 from 08-31 02:00 EDT**. That is exactly float32 rounding: spacing is 2.4e-7 near 3
(increment rounds down), 4.8e-7 near 4–8 (rounds up), 9.5e-7 at 8 (increment < half-spacing
→ rounds to zero). Consequences:

- `magfit` values are not a calibration-quality signal between adoption events. Only jumps
  (08-27 06:00 reboot: 7.9 → 2.86, the stored calibration's real fit error) mean anything.
- Aging is *permanently dead* once fFitErrorpc ≥ 8.0, so a trial calibration is accepted
  only if `ftrFitErrorpc ≤ 8.0` (or ≤ 3.5 % with a higher-order solver). Mildly
  protective for us; an upstream library bug worth reporting.
- `lastcaleventfitdeltapct` staying 0 all week is correct — nothing was adopted.

## Next steps

1. **Firmware instrument (decisive, cheap):** publish per-axis 1-s standard deviation of
   `Bc` (x, y, z) at 1 Hz, plus an on-demand ~2-s raw burst at full ODR via the existing
   port-80 API. The axis with the variance gives the direction to the source (vertical vs.
   horizontal, fore-aft vs. athwartships); the burst gives the frequency (60 Hz vs. a
   switcher) and confirms AC vs. impulsive. One elevated hour settles source class and
   bearing.
2. **Field checks during an elevated period:** unplug Morticia's shore cord for a minute
   (own-boat AC side in/out); note which neighboring boats are occupied / running A/C.
3. **Mitigation regardless of source:** read the magnetometer at the 200 Hz hybrid ODR and
   average 5 samples per 40 Hz fusion cycle (~4× attenuation of 60 Hz, ~1.5 cycles per
   window). Currently every fusion cycle trusts one raw sample.
4. Re-run the sample-distribution check after any change; the at-floor fraction and the
   histogram mode are the two numbers to watch.
