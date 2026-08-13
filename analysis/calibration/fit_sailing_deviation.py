"""
Fits a deviation curve to the 2026-08-12 sailing-configuration data
(engine up/forward -- the position the original magfit used), and compares
it against the 2026-08-10 motoring-configuration curve (clean_data.py /
fit_deviation.py).

Unlike the motoring session, leeway is real here and expected to correlate
with TWA rather than heading -- this script explicitly checks for that
confound (see "TWA confound check" below) rather than assuming the naive
COGt-HDGt difference is clean deviation.

Coverage caveat: a single race course does not visit all 12 target
headings -- see sailing_data_quality_summary.md for the gaps. This is a
first sailing-mode data point, not a finished table; more sessions across
different wind directions are still needed (see the handoff/TODO).

Reads data/clean_sailing.csv (from clean_sailing_data.py) and reuses the
motoring fit from fit_deviation.py for comparison. Writes:
  - plots/sailing_vs_motoring_deviation.png
  - plots/sailing_deviation_twa_confound.png
  - sailing_deviation_summary.md
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

from fit_deviation import (  # noqa: E402
    _design_matrix, eval_curve, fit_deviation_curve, load_clean as load_clean_motoring,
)

TABLE_HEADINGS_DEG = list(range(0, 360, 30))


def load_clean_sailing() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_sailing.csv", index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def fit_with_twa(heading_deg: np.ndarray, twa_deg: np.ndarray, dev_deg: np.ndarray):
    """Fourier(heading) + linear TWA term -- a simple, transparent proxy for
    leeway/wind-angle-linked error, not a rigorous leeway model."""
    X_hdg = _design_matrix(heading_deg)
    X = np.column_stack([X_hdg, twa_deg])
    coefs, *_ = np.linalg.lstsq(X, dev_deg, rcond=None)
    pred = X @ coefs
    resid = dev_deg - pred
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((dev_deg - dev_deg.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    return coefs, resid, r2  # coefs = [A, B, C, D, E, F(TWA)]


def main():
    sail = load_clean_sailing()
    n_before_twa_drop = len(sail)
    sail = sail.dropna(subset=["TWA"]).copy()  # TWA publishes less often than HDGt/COGt
    n_twa_dropped = n_before_twa_drop - len(sail)
    heading = sail["HDGt"].to_numpy()
    dev = sail["dev_deg"].to_numpy()
    twa = sail["TWA"].to_numpy()

    # Naive heading-only fit (same model as the motoring curve)
    coefs_naive, resid_naive, r2_naive = fit_deviation_curve(heading, dev)
    resid_vs_twa = float(np.corrcoef(resid_naive, twa)[0, 1])
    dev_vs_twa = float(np.corrcoef(dev, twa)[0, 1])

    # Heading + TWA joint fit
    coefs_twa, resid_twa, r2_twa = fit_with_twa(heading, twa, dev)
    A, B, C, D, E, F = coefs_twa

    # Motoring curve, refit fresh for a same-basis comparison
    mot = load_clean_motoring()
    coefs_mot, _, r2_mot = fit_deviation_curve(mot["HDGt"].to_numpy(), mot["dev_deg"].to_numpy())

    table = pd.DataFrame({
        "heading_deg": TABLE_HEADINGS_DEG,
        "sailing_naive_deg": eval_curve(coefs_naive, TABLE_HEADINGS_DEG).round(2),
        "sailing_heading_component_deg": (_design_matrix(TABLE_HEADINGS_DEG) @ coefs_twa[:5]).round(2),
        "motoring_deg": eval_curve(coefs_mot, TABLE_HEADINGS_DEG).round(2),
    })
    table.to_csv(DATA_DIR / "sailing_vs_motoring_table.csv", index=False)

    # --- Plot 1: sailing (naive) vs. motoring curves, with raw sailing scatter ---
    bin_means = sail.groupby(sail["heading_bin_30"])["dev_deg"].agg(["mean", "std", "count"])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(sail["HDGt"], sail["dev_deg"], s=6, alpha=0.35, color="gray",
               label="sailing, raw (steady-state)")
    ax.errorbar(bin_means.index + 15, bin_means["mean"], yerr=bin_means["std"],
                fmt="o", color="tab:green", capsize=3, label="sailing, 30 deg bin mean +/- std")
    xs = np.linspace(0, 360, 361)
    ax.plot(xs, eval_curve(coefs_naive, xs), color="tab:green", lw=2,
            label=f"sailing fit, naive (R^2={r2_naive:.3f})")
    ax.plot(xs, eval_curve(coefs_mot, xs), color="tab:red", lw=2, ls="--",
            label=f"motoring fit, for comparison (R^2={r2_mot:.3f})")
    ax.axhline(0, color="black", lw=0.6, alpha=0.5)
    ax.set_xlabel("Compass heading, HDGt (deg)")
    ax.set_ylabel("Deviation, COGt - HDGt (deg)")
    ax.set_title("Sailing-configuration deviation vs. heading, vs. motoring curve")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, 360)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "sailing_vs_motoring_deviation.png", dpi=130)
    plt.close(fig)

    # --- Plot 2: TWA confound -- residual after the naive heading-only fit vs. TWA ---
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sc = ax.scatter(twa, resid_naive, c=heading, cmap="hsv", s=10, alpha=0.6)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("HDGt (deg)")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("True wind angle, TWA (deg)")
    ax.set_ylabel("Residual after naive heading-only fit (deg)")
    ax.set_title(f"TWA confound check: residual vs. TWA (r={resid_vs_twa:.2f})")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "sailing_deviation_twa_confound.png", dpi=130)
    plt.close(fig)

    lines = [
        "# Sailing-Configuration Deviation — Fit Summary (PRELIMINARY)",
        "",
        "**Preliminary, not the final table.** Single race session, engine "
        "up/forward (matches the original `magfit` position). Coverage gaps "
        "at 30-90 deg and 300-330 deg (see `sailing_data_quality_summary.md`), "
        "and a real TWA confound (below) mean this needs more sessions across "
        "different wind directions before it's a deployment candidate. See "
        "`morticia-project/handoffs/heading-deviation-table-investigation.md`.",
        "",
        "## TWA confound check",
        f"- `dev_deg` vs. `TWA`, before any fit: r = {dev_vs_twa:.3f}",
        f"- Residual vs. `TWA`, after the naive heading-only fit: r = {resid_vs_twa:.3f}",
        "",
        "That's a real correlation, much stronger than anything seen in the "
        "motoring data (where tack-independence was the whole argument for "
        "trusting COGt as heading). It means a meaningful part of the naive "
        "`sailing_naive_deg` curve below is wind-angle-linked (leeway, or "
        "something else that tracks TWA), not pure heading-locked compass "
        "deviation, and a single race course does not vary TWA independently "
        "of heading enough to cleanly separate the two (each leg tends to "
        "hold both roughly constant together).",
        "",
        "**Important:** the residual-vs-TWA correlation drops to ~0 *after* "
        "the heading-only fit -- but that is NOT evidence the confound is "
        "resolved. It's the expected signature of heading and TWA being "
        "collinear in a single session (each leg pins both together), which "
        "means the heading-only model can silently absorb TWA-driven "
        "variation into its heading terms rather than leaving it in the "
        "residual where it would be visible. The near-zero residual "
        "correlation is consistent with the confound being unresolvable from "
        "this session alone, not with it being absent. Only more sessions "
        "that revisit the same headings at different TWA (different wind "
        "directions) can actually break this collinearity.",
        "",
        "## Two fits",
        "1. **Naive** — same 5-coefficient heading-only model as the motoring "
        "curve. R^2 = " + f"{r2_naive:.4f}. Confounded with TWA per above.",
        "2. **Heading + TWA** — adds a simple linear TWA term "
        "(`dev = A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h) + F*TWA`) "
        f"as a transparent proxy for wind-angle-linked error, not a rigorous "
        f"leeway model. R^2 = {r2_twa:.4f} (vs. {r2_naive:.4f} without TWA). "
        f"TWA coefficient F = {F:.4f} deg/deg. The heading-only component of "
        "this fit (columns A-E) is the closer-to-clean estimate of actual "
        "deviation, but still built on one session's worth of heading/TWA "
        "combinations.",
        "",
        "## Comparison to the motoring curve",
        f"Motoring curve (2026-08-10, refit here for a same-basis comparison): "
        f"R^2 = {r2_mot:.4f}.",
        "",
        table.to_string(index=False),
        "",
        "The two curves do not resemble each other in shape or magnitude at "
        "the headings both cover — consistent with the engine-position "
        "hypothesis (different physical configuration, different hard-iron "
        "picture), though this single sailing session isn't a clean enough "
        "comparison to call that confirmed.",
        "",
        "## Plots",
        "- `plots/sailing_vs_motoring_deviation.png` — sailing raw/binned/fit vs. motoring fit",
        "- `plots/sailing_deviation_twa_confound.png` — residual vs. TWA, colored by heading",
    ]

    (BASE_DIR / "sailing_deviation_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
