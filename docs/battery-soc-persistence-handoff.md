# Morticia eCompass — Battery SoC Persistence Handoff

> **PLANNING DOCUMENT** — not yet implemented. Written from a design discussion
> in `morticia-project` on 2026-07-06. Current firmware is `main.cpp` as of
> commit `ec25c59` (v1.2.1 line — see `CHANGELOG.md`).
>
> **2026-07-06 update:** open parameters below decided; implementation planning
> underway. See "Decided Parameters" section.

## Purpose

Resolve stale State-of-Charge (SoC) after a SensESP power cycle. This document
maps out the problem, the decided strategy, and what's still open, so
implementation can pick up without re-deriving the discussion.

---

## Problem Statement

`g_battery_seed_ah` (Ah remaining at the last configure) is only ever written
in one place: the `/api/battery/configure` HTTP handler (`main.cpp:569-616`),
triggered manually via boat-panel. At boot, it's loaded back from NVS
(`main.cpp:161`, `Preferences` namespace `"battery"`, key `"seed_ah"`), and the
live remaining-Ah figure is computed as:

```
remaining_ah = g_battery_seed_ah + accumulated_ah   // accumulated_ah from INA228 hardware coulomb counter
```

If the SH-ESP32 (or the whole enclosure) loses power, the INA228's hardware
accumulation registers reset to zero, and on reboot the firmware resumes from
whatever `seed_ah` happens to be sitting in NVS — which could be **days
stale** if nobody has called `/api/battery/configure` recently. The firmware
has no way to distinguish "seed_ah is from 5 minutes ago" from "seed_ah is
from last week."

---

## Decided Strategy

Two complementary mechanisms, addressing two different failure modes:

### 1. Periodic NVS checkpointing (bounds staleness after a power loss)

Automatically write the live computed `remaining_ah` back to NVS on a timer,
using the same persistence path the manual configure handler already uses
(`prefs.putFloat("seed_ah", ...)` + `ina_battery->setAccumulation(1)` to reset
the hardware accumulator). This is a mechanical extension of existing code —
no new persistence mechanism, just automating what `/api/battery/configure`
already does.

This does **not** correct drift — it just bounds the *staleness window* after
an unplanned reset to "however long since the last checkpoint" instead of
"however long since the last manual configure call" (which could be weeks).

Follows the existing `event_loop()->onRepeat(...)` pattern already used for
watchdog feeding (`main.cpp:202`):

```cpp
event_loop()->onRepeat(CHECKPOINT_INTERVAL_MS, []() {
    float accumulated_ah = static_cast<float>(ina_battery->getCharge()) / 3600.0f;
    float remaining_ah = g_battery_seed_ah + accumulated_ah;
    // only write if changed enough to be worth a flash write — see open question below
    Preferences prefs;
    prefs.begin("battery", false);
    prefs.putFloat("seed_ah", remaining_ah);
    prefs.end();
    g_battery_seed_ah = remaining_ah;
    ina_battery->setAccumulation(1);  // reset hardware accumulator to match new seed
});
```

