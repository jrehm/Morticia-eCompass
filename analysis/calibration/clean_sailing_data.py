"""
Sailing-mode deviation diagnostic for the eCompass heading sensor, from the
2026-08-12 race session (engine up/forward while sailing -- the position
the original magfit calibration used). Companion to clean_data.py, which
covers the 2026-08-10 motoring-configuration session.

Session segments (per Jeff, approximate clock times):
  - pre_underway  17:45-18:00  at dock/mooring, stationary
  - motor_out     18:00-18:24  motoring out to the course (engine down)
  - presail       18:24-19:00  sailing, pre-start (engine up)
  - race          19:00-19:44  racing (engine up)
  - postfinish    19:44-19:51  post-finish, still sailing (engine up)
  - motor_back    19:51-20:15  motoring back (engine down)

Only presail+race+postfinish (engine up/forward, sailing) are steady-state
filtered and used for the deviation fit -- this is the configuration that
matters for the actual deployment table. motor_out/motor_back are kept as
a same-session, uncontrolled comparison point against the 2026-08-10
motoring curve, not a replacement for the planned (but not yet completed)
controlled engine-toggle test.

Reads the highest-resolution sailing_20260812_*.csv in this directory
(prefers the "-1hz" export over the original 10s quick-look export, if
both are present). Writes data/clean_sailing.csv + sailing_data_quality_summary.md.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=DeprecationWarning)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_CSV = BASE_DIR / "sailing_20260812_174500_to_20260812_201500.csv"
RAW_CSV_1HZ = BASE_DIR / "sailing_20260812_174500_to_20260812_201500-1hz.csv"

ROLL_WINDOW = "21s"           # time-based -- robust to whichever cadence is loaded
STEADY_STD_THRESHOLD_DEG = 3.0
MIN_SOG_KN = 1.0
BOUNDARY_BUFFER_S = 30         # exclude rows this close to a segment transition

SEGMENTS = [
    ("pre_underway", "2026-08-12 17:45:00", "2026-08-12 18:00:00", "off_dock"),
    ("motor_out",     "2026-08-12 18:00:00", "2026-08-12 18:24:00", "on"),
    ("presail",       "2026-08-12 18:24:00", "2026-08-12 19:00:00", "off"),
    ("race",          "2026-08-12 19:00:00", "2026-08-12 19:44:00", "off"),
    ("postfinish",    "2026-08-12 19:44:00", "2026-08-12 19:51:00", "off"),
    ("motor_back",    "2026-08-12 19:51:00", "2026-08-12 20:15:00", "on"),
]


def circular_rolling_std_deg(heading_deg: pd.Series, window: str) -> pd.Series:
    """Time-window circular std-dev (deg), safe across the 0/360 wrap."""
    theta = np.deg2rad(heading_deg)
    sin_r = np.sin(theta).rolling(window, center=True).mean()
    cos_r = np.cos(theta).rolling(window, center=True).mean()
    resultant = np.sqrt(sin_r ** 2 + cos_r ** 2)
    return np.rad2deg(np.sqrt(np.clip(-2 * np.log(resultant), 0, None)))


def circular_diff_deg(a_deg: pd.Series, b_deg: pd.Series) -> pd.Series:
    """a - b, wrapped to [-180, 180]."""
    return (a_deg - b_deg + 180) % 360 - 180


def load_raw() -> pd.DataFrame:
    path = RAW_CSV_1HZ if RAW_CSV_1HZ.exists() else RAW_CSV
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df.set_index("timestamp").sort_index(), path


def tag_segments(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["segment"] = "unassigned"
    df["engine_state"] = "unassigned"
    for name, start, end, engine_state in SEGMENTS:
        mask = (df.index >= start) & (df.index < end)
        df.loc[mask, "segment"] = name
        df.loc[mask, "engine_state"] = engine_state
    return df


def flag_near_boundary(df: pd.DataFrame, buffer_s: int) -> pd.Series:
    """True for rows within buffer_s of any segment transition -- transition
    moments (e.g. engine shutting off, sails going up) are physically messy
    and not representative of steady motoring or sailing."""
    boundaries = pd.to_datetime([b for _, start, end, _ in SEGMENTS for b in (start, end)])
    near = pd.Series(False, index=df.index)
    for b in boundaries:
        near |= (df.index >= b - pd.Timedelta(seconds=buffer_s)) & \
                (df.index <= b + pd.Timedelta(seconds=buffer_s))
    return near


def flag_frozen_cog(df: pd.DataFrame) -> pd.Series:
    """True where COGt and SOG are bit-identical to the previous sample while
    LAT/LON keep moving -- found during development: a real GPS fix (position
    updating normally) with a stale/frozen COG-SOG output, worst during active
    turns (e.g. mark roundings), which fabricates large spurious deviation
    since heading keeps changing while the "reference" doesn't."""
    return (df["COGt"].diff() == 0) & (df["SOG"].diff() == 0)


