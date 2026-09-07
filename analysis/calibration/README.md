# Heading & Calibration Analysis — Current State

**Read this first.** The dated documents in this directory are a chronological record;
several of their conclusions have since been superseded. This file states what we currently
believe, what is still open, and which earlier claims were overturned.

Last updated: 2026-09-07.

---

## Current understanding

**Root cause.** At 71° magnetic dip the horizontal field is only ~15.6 µT of a ~48 µT total,
and heading derives entirely from that horizontal component. A bow-axis offset of ~7 µT
therefore produces ~29° of semicircular deviation, and the FXOS8700's in-spec thermal
coefficient (0.76 µT/°C measured, ±0.8 typical) drifts that offset by an amount comparable to
the whole horizontal field over a 20 °C day. One mechanism explains the deviation curve, the
noise, and the inclination anomaly.

**Both instruments deviate; the fluxgate is worse.** Against the 09-04 absolute reference
(GPS COG on the pure-motoring legs of the 09-02 sail, variation −7.68°, current grid-search):

| | deviation | σ |
|---|---|---|
| Fluxgate (raw) | ~26° pk-pk | 13.1° |
| eCompass, TCO-corrected | ~11° pk-pk | 8.1° |

**The relative gap curve reproduces across sessions.** eCompass − fluxgate, k=2 Fourier in
heading plus a thermal term, fitted independently on 08-26 and 09-02 (TWD 64° apart,
median die temperature 5.7 °C apart): the dominant `sin H` coefficient agrees to **0.12°**
(−29.16 vs −29.04). Out-of-sample RMS 6.4–9.0°. This is the first result where the
heading/TWA confound is actually broken rather than noted as unresolved — two sessions with
a shifted heading→TWA mapping could not agree this closely if the curve were encoding TWA.

**The Phase 2a TC correction works.** Temperature coefficient −1.37 °/°C raw vs **+0.25 °/°C**
corrected; temperature-only R² on the corrected path is 0.027. It removes ~82% of thermal
error.

**Signal-to-noise varies through the day.** `B·cos(incl)` runs 14.7 µT at 19 °C down to
5.6 µT at 33.5 °C, so the same 0.89 µT sensor noise gives ~3.5° of heading noise cold and
~9° hot. Swing and measure in the cool part of the day.

**Neither instrument is currently a usable heading source.** For tactical TWD you want ~2°.
That gap is the reason this work continues.

---

## Open questions

1. **Secular drift: relaxation or walk?** ~+4 to +7 °/day at a fixed dock heading, confirmed
   model-free by matched-temperature comparison. This is the compensate-vs-replace decision.
   2.8 days is too few time constants to call it. **Resolves by re-swinging a week after the
   first swing** — if the table still fits, the drift bounded out.
2. **Decomposing the relative curve.** The 29.4° gap curve is eCompass *minus* fluxgate.
   Splitting it into per-instrument shares needs the TCO coefficients applied to the *sailing*
   data and re-fitted against the 09-04 absolute reference. Magnitudes do not currently
   reconcile (pooled gap σ 23.2° over the 09-02 race window vs 16.0°/8.5° raw/TCO over the
   motoring legs) — different windows and statistics, needs doing properly.
3. **Coverage, not collinearity, is now the binding constraint.** Pooled residual σ is 12.5°
   in the 0–30° bin (90 samples across both sessions) against ~4.6° in well-covered bins.
   Race courses do not visit those headings. A powered swing circle fixes this in ~15 minutes
   where more racing does not.

---

## Corrections log

Claims that were stated confidently and later overturned. The reasoning is usually more
useful than the conclusion.

