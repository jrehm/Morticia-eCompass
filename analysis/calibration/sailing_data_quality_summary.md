# Sailing-Configuration Deviation Diagnostic — Data Quality Summary

Source: `sailing_20260812_174500_to_20260812_201500-1hz.csv`
Window: 2026-08-12 17:45:00 -> 2026-08-12 20:14:59 (8993 rows @ ~1s)

**Session segments (per Jeff, approximate clock times):**
                engine     n  sog_mean  sog_std  roll_std  mincl_mean  mincl_std  magb_mean
segment                                                                                    
pre_underway  off_dock   900      0.10     0.06      0.38       63.85       0.21      48.09
motor_out           on  1440      4.82     2.97      0.84       69.26       3.53      48.09
presail            off  2160      5.43     3.58      2.60       67.13       3.17      48.09
race               off  2640     11.31     2.74      7.52       67.98       3.66      48.09
postfinish         off   420      8.72     1.35      1.95       62.98       0.52      48.09
motor_back          on  1433      3.10     3.02      0.58       63.56       2.15      48.09

## Calibration stability across the session
- Calibration-acceptance events (`MCALF != 0`): 0 (none fired -- clean session, no auto-recal confound)
- `MFIT` (in-use fit error) ranged 3.199% - 3.285% -- smooth aging drift only, consistent with no discrete recalibration
- `MAGB` (in-use field magnitude) was constant all session -- expected, since it's a property of the active calibration model, not a live per-sample field reading, and the active calibration never changed (see above)

## Steady-state filter (sailing/engine-up rows only)
Circular rolling std of `HDGt` over 21s < 3.0 deg, and SOG >= 1.0 kn. `HDGt` missing on 1657 of 8993 rows (18.4%) session-wide, dropped before filtering. Rows within 30s of any segment transition are also excluded -- a 3-sample SOG/COG glitch (6-22 kn in 2s, dev_deg to -133) turned up right at the motor-out->presail boundary during development; excluding transition windows removes it on principled grounds (transitions are physically messy generally) rather than an ad hoc outlier rule.

**Frozen-COG filter:** 471 of 8993 rows (5.2%) session-wide have `COGt`/`SOG` bit-identical to the previous sample while `LAT`/`LON` keep updating normally -- a real GPS fix with a stale COG/SOG output, worst during active turns (heading sweeping through 5+ deg while COGt sits frozen), which fabricates large spurious deviation. Excluded from the steady-state set.
- Sailing rows (presail+race+postfinish): 3957
- Steady-state rows retained: 2084 of 3957 (52.7%)

## Heading-bin coverage (30 deg bins, steady-state sailing rows only)
                     mean        std  count
heading_bin_30                             
0               24.752422   2.042442  163.0
30                    NaN        NaN    NaN
60                    NaN        NaN    NaN
90               3.520514   1.876608   43.0
120             -0.509805   1.931951  133.0
150             -2.663518   1.697848   44.0
180             -3.137752  12.174280  885.0
210              2.114535   5.653974   71.0
240             33.521544   9.660907  274.0
270             29.763354   8.427992  405.0
300                   NaN        NaN    NaN
330             27.414203   1.677082   66.0

### Thin/missing coverage (< 20 steady samples)
- 30-60 deg: 0 (no steady samples)
- 60-90 deg: 0 (no steady samples)
- 300-330 deg: 0 (no steady samples)

## Output
Clean steady-state sailing dataset -> `data/clean_sailing.csv` (2084 rows)
