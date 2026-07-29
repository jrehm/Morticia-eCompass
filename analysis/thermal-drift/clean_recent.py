"""
Data validation & cleanup for the eCompass recent-window coefficient check
(2026-07-20 17:00 local -> 2026-07-23), mirroring clean_data.py's approach
but operating on data/raw_recent.csv (pulled by pull_recent.py) and writing
data/clean_recent.csv + recent_data_quality_summary.md.

See docs/thermal-drift-compensation-handoff.md for background: this window
is used to check whether the deployed v1.3.2 thermal coefficients (fit on
2026-07-08/13 dockside data) are still tracking correctly, per Jeff's
Grafana observation of apparent miscalibration.
"""

import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

DATA_DIR = Path(__file__).parent / "data"
GAP_THRESHOLD_S = 5.0
SWING_LOOKAHEAD_MIN = 10
SWING_THRESHOLD_DEG = 15.0
BASELINE_WINDOW_MIN = 30
SETTLE_TOLERANCE_DEG = 3.0
SOG_THRESHOLD_KN = 1.0
RESAMPLE_RULE = "5s"


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "raw_recent.csv", index_col="time")
    df.index = pd.to_datetime(df.index, utc=True, format="ISO8601")
    return df.sort_index()


def find_gaps(idx: pd.DatetimeIndex, threshold_s: float) -> pd.DataFrame:
    dt = idx.to_series().diff().dt.total_seconds()
    gaps = dt[dt > threshold_s]
    return pd.DataFrame({"gap_end": gaps.index, "gap_s": gaps.values})


def find_artifact_windows(heading: pd.Series, gaps: pd.DataFrame):
    artifacts = []
    for gap_end, gap_s in zip(gaps["gap_end"], gaps["gap_s"]):
        baseline_window = heading[gap_end - pd.Timedelta(minutes=BASELINE_WINDOW_MIN):gap_end]
        if baseline_window.empty:
            continue
        baseline = baseline_window.median()

        lookahead = heading[gap_end: gap_end + pd.Timedelta(minutes=SWING_LOOKAHEAD_MIN)]
        if lookahead.empty:
            continue
        deviation = (lookahead - baseline).abs()
        peak_dev = deviation.max()
        if peak_dev < SWING_THRESHOLD_DEG:
            continue

        peak_time = deviation.idxmax()
        after_peak = heading[peak_time:]
        settled = after_peak[(after_peak - baseline).abs() < SETTLE_TOLERANCE_DEG]
        end_time = settled.index[0] if len(settled) else lookahead.index[-1]
        artifacts.append((gap_end, end_time, float(peak_dev)))
    return artifacts


def main():
    df = load_raw()
    heading = df["heading_deg"].dropna()

    gaps = find_gaps(heading.index, GAP_THRESHOLD_S)
    artifacts = find_artifact_windows(heading, gaps)

    excluded_mask = pd.Series(False, index=df.index)
    for start, end, peak_dev in artifacts:
        excluded_mask |= (df.index >= start) & (df.index <= end)

    sog_flag = df["sog_kn"] > SOG_THRESHOLD_KN
    sog_flag_windows = []
    if sog_flag.any():
        flagged = sog_flag[sog_flag]
        groups = (flagged.index.to_series().diff() > pd.Timedelta(minutes=5)).cumsum()
        for _, grp in flagged.groupby(groups):
            sog_flag_windows.append((grp.index.min(), grp.index.max()))
        for start, end in sog_flag_windows:
            excluded_mask |= (df.index >= start - pd.Timedelta(minutes=2)) & (df.index <= end + pd.Timedelta(minutes=2))

    clean = df.loc[~excluded_mask].copy()
    resampled = clean.resample(RESAMPLE_RULE).mean()

    out_path = DATA_DIR / "clean_recent.csv"
    resampled.to_csv(out_path)

    summary_lines = [
        "# eCompass Recent-Window Coefficient Check — Data Quality Summary",
        "",
        f"Raw window: {df.index.min()} -> {df.index.max()}",
        f"Raw rows: {len(df)}",
        f"Heading samples: {len(heading)} (~{len(heading) / ((heading.index[-1]-heading.index[0]).total_seconds()/3600):.2f}/hr)",
        "",
        f"## Gaps in heading series (> {GAP_THRESHOLD_S}s)",
        f"Total gaps: {len(gaps)}",
        gaps.to_string(index=False) if not gaps.empty else "(none)",
        "",
        "## Reconnect-swing artifacts excluded (gap followed by swing-and-return)",
        f"Count: {len(artifacts)}",
    ]
    for start, end, peak_dev in artifacts:
        summary_lines.append(
            f"- {start} -> {end} (duration {(end - start)}), peak deviation {peak_dev:.1f} deg from baseline"
        )
    if not artifacts:
        summary_lines.append("(none found)")

    summary_lines += [
        "",
        f"## Speed-over-ground exceptions (> {SOG_THRESHOLD_KN} kn, i.e. possibly not stationary)",
        f"Count of flagged windows: {len(sog_flag_windows)}",
    ]
    for start, end in sog_flag_windows:
        summary_lines.append(f"- {start} -> {end}")
    if not sog_flag_windows:
        summary_lines.append("(none found)")

    summary_lines += [
        "",
        "## Result",
        f"Rows excluded (artifact + SOG windows): {int(excluded_mask.sum())} of {len(df)} raw rows",
        f"Resampled ({RESAMPLE_RULE}) clean dataset: {len(resampled)} rows -> data/clean_recent.csv",
        f"Temperature range: {resampled['temp_c'].min():.2f} - {resampled['temp_c'].max():.2f} C",
        f"Heading range (post-cleanup, already thermally-compensated by v1.3.2 firmware): "
        f"{resampled['heading_deg'].min():.2f} - {resampled['heading_deg'].max():.2f} deg",
    ]

    (DATA_DIR / "recent_data_quality_summary.md").write_text("\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
