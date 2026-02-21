# Morticia eCompass

9-axis orientation sensor for the SeaCart 30 trimaran "Morticia", providing
heading, attitude, and rate-of-turn data to Signal K via WiFi.

## Hardware

- **Board:** SH-ESP32 (Hat Labs Sailor Hat for ESP32)
- **Sensor:** BRKT-STBC-AGM01 (NXP FXOS8700CQ accel/mag + FXAS21002C gyro)
- **Server:** OpenPlotter Raspberry Pi 4 running Signal K

## Wiring

| BRKT-STBC-AGM01 Pin | Signal | SH-ESP32 |
|---------------------|--------|----------|
| Pin 5 (SDA1) | I2C Data | SDA (GPIO 16) |
| Pin 4 (SCL1) | I2C Clock | SCL (GPIO 17) |
| Pin 1 (VDD_8700) | Power | 3.3V |
| Pin 3 (VDDIO_8700) | I/O Voltage | 3.3V |
| Pin 7 (VDD_21002) | Power | 3.3V |
| Pin 9 (VDDIO_21002) | I/O Voltage | 3.3V |
| TP 5 (GND) | Ground | GND |

**Note:** SH-ESP32 has 2kΩ pull-ups on I2C. Do not add external pull-ups.

## I2C Addresses

The BRKT-STBC-AGM01 uses different default addresses than the Adafruit 3463:

| IC | BRKT Address | Adafruit Default |
|----|-------------|-----------------|
| FXOS8700CQ (accel/mag) | **0x1E** | 0x1F |
| FXAS21002C (gyro) | **0x20** | 0x21 |

## Signal K Paths

| Path | Description | Rate |
|------|-------------|------|
| `navigation.headingCompass` | Compass heading (with mounting offset) | 10 Hz |
| `navigation.headingMagnetic` | Magnetic heading (with deviation correction) | 10 Hz |
| `navigation.attitude` | Yaw, pitch, roll (heel angle for racing) | 5 Hz |
| `navigation.rateOfTurn` | Turn rate | 5 Hz |
| `orientation.calibration.*` | Magnetic calibration diagnostics | 0.25 Hz |

## Setup

1. Install VS Code + PlatformIO (pioarduino)
2. Open this project folder
3. Build and upload: PlatformIO > shesp32 > Upload and Monitor
4. Connect to the `morticia-ecompass` WiFi AP (password: `thisisfine`)
5. Configure WiFi and Signal K server via the web interface
6. Perform magnetic calibration by rotating sensor through all axes

## Watchdog & Reliability

The firmware includes two watchdog mechanisms for unattended operation:

- **Hardware watchdog (120s):** Reboots the ESP32 if the main event loop
  stalls completely (I2C bus hang, stack overflow, etc.). Uses the ESP-IDF
  task watchdog timer, fed every 15 seconds.
- **Connectivity watchdog (5 min):** Monitors the Signal K WebSocket
  connection. If disconnected for more than 5 minutes — e.g., after a
  Signal K server restart where the underlying `esp_websocket_client`
  fails to fire a disconnect callback — the ESP32 reboots to force a
  clean reconnection.

Timeouts are configurable via `HW_WATCHDOG_TIMEOUT_S` and
`SK_CONNECTION_TIMEOUT_MS` at the top of `src/main.cpp`.

## Magnetic Calibration

After power-on, rotate the sensor through various orientations for 15-30 seconds.
Monitor `orientation.calibration.magfit` — values below 3.5% indicate good calibration.
Save calibration via the SH-ESP32 boot button or the web interface.

## Credits

Built on [SignalK-Orientation](https://github.com/BjarneBitscrambler/SignalK-Orientation)
by Bjarne Hansen, using [SensESP](https://github.com/SignalK/SensESP) framework.
