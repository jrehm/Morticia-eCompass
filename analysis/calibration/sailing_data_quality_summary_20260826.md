# 2026-08-26 Race Session — Data Quality Summary

Source: `sailing_20260826_1855_to_1950_cleaned.csv` (Jeff's manually-tagged race-window export, Main/Headsail/Dagger/Tack-Gybe/PointOfSail added by hand -- same pattern as the 2026-07-29 log). Not the raw programmatic export (`sailing_20260826_185500_to_20260826_195000.csv`), which covers a wider window but has no per-row engine/sail state and, separately, has `HDGmE`/`HDGmF` essentially all-null (see below).
Window: 2026-08-26 19:00:00 -> 2026-08-26 19:46:51 (2802 rows @ ~1s)
Sail-configuration coverage: 100.0% of rows have Main/Headsail populated -- confirms this file is race/sailing throughout, no motor segment to exclude (unlike the 2026-08-12 session).

## Methodology note: heading-under-test changed from HDGt to HDGmE
The 2026-08-12 pipeline evaluated `HDGt` directly, because at the time `navigation.headingMagnetic` (and the derived `HDGt`) resolved to the eCompass. That changed 2026-08-19 -- `HDGt` now reflects the fluxgate (`handoffs/fluxgate-heading-source-switch.md`). This script uses `HDGmE` (the `signalk-path-mapper` duplicate of the eCompass's raw heading, added in that same cutover) as the eCompass-under-test column. `HDGt` and `HDGmF` are still evaluated below for context, not as the primary result.

## Known exporter gap -- still present
Raw export `HDGmE`: 393/2802 rows null in the manually-tagged file (partially filled by hand); the programmatic raw export for this same session has it null on all but 1 of 3290 rows. Same gap flagged in the fluxgate handoff (commit `ca6891a`, not yet landed as of this writing there) -- confirm whether that commit has since been pushed/pulled and, if so, whether it actually fixes this (it may need `sensors.ecompass.headingMagnetic` specifically, not a `navigation.headingMagnetic` source filter -- see the handoff's 'Outcome' section, item 3).

## Calibration stability across the session
- Calibration-acceptance events (`MCALF != 0`): 0 (none fired -- clean session)
- `MFIT` (in-use fit error) ranged 7.220% - 7.273% -- tight, but notably higher than the ~3% achieved right after the ADR-013 sensor relocation; worth keeping an eye on across future sessions, not urgent on its own.

## Steady-state filter (eCompass/HDGmE basis, this project's actual subject)
Circular rolling std of `HDGmE` over 21s < 3.0 deg, SOG >= 1.0 kn, frozen-COG rows excluded (below). `HDGmE` missing 393/2802 (14.0%), `COGt` missing 1253/2802 (44.7%) -- COGt's lower population rate (GPS-rate limited) is the main constraint on steady-state sample count, more than the rolling-std filter itself.

**Frozen-COG filter:** 4 of 2802 rows (0.1%) have `COGt`/`SOG` bit-identical to the previous sample -- same GPS pipeline bug documented in the 2026-08-12 session, still present, still small here.
- Steady-state rows retained (HDGmE basis): 744 of 2802

## Heading-bin coverage (30 deg bins, HDGmE basis)
                     mean       std  count
heading_bin_30                            
0               17.115625  2.510527  128.0
30              22.449832  2.579573  297.0
60              21.390909  2.451221   22.0
90              18.882883  2.973974  111.0
120             12.203030  3.257841   66.0
150                   NaN       NaN    NaN
180                   NaN       NaN    NaN
210             -3.395238  2.464037   21.0
240             -8.186275  2.419836   51.0
270             -1.414894  2.119986   47.0
300              2.100000       NaN    1.0
330                   NaN       NaN    NaN

### Thin/missing coverage (< 20 steady samples)
- 150-180 deg: 0 (no steady samples)
- 180-210 deg: 0 (no steady samples)
- 300-330 deg: 1
- 330-360 deg: 0 (no steady samples)

## Context: fluxgate (HDGmF) and system heading (HDGt) vs. COGt
- `HDGmF` vs `COGt`, steady-state: n=870, mean=-8.55 deg, std=10.23 deg
- `HDGt` vs `COGt`, steady-state: n=872, mean=-10.89 deg, std=10.25 deg
Both show substantial heading-dependent structure, similar in spirit to the eCompass result below -- given the strong TWA confound this session (see fit summary), this is consistent with leeway affecting *any* COGt-referenced deviation estimate under sail, not necessarily evidence that the fluxgate itself has comparable deviation to the eCompass. Not a clean read either way from COGt alone this session.

## eCompass vs. fluxgate, direct sensor-to-sensor gap (no COGt/GPS involved)
`HDGmE - HDGmF`, all rows with both present (n=2167): mean=-10.83 deg, std=22.42 deg, range [-45.70, 23.80] deg.
This is independent of COGt/leeway entirely -- a large, heading-varying gap between the two magnetic-heading sensors under sail, over and above whatever the TWA confound is doing to either one's COGt-referenced deviation estimate. New data point, not previously quantified under sail.

## Known issue, per Jeff (post-hoc): GPS malfunction, tack-correlated
GPS had problems live during the race; Jeff power-cycled it mid-session with no
improvement, and manually deleted a large amount of `COGt`/`SOG` (and everything
derived from them) from this file before handing it off -- this is *why* it's
called the "cleaned" file. That deletion is not evenly distributed:

- `COGt`/`SOG` missing on **82.0%** of Port-tagged rows vs. **3.9%** of
  Starboard-tagged rows (`Tack/Gybe` column; n=1454 Port, 1316 Star, 32 Tack).

Jeff's read is a mechanical/electrical connection issue sensitive to heel
direction or antenna geometry, not random GPS noise -- the tack-correlation is
clean enough to support that. Two consequences for the analysis above:

1. **The steady-state fit set (744 rows) ended up 83.9% Starboard / 16.1%
   Port** (624 vs. 120 rows) as a direct result -- not an independent coverage
   gap like 2026-08-12's, but a side effect of this fault. Effectively a
   single-tack measurement this session. See `sailing_deviation_summary_20260826.md`
   for what that means for the fit.
2. Worth a physical inspection focused on what differs mechanically/electrically
   between tacks near the GPS antenna/cable run -- a new, separate item, not
   part of the eCompass/fluxgate work above.

**Wind sensor loss, checked and clean:** `AWS`/`AWA` (and therefore `TWS`/`TWA`)
dropped out at 19:26:21 and stayed cleanly `NaN` afterward -- confirmed no
stale/frozen values masquerading as live data. The TWA-confound fit in
`fit_sailing_deviation_20260826.py` already drops rows with missing `TWA`, so
this was handled correctly without any fix needed; noted here for the record.

**VMG/waypoint data unreliable this session, per Jeff:** the system wasn't
advancing properly from one waypoint to the next, making `VMG`/`VMC`/`TGTA`/
`TGTS`/`TVMG` untrustworthy despite being ~40-60% populated (i.e. this doesn't
show up as a null-rate problem -- the values are just wrong). Not used in this
analysis, but flagging so a future performance/polar pass on this session
knows to exclude or re-derive them.

## Output
Clean steady-state eCompass dataset -> `data/clean_sailing_20260826.csv` (744 rows)
