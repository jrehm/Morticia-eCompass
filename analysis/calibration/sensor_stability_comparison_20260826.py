"""
Direct relative comparison of HDGmE (eCompass) vs. HDGmF (fluxgate) against
COGt, prompted by Jeff: even including the GPS-malfunction-affected COG data
(what survived Jeff's manual cleanup -- mostly Starboard tack, per the
tack-correlated dropout already documented), how do the two magnetic sources
compare to each other, and which looks more internally consistent?

Both HDGmE and HDGmF carry uncorrected mounting offsets -- this is NOT an
attempt to determine either sensor's true accuracy. It's a same-COG,
same-timestamps, same-methodology comparison of which one's relationship to
COGt is tighter/more explainable by a smooth heading-locked curve -- a
stability/internal-consistency proxy, not a ground-truth accuracy call.

Minimal filtering deliberately used here (SOG>=1kn, frozen-COG glitch
excluded, nothing else) -- no steady-state rolling-std filter, so this
includes rows the main pipeline's steady-state filter would have dropped.
That's intentional per Jeff's request to "throw in" the available COG data
rather than the more conservative steady-state subset used elsewhere.

Reads sailing_20260826_1855_to_1950_cleaned.csv (this directory) directly.
Writes plots/sensor_vs_cog_comparison.png and
sensor_stability_comparison_20260826.md.
"""

import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).parent
PLOT_DIR = BASE_DIR / "plots"
PLOT_DIR.mkdir(exist_ok=True)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAW_CSV = BASE_DIR / "sailing_20260826_1855_to_1950_cleaned.csv"
SESSION_DATE = "2026-08-26"


def circular_diff_deg(a_deg, b_deg):
    return (a_deg - b_deg + 180) % 360 - 180


def circular_rolling_std_deg(heading_deg, window):
    theta = np.deg2rad(heading_deg)
    sin_r = np.sin(theta).rolling(window, center=True).mean()
    cos_r = np.cos(theta).rolling(window, center=True).mean()
    resultant = np.sqrt(sin_r ** 2 + cos_r ** 2)
    return np.rad2deg(np.sqrt(np.clip(-2 * np.log(resultant), 0, None)))


def design_matrix(heading_deg):
    theta = np.deg2rad(np.asarray(heading_deg, dtype=float))
    return np.column_stack([
        np.ones_like(theta), np.sin(theta), np.cos(theta),
        np.sin(2 * theta), np.cos(2 * theta),
    ])


def fit_curve(heading_deg, dev_deg):
    X = design_matrix(heading_deg)
    coef, *_ = np.linalg.lstsq(X, dev_deg, rcond=None)
    pred = X @ coef
    resid = dev_deg - pred
    r2 = 1 - np.sum(resid ** 2) / np.sum((dev_deg - dev_deg.mean()) ** 2)
    return coef, resid, r2


def eval_curve(coef, heading_deg):
    return design_matrix(heading_deg) @ coef


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    df = df.dropna(how="all").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(
        f"{SESSION_DATE} " + df["timestamp"], format="%Y-%m-%d %I:%M:%S %p"
    )
    return df.set_index("timestamp").sort_index()


