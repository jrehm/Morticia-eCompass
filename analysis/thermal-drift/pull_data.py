"""
Pull raw Signal K series from QuestDB for the eCompass thermal-drift analysis and write a
merged, unit-converted CSV (default data/raw_merged.csv).

QuestDB history starts 2026-11-14. For the July datasets use the scripts in influx-legacy/.

Usage:
    pip install -r requirements.txt
    # on the Pi:   export QUESTDB_URL=http://localhost:9000
    # elsewhere:   uses `ssh halos` (override with QUESTDB_SSH_HOST) or an ssh -L tunnel + QUESTDB_URL
    python pull_data.py --start 2026-11-14T00:00:00Z [--stop now] [--out raw_merged.csv]

The old pull_newloc.py / pull_recent.py were this script with different ranges/outputs:
    --start 2026-07-30T13:00:00Z --out raw_newloc.csv
    --start 2026-07-20T21:00:00Z --out raw_recent.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skdata  # noqa: E402

# sk_path -> (output column name, unit conversion fn)
PATHS = {
    "navigation.headingCompass": ("heading_deg", lambda v: v * 180.0 / 3.14159265358979),
    "environment.inside.ecompass.temperature": ("temp_c", lambda v: v - 273.15),
    "navigation.rateOfTurn": ("rate_of_turn_deg_s", lambda v: v * 180.0 / 3.14159265358979),
    "navigation.roll": ("roll_deg", lambda v: v * 180.0 / 3.14159265358979),
    "navigation.pitch": ("pitch_deg", lambda v: v * 180.0 / 3.14159265358979),
    "navigation.speedOverGround": ("sog_kn", lambda v: v * 1.9438444924),
    "environment.wind.speedApparent": ("wind_speed_kn", lambda v: v * 1.9438444924),
    "environment.wind.angleApparent": ("wind_angle_deg", lambda v: v * 180.0 / 3.14159265358979),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="ISO-8601 UTC start, e.g. 2026-11-14T00:00:00Z")
    ap.add_argument("--stop", default="now", help="ISO-8601 UTC stop or 'now' (default)")
    ap.add_argument("--out", default="raw_merged.csv", help="output file name inside data/")
    args = ap.parse_args()

    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)

    series = {}
    for sk_path, (col_name, convert) in PATHS.items():
        print(f"Fetching {sk_path} ...")
        raw = skdata.fetch_series(sk_path, args.start, args.stop)
        print(f"  {len(raw)} points")
        if raw.empty:
            print(f"  WARNING: no data returned for {sk_path}")
        series[col_name] = convert(raw) if not raw.empty else raw.rename(col_name)

    merged = pd.DataFrame(series)
    merged.index.name = "time"
    merged = merged.sort_index()

    raw_path = out_dir / args.out
    merged.to_csv(raw_path)
    print(f"\nWrote {len(merged)} rows to {raw_path}")
    print(merged.describe())


if __name__ == "__main__":
    main()
