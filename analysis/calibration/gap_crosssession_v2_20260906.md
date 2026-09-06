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

⚠️ **Null handling matters here, and the first version of this script got it wrong.**
`SATS`/`HDOP` publish at ~1 Hz but drop the occasional tick — null runs are median 1 s, max
3 s. Because `NaN >= 6` evaluates False in pandas, those rows were being silently discarded
along with the genuinely bad ones, costing ~15% of each session for no reason. They are
transport gaps, not fix loss: satellite count does not change meaningfully in 1–3 s, and
those rows behave like good data (frozen rate 20–31%) rather than bad (91–95% for genuine
`SATS<6`). Fixed by a short `ffill(limit=3)` before filtering, plus an explicit
`SATS.notna()` step so nulls are dropped deliberately rather than by comparison semantics.

| step | 08-26 | 09-02 |
|---|---|---|
| all rows | 8991 | 9000 |
| underway (>500 m from dock) | 6627 (74%) | 5631 (63%) |
| both compasses non-null | 5140 (57%) | 4320 (48%) |
| `SATS` present (after ffill) | 5140 | 4320 |
| `SATS>=6` | **3874 (43%)** | **3837 (43%)** |
| `0<HDOP<=5` | 3874 | 3837 |

The fix-quality filter removes 25% of compass-paired rows on 08-26 and 11% on 09-02.
`HDOP` adds nothing beyond `SATS`; the two are redundant here, so `SATS` alone suffices.

**Validation that `SATS` is the right filter:** rows with a genuine `SATS<6` have a frozen
velocity solution 91.5% (08-26) and 95.4% (09-02) of the time, against 4.9% and 7.7% for
`SATS>=6`. The satellite count and the freeze are the same phenomenon.

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
| 1 | no | 6.03 | 9.76 |
| 1 | yes | 5.59 | 8.03 |
| 2 | no | 4.99 | 7.28 |
| 2 | **yes** | **4.86** | **6.65** |
| 3 | no | 4.96 | 7.11 |
| 3 | yes | 4.81 | 6.26 |

The thermal term helps at every order, and more on the warmer session — as it should if it
is capturing something physical. k=3 buys little over k=2; k=2 + thermal is the sensible
stopping point.

## The result worth noting

k=2 coefficients, without and with the thermal term:

| | 08-26 | 09-02 | apart |
|---|---|---|---|
| **heading only** | | | |
| A | −11.36 | −7.78 | 3.6 |
| sin H | −25.14 | −31.25 | **6.1** |
| cos H | −8.63 | −10.86 | 2.2 |
| sin 2H | 4.98 | 9.62 | 4.6 |
| **+ thermal** | | | |
| A | −8.96 | −8.32 | 0.6 |
| sin H | **−29.16** | **−29.04** | **0.12** |
| cos H | −6.86 | −12.46 | 5.6 |
| sin 2H | 4.59 | 8.39 | 3.8 |
| dT | 0.50 | 0.83 | — |
| dT·sin H | −0.86 | −1.39 | — |

`sin H` is the dominant term at roughly −29°. Fitted independently on two sessions a week
apart, at different wind directions and different temperatures, adding a thermal term brings
them from 6.1° apart to **0.12° apart**. The `dT` and `dT·sin H` terms agree in sign and
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
| no | 08-26 | 09-02 | +5.21 | 10.59 |
| no | 09-02 | 08-26 | −1.50 | 7.60 |
| **yes** | 08-26 | 09-02 | +2.54 | **8.95** |
| **yes** | 09-02 | 08-26 | −1.15 | **6.35** |

The thermal term improves both directions. But **these are worse than the 5.30/6.30 RMS
reported on 09-05**, and the earlier figures should be treated as optimistic artifacts of
narrow windows: that pass used a 50-minute slice of 09-02 and an Excel copy of 08-26, both
of which sampled a narrower range of conditions than the full sessions do.

**What this means for the collinearity claim.** The 09-05 conclusion — that the
heading/TWA confound is broken by cross-session agreement — still holds directionally:
biases are small (1–2.5° with thermal), the dominant coefficient now agrees to 0.12°, and
pooled residual correlations are all negligible (TWA −0.066, ROLL −0.106, ETEMP +0.000,
MROT −0.009). But the residual scatter is 6.4–9.0° out of sample, not 5–6°. A table deployed
from this would carry that error. It is not yet good enough to deploy.

## Pooled fit

| | RMS | n |
|---|---|---|
| k=2, heading only | 6.98 | 7711 |
| k=2 + thermal | **6.08** | 7711 |

Pooled thermal coefficients: `A=−8.13, sinH=−29.52, cosH=−10.55, sin2H=7.27, cos2H=2.37,
dT=0.74, dT·sinH=−1.07, dT·cosH=0.05`.

## What is now the binding constraint

Not collinearity — coverage. Pooled residual σ by heading bin:

| heading | n | resid σ |
|---|---|---|
| 0–30° | 90 | **12.48** |
| 150–180° | ~738 | ~8.1 |
| 30–60° | 433 | 7.23 |
| 240–270° | 186 | ~5.7 |
| (best bins) 270–330° | ~1007 | ~4.6 |

The 0–30° bin has 90 samples pooled across both sessions and σ 12.5°. 240–270° has 186.
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
