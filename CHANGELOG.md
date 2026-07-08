# Changelog

All notable changes to Morticia eCompass will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version bump checklist:**
1. Update `FIRMWARE_VERSION` in `platformio.ini`
2. Add entry here under `[Unreleased]`, then move to a new `[X.Y.Z]` section
3. Build, test, OTA flash to boat
4. `git tag -a vX.Y.Z -m "Release vX.Y.Z"` and `git push origin vX.Y.Z`

---

## [Unreleased]

---

## [1.3.1] - 2026-07-08

### Added
- Full-charge detector's `passRatio` and `latched` state now also published
  to Signal K (`electrical.batteries.house.fullChargeDetector.{passRatio,
  latched}`), not just the `GET /api/battery/config` snapshot. The HTTP
  endpoint only ever showed the current instant, and the latch's own
  hysteresis reset erases any earlier trigger before the next poll — this
  makes detector behavior queryable from the same InfluxDB history already
  used for `electrical.batteries.house.{voltage,current}`, closing the gap
  needed to validate the detector's real-world soak test.

---

## [1.3.0] - 2026-07-06

### Added
- Battery SoC persistence: periodic NVS checkpoint (30 min) bounds SoC
  staleness after an unplanned power loss, and an automated full-charge
  detector (rolling 20-minute window, 80% pass threshold on voltage
  ≥14.4V / |current| ≤0.2A, edge-triggered with 14.0V hysteresis reset)
  auto-seeds SoC to 100% on genuine full-charge events, correcting
  coulomb-counting drift without manual intervention. See
  `docs/battery-soc-persistence-handoff.md` for the design rationale and
  threshold/dwell-time tradeoffs.
- `GET /api/battery/config` now also reports `full_charge_pass_ratio` and
  `full_charge_latched`, so the detector can be observed live during a
  soak test without needing serial/USB access.

### Fixed
- SensESP dependency pinned exact (`3.4.0`, no caret) — a caret range had
  resolved to an untagged git-HEAD alpha (`3.4.1-alpha`) instead of the
  intended registry release, breaking build reproducibility.
- OrientationSensorFusion-ESP pinned to an exact commit. It's a transitive
  dependency of `SignalK-Orientation`, whose own `library.json` declares it
  as a bare git URL with no version constraint, so it floated to whatever
  was on `main` at install time. No code change — pinned to the commit
  already built and flashed.

---

## [1.2.3] - 2026-07-06

### Changed
- SensESP bumped `^3.3.0` → `^3.4.0`: user-configured hostname now persists
  across reboots, v2-style IP address logging restored on network connect,
  `StreamLineProducer` internal `emit()` fix, `esp_websocket_client` dropped
  from SensESP's own manifest (no effect here — already declared directly in
  `platformio.ini`). Pulls in ReactESP `3.3.1` (was `3.3.0`, which upstream
  identified as broken under the C++14 Arduino-Espressif toolchain).
- Reapplied local `get_http_server()` patch to `sensesp_app.h` — `http_server_`
  remains `protected` in 3.4.0. See README § "Local SensESP Patches".

---

## [1.2.2] - 2026-07-04

### Added
- `environment.inside.ecompass.temperature` Signal K path — publishes the
  FXOS8700CQ's onboard thermometer (`OrientationValues::kTemperature`,
  reported in Kelvin) at the calibration-diagnostics interval (4s). No
  compensation logic yet; intended to correlate against heading/attitude
  drift to characterize thermal drift magnitude before deciding on a fix.

---

## [1.2.1] - 2026-06-15

### Added
- `GET /api/battery/config` HTTP endpoint — returns current NVS battery
  config (`capacity_ah`, `seed_ah`, `nominal_v`) so boat-panel can read and
  display the active configuration

---

## [1.2.0] - 2026-06-15

### Added
- NVS-backed battery config: `capacity_ah`, `nominal_v`, and `seed_ah`
  loaded from Preferences at startup; compile-time `#define`s serve as
  fallback defaults on first boot
- `/api/battery/configure` HTTP endpoint (replaces `/api/battery/set-full`):
  accepts `{"capacity_ah": N, "soc": N, "nominal_v": V}` (all optional),
  computes `seed_ah = capacity_ah * soc`, writes to NVS, resets the INA228
  accumulator, and returns a JSON confirmation

### Changed
- Signed power: battery and solar power now computed as `current * voltage`,
  following the current sign convention (negative = discharge/consuming,
  positive = charge/producing)

---

## [1.1.0] - 2026-05-29

### Added
- INA228 power monitoring: voltage, current, power published to
  `electrical.batteries.house.*` and `electrical.solar.*` Signal K paths
- Remaining capacity paths (computed from INA228 hardware accumulators):
  - `electrical.batteries.house.capacity.remaining` — remaining Ah
  - `electrical.batteries.house.capacity.stateOfCharge` — SoC ratio 0–1
  - `electrical.batteries.house.energy` — remaining Wh
- `/api/battery/set-full` HTTP endpoint — sets INA228 RSTACC bit to reset
  charge and energy accumulators, establishing a full-charge reference point
- `/api/calibration/save-mag` HTTP endpoint restored — removed when SensESP
  3.3.1 dropped `get_http_server()`; restored via local patch (see below)
- Nominal pack constants: `INA_BATTERY_NOMINAL_AH` (100Ah),
  `INA_BATTERY_NOMINAL_V` (12.8V), `INA_BATTERY_NOMINAL_WH` (1280Wh)

