# Mag Noise (`orientation.calibration.magnoise`) — Diagnostic Characterization

**Status (2026-09-03):** three phenomena, in priority order:

1. **Magnetometer offset drift with temperature (TCO)** — 0.73 µT/°C along a fixed diagonal
   direction in the chip frame, linear, reversible. Produces up to **100° of eCompass
   heading error at the dock** on a hot afternoon while the fluxgate holds ±1°. Measured
   directly from `Bc` on 2026-09-02; the NXP datasheet specs this part's TCO_MAG at
   ±0.8 µT/°C typical, so **the FXOS8700 is operating within spec** — it is simply not a
   precision compass sensor over a 17 °C swing. See "TCO drift" below.
2. **A non-thermal walk** in the resting baseline, not explained by TCO and not yet
   separated from gear movement aboard. This, not the tempco, decides whether temperature
   compensation is sufficient. See "Non-thermal walk".
3. `magfit` "drift" — float32 artifact, not a signal. See "magfit".
4. **Intermittent AC-like field** of ~4–8 µT at the sensor on an occupancy-shaped schedule,
   source off-boat most likely. Well suppressed by the Kalman filter. Lower priority.

**Corrections to earlier revisions of this document** (git history has the originals; stated
here because the retracted claims were confident and drove work):
- *"Drift is confined to the chip's marked X channel."* **Wrong.** It was back-solved from
  two observables (inclination, heading error) for a three-component vector, closed by
  assuming |Bc| = 48.09 and no vertical component. The direct vector measurement falsifies
  both assumptions: |Bc| moves −0.26 µT/°C and the drift has a z-component. The real
  direction is diagonal, with all three axes contributing.
- *"Thermal term ~0.5 µT/°C, steepening above ~35 °C."* **Wrong twice.** The magnitude is
  0.73 µT/°C, and the apparent steepening was an artifact of viewing a linear offset drift
  through `maginclination`, which is an arctan of the components. Measured directly, the
  drift is linear (r = −0.96) with 0.1–0.4 µT of hysteresis.
- *"On-board magnetics (buck inductor, steel-cored pins) are the leading suspect."*
  Superseded: the load-step test was negative, the SH-ESP32 is 1 m away, and an in-spec
  TCO explains the observation without any external source.

**Source:** live InfluxDB `signalk` bucket on HALPI2, 2026-08-26 → 2026-09-03. Query helper:
`~/bin/fluxq "<flux>"` on `halos` (reads the token from the `signalk-to-influxdb2` plugin
config). Analysis script: `analysis/calibration/magvector_vs_temp.py`.

## TCO drift: the measurement (2026-09-02, full diurnal cycle)

Firmware v1.5.0 publishes the calibrated vector `Bc[x,y,z]` at 1 Hz, so the drift is now
measured rather than inferred. Two dock windows at different headings, bracketing a sail:

| quantity (heading-invariant) | segment A: dock @190°, 26→40 °C | segment B: dock @184°, 30→23 °C |
|---|---|---|
| d\|B\|/dT | −0.264 µT/°C (r = −0.96) | −0.254 µT/°C (r = −0.87) |
| d(incl)/dT | +0.337 °/°C (r = +0.88) | +0.341 °/°C (r = +0.94) |

Both quantities are invariant to the 6° mooring swing between segments, and two independent
windows agree to 4%. Hysteresis on the rising vs. falling ramp is 0.1–0.4 µT — the effect is
reversible, not creep.

**Drift vector.** Relative to the coolest point of segment A, the unit direction in the
chip's *marked* axes holds steady while the magnitude scales with temperature:

| point | T | \|d\| | unit (Xm, Ym, Zm) |
|---|---|---|---|
| A 09:30 | 30.2 °C | 3.03 µT | (−0.76, +0.65, +0.08) |
| A 11:00 | 37.0 °C | 8.02 µT | (−0.75, +0.61, +0.26) |
| A 12:30 | 40.3 °C | 10.47 µT | (−0.74, +0.60, +0.30) |
| A 15:00 | 39.1 °C | 7.15 µT | (−0.76, +0.56, +0.32) |

