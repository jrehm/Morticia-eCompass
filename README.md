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
- Backup: RPi4 running HALOS, Signal K at `https://rpi4.lan:4430` (192.168.8.212)
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
| `electrical.batteries.house.energy` | Remaining energy (Wh) | INA228 hardware register |
| `electrical.batteries.house.capacity.remaining` | Remaining charge (Ah) | INA228 hardware register |
| `electrical.batteries.house.capacity.stateOfCharge` | State of charge (0–1 ratio) | INA228 hardware register |

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

**This only works from a machine physically on the boat's local WiFi**
(the GL-X750 travel router, SSID `Morticia`, subnet `192.168.8.0/24`) — the
ESP32's `192.168.8.214` address isn't reachable from anywhere else. In
particular, **a dev machine connected only via Tailscale cannot reach it**:
HALOS (`halos`, Tailscale IP `100.64.200.98`) is on the boat LAN too
(`192.168.8.102`), but does not advertise `192.168.8.0/24` as a Tailscale
subnet route, so Tailscale gives no path in. (`ping 192.168.8.214` from an
off-boat-LAN machine will simply time out — that's the symptom, not a
firmware or auth problem.)

**Workaround — flash via HALOS**, which shares the boat LAN with the ESP32:

```bash
# From the dev machine, build first, then:
scp .pio/build/shesp32/firmware.bin halos:/tmp/ecompass-firmware.bin
ssh halos "python3 /home/pi/espota.py -i 192.168.8.214 -a morticia \
    -f /tmp/ecompass-firmware.bin -r -d -t 30"
ssh halos "rm -f /tmp/ecompass-firmware.bin"   # cleanup
```

`espota.py` is already present on HALOS at `/home/pi/espota.py` (a standalone
copy of the same script PlatformIO's `pio run -t upload` uses internally, from
`~/.platformio/packages/framework-arduinoespressif32/tools/espota.py` —
no PlatformIO install needed on HALOS itself, just Python 3, which HALOS has).
After flashing, sanity-check the device came back up, e.g.:

```bash
ssh halos "curl -s http://192.168.8.214/api/battery/config"  # or any GET endpoint the firmware exposes
```

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

### Battery state of charge

The INA228's hardware charge and energy accumulation registers track Coulombs
and Joules in/out since the last "set full" event. The firmware converts these
to operator-friendly values using the pack's nominal capacity:

```cpp
#define INA_BATTERY_NOMINAL_AH  (100.0f)   // Eco-Worthy 100Ah pack
#define INA_BATTERY_NOMINAL_V   (12.8f)    // nominal LiFePO4 voltage
```

**Set full** (call after a confirmed full charge):
- Boat admin panel: use the **Set Battery Full** button at `halos.local/boat-panel`
- HTTP endpoint: `curl -X POST http://sensesp.local/api/battery/set-full`

**Sign convention:** discharge produces a *negative* accumulator value, so
`remaining_Ah` decreases during discharge. If `capacity.remaining` increases
during discharge, swap the INA228 shunt sense wires (IN+/IN−) — hardware fix,
no code change needed.

## Watchdog & Reliability

- **Hardware watchdog (120s):** Reboots if the main event loop stalls
  (I2C bus hang, stack overflow, etc.). Fed every 15 seconds from the event loop.
- **Connectivity watchdog (60s):** Monitors the Signal K WebSocket
  connection. Reboots if disconnected longer than 60 seconds — handles the
  edge case where `esp_websocket_client` fails to fire a disconnect callback
  after a Signal K server restart.

Timeouts are configurable via `HW_WATCHDOG_TIMEOUT_S` and
`SK_CONNECTION_TIMEOUT_MS` in `src/main.cpp`.

## Local Library Patches

Two vendored libraries need local patches to expose members their upstream APIs
keep private. **These are applied automatically** by `scripts/apply_patches.py`,
wired in as a PlatformIO pre-build hook (`extra_scripts` in `platformio.ini`).
The script is idempotent, covers every env's independent `.pio/libdeps/` copy,
and **aborts the build** if an anchor is missing rather than letting the compile
fail later with an obscure access error.

