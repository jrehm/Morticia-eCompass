# Morticia eCompass — INA226 Integration Handoff

> **ARCHIVED PLANNING DOCUMENT** — The INA226/INA228 integration described here
> is complete as of April 2026. The firmware is deployed on the boat. See `README.md`
> for current hardware state and `CHANGELOG.md` for version history. This document
> is preserved for design rationale and decision history.
>
> **Address correction:** The final implementation swapped addresses from the plan
> below — INA226 solar landed at **0x40** (A0/A1 floating) and INA228 battery
> landed at **0x41** (A0 tied to VS). See the I2C Address Map in README.md.

## Purpose
This document provides everything needed to continue development on the
Morticia-eCompass project, specifically adding an INA226 current/voltage/power
sensor to the existing SensESP v3 firmware running on the SH-ESP32.

---

## Project Overview

**What:** 9-DOF heading/attitude sensor + (soon) power monitoring for the
SeaCart 30 trimaran "Morticia," reporting to Signal K via WiFi/WebSocket.

**Repo:** https://github.com/jrehm/Morticia-eCompass  
**Local:** `~/Documents/GitHub/Morticia-eCompass/`  
**Branch:** `main` (latest commit: `a074dd6`)

---

## Current Hardware

| Component | Details |
|-----------|---------|
| MCU | SH-ESP32 (Hat Labs Sailor Hat for ESP32), ESP32 D0WD-Q5 rev 3.01, 16MB flash |
| 9-DOF Sensor | BRKT-STBC-AGM01 (FXOS8700CQ accel/mag @ 0x1E + FXAS21002C gyro @ 0x20) |
| I2C Bus | GPIO16 (SDA), GPIO17 (SCL), 2kΩ pull-ups on SH-ESP32 header |
| WiFi | Connects to SSID "Morticia" (boat's network), gets IP 192.168.8.214 |
| Signal K Server | OpenPlotter RPi4 at 192.168.8.212:3000, discovered via mDNS |
| Serial Port | /dev/cu.usbserial-1420 (may change on reconnect) |

## Planned Addition: INA226

The INA226 is a high-side/low-side current and power monitor with I2C interface.
Jeff wants to add it to the same SH-ESP32 to monitor battery voltage/current/power
and report to Signal K. The INA226 shares the same I2C bus (GPIO16/17).

**Key INA226 specs:**
- Default I2C address: 0x40 (configurable via A0/A1 pins, range 0x40-0x4F)
- No conflict with existing BRKT addresses (0x1E, 0x20)
- Measures bus voltage (0-36V), shunt voltage, current, and power
- Requires external shunt resistor (value determines current range)

---

## Software Stack

| Layer | Version | Notes |
|-------|---------|-------|
| PlatformIO | pioarduino platform | `platform-espressif32.zip` (stable) |
| Arduino Core | 3.3.7 | ESP-IDF v5.5.2 underneath |
| SensESP | 3.2.2 | Signal K integration framework |
| SignalK-Orientation | 0.2.1 | 9-DOF sensor fusion library |
| esp_websocket_client | Espressif component | Required by pioarduino build |

**Build command:** `pio run -e shesp32`  
**Upload command:** `pio run -e shesp32 -t upload`  
**PIO binary:** `~/.platformio/penv/bin/pio`

---

## Current Firmware Architecture (src/main.cpp)

The firmware follows SensESP v3 patterns:

1. **SensESPAppBuilder** creates the app with hostname `morticia-ecompass`
2. **Watchdogs** (added in latest commit):
   - Hardware WDT: 120s timeout, reboots on main loop stall
   - Connectivity WDT: 5-min timeout, reboots if Signal K disconnected
   - Both fed every 15s from `event_loop()->onRepeat(15000, ...)`
3. **OrientationSensor** reads 9-DOF at fusion rate (~100Hz)
4. **Signal K outputs** via `RepeatSensor` → transform chain → `SKOutput`:
   - `navigation.headingCompass` (10 Hz) — raw compass + mounting offset
   - `navigation.headingMagnetic` (10 Hz) — compass → deviation table correction
   - `navigation.attitude` (5 Hz) — roll/pitch/yaw as AttitudeVector
   - `navigation.rateOfTurn` (5 Hz)
   - `orientation.calibration.*` (0.25 Hz) — magfit, magfittrial, magsolver, magnoise
5. **Deviation table** via `CurveInterpolator` — default 1:1 passthrough, configurable via web UI
6. **Mag cal save button** on GPIO0 (boot button) with debounce

---

## Key Files

| File | Purpose |
|------|---------|
| `src/main.cpp` | All application code (single-file SensESP pattern) |
| `platformio.ini` | Build config, I2C pins, I2C addresses, library deps |
| `README.md` | Project documentation |

---

## Build Notes & Gotchas

- **TAG macro:** Must use `build_src_flags` (not `build_flags`) to avoid collision with ESP-IDF C libraries. Currently: `-D TAG='"Morticia-eCompass"'`
- **I2C addresses:** BRKT uses non-standard 0x1E/0x20 (not Adafruit defaults 0x1F/0x21). INA226 at 0x40+ won't conflict.
- **Partition table:** `min_spiffs.csv` — OTA-capable with 1920KB per app slot
- **Flash usage:** 85.6% (1,682,954 / 1,966,080 bytes) — room is getting tight, monitor after adding INA226 library
- **RAM usage:** 16.6% (54,552 / 327,680 bytes) — plenty of headroom

---

## Signal K Path Conventions for Power Monitoring

Standard Signal K paths for electrical monitoring:
- `electrical.batteries.house.voltage` (V)
- `electrical.batteries.house.current` (A, positive = charging)
- `electrical.batteries.house.power` (W)

Jeff should confirm the battery bank name and sign convention for his setup.

---

## SensESP Pattern for Adding a New I2C Sensor

```cpp
// 1. Include the library header
#include "SomeINA226Library.h"

// 2. Initialize the sensor (shares existing I2C bus, no extra Wire.begin needed)
auto* ina226 = new INA226(0x40);  // or whatever library API
ina226->begin();
ina226->configure(...);  // shunt resistor value, averaging, etc.

// 3. Create RepeatSensor to poll it
auto voltage_sensor = std::make_shared<RepeatSensor<float>>(
    1000,  // 1 Hz is plenty for battery monitoring
    [ina226]() { return ina226->readBusVoltage(); });

// 4. Connect to Signal K output
auto voltage_output = std::make_shared<SKOutput<float>>(
    "electrical.batteries.house.voltage", "");
voltage_sensor->connect_to(voltage_output);
```

---

## INA226 Library Options for ESP32/PlatformIO

- **zanduino/INA** — multi-device INA library (supports INA226), available in PlatformIO registry
- **adafruit/Adafruit_INA226** — if available
- **Custom register-level** — INA226 is simple enough for direct I2C register reads

Evaluate which is compatible with pioarduino / ESP-IDF v5.5.2 / Arduino Core 3.3.7.

---

## Power System Architecture Decisions (from sensor selection session, Feb 2026)

### Dual-Sensor Topology
Two sensors are planned, sharing the same I2C bus on the SH-ESP32:

| Sensor | I2C Address | Measurement Point | Role |
|--------|-------------|-------------------|------|
| INA228 (Adafruit #5832) | 0x40 | Battery negative bus shunt | Net charge/discharge current, SoC tracking |
| INA226 | 0x41 | Solar charge controller negative output | Solar production monitoring |

**INA228 (Adafruit #5832) is the confirmed device for the battery position** — in hand as of March 2026. Selected for 20-bit resolution and hardware energy/charge accumulation registers (Wh and Ah counters in silicon).

**INA226 is used at the solar position (0x41)** — production monitoring only, no accumulation needed.

### Compile-Time Sensor Flag
The firmware uses `#define USE_INA228` to enable INA228-specific initialization and accumulation register reads:

```cpp
#define USE_INA228  // INA228 at 0x40 (battery) — confirmed hardware
```

Use `#ifdef USE_INA228` blocks around differing initialization and read calls. SignalK paths,
SensESP scaffolding, and all downstream infrastructure remain unchanged.

### Shunt Resistor Specifications

| Position | Spec | Resistance | Reason |
|----------|------|------------|--------|
| Battery bus (Shunt #1) | 50A / 75mV | 1.5mΩ | Better resolution at typical 1.5–3A loads vs 100A shunt |
| Solar controller output (Shunt #2) | 50A / 75mV or smaller | 1.5mΩ | Solar max ~6.25A, well within range |

The `setShunt()` call for a 50A/75mV shunt:
```cpp
setShunt(0.0015, 10.0)  // 1.5mΩ, 10A max expected
```

**Important:** Do NOT run load current through the INA226 breakout board's onboard screw
terminals. The onboard shunt resistor (typically 0.1Ω/3.2A) is bypassed automatically when
you wire IN+ and IN- to the external shunt sense points. Thin sense wires only (22–24AWG)
run from the enclosure to the shunt. No desoldering required.

### Shunt Physical Placement (per electrical diagram)
- **Shunt #1:** In the waterproof fiberglass box, on the battery negative, between the battery
  terminal and the main negative bus. Replaces the "Current Meter" placeholder in the diagram.
  Captures all current in/out of the battery (solar, 110V charger, and all loads).
- **Shunt #2:** On the negative output wire of the solar charge controller, before it reaches
  the main negative bus bar.
- Load current is derived in SignalK by subtraction (battery current − solar current). No
  third shunt needed.
- Both shunts are on the **negative side** — standard DC convention, avoids measurement
  reference issues.

### Wiring Notes
- Sense wires are voltage sense only (microamp current) — wire length is not a practical
  concern. Run whatever length is needed to reach shunts from the enclosure.
- **Twist the sense wire pairs** loosely for noise rejection from adjacent current-carrying cables.
- INA226/INA228 boards live in the same enclosure as the SH-ESP32. I2C runs are just
  short jumpers inside the enclosure — ideal for signal integrity.
- I2C address on INA226 #2 (solar, 0x41): tie A0 pin to VS (VCC) on that board.

### Complete I2C Address Map
| Address | Device | Notes |
|---------|--------|-------|
| 0x1E | FXOS8700CQ accel/mag (9DOF) | Existing |
| 0x20 | FXAS21002C gyro (9DOF) | Existing |
| 0x40 | INA228 (Adafruit #5832) — battery shunt | New |
| 0x41 | INA226 — solar shunt | New |

### SignalK Paths (confirmed)
```
electrical.batteries.house.voltage      (V)   — from 0x40
electrical.batteries.house.current      (A)   — from 0x40, positive = charging
electrical.batteries.house.power        (W)   — from 0x40
electrical.solar.voltage                (V)   — from 0x41
electrical.solar.current                (A)   — from 0x41
electrical.solar.power                  (W)   — from 0x41
```
INA228 additional paths (hardware accumulation registers):
```
electrical.batteries.house.energy       (Wh)  — from hardware accumulation register
electrical.batteries.house.capacity     (Ah)  — from hardware charge register
```

### Library Recommendations
- **Battery sensor (0x40, INA228):** `https://github.com/RobTillaart/INA228`
- **Solar sensor (0x41, INA226):** `https://github.com/RobTillaart/INA226`
- Same author, same coding style — consistent API between both
- Verify compatibility with pioarduino / ESP-IDF v5.5.2 / Arduino Core 3.3.7 on first build

### Eco-Worthy Battery BMS Bluetooth — Deferred
The battery (Eco-Worthy 12.8V 100Ah LiFePO4) has built-in Bluetooth BMS. Integration is
not currently feasible — Eco-Worthy recently changed BMS suppliers and the current hardware
uses a proprietary classic Bluetooth implementation that does not respond to standard
JBD/Xiaoxiang protocol tools. The BMS_BLE-HA integration explicitly excludes ECOxxxx devices.

The BMS broadcasts A1/A2 hex frames containing basic data — reverse engineering these via
Python BLE on the RPi is the best future path, but is low priority. SoC estimation will
be handled via INA228 hardware accumulation registers and voltage curve in SignalK.

### Flash Usage Warning
Current flash usage is 85.6% before adding INA226/INA228 libraries. Monitor carefully
after adding dependencies — may need to evaluate library size or optimize if space is tight.

---

## What Needs to Happen

### Resolved (decisions made, hardware not yet installed)
- [x] **Sensor selection:** INA228 (Adafruit #5832, in hand) at 0x40 (battery); INA226 at 0x41 (solar)
- [x] **Library selection:** RobTillaart INA228 + INA226 (same author, consistent API)
- [x] **Shunt spec:** 50A/75mV (1.5mΩ) at both positions
- [x] **Shunt placement:** Battery negative in waterproof box (Shunt #1), solar controller negative output (Shunt #2)
- [x] **I2C address map:** confirmed no conflicts with existing 0x1E/0x20 (BRKT)
- [x] **SignalK paths:** confirmed (see architecture section above)

### Hardware (pending)
- [ ] Order INA226 breakout board x1 and 50A/75mV shunt resistors x2
- [ ] Set A0 pin to VS on the solar INA226 board to set address 0x41
- [ ] Wire shunts and sense leads, install in enclosure with SH-ESP32
- [ ] Twist sense wire pairs before routing

### Firmware (pending)
- [ ] Add `#define USE_INA228` to `main.cpp`
- [ ] Add RobTillaart INA228 and INA226 libraries to `lib_deps` in `platformio.ini`
- [ ] Initialize INA228 at 0x40 and INA226 at 0x41, both with `setShunt(0.0015, 10.0)`
- [ ] Add `RepeatSensor` + `SKOutput` for voltage, current, power on both sensors
- [ ] Add INA228 energy/charge accumulation reads (Wh, Ah)
- [ ] Verify I2C bus sharing at 100kHz with all four devices (0x1E, 0x20, 0x40, 0x41)
- [ ] Monitor flash usage after adding libraries — currently at 85.6%, headroom is tight
- [ ] Test and verify all SignalK paths visible in data browser
- [ ] Update README and commit

---

## MCP Tools Available

Claude has access to these MCP servers for real-time integration:
- **Signal K MCP** — query live vessel data at 192.168.8.212:3000
- **InfluxDB MCP** — query/write time-series data
- **Desktop Commander / Filesystem** — read/write project files, run builds
- **Claude in Chrome** — browser automation if needed

---

## Reference Documents

- Previous transcript: `/mnt/transcripts/2026-02-16-17-04-37-sh-esp32-brkt-ecompass-build-deploy.txt`
- Compacted session transcript: `/mnt/transcripts/2026-02-21-20-27-56-morticia-ecompass-watchdog-reconnect.txt`
- Reference guide: `Morticia-eCompass-Reference-Guide.docx` (created in earlier session)
