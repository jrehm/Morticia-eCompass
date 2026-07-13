# eCompass Thermal Drift — Correlation Analysis

Baseline heading (median over full window): 201.310 deg
Smoothing window (residual/temp/wind, to suppress wind-gust wobble): 20min
Samples used (after baseline/dropna): 89972
Temperature range in analysis set: 26.58 - 35.52 C

## Raw linear fit: residual_deg = slope * temp_c + intercept
slope = -1.0211 deg/C, intercept = 30.7068 deg
r = -0.8756, r^2 = 0.7666, p = 0.000e+00
Predicted swing over observed temp range: -9.13 deg

## Lag / cross-correlation (positive lag = temperature leads heading residual)
Best |correlation| at lag = 0 min, r = -0.8756

## Wind-controlled multiple regression: residual ~ temp_c + wind_kn
intercept = 30.2281, temp_coef = -0.9892 deg/C, wind_coef = -0.1005 deg/kn
R^2 = 0.7723  (vs. R^2 = 0.7666 for temp alone)

## Hysteresis check (separate fits for rising vs. falling temperature)
Rising:  slope = -1.0131 deg/C, r^2 = 0.6924, n = 15067
Falling: slope = -1.0399 deg/C, r^2 = 0.6369, n = 17265
Slope difference (rising - falling): 0.0268 deg/C

## Diurnal pattern (hourly mean, UTC hour of day)
      residual     temp_c
hour                     
0    -2.404417  32.258068
1    -1.107934  30.750795
2     0.093274  29.785022
3     1.093991  29.150881
4     1.500653  28.653556
5     1.759941  28.274953
6     2.185464  28.007558
7     2.753056  27.780432
8     2.932841  27.496496
9     3.378833  27.256938
10    3.340003  27.112073
11    2.366584  27.442533
12    1.970090  28.227721
13    1.435854  29.213990
14   -0.565512  30.366725
15   -2.372856  31.486878
16   -2.776736  32.423409
17   -3.153799  33.376845
18   -3.797038  34.121749
19   -4.418143  34.502317
20   -4.411755  34.515499
21   -4.695827  34.310800
22   -4.570640  34.204143
23   -3.275104  33.642076

## Plots written
- plots/diurnal_pattern.png
- plots/hysteresis.png
- plots/lag_correlation.png
- plots/residual_vs_temp.png
- plots/timeseries_overlay.png
