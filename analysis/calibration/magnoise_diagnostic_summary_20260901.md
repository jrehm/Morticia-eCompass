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

### 2. Separate, at-rest daytime pattern — driver still unidentified (solar current and temperature both ruled out)

On non-sailing days (e.g. 2026-08-31 -> 09-01, and to a lesser extent 08-28 -> 08-31),
`magnoise` still climbs during daylight hours even though `navigation.speedOverGround`
confirms the boat never left the dock (stayed at the ~0.05 kn GPS noise floor all day —
moored in its usual current-free home berth).

**Initial hypothesis (disconfirmed):** the 24-hour hourly-mean view showed `magnoise`
tracking `electrical.solar.current` (~0 overnight to ~1.5A midday peak) and
`environment.inside.ecompass.temperature` (~24°C overnight to ~40°C by late afternoon).
Both looked plausible and were confounded with each other (both sun-driven), so two
follow-up tests were run at finer resolution to separate them:

**Test A — last-hour, fine resolution (2026-09-01, ~5-6PM EDT):** `magnoise` climbed
smoothly from 0.00177 to 0.00326 (~1.8x) over one hour, while `electrical.solar.power` was
flat-to-declining (5.5W -> 4.9W -> 5.8W -> 3.9W, no upward trend) and
`environment.inside.ecompass.temperature` was essentially flat (~311.5K the whole hour).
Roll variance stayed near-zero, confirming the boat was still moored. Neither candidate
tracks the rise at this resolution.

**Test B — clean overnight charger cycle, no sailing, no sun (2026-08-30 22:00 UTC ->
2026-08-31 09:00 UTC):** the battery charger switched on at ~2AM EDT, `electrical.batteries.
house.current` jumping from -1.2A (discharging) to +2.9A (charging) — a larger swing than
the daytime solar current ever produces. `magnoise` did not respond at all: 0.00044 just
before the jump, 0.00028-0.00035 during and after 3+ hours of steady charging. Confirmed by
the boat owner independently: the charger also runs overnight with no associated `magnoise`
change, which is what this test shows directly.

**Conclusion: solar/charge current and sensor self-heating (as measured by
`environment.inside.ecompass.temperature`) are both ruled out as drivers of the at-rest
daytime pattern.** The original correlation in the 24-hour hourly-mean view was most likely
a coincidental diurnal-shape overlap (both curves happen to rise-then-fall across a day)
rather than a causal link. The actual driver remains unidentified — see Open Questions.

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

Across the full week, elevated `magnoise` — whether from sailing dynamics or the unexplained
at-rest daytime pattern — has not been observed to trigger a bad recalibration event
(`lastcaleventfitdeltapct` stayed 0 throughout both episodes examined here). Whatever is
driving the daytime pattern, it hasn't been shown to degrade the calibration in use.

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

- **What actually drives the at-rest daytime pattern.** Solar/charge current and eCompass
  self-heating are both ruled out (see Test A/B above). Other candidates worth checking
  before speculating further: something else diurnal near the sensor that isn't captured by
  current/temperature (marina RF/other vessels' electronics active during the day, a
  scheduled process on the Pi itself, WiFi/AIS/other onboard transmitters with a daily
  pattern), or an artifact internal to the fusion library's noise-covariance calculation
  unrelated to the physical environment. No evidence for any of these yet.
- Whether the ~13-hour decay constant after a sailing disturbance is consistent across
  multiple sailing sessions, or specific to 08-26's conditions.
- Whether `magfit`'s multi-day drift (6.9% -> 7.9% -> 2.9% -> 8%) has its own pattern worth
  tracking (e.g. does it reset on each reboot/recalibration, or wander continuously).
