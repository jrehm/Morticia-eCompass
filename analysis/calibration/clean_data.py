"""
Motoring-configuration deviation diagnostic for the eCompass heading sensor
(Morticia-eCompass). Data collected 2026-08-10, engine down and shifted
~18in aft of its sailing position -- NOT the position the original magfit
calibration was performed in (engine up/forward). Leeway and Great Lakes
current (~5cm/s N->S) are both negligible under power, so COGt is treated
as a clean heading reference here -- this does NOT hold for sailing data.

This is a DIAGNOSTIC pass, not a firmware deliverable: heading accuracy
under sail (engine up/forward, the position the original magfit used) is
the actual project goal, so this motoring-position curve is not intended
for deployment. See the accompanying project handoff for the reasoning.

Reads the raw sailing_*.csv export from this directory, writes
data/clean_motoring.csv + data_quality_summary.md.
"""

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

ROLL_WINDOW = 21              # samples (~21s at 1Hz) for circular heading rolling std
STEADY_STD_THRESHOLD_DEG = 3.0
MIN_SOG_KN = 1.0              # below this, COG direction is unreliable


def find_raw_csv() -> Path:
    matches = sorted(BASE_DIR.glob("sailing_*.csv"))
    if not matches:
        raise FileNotFoundError(f"No sailing_*.csv found in {BASE_DIR}")
    return matches[-1]


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    date_match = re.search(r"sailing_(\d{8})_", path.name)
    if date_match is None:
        raise ValueError(f"Could not parse date from filename: {path.name}")
    date_str = date_match.group(1)
    df["t"] = pd.to_datetime(date_str + " " + df["timestamp"], format="%Y%m%d %I:%M:%S %p")
    return df.set_index("t").sort_index()


def circular_rolling_std_deg(heading_deg: pd.Series, window: int) -> pd.Series:
    """Rolling circular std-dev (deg) of a heading series, safe across the 0/360 wrap."""
    theta = np.deg2rad(heading_deg)
    min_p = int(window * 0.7)
    sin_r = np.sin(theta).rolling(window, center=True, min_periods=min_p).mean()
    cos_r = np.cos(theta).rolling(window, center=True, min_periods=min_p).mean()
    resultant = np.sqrt(sin_r ** 2 + cos_r ** 2)
    return np.rad2deg(np.sqrt(np.clip(-2 * np.log(resultant), 0, None)))


def circular_diff_deg(a_deg: pd.Series, b_deg: pd.Series) -> pd.Series:
    """a - b, wrapped to [-180, 180]."""
    return (a_deg - b_deg + 180) % 360 - 180


def main():
    raw_path = find_raw_csv()
    df = load_raw(raw_path)

    n_raw = len(df)
    n_hdgt_missing = int(df["HDGt"].isna().sum())

    present = df["HDGt"].notna().astype(int)
    n_gap_events = int((present.diff() == -1).sum())

    df["hdg_rollstd"] = circular_rolling_std_deg(df["HDGt"], ROLL_WINDOW)

    valid = df.dropna(subset=["HDGt", "COGt"]).copy()
    n_valid = len(valid)

    steady = valid[
        (valid["hdg_rollstd"] < STEADY_STD_THRESHOLD_DEG) & (valid["SOG"] >= MIN_SOG_KN)
    ].copy()
    n_steady = len(steady)

    steady["dev_deg"] = circular_diff_deg(steady["COGt"], steady["HDGt"])
    steady["heading_bin_30"] = (steady["HDGt"] // 30 * 30).astype(int)

    out_cols = [
        "HDGt", "COGt", "SOG", "ROLL", "PITCH", "AWA", "TWA",
        "hdg_rollstd", "dev_deg", "heading_bin_30",
    ]
    clean_path = DATA_DIR / "clean_motoring.csv"
    steady[out_cols].to_csv(clean_path)

    all_bins = pd.Index(range(0, 360, 30), name="heading_bin_30")
    bin_coverage = steady.groupby("heading_bin_30")["dev_deg"].agg(["mean", "std", "count"])
    bin_coverage = bin_coverage.reindex(all_bins)
    thin_bins = bin_coverage[bin_coverage["count"].isna() | (bin_coverage["count"] < 20)]

    lines = [
        "# Motoring-Configuration Deviation Diagnostic — Data Quality Summary",
        "",
        f"Source: `{raw_path.name}`",
        f"Window: {df.index.min()} -> {df.index.max()} ({n_raw} rows @ ~1Hz)",
        "",
        "**Collection conditions (per Jeff):** engine running, engine tilted down "
        "and ~18in aft of its sailing position. ~5cm/s N->S current (Great Lakes, "
        "negligible at this boat speed). Leeway under power treated as negligible. "
        "COGt is therefore used as a heading reference for this diagnostic only -- "
        "this assumption does NOT hold for sailing data, where leeway is real.",
        "",
        "## Raw data quality",
        f"- `HDGt` missing: {n_hdgt_missing} of {n_raw} rows ({n_hdgt_missing / n_raw:.1%})",
        f"- `HDGt` dropout events (gap starts): {n_gap_events}",
        f"- Rows with both `HDGt` and `COGt` present: {n_valid}",
        "",
        "## Steady-state filter",
        f"Circular rolling std of `HDGt` over {ROLL_WINDOW}s < {STEADY_STD_THRESHOLD_DEG} deg, "
        f"and SOG >= {MIN_SOG_KN} kn (COG unreliable below this). `ROT` was NOT used for this "
        "filter -- known ~60x scaling bug in the Signal K pipeline, not yet fixed.",
        f"- Steady-state rows retained: {n_steady} of {n_valid} valid rows ({n_steady / n_valid:.1%})",
        "",
        "## Heading-bin coverage (30 deg bins, steady-state rows only)",
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

    lines.append("## Output")
    lines.append(f"Clean steady-state dataset -> `data/clean_motoring.csv` ({n_steady} rows)")

    (BASE_DIR / "data_quality_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
