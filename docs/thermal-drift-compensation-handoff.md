# Morticia eCompass — Thermal Drift Compensation Handoff

> Written from a data-driven analysis in `analysis/thermal-drift/`
> (2026-07-13), against firmware `main.cpp` as of commit `59627c5` (v1.3.1
> line — see `CHANGELOG.md`).
>
> **2026-07-13 update:** implemented in `main.cpp` (targeting v1.3.2, not yet
> flashed). Compiles clean (`pio run -e shesp32`). A sign error (`+` instead
> of `-` in the correction formula) was caught by numerically cross-checking
> the compiled formula against `analysis/thermal-drift/validate.py` before
> FOTA — see the Formula section below. Still pending before flashing: a
> live serial-monitor smoke test.
>
> **2026-07-29 update — deployed coefficient invalidated by sensor relocation.**
> Analysis of a full 9-day dockside window (`analysis/thermal-drift/recent_correlation_summary.md`)
> found the deployed `-1.0211 deg/C` was substantially overcorrecting: the
> post-correction residual still showed a strong (`r^2=0.67`) temperature
> relationship of the *opposite* sign, and backing out the applied correction
> put the sensor's actual current thermal sensitivity at only `-0.164 deg/C`
> (`r^2=0.07`) — about 6x weaker than the original fit, with wind (`~-0.20
> deg/kn`, stable across both the 3-day and 9-day windows) a more reliable
> predictor than temperature at that point.
>
> Shortly after, the compass sensor was physically relocated — a second
> BRKT-STBC-AGM01 mounted ~3ft from the SensESP enclosure/battery via a
> twisted-pair I2C extension, out of the SensESP PCB's near-field entirely
> (see ADR-013 in morticia-project `DECISIONS.md`). `magfit`/`magfittrial`
> dropped from stuck-at-12% to under 3% immediately, consistent with the
> original diagnosis that PCB-proximity noise (not distance-scaled onboard
> DC wiring) was the dominant disturbance. This also means the `-1.0211
> deg/C` fit — and the `-0.164 deg/C` re-check above — were both measured
> against a sensor thermal environment (self-heating from an adjacent
> ESP32/regulator/radio) that no longer exists at the new location. Treat
> the deployed coefficient as invalid, not just stale.
>
> **Action taken:** `slope_deg_per_c` reset to `0` via `POST
> /api/thermal/config` on 2026-07-29. Plan: collect several days of dockside
> data at the new sensor location, rerun the `analysis/thermal-drift/`
> pipeline against it, and only then decide whether a nonzero coefficient is
> warranted — the lower noise floor at the new location should also make
> this fit meaningfully cleaner (higher r^2, less wind confound) than either
> prior attempt, if a real thermal effect is present at all.
>
> **2026-08-01 update — new coefficient deployed at the new location.** Two
> days of dockside data (7/30 13:00 UTC -> 8/1, 32,884 samples, temp 23-37C)
> gave `slope = -0.1695 deg/C, r^2 = 0.39` — a real, moderately strong
> relationship (vs. r^2=0.07 for the 9-day re-check that had to back the old
> correction out of PCB-noise-contaminated data). Wind-controlled regression
> barely moved the temp coefficient despite high temp/wind collinearity
> (r=0.75), consistent with the boat being dockside with only line-stretch
> movement during this window — a cleaner test than the prior windows. This
> also converges closely with the -0.164 deg/C estimate from the old
> location's 9-day re-check, which is a good independent cross-check that
> both that number and the `slope_deg_per_c=0` reset (see above) actually
> took effect. Full writeup: `analysis/thermal-drift/newloc_correlation_summary.md`.
>
> Deployed `slope_deg_per_c=-0.17, tref_c=30.4` via `POST /api/thermal/config`,
> 2026-08-01 07:00 local. Treated as provisional, not final — r^2=0.39 still
> leaves the majority of heading variance unexplained by temperature alone,
> and 2 days dockside is a thin sample vs. the original 5-day fit. Plan to
> monitor Grafana over the next several days and an actual sail before
> treating this as settled.
>
> **2026-08-01 update — headingCompass/headingMagnetic rate fixed, 0.25Hz -> 5Hz.**
> The thermal-compensation `Zip` added in v1.3.2 only emits once both its
> inputs (heading, temperature) have produced a fresh value since the last
> emission, so the corrected heading was capped at temperature's reporting
> rate (`CALIBRATION_REPORTING_INTERVAL_MS`, 4000ms/0.25Hz) even though raw
> fusion heading is ready at 10Hz — an unintended side effect of reusing that
> constant, not a deliberate design choice, and it was causing skipped/gapped
> values in InfluxDB. Fixed in v1.3.3 (targeting; not yet flashed) by giving
> temperature a second, dedicated, faster producer (`temperature_fast`,
> `THERMAL_ZIP_INTERVAL_MS`=200ms/5Hz) feeding only the Zip, decoupled from
> the diagnostic-reporting-rate `temperature` producer that still feeds
> `environment.inside.ecompass.temperature`/magfit/magsolver at the original
> 0.25Hz (harmless — temperature's thermal time constant is minutes, not
> milliseconds). `Zip`'s `max_age` reduced from 10000ms to 1000ms to match
> (same ~5x margin ratio as before). Compiles clean (`pio run -e shesp32`).
> Still pending: OTA flash and a live check that `headingCompass` actually
> reports at ~5Hz post-flash.

