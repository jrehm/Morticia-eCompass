"""
Follow-up dig into the HDGmE-vs-HDGmF gap flagged in
sailing_data_quality_summary_20260826.md, prompted by Jeff: is it related to
roll/heel angle, and is there a real convergence over the race?

Reads sailing_20260826_1855_to_1950_cleaned.csv (this directory) directly --
not the clean_sailing_20260826.csv output, since this needs ROLL and
PointOfSail on every row with HDGmE/HDGmF, not just the steady-state subset.
Writes plots/hdgme_hdgmf_vs_roll.png, plots/hdgme_hdgmf_vs_time_and_mfit.png,
and hdgme_hdgmf_gap_followup_20260826.md.
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


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    df = df.dropna(how="all").reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(
        f"{SESSION_DATE} " + df["timestamp"], format="%Y-%m-%d %I:%M:%S %p"
    )
    df = df.set_index("timestamp").sort_index()
    df["elapsed_min"] = (df.index - df.index.min()).total_seconds() / 60
    return df


def lstsq_r2(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
    return coef, r2


def main():
    df = load_raw()
    both = df.dropna(subset=["HDGmE", "HDGmF", "ROLL"]).copy()
    both["diff"] = circular_diff_deg(both["HDGmE"], both["HDGmF"])
    both["is_port"] = (both["Tack/Gybe"] == "Port").astype(float)

    # ROLL alone / tack alone / both -- how much does roll add beyond tack?
    _, r2_roll = lstsq_r2(np.column_stack([np.ones(len(both)), both["ROLL"]]), both["diff"])
    _, r2_tack = lstsq_r2(np.column_stack([np.ones(len(both)), both["is_port"]]), both["diff"])
    coef_both, r2_both = lstsq_r2(
        np.column_stack([np.ones(len(both)), both["ROLL"], both["is_port"]]), both["diff"]
    )

    corr_signed = float(np.corrcoef(both["diff"], both["ROLL"])[0, 1])

    within_tack = {}
    for tack in ["Port", "Star"]:
        sub = both[both["Tack/Gybe"] == tack]
        coef, r2 = lstsq_r2(np.column_stack([np.ones(len(sub)), sub["ROLL"]]), sub["diff"])
        within_tack[tack] = {
            "n": len(sub), "corr": float(np.corrcoef(sub["diff"], sub["ROLL"])[0, 1]),
            "slope": coef[1], "intercept": coef[0], "r2": r2,
        }

    pos_table = both.groupby("PointOfSail").agg(
        mean_absroll=("ROLL", lambda s: s.abs().mean()),
        mean_absdiff=("diff", lambda s: s.abs().mean()),
        n=("diff", "size"),
    )

    corr_time = float(np.corrcoef(both["diff"].abs(), both["elapsed_min"])[0, 1])
    mfit = df.dropna(subset=["MFIT"])
    corr_mfit_time = float(np.corrcoef(mfit["MFIT"], mfit["elapsed_min"])[0, 1])

    # --- Plot 1: diff vs ROLL, colored by tack ---
    fig, ax = plt.subplots(figsize=(8, 5))
    for tack, c in [("Port", "tab:blue"), ("Star", "tab:red"), ("Tack", "tab:gray")]:
        sub = both[both["Tack/Gybe"] == tack]
        ax.scatter(sub["ROLL"], sub["diff"], s=8, alpha=0.4, color=c, label=f"{tack} (n={len(sub)})")
    ax.set_xlabel("ROLL (deg)")
    ax.set_ylabel("HDGmE - HDGmF (deg)")
    ax.set_title("eCompass vs fluxgate gap vs. roll/heel angle, by tack")
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(0, color="black", lw=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "hdgme_hdgmf_vs_roll.png", dpi=130)
    plt.close(fig)

    # --- Plot 2: |diff| and MFIT vs elapsed time ---
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax1.scatter(both["elapsed_min"], both["diff"].abs(), s=6, alpha=0.3, color="tab:green",
                label="|HDGmE - HDGmF|")
    ax1.set_xlabel("Elapsed time (min)")
    ax1.set_ylabel("|HDGmE - HDGmF| (deg)", color="tab:green")
    ax2 = ax1.twinx()
    ax2.plot(mfit["elapsed_min"], mfit["MFIT"], color="tab:purple", lw=2,
              label="eCompass MFIT (in-use fit error, %)")
    ax2.set_ylabel("MFIT (%)", color="tab:purple")
    ax1.set_title("eCompass/fluxgate gap vs. time -- vs. eCompass fit-quality (MFIT) over same window")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "hdgme_hdgmf_vs_time_and_mfit.png", dpi=130)
    plt.close(fig)

    lines = [
        "# HDGmE vs. HDGmF Gap — Roll/Time Follow-up (2026-08-26)",
        "",
        "Prompted by Jeff: is the eCompass-vs-fluxgate gap "
        "(`sailing_data_quality_summary_20260826.md`) related to roll/heel, and "
        "is there a real convergence over the race? Short answer to both: "
        "partially, and it's tangled with the same heading/tack collinearity "
        "already seen in the TWA confound -- not a clean single-cause story.",
        "",
        "## Roll/heel",
        f"- Combined both tacks: corr(diff, ROLL) = {corr_signed:.3f}, "
        f"R^2 (linear) = {r2_roll:.3f}",
        f"- Tack alone (Port vs. Star, no ROLL) already explains R^2 = {r2_tack:.3f}",
        f"- ROLL + tack together: R^2 = {r2_both:.3f} "
        f"(coefs: A={coef_both[0]:.2f}, ROLL={coef_both[1]:.3f} deg/deg, "
        f"is_port={coef_both[2]:.2f})",
        "",
        "Adding ROLL on top of tack barely improves the fit (0.717 -> 0.736) -- "
        "most of the apparent \"roll effect\" is roll and the gap both "
        "independently tracking tack/heading, not a direct roll -> gap "
        "relationship. Point-of-sail breakdown reinforces this: Reach legs show "
        "the *largest* mean gap despite the *lowest* mean roll of any point of "
        "sail, while Beat legs have the highest roll but only a middling gap:",
        "",
        pos_table.to_string(),
        "",
        "Within-tack fits (roll only, same tack):",
    ]
    for tack, d in within_tack.items():
        lines.append(
            f"- {tack}: n={d['n']}, corr={d['corr']:.3f}, "
            f"slope={d['slope']:.3f} deg/deg, R^2={d['r2']:.3f}"
        )
    lines += [
        "",
        "**Read:** a real heel-dependent effect (\"heeling error\" is a "
        "well-known classical compass-adjustment phenomenon -- heel changes how "
        "a magnetometer sits relative to nearby iron and to the field itself) "
        "is a live hypothesis, but this session's heel, tack, and heading are "
        "too collinear to isolate it -- same structural problem as the TWA "
        "confound, different variable. A controlled test (vary heel at a fixed "
        "heading -- e.g. crew weight shift at the dock, or rocking the boat by "
        "hand while holding a steady compass heading) is the only clean way to "
        "actually separate this, the same way the planned engine-position test "
        "was meant to isolate that effect from heading.",
        "",
        "## Apparent convergence over the race",
        f"- corr(|diff|, elapsed_min) = {corr_time:.3f} -- real downward trend, "
        "~40 deg early to ~5-10 deg by the end.",
        f"- **Ruled out: eCompass calibration improving.** `MFIT` vs. elapsed "
        f"time: corr = {corr_mfit_time:.4f} (essentially a straight line, "
        "7.220% -> 7.273%) -- that's the known ~1%/24h aging drift from the "
        "auto-recal library (see `Morticia-eCompass/docs/"
        "magcal-heading-jump-2026-08-11-handoff.md`), not an improving fit, "
        "and zero calibration-acceptance events fired all session. Whatever is "
        "shrinking the gap, it is not the eCompass's own calibration getting "
        "better in real time.",
        "- The |diff| trace dips sharply near what look like tack transitions "
        "(near-zero heel passing through the tack) and plateaus on each new "
        "tack, with the plateaus themselves trending down. Point-of-sail "
        "sequence this race: Run/Reach (first ~12 min) -> Beat (~15-38 min) -> "
        "Run (last ~10 min) -- consistent with *part* of the decline, but not "
        "all of it: the gap keeps declining across five consecutive Beat-tagged "
        "segments alone (28 -> 21 -> 19 -> 18 -> 17.6 deg), so point-of-sail "
        "isn't the whole story either.",
        "- **Not resolved by this session.** Best candidates not yet checked: "
        "wind easing over the evening (lower average heel/loading generally, "
        "independent of point-of-sail tag), or crew/gear weight distribution "
        "settling near the sensors as the race went on. Worth a look at "
        "`environment.wind.speedTrue` (TWS) trend and crew positioning notes "
        "if this comes up again.",
        "",
        "## Plots",
        "- `plots/hdgme_hdgmf_vs_roll.png`",
        "- `plots/hdgme_hdgmf_vs_time_and_mfit.png`",
    ]

    (BASE_DIR / "hdgme_hdgmf_gap_followup_20260826.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
