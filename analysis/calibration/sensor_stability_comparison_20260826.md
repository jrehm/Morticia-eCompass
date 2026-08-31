# eCompass vs. Fluxgate — Relative Stability Comparison (2026-08-26)

Prompted by Jeff: including whatever COGt data survived the GPS malfunction (mostly Starboard tack, per `sailing_data_quality_summary_20260826.md`), how do HDGmE and HDGmF compare *to each other*, and which looks more stable/correct? Both carry uncorrected mounting offsets, so this is a same-COG, same-timestamps comparison of internal consistency, not an accuracy verdict against ground truth.

n = 1199 rows with COGt/HDGmE/HDGmF/SOG all present, SOG>=1kn (4 frozen-COG glitch rows excluded, n=1195 used below). Deliberately minimal filtering -- no steady-state rolling-std filter like the main pipeline uses, per Jeff's request to include the available COG data rather than the more conservative subset.

## Raw comparison (no curve fit)
- `COGt - HDGmE`: mean=14.61 deg, std=9.82 deg
- `COGt - HDGmF`: mean=-8.92 deg, std=10.05 deg
Raw std is close between the two -- not very discriminating on its own, since both are dominated by the real heading-locked deviation signal (different for each sensor, since they're physically different sensors in different locations), not noise.

## Heading-only 5-coefficient deviation-curve fit, same rows
Same model used throughout this project (`A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h)`), fit separately to each sensor's own COGt-referenced deviation on the identical 1195 timestamps:
- eCompass (HDGmE basis): R^2 = 0.8268, residual std = 4.083 deg
- Fluxgate (HDGmF basis): R^2 = 0.8519, residual std = 3.866 deg

Fluxgate fits a bit tighter -- higher R^2, lower residual std -- meaning its relationship to COGt is more fully explained by a smooth heading-locked curve, with less left over as scatter.

## Within-heading-bin scatter (30 deg bins, robust bins only, n>=20)
Same idea from a different angle -- how tightly clustered is each sensor's deviation at a fixed heading:

eCompass:
            mean       std  count
bin_E                            
0      18.083249  3.489397    197
30     22.599016  2.682920    305
60     20.096226  4.505721     53
90     18.568273  3.933243    249
120    10.719186  4.653482    172
210     0.467073  6.820848     82
240    -7.227941  3.097078     68
270    -1.722917  2.831828     48
avg within-bin std: 4.002 deg

Fluxgate:
            mean       std  count
bin_F                            
30    -18.755340  2.475160    103
60    -15.866751  2.485374    394
90    -11.666176  3.125848     68
120    -8.694550  2.977341    367
150    -8.002083  5.559025     48
210    12.451701  6.523638    147
270     0.936735  2.262437     49
avg within-bin std: 3.630 deg

## Moment-to-moment jitter (independent of COGt entirely)
21s rolling circular std of each raw heading signal, same timestamps (own-signal noise, nothing to do with COG or deviation):
- eCompass: mean=4.166 deg, median=2.279 deg
- Fluxgate: mean=3.999 deg, median=2.367 deg
Essentially a wash on this metric -- mean slightly favors the fluxgate, median slightly favors the eCompass, neither by much. The two sensors' moment-to-moment noise floor looks similar; the gap shows up specifically in how well each one's relationship to COGt is explained by a clean curve, not in raw jitter.

## Verdict
Modest, consistent edge to the **fluxgate** on every metric that involves COGt (fit R^2, residual std, within-bin std) -- roughly 5-10% tighter across the board, not a dramatic gap. Both sensors show clean, well-behaved deviation curves (R^2 > 0.8 for both) -- this isn't "one sensor is garbage," it's "both are internally consistent, the fluxgate slightly more so." Consistent with, though not a dramatic confirmation of, the decision to make the fluxgate primary.

**Caveats:** (1) both curves are built against the *same* COGt, so whatever leeway/TWA confound and Starboard-tack skew is in that reference (see `sailing_data_quality_summary_20260826.md` and `sailing_deviation_summary_20260826.md`) affects both sensors identically -- fair for a head-to-head comparison, but neither R^2 should be read as "accuracy against true heading." (2) Single session, heavily Starboard-tack-skewed as a side effect of which COG data survived the GPS malfunction -- not a claim about behavior across the full heading circle or on Port tack specifically.

## Plot
- `plots/sensor_vs_cog_comparison.png`