## Purpose

Quantify and design a fix for temperature-driven drift in `navigation.headingCompass`
/ `navigation.headingMagnetic`. `environment.inside.ecompass.temperature` was added in
v1.2.2 specifically as diagnostic groundwork for this — "no compensation logic yet;
intended to correlate against heading/attitude drift to characterize thermal drift
magnitude before deciding on a fix." This document is that decision.

---

## Evidence

Full analysis, data, and plots: `analysis/thermal-drift/` (`correlation_summary.md`,
`data/clean_merged.csv`, `plots/*.png`).

**Data:** InfluxDB `signalk` bucket, 2026-07-08T00:00 → 2026-07-13T06:00. The boat was
tied off at the dock the entire window (`speedOverGround` ≈ 0 throughout, confirmed),
so `navigation.headingCompass` should have been constant except for small wind/wake wobble.
One known WiFi-reconnect artifact (a 116° spike-and-recover at 2026-07-08 11:49–11:53,
matching the non-thermal signature already documented in `morticia-project/MODIFICATIONS.md`)
was detected and excluded before analysis.

**Method:** heading residual = `headingCompass − median(headingCompass)` over the whole
window (a single constant baseline — the boat's true resting orientation didn't change).
Residual and temperature were both smoothed with a 20-minute rolling mean purely to
suppress wind-gust wobble for the *correlation analysis*; the underlying relationship
itself has no lag, so the deployed correction (below) uses raw, unsmoothed values.

**Result — real, strong, linear, no lag, no hysteresis:**

| Metric | Value |
|---|---|
| Slope | **−1.021 °/°C** (95% CI tight; r² = 0.767, p ≈ 0) |
| Wind-controlled slope | −0.989 °/°C (R² 0.767 → 0.772 adding wind — wind is not a confound) |
| Best cross-correlation lag | 0 min (no thermal-mass lag detected) |
| Hysteresis (rising vs. falling slope) | −1.013 vs. −1.040 °/°C — 0.027 °/°C difference, negligible |
| Observed temp range | 26.6 – 35.5 °C |
| Resulting heading error | up to **~9° peak-to-peak** over that range |

The time-series overlay (`plots/timeseries_overlay.png`) shows heading tracking
temperature as a near-mirror image across all 5+ diurnal cycles in the window — this is
unambiguous, not a marginal statistical artifact.

Because the relationship is linear with no lag and no meaningful hysteresis, **a simple
linear correction is sufficient** — no lookup table, no lagged/filtered temperature
input needed.

---

## Decided Strategy

### Formula

```
corrected_heading = heading_raw - SLOPE_RAD_PER_K * (temp_k - T_REF_K)
```

Note the **minus** sign: `SLOPE_RAD_PER_K` is the raw fitted regression slope (negative
— heading residual = `slope * (T - T_ref)`), so cancelling it out requires subtracting,
not adding. A `+` form was tried first during implementation and caught by
cross-checking the compiled formula numerically against
`analysis/thermal-drift/validate.py` before FOTA — it would have **doubled** the drift
(residual std 3.50° → 6.03°) instead of removing it (correct form: → 2.08°, matching
Phase 4). Worth flagging because it's an easy sign error to reintroduce if this is ever
rewritten.

Fitted defaults (radians, since `compass_heading` is in radians and
`environment.inside.ecompass.temperature` is in Kelvin — a 1 K step equals a 1 °C step,
so the same slope applies unconverted):

```cpp
constexpr float kThermalSlopeRadPerK = -0.017822f;  // -1.021 deg/C, from analysis/thermal-drift
constexpr float kThermalRefTempK = 303.222f;         // 30.07 C — temp at which correction is zero
```

