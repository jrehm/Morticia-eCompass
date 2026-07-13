"""
Phase 2 — correlation analysis for the eCompass thermal-drift study.

Reads data/clean_merged.csv (from clean_data.py) and:
  1. Computes a robust baseline heading (rolling median) and residual.
  2. Correlates residual against temperature: raw regression, lag/cross-
     correlation (to look for thermal-mass lag), and a wind-controlled
     multiple regression (to avoid attributing wind-driven wobble to temp).
  3. Checks for hysteresis (rising vs falling temperature).
  4. Writes plots to plots/ and a written summary to correlation_summary.md.
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

# NOTE: baseline must be a single constant (or a window much longer than the
# diurnal cycle we're trying to detect), not a short rolling detrend -- a
# rolling window on the order of the drift's own timescale removes the very
# signal we're measuring. The boat was tied off the whole window, so "true"
# heading is a single constant; we smooth (not detrend) afterward to
# suppress fast wind wobble while preserving slow thermal-timescale drift.
SMOOTHING_WINDOW = "20min"
MAX_LAG_MIN = 360
LAG_STEP_MIN = 10


def load_clean() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_merged.csv", index_col="time")
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df.sort_index()


def ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Simple OLS with intercept. Returns (coefs incl. intercept, residuals)."""
    X1 = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ coefs
    return coefs, resid


