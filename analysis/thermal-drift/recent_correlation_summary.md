# eCompass Recent-Window Coefficient Check (2026-07-20/23)

Deployed firmware (v1.3.2) is already applying: slope = -1.0211 deg/C, T_ref = 30.0723 C. `heading_deg` below (navigation.headingCompass) is therefore the *post-correction* output, not raw sensor output.

Baseline heading (median, post-correction): 212.257 deg
Samples used: 50954
Temperature range: 22.95 - 32.64 C

## 1. Post-correction residual vs. temperature
slope = 0.8250 deg/C, intercept = -23.3787 deg
r = 0.8544, r^2 = 0.7301, p = 0.000e+00
A large *positive* slope here (opposite sign to the original pre-correction -1.0211 deg/C fit) is the signature of overcorrection: the firmware is adding back more than the sensor is currently losing to temperature.

## 2. Wind-controlled multiple regression (post-correction residual ~ temp_c + wind_kn)
intercept = -25.3155, temp_coef = 0.9578 deg/C, wind_coef = -0.2234 deg/kn
R^2 = 0.7761  (vs. R^2 = 0.7301 for temp alone)

## 3. Diurnal pattern (hourly mean, UTC hour of day)
      residual     temp_c    wind_kn
hour                                
0     0.951143  29.440673   7.645572
1    -0.052941  28.493928   6.783400
2    -0.650434  27.766314   6.604808
3    -1.634724  27.132063   7.148715
4    -2.085520  26.551071   7.199001
5    -2.137945  26.037224   7.643224
6    -2.203810  25.739619   7.441887
7    -1.835681  25.552861   7.165682
8    -1.666075  25.375218   6.292132
9    -2.246448  25.187034   7.214700
10   -2.784641  24.977756   5.914902
11   -2.634937  25.057507   6.916672
12   -1.836216  25.740299   7.269102
13   -1.161983  26.278486   7.121693
14   -0.699788  27.273178   8.137221
15    0.817709  28.189556   7.942638
16    1.334897  28.995577   8.881965
17    1.783524  29.710248   9.592670
18    1.310936  30.263057   9.327735
19    0.986344  30.466782   9.957227
20    0.055005  30.659794  10.107152
21    2.081888  30.972622   9.128675
22    1.922801  30.967929   9.175391
23    0.983567  30.316528   8.399999

## 4. Reconstructed pre-correction ('raw sensor') signal vs. temperature
Backs out the firmware's applied correction to estimate what the sensor's own output looks like before v1.3.2 compensation, for direct comparison with the original 2026-07-08/13 dockside fit.
Reconstructed raw slope = -0.1958 deg/C (implied T_ref = 26.665 C), r = -0.3639, r^2 = 0.1324
Original dockside fit (analysis/thermal-drift/correlation_summary.md): slope = -1.0211 deg/C, r^2 = 0.7666
Magnitude ratio (this window / original fit): 0.19x

## 5. Wind-controlled regression on the reconstructed raw signal
intercept = 3.2869, temp_coef = -0.0627 deg/C, wind_coef = -0.2244 deg/kn, R^2 = 0.2821
temp/wind collinearity in this window: r = 0.5387
Temperature's own contribution drops sharply once wind is included, while wind picks up a comparable-sized coefficient. Combined with the temp/wind collinearity above, this means the residual measured here may be partly (or mostly) a wind-correlated effect rather than pure sensor thermal drift -- and if the boat has any freedom to swing at the dock/mooring, part of this could be genuine heading change, not sensor error at all. This should be checked (mooring/dockline configuration, rate-of-turn during wind shifts) before trusting a temperature-only refit.

## 6. Synthesis / recommendation
1. The post-correction heading still shows a strong residual-vs-temperature relationship (slope +0.825 deg/C, r^2=0.73), opposite in sign to the original raw fit -- the signature of overcorrection, not undercorrection.
2. Reconstructing the pre-correction raw signal gives a current thermal slope of only -0.196 deg/C (r^2=0.13), about 0.2x weaker than the -1.0211 deg/C, r^2=0.77 relationship the deployed coefficient was fit on -- the coefficient is sized for a much stronger effect than is present now.
3. However, wind is a significant competing/confounding factor here (see section 5) in a way it was not in the original dockside fit -- so before deploying a new fixed slope, recommend: (a) temporarily set slope_deg_per_c=0 via POST /api/thermal/config and watch Grafana to confirm overcorrection is the dominant effect, (b) confirm mooring/dockline configuration didn't allow the boat to swing with wind during this window, (c) only then refit, ideally with wind included in the deployed model rather than temperature alone.

## Plots written
- plots/recent_diurnal_pattern.png
- plots/recent_residual_vs_temp.png
- plots/recent_timeseries_overlay.png
