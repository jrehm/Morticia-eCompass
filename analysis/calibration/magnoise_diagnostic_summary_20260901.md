# Mag Noise (`orientation.calibration.magnoise`) — Diagnostic Characterization

**Source:** live InfluxDB `signalk` bucket queries (HALPI2), 2026-08-25 through 2026-09-01,
not a CSV export from a single logged session. No raw data files saved to `data/` for this
pass — queries are reproducible via the Flux snippets below against the same bucket.

## What the field is

`orientation.calibration.magnoise` (`src/main.cpp:584-597`) is the FXOS8700CQ fusion
library's magnetic noise covariance — how noisy/inconsistent raw magnetometer readings are
while the library fits the calibration ellipsoid. Unitless, reported at 0.25 Hz. Firmware
metadata (`main.cpp:592`) flags values **above 0.00056 as unreliable**. Per the fusion
library's own docs, the companion diagnostic is comparing `magfieldmagnitude` (in-use) vs.
`magfieldmagnitudetrial` — that's how to tell a genuine magnetic disturbance from an
ordinary periodic recalibration on stationary data.

## Two distinct drivers found, not one

Naively this metric "varies a lot" over any given day. Lining it up against `navigation.
speedOverGround`, `navigation.attitude.roll`, `electrical.solar.current`, and
`environment.inside.ecompass.temperature` over the week separates two unrelated mechanisms.

### 1. Motion/heel-driven spike — confirmed against the 2026-08-26 race session

Boat was on/around the dock from ~4PM EDT, raced 6-8PM EDT (per owner). `magnoise` sat flat
at baseline (~0.00025) through the first two hours (dockside prep), then tracked heel
dynamics almost to the minute once racing started:

| Time (EDT) | SOG | Roll std-dev (15-min) | `magnoise` |
|---|---|---|---|
| 6:15 PM | rising | 0.017 | still baseline |
| 6:45 PM | 2.0 kn | 0.058 | 0.00092 |
| 7:15 PM | 4.3 kn | 0.064 | 0.00308 |
| 7:30-7:45 PM | 4.3 kn | **0.16 (peak)** | — |
| 8:00 PM | 3.3 kn | 0.035 | **0.00434 (peak, ~17x baseline)** |
| 8:15 PM | ~0 (docked) | 0.009 | 0.00107 |

Roll variance (heel/tacking) and `magnoise` rise and peak together. Physically sensible:
rapid heel changes and tacking genuinely move raw magnetometer readings relative to the
fitted calibration ellipsoid, so the fusion library is correctly reporting real reading
variance from boat motion — not an electrical fault.

**Slow decay tail:** roll variance collapsed back to near-zero within 15 minutes of docking
(8:15 PM), but `magnoise` took **~13 hours** to fully settle back to baseline (didn't reach
quiet levels again until ~10 AM the next morning, 2026-08-27). The metric has a
slow-decaying memory — a disturbance during a sail keeps showing as "elevated" well after
the boat is calm again. Relevant if this is ever used as a live/alerting health check: don't
expect a fast clear after a sail.

### 2. Separate, at-rest daytime pattern — confounded solar/thermal

On non-sailing days (e.g. 2026-08-31 -> 09-01, and to a lesser extent 08-28 -> 08-31),
`magnoise` still climbs during daylight hours even though `navigation.speedOverGround`
confirms the boat never left the dock (stayed at the ~0.05 kn GPS noise floor all day —
moored in its usual current-free home berth). This at-rest rise tracks with:

- **Solar charge current** climbing from ~0 overnight to a ~1.5A midday peak.
- **eCompass internal temperature** climbing from ~24°C overnight to ~40°C by late
  afternoon (16°C swing).

Both are sun-exposure driven and therefore confounded with each other in this data — cannot
yet separate "solar-controller EMI reaching the magnetometer" from "sensor self-heating"
without a targeted comparison (a cloudy/no-charge day, or physically shading the panel or
the eCompass enclosure independently).

**Not yet done — next step to disambiguate:** compare a low-solar-output day (overcast, or
panel manually covered) against a sunny day with similar ambient temperature. If `magnoise`
still climbs with temperature alone (charge current flat/near-zero), that points to sensor
self-heating rather than solar EMI.

## `magfit` (actual calibration quality) is a separate, slower-moving signal

Around the 08-26 race, `magfit` did not jump with the `magnoise` spike, and no
`lastcaleventfitdeltapct` recalibration event fired at all during the observed window. It
instead drifted slowly: ~6.9% -> ~7.9% over the evening of 08-26 into the morning of 08-27,
then dropped to ~2.9-3.0% by mid-morning 08-27. By 2026-09-01 it had drifted back up to a
flat 8% for the entire day (zero cal events that day either).

This reconciles an inconsistency spotted in passing: [CALIBRATION.md](../../../morticia-project/CALIBRATION.md)
(in the morticia-project repo) currently states magfit is "<3%" — that was accurate as of
the morning of 08-27, but the value has since drifted back up to 8% by 09-01. `magfit`
wanders over a period of days independent of the much faster `magnoise` swings above, and is
worth spot-checking periodically rather than treated as a fixed number.

## Reassurance

Across the full week, elevated `magnoise` — whether from sailing dynamics or the daytime
solar/thermal pattern — has not been observed to trigger a bad recalibration event
(`lastcaleventfitdeltapct` stayed 0 throughout both episodes examined here). The signal
looks like it's working as designed, not indicating a hardware fault.

## Reproducing these queries

Token/org/bucket per `signalk-to-influxdb2` plugin config on HALPI2 (`org: marine, bucket:
signalk`). Example — hourly mean of `magnoise` over N days:

```flux
from(bucket:"signalk")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "orientation.calibration.magnoise" and r._field == "value")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> keep(columns: ["_time","_value"])
```

Swap `_measurement` for `navigation.speedOverGround`, `navigation.attitude.roll`,
`electrical.solar.current`, `environment.inside.ecompass.temperature`, or
`orientation.calibration.magfit` / `orientation.calibration.lastcaleventfitdeltapct` to pull
the comparison series used above.

## Open questions / not yet done

- Cloudy-day or shaded-panel comparison to separate solar-EMI vs. self-heating for the
  at-rest daytime pattern.
- Whether the ~13-hour decay constant after a sailing disturbance is consistent across
  multiple sailing sessions, or specific to 08-26's conditions.
- Whether `magfit`'s multi-day drift (6.9% -> 7.9% -> 2.9% -> 8%) has its own pattern worth
  tracking (e.g. does it reset on each reboot/recalibration, or wander continuously).
