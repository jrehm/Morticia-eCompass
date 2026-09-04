# Device config snapshots

Point-in-time captures of the eCompass runtime configuration, taken before
firmware changes so live settings can be restored without guesswork.

Capture: `python3 /tmp/snap.py` on `halos` (see git history of this file), or
re-derive from `GET http://192.168.8.214/api/config` + `/api/thermal/config`.

## device-config-20260904.json — taken before the vector-TCO firmware work

Running build `Sep 2 2026 07:06:25` (v1.5.0, the `Bc[x,y,z]` publish).

- `thermal`: `slope_deg_per_c = -0.17`, `tref_c = 30.4`. **Provenance:** set
  during our own earlier work this month and never documented at the time;
  NOT a change by Chris. Superseded by the vector-domain TCO — this
  heading-domain scalar is structurally the wrong model (a vector offset
  produces a heading error that is sinusoidal in heading, so a scalar can only
  be correct at one heading). Expected to be zeroed once the vector correction
  is enabled.
- `/sensors/hdg/offset`: `-0.261803` rad = `-15.0` deg mounting offset.
- `/sensors/hdg/deviation`: identity (3 pass-through points) — no deviation
  correction is currently applied.
- `/system/httpserver`: `auth_required = false` (OTA itself uses `--auth`).

## Rollback binaries

Not in git (1.7 MB each). Two copies of the running firmware:
- `halos:/home/pi/firmware-archive/firmware-v1.5.0-20260902-rollback.bin`
- Mac: `~/Documents/morticia-firmware-archive/firmware-v1.5.0-20260902-rollback.bin`

Both md5 `eb2aecdff55f99fa51ac4c9bd2bede29`, identical to the
`.pio/build/shesp32_ota/firmware.bin` that produced the running build.
**`pio run` overwrites that build artifact — always archive before building.**

Roll back with:
`~/.platformio/packages/framework-arduinoespressif32/tools/espota.py -i 192.168.8.214 -f <bin> -a morticia`
