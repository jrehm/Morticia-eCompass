# eCompass Thermal Drift — Algorithm Validation (Phase 4)

Fixed coefficients under test: slope = -1.0211 deg/C, T_ref = 30.0723 C

## A. Full-dataset backtest (raw 5s samples, not smoothed)
### Full window
n = 89936
residual std:  before = 3.499 deg, after = 2.078 deg (40.6% reduction)
corr with temp: before r = -0.8046 (r^2=0.6474), after r = 0.0129 (r^2=0.0002)

## B. Chronological train/test split (80/20)
Train: 2026-07-08 00:00:00+00:00 -> 2026-07-12 04:56:35+00:00 (n=71948)
Test:  2026-07-12 04:56:40+00:00 -> 2026-07-13 05:59:55+00:00 (n=17988)
Refit on train: slope = -1.0541 deg/C, T_ref = 29.9361 C (vs. full-window fit: -1.0211 deg/C, 30.0723 C)

### Test set, using train-fitted coefficients
n = 17988
residual std:  before = 3.061 deg, after = 1.928 deg (37.0% reduction)
corr with temp: before r = -0.7993 (r^2=0.6389), after r = 0.2996 (r^2=0.0898)

### Test set, using Phase 3 fixed coefficients (for comparison)
n = 17988
residual std:  before = 3.061 deg, after = 1.902 deg (37.9% reduction)
corr with temp: before r = -0.7993 (r^2=0.6389), after r = 0.2539 (r^2=0.0645)

## C. Known WiFi-reconnect artifact window (2026-07-08 11:33:30-12:05, excluded from Phases 1-2)
n = 1776
Raw heading range in window: 193.35 - 320.02 deg (peak swing 126.67 deg)
Temperature range in window: 27.84 - 28.80 C (span 0.960 C)
Correction applied: min -2.279 deg, max -1.299 deg, range 0.980 deg
Corrected heading range: 191.07 - 317.74 deg (peak swing 126.67 deg)

Interpretation: temperature barely moves during this window, so the correction applied is nearly constant (small range above) -- it does not meaningfully reshape the anomaly. This confirms the thermal correction is inert during a non-thermal (WiFi-reconnect) event, as expected; it is not designed to and does not mask/fix that separate failure mode.

## D. Literal firmware formula cross-check (radians/Kelvin, exact main.cpp constants)
slope_rad_per_k = -0.017822, ref_k = 303.222
corrected = heading_rad - slope_rad_per_k * (temp_k - ref_k)
### Full window, firmware-literal formula
n = 89936
residual std:  before = 3.499 deg, after = 2.078 deg (40.6% reduction)
corr with temp: before r = -0.8046 (r^2=0.6474), after r = 0.0129 (r^2=0.0002)

Matches section A's degrees-based result (2.078 deg std, r^2 ~0.0002), confirming the unit conversions in the firmware formula are correct, not just the deg/C version used for exploration above.

