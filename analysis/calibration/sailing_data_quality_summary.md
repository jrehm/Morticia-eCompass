# Sailing-Configuration Deviation Diagnostic — Data Quality Summary

Source: `sailing_20260812_174500_to_20260812_201500.csv`
Window: 2026-08-12 17:45:10 -> 2026-08-12 20:15:00 (900 rows @ ~10s)

**Session segments (per Jeff, approximate clock times):**
                engine    n  sog_mean  sog_std  roll_std  mincl_mean  mincl_std  magb_mean
segment                                                                                   
pre_underway  off_dock   89      0.10     0.03      0.35       63.84       0.20      48.09
motor_out           on  144      4.79     2.97      0.67       69.20       3.55      48.09
presail            off  216      5.42     3.43      2.43       67.04       3.09      48.09
race               off  264     11.30     2.71      7.42       68.05       3.63      48.09
postfinish         off   42      8.78     1.29      1.76       62.97       0.48      48.09
motor_back          on  144      3.13     3.02      0.57       63.55       2.13      48.09

## Calibration stability across the session
- Calibration-acceptance events (`MCALF != 0`): 0 (none fired -- clean session, no auto-recal confound)
- `MFIT` (in-use fit error) ranged 3.199% - 3.285% -- smooth aging drift only, consistent with no discrete recalibration
- `MAGB` (in-use field magnitude) was constant all session -- expected, since it's a property of the active calibration model, not a live per-sample field reading, and the active calibration never changed (see above)

## Steady-state filter (sailing/engine-up rows only)
Circular rolling std of `HDGt` over 21s < 3.0 deg, and SOG >= 1.0 kn.
- Sailing rows (presail+race+postfinish): 522
- Steady-state rows retained: 282 of 522 (54.0%)

## Heading-bin coverage (30 deg bins, steady-state sailing rows only)
                     mean        std  count
heading_bin_30                             
0               24.161627   1.358767   15.0
30                    NaN        NaN    NaN
60                    NaN        NaN    NaN
90               2.800630   2.041483   10.0
120             -0.595924   1.430823   17.0
150             -2.951883   0.957021   12.0
180             -4.035242  12.751151  116.0
210              4.765309   2.898335   11.0
240             34.588697   9.664967   37.0
270             26.909653  15.942122   58.0
300                   NaN        NaN    NaN
330             27.297817   0.720884    6.0

### Thin/missing coverage (< 20 steady samples)
- 0-30 deg: 15
- 30-60 deg: 0 (no steady samples)
- 60-90 deg: 0 (no steady samples)
- 90-120 deg: 10
- 120-150 deg: 17
- 150-180 deg: 12
- 210-240 deg: 11
- 300-330 deg: 0 (no steady samples)
- 330-360 deg: 6

## Output
Clean steady-state sailing dataset -> `data/clean_sailing.csv` (282 rows)