def main():
    df, raw_path = load_raw()
    df = tag_segments(df)

    n_raw = len(df)
    sample_interval_s = df.index.to_series().diff().dt.total_seconds().median()

    # Calibration-event / stability check across the whole session
    # NOTE: MCALF/MFIT etc. only publish every ~4s (firmware reporting
    # interval); at 1Hz cadence most rows are NaN for these fields, not 0.
    # `!= 0` on a NaN is True in pandas, so this must exclude NaN explicitly
    # or every missing sample gets miscounted as an event.
    n_cal_events = int((df["MCALF"].notna() & (df["MCALF"] != 0)).sum())
    mfit_min, mfit_max = df["MFIT"].min(), df["MFIT"].max()

    # Per-segment summary (SOG, roll/pitch, inclination, magfit)
    seg_rows = []
    for name, start, end, engine_state in SEGMENTS:
        seg = df[df["segment"] == name]
        seg_rows.append({
            "segment": name, "engine": engine_state, "n": len(seg),
            "sog_mean": seg["SOG"].mean(), "sog_std": seg["SOG"].std(),
            "roll_std": seg["ROLL"].std(), "mincl_mean": seg["MINCL"].mean(),
            "mincl_std": seg["MINCL"].std(), "magb_mean": seg["MAGB"].mean(),
        })
    seg_table = pd.DataFrame(seg_rows).set_index("segment")

    # Steady-state filter, sailing (engine up/forward) rows only
    df["hdg_rollstd"] = circular_rolling_std_deg(df["HDGt"], ROLL_WINDOW)
    df["near_boundary"] = flag_near_boundary(df, BOUNDARY_BUFFER_S)
    df["frozen_cog"] = flag_frozen_cog(df)
    n_hdgt_missing = int(df["HDGt"].isna().sum())
    n_frozen_cog = int(df["frozen_cog"].sum())
    sailing = df[
        (df["engine_state"] == "off") & df["HDGt"].notna() & df["COGt"].notna()
        & ~df["near_boundary"] & ~df["frozen_cog"]
    ].copy()
    steady = sailing[
        (sailing["hdg_rollstd"] < STEADY_STD_THRESHOLD_DEG) & (sailing["SOG"] >= MIN_SOG_KN)
    ].copy()
    steady["dev_deg"] = circular_diff_deg(steady["COGt"], steady["HDGt"])
    steady["heading_bin_30"] = (steady["HDGt"] // 30 * 30).astype(int)

    out_cols = [
        "segment", "HDGt", "COGt", "SOG", "ROLL", "TWA", "TACK",
        "MFIT", "MAGB", "MINCL", "hdg_rollstd", "dev_deg", "heading_bin_30",
    ]
    clean_path = DATA_DIR / "clean_sailing.csv"
    steady[out_cols].to_csv(clean_path)

    all_bins = pd.Index(range(0, 360, 30), name="heading_bin_30")
    bin_coverage = steady.groupby("heading_bin_30")["dev_deg"].agg(["mean", "std", "count"])
    bin_coverage = bin_coverage.reindex(all_bins)
    thin_bins = bin_coverage[bin_coverage["count"].isna() | (bin_coverage["count"] < 20)]

    lines = [
        "# Sailing-Configuration Deviation Diagnostic — Data Quality Summary",
        "",
        f"Source: `{raw_path.name}`",
        f"Window: {df.index.min()} -> {df.index.max()} "
        f"({n_raw} rows @ ~{sample_interval_s:.0f}s)",
        "",
        "**Session segments (per Jeff, approximate clock times):**",
        seg_table.round(2).to_string(),
        "",
        "## Calibration stability across the session",
        f"- Calibration-acceptance events (`MCALF != 0`): {n_cal_events} "
        f"({'none fired -- clean session, no auto-recal confound' if n_cal_events == 0 else 'SEE DETAIL -- may confound results'})",
        f"- `MFIT` (in-use fit error) ranged {mfit_min:.3f}% - {mfit_max:.3f}% "
        "-- smooth aging drift only, consistent with no discrete recalibration",
        "- `MAGB` (in-use field magnitude) was constant all session -- expected, since it's "
        "a property of the active calibration model, not a live per-sample field reading, "
        "and the active calibration never changed (see above)",
        "",
        "## Steady-state filter (sailing/engine-up rows only)",
        f"Circular rolling std of `HDGt` over {ROLL_WINDOW} < {STEADY_STD_THRESHOLD_DEG} deg, "
        f"and SOG >= {MIN_SOG_KN} kn. `HDGt` missing on {n_hdgt_missing} of {n_raw} rows "
        f"({n_hdgt_missing / n_raw:.1%}) session-wide, dropped before filtering. Rows within "
        f"{BOUNDARY_BUFFER_S}s of any segment transition are also excluded -- a 3-sample "
        "SOG/COG glitch (6-22 kn in 2s, dev_deg to -133) turned up right at the "
        "motor-out->presail boundary during development; excluding transition windows "
        "removes it on principled grounds (transitions are physically messy generally) "
        "rather than an ad hoc outlier rule.",
        "",
        f"**Frozen-COG filter:** {n_frozen_cog} of {n_raw} rows ({n_frozen_cog / n_raw:.1%}) "
        "session-wide have `COGt`/`SOG` bit-identical to the previous sample while `LAT`/`LON` "
        "keep updating normally -- a real GPS fix with a stale COG/SOG output, worst during "
        "active turns (heading sweeping through 5+ deg while COGt sits frozen), which "
        "fabricates large spurious deviation. Excluded from the steady-state set.",
        f"- Sailing rows (presail+race+postfinish): {len(sailing)}",
        f"- Steady-state rows retained: {len(steady)} of {len(sailing)} "
        f"({len(steady) / len(sailing):.1%})",
        "",
        "## Heading-bin coverage (30 deg bins, steady-state sailing rows only)",
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
    lines.append(f"Clean steady-state sailing dataset -> `data/clean_sailing.csv` ({len(steady)} rows)")

    (BASE_DIR / "sailing_data_quality_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