def main():
    df = load_clean()

    heading = df["heading_deg"]
    baseline = heading.median()  # single constant: boat was tied off the whole window
    raw_residual = heading - baseline
    # smooth (not detrend) to suppress fast wind-gust wobble, preserving slow
    # thermal-timescale drift
    residual = raw_residual.rolling(SMOOTHING_WINDOW, center=True, min_periods=50).mean()
    temp_smoothed = df["temp_c"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()
    wind_smoothed = df["wind_speed_kn"].rolling(SMOOTHING_WINDOW, center=True, min_periods=20).mean()

    work = pd.DataFrame({
        "residual": residual,
        "raw_residual": raw_residual,
        "temp_c": temp_smoothed,
        "wind_kn": wind_smoothed,
        "rot": df["rate_of_turn_deg_s"],
    }).dropna()

    lines = ["# eCompass Thermal Drift — Correlation Analysis", ""]
    lines.append(f"Baseline heading (median over full window): {baseline:.3f} deg")
    lines.append(f"Smoothing window (residual/temp/wind, to suppress wind-gust wobble): {SMOOTHING_WINDOW}")
    lines.append(f"Samples used (after baseline/dropna): {len(work)}")
    lines.append(f"Temperature range in analysis set: {work['temp_c'].min():.2f} - {work['temp_c'].max():.2f} C")
    lines.append("")

    # --- 1. Raw linear regression: residual ~ temp ---
    slope, intercept, r, p, se = stats.linregress(work["temp_c"], work["residual"])
    lines.append("## Raw linear fit: residual_deg = slope * temp_c + intercept")
    lines.append(f"slope = {slope:.4f} deg/C, intercept = {intercept:.4f} deg")
    lines.append(f"r = {r:.4f}, r^2 = {r**2:.4f}, p = {p:.3e}")
    lines.append(f"Predicted swing over observed temp range: {slope * (work['temp_c'].max() - work['temp_c'].min()):.2f} deg")
    lines.append("")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(work["temp_c"], work["residual"], s=2, alpha=0.15)
    xs = np.linspace(work["temp_c"].min(), work["temp_c"].max(), 100)
    ax.plot(xs, slope * xs + intercept, color="red", label=f"fit: {slope:.3f} deg/C")
    ax.set_xlabel("Temperature (C)")
    ax.set_ylabel("Heading residual (deg, heading - rolling baseline)")
    ax.set_title("Heading residual vs. temperature")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "residual_vs_temp.png", dpi=130)
    plt.close(fig)

    # --- 2. Overlay time series ---
    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax1.plot(work.index, work["residual"], color="tab:blue", lw=0.6, label="heading residual (deg)")
    ax1.set_ylabel("Heading residual (deg)", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(work.index, work["temp_c"], color="tab:red", lw=0.8, label="temperature (C)")
    ax2.set_ylabel("Temperature (C)", color="tab:red")
    ax1.set_title("Heading residual and temperature over the analysis window")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "timeseries_overlay.png", dpi=130)
    plt.close(fig)

    # --- 3. Lag / cross-correlation ---
    lags_min = list(range(-MAX_LAG_MIN, MAX_LAG_MIN + 1, LAG_STEP_MIN))
    step = pd.Timedelta(work.index.to_series().diff().median())
    lag_steps = {lag: int(round((lag * 60) / step.total_seconds())) for lag in lags_min}

    temp_series = work["temp_c"].to_numpy()
    resid_series = work["residual"].to_numpy()
    corrs = []
    for lag in lags_min:
        shift = lag_steps[lag]
        if shift >= 0:
            a = resid_series[shift:]
            b = temp_series[: len(temp_series) - shift] if shift > 0 else temp_series
        else:
            a = resid_series[: len(resid_series) + shift]
            b = temp_series[-shift:]
        n = min(len(a), len(b))
        if n < 100:
            corrs.append(np.nan)
            continue
        c = np.corrcoef(a[:n], b[:n])[0, 1]
        corrs.append(c)

    best_idx = int(np.nanargmax(np.abs(corrs)))
    best_lag = lags_min[best_idx]
    best_corr = corrs[best_idx]

    lines.append("## Lag / cross-correlation (positive lag = temperature leads heading residual)")
    lines.append(f"Best |correlation| at lag = {best_lag} min, r = {best_corr:.4f}")
    lines.append("")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(lags_min, corrs, marker="o", ms=3)
    ax.axvline(0, color="grey", lw=0.5)
    ax.axvline(best_lag, color="red", lw=0.8, ls="--", label=f"best lag = {best_lag} min")
    ax.set_xlabel("Lag (min); temperature shifted relative to heading residual")
    ax.set_ylabel("Correlation")
    ax.set_title("Cross-correlation: heading residual vs. lagged temperature")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lag_correlation.png", dpi=130)
    plt.close(fig)

    # --- 4. Wind-controlled multiple regression ---
    coefs, resid_after = ols(work["residual"].to_numpy(), work[["temp_c", "wind_kn"]].to_numpy())
    intercept_mr, temp_coef_mr, wind_coef_mr = coefs
    ss_res = np.sum(resid_after ** 2)
    ss_tot = np.sum((work["residual"].to_numpy() - work["residual"].mean()) ** 2)
    r2_mr = 1 - ss_res / ss_tot

    lines.append("## Wind-controlled multiple regression: residual ~ temp_c + wind_kn")
    lines.append(f"intercept = {intercept_mr:.4f}, temp_coef = {temp_coef_mr:.4f} deg/C, wind_coef = {wind_coef_mr:.4f} deg/kn")
    lines.append(f"R^2 = {r2_mr:.4f}  (vs. R^2 = {r**2:.4f} for temp alone)")
    lines.append("")

    # --- 5. Hysteresis check: rising vs falling temperature ---
    dtemp = work["temp_c"].diff().rolling(12, min_periods=6).mean()  # smoothed slope, ~1min window at 5s cadence
    rising = work[dtemp > 0.001]
    falling = work[dtemp < -0.001]
    if len(rising) > 100 and len(falling) > 100:
        s_r, i_r, r_r, *_ = stats.linregress(rising["temp_c"], rising["residual"])
        s_f, i_f, r_f, *_ = stats.linregress(falling["temp_c"], falling["residual"])
        lines.append("## Hysteresis check (separate fits for rising vs. falling temperature)")
        lines.append(f"Rising:  slope = {s_r:.4f} deg/C, r^2 = {r_r**2:.4f}, n = {len(rising)}")
        lines.append(f"Falling: slope = {s_f:.4f} deg/C, r^2 = {r_f**2:.4f}, n = {len(falling)}")
        lines.append(f"Slope difference (rising - falling): {s_r - s_f:.4f} deg/C")
        lines.append("")

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(rising["temp_c"], rising["residual"], s=2, alpha=0.15, color="tab:orange", label="rising T")
        ax.scatter(falling["temp_c"], falling["residual"], s=2, alpha=0.15, color="tab:blue", label="falling T")
        xs = np.linspace(work["temp_c"].min(), work["temp_c"].max(), 100)
        ax.plot(xs, s_r * xs + i_r, color="darkorange")
        ax.plot(xs, s_f * xs + i_f, color="darkblue")
        ax.set_xlabel("Temperature (C)")
        ax.set_ylabel("Heading residual (deg)")
        ax.set_title("Hysteresis: residual vs temp, rising vs falling")
        ax.legend()
        fig.tight_layout()
        fig.savefig(PLOT_DIR / "hysteresis.png", dpi=130)
        plt.close(fig)
    else:
        lines.append("## Hysteresis check: insufficient data in rising/falling subsets")
        lines.append("")

    # --- 6. Diurnal pattern check ---
    work_local = work.copy()
    work_local["hour"] = work_local.index.hour
    hourly = work_local.groupby("hour")[["residual", "temp_c"]].mean()
    lines.append("## Diurnal pattern (hourly mean, UTC hour of day)")
    lines.append(hourly.to_string())
    lines.append("")

    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(hourly.index, hourly["residual"], color="tab:blue", marker="o", label="residual")
    ax1.set_ylabel("Mean heading residual (deg)", color="tab:blue")
    ax1.set_xlabel("Hour of day (UTC)")
    ax2 = ax1.twinx()
    ax2.plot(hourly.index, hourly["temp_c"], color="tab:red", marker="o", label="temp")
    ax2.set_ylabel("Mean temperature (C)", color="tab:red")
    ax1.set_title("Diurnal pattern: residual and temperature by hour")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "diurnal_pattern.png", dpi=130)
    plt.close(fig)

    lines.append("## Plots written")
    for p in sorted(PLOT_DIR.glob("*.png")):
        lines.append(f"- plots/{p.name}")

    (Path(__file__).parent / "correlation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
