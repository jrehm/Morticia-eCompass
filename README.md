# Morticia eCompass

9-axis orientation sensor and battery/solar power monitor for the SeaCart 30
trimaran "Morticia", reporting to Signal K via WiFi.

## Hardware

**Microcontroller**
- SH-ESP32 (Hat Labs Sailor Hat for ESP32), 16MB flash

**Orientation**
- BRKT-STBC-AGM01 (NXP FXOS8700CQ accel/mag + FXAS21002C gyro)

**Power monitoring**
- MJKDZ INA226 @ 0x40 — solar charge controller
- INA228 (Adafruit #5832) @ 0x41 — house battery

**Network**
- Primary: HALPI2 running Signal K at `halos.local:3000` (192.168.8.211)
- Backup: OpenPlotter Raspberry Pi 4 at `openplotter.local:3000` (192.168.8.212)
- ESP32 web UI: `http://sensesp.local` (192.168.8.214)

## Wiring

### BRKT-STBC-AGM01 → SH-ESP32

| BRKT Pin | Signal | SH-ESP32 |
|----------|--------|----------|
| Pin 5 (SDA1) | I2C Data | SDA (GPIO 16) |
| Pin 4 (SCL1) | I2C Clock | SCL (GPIO 17) |
| Pin 1 (VDD_8700) | Power | 3.3V |
| Pin 3 (VDDIO_8700) | I/O Voltage | 3.3V |
| Pin 7 (VDD_21002) | Power | 3.3V |
| Pin 9 (VDDIO_21002) | I/O Voltage | 3.3V |
| TP 5 (GND) | Ground | GND |

**Note:** SH-ESP32 has 2kΩ pull-ups on I2C. Do not add external pull-ups.

### INA226/INA228 (power sensors) → SH-ESP32

Both sensors share the same I2C bus. I2C header pins (SDA, SCL, VCC, GND)
connect to the SH-ESP32 directly inside the enclosure.

| Pin | Signal | SH-ESP32 |
|-----|--------|----------|
| VCC | Power | 3.3V |
| GND | Ground | GND |
| SDA | I2C Data | SDA (GPIO 16) |
| SCL | I2C Clock | SCL (GPIO 17) |

**Address configuration:**
- Solar INA226 (0x40): A0 and A1 floating (default)
- Battery INA228 (0x41): A0 pin tied to VS (VCC); A1 floating

### MJKDZ INA226 solar sensor — screw terminal wiring

Onboard shunt R002 has been desoldered. V+ and Current+ are pure sense points
connected via twisted-pair sense wires (22–24 AWG) to the external 20A/75mV shunt.

| Terminal | Connect to |
|----------|-----------|
| V+ (orange) | Sense wire — high side of external shunt |
| Current+ (orange) | Sense wire — low side of external shunt |
| Current− / V− (green, jumped together) | Negative rail / GND |

### Battery INA228 — screw terminal wiring

Onboard shunt resistor has been desoldered. The battery sensor uses an external
20A/75mV shunt on the battery negative rail. Thin sense wires (22–24 AWG,
twisted pair) run from the board to the shunt.

| Terminal | Connect to |
|----------|-----------|
| IN+ | Shunt sense — load side (toward bus bar) |
| IN− | Shunt sense — battery negative terminal |
| V+ / VBS | Battery positive (for bus voltage measurement) |
| GND | Negative rail |

**Shunt placement:** On the battery negative, between the battery terminal and
the main negative bus bar. Captures all current in/out of the battery.

**Current sign convention:** Positive = charging. If reversed, swap IN+ and IN−
at the shunt (hardware fix, no code change).

## I2C Address Map

| Address | Device | Notes |
|---------|--------|-------|
| 0x1E | FXOS8700CQ (accel/mag) | BRKT default; differs from Adafruit 0x1F |
| 0x20 | FXAS21002C (gyro) | BRKT default; differs from Adafruit 0x21 |
| 0x40 | INA226 — solar | MJKDZ board, A0/A1 floating (default) |
| 0x41 | INA228 — battery | Adafruit #5832, A0 tied to VS |

## Signal K Paths

### Orientation

| Path | Description | Rate |
|------|-------------|------|
| `navigation.headingCompass` | Compass heading (with mounting offset) | 10 Hz |
| `navigation.headingMagnetic` | Magnetic heading (with deviation correction) | 10 Hz |
| `navigation.attitude` | Yaw, pitch, roll | 5 Hz |
| `navigation.rateOfTurn` | Turn rate (rad/s) | 5 Hz |
| `orientation.calibration.magfit` | Mag cal fit in use (% — lower is better) | 0.25 Hz |
| `orientation.calibration.magfittrial` | Mag cal fit trial | 0.25 Hz |
| `orientation.calibration.magsolver` | Solver order [0,4,7,10] | 0.25 Hz |
| `orientation.calibration.magnoise` | Magnetic noise covariance | 0.25 Hz |

### Power Monitoring

| Path | Description | Source |
|------|-------------|--------|
| `electrical.solar.voltage` | Solar voltage (V) | INA226 @ 0x40 |
| `electrical.solar.current` | Solar current (A) | INA226 @ 0x40 |
| `electrical.solar.power` | Solar power (W) | INA226 @ 0x40 |
| `electrical.batteries.house.voltage` | Battery bus voltage (V) | INA228 @ 0x41 |
| `electrical.batteries.house.current` | Battery current (A, + = charging) | INA228 @ 0x41 |
| `electrical.batteries.house.power` | Battery power (W) | INA228 @ 0x41 |
| `electrical.batteries.house.energy` | Accumulated energy (J) | INA228 hardware register |
| `electrical.batteries.house.capacity` | Accumulated charge (C) | INA228 hardware register |

Load current is derived in Signal K by subtraction (battery current − solar
current) — no third shunt is needed.

## Setup

### Prerequisites

- [VS Code](https://code.visualstudio.com/) with [PlatformIO](https://platformio.org/) extension (pioarduino platform)

### First-time setup

1. Open this project folder in VS Code
2. Build and upload via USB: **PlatformIO > shesp32 > Upload and Monitor**
3. Connect to the `SensESP` WiFi AP (password: `thisisfine`)
4. Configure WiFi credentials and Signal K server via the web interface at `http://192.168.4.1`
5. After WiFi connects, the web interface moves to `http://sensesp.local`

### OTA firmware updates

ArduinoOTA is enabled with password `morticia`. After the initial USB flash,
all subsequent updates can be done over WiFi:

```bash
pio run -t upload --upload-port 192.168.8.214
```

The auth password is configured in `platformio.ini` via `upload_flags`.

### Magnetic calibration

After power-on, rotate the sensor through various orientations for 15–30 seconds.
Monitor `orientation.calibration.magfit` — values below 3.5% indicate good
calibration.

**Save calibration** (persists to NVS across reboots):
- Boat admin panel (preferred): use the compass calibration button at `halos.local/boat-panel`
- HTTP endpoint: `curl -X POST http://sensesp.local/api/calibration/save-mag`
- Physical fallback: press the BOOT button (GPIO 0) on the SH-ESP32

## Power Monitoring Configuration

### Shunt configuration

Both positions use identical 20A/75mV external shunts (3.75mΩ). Onboard shunt
resistors have been desoldered from both sensor PCBs.

```cpp
#define INA_SOLAR_SHUNT_OHMS   (0.00375f)  // 20A/75mV external shunt
#define INA_BATTERY_SHUNT_OHMS (0.00375f)  // 20A/75mV external shunt
```

These can be adjusted independently in `src/main.cpp` if a shunt is replaced.

### INA228 battery sensor

The INA228 is enabled via `#define USE_INA228` in `src/main.cpp`. It provides
20-bit ADC resolution and hardware energy/charge accumulation registers not
available on the INA226.

To revert to INA226 at the battery position, comment out `#define USE_INA228`.

## Watchdog & Reliability

- **Hardware watchdog (120s):** Reboots if the main event loop stalls
  (I2C bus hang, stack overflow, etc.). Fed every 15 seconds from the event loop.
- **Connectivity watchdog (60s):** Monitors the Signal K WebSocket
  connection. Reboots if disconnected longer than 60 seconds — handles the
  edge case where `esp_websocket_client` fails to fire a disconnect callback
  after a Signal K server restart.

Timeouts are configurable via `HW_WATCHDOG_TIMEOUT_S` and
`SK_CONNECTION_TIMEOUT_MS` in `src/main.cpp`.

## Local SensESP Patches

This project patches two methods into the local SensESP library copy
(`.pio/libdeps/shesp32/SensESP/src/sensesp_app.h`). These are lost on
`pio run --target clean` or library upgrade and must be reapplied:

- `set_client_id()` / `reset_auth_token()` on `SKWSClient` — human-readable
  Signal K source naming (see [ADR-005](https://github.com/jrehm/morticia-project/blob/main/DECISIONS.md))
- `get_http_server()` on `SensESPApp` — exposes HTTP server for custom
  endpoints like the calibration save handler (see [ADR-007](https://github.com/jrehm/morticia-project/blob/main/DECISIONS.md))

## Credits

Built on [SignalK-Orientation](https://github.com/BjarneBitscrambler/SignalK-Orientation)
by Bjarne Hansen, using the [SensESP](https://github.com/SignalK/SensESP) framework.
Power monitoring uses [RobTillaart/INA226](https://github.com/RobTillaart/INA226)
and [RobTillaart/INA228](https://github.com/RobTillaart/INA228).
