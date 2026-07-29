"""
Pull recent Signal K series (2026-07-20 17:00 local -> now) to check whether
the deployed thermal compensation coefficient (v1.3.2, slope -1.0211 deg/C,
T_ref 30.0723 C) is still tracking correctly, per Jeff's Grafana observation.

Mirrors pull_data.py's PATHS/columns but writes to data/raw_recent.csv so it
doesn't clobber the original 2026-07-08/13 dockside dataset.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv(Path(__file__).parent / ".env")

INFLUXDB_URL = os.environ["INFLUXDB_URL"]
INFLUXDB_TOKEN = os.environ["INFLUXDB_TOKEN"]
INFLUXDB_ORG = os.environ["INFLUXDB_ORG"]
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "signalk")

# 2026-07-20 17:00 America/New_York (EDT, UTC-4) -> 21:00 UTC
RANGE_START = "2026-07-20T21:00:00Z"
RANGE_STOP = "now()"

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


def fetch_path(client: InfluxDBClient, sk_path: str) -> pd.Series:
    query = f"""
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {RANGE_START}, stop: {RANGE_STOP})
      |> filter(fn: (r) => r._measurement == "{sk_path}" and r._field == "value")
      |> keep(columns: ["_time", "_value"])
    """
    df = client.query_api().query_data_frame(query, org=INFLUXDB_ORG)
    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True) if df else pd.DataFrame(columns=["_time", "_value"])
    if df.empty:
        print(f"  WARNING: no data returned for {sk_path}")
        return pd.Series(dtype=float, name=sk_path)
    s = pd.Series(df["_value"].values, index=pd.to_datetime(df["_time"]), name=sk_path)
    return s.sort_index()


def main():
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)

    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    series = {}
    for sk_path, (col_name, convert) in PATHS.items():
        print(f"Fetching {sk_path} ...")
        raw = fetch_path(client, sk_path)
        print(f"  {len(raw)} points")
        series[col_name] = convert(raw) if not raw.empty else raw.rename(col_name)
    client.close()

    merged = pd.DataFrame(series)
    merged.index.name = "time"
    merged = merged.sort_index()

    raw_path = out_dir / "raw_recent.csv"
    merged.to_csv(raw_path)
    print(f"\nWrote {len(merged)} rows to {raw_path}")
    print(merged.describe())


if __name__ == "__main__":
    main()