**Decided: fixed 30-minute interval, no %-change trigger.** The %-change
half of the original candidate was dropped — the full-charge detector
(mechanism #2, below) already handles "a meaningful event just happened,
persist it now" by writing immediately when it fires, so the periodic timer
only needs to bound worst-case staleness after an *unplanned* reset, not
also react to magnitude of change. Flash wear is a non-issue at this cadence
regardless (~17,500 writes/year, trivial against NVS wear-leveled endurance).
Tradeoff: a fast shore-power bulk charge that completes and reverses within
a 30-min window right before a power loss would still be lost to staleness —
narrow edge case; shrinking to 15 min (still trivial for flash wear) is a
cheaper fix than adding the %-change trigger back if this shows up in
practice.

### 2. Automated full-charge detection (corrects drift, not just staleness)

This is the actual anti-drift mechanism — periodic checkpointing alone just
persists whatever value coulomb-counting drift has already produced. Ground
truth is needed periodically, and "battery reaches physically full" is a
ground-truth event that happens automatically (solar + shore power), unlike a
manual re-entry which depends on someone remembering to do it.

This revives the deferred TODO item already on record in `morticia-project`'s
`TODO.md`:

> Automated battery-full detection: voltage tail + low-current threshold →
> auto-seed SOC to 100% (manual override remains via
> `POST /api/battery/configure`)

**Design constraint discovered from real data (see below): needs a real dwell
time, not a single-sample threshold.** A naive check like
`voltage > 14.4 && abs(current) < 0.2` evaluated once per sample will
false-trigger on ordinary cloudy-day solar variability — see the InfluxDB
analysis below. The condition needs to hold for a sustained window (candidate:
several minutes to tens of minutes) before auto-seeding to 100%, and probably
needs hysteresis/percentage-of-samples logic rather than a single continuous
streak, since even genuine full-charge periods will have brief dips.

**Decided:**
- **Voltage threshold: ≥14.4V** (not 14.6V). Setting it near the charger's
  actual absorption setpoint risks the detector never firing on marginal
  days (peak observed was 14.43V on a cloudy day) — undermining the point of
  an automatic ground-truth correction. 14.4V is a reasonable "effectively
  full" line specifically because this is a 4S LiFePO4 pack (`nominal_v:
  12.8`): that chemistry has a flat voltage curve through the middle of its
  range and only rises steeply near the top, so 14.4V at near-zero current
  is already deep into >95% SoC regardless of whether 14.6V was technically
  reached.
- **Current threshold: |current| ≤ 0.2A** — unchanged from the original naive
  guess. The false-positive example (14.424V @ 0.108A) would satisfy *any*
  reasonable threshold, tight or loose — that's the actual finding: no
  static threshold alone solves this, so no design effort was spent
  tightening it further. The dwell logic below is what discriminates the
  false positive from a real one.
- **Dwell design: rolling 20-minute window, ≥80% of samples must pass.**
  Rejected continuous-streak: a passing cloud can dip below threshold for a
  few minutes even during a genuinely successful absorption/full period, and
  a streak-reset-to-zero design means one dip erases all progress — in bad
  weather the streak might never complete. A percentage-based rolling window
  tolerates those dips by design. The false-positive sample was isolated (15
  min later, voltage had dropped to 14.05V discharging at -0.39A) — a
  20-minute window straddling that timestamp would see mostly failing
  samples and correctly reject it; a genuine full/float period typically
  holds near setpoint for tens of minutes to hours, easily clearing 80%.

Tradeoff for both dwell parameters: shorter window / higher pass-% triggers
faster but is more false-positive-prone; longer window / lower pass-%
is more forgiving of real dips but slower to react and slightly more
permissive of marginal conditions. 20 min / 80% is a starting point, not
precision-tuned — cheap to adjust later since it's just constants, no new
sensor plumbing.

**Additional design point surfaced during this discussion (not one of the
original three, but a direct consequence of #2/#3 above):** the detector
needs an edge-trigger/cooldown guard, or it will re-seed every 20 minutes
for as long as the battery sits at float voltage (hours). Plan: track a
bool, only act on the *transition* into the "full" state (false→true), and
reset that bool once voltage drops clearly below threshold for a while
(e.g. <14.0V), signaling a new discharge cycle has begun. This avoids both
pointless repeated NVS writes and interaction weirdness with the periodic
checkpoint above.

### 3. Manual entry from the battery's Bluetooth app (secondary/backup only)

The existing `/api/battery/configure` endpoint already supports this — a
human reads SoC off Eco-Worthy's BMS app and POSTs it in. Per the
`INA226-Integration-Handoff.md` in this repo, **direct BLE integration with
the Eco-Worthy BMS is not feasible** (proprietary classic-Bluetooth protocol,
excluded from `BMS_BLE-HA`/JBD tooling) — so this will remain a manual,
occasional sanity-check path, not something to automate. Not the primary
mitigation for the staleness problem (too easy to forget), but worth keeping
as a manual override for whenever someone happens to check the app.

---

## Supporting Data: Why Dwell Time Matters (2026-07-05/06 InfluxDB analysis)

Pulled 24h of `electrical.batteries.house.{voltage,current}` and
`electrical.solar.{voltage,current}` from the HALPI2's InfluxDB (`signalk`
bucket) to check whether the solar charger's setpoint was fighting the
battery's BMS (a competing hypothesis raised during the discussion). Findings:

- **House load stayed essentially flat (~0.85-0.90A)** for the entire
  ~16:35-23:55 UTC solar-active window, computed as
  `solar_current - battery_current`. Load-cycling was ruled out as the cause
  of the swings.
- **Solar current itself cycled wildly** — 0.15A up to 1.4A and back, roughly
  every 15-40 minutes, all afternoon — with battery voltage/current tracking
  it almost exactly (13.6V-14.4V, -0.9A to +1.5A).
- **Peak battery voltage all day: 14.43V** — never reached the Genasun
  GV-10's 14.6V lithium absorption setpoint, ruling out "charger pushing
  against a lower BMS cutoff" as the cause, at least for this day.
- **Confirmed cause: it was cloudy that afternoon.** Passing cloud cover
  intermittently cutting solar production explains the pattern fully.
- **Concretely, at 18:50 UTC:** battery hit 14.424V at only 0.108A — a
  single-sample "voltage near setpoint + low current" check would have fired
  right there. 15 minutes later, voltage was back down to 14.05V, discharging
  at -0.39A. This is the concrete example motivating the dwell-time
  requirement above.
- One unexplained anomaly: a sharp current spike to +1.457A at 22:20 UTC not
  matched by a corresponding solar bump — not investigated further, flagged
  in case it recurs.

Diagnostic method for future reference: query InfluxDB directly
(`http://localhost:8086`, org `marine`, bucket `signalk`, token in
`/etc/rpi-clone-backup/backup.conf` on the HALPI2) rather than relying on
Grafana's downsampled dashboard view — raw resolution was needed to see the
implied-load-is-flat signal clearly.