| claim | verdict | why it was wrong |
|---|---|---|
| "The eCompass carries most of the deviation" | **wrong** | Came from per-heading-bin spread of COG−heading on steady segments. The 09-04 absolute reference used the pure-motoring legs with variation applied and a current grid-search, and found the fluxgate is the larger error source. |
| "The 8° jitter is accelerometer-only tilt compensation — add a gyro" | **wrong** | The FXAS21002C gyro is on the BRKT-STBC-AGM01 and already in the fusion loop (`SV_9DOF_GBY_KALMAN`). The architecture was never the problem. |
| "08-10, 08-12, 08-19 can be recovered by re-exporting" | **wrong** | Inferred from CSV contents without checking InfluxDB. Both compass paths have their first row at 2026-08-19 20:00 EDT; the data was never recorded. No exporter change retrieves it. |
| "09-04 and 09-05 are sailing sessions worth exporting" | **wrong** | Detected with a max-`SOG` scan — the wrong detector when the GPS emits spurious speeds (23.6 kn tied up). Position displacement shows 200 m and 44 m. Use `navigation.position`, never `speedOverGround`. |
| "The TC path overcorrects by ~35%" | **wrong** | Attributed secular drift to temperature. Separated properly, the residual thermal coefficient is +0.25 °/°C and temp-only R² is 0.027. |
| "The drift is relaxation, τ≈1 d, nearly settled" | **overstated** | Depended on one temperature model. The trend survives a quadratic temperature fit at +3.95 °/day with no clear deceleration. Now recorded as open. |
| "The fluxgate has mounting offset 0" | **wrong** | It is 10°, set at the dock ~08-26. It has still never been *swung* — a scalar is not a deviation table. |
| Cross-validation RMS 5.30/6.30° (09-05) | **optimistic** | Used a 50-minute slice of 09-02 and an Excel copy of 08-26. On full windows with fix-quality filtering it is 6.4–9.0°. |

**Recurring lesson:** every one of these came from inferring a system's state from a
derived artifact — a CSV, a narrative doc, a fitted residual — instead of checking the live
system. Check InfluxDB, check the plugin config, check the path mapping.

---

## Method notes

- **Finding sailing sessions:** use `navigation.position` displacement from the dock median.
  Real sails show >3 nm; dock noise is ~15 m. Never use `speedOverGround`.
- **Filtering GPS rows:** filter on `SATS >= 6`. Rows below that threshold have a frozen
  velocity solution 91–95% of the time; rows above, 5–8%. `HDOP` is redundant with `SATS`.
  Forward-fill `SATS` over short gaps first (`limit=3`) — nulls are ~1 s transport gaps, and
  `NaN >= 6` is False, so they are otherwise dropped silently (~15% of a session).
- **`ETEMP`** samples at ~0.25 Hz against 1 Hz elsewhere; forward-fill before joining.
- **`HDGmE`/`HDGmF` are both raw.** `HDGmF` in particular does *not* include the fluxgate's
  +10° `derived-data` offset — that republishes under a different source than the path-mapper
  filter captures. See ADR-015.
- **Prefer raw exports** to the `*-cleaned.csv` Excel working copies for scripted analysis.

---

## Document index

| document | covers | status |
|---|---|---|
| `gap_crosssession_v2_20260906.md` | Cross-session gap fit, thermal term, fix-quality filtering | **current** |
| `magnoise_diagnostic_summary_20260901.md` | `magnoise` source hunt, dock-week characterisation | current |
| `hdgme_hdgmf_crosssession_20260905.md` | First cross-session pass | §1 current; **§2 superseded by v2**, §3 superseded (see corrections log) |
| `sensor_stability_comparison_20260826.md` | eCompass vs fluxgate internal consistency | superseded by the 09-04 absolute reference |
| `hdgme_hdgmf_gap_followup_20260826.md` | Roll/heel and convergence follow-up | open question, not superseded |
| `sailing_deviation_summary_20260826.md` | 08-26 session fit | superseded — used the Excel copy; session now available as raw |
| `sailing_data_quality_summary_20260826.md` | 08-26 data quality | largely superseded by the `SATS`-based method above |
| `sailing_deviation_summary.md` / `sailing_data_quality_summary.md` | 08-12 session | historical |
| `deviation_summary.md` / `data_quality_summary.md` | 08-10 motoring diagnostic | historical; motoring table explicitly rejected |

Scripts: `fit_gap_crosssession_v2.py` is the current fit. Earlier per-session scripts are
kept alongside their summaries.
