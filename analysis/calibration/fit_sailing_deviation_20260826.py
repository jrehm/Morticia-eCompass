"""
Fits a deviation curve to the 2026-08-26 race session (eCompass/HDGmE basis
-- see clean_sailing_data_20260826.py for why HDGmE, not HDGt), and compares
it against both prior curves: the 2026-08-10 motoring session and the
2026-08-12 sailing session (both originally fit on HDGt, back when HDGt
still meant the eCompass -- same physical quantity as today's HDGmE, so the
comparison is apples-to-apples).

Same TWA-confound caveat as the 2026-08-12 session applies here, and shows
up just as strongly (see below) -- a single race course does not vary TWA
independently of heading, so a heading-only fit can silently absorb
TWA-driven variation. Not resolved by this session either; needs multiple
sessions across different wind directions (see TODO.md).

Reads data/clean_sailing_20260826.csv (from clean_sailing_data_20260826.py),
data/clean_motoring.csv, and data/clean_sailing.csv (the 2026-08-12 set) for
comparison. Writes:
  - plots/sailing_20260826_vs_prior_deviation.png
  - plots/sailing_20260826_twa_confound.png
  - sailing_deviation_summary_20260826.md
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


def load_clean_sailing_20260826() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_sailing_20260826.csv", index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def load_clean_sailing_20260812() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "clean_sailing.csv", index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def fit_with_twa(heading_deg, twa_deg, dev_deg):
    """Same transparent heading+TWA proxy model as fit_sailing_deviation.py."""
    X_hdg = _design_matrix(heading_deg)
    X = np.column_stack([X_hdg, twa_deg])
    coefs, *_ = np.linalg.lstsq(X, dev_deg, rcond=None)
    pred = X @ coefs
    resid = dev_deg - pred
    ss_res = np.sum(resid ** 2)
    ss_tot = np.sum((dev_deg - dev_deg.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    return coefs, resid, r2


def main():
    sail = load_clean_sailing_20260826()
    n_before_twa_drop = len(sail)
    sail = sail.dropna(subset=["TWA"]).copy()
    n_twa_dropped = n_before_twa_drop - len(sail)
    heading = sail["HDGmE"].to_numpy()
    dev = sail["dev_deg"].to_numpy()
    twa = sail["TWA"].to_numpy()

    coefs_naive, resid_naive, r2_naive = fit_deviation_curve(heading, dev)
    resid_vs_twa = float(np.corrcoef(resid_naive, twa)[0, 1])
    dev_vs_twa = float(np.corrcoef(dev, twa)[0, 1])

    coefs_twa, resid_twa, r2_twa = fit_with_twa(heading, twa, dev)
    A, B, C, D, E, F = coefs_twa

    mot = load_clean_motoring()
    coefs_mot, _, r2_mot = fit_deviation_curve(mot["HDGt"].to_numpy(), mot["dev_deg"].to_numpy())

    sail0812 = load_clean_sailing_20260812()
    coefs_0812, _, r2_0812 = fit_deviation_curve(
        sail0812["HDGt"].to_numpy(), sail0812["dev_deg"].to_numpy()
    )

    table = pd.DataFrame({
        "heading_deg": TABLE_HEADINGS_DEG,
        "sailing_20260826_naive_deg": eval_curve(coefs_naive, TABLE_HEADINGS_DEG).round(2),
        "sailing_20260826_heading_component_deg":
            (_design_matrix(TABLE_HEADINGS_DEG) @ coefs_twa[:5]).round(2),
        "sailing_20260812_deg": eval_curve(coefs_0812, TABLE_HEADINGS_DEG).round(2),
        "motoring_20260810_deg": eval_curve(coefs_mot, TABLE_HEADINGS_DEG).round(2),
    })
    table.to_csv(DATA_DIR / "sailing_20260826_vs_prior_table.csv", index=False)

    # --- Plot 1: three curves ---
    bin_means = sail.groupby(sail["heading_bin_30"])["dev_deg"].agg(["mean", "std", "count"])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(sail["HDGmE"], sail["dev_deg"], s=6, alpha=0.35, color="gray",
               label="2026-08-26, raw (steady-state)")
    ax.errorbar(bin_means.index + 15, bin_means["mean"], yerr=bin_means["std"],
                fmt="o", color="tab:green", capsize=3, label="2026-08-26, 30 deg bin mean +/- std")
    xs = np.linspace(0, 360, 361)
    ax.plot(xs, eval_curve(coefs_naive, xs), color="tab:green", lw=2,
            label=f"2026-08-26 fit, naive (R^2={r2_naive:.3f})")
    ax.plot(xs, eval_curve(coefs_0812, xs), color="tab:orange", lw=2, ls="--",
            label=f"2026-08-12 sailing fit, for comparison (R^2={r2_0812:.3f})")
    ax.plot(xs, eval_curve(coefs_mot, xs), color="tab:red", lw=2, ls=":",
            label=f"2026-08-10 motoring fit, for comparison (R^2={r2_mot:.3f})")
    ax.axhline(0, color="black", lw=0.6, alpha=0.5)
    ax.set_xlabel("eCompass heading, HDGmE (deg)")
    ax.set_ylabel("Deviation, COGt - HDGmE (deg)")
    ax.set_title("2026-08-26 eCompass deviation vs. heading, vs. prior sessions")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, 360)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "sailing_20260826_vs_prior_deviation.png", dpi=130)
    plt.close(fig)

    # --- Plot 2: TWA confound ---
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sc = ax.scatter(twa, resid_naive, c=heading, cmap="hsv", s=10, alpha=0.6)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("HDGmE (deg)")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("True wind angle, TWA (deg)")
    ax.set_ylabel("Residual after naive heading-only fit (deg)")
    ax.set_title(f"2026-08-26 TWA confound check: residual vs. TWA (r={resid_vs_twa:.2f})")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "sailing_20260826_twa_confound.png", dpi=130)
    plt.close(fig)

    lines = [
        "# 2026-08-26 Race Session — eCompass Deviation Fit Summary (PRELIMINARY)",
        "",
        "**Preliminary, not the final table.** Second sailing-mode session (after "
        "2026-08-12). Fit against `HDGmE` (eCompass raw heading), not `HDGt` -- see "
        "`clean_sailing_data_20260826.py` docstring for why that changed. Coverage "
        "gaps at 150-210 deg and 330-360 deg this session (different from "
        "2026-08-12's 30-90/300-330 gaps -- together the two sessions are filling in "
        "different parts of the circle, still not the full 12 headings from either "
        "alone). TWA confound (below) is, if anything, stronger than 2026-08-12's.",
        "",
        f"n dropped for missing TWA: {n_twa_dropped} of {n_before_twa_drop}",
        "",
        "## TWA confound check",
        f"- `dev_deg` vs. `TWA`, before any fit: r = {dev_vs_twa:.3f}",
        f"- Residual vs. `TWA`, after the naive heading-only fit: r = {resid_vs_twa:.3f}",
        "",
        f"Raw correlation (r={dev_vs_twa:.3f}) is comparable in strength to "
        "2026-08-12's (r=-0.68), same underlying issue: a single race course doesn't "
        "vary TWA independently of heading, so this session alone still can't "
        "cleanly separate real eCompass deviation from leeway. Two sessions now "
        "showing the same confound, from different course/wind combinations -- "
        "useful confirmation the problem is real and structural, not session-specific, "
        "but doesn't yet resolve it (that needs comparing the *same heading bins* "
        "across sessions with different TWA at that heading, not just stacking more "
        "single-session fits).",
        "",
        "## Two fits",
        "1. **Naive** — heading-only 5-coefficient model. "
        f"R^2 = {r2_naive:.4f}. Confounded with TWA per above.",
        "2. **Heading + TWA** — adds a linear TWA term. "
        f"R^2 = {r2_twa:.4f} (vs. {r2_naive:.4f} without TWA). "
        f"TWA coefficient F = {F:.4f} deg/deg.",
        "",
        "## Comparison to prior sessions",
        f"- 2026-08-12 sailing (HDGt, back when HDGt meant the eCompass): R^2 = {r2_0812:.4f}",
        f"- 2026-08-10 motoring (diagnostic only): R^2 = {r2_mot:.4f}",
        "",
        table.to_string(index=False),
        "",
        "The 2026-08-26 curve does not resemble either prior curve closely in the "
        "headings where more than one session has coverage -- with two confounded, "
        "coverage-gapped sessions and a sensor whose fit error has drifted from ~3% "
        "to ~7% since relocation, this is genuinely inconclusive on its own, not a "
        "sign any particular prior curve was wrong. More sessions, specifically "
        "ones that revisit already-covered headings under different wind, are what "
        "would actually start to resolve this.",
        "",
        "## eCompass vs. fluxgate: the bigger new finding this session",
        "Independent of all of the above (no COGt/leeway involved at all): `HDGmE` "
        "and `HDGmF` (fluxgate raw) disagree by up to ~46 deg at times this session, "
        "varying with heading rather than sitting at a fixed offset -- see "
        "`sailing_data_quality_summary_20260826.md`. Since the fluxgate is now the "
        "trusted live heading source, this bounds how far off the eCompass may "
        "currently be running in absolute terms, separately from anything this "
        "deviation-table exercise is trying to measure via COGt.",
        "",
        "## Plots",
        "- `plots/sailing_20260826_vs_prior_deviation.png`",
        "- `plots/sailing_20260826_twa_confound.png`",
    ]

    (BASE_DIR / "sailing_deviation_summary_20260826.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
