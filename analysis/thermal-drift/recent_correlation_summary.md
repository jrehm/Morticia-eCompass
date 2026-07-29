# eCompass Recent-Window Coefficient Check (2026-07-20/23)

Deployed firmware (v1.3.2) is already applying: slope = -1.0211 deg/C, T_ref = 30.0723 C. `heading_deg` below (navigation.headingCompass) is therefore the *post-correction* output, not raw sensor output.

Baseline heading (median, post-correction): 213.166 deg
Samples used: 150734
Temperature range: 22.95 - 33.60 C

## 1. Post-correction residual vs. temperature
slope = 0.8568 deg/C, intercept = -24.5347 deg
r = 0.8163, r^2 = 0.6663, p = 0.000e+00
A large *positive* slope here (opposite sign to the original pre-correction -1.0211 deg/C fit) is the signature of overcorrection: the firmware is adding back more than the sensor is currently losing to temperature.

## 2. Wind-controlled multiple regression (post-correction residual ~ temp_c + wind_kn)
intercept = -25.7189, temp_coef = 0.9427 deg/C, wind_coef = -0.2026 deg/kn
R^2 = 0.7512  (vs. R^2 = 0.6663 for temp alone)

## 3. Diurnal pattern (hourly mean, UTC hour of day)
      residual     temp_c   wind_kn
hour                               
0     0.623305  29.826772  6.419557
1    -0.192548  28.806370  5.469951
2    -0.244593  28.053291  4.741585
3    -0.564285  27.418748  4.620766
4    -1.016782  27.047300  4.692974
5    -1.548506  26.567980  4.760024
6    -2.049818  26.307062  5.488292
7    -2.204277  26.156909  8.414998
8    -2.004545  25.971479  4.848863
9    -2.270039  25.773711  4.705315
10   -2.345634  25.630623  4.054721
11   -2.151888  25.821283  4.659122
12   -1.492049  26.443042  5.169555
13   -0.900374  27.137909  5.528432
14   -0.302756  28.115400  6.271103
15    0.789435  29.118298  6.988225
16    1.525922  29.935723  7.805520
17    1.852695  30.471083  7.842077
18    1.727106  30.863923  7.791808
19    1.626865  31.074124  8.217730
20    0.807299  31.052024  8.225244
21    1.666250  31.154418  7.933187
22    1.736710  31.102694  7.260342
23    1.094665  30.686350  6.991147

## 4. Reconstructed pre-correction ('raw sensor') signal vs. temperature
Backs out the firmware's applied correction to estimate what the sensor's own output looks like before v1.3.2 compensation, for direct comparison with the original 2026-07-08/13 dockside fit.
Reconstructed raw slope = -0.1643 deg/C (implied T_ref = 27.452 C), r = -0.2610, r^2 = 0.0681
Original dockside fit (analysis/thermal-drift/correlation_summary.md): slope = -1.0211 deg/C, r^2 = 0.7666
Magnitude ratio (this window / original fit): 0.16x

## 5. Wind-controlled regression on the reconstructed raw signal
intercept = 3.3368, temp_coef = -0.0787 deg/C, wind_coef = -0.2025 deg/kn, R^2 = 0.3053
temp/wind collinearity in this window: r = 0.2689
Temperature's own contribution drops sharply once wind is included, while wind picks up a comparable-sized coefficient. Combined with the temp/wind collinearity above, this means the residual measured here may be partly (or mostly) a wind-correlated effect rather than pure sensor thermal drift -- and if the boat has any freedom to swing at the dock/mooring, part of this could be genuine heading change, not sensor error at all. This should be checked (mooring/dockline configuration, rate-of-turn during wind shifts) before trusting a temperature-only refit.

## 6. Synthesis / recommendation
1. The post-correction heading still shows a strong residual-vs-temperature relationship (slope +0.857 deg/C, r^2=0.67), opposite in sign to the original raw fit -- the signature of overcorrection, not undercorrection.
2. Reconstructing the pre-correction raw signal gives a current thermal slope of only -0.164 deg/C (r^2=0.07), about 0.2x weaker than the -1.0211 deg/C, r^2=0.77 relationship the deployed coefficient was fit on -- the coefficient is sized for a much stronger effect than is present now.
3. However, wind is a significant competing/confounding factor here (see section 5) in a way it was not in the original dockside fit -- so before deploying a new fixed slope, recommend: (a) temporarily set slope_deg_per_c=0 via POST /api/thermal/config and watch Grafana to confirm overcorrection is the dominant effect, (b) confirm mooring/dockline configuration didn't allow the boat to swing with wind during this window, (c) only then refit, ideally with wind included in the deployed model rather than temperature alone.

## Plots written
- plots/recent_diurnal_pattern.png
- plots/recent_residual_vs_temp.png
- plots/recent_timeseries_overlay.png