def main():
    df = load_raw()

    common = df.dropna(subset=["COGt", "HDGmE", "HDGmF", "SOG"]).copy()
    common = common[common["SOG"] >= 1.0]
    n_common = len(common)
    frozen = (common["COGt"].diff() == 0) & (common["SOG"].diff() == 0)
    n_frozen = int(frozen.sum())
    sub = common[~frozen].copy()

    sub["dev_E"] = circular_diff_deg(sub["COGt"], sub["HDGmE"])
    sub["dev_F"] = circular_diff_deg(sub["COGt"], sub["HDGmF"])

    coef_E, resid_E, r2_E = fit_curve(sub["HDGmE"].to_numpy(), sub["dev_E"].to_numpy())
    coef_F, resid_F, r2_F = fit_curve(sub["HDGmF"].to_numpy(), sub["dev_F"].to_numpy())

    sub["bin_E"] = (sub["HDGmE"] // 30 * 30).astype(int)
    sub["bin_F"] = (sub["HDGmF"] // 30 * 30).astype(int)
    be = sub.groupby("bin_E")["dev_E"].agg(["mean", "std", "count"])
    bf = sub.groupby("bin_F")["dev_F"].agg(["mean", "std", "count"])
    be_robust = be[be["count"] >= 20]
    bf_robust = bf[bf["count"] >= 20]

    df["hdgme_rollstd"] = circular_rolling_std_deg(df["HDGmE"], "21s")
    df["hdgmf_rollstd"] = circular_rolling_std_deg(df["HDGmF"], "21s")
    both_idx = df.dropna(subset=["HDGmE", "HDGmF"]).index

    # --- Plot: both sensors vs. COGt, same timestamps ---
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(sub["HDGmE"], sub["dev_E"], s=6, alpha=0.3, color="tab:blue",
               label="eCompass raw (COGt-HDGmE)")
    ax.scatter(sub["HDGmF"], sub["dev_F"], s=6, alpha=0.3, color="tab:orange",
               label="fluxgate raw (COGt-HDGmF)")
    xs = np.linspace(0, 360, 361)
    ax.plot(xs, eval_curve(coef_E, xs), color="tab:blue", lw=2.5,
            label=f"eCompass fit (R2={r2_E:.3f}, resid std={resid_E.std():.2f})")
    ax.plot(xs, eval_curve(coef_F, xs), color="tab:orange", lw=2.5,
            label=f"fluxgate fit (R2={r2_F:.3f}, resid std={resid_F.std():.2f})")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("Own heading (deg)")
    ax.set_ylabel("COGt - own heading (deg)")
    ax.set_title(f"eCompass vs fluxgate: deviation from COGt, same {len(sub)} timestamps")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_xlim(0, 360)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "sensor_vs_cog_comparison.png", dpi=130)
    plt.close(fig)

    lines = [
        "# eCompass vs. Fluxgate — Relative Stability Comparison (2026-08-26)",
        "",
        "Prompted by Jeff: including whatever COGt data survived the GPS "
        "malfunction (mostly Starboard tack, per "
        "`sailing_data_quality_summary_20260826.md`), how do HDGmE and HDGmF "
        "compare *to each other*, and which looks more stable/correct? Both "
        "carry uncorrected mounting offsets, so this is a same-COG, "
        "same-timestamps comparison of internal consistency, not an accuracy "
        "verdict against ground truth.",
        "",
        f"n = {n_common} rows with COGt/HDGmE/HDGmF/SOG all present, SOG>=1kn "
        f"({n_frozen} frozen-COG glitch rows excluded, n={len(sub)} used below). "
        "Deliberately minimal filtering -- no steady-state rolling-std filter "
        "like the main pipeline uses, per Jeff's request to include the "
        "available COG data rather than the more conservative subset.",
        "",
        "## Raw comparison (no curve fit)",
        f"- `COGt - HDGmE`: mean={sub['dev_E'].mean():.2f} deg, std={sub['dev_E'].std():.2f} deg",
        f"- `COGt - HDGmF`: mean={sub['dev_F'].mean():.2f} deg, std={sub['dev_F'].std():.2f} deg",
        "Raw std is close between the two -- not very discriminating on its own, "
        "since both are dominated by the real heading-locked deviation signal "
        "(different for each sensor, since they're physically different "
        "sensors in different locations), not noise.",
        "",
        "## Heading-only 5-coefficient deviation-curve fit, same rows",
        "Same model used throughout this project "
        "(`A + B*sin(h) + C*cos(h) + D*sin(2h) + E*cos(2h)`), fit separately "
        "to each sensor's own COGt-referenced deviation on the identical "
        f"{len(sub)} timestamps:",
        f"- eCompass (HDGmE basis): R^2 = {r2_E:.4f}, residual std = {resid_E.std():.3f} deg",
        f"- Fluxgate (HDGmF basis): R^2 = {r2_F:.4f}, residual std = {resid_F.std():.3f} deg",
        "",
        "Fluxgate fits a bit tighter -- higher R^2, lower residual std -- "
        "meaning its relationship to COGt is more fully explained by a smooth "
        "heading-locked curve, with less left over as scatter.",
        "",
        "## Within-heading-bin scatter (30 deg bins, robust bins only, n>=20)",
        "Same idea from a different angle -- how tightly clustered is each "
        "sensor's deviation at a fixed heading:",
        "",
        "eCompass:",
        be_robust.to_string(),
        f"avg within-bin std: {be_robust['std'].mean():.3f} deg",
        "",
        "Fluxgate:",
        bf_robust.to_string(),
        f"avg within-bin std: {bf_robust['std'].mean():.3f} deg",
        "",
        "## Moment-to-moment jitter (independent of COGt entirely)",
        "21s rolling circular std of each raw heading signal, same timestamps "
        "(own-signal noise, nothing to do with COG or deviation):",
        f"- eCompass: mean={df.loc[both_idx, 'hdgme_rollstd'].mean():.3f} deg, "
        f"median={df.loc[both_idx, 'hdgme_rollstd'].median():.3f} deg",
        f"- Fluxgate: mean={df.loc[both_idx, 'hdgmf_rollstd'].mean():.3f} deg, "
        f"median={df.loc[both_idx, 'hdgmf_rollstd'].median():.3f} deg",
        "Essentially a wash on this metric -- mean slightly favors the "
        "fluxgate, median slightly favors the eCompass, neither by much. "
        "The two sensors' moment-to-moment noise floor looks similar; the "
        "gap shows up specifically in how well each one's relationship to "
        "COGt is explained by a clean curve, not in raw jitter.",
        "",
        "## Verdict",
        "Modest, consistent edge to the **fluxgate** on every metric that "
        "involves COGt (fit R^2, residual std, within-bin std) -- roughly "
        "5-10% tighter across the board, not a dramatic gap. Both sensors "
        "show clean, well-behaved deviation curves (R^2 > 0.8 for both) -- "
        "this isn't \"one sensor is garbage,\" it's \"both are internally "
        "consistent, the fluxgate slightly more so.\" Consistent with, though "
        "not a dramatic confirmation of, the decision to make the fluxgate "
        "primary.",
        "",
        "**Caveats:** (1) both curves are built against the *same* COGt, so "
        "whatever leeway/TWA confound and Starboard-tack skew is in that "
        "reference (see `sailing_data_quality_summary_20260826.md` and "
        "`sailing_deviation_summary_20260826.md`) affects both sensors "
        "identically -- fair for a head-to-head comparison, but neither R^2 "
        "should be read as \"accuracy against true heading.\" (2) Single "
        "session, heavily Starboard-tack-skewed as a side effect of which COG "
        "data survived the GPS malfunction -- not a claim about behavior "
        "across the full heading circle or on Port tack specifically.",
        "",
        "## Plot",
        "- `plots/sensor_vs_cog_comparison.png`",
    ]

    (BASE_DIR / "sensor_stability_comparison_20260826.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