You should not need to do anything. To verify or repair without building:

```sh
python3 scripts/apply_patches.py            # all envs present in .pio/libdeps
python3 scripts/apply_patches.py shesp32_ota
```

The patches are:

1. **SensESP** `src/sensesp_app.h` — add a public `get_http_server()`.
   SensESP 3.3.x–3.5.x keep `http_server_` protected with no accessor; the
   custom `/api/*` handlers in `main.cpp` need it.
2. **OrientationSensorFusion-ESP** `src/sensor_fusion_class.{h,cc}` — add
   `GetMagneticBcX/Y/Z()`. Upstream exposes field *magnitude* and inclination
   but no vector accessor; `sfg_->Mag.fBc[]` is the per-cycle calibrated
   (hard-/soft-iron corrected) field vector from `conditionSensorReadings()`.
   Published as `orientation.calibration.magfieldvector.{x,y,z}`.

If a library upgrade moves the anchors, the script prints the anchor it could
not find and stops — rewrite that patch in `scripts/apply_patches.py` against
the new source. (History: patching only `shesp32/` and forgetting
`shesp32_ota/` compiles fine for USB but breaks OTA builds — cost a session on
2026-08-12. The script exists so that cannot recur.)

**Frame of the published vector (verified against the dock field, 2026-09-02):**
the vector is in the library's remapped body frame, **not** the chip's marked
axes and not bow/starboard/down. With the AGM01 mounted component-side up,
J3 row fore-aft, marked +Y toward port (so marked +X toward the stern, +Z up),
the published axes are `x = starboard, y = astern, z = down` — i.e.
`(x, y, z)_published = (−Y, +X, −Z)_marked`. Check: at heading 190° the field
reads (0.9, 12.2, 45.8) µT — horizontal component astern on +y, dip down on +z.
See `analysis/calibration/magnoise_diagnostic_summary_20260901.md`.

## Known Upgrade Issues

Issues encountered during the v1.0.0 dependency upgrade (April 2026) that
may recur on future upgrades:

**1. OrientationSensorFusion-ESP: FIFO size constants undefined**

Symptom: compile errors `'ACCEL_FIFO_SIZE' undeclared` in `sensor_fusion.h`.

Cause: header include order bug in `OrientationSensorFusion-ESP` HEAD — the
`SENSOR_FXAX2100x_AND_FXOS8700` define from `board.h` arrives too late for
`driver_sensors.h` to see it.

Fix: already applied — `-D SENSOR_FXAX2100x_AND_FXOS8700` in `platformio.ini`
`build_flags` makes the hardware selection explicit and sidesteps the bug.

**2. SignalK-Orientation v1.0.1: `OrientationSensor` constructor changed**

Symptom: `no matching function for call to 'OrientationSensor::OrientationSensor(int, int, int, int)'`.

Cause: v1.0.1 added STM sensor support and split the 4-arg constructor into
6 args: `(sda, scl, accel_addr, mag_addr, gyro_addr, therm_addr)`.

Fix: already applied in `main.cpp` — for FXOS8700CQ, accel/mag/therm are all
the same chip at 0x1E, so `BOARD_ACCEL_MAG_I2C_ADDR` is passed for all three.

## Credits

Runs on the [SH-ESP32](https://github.com/hatlabs/SH-ESP32) (Hat Labs Sailor Hat for ESP32).
Documentation: [docs.hatlabs.fi/sh-esp32](https://docs.hatlabs.fi/sh-esp32/)

Built on [SignalK-Orientation](https://github.com/BjarneBitscrambler/SignalK-Orientation)
by Bjarne Hansen, using the [SensESP](https://github.com/SignalK/SensESP) framework.
Power monitoring uses [RobTillaart/INA226](https://github.com/RobTillaart/INA226)
and [RobTillaart/INA228](https://github.com/RobTillaart/INA228).