Total 0.73 µT/°C; per marked axis ≈ (−0.55, +0.44, +0.21) µT/°C. A fixed diagonal direction
with all three channels participating is exactly what three independent per-axis offset
tempcos produce.

**Datasheet check** (FXOS8700CQ Rev. 8, Table 4, magnetometer magnetic characteristics):

| symbol | parameter | typ |
|---|---|---|
| TCO_MAG | zero-flux offset change with temperature | **±0.8 µT/°C** |
| OFF_MAG | zero-flux offset accuracy | ±10 µT |
| TCS_MAG | sensitivity change vs. temperature | ±0.1 %/°C |

Measured 0.73 vs. ±0.8 typical: **the part is in spec.** It is not defective, not permed,
and not obviously stressed. The datasheet also notes (§8.2) that offset is to some extent a
result of stress on the sensor and can change after board mounting or mechanical stress —
so epoxy potting cannot be *excluded* as an additional contributor, but nothing in the data
requires it. `magfit` converging well pre-potting is consistent either way: at a single
temperature a TCO of this size is invisible.

## Non-thermal walk (open, confounded)

Two observations the tempco does not explain:
- Night-baseline inclination moved ~7° across 08-27 → 09-01 at near-constant temperature.
- |B| at matched temperature is ~3 µT higher after the 09-02 sail than before it.

Jeff was aboard 15:00–20:30 on 09-02 (setup, sail, packing), and gear movement changes hard
iron, so neither is clean evidence of sensor walk. **This is the deciding measurement for
the fix:** a two-point temperature calibration removes the TCO but not a random walk. What
is needed is a clean unattended multi-day dock baseline with the vector flowing and nobody
aboard.

## DC drift: eCompass heading vs. fluxgate at the dock

`maginclination` (`SV_9DOF_GBY_KALMAN.fDeltaPl`) is the angle between the Kalman-filtered
geomagnetic vector and gravity — orientation-independent, so mount sag cannot move it; only
a field change or a sensor offset change can. Nights it reads 71–72° (local dip ≈ 70.5°,
i.e. the calibration is right at ~21 °C). Then:

| local time | die temp | incl | B_h′ = 48.1·cos(incl) | eCompass − fluxgate |
|---|---|---|---|---|
| 08-29 03:00 | 21 °C | 70.9° | 15.7 µT | +3° |
| 08-29 13:00 | 34 °C | 79.2° | 9.0 µT | −3.4° |
| 08-30 (overcast, 23 °C all day) | 23 °C | 71 → 75° | 15.7 → 12.4 µT | +4 → −2° |
| 09-01 03:00 | 25 °C | 79.2° | 9.0 µT | −9.9° |
| 09-01 14:00 | 39 °C | 84.9° | 4.3 µT | **−99.6°** |

Fluxgate (`sensors.fluxgate.headingMagnetic`) range for the whole week: 3.9°. eCompass
(`sensors.ecompass.headingMagnetic`) range: 107.5°. Inclination correlates with die
temperature at r = 0.84–0.98 within a day; high-pass (cloud-scale) residuals show no
tracking of solar or battery current — so the daily term is thermal, not current.

With |B| held at 48.1 by the calibration, inclination gives the remaining horizontal field
and the heading error gives its rotation, so the disturbance vector is solvable
(along-B_h / across-B_h, µT): 08-29 13:00 → −6.6 / +0.5; 09-01 03:00 → −6.7 / +1.5;
09-01 14:00 → −16.3 / +4.2. The vector is almost purely anti-parallel to the horizontal
geomagnetic field. The boat sits at 190°, so B_h points toward the stern and the disturbance
points **toward the bow** — a fixed sensor/boat-frame axis. That fits a sensor-axis offset
drift or a fixed nearby magnet, and does not fit an external or moving source.

