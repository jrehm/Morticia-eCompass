# Cross-Session `HDGmE`/`HDGmF` Gap + First In-Service Look at the TC Path (2026-09-05)

Three things, from re-examining the 09-02 race export alongside 08-26 and pulling the
live TC path from InfluxDB.

**Read this alongside**, not instead of, the 09-04 absolute-reference result in `TODO.md`
("the ~24° deviation curve is the FLUXGATE's, not the eCompass's"). That result used a
better method than anything here and is not challenged by this document. See
"Corrections" at the end.

## 1. Which file to use, and what the cleaned one does differently

Each session has two files side by side. The `*-cleaned.csv` is **Jeff's Excel working
copy**, made to support spreadsheet analysis — not a canonical artifact. The raw export is
always present and is the right input for scripted work.

Recorded here only because the 08-26 cleaned file is currently the *sole* source of
`HDGmE`/`HDGmF` for that session (the raw has 1 and 0 non-null rows — the `ca6891a` gap),
so a script has no choice but to read it until that lands and the session is re-pulled.

Round-trip side effects, harmless in Excel, relevant to a script:

- **1-dp rounding.** Median |raw − cleaned| = 0.025, max 0.05 on every numeric column.
  This is rounding, not manual correction — don't read it as edited data. At 0.05°
  quantization against 3–6° fit residuals it is negligible.
- **Timestamps lose their date** — stored as `7:00:00 PM`, parse with `%I:%M:%S %p`.
- **Trailing blank rows** (252 in the 09-02 file; 2748 real rows, not 3000).
- **Dropped columns** — 24 target/polar/layline fields in the 09-02 file (`TGTA`, `TVMG`,
  `PSPD`, `BTA`, `VMAX`, `TTS`, `OWA`, `TACK`, …).
- **Added columns** — `Main`, `Headsail`, `Dagger`, `Tack/Gybe`, `PointOfSail`,
  `Diff  (COG - HDG)` (two spaces), `Diff (HDGmE-HDGmF)`. The sail-config tags are real
  added value and exist nowhere else; a timestamp-keyed side file would let both the Excel
  and scripted workflows use them.
- **Cells blanked** in the 09-02 file: `BRG`/`DTG`/`XTE` 1653 each (no active waypoint),
  `VMC` 862, `COGt` 439, `TWS`/`TWA`/`TWD` ~419, `SOG` 328.

### One unwrap artifact, in the 09-02 file only

Rows **19:15:57–19:16:22** (26 rows) have `HDGmF` and `HDGt` above 360°, up to 387.7° —
unwrapped across the 0/360 boundary so the trace would plot continuously in Excel. `HDGmE`
was left wrapped. Apply `% 360` to those two columns if using this file, or just use the
raw export, where the values are in range (raw `HDGmF` max = 356.72).

**Checked: the 08-26 cleaned file has no such artifact** — `HDGmE` [3.40, 356.20],
`HDGmF` [0.20, 359.10], `HDGt` [0.10, 359.40], zero values outside [0, 360). The
cross-session fit in §2 is therefore unaffected: 09-02 came from the raw export, 08-26 from
the cleaned file with only 1-dp rounding.

### GPS freeze — cause now known

Of the 328 blanked `SOG` cells, 308 are bit-identical to the previous row; of 439 blanked
`COGt` cells, 399 are. Root cause identified by Jeff 2026-09-05: **the GPS19 antenna sits
near the mast base and a turning block intermittently lies on or near it**, shadowing the
sky view. Not a data-pipeline fault. It accounts for the 08-26 tack asymmetry (82% of Port
rows vs 3.9% Starboard — block position depends on tack), for power-cycling the receiver
having no effect, and for LAT/LON persisting while COG/SOG froze. Antenna relocation is
planned for fall 2026; until then the bit-identical-to-previous filter stays in the
pipeline for all historical sessions.


## 2. The gap curve reproduces across two sessions at different TWD

Both the 08-26 cleaned file and the 09-02 raw export carry `HDGmE` and `HDGmF`
(2167 and 2311 paired samples after dropping nulls). Note the 08-10, 08-12 and 08-19 raw
exports have **zero** non-null values on both columns — the unlanded `ca6891a` gap. Only
these two sessions are usable.

`gap = wrap(HDGmE − HDGmF)`, uncorrected eCompass path (`sensors.ecompass.headingMagnetic`,
per `sailing-data-exporter/app.py` L82 — *not* the TC path, which did not exist yet).

Binned by heading, within-bin scatter is 2–6°, i.e. the gap is a clean function of heading.
Within *mast-rotation* bins it is 15–18°, so MROT does not explain it (checked because
`MROT` read 44.5° at the unwrap block; the lead went nowhere).

Fourier fit in heading, `A + Σ Bₙsin(nH) + Cₙcos(nH)`:

| terms | RMS resid 08-26 | RMS resid 09-02 |
|---|---|---|
| k=1 | 5.97° | 6.16° |
| k=2 | 4.77° | 3.49° |
| k=3 | 4.65° | 3.04° |

k=2 coefficients (semicircular + quadrantal):

| | A | sin H | cos H | sin 2H | cos 2H |
|---|---|---|---|---|---|
| 08-26 | −11.00 | −25.35 | −11.54 | 4.76 | 1.53 |
| 09-02 | −9.01 | −28.71 | −12.17 | 5.96 | 3.85 |
| pooled | −9.94 | −27.00 | −11.67 | 5.14 | 2.87 |

