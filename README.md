# Morticia eCompass

9-axis orientation sensor and battery/solar power monitor for the SeaCart 30
trimaran "Morticia", reporting to Signal K via WiFi.

## Hardware

**Microcontroller**
- SH-ESP32 (Hat Labs Sailor Hat for ESP32), 16MB flash

**Orientation**
- BRKT-STBC-AGM01 (NXP FXOS8700CQ accel/mag + FXAS21002C gyro)

**Power monitoring** *(hardware pending installation)*
- INA226 @ 0x40 — battery shunt (interim; INA228 is the target, see below)
- INA226 @ 0x41 — solar charge controller shunt
- External shunt resistors: 20A/75mV (3.75mΩ) at both positions

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

Both INA226 boards share the same I2C bus as the BRKT sensor. Boards and
sense wires live inside the enclosure with the SH-ESP32; only thin sense
wires (22–24 AWG, twisted pairs) run out to the shunts.

| INA226 Pin | Signal | SH-ESP32 |
|------------|--------|----------|
| VBS / VCC | Power | 3.3V |
| GND | Ground | GND |
| SDA | I2C Data | SDA (GPIO 16) |
| SCL | I2C Clock | SCL (GPIO 17) |
| IN+ / IN- | Shunt sense | External shunt sense points |

**Address configuration:**
- Battery INA226 (0x40): A0 and A1 pins floating (default)
- Solar INA226 (0x41): A0 pin tied to VS (VCC); A1 floating

**Shunt placement:**
- **Battery shunt:** On the battery negative, between the battery terminal
  and the main negative bus bar. Captures all current in/out of the battery.
- **Solar shunt:** On the negative output wire of the solar charge controller,
  before it reaches the main negative bus bar.

**Current sign convention:** Positive current = charging. Verify after
installation — if the sign is reversed, swap IN+ and IN- at the shunt
(hardware fix, no code change needed).

## I2C Address Map

| Address | Device | Notes |
|---------|--------|-------|
| 0x1E | FXOS8700CQ (accel/mag) | BRKT default; differs from Adafruit 0x1F |
| 0x20 | FXAS21002C (gyro) | BRKT default; differs from Adafruit 0x21 |
| 0x40 | INA226/INA228 — battery shunt | INA228 target when available |
| 0x41 | INA226 — solar shunt | A0 tied to VS on board |

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
| `electrical.batteries.house.voltage` | Battery bus voltage (V) | 0x40 |
| `electrical.batteries.house.current` | Battery current (A, + = charging) | 0x40 |
| `electrical.batteries.house.power` | Battery power (W) | 0x40 |
| `electrical.solar.voltage` | Solar voltage (V) | 0x41 |
| `electrical.solar.current` | Solar current (A) | 0x41 |
| `electrical.solar.power` | Solar power (W) | 0x41 |

When INA228 is fitted at 0x40 (enable `USE_INA228` in firmware):

| Path | Description | Source |
|------|-------------|--------|
| `electrical.batteries.house.energy` | Accumulated energy (J) | 0x40 hardware register |
| `electrical.batteries.house.capacity` | Accumulated charge (C) | 0x40 hardware register |

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

### Shunt resistor

The shunt value is set in `src/main.cpp`:

```cpp
#define INA_SHUNT_OHMS (0.00375f)  // 20A/75mV = 3.75mΩ
#define INA_MAX_AMPS   (10.0f)     // realistic peak current (not shunt max)
```

To change shunt specs, update `INA_SHUNT_OHMS`:

| Shunt rating | Resistance | `INA_SHUNT_OHMS` |
|--------------|-----------|-----------------|
| 50A / 75mV | 1.5mΩ | `0.00150f` |
| 20A / 75mV | 3.75mΩ | `0.00375f` |
| 20A / 50mV | 2.5mΩ | `0.00250f` |

### Upgrading to INA228 (battery position)

The INA228 (Adafruit #5832) is a drop-in hardware replacement for the INA226
at 0x40. It adds 20-bit resolution and hardware energy/charge accumulation
registers. Wiring is identical.

To enable INA228 support: uncomment one line in `src/main.cpp` and reflash:

```cpp
#define USE_INA228   // uncomment this line
```

On first power-up after fitting INA228, call `resetAccumulators()` to zero
the energy and charge counters from a known state.

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