Two components, both later superseded by the direct vector measurement (see "TCO drift"):
- **thermal:** estimated here as ~0.5 µT/°C with apparent steepening above ~35 °C. Direct
  measurement gives 0.73 µT/°C, linear; the steepening was an arctan artifact of viewing
  offset drift through inclination.
- **creep:** night baseline moved ~6.7 µT in three days, including through the flat-23 °C
  overcast day — not thermal. Still open; see "Non-thermal walk".

Why `magnoise` missed it: a horizontal disturbance projects onto the 71°-dipped field by
only cos 71° ≈ 0.33, so |Bc| moves ~2 µT (just above the floor) while inclination swings
7°. Inclination is the sensitive DC detector; magnoise is a magnitude-only, single-sample
metric.

Consequences:
- The 46° HDGmE/HDGmF gap under sail and session-to-session inconsistency in the deviation
  work may be substantially this rather than mounting or soft-iron. Deviation fits need
  `environment.inside.ecompass.temperature` as a covariate and the calibration's reference
  temperature recorded.
- The eCompass is not usable as a heading source unless this is fixed; the fluxgate switch
  on 2026-08-19 was the right call.

Separating sensor offset from a nearby magnet needs physical tests (see "Next steps").

**Mounting facts (Jeff, 2026-09-02):** the magnetometer is an NXP **BRKT-STBC-AGM01**
breakout (FXOS8700 + FXAS21002), potted in epoxy, taped component-side up to a CF cross
member immediately aft of the daggerboard trunk. J3 row runs fore-aft; marked +Y → port,
so marked +X → stern, +Z → up. I2C/power soldered to the J4-side pads, twisted pairs, led
away along +Y (port) across the cross member, down the hull side, to the SH-ESP32 **~1 m
below**. Hull entirely CF; the only metal nearby is the stainless mast step 20–25 cm
directly above (on the Z axis).

**Published vector frame:** (x, y, z)_published = (−Y, +X, −Z)_marked = (starboard,
astern, down). Verified from the dock field (see README).

**Accelerometer is clean:** hourly mean roll/pitch vs. die temperature: slope 0.002 °/°C,
r ≈ 0 (inclination: 0.62 °/°C, r = 0.80). The only roll/pitch step all week is 08-29 08:00
(0.3° trim change, someone stepping aboard) and inclination did not respond. So the drift
is entirely on the magnetometer side.

**Disturbance axis (superseded by the direct measurement above — retained because the
geometry reasoning is still valid).** The back-solve suggested a single bow-axis vector;
the vector data shows a fixed *diagonal* direction, (−0.75, +0.60, +0.29) in marked chip
axes. What the geometry does establish is that no external source can account for it: the
SH-ESP32 (inductor, pins, shield can) is 1 m away, the I2C harness leaves perpendicular
along +Y carrying milliamps, the mast step is on Z, and the AGM01 itself carries only the
FXAS21002 gyro (no magnetic material) and passives. Combined with the negative load-step
test and an in-spec TCO_MAG of ±0.8 µT/°C, the drift is **internal to the FXOS8700
magnetometer**. Driver check: magnetic sensor reset is enabled every cycle
(`M_CTRL_REG2 m_rst_cnt = 00`), so the chip's own degauss is already active and does not
remove it — as expected, since degauss cancels element hysteresis, not offset tempco.

## What `magnoise` actually is

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

**DC drift (priority 1):**

1. **Warm the board alone (dock, any day):** hair dryer on the potted PCB for a few
   minutes while the boat stays cool; watch `maginclination` and
   `sensors.ecompass.headingMagnetic` vs. fluxgate. Expected to move (board-local); if it
   doesn't, the source is off-board and the mast step / RF25 go back on the list.
