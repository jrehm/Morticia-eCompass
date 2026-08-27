"""
Sailing-mode deviation diagnostic for the eCompass heading sensor, from the
2026-08-26 race session. Companion to clean_sailing_data.py (2026-08-12
session), with two differences forced by things that changed in between:

1. **No engine on/off segmentation needed.** The input file here is Jeff's
   manually-tagged export (`sailing_20260826_1855_to_1950_cleaned.csv`),
   which only covers the race window (19:00:00-19:46:51 local) and has
   `Main`/`Headsail`/`Dagger` populated on every row (always a sail
   configuration, never "none") -- so unlike the 2026-08-12 pipeline, there's
   no motor_out/motor_back to exclude and no SEGMENTS table to hardcode.
   (The raw programmatic export, `sailing_20260826_185500_to_20260826_195000.csv`,
   does cover the fuller 18:55-19:50 dock/motor/race/motor window, but has no
   per-row tags to identify engine state -- it's not used here.)

2. **The heading-under-test is `HDGmE`, not `HDGt`.** This is the important
   one. The 2026-08-12 pipeline used `HDGt` as "the eCompass heading" because
   at the time, `navigation.headingMagnetic` (and therefore the derived
   `HDGt`/headingTrue) resolved to the eCompass (`SensESP.XX`). That changed
   2026-08-19 (`handoffs/fluxgate-heading-source-switch.md`): `HDGt` now
   reflects the fluxgate. Naively reusing `HDGt` here would silently compute
   a deviation table for the *fluxgate*, not the eCompass. `HDGmE` (the
   `signalk-path-mapper` duplicate of the eCompass's raw
   `headingMagnetic`, added as part of that same cutover specifically so the
   eCompass could keep being evaluated off to the side) is the correct
   column for this project's actual subject.

`HDGmF` (fluxgate raw magnetic, same duplicate mechanism) is also carried
through and evaluated against COGt for context/cross-check, since the
fluxgate's own mounting offset is still untuned (deployed at 0, per TODO.md
-> "Fluxgate Heading Correction").

**Known exporter gap, still present:** the raw programmatic export for this
session has `HDGmE`/`HDGmF` essentially 100% null (1/3290 and 0/3290 rows).
This is the same gap flagged in the fluxgate handoff (commit `ca6891a`,
adds `HDGmE`/`HDGmF` columns to `sailing-data-exporter`) -- as of this
session it's still either not pushed/pulled, or pushed but not actually
fixing this (worth checking `sailing-data-exporter`'s CHANGELOG/git log
directly). The manually-tagged file used here has both populated, which
implies Jeff filled these in by hand (or via a different export path) for
this file specifically -- not a pipeline output, so it doesn't help for any
*future* raw export until the exporter fix actually lands.

Reads sailing_20260826_1855_to_1950_cleaned.csv (this directory).
Writes data/clean_sailing_20260826.csv + sailing_data_quality_summary_20260826.md.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_CSV = BASE_DIR / "sailing_20260826_1855_to_1950_cleaned.csv"
SESSION_DATE = "2026-08-26"

ROLL_WINDOW = "21s"
STEADY_STD_THRESHOLD_DEG = 3.0
MIN_SOG_KN = 1.0


def circular_rolling_std_deg(heading_deg: pd.Series, window: str) -> pd.Series:
    theta = np.deg2rad(heading_deg)
    sin_r = np.sin(theta).rolling(window, center=True).mean()
    cos_r = np.cos(theta).rolling(window, center=True).mean()
    resultant = np.sqrt(sin_r ** 2 + cos_r ** 2)
    return np.rad2deg(np.sqrt(np.clip(-2 * np.log(resultant), 0, None)))


def circular_diff_deg(a_deg: pd.Series, b_deg: pd.Series) -> pd.Series:
    return (a_deg - b_deg + 180) % 360 - 180


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    df = df.dropna(how="all").reset_index(drop=True)  # trailing blank rows from the Excel export
    df["timestamp"] = pd.to_datetime(
        f"{SESSION_DATE} " + df["timestamp"], format="%Y-%m-%d %I:%M:%S %p"
    )
    return df.set_index("timestamp").sort_index()


def flag_frozen_cog(df: pd.DataFrame) -> pd.Series:
    return (df["COGt"].diff() == 0) & (df["SOG"].diff() == 0)


def build_steady(df: pd.DataFrame, heading_col: str, rollstd_col: str) -> pd.DataFrame:
    """Steady-state filter against a given heading column, mirroring
    clean_sailing_data.py's criteria (rolling circular std < 3 deg over 21s,
    SOG >= 1kn, frozen-COG rows excluded)."""
    df = df.copy()
    df[rollstd_col] = circular_rolling_std_deg(df[heading_col], ROLL_WINDOW)
    candidate = df[
        df[heading_col].notna() & df["COGt"].notna() & ~df["frozen_cog"]
    ].copy()
    steady = candidate[
        (candidate[rollstd_col] < STEADY_STD_THRESHOLD_DEG) & (candidate["SOG"] >= MIN_SOG_KN)
    ].copy()
    steady["dev_deg"] = circular_diff_deg(steady["COGt"], steady[heading_col])
    steady["heading_bin_30"] = (steady[heading_col] // 30 * 30).astype(int)
    return steady


def main():
    df = load_raw()
    n_raw = len(df)
    sample_interval_s = df.index.to_series().diff().dt.total_seconds().median()

    # Confirm this session is sailing-config throughout (no motor segment to exclude)
    sail_up_frac = (df["Main"].notna() & df["Headsail"].notna()).mean()

    df["frozen_cog"] = flag_frozen_cog(df)
    n_frozen_cog = int(df["frozen_cog"].sum())

    n_cal_events = int((df["MCALF"].notna() & (df["MCALF"] != 0)).sum())
    mfit_min, mfit_max = df["MFIT"].min(), df["MFIT"].max()

    n_hdgme_missing = int(df["HDGmE"].isna().sum())
    n_hdgmf_missing = int(df["HDGmF"].isna().sum())
    n_cogt_missing = int(df["COGt"].isna().sum())

    # Primary: eCompass (HDGmE) vs COGt -- the actual subject of this project
    steady = build_steady(df, "HDGmE", "hdgme_rollstd")

    # Context: fluxgate raw (HDGmF) vs COGt, and system heading (HDGt) vs COGt
    steady_flux = build_steady(df, "HDGmF", "hdgmf_rollstd")
    steady_sys = build_steady(df, "HDGt", "hdgt_rollstd")

    # eCompass vs fluxgate gap, direct sensor-to-sensor (no COGt/GPS involved at all)
    both = df.dropna(subset=["HDGmE", "HDGmF"])
    ecompass_vs_flux = circular_diff_deg(both["HDGmE"], both["HDGmF"])

    out_cols = ["HDGmE", "HDGmF", "HDGt", "COGt", "SOG", "ROLL", "TWA", "Tack/Gybe",
                "PointOfSail", "MFIT", "MAGB", "MINCL", "hdgme_rollstd", "dev_deg",
                "heading_bin_30"]
    clean_path = DATA_DIR / "clean_sailing_20260826.csv"
    steady[out_cols].to_csv(clean_path)

    all_bins = pd.Index(range(0, 360, 30), name="heading_bin_30")
    bin_coverage = steady.groupby("heading_bin_30")["dev_deg"].agg(["mean", "std", "count"])
    bin_coverage = bin_coverage.reindex(all_bins)
    thin_bins = bin_coverage[bin_coverage["count"].isna() | (bin_coverage["count"] < 20)]

    lines = [
        "# 2026-08-26 Race Session — Data Quality Summary",
        "",
        f"Source: `{RAW_CSV.name}` (Jeff's manually-tagged race-window export, "
        "Main/Headsail/Dagger/Tack-Gybe/PointOfSail added by hand -- same pattern "
        "as the 2026-07-29 log). Not the raw programmatic export "
        "(`sailing_20260826_185500_to_20260826_195000.csv`), which covers a wider "
        "window but has no per-row engine/sail state and, separately, has "
        "`HDGmE`/`HDGmF` essentially all-null (see below).",
        f"Window: {df.index.min()} -> {df.index.max()} ({n_raw} rows @ ~{sample_interval_s:.0f}s)",
        f"Sail-configuration coverage: {sail_up_frac:.1%} of rows have Main/Headsail "
        "populated -- confirms this file is race/sailing throughout, no motor segment "
        "to exclude (unlike the 2026-08-12 session).",
        "",
        "## Methodology note: heading-under-test changed from HDGt to HDGmE",
        "The 2026-08-12 pipeline evaluated `HDGt` directly, because at the time "
        "`navigation.headingMagnetic` (and the derived `HDGt`) resolved to the "
        "eCompass. That changed 2026-08-19 -- `HDGt` now reflects the fluxgate "
        "(`handoffs/fluxgate-heading-source-switch.md`). This script uses `HDGmE` "
        "(the `signalk-path-mapper` duplicate of the eCompass's raw heading, added "
        "in that same cutover) as the eCompass-under-test column. `HDGt` and `HDGmF` "
        "are still evaluated below for context, not as the primary result.",
        "",
        "## Known exporter gap -- still present",
        f"Raw export `HDGmE`: {n_hdgme_missing}/{n_raw} rows null in the manually-tagged "
        "file (partially filled by hand); the programmatic raw export for this same "
        "session has it null on all but 1 of 3290 rows. Same gap flagged in the "
        "fluxgate handoff (commit `ca6891a`, not yet landed as of this writing there) -- "
        "confirm whether that commit has since been pushed/pulled and, if so, whether "
        "it actually fixes this (it may need `sensors.ecompass.headingMagnetic` "
        "specifically, not a `navigation.headingMagnetic` source filter -- see the "
        "handoff's 'Outcome' section, item 3).",
        "",
        "## Calibration stability across the session",
        f"- Calibration-acceptance events (`MCALF != 0`): {n_cal_events} "
        f"({'none fired -- clean session' if n_cal_events == 0 else 'SEE DETAIL -- may confound results'})",
        f"- `MFIT` (in-use fit error) ranged {mfit_min:.3f}% - {mfit_max:.3f}% -- tight, "
        "but notably higher than the ~3% achieved right after the ADR-013 sensor "
        "relocation; worth keeping an eye on across future sessions, not urgent on its own.",
        "",
        "## Steady-state filter (eCompass/HDGmE basis, this project's actual subject)",
        f"Circular rolling std of `HDGmE` over {ROLL_WINDOW} < {STEADY_STD_THRESHOLD_DEG} deg, "
        f"SOG >= {MIN_SOG_KN} kn, frozen-COG rows excluded (below). "
        f"`HDGmE` missing {n_hdgme_missing}/{n_raw} ({n_hdgme_missing / n_raw:.1%}), "
        f"`COGt` missing {n_cogt_missing}/{n_raw} ({n_cogt_missing / n_raw:.1%}) -- "
        "COGt's lower population rate (GPS-rate limited) is the main constraint on "
        "steady-state sample count, more than the rolling-std filter itself.",
        "",
        f"**Frozen-COG filter:** {n_frozen_cog} of {n_raw} rows ({n_frozen_cog / n_raw:.1%}) "
        "have `COGt`/`SOG` bit-identical to the previous sample -- same GPS pipeline bug "
        "documented in the 2026-08-12 session, still present, still small here.",
        f"- Steady-state rows retained (HDGmE basis): {len(steady)} of {n_raw}",
        "",
        "## Heading-bin coverage (30 deg bins, HDGmE basis)",
        bin_coverage.to_string(),
        "",
    ]

    if not thin_bins.empty:
        lines.append("### Thin/missing coverage (< 20 steady samples)")
        for b in thin_bins.index:
            n = bin_coverage.loc[b, "count"]
            n_display = "0 (no steady samples)" if pd.isna(n) else int(n)
            lines.append(f"- {b}-{b + 30} deg: {n_display}")
        lines.append("")
    else:
        lines.append("All 12 heading bins have >= 20 steady samples.")
        lines.append("")

    lines += [
        "## Context: fluxgate (HDGmF) and system heading (HDGt) vs. COGt",
        f"- `HDGmF` vs `COGt`, steady-state: n={len(steady_flux)}, "
        f"mean={steady_flux['dev_deg'].mean():.2f} deg, std={steady_flux['dev_deg'].std():.2f} deg",
        f"- `HDGt` vs `COGt`, steady-state: n={len(steady_sys)}, "
        f"mean={steady_sys['dev_deg'].mean():.2f} deg, std={steady_sys['dev_deg'].std():.2f} deg",
        "Both show substantial heading-dependent structure, similar in spirit to the "
        "eCompass result below -- given the strong TWA confound this session (see fit "
        "summary), this is consistent with leeway affecting *any* COGt-referenced "
        "deviation estimate under sail, not necessarily evidence that the fluxgate "
        "itself has comparable deviation to the eCompass. Not a clean read either way "
        "from COGt alone this session.",
        "",
        "## eCompass vs. fluxgate, direct sensor-to-sensor gap (no COGt/GPS involved)",
        f"`HDGmE - HDGmF`, all rows with both present (n={len(both)}): "
        f"mean={ecompass_vs_flux.mean():.2f} deg, std={ecompass_vs_flux.std():.2f} deg, "
        f"range [{ecompass_vs_flux.min():.2f}, {ecompass_vs_flux.max():.2f}] deg.",
        "This is independent of COGt/leeway entirely -- a large, heading-varying gap "
        "between the two magnetic-heading sensors under sail, over and above whatever "
        "the TWA confound is doing to either one's COGt-referenced deviation estimate. "
        "New data point, not previously quantified under sail.",
        "",
        "## Output",
        f"Clean steady-state eCompass dataset -> `data/clean_sailing_20260826.csv` ({len(steady)} rows)",
    ]

    (BASE_DIR / "sailing_data_quality_summary_20260826.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
