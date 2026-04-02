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

[Unreleased]: https://github.com/jrehm/Morticia-eCompass/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/jrehm/Morticia-eCompass/releases/tag/v1.0.0
