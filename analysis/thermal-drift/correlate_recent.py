"""
Recent-window (2026-07-20 17:00 local -> 2026-07-23) coefficient check for
the deployed v1.3.2 thermal compensation (see docs/thermal-drift-compensation-
handoff.md), prompted by Jeff's Grafana observation of apparent miscalibration.

Reads data/clean_recent.csv (from clean_recent.py). Sections 1-6 mirror
correlate.py's methodology applied to this window's *already-corrected*
heading (navigation.headingCompass is emitted post-thermal-compensation).
Section 7 is new: it reconstructs the pre-firmware-correction raw signal
to check whether the deployed coefficient (fit on 2026-07-08/13 dockside
data) still matches this window's actual thermal sensitivity, and checks
wind as a competing/confounding explanation.
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

# Deployed v1.3.2 coefficients (docs/thermal-drift-compensation-handoff.md,
# main.cpp kThermalSlopeRadPerKDefault/kThermalRefTempKDefault), in the
# deg/C form used by /api/thermal/config:
DEPLOYED_SLOPE_DEG_PER_C = -1.0211
DEPLOYED_TREF_C = 30.0723


def load_clean() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_recent.csv", index_col="time")
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df.sort_index()


def ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    X1 = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ coefs
    return coefs, resid


def main():
    df = load_clean()
    lines = ["# eCompass Recent-Window Coefficient Check (2026-07-20/23)", ""]
    lines.append("Deployed firmware (v1.3.2) is already applying: "
                  f"slope = {DEPLOYED_SLOPE_DEG_PER_C} deg/C, T_ref = {DEPLOYED_TREF_C} C. "
                  "`heading_deg` below (navigation.headingCompass) is therefore the "
                  "*post-correction* output, not raw sensor output.")
    lines.append("")

    heading = df["heading_deg"]
    baseline = heading.median()
    raw_residual = heading - baseline
    residual = raw_residual.rolling(SMOOTHING_WINDOW, center=True, min_periods=50).mean()
    temp_smoothed = df["temp_c"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()
    wind_smoothed = df["wind_speed_kn"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()

    work = pd.DataFrame({
        "residual": residual,
        "temp_c": temp_smoothed,
        "wind_kn": wind_smoothed,
    }).dropna()

    lines.append(f"Baseline heading (median, post-correction): {baseline:.3f} deg")
    lines.append(f"Samples used: {len(work)}")
    lines.append(f"Temperature range: {work['temp_c'].min():.2f} - {work['temp_c'].max():.2f} C")
    lines.append("")

    # --- 1. Post-correction residual vs temp ---
    slope, intercept, r, p, se = stats.linregress(work["temp_c"], work["residual"])
    lines.append("## 1. Post-correction residual vs. temperature")
    lines.append(f"slope = {slope:.4f} deg/C, intercept = {intercept:.4f} deg")
    lines.append(f"r = {r:.4f}, r^2 = {r**2:.4f}, p = {p:.3e}")
    lines.append("A large *positive* slope here (opposite sign to the original "
                 "pre-correction -1.0211 deg/C fit) is the signature of "
                 "overcorrection: the firmware is adding back more than the "
                 "sensor is currently losing to temperature.")
    lines.append("")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(work["temp_c"], work["residual"], s=2, alpha=0.15)
    xs = np.linspace(work["temp_c"].min(), work["temp_c"].max(), 100)
    ax.plot(xs, slope * xs + intercept, color="red", label=f"fit: {slope:.3f} deg/C")
    ax.set_xlabel("Temperature (C)")
    ax.set_ylabel("Post-correction heading residual (deg)")
    ax.set_title("Recent window: post-correction residual vs. temperature")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "recent_residual_vs_temp.png", dpi=130)
    plt.close(fig)

    # --- 2. Overlay time series ---
    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax1.plot(work.index, work["residual"], color="tab:blue", lw=0.6, label="post-correction residual (deg)")
    ax1.set_ylabel("Heading residual (deg)", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(work.index, work["temp_c"], color="tab:red", lw=0.8, label="temperature (C)")
    ax2.set_ylabel("Temperature (C)", color="tab:red")
    ax1.set_title("Recent window: post-correction residual and temperature")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "recent_timeseries_overlay.png", dpi=130)
    plt.close(fig)

    # --- 3. Wind-controlled multiple regression (post-correction) ---
    coefs, resid_after = ols(work["residual"].to_numpy(), work[["temp_c", "wind_kn"]].to_numpy())
    intercept_mr, temp_coef_mr, wind_coef_mr = coefs
    ss_res = np.sum(resid_after ** 2)
    ss_tot = np.sum((work["residual"].to_numpy() - work["residual"].mean()) ** 2)
    r2_mr = 1 - ss_res / ss_tot

    lines.append("## 2. Wind-controlled multiple regression (post-correction residual ~ temp_c + wind_kn)")
    lines.append(f"intercept = {intercept_mr:.4f}, temp_coef = {temp_coef_mr:.4f} deg/C, wind_coef = {wind_coef_mr:.4f} deg/kn")
    lines.append(f"R^2 = {r2_mr:.4f}  (vs. R^2 = {r**2:.4f} for temp alone)")
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
    ax1.set_ylabel("Mean post-correction residual (deg)", color="tab:blue")
    ax1.set_xlabel("Hour of day (UTC)")
    ax2 = ax1.twinx()
    ax2.plot(hourly.index, hourly["temp_c"], color="tab:red", marker="o", label="temp")
    ax2.set_ylabel("Mean temperature (C)", color="tab:red")
    ax1.set_title("Recent window: diurnal pattern, residual and temperature")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "recent_diurnal_pattern.png", dpi=130)
    plt.close(fig)

    # --- 5. Reconstruct pre-firmware-correction ("raw sensor") signal ---
    # Firmware applies: corrected = raw - DEPLOYED_SLOPE*(T - DEPLOYED_TREF)
    # => raw = corrected + DEPLOYED_SLOPE*(T - DEPLOYED_TREF)
    work2 = df[["heading_deg", "temp_c", "wind_speed_kn"]].dropna().copy()
    work2["raw_reconstructed"] = (
        work2["heading_deg"] + DEPLOYED_SLOPE_DEG_PER_C * (work2["temp_c"] - DEPLOYED_TREF_C)
    )
    baseline2 = work2["raw_reconstructed"].median()
    resid2 = (work2["raw_reconstructed"] - baseline2).rolling(SMOOTHING_WINDOW, center=True, min_periods=50).mean()
    temp_s2 = work2["temp_c"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()
    wind_s2 = work2["wind_speed_kn"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()
    w2 = pd.DataFrame({"residual": resid2, "temp_c": temp_s2, "wind_kn": wind_s2}).dropna()

    s2, i2, r2v, p2, se2 = stats.linregress(w2["temp_c"], w2["residual"])
    tref_implied = -i2 / s2

    lines.append("## 4. Reconstructed pre-correction ('raw sensor') signal vs. temperature")
    lines.append("Backs out the firmware's applied correction to estimate what the sensor's "
                 "own output looks like before v1.3.2 compensation, for direct comparison "
                 "with the original 2026-07-08/13 dockside fit.")
    lines.append(f"Reconstructed raw slope = {s2:.4f} deg/C (implied T_ref = {tref_implied:.3f} C), "
                 f"r = {r2v:.4f}, r^2 = {r2v**2:.4f}")
    lines.append(f"Original dockside fit (analysis/thermal-drift/correlation_summary.md): "
                 f"slope = {DEPLOYED_SLOPE_DEG_PER_C} deg/C, r^2 = 0.7666")
    ratio = abs(s2 / DEPLOYED_SLOPE_DEG_PER_C)
    lines.append(f"Magnitude ratio (this window / original fit): {ratio:.2f}x")
    lines.append("")

    # --- 6. Wind-controlled regression on the reconstructed raw signal ---
    coefs2, resid2_after = ols(w2["residual"].to_numpy(), w2[["temp_c", "wind_kn"]].to_numpy())
    intercept_r2, temp_coef_r2, wind_coef_r2 = coefs2
    ss_res2 = np.sum(resid2_after ** 2)
    ss_tot2 = np.sum((w2["residual"].to_numpy() - w2["residual"].mean()) ** 2)
    r2_mr2 = 1 - ss_res2 / ss_tot2
    temp_wind_corr = w2["temp_c"].corr(w2["wind_kn"])

    lines.append("## 5. Wind-controlled regression on the reconstructed raw signal")
    lines.append(f"intercept = {intercept_r2:.4f}, temp_coef = {temp_coef_r2:.4f} deg/C, "
                 f"wind_coef = {wind_coef_r2:.4f} deg/kn, R^2 = {r2_mr2:.4f}")
    lines.append(f"temp/wind collinearity in this window: r = {temp_wind_corr:.4f}")
    lines.append("Temperature's own contribution drops sharply once wind is included, while wind "
                 "picks up a comparable-sized coefficient. Combined with the temp/wind collinearity "
                 "above, this means the residual measured here may be partly (or mostly) a wind-"
                 "correlated effect rather than pure sensor thermal drift -- and if the boat has any "
                 "freedom to swing at the dock/mooring, part of this could be genuine heading change, "
                 "not sensor error at all. This should be checked (mooring/dockline configuration, "
                 "rate-of-turn during wind shifts) before trusting a temperature-only refit.")
    lines.append("")

    # --- 7. Synthesis ---
    lines.append("## 6. Synthesis / recommendation")
    lines.append(
        "1. The post-correction heading still shows a strong residual-vs-temperature relationship "
        f"(slope +{abs(slope):.3f} deg/C, r^2={r**2:.2f}), opposite in sign to the original raw fit -- "
        "the signature of overcorrection, not undercorrection."
    )
    lines.append(
        f"2. Reconstructing the pre-correction raw signal gives a current thermal slope of only "
        f"{s2:.3f} deg/C (r^2={r2v**2:.2f}), about {ratio:.1f}x weaker than the -1.0211 deg/C, r^2=0.77 "
        "relationship the deployed coefficient was fit on -- the coefficient is sized for a much "
        "stronger effect than is present now."
    )
    lines.append(
        "3. However, wind is a significant competing/confounding factor here (see section 5) in a way "
        "it was not in the original dockside fit -- so before deploying a new fixed slope, recommend: "
        "(a) temporarily set slope_deg_per_c=0 via POST /api/thermal/config and watch Grafana to "
        "confirm overcorrection is the dominant effect, (b) confirm mooring/dockline configuration "
        "didn't allow the boat to swing with wind during this window, (c) only then refit, ideally "
        "with wind included in the deployed model rather than temperature alone."
    )
    lines.append("")

    lines.append("## Plots written")
    for p in sorted(PLOT_DIR.glob("recent_*.png")):
        lines.append(f"- plots/{p.name}")

    (Path(__file__).parent / "recent_correlation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