`T_REF` is not a physically special temperature — it's simply where the fitted line
crosses zero residual against this window's baseline heading, so the correction has
(near-)zero bias under typical conditions. If the mounting or magnetic calibration is
ever redone, `T_REF` may need a bias adjustment (re-run the analysis); the slope itself
is a sensor-thermal characteristic and shouldn't need to change.

### Firmware insertion point

Insert **before** `mountingOffset`, right after `compass_heading` is created
(`main.cpp:293-295`), so the correction is applied once and propagates to *both*
`navigation.headingCompass` and `navigation.headingMagnetic` (the latter derives from
the former via `deviationInterpolator`, `main.cpp:317-322`):

```
compass_heading ─┐
                  ├─▶ Zip<float,float> ─▶ ThermalCompensation ─▶ mountingOffset ─▶ compass_sk_output ─▶ deviationInterpolator ─▶ ... ─▶ magneticheading_sk_output
temperature ─────┘
```

`setup()` was reordered: the `temperature` / `sensor_temperature` `RepeatSensor` (was
created later, old `main.cpp:419-434`) had to move up to just after `orientation_sensor`
is constructed and before the `COMPASS HEADING` section, since the compensation
transform needs both producers to exist before it can zip them together. The SK output
for raw temperature (`environment.inside.ecompass.temperature`) is unaffected — it still
just reads `sensor_temperature->ReportValue()` directly, unrelated to the correction
path.

`Zip<float,float>`'s actual API (its `consumers` member is a `std::tuple` of
`LambdaConsumer`s, not `get_input_a()/get_input_b()` accessors as an earlier sketch of
this doc assumed) combines the two producers into a `std::tuple<float,float>` once both
have a value within `max_age`; `max_age` is 10000 ms (temperature reports every
`CALIBRATION_REPORTING_INTERVAL_MS` = 4000 ms, so 10 s gives comfortable margin without
masking a real sensor stall). This means `headingCompass`/`headingMagnetic` won't publish
until the first temperature reading lands (up to ~4 s after boot) — a minor, accepted
startup delay.

`ThermalCompensation` is a small custom `LambdaTransform<std::tuple<float,float>, float>`
(no existing SensESP transform takes a tuple and produces a corrected angle — `Linear`
and `AngleCorrection` are both single-input). As implemented (`main.cpp`, `COMPASS
HEADING` section):

```cpp
auto* thermal_zip = new Zip<float, float>(10000);
compass_heading->connect_to(std::get<0>(thermal_zip->consumers));
temperature->connect_to(std::get<1>(thermal_zip->consumers));

auto thermal_compensation = std::make_shared<
    LambdaTransform<std::tuple<float, float>, float>>(
    [](std::tuple<float, float> input) -> float {
      float heading_rad = std::get<0>(input);
      float temp_k = std::get<1>(input);
      return heading_rad -
             g_thermal_slope_rad_per_k * (temp_k - g_thermal_ref_temp_k);
    });
thermal_zip->connect_to(thermal_compensation);
thermal_compensation->connect_to(mountingOffset);
```

(`g_thermal_slope_rad_per_k` / `g_thermal_ref_temp_k` are the NVS-backed globals below,
not the `constexpr` defaults directly — defaults seed NVS on first boot.)

### Coefficient storage

New `Preferences` NVS namespace `"thermalcomp"` (mirrors the existing `"battery"`
namespace pattern, `main.cpp:192-199`), keys `"slope"` and `"tref_k"`. **Not** the
`OrientationSensorFusion-ESP` library's raw EEPROM calibration blob — that's a separate
mechanism owned by the fusion library for hard/soft-iron calibration, unrelated to this.

Load at boot with the `constexpr` values above as fallback defaults (first-boot / NVS-erased
case). Add a small HTTP config endpoint mirroring `/api/battery/config`
(`main.cpp:455-466` for the pattern) — `GET/POST /api/thermal/config` — so the
coefficients can be retuned in the field (e.g. after a future re-run of the analysis with
more data, or a seasonal recalibration) without a reflash.

---

## Open Items for Implementation

- Exact `Zip` `max_age` value — 10000 ms is a starting recommendation, not yet stress-tested against real reporting jitter.
- HTTP endpoint request/response JSON shape — follow `/api/battery/config`'s shape (`main.cpp:455-466`) for consistency.
- Whether to expose the coefficients via a `ConfigItem` (SensESP's own web config UI, as `mountingOffset`/`deviationInterpolator` do) instead of a bespoke HTTP endpoint — the existing `battery` config didn't use `ConfigItem` and went with bespoke HTTP + boat-panel, so following that precedent is simpler and consistent with this codebase's practice for non-`Configurable`-based values.