---

## What Needs to Happen

### Decisions (2026-07-06 — see "Decided Strategy" above for rationale/tradeoffs)
- [x] Checkpoint interval: fixed 30 minutes, no %-change trigger
- [x] Full-charge thresholds: voltage ≥14.4V, |current| ≤0.2A
- [x] Dwell logic: rolling 20-minute window, ≥80% of samples must pass
- [x] Edge-trigger/cooldown guard for the full-charge detector (surfaced
      during this discussion, not in the original three)

### Firmware (implemented in v1.3.0 — `src/main.cpp`)
- [x] Add periodic checkpoint timer (`event_loop()->onRepeat`) writing
      `remaining_ah` to NVS `"seed_ah"` + resetting the INA228 accumulator,
      mirroring the existing `/api/battery/configure` handler's persistence
      logic
- [x] Implement full-charge detector with dwell time, auto-calling the same
      seed/reset logic as `/api/battery/configure` when triggered
- [x] Update CHANGELOG
- [ ] **Real-world soak test still needed.** Hand-traced against this doc's
      2026-07-05/06 data: the false-positive rejection is well-supported (the
      afternoon's described current variability — cycling -0.9A to +1.5A
      every 15-40 min — would keep a 20-minute window well under the 80%
      pass bar). The *acceptance* case (a genuine sustained full/float period
      actually reaching 80%) is **not** confirmed against real data — that
      day was cloudy and never produced a real full-charge event to check
      against (peak was 14.43V, the same event flagged as the false
      positive). Needs a few real charge cycles, ideally including at least
      one sunny day, before this is considered validated.
- [x] **v1.3.1:** `full_charge_pass_ratio` / `full_charge_latched` also
      published to Signal K (`electrical.batteries.house.fullChargeDetector.
      {passRatio,latched}`), not just the `GET /api/battery/config` snapshot —
      the HTTP endpoint only showed the current instant, and the latch's own
      hysteresis reset erased evidence of any earlier trigger before the next
      poll. This makes the soak test above checkable retroactively from
      InfluxDB history (same query method as the original cloudy-day
      analysis) rather than requiring live polling during the exact window a
      full-charge event happens.

### Documentation
- [ ] Once implemented, check off the "Automated battery-full detection" item
      in `morticia-project/TODO.md`

---

## Reference

- `morticia-project/TODO.md` — original deferred TODO item this revives
- `morticia-project/MODIFICATIONS.md` — battery time-remaining derived-data
  calc (2026-07-06 entry) that consumes `capacity.remaining` — same
  Signal K paths as this work
- `docs/INA226-Integration-Handoff.md` (this repo) — original INA228/INA226
  integration design, sign conventions, and the Eco-Worthy BMS Bluetooth
  infeasibility note
- `src/main.cpp:105-131, 496-616` — current battery config/SoC/accumulation
  code this handoff builds on
