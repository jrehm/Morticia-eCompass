#!/usr/bin/env python3
"""
apply_patches.py — idempotently reapply local patches to vendored libraries.

WHY
---
Two vendored libraries need local patches to expose members the upstream APIs
keep private. PlatformIO wipes `.pio/libdeps/` on `--target clean`, on library
upgrades, and (observed 2026-08) sometimes on a plain `pio run`. Each env
(`shesp32`, `shesp32_ota`) has its own independent libdeps tree, so a patch
applied to only one compiles fine for USB but fails the OTA build — that cost a
debugging session on 2026-08-12.

This script replaces the manual procedure formerly documented in README.md.
It is idempotent: already-patched files are left untouched.

USAGE
-----
Automatically, as a PlatformIO pre-build step (see platformio.ini):
    extra_scripts = pre:scripts/apply_patches.py

Standalone, to verify or repair without building:
    python3 scripts/apply_patches.py            # all envs found in .pio/libdeps
    python3 scripts/apply_patches.py shesp32_ota

EXIT CODES
----------
0 = all patches present (applied or already there).
1 = a target file is missing, or an anchor could not be found. The anchor text
    is printed. A missing anchor usually means the library was upgraded and the
    patch needs rewriting against the new source — do NOT ignore it, the build
    will otherwise fail later with a confusing access error.
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each patch: library-relative file path, a marker used to detect "already
# applied", an anchor line that must match exactly once, and the text inserted
# immediately after that anchor.
PATCHES = [
    dict(
        name="SensESP: expose HTTP server",
        path="SensESP/src/sensesp_app.h",
        marker="get_http_server",
        anchor="std::shared_ptr<SKDeltaQueue> get_sk_delta() { return this->sk_delta_queue_; }",
        insert="""
  // LOCAL PATCH (scripts/apply_patches.py) — expose HTTP server for custom
  // endpoints. SensESP 3.3.x/3.4.x keep http_server_ protected with no public
  // accessor; needed by the custom /api/* handlers in main.cpp.
  std::shared_ptr<HTTPServer> get_http_server() { return this->http_server_; }""",
    ),
    dict(
        name="OrientationSensorFusion: Bc vector getters (declarations)",
        path="OrientationSensorFusion-ESP/src/sensor_fusion_class.h",
        marker="GetMagneticBcX",
        anchor="float GetMagneticBMagTrial(void);",
        insert="""
  // LOCAL PATCH (scripts/apply_patches.py) — expose the calibrated field
  // vector (uT). Upstream exposes magnitude and inclination but no vector
  // accessor. Published as orientation.calibration.magfieldvector.{x,y,z}.
  // Frame: (x, y, z) = (starboard, astern, down). See README.
  float GetMagneticBcX(void);
  float GetMagneticBcY(void);
  float GetMagneticBcZ(void);""",
    ),
    dict(
        name="OrientationSensorFusion: Bc vector getters (definitions)",
        path="OrientationSensorFusion-ESP/src/sensor_fusion_class.cc",
        marker="GetMagneticBcX",
        anchor="}  // end GetMagneticBMag()",
        insert="""
// LOCAL PATCH (scripts/apply_patches.py) — see header for rationale.
// sfg_->Mag.fBc[] is the per-cycle calibrated (hard-/soft-iron corrected)
// field vector computed in conditionSensorReadings().
float SensorFusion::GetMagneticBcX(void) {
  return sfg_->Mag.fBc[CHX];
}  // end GetMagneticBcX()

float SensorFusion::GetMagneticBcY(void) {
  return sfg_->Mag.fBc[CHY];
}  // end GetMagneticBcY()

float SensorFusion::GetMagneticBcZ(void) {
  return sfg_->Mag.fBc[CHZ];
}  // end GetMagneticBcZ()""",
    ),
]


def apply_to_env(libdeps_env_dir, env_name, log=print):
    """Apply every patch to one env's libdeps tree. Returns (applied, present, errors)."""
    applied = present = 0
    errors = []
    for p in PATCHES:
        target = os.path.join(libdeps_env_dir, p["path"])
        if not os.path.isfile(target):
            errors.append(f"[{env_name}] MISSING FILE {p['path']} (for '{p['name']}')")
            continue
        with open(target, "r", encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
        if p["marker"] in text:
            present += 1
            continue
        lines = text.split("\n")
        hits = [i for i, ln in enumerate(lines) if ln.strip() == p["anchor"]]
        if len(hits) != 1:
            what = "NOT FOUND" if not hits else f"AMBIGUOUS ({len(hits)}x)"
            errors.append(
                f"[{env_name}] ANCHOR {what} in {p['path']} for '{p['name']}'\n"
                f"             anchor: {p['anchor']}\n"
                f"             (library likely upgraded — rewrite the patch)"
            )
            continue
        lines.insert(hits[0] + 1, p["insert"].rstrip("\n"))
        with open(target, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write("\n".join(lines))
        log(f"  [{env_name}] applied: {p['name']}")
        applied += 1
    return applied, present, errors


def run(env_names, log=print):
    libdeps_root = os.path.join(PROJECT_DIR, ".pio", "libdeps")
    if not os.path.isdir(libdeps_root):
        log("apply_patches: no .pio/libdeps yet (first build?) — nothing to patch")
        return 0
    if not env_names:
        env_names = sorted(
            d for d in os.listdir(libdeps_root)
            if os.path.isdir(os.path.join(libdeps_root, d))
        )
    all_errors = []
    total_applied = total_present = 0
    for env_name in env_names:
        d = os.path.join(libdeps_root, env_name)
        if not os.path.isdir(d):
            log(f"apply_patches: no libdeps for env '{env_name}' — skipping")
            continue
        a, pr, errs = apply_to_env(d, env_name, log)
        total_applied += a
        total_present += pr
        all_errors.extend(errs)
    if all_errors:
        log("apply_patches: FAILED")
        for e in all_errors:
            log("  " + e)
        return 1
    log(f"apply_patches: OK — {total_applied} applied, {total_present} already present")
    return 0


# --- PlatformIO pre-script entry point -------------------------------------
try:
    Import("env")  # noqa: F821  (injected by PlatformIO/SCons)
except NameError:
    pass
else:
    _pioenv = env.subst("$PIOENV")  # noqa: F821
    print(f"apply_patches: pre-build check for env '{_pioenv}'")
    if run([_pioenv]) != 0:
        raise SystemExit("apply_patches: refusing to build with missing/failed patches")

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
