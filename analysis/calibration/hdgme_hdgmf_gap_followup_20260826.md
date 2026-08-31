# HDGmE vs. HDGmF Gap — Roll/Time Follow-up (2026-08-26)

Prompted by Jeff: is the eCompass-vs-fluxgate gap (`sailing_data_quality_summary_20260826.md`) related to roll/heel, and is there a real convergence over the race? Short answer to both: partially, and it's tangled with the same heading/tack collinearity already seen in the TWA confound -- not a clean single-cause story.

## Roll/heel
- Combined both tacks: corr(diff, ROLL) = 0.814, R^2 (linear) = 0.663
- Tack alone (Port vs. Star, no ROLL) already explains R^2 = 0.717
- ROLL + tack together: R^2 = 0.736 (coefs: A=-25.34, ROLL=0.900 deg/deg, is_port=26.21)

Adding ROLL on top of tack barely improves the fit (0.717 -> 0.736) -- most of the apparent "roll effect" is roll and the gap both independently tracking tack/heading, not a direct roll -> gap relationship. Point-of-sail breakdown reinforces this: Reach legs show the *largest* mean gap despite the *lowest* mean roll of any point of sail, while Beat legs have the highest roll but only a middling gap:

             mean_absroll  mean_absdiff    n
PointOfSail                                 
Beat             8.932365     20.727856  998
Gybe             4.111111     29.722222    9
Reach            4.140636     36.596466  283
Run              4.312583     18.452649  604

Within-tack fits (roll only, same tack):
- Port: n=974, corr=0.691, slope=3.215 deg/deg, R^2=0.478
- Star: n=894, corr=-0.502, slope=-1.099 deg/deg, R^2=0.252

**Read:** a real heel-dependent effect ("heeling error" is a well-known classical compass-adjustment phenomenon -- heel changes how a magnetometer sits relative to nearby iron and to the field itself) is a live hypothesis, but this session's heel, tack, and heading are too collinear to isolate it -- same structural problem as the TWA confound, different variable. A controlled test (vary heel at a fixed heading -- e.g. crew weight shift at the dock, or rocking the boat by hand while holding a steady compass heading) is the only clean way to actually separate this, the same way the planned engine-position test was meant to isolate that effect from heading.

## Apparent convergence over the race
- corr(|diff|, elapsed_min) = -0.733 -- real downward trend, ~40 deg early to ~5-10 deg by the end.
- **Ruled out: eCompass calibration improving.** `MFIT` vs. elapsed time: corr = 1.0000 (essentially a straight line, 7.220% -> 7.273%) -- that's the known ~1%/24h aging drift from the auto-recal library (see `Morticia-eCompass/docs/magcal-heading-jump-2026-08-11-handoff.md`), not an improving fit, and zero calibration-acceptance events fired all session. Whatever is shrinking the gap, it is not the eCompass's own calibration getting better in real time.
- The |diff| trace dips sharply near what look like tack transitions (near-zero heel passing through the tack) and plateaus on each new tack, with the plateaus themselves trending down. Point-of-sail sequence this race: Run/Reach (first ~12 min) -> Beat (~15-38 min) -> Run (last ~10 min) -- consistent with *part* of the decline, but not all of it: the gap keeps declining across five consecutive Beat-tagged segments alone (28 -> 21 -> 19 -> 18 -> 17.6 deg), so point-of-sail isn't the whole story either.
- **Not resolved by this session.** Best candidates not yet checked: wind easing over the evening (lower average heel/loading generally, independent of point-of-sail tag), or crew/gear weight distribution settling near the sensors as the race went on. Worth a look at `environment.wind.speedTrue` (TWS) trend and crew positioning notes if this comes up again.

## Plots
- `plots/hdgme_hdgmf_vs_roll.png`
- `plots/hdgme_hdgmf_vs_time_and_mfit.png`
