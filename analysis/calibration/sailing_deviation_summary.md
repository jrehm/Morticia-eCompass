# Sailing-Configuration Deviation — Fit Summary (PRELIMINARY)

**Preliminary, not the final table.** Single race session, engine up/forward (matches the original `magfit` position). Coverage gaps at 30-90 deg and 300-330 deg (see `sailing_data_quality_summary.md`), and a real TWA confound (below) mean this needs more sessions across different wind directions before it's a deployment candidate. See `morticia-project/handoffs/heading-deviation-table-investigation.md`.

## TWA confound check
- `dev_deg` vs. `TWA`, before any fit: r = -0.681
- Residual vs. `TWA`, after the naive heading-only fit: r = 0.021

That's a real correlation, much stronger than anything seen in the motoring data (where tack-independence was the whole argument for trusting COGt as heading). It means a meaningful part of the naive `sailing_naive_deg` curve below is wind-angle-linked (leeway, or something else that tracks TWA), not pure heading-locked compass deviation, and a single race course does not vary TWA independently of heading enough to cleanly separate the two (each leg tends to hold both roughly constant together).

**Important:** the residual-vs-TWA correlation drops to ~0 *after* the heading-only fit -- but that is NOT evidence the confound is resolved. It's the expected signature of heading and TWA being collinear in a single session (each leg pins both together), which means the heading-only model can silently absorb TWA-driven variation into its heading terms rather than leaving it in the residual where it would be visible. The near-zero residual correlation is consistent with the confound being unresolvable from this session alone, not with it being absent. Only more sessions that revisit the same headings at different TWA (different wind directions) can actually break this collinearity.

## Two fits
1. **Naive** — same 5-coefficient heading-only model as the motoring curve. R^2 = 0.7446. Confounded with TWA per above.
2. **Heading + TWA** — adds a simple linear TWA term (`dev = A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h) + F*TWA`) as a transparent proxy for wind-angle-linked error, not a rigorous leeway model. R^2 = 0.7483 (vs. 0.7446 without TWA). TWA coefficient F = 0.0852 deg/deg. The heading-only component of this fit (columns A-E) is the closer-to-clean estimate of actual deviation, but still built on one session's worth of heading/TWA combinations.

## Comparison to the motoring curve
Motoring curve (2026-08-10, refit here for a same-basis comparison): R^2 = 0.9740.

 heading_deg  sailing_naive_deg  sailing_heading_component_deg  motoring_deg
           0              23.87                          36.51         33.25
          30              27.58                          35.87         17.19
          60              29.48                          29.90          1.28
          90              21.73                          14.63        -11.87
         120               5.24                          -5.55        -19.81
         150              -9.37                         -19.33        -19.88
         180             -10.85                         -17.42        -10.41
         210               2.35                          -0.66          7.15
         240              20.51                          20.57         27.55
         270              31.42                          34.99         43.67
         300              31.00                          39.05         50.12
         330              25.55                          37.56         45.70

The two curves do not resemble each other in shape or magnitude at the headings both cover — consistent with the engine-position hypothesis (different physical configuration, different hard-iron picture), though this single sailing session isn't a clean enough comparison to call that confirmed.

## Plots
- `plots/sailing_vs_motoring_deviation.png` — sailing raw/binned/fit vs. motoring fit
- `plots/sailing_deviation_twa_confound.png` — residual vs. TWA, colored by heading
