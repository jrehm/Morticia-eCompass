# eCompass New-Location Check (2026-07-30 onward)

Relocated sensor (~3ft from SensESP/battery, twisted-pair I2C, ADR-013). Dockside, low wind, only line-stretch movement. `heading_deg` below is `navigation.headingCompass` -- if `slope_deg_per_c` was reset to 0, this is the sensor's raw (uncorrected) output; section 4 checks that.

Window: 2026-07-30 13:00:00+00:00 -> 2026-08-01 10:40:15+00:00
Baseline heading (median): 201.706 deg
Samples used: 32884
Heading range: 196.40 - 205.92 deg (span 9.52 deg)
Temperature range: 22.95 - 37.44 C

## 1. Heading residual vs. temperature
slope = -0.1695 deg/C, intercept = 5.0060 deg
r = -0.6241, r^2 = 0.3895, p = 0.000e+00

## 2. Wind-controlled multiple regression (residual ~ temp_c + wind_kn)
intercept = 5.6681, temp_coef = -0.2024 deg/C, wind_coef = 0.0940 deg/kn
R^2 = 0.4008  (vs. R^2 = 0.3895 for temp alone)
temp/wind collinearity: r = 0.7513

## 3. Diurnal pattern (hourly mean, UTC hour of day)
      residual     temp_c   wind_kn
hour                               
0     0.739373  30.845249  2.310867
1     1.008722  28.741881  3.555961
2     1.409541  27.333445  3.204039
3     1.360809  26.510698  3.362223
4     1.217736  26.376811  2.166235
5     1.226881  26.034840  0.972494
6     0.606558  25.477526  1.420624
7     0.652150  25.341654  1.852007
8     0.769782  24.965422  2.091154
9     1.093512  24.576828  1.025678
10    0.199340  24.053343  2.164521
11   -0.304280  23.326083  1.056214
12   -0.858852  26.750739  1.192339
13   -1.599686  29.471739  3.098870
14   -1.705880  32.969360  3.488589
15   -1.364270  35.267667  4.850465
16   -1.693138  35.947868  5.659572
17   -1.779484  36.424214  6.300502
18   -1.429185  36.871003  6.344662
19   -0.826095  36.446540  6.383240
20   -0.929054  36.172079  6.399989
21   -1.114142  35.810852  5.794537
22   -0.719091  34.577572  5.461444
23    0.123628  33.040610  3.961599

## 4. Sanity check: is a firmware thermal correction still active?
If `slope_deg_per_c` was successfully reset to 0, `heading_deg` here is raw sensor output, and section 1's slope (-0.1695 deg/C) is the sensor's actual current thermal sensitivity -- not a residual after correction.
For reference, the OLD location's fits were -1.0211 deg/C (original, r^2=0.77) and -0.164 deg/C (9-day recheck, r^2=0.07), both against a sensor 3cm from the SensESP PCB. If this window's slope is nowhere near -1.0 deg/C in magnitude, that's consistent with either the reset having been applied, or the new location genuinely having little thermal sensitivity (both are plausible and not mutually exclusive) -- this can't fully distinguish the two without checking `GET /api/thermal/config` directly.

## 5. Synthesis
1. Residual-vs-temperature slope at the new location: -0.1695 deg/C, r^2=0.3895.
2. Wind-controlled: temp_coef=-0.2024 deg/C, wind_coef=0.0940 deg/kn, R^2=0.4008, temp/wind collinearity r=0.7513.
3. Jeff reports the boat has been dockside, low wind, only line-stretch movement during this window -- so unlike the prior 9-day check, wind-driven boat swing is less likely to be a major confound here, making this a cleaner test of temperature alone, if the sample is large/varied enough in temperature range.

## Plots written
- plots/newloc_diurnal_pattern.png
- plots/newloc_residual_vs_temp.png
- plots/newloc_timeseries_overlay.png