2. **Load-step test (separates inductor from sensor tempco) — DONE 2026-09-02 08:20 EDT,
   negative.** Three 60-s cycles of 4-parallel `curl` against `http://192.168.8.214/api/info`
   from HALPI2 (`/tmp/loadstep.sh`). Load confirmed: free heap −24 kB, Signal K delivery
   dropped from ~40 to 7–20 samples/min. Field: hammer − rest = bx +0.09, by −0.20,
   bz +0.48 µT against a 1-Hz single-sample noise of 0.84 µT rms and ~0.25 µT standard
   error — no step above noise. A ~30–50 mA (inferred, not measured) current step moved the
   field < 0.5 µT on every axis, so the buck inductor's DC-biased field is not the 6–16 µT
   thermal source. Option 1 (12 V → USB power swap) would close the "current step not
   measured" gap if wanted; the FXOS8700's own offset tempco is now the leading explanation.
3. **Publish the calibrated field vector** `Bc[x,y,z]` — **DONE, firmware v1.5.0
   (2026-09-02 07:06)**: `orientation.calibration.magfieldvector.{x,y,z}` at 1 Hz, flowing
   to InfluxDB. This is what made the direct TCO measurement possible. Analysis script: `analysis/calibration/magvector_vs_temp.py` (per-axis dB/dT from
   live InfluxDB; needs > 3 °C of range).
4. **Deviation analysis:** add `environment.inside.ecompass.temperature` as a covariate in
   the sailing-deviation fits and check the 08-12 / 08-26 sessions for temperature range;
   record the calibration's reference temperature in `CALIBRATION.md`.
5. **Clean unattended dock baseline (do this first — it decides the fix).** Several days
   with the vector flowing and nobody aboard. Compare `Bc` at matched temperature across
   days. If it repeats, the TCO is the whole story and item 6 suffices. If it walks, only
   item 7 fixes it.
6. **Two-point temperature calibration** — NXP's own recommendation for this part: collect
   per-axis magnetic data at two temperatures along with the internal temperature reading,
   then correct in firmware. We already log die temperature and `Bc`, so one diurnal cycle
   is enough to fit it. No hardware change. Expected to remove most of the 0.73 µT/°C.
7. **Replace the magnetometer** if the baseline walks (or if item 6 leaves too much
   residual). Choose a part that removes offset by construction rather than by fitting:
   **MMC5983MA / MMC5603** (AMR with SET/RESET each measurement — element offset and its
   tempco cancel) or **RM3100** (PNI magneto-inductive, no offset by principle). Either
   needs a driver in `OrientationSensorFusion-ESP`'s sensor layer (`driver_fxos8700.c` is
   the template; the FXOS8700 accel and FXAS21002 gyro can stay) and a fresh calibration.
   Note the FXOS8700CQ is EOL and not recommended for new designs, so this is coming
   eventually regardless.
8. **Bare-board A/B (optional, bounded value).** One un-potted AGM01 remains. Wiring it up
   in the same place and orientation tests whether epoxy stress adds anything on top of the
   intrinsic TCO. Expected result is "same drift" — 0.73 is already in spec — so this
   converts a hypothesis into a measurement rather than being likely to change the plan.
   Fingerprint to compare: d|B|/dT = −0.26 µT/°C, d(incl)/dT = +0.34 °/°C. No recalibration
   needed: each chip has its own hard-iron offset so heading/inclination will read wrong,
   but d`Bc`/dT is calibration-independent.

**AC noise (priority 4):**

9. **Firmware instrument:** per-axis 1-s standard deviation of `Bc` at 1 Hz, plus an
   on-demand ~2-s raw burst at full ODR via the existing port-80 API — axis gives the
   source direction, burst gives the frequency (60 Hz vs. a switcher).
10. **Field checks during an elevated period:** unplug Morticia's shore cord for a minute;
   note which neighboring boats are occupied / running A/C.
11. **Mitigation regardless of source:** read the magnetometer at the 200 Hz hybrid ODR and
   average 5 samples per 40 Hz fusion cycle (~4× attenuation of 60 Hz). Do this only after
   at least one elevated period has been captured with item 9.
12. Re-run the sample-distribution check after any change; at-floor fraction and histogram
   mode are the two numbers to watch.
