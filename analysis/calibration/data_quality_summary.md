# Motoring-Configuration Deviation Diagnostic — Data Quality Summary

Source: `sailing_20260810_153000_to_20260810_171000.csv`
Window: 2026-08-10 15:40:00 -> 2026-08-10 17:09:59 (5400 rows @ ~1Hz)

**Collection conditions (per Jeff):** engine running, engine tilted down and ~18in aft of its sailing position. ~5cm/s N->S current (Great Lakes, negligible at this boat speed). Leeway under power treated as negligible. COGt is therefore used as a heading reference for this diagnostic only -- this assumption does NOT hold for sailing data, where leeway is real.

## Raw data quality
- `HDGt` missing: 1011 of 5400 rows (18.7%)
- `HDGt` dropout events (gap starts): 930
- Rows with both `HDGt` and `COGt` present: 4322

## Steady-state filter
Circular rolling std of `HDGt` over 21s < 3.0 deg, and SOG >= 1.0 kn (COG unreliable below this). `ROT` was NOT used for this filter -- known ~60x scaling bug in the Signal K pipeline, not yet fixed.
- Steady-state rows retained: 2937 of 4322 valid rows (68.0%)

## Heading-bin coverage (30 deg bins, steady-state rows only)
                     mean       std  count
heading_bin_30                            
0               30.098256  2.088114   27.0
30              14.529638  2.015525  119.0
60                    NaN       NaN    NaN
90             -16.465416  3.627589  424.0
120            -20.945525  3.264768  434.0
150            -16.292957  3.641949  143.0
180             -1.544902  9.782497  437.0
210             18.171166  7.829084  409.0
240             32.008988  8.309261  204.0
270             51.649252  2.762828  242.0
300             49.221080  4.186830  338.0
330             36.402353  3.178258  160.0

### Thin/missing coverage (< 20 steady samples)
- 60-90 deg: 0 (no steady samples)

## Output
Clean steady-state dataset -> `data/clean_motoring.csv` (2937 rows)
