"""
NEW-LOCATION check (2026-07-30 09:00 local onward) for the relocated
eCompass sensor (second BRKT-STBC-AGM01, ~3ft from SensESP/battery via
twisted-pair I2C -- ADR-013). Dockside the whole window, low wind,
only line-stretch movement per Jeff.

Reads data/clean_newloc.csv (from clean_newloc.py). This does NOT
reconstruct a pre-correction signal the way correlate_recent.py did --
if slope_deg_per_c has been reset to 0 via /api/thermal/config,
heading_deg here already IS the raw signal. Section 4 checks whether
that reset was actually applied.
"""

import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=DeprecationWarning)

DATA_DIR = Path(__file__).parent / "data"
PLOT_DIR = Path(__file__).parent / "plots"
PLOT_DIR.mkdir(exist_ok=True)

SMOOTHING_WINDOW = "20min"

# For reference / comparison only -- the OLD (PCB-adjacent) location's fits:
OLD_LOCATION_ORIGINAL_SLOPE = -1.0211  # deg/C, r^2=0.7666, 2026-07-08/13
OLD_LOCATION_9DAY_RECHECK_SLOPE = -0.164  # deg/C, r^2=0.07, 2026-07-20/29


def load_clean() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_newloc.csv", index_col="time")
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df.sort_index()


def ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    X1 = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ coefs
    return coefs, resid


