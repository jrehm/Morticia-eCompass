# Morticia eCompass

9-axis orientation sensor and battery/solar power monitor for the SeaCart 30
trimaran "Morticia", reporting to Signal K via WiFi.

## Hardware

**Microcontroller**
- SH-ESP32 (Hat Labs Sailor Hat for ESP32), 16MB flash

**Orientation**
- BRKT-STBC-AGM01 (NXP FXOS8700CQ accel/mag + FXAS21002C gyro)

**Power monitoring**
- MJKDZ INA226 @ 0x40 — solar charge controller *(installed)*
- INA226/INA228 @ 0x41 — house battery *(pending installation)*

**Network**
- OpenPlotter Raspberry Pi 4 running Signal K at 192.168.8.212:3000

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

### INA226 (power sensors) → SH-ESP32

Both INA226 boards share the same I2C bus. I2C header pins (SDA, SCL, VCC, GND)
connect to the SH-ESP32 directly inside the enclosure.

| INA226 Pin | Signal | SH-ESP32 |
|------------|--------|----------|
| VCC | Power | 3.3V |
| GND | Ground | GND |
| SDA | I2C Data | SDA (GPIO 16) |
| SCL | I2C Clock | SCL (GPIO 17) |

**Address configuration:**
- Solar INA226 (0x40): A0 and A1 floating (default)
- Battery INA226/INA228 (0x41): A0 pin tied to VS (VCC); A1 floating

### MJKDZ INA226 solar sensor — screw terminal wiring

The MJKDZ board has an onboard 2mΩ shunt (R002) between the V+ and Current+
terminals. For production installation, **desolder R002** so that no load
current flows through the board — V+ and Current+ then become pure sense points.
Run thin twisted-pair sense wires (22–24 AWG) from those terminals to the
external shunt. The three screw terminals are:

| Terminal | Connect to |
|----------|-----------|
| V+ (orange) | Sense wire — high side of external shunt |
| Current+ (orange) | Sense wire — low side of external shunt |
| Current− / V− (green, jumped together) | Negative rail / GND |

**External shunt:** Load current flows through the shunt only — not through
the board. After desoldering R002, update `INA_SHUNT_OHMS` in firmware to
match the external shunt (see Power Monitoring Configuration below).

**Bench/interim:** With R002 intact, the board can be used in-line (current
flowing through the board via V+ → R002 → Current+). This is how it is
currently wired for bench testing.

### Battery sensor — screw terminal wiring *(pending)*

The battery sensor uses an external shunt on the battery negative rail.
Thin sense wires (22–24 AWG, twisted pair) run from the board to the shunt.

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
| 0x41 | INA226/INA228 — battery | A0 tied to VS; INA228 target when available |

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

| Path | Description | Source | Status |
|------|-------------|--------|--------|
| `electrical.solar.voltage` | Solar voltage (V) | 0x40 | ✓ Working |
| `electrical.solar.current` | Solar current (A) | 0x40 | ✓ Working |
| `electrical.solar.power` | Solar power (W) | 0x40 | ✓ Working |
| `electrical.batteries.house.voltage` | Battery bus voltage (V) | 0x41 | Pending |
| `electrical.batteries.house.current` | Battery current (A, + = charging) | 0x41 | Pending |
| `electrical.batteries.house.power` | Battery power (W) | 0x41 | Pending |

When INA228 is fitted at 0x41 (enable `USE_INA228` in firmware):

| Path | Description | Source |
|------|-------------|--------|
| `electrical.batteries.house.energy` | Accumulated energy (J) | 0x41 hardware register |
| `electrical.batteries.house.capacity` | Accumulated charge (C) | 0x41 hardware register |

Load current is derived in Signal K by subtraction (battery current − solar
current) — no third shunt is needed.

## Setup

1. Install VS Code + PlatformIO (pioarduino)
2. Open this project folder
3. Build and upload: PlatformIO > shesp32 > Upload and Monitor
4. Connect to the `morticia-ecompass` WiFi AP (password: `thisisfine`)
5. Configure WiFi and Signal K server via the web interface
6. Perform magnetic calibration by rotating sensor through all axes

## Power Monitoring Configuration

### Shunt configuration

Both sensor positions use the same 20A/75mV external shunt (3.75mΩ). Since
both shunts are identical, a single `INA_SHUNT_OHMS` constant covers both.

**Production (external shunts at both positions):**
```cpp
#define INA_SHUNT_OHMS (0.00375f)  // 20A/75mV external shunt = 3.75mΩ
```

**Solar (bench/interim — R002 intact, current through board):**
```cpp
#define INA_SHUNT_OHMS (0.00200f)  // onboard R002 on MJKDZ INA226 board
```

**Reference — shunt resistance values:**

| Shunt rating | Resistance | `INA_SHUNT_OHMS` |
|--------------|-----------|-----------------|
| 20A / 75mV | 3.75mΩ | `0.00375f` ← production |
| 50A / 75mV | 1.5mΩ | `0.00150f` |
| MJKDZ R002 onboard | 2mΩ | `0.00200f` ← bench only |

### Upgrading to INA228 (battery position)

The INA228 (Adafruit #5832) is a drop-in hardware replacement for the INA226
at 0x41. It adds 20-bit resolution and hardware energy/charge accumulation
registers. Wiring is identical.

To enable INA228 support: uncomment one line in `src/main.cpp` and reflash:

```cpp
#define USE_INA228   // uncomment this line
```

On first power-up after fitting INA228, see the TODO comment in the
`#ifdef USE_INA228` block regarding `resetAccumulators()`.

## Watchdog & Reliability

- **Hardware watchdog (120s):** Reboots if the main event loop stalls
  (I2C bus hang, stack overflow, etc.). Fed every 15 seconds from the event loop.
- **Connectivity watchdog (5 min):** Monitors the Signal K WebSocket
  connection. Reboots if disconnected longer than 5 minutes — handles the
  edge case where `esp_websocket_client` fails to fire a disconnect callback
  after a Signal K server restart.

Timeouts are configurable via `HW_WATCHDOG_TIMEOUT_S` and
`SK_CONNECTION_TIMEOUT_MS` in `src/main.cpp`.

## Magnetic Calibration

After power-on, rotate the sensor through various orientations for 15–30 seconds.
Monitor `orientation.calibration.magfit` — values below 3.5% indicate good
calibration. Save calibration via the SH-ESP32 boot button (GPIO0) or the
SensESP web interface.

## Credits

Built on [SignalK-Orientation](https://github.com/BjarneBitscrambler/SignalK-Orientation)
by Bjarne Hansen, using the [SensESP](https://github.com/SignalK/SensESP) framework.
Power monitoring uses [RobTillaart/INA226](https://github.com/RobTillaart/INA226)
and [RobTillaart/INA228](https://github.com/RobTillaart/INA228).
