# Cross-Session Gap Fit v2 — Raw Exports, Fix-Quality Filtering, Thermal Term (2026-09-06)

**Supersedes §2 of `hdgme_hdgmf_crosssession_20260905.md`.** Same question, better inputs:
both sessions now from raw exports at exporter 0.7.0 (08-26 previously came from an Excel
working copy), full underway windows instead of narrow slices, GPS rows filtered on actual
fix quality, and die temperature available so the thermal term can be tested rather than
assumed away.

Script: `fit_gap_crosssession_v2.py`. Data: `sailing_2026{0826,0902}_18*_to_*_203000.csv`
at `Morticia-eCompass@47f550c`.

## Headline

The thermal term is real, and it does something specific and convincing: **it makes the
dominant coefficient agree between sessions almost exactly.** But the honest cross-session
agreement is *worse* than the 09-05 pass reported, and that earlier number should not be
quoted.

## Cleaning

`SATS >= 6` and `0 < HDOP <= 5`, applied on top of underway + both-compasses-present.

| step | 08-26 | 09-02 |
|---|---|---|
| all rows | 8991 | 9000 |
| underway (>500 m from dock) | 6627 (74%) | 5631 (63%) |
| both compasses non-null | 5140 (57%) | 4320 (48%) |
| `SATS>=6` | **3341 (37%)** | **3294 (37%)** |
| `0<HDOP<=5` | 3341 | 3294 |

The fix-quality filter is expensive — it removes 35% of compass-paired rows on 08-26 and
24% on 09-02 — but it is removing rows where the velocity solution is genuinely stale, not
rows that merely look repetitive. `HDOP` adds nothing beyond `SATS`; the two are redundant
here, so `SATS` alone is a sufficient filter.

Session conditions, post-clean:

| | TWD (circ. mean) | ETEMP range | ETEMP median |
|---|---|---|---|
| 08-26 | 187° | 24.0–32.6 °C | 26.9 °C |
| 09-02 | 251° | 29.8–38.4 °C | 32.6 °C |

The sessions differ by 64° in wind direction **and 5.7 °C in median die temperature**,
straddling the TCO model's 30.4 °C reference. Both differences are uncontrolled in a
heading-only fit.

## Model selection (RMS residual, degrees)

| k | thermal | 08-26 | 09-02 |
|---|---|---|---|
| 1 | no | 6.04 | 9.75 |
| 1 | yes | 5.59 | 8.00 |
| 2 | no | 4.99 | 7.27 |
| 2 | **yes** | **4.86** | **6.63** |
| 3 | no | 4.97 | 7.09 |
| 3 | yes | 4.81 | 6.23 |

The thermal term helps at every order, and more on the warmer session — as it should if it
is capturing something physical. k=3 buys little over k=2; k=2 + thermal is the sensible
stopping point.

## The result worth noting

k=2 coefficients, without and with the thermal term:

| | 08-26 | 09-02 | apart |
|---|---|---|---|
| **heading only** | | | |
| A | −11.34 | −7.82 | 3.5 |
| sin H | −25.14 | −31.30 | **6.2** |
| cos H | −8.69 | −10.81 | 2.1 |
| sin 2H | 5.03 | 9.65 | 4.6 |
| **+ thermal** | | | |
| A | −8.92 | −8.40 | 0.5 |
| sin H | **−29.20** | **−29.09** | **0.11** |
| cos H | −6.92 | −12.60 | 5.7 |
| sin 2H | 4.64 | 8.36 | 3.7 |
| dT | 0.51 | 0.84 | — |
| dT·sin H | −0.87 | −1.40 | — |

`sin H` is the dominant term at roughly −29°. Fitted independently on two sessions a week
apart, at different wind directions and different temperatures, adding a thermal term brings
them from 6.2° apart to **0.11° apart**. The `dT` and `dT·sin H` terms agree in sign and
rough magnitude across both.

That is a meaningful result: it says a large part of what looked like session-to-session
disagreement in the semicircular term was temperature, not noise and not TWA.

`cos H` moves the wrong way (2.1° apart → 5.7°), and `sin 2H` stays ~4° apart. So this is
not a clean win across the board — the quadrantal structure is still not consistent between
sessions.

## Cross-validation — and a correction to the 09-05 numbers

Fit on one session, predict the other:

| thermal | fit on | predict | bias | RMS |
|---|---|---|---|---|
| no | 08-26 | 09-02 | +5.15 | 10.54 |
| no | 09-02 | 08-26 | −1.39 | 7.58 |
| **yes** | 08-26 | 09-02 | +2.41 | **8.85** |
| **yes** | 09-02 | 08-26 | −1.15 | **6.42** |

The thermal term improves both directions. But **these are worse than the 5.30/6.30 RMS
reported on 09-05**, and the earlier figures should be treated as optimistic artifacts of
narrow windows: that pass used a 50-minute slice of 09-02 and an Excel copy of 08-26, both
of which sampled a narrower range of conditions than the full sessions do.

**What this means for the collinearity claim.** The 09-05 conclusion — that the
heading/TWA confound is broken by cross-session agreement — still holds directionally:
biases are small (1–2° with thermal), the dominant coefficient now agrees to 0.11°, and
pooled residual correlations are all negligible (TWA −0.066, ROLL −0.106, ETEMP −0.000,
MROT −0.011). But the residual scatter is 6.4–8.9° out of sample, not 5–6°. A table deployed
from this would carry that error. It is not yet good enough to deploy.

## Pooled fit

| | RMS | n |
|---|---|---|
| k=2, heading only | 6.96 | 6635 |
| k=2 + thermal | **6.07** | 6635 |

Pooled thermal coefficients: `A=−8.15, sinH=−29.52, cosH=−10.54, sin2H=7.28, cos2H=2.35,
dT=0.74, dT·sinH=−1.08, dT·cosH=0.07`.

## What is now the binding constraint

Not collinearity — coverage. Pooled residual σ by heading bin:

| heading | n | resid σ |
|---|---|---|
| 0–30° | 82 | **12.62** |
| 150–180° | 637 | 8.12 |
| 30–60° | 370 | 7.33 |
| 240–270° | 164 | 5.71 |
| (best bins) 270–330° | 867 | ~4.6 |

The 0–30° bin has 82 samples pooled across both sessions and σ 12.6°. 240–270° has 164.
These are the bins a race course rarely visits, and no amount of additional racing at
similar wind directions will fill them efficiently.

**This is the argument for the powered swing circle.** Two slow 360s in flat water visit
every bin evenly, under power where COG is a trustworthy absolute reference, in maybe 15
minutes. That directly attacks the limiting factor, where another race session does not.

## Caveats

- The gap is still **relative** — eCompass minus fluxgate. Per the 09-04 absolute reference
  the fluxgate owns the larger share. Decomposition remains open.
- `HDGmT` is null in both sessions (TC path went live 2026-09-04), so the thermal term here
  is fitted, not the deployed TC model. Comparing the two is the obvious next step once
  post-flash sailing data exists.
- The 08-26 session is ~84% starboard tack because of the GPS antenna fault; the `SATS`
  filter does not fix that imbalance, it just makes it explicit.
- `ETEMP` samples at ~0.25 Hz and is forward-filled to 1 Hz. Within-window thermal gradients
  faster than 4 s are not resolved.
