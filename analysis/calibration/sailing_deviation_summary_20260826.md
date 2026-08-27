# 2026-08-26 Race Session — eCompass Deviation Fit Summary (PRELIMINARY)

**Preliminary, not the final table — and more limited than a first read suggests.** Second sailing-mode session (after 2026-08-12). Fit against `HDGmE` (eCompass raw heading), not `HDGt` -- see `clean_sailing_data_20260826.py` docstring for why that changed. Coverage gaps at 150-210 deg and 330-360 deg this session (different from 2026-08-12's 30-90/300-330 gaps -- together the two sessions are filling in different parts of the circle, still not the full 12 headings from either alone). TWA confound (below) is, if anything, stronger than 2026-08-12's.

**Bigger caveat, discovered after the first pass:** a tack-correlated GPS malfunction during the race (see `sailing_data_quality_summary_20260826.md`) meant Jeff had to delete `COGt`/`SOG` on 82% of Port-tack rows vs. 3.9% of Starboard -- so the 744-row fit set below is 83.9% Starboard / 16.1% Port. This isn't just another coverage gap; it means the curve below is close to a single-tack measurement, and if there's any tack-asymmetric leeway (plausible given the trimaran's foils), it's baked into the curve with no way to separate it out this session. Treat the numbers below as "Starboard tack, this session" rather than as a general deviation estimate.

n dropped for missing TWA: 180 of 744

## TWA confound check
- `dev_deg` vs. `TWA`, before any fit: r = 0.734
- Residual vs. `TWA`, after the naive heading-only fit: r = -0.013

Raw correlation (r=0.734) is comparable in strength to 2026-08-12's (r=-0.68), same underlying issue: a single race course doesn't vary TWA independently of heading, so this session alone still can't cleanly separate real eCompass deviation from leeway. Two sessions now showing the same confound, from different course/wind combinations -- useful confirmation the problem is real and structural, not session-specific, but doesn't yet resolve it (that needs comparing the *same heading bins* across sessions with different TWA at that heading, not just stacking more single-session fits).

## Two fits
1. **Naive** — heading-only 5-coefficient model. R^2 = 0.9099. Confounded with TWA per above.
2. **Heading + TWA** — adds a linear TWA term. R^2 = 0.9137 (vs. 0.9099 without TWA). TWA coefficient F = -0.1457 deg/deg.

## Comparison to prior sessions
- 2026-08-12 sailing (HDGt, back when HDGt meant the eCompass): R^2 = 0.7457
- 2026-08-10 motoring (diagnostic only): R^2 = 0.9740

 heading_deg  sailing_20260826_naive_deg  sailing_20260826_heading_component_deg  sailing_20260812_deg  motoring_20260810_deg
           0                        6.29                                   29.12                 23.97                  33.25
          30                       19.15                                   38.74                 27.48                  17.19
          60                       23.31                                   36.09                 29.22                   1.28
          90                       20.76                                   28.00                 21.45                 -11.87
         120                       17.44                                   21.56                  5.07                 -19.81
         150                       16.35                                   17.32                 -9.41                 -19.88
         180                       14.66                                   10.31                -10.85                 -10.41
         210                        7.60                                   -2.51                  2.31                   7.15
         240                       -5.07                                  -16.55                 20.44                  27.55
         270                      -16.84                                  -21.93                 31.41                  43.67
         300                      -19.32                                  -12.28                 31.10                  50.12
         330                       -9.71                                    8.64                 25.72                  45.70

The 2026-08-26 curve does not resemble either prior curve closely in the headings where more than one session has coverage -- with two confounded, coverage-gapped sessions and a sensor whose fit error has drifted from ~3% to ~7% since relocation, this is genuinely inconclusive on its own, not a sign any particular prior curve was wrong. More sessions, specifically ones that revisit already-covered headings under different wind, are what would actually start to resolve this.

## eCompass vs. fluxgate: the bigger new finding this session
Independent of all of the above (no COGt/leeway involved at all): `HDGmE` and `HDGmF` (fluxgate raw) disagree by up to ~46 deg at times this session, varying with heading rather than sitting at a fixed offset -- see `sailing_data_quality_summary_20260826.md`. Since the fluxgate is now the trusted live heading source, this bounds how far off the eCompass may currently be running in absolute terms, separately from anything this deviation-table exercise is trying to measure via COGt.

## Plots
- `plots/sailing_20260826_vs_prior_deviation.png`
- `plots/sailing_20260826_twa_confound.png`