### Changed
- SensESP updated to 3.3.1-alpha (pulled as transitive dep alongside 3.3.0)
- Removed `set_client_id()` local patch — no longer needed; SK source key
  is now derived from the hostname
- Replaced UIButton approach with HTTP endpoints — Control tab not yet
  implemented in SensESP 3.3.x frontend
- `FIRMWARE_VERSION` → `1.1.0`

### Fixed
- `setAccumulation(1)` not `setAccumulation(0)` — RSTACC bit must be set (1)
  to trigger a hardware accumulator reset; clearing it (0) is a no-op

### Local Patches (applied to `.pio/libdeps/shesp32/SensESP/src/sensesp_app.h`)
- Added `get_http_server()` public accessor — re-apply after `pio pkg update`

---

## [1.0.1] - 2026-04-23

### Changed
- Bumped SensESP dependency floor from `^3.2.2` to `^3.3.0` (released 2026-04-11)
- `FIRMWARE_VERSION` → `1.0.1`

### Why this matters
- **Memory safety**: CurveInterpolator memory leak fixed (we use it for the deviation table);
  use-after-free in WebSocket restart path fixed
- **Reliability**: `DigitalInputChange` data race fixed (used for mag cal save button);
  WebSocket reconnect now uses exponential backoff (reduces unnecessary reboots from our
  connectivity watchdog)
- **Security**: Admin password now stored as HA1 hash; CSRF protection on destructive HTTP
  endpoints (including our `/api/calibration/save-mag`)

### Build note
After `pio run` pulls 3.3.0, the two local SensESP patches must be reapplied before the
project will compile. See README § "Local SensESP Patches" for the exact lines to add to:
- `.pio/libdeps/shesp32/SensESP/src/sensesp/signalk/signalk_ws_client.h`
- `.pio/libdeps/shesp32/SensESP/src/sensesp_app.h`

---

## [1.0.0] - 2026-04-02

Initial production release. Firmware deployed on Morticia's SH-ESP32 at
`sensesp.local` (192.168.8.214), reporting to Signal K at `halos.local:3000`.

### Added

**Orientation**
- 9-axis heading/attitude sensor via BRKT-STBC-AGM01 (NXP FXOS8700CQ + FXAS21002C)
  using the SignalK-Orientation sensor fusion library
- `navigation.headingCompass` — raw compass heading with mounting offset (10 Hz)
- `navigation.headingMagnetic` — with deviation table correction (10 Hz)
- `navigation.attitude` — roll, pitch, yaw as AttitudeVector (5 Hz)
- `navigation.rateOfTurn` — turn rate in rad/s (5 Hz)
- `orientation.calibration.*` — magfit, magfittrial, magsolver, magnoise (0.25 Hz)
- Deviation table configurable via SensESP web UI
- Magnetic calibration save: HTTP POST, boot button (GPIO 0), or remote endpoint

**Power Monitoring**
- INA226 solar monitoring at 0x40 (MJKDZ board, external 20A/75mV shunt, R002 desoldered)
- INA228 battery monitoring at 0x41 (Adafruit #5832, external 20A/75mV shunt, onboard shunt desoldered)
- `electrical.solar.{voltage,current,power}` (1 Hz)
- `electrical.batteries.house.{voltage,current,power}` (1 Hz)
- `electrical.batteries.house.energy` — INA228 hardware accumulation register (Joules)
- `electrical.batteries.house.capacity` — INA228 hardware charge register (Coulombs)
- Compile-time `#define USE_INA228` to switch battery position between INA228 and INA226

**Reliability**
- Hardware watchdog (120 s) — reboots on main loop stall (I2C hang, stack overflow)
- Connectivity watchdog (60 s) — reboots if Signal K WebSocket disconnected
- ArduinoOTA with password authentication (`morticia`) for WiFi firmware updates
- OTA target: `pio run -t upload --upload-port 192.168.8.214`

**Signal K integration**
- Human-readable source naming via patched `SKWSClient` (`set_client_id` / `reset_auth_token`)
- Custom HTTP endpoint for calibration save via patched `SensESPApp` (`get_http_server`)

### Dependencies

| Library | Version | Source |
|---------|---------|--------|
| SensESP | ^3.2.2 | `SignalK/SensESP` |
| SignalK-Orientation | v1.0.1 | `BjarneBitscrambler/SignalK-Orientation` |
| RobTillaart INA226 | 0.6.6 | `RobTillaart/INA226` |
| RobTillaart INA228 | 0.4.1 | `RobTillaart/INA228` |
| pioarduino platform | stable | `pioarduino/platform-espressif32` |

### Known limitations / future work

- SensESP patches (`set_client_id`, `get_http_server`) are applied to the local
  `.pio/libdeps` copy and must be reapplied after `pio run --target clean` or a
  library upgrade. Track upstream SensESP for native support.
- INA228 accumulator reset strategy not yet decided — accumulators reset on every
  power cycle. Consider `resetAccumulators()` call on confirmed full charge.
- BMS Bluetooth integration deferred (Eco-Worthy proprietary protocol).

[Unreleased]: https://github.com/jrehm/Morticia-eCompass/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/jrehm/Morticia-eCompass/releases/tag/v1.0.1
[1.0.0]: https://github.com/jrehm/Morticia-eCompass/releases/tag/v1.0.0
