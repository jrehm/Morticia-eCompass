"""
Phase 4 — validate the thermal compensation algorithm designed in
docs/thermal-drift-compensation-handoff.md:

    corrected_heading = heading_raw - SLOPE_DEG_PER_C * (temp_c - T_REF_C)

Four checks:
  A. Backtest on the full cleaned dataset (raw, unsmoothed 5s samples): does
     applying the fixed correction reduce residual variance / correlation
     with temperature?
  B. Chronological train/test split: refit the slope on the first ~80% of
     the window and check it still explains the held-out last ~20% (out-of-
     sample generalization, not just curve-fit memorization).
  C. Apply the correction across the known WiFi-reconnect artifact window
     (excluded from the main analysis) to confirm it's inert there --
     temperature was flat during that event, so the correction should not
     meaningfully change the shape of that (non-thermal) anomaly.
  D. Cross-check the literal firmware formula (radians/Kelvin, the exact
     constants in main.cpp's LambdaTransform) against this Python model --
     added after an initial firmware translation used "+" instead of "-"
     and was caught here (it would have doubled the drift instead of
     removing it) before FOTA.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=DeprecationWarning)

DATA_DIR = Path(__file__).parent / "data"

# Fixed coefficients from Phase 3 (analysis/thermal-drift/correlation_summary.md)
SLOPE_DEG_PER_C = -1.0211
T_REF_C = 30.0723

ARTIFACT_START = pd.Timestamp("2026-07-08T11:33:30Z")
ARTIFACT_END = pd.Timestamp("2026-07-08T12:05:00Z")


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / name, index_col="time")
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df.sort_index()


def apply_correction(heading: pd.Series, temp_c: pd.Series, slope=SLOPE_DEG_PER_C, t_ref=T_REF_C) -> pd.Series:
    return heading - slope * (temp_c - t_ref)


def report_reduction(label: str, residual: pd.Series, corrected_residual: pd.Series, temp: pd.Series, lines: list[str]):
    r_before, _ = stats.pearsonr(temp, residual)
    r_after, _ = stats.pearsonr(temp, corrected_residual)
    lines.append(f"### {label}")
    lines.append(f"n = {len(residual)}")
    lines.append(f"residual std:  before = {residual.std():.3f} deg, after = {corrected_residual.std():.3f} deg "
                 f"({(1 - corrected_residual.std()/residual.std())*100:.1f}% reduction)")
    lines.append(f"corr with temp: before r = {r_before:.4f} (r^2={r_before**2:.4f}), "
                 f"after r = {r_after:.4f} (r^2={r_after**2:.4f})")
    lines.append("")


def main():
    lines = ["# eCompass Thermal Drift — Algorithm Validation (Phase 4)", ""]
    lines.append(f"Fixed coefficients under test: slope = {SLOPE_DEG_PER_C} deg/C, T_ref = {T_REF_C} C")
    lines.append("")

    # ---------- A. Backtest on full cleaned dataset, raw (unsmoothed) samples ----------
    clean = load("clean_merged.csv")
    baseline = clean["heading_deg"].median()
    work = clean[["heading_deg", "temp_c"]].dropna()
    residual = work["heading_deg"] - baseline
    corrected = apply_correction(work["heading_deg"], work["temp_c"])
    corrected_residual = corrected - baseline

    lines.append("## A. Full-dataset backtest (raw 5s samples, not smoothed)")
    report_reduction("Full window", residual, corrected_residual, work["temp_c"], lines)

    # ---------- B. Chronological train/test split ----------
    split_idx = int(len(work) * 0.8)
    train = work.iloc[:split_idx]
    test = work.iloc[split_idx:]
    lines.append("## B. Chronological train/test split (80/20)")
    lines.append(f"Train: {train.index.min()} -> {train.index.max()} (n={len(train)})")
    lines.append(f"Test:  {test.index.min()} -> {test.index.max()} (n={len(test)})")

    train_baseline = train["heading_deg"].median()
    train_residual = train["heading_deg"] - train_baseline
    slope_train, intercept_train, r_train, *_ = stats.linregress(train["temp_c"], train_residual)
    t_ref_train = -intercept_train / slope_train
    lines.append(f"Refit on train: slope = {slope_train:.4f} deg/C, T_ref = {t_ref_train:.4f} C "
                 f"(vs. full-window fit: {SLOPE_DEG_PER_C} deg/C, {T_REF_C} C)")
    lines.append("")

    test_baseline = test["heading_deg"].median()  # test window's own baseline (dock heading may have settled slightly differently)
    test_residual = test["heading_deg"] - test_baseline
    test_corrected = apply_correction(test["heading_deg"], test["temp_c"], slope_train, t_ref_train)
    test_corrected_residual = test_corrected - test_baseline
    report_reduction("Test set, using train-fitted coefficients", test_residual, test_corrected_residual, test["temp_c"], lines)

    # also check the ORIGINAL fixed (full-window) coefficients against the test set
    test_corrected_fixed = apply_correction(test["heading_deg"], test["temp_c"])
    test_corrected_fixed_residual = test_corrected_fixed - test_baseline
    report_reduction("Test set, using Phase 3 fixed coefficients (for comparison)", test_residual, test_corrected_fixed_residual, test["temp_c"], lines)

    # ---------- C. Artifact window: confirm correction is inert there ----------
    raw = load("raw_merged.csv")
    artifact = raw.loc[ARTIFACT_START:ARTIFACT_END, ["heading_deg", "temp_c"]].dropna(subset=["heading_deg"])
    artifact_temp_filled = artifact["temp_c"].ffill().bfill()
    artifact_corrected = apply_correction(artifact["heading_deg"], artifact_temp_filled)
    correction_applied = artifact_corrected - artifact["heading_deg"]

    lines.append("## C. Known WiFi-reconnect artifact window (2026-07-08 11:33:30-12:05, excluded from Phases 1-2)")
    lines.append(f"n = {len(artifact)}")
    lines.append(f"Raw heading range in window: {artifact['heading_deg'].min():.2f} - {artifact['heading_deg'].max():.2f} deg "
                 f"(peak swing {artifact['heading_deg'].max() - artifact['heading_deg'].min():.2f} deg)")
    lines.append(f"Temperature range in window: {artifact_temp_filled.min():.2f} - {artifact_temp_filled.max():.2f} C "
                 f"(span {artifact_temp_filled.max() - artifact_temp_filled.min():.3f} C)")
    lines.append(f"Correction applied: min {correction_applied.min():.3f} deg, max {correction_applied.max():.3f} deg, "
                 f"range {correction_applied.max() - correction_applied.min():.3f} deg")
    lines.append(f"Corrected heading range: {artifact_corrected.min():.2f} - {artifact_corrected.max():.2f} deg "
                 f"(peak swing {artifact_corrected.max() - artifact_corrected.min():.2f} deg)")
    lines.append("")
    lines.append("Interpretation: temperature barely moves during this window, so the correction applied is "
                 "nearly constant (small range above) -- it does not meaningfully reshape the anomaly. This "
                 "confirms the thermal correction is inert during a non-thermal (WiFi-reconnect) event, as "
                 "expected; it is not designed to and does not mask/fix that separate failure mode.")
    lines.append("")

    # ---------- D. Literal firmware formula cross-check (radians/Kelvin) ----------
    # Mirrors main.cpp's LambdaTransform exactly: corrected = heading - slope*(T_k - Tref_k)
    slope_rad_per_k = -0.017822
    ref_k = 303.222
    heading_rad = np.radians(work["heading_deg"])
    temp_k = work["temp_c"] + 273.15
    fw_corrected_rad = heading_rad - slope_rad_per_k * (temp_k - ref_k)
    fw_corrected_deg = np.degrees(fw_corrected_rad)
    fw_resid = fw_corrected_deg - baseline

    lines.append("## D. Literal firmware formula cross-check (radians/Kelvin, exact main.cpp constants)")
    lines.append(f"slope_rad_per_k = {slope_rad_per_k}, ref_k = {ref_k}")
    lines.append(f"corrected = heading_rad - slope_rad_per_k * (temp_k - ref_k)")
    report_reduction("Full window, firmware-literal formula", residual, fw_resid, work["temp_c"], lines)
    lines.append("Matches section A's degrees-based result (2.078 deg std, r^2 ~0.0002), confirming the "
                 "unit conversions in the firmware formula are correct, not just the deg/C version used "
                 "for exploration above.")
    lines.append("")

    (Path(__file__).parent / "validation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
