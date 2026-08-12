# Motoring-Configuration Deviation — Fit Summary (DIAGNOSTIC ONLY)

**Not a firmware deliverable.** Engine was down and ~18in aft of its sailing position during collection -- a different hard-iron configuration than the original magfit calibration (engine up/forward). This curve characterizes deviation *in the motoring configuration* and exists to (a) validate the analysis pipeline against a case with a trustworthy heading reference, and (b) support the engine-position hypothesis for why today's data differs so much from the previously-logged 6-18 deg estimate. See `data_quality_summary.md` for data-quality detail.

## Model
`deviation(heading) = A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h)`
(constant + semicircular + quadrantal terms -- the standard maritime deviation-curve form.)

- A (constant) = 13.662 deg
- B, C (semicircular) = -27.769, 21.829 deg
- D, E (quadrantal) = -0.428, -2.242 deg
- R^2 = 0.9740  (n=2937)

## Residual checks
- residual vs. SOG: r = -0.149
- residual vs. ROLL: r = 0.044 (n=2606 of 2937; 331 rows missing ROLL)
(Both near zero is expected/good -- means the fitted curve is capturing essentially all of the heading-locked signal, with nothing obviously left over that tracks boat speed or heel.)

## 12-point table (every 30 deg, from the fitted curve)
 heading_deg  deviation_deg
           0          33.25
          30          17.19
          60           1.28
          90         -11.87
         120         -19.81
         150         -19.88
         180         -10.41
         210           7.15
         240          27.55
         270          43.67
         300          50.12
         330          45.70

## Plots
- `plots/motoring_deviation_curve.png` -- raw scatter, binned means, fitted curve
- `plots/motoring_deviation_residuals.png` -- residuals after the fit
