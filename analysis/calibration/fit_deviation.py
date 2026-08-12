"""
Fits a smooth deviation curve (constant + semicircular + quadrantal terms,
the standard maritime deviation-curve model) to the motoring-configuration
diagnostic dataset, and evaluates it at 12 headings (every 30 deg).

DIAGNOSTIC ONLY -- engine was down/aft (~18in from its sailing position),
not the position the original magfit calibration used. Not intended for
firmware deployment; see data_quality_summary.md and the accompanying
project handoff for why.

Reads data/clean_motoring.csv (from clean_data.py). Writes:
  - data/motoring_deviation_table.csv (12-point table)
  - plots/motoring_deviation_curve.png
  - plots/motoring_deviation_residuals.png
  - deviation_summary.md
"""

import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PLOT_DIR = BASE_DIR / "plots"
PLOT_DIR.mkdir(exist_ok=True)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TABLE_HEADINGS_DEG = list(range(0, 360, 30))


def load_clean() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_motoring.csv", index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _design_matrix(heading_deg) -> np.ndarray:
    theta = np.deg2rad(np.asarray(heading_deg, dtype=float))
    return np.column_stack([
        np.ones_like(theta),
        np.sin(theta), np.cos(theta),
        np.sin(2 * theta), np.cos(2 * theta),
    ])


def fit_deviation_curve(heading_deg: np.ndarray, dev_deg: np.ndarray):
    """Least-squares fit: dev = A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h)."""
    X = _design_matrix(heading_deg)
    coefs, *_ = np.linalg.lstsq(X, dev_deg, rcond=None)
    pred = X @ coefs
    resid = dev_deg - pred
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((dev_deg - dev_deg.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    return coefs, resid, r2


def eval_curve(coefs: np.ndarray, heading_deg) -> np.ndarray:
    return _design_matrix(heading_deg) @ coefs


def main():
    df = load_clean()
    heading = df["HDGt"].to_numpy()
    dev = df["dev_deg"].to_numpy()

    coefs, resid, r2 = fit_deviation_curve(heading, dev)
    A, B, C, D, E = coefs
    df = df.copy()
    df["dev_resid"] = resid

    def safe_corr(a: np.ndarray, b: pd.Series) -> float:
        mask = np.isfinite(a) & b.notna().to_numpy()
        return float(np.corrcoef(a[mask], b.to_numpy()[mask])[0, 1])

    resid_vs_sog = safe_corr(resid, df["SOG"])
    resid_vs_roll = safe_corr(resid, df["ROLL"])
    n_roll_missing = int(df["ROLL"].isna().sum())

    table = pd.DataFrame({
        "heading_deg": TABLE_HEADINGS_DEG,
        "deviation_deg": eval_curve(coefs, TABLE_HEADINGS_DEG),
    })
    table["deviation_deg"] = table["deviation_deg"].round(2)
    table.to_csv(DATA_DIR / "motoring_deviation_table.csv", index=False)

    # --- Plot 1: raw scatter + binned means + fitted curve ---
    bin_means = df.groupby(df["heading_bin_30"])["dev_deg"].agg(["mean", "std", "count"])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(df["HDGt"], df["dev_deg"], s=3, alpha=0.15, color="gray",
               label="raw (steady-state)")
    ax.errorbar(bin_means.index + 15, bin_means["mean"], yerr=bin_means["std"],
                fmt="o", color="tab:blue", capsize=3, label="30 deg bin mean +/- std")
    xs = np.linspace(0, 360, 361)
    ax.plot(xs, eval_curve(coefs, xs), color="tab:red", lw=2,
            label=f"fitted curve (R^2={r2:.3f})")
    ax.set_xlabel("Compass heading, HDGt (deg)")
    ax.set_ylabel("Deviation, COGt - HDGt (deg)")
    ax.set_title("Motoring-configuration deviation vs. heading (diagnostic)")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, 360)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "motoring_deviation_curve.png", dpi=130)
    plt.close(fig)

    # --- Plot 2: residuals after the fit ---
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.scatter(df["HDGt"], df["dev_resid"], s=3, alpha=0.2, color="tab:purple")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Compass heading, HDGt (deg)")
    ax.set_ylabel("Residual after fit (deg)")
    ax.set_title("Residual after 5-coefficient deviation fit")
    ax.set_xlim(0, 360)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "motoring_deviation_residuals.png", dpi=130)
    plt.close(fig)

    lines = [
        "# Motoring-Configuration Deviation — Fit Summary (DIAGNOSTIC ONLY)",
        "",
        "**Not a firmware deliverable.** Engine was down and ~18in aft of its "
        "sailing position during collection -- a different hard-iron configuration "
        "than the original magfit calibration (engine up/forward). This curve "
        "characterizes deviation *in the motoring configuration* and exists to "
        "(a) validate the analysis pipeline against a case with a trustworthy "
        "heading reference, and (b) support the engine-position hypothesis for "
        "why today's data differs so much from the previously-logged 6-18 deg "
        "estimate. See `data_quality_summary.md` for data-quality detail.",
        "",
        "## Model",
        "`deviation(heading) = A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h)`",
        "(constant + semicircular + quadrantal terms -- the standard maritime "
        "deviation-curve form.)",
        "",
        f"- A (constant) = {A:.3f} deg",
        f"- B, C (semicircular) = {B:.3f}, {C:.3f} deg",
        f"- D, E (quadrantal) = {D:.3f}, {E:.3f} deg",
        f"- R^2 = {r2:.4f}  (n={len(df)})",
        "",
        "## Residual checks",
        f"- residual vs. SOG: r = {resid_vs_sog:.3f}",
        f"- residual vs. ROLL: r = {resid_vs_roll:.3f} "
        f"(n={len(df) - n_roll_missing} of {len(df)}; {n_roll_missing} rows missing ROLL)",
        "(Both near zero is expected/good -- means the fitted curve is capturing "
        "essentially all of the heading-locked signal, with nothing obviously "
        "left over that tracks boat speed or heel.)",
        "",
        "## 12-point table (every 30 deg, from the fitted curve)",
        table.to_string(index=False),
        "",
        "## Plots",
        "- `plots/motoring_deviation_curve.png` -- raw scatter, binned means, fitted curve",
        "- `plots/motoring_deviation_residuals.png` -- residuals after the fit",
    ]

    (BASE_DIR / "deviation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