**Out-of-sample cross-validation:**

- 08-26 model → 09-02 data: bias +1.90°, RMS 5.30°
- 09-02 model → 08-26 data: bias −1.82°, RMS 6.30°

### Why this is the collinearity break, and why the usual caveat doesn't apply

TWD was 187° (08-26) and 263° (09-02), circular means — **76° apart**. The same magnetic
heading therefore maps to a substantially different TWA in each session.

The pooled residual/TWA correlation is −0.034, but per the standing caveat that proves
nothing on its own: a flexible Fourier curve absorbing TWA-driven variance into heading
terms produces exactly that signature. The evidence here is different. A curve that were
really encoding TWA would have to **disagree between the two sessions**, because the
heading→TWA mapping is shifted 76°. It does not disagree — it cross-predicts to within
2° bias and ~6° RMS.

This is the first result in this project where the heading/TWA confound is actually
broken rather than noted as unresolved.

### What the curve is *of* — open, do not assume

Semicircular amplitude is √(27.00² + 11.67²) ≈ 29.4°. This is a **relative** curve —
eCompass minus fluxgate — and says nothing by itself about which instrument owns it.

Per the 09-04 absolute reference, the fluxgate owns roughly 26° pk-pk of deviation and the
TCO-corrected eCompass roughly 11°. So the pooled curve above is plausibly *mostly the
fluxgate's*, which would make it directly useful to the open **"Swing the fluxgate"** item
rather than to the eCompass deviation table.

**Not asserted.** The magnitudes do not cleanly reconcile: the pooled gap has σ 23.2° over
the 09-02 race window, while the 09-04 work reports 09-02 heading scatter vs fluxgate of
16.0° raw / 8.5° TCO-corrected over the motoring legs. Different windows (sailing vs
motoring), different statistics (σ of a difference vs pk-pk of a fitted curve), and mine
uses the uncorrected eCompass. Decomposing properly means applying the validated TCO
coefficients to the 08-26 and 09-02 *sailing* data and re-fitting against the 09-04
absolute reference. That is the next step, not a conclusion available now.

## 3. First in-service look at the Phase 2a TC path

`sensors.ecompass.headingMagneticTC` began publishing **2026-09-04 17:04 UTC** and has run
continuously since. Boat at the dock throughout; fluxgate heading spans only 6.03° over the
window, so heading is effectively fixed at ~183°.

InfluxDB, 1-minute means, 1715 paired minutes, die temperature 22.1–33.6 °C:

| | mean gap vs fluxgate | sd | range | corr w/ temp |
|---|---|---|---|---|
| `headingMagnetic` (raw) | −9.83° | 7.97° | 39.7° | **−0.788** |
| `headingMagneticTC` | +14.16° | 3.94° | 19.4° | **+0.594** |

Binned by die temperature:

| temp bin | n | mean T | raw gap | TC gap |
|---|---|---|---|---|
| 20–25 °C | 829 | 23.29 | −4.81° | +11.91° |
| 25–30 °C | 475 | 27.61 | −10.05° | +15.28° |
| 30–35 °C | 411 | 32.10 | −19.72° | +17.41° |

**Working, and overshooting.** Thermal swing across the range drops from ~14.9° to ~5.5°,
roughly a 63% reduction — the model is doing real work. But the temperature correlation
did not go to zero, it **flipped sign**. At this heading the correction applies something
like 2.3 °/°C where ~1.7 °/°C was needed: a ~35% overcorrection. That is a coefficient to
retune, not a broken model.

**Caveats — do not over-read this:**

- **Single heading.** A vector correction projects onto heading differently depending on
  bow direction, so the °/°C figures here are heading-specific and must not be generalised.
- **The +14.16° constant bias is unverified.** At one heading a constant offset and a
  heading-dependent deviation are indistinguishable. It is probably absorbable into the
  mounting offset, but that is an assumption until the boat turns.
- **The sd column is drift, not jitter.** These are 1-minute means, so the ~8° single-sample
  noise from Phase 2a bypassing the Kalman filter is averaged away. This table says nothing
  about Phase 2a's known jitter, which Phase 2b addresses.
- Only 11.5 °C of range. The interesting failures were at 39 °C.

## Corrections to earlier claims made in this session

Recorded because they were stated confidently before the repo was checked.

- **"The eCompass carries most of the deviation" — WRONG.** Based on a per-heading-bin
  spread of COG−heading on steady segments (09-02: `HDGmE` 25.0° vs `HDGmF` 7.7°; 08-26:
  12.8° vs 12.5°, a tie). Superseded by the 09-04 absolute-reference result, which used the
  pure-motoring legs with variation applied and a current grid search and found the opposite.
- **"The 8° jitter comes from accelerometer-only tilt compensation; add a gyro" — WRONG.**
  The FXAS21002C gyro is on the BRKT-STBC-AGM01 and already in the fusion loop
  (`main.cpp` L406 passes `BOARD_GYRO_I2C_ADDR`; the diagnostic summary references
  `SV_9DOF_GBY_KALMAN`). The architecture was never the problem.
- **"Mast rotation may drive the gap" — NO.** Within-MROT-bin scatter 15–18° vs
  within-heading-bin 2–6°.
- **"Calibration drifted between 09-02 and now via auto-recal" — has a documented cause.**
  The 09-04 21z reflash cleared the buffer. Not a silent swap.