def main():
    df = load_clean()
    lines = ["# eCompass New-Location Check (2026-07-30 onward)", ""]
    lines.append(
        "Relocated sensor (~3ft from SensESP/battery, twisted-pair I2C, ADR-013). "
        "Dockside, low wind, only line-stretch movement. `heading_deg` below is "
        "`navigation.headingCompass` -- if `slope_deg_per_c` was reset to 0, this "
        "is the sensor's raw (uncorrected) output; section 4 checks that."
    )
    lines.append("")

    heading = df["heading_deg"]
    baseline = heading.median()
    residual = (heading - baseline).rolling(SMOOTHING_WINDOW, center=True, min_periods=50).mean()
    temp_smoothed = df["temp_c"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()
    wind_smoothed = df["wind_speed_kn"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()

    work = pd.DataFrame({
        "residual": residual, "temp_c": temp_smoothed, "wind_kn": wind_smoothed,
    }).dropna()

    lines.append(f"Window: {df.index.min()} -> {df.index.max()}")
    lines.append(f"Baseline heading (median): {baseline:.3f} deg")
    lines.append(f"Samples used: {len(work)}")
    lines.append(f"Heading range: {heading.min():.2f} - {heading.max():.2f} deg "
                 f"(span {heading.max()-heading.min():.2f} deg)")
    lines.append(f"Temperature range: {work['temp_c'].min():.2f} - {work['temp_c'].max():.2f} C")
    lines.append("")
    # --- 1. Residual vs temp ---
    slope, intercept, r, p, se = stats.linregress(work["temp_c"], work["residual"])
    tref_implied = baseline - intercept / slope if slope != 0 else float("nan")
    lines.append("## 1. Heading residual vs. temperature")
    lines.append(f"slope = {slope:.4f} deg/C, intercept = {intercept:.4f} deg")
    lines.append(f"r = {r:.4f}, r^2 = {r**2:.4f}, p = {p:.3e}")
    lines.append("")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(work["temp_c"], work["residual"], s=2, alpha=0.15)
    xs = np.linspace(work["temp_c"].min(), work["temp_c"].max(), 100)
    ax.plot(xs, slope * xs + intercept, color="red", label=f"fit: {slope:.3f} deg/C")
    ax.set_xlabel("Temperature (C)")
    ax.set_ylabel("Heading residual (deg)")
    ax.set_title("New location: residual vs. temperature")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "newloc_residual_vs_temp.png", dpi=130)
    plt.close(fig)

    # --- 2. Overlay time series ---
    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax1.plot(work.index, work["residual"], color="tab:blue", lw=0.6, label="residual (deg)")
    ax1.set_ylabel("Heading residual (deg)", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(work.index, work["temp_c"], color="tab:red", lw=0.8, label="temperature (C)")
    ax2.set_ylabel("Temperature (C)", color="tab:red")
    ax1.set_title("New location: residual and temperature over time")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "newloc_timeseries_overlay.png", dpi=130)
    plt.close(fig)
    # --- 3. Wind-controlled multiple regression ---
    coefs, resid_after = ols(work["residual"].to_numpy(), work[["temp_c", "wind_kn"]].to_numpy())
    intercept_mr, temp_coef_mr, wind_coef_mr = coefs
    ss_res = np.sum(resid_after ** 2)
    ss_tot = np.sum((work["residual"].to_numpy() - work["residual"].mean()) ** 2)
    r2_mr = 1 - ss_res / ss_tot
    temp_wind_corr = work["temp_c"].corr(work["wind_kn"])

    lines.append("## 2. Wind-controlled multiple regression (residual ~ temp_c + wind_kn)")
    lines.append(f"intercept = {intercept_mr:.4f}, temp_coef = {temp_coef_mr:.4f} deg/C, "
                 f"wind_coef = {wind_coef_mr:.4f} deg/kn")
    lines.append(f"R^2 = {r2_mr:.4f}  (vs. R^2 = {r**2:.4f} for temp alone)")
    lines.append(f"temp/wind collinearity: r = {temp_wind_corr:.4f}")
    lines.append("")

    # --- 4. Diurnal pattern ---
    work_local = work.copy()
    work_local["hour"] = work_local.index.hour
    hourly = work_local.groupby("hour")[["residual", "temp_c", "wind_kn"]].mean()
    lines.append("## 3. Diurnal pattern (hourly mean, UTC hour of day)")
    lines.append(hourly.to_string())
    lines.append("")

    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(hourly.index, hourly["residual"], color="tab:blue", marker="o", label="residual")
    ax1.set_ylabel("Mean residual (deg)", color="tab:blue")
    ax1.set_xlabel("Hour of day (UTC)")
    ax2 = ax1.twinx()
    ax2.plot(hourly.index, hourly["temp_c"], color="tab:red", marker="o", label="temp")
    ax2.set_ylabel("Mean temperature (C)", color="tab:red")
    ax1.set_title("New location: diurnal pattern")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "newloc_diurnal_pattern.png", dpi=130)
    plt.close(fig)
    # --- 5. Sanity check: was the thermal-correction reset actually applied? ---
    lines.append("## 4. Sanity check: is a firmware thermal correction still active?")
    lines.append(
        f"If `slope_deg_per_c` was successfully reset to 0, `heading_deg` here is raw "
        f"sensor output, and section 1's slope ({slope:.4f} deg/C) is the sensor's actual "
        f"current thermal sensitivity -- not a residual after correction."
    )
    lines.append(
        f"For reference, the OLD location's fits were {OLD_LOCATION_ORIGINAL_SLOPE} deg/C "
        f"(original, r^2=0.77) and {OLD_LOCATION_9DAY_RECHECK_SLOPE} deg/C (9-day recheck, "
        f"r^2=0.07), both against a sensor 3cm from the SensESP PCB. If this window's slope "
        f"is nowhere near -1.0 deg/C in magnitude, that's consistent with either the reset "
        f"having been applied, or the new location genuinely having little thermal "
        f"sensitivity (both are plausible and not mutually exclusive) -- this can't fully "
        f"distinguish the two without checking `GET /api/thermal/config` directly."
    )
    lines.append("")

    # --- 6. Synthesis ---
    lines.append("## 5. Synthesis")
    lines.append(
        f"1. Residual-vs-temperature slope at the new location: {slope:.4f} deg/C, r^2={r**2:.4f}."
    )
    lines.append(
        f"2. Wind-controlled: temp_coef={temp_coef_mr:.4f} deg/C, wind_coef={wind_coef_mr:.4f} deg/kn, "
        f"R^2={r2_mr:.4f}, temp/wind collinearity r={temp_wind_corr:.4f}."
    )
    lines.append(
        "3. Jeff reports the boat has been dockside, low wind, only line-stretch movement "
        "during this window -- so unlike the prior 9-day check, wind-driven boat swing is "
        "less likely to be a major confound here, making this a cleaner test of temperature "
        "alone, if the sample is large/varied enough in temperature range."
    )
    lines.append("")

    lines.append("## Plots written")
    for p in sorted(PLOT_DIR.glob("newloc_*.png")):
        lines.append(f"- plots/{p.name}")

    (Path(__file__).parent / "newloc_correlation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
