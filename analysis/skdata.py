"""
skdata.py -- pull Signal K history from QuestDB for the analysis scripts.

Replaces the InfluxDB/Flux pulls (influxdb-client, ~/bin/fluxq). Stdlib + pandas only.

Transport (QuestDB listens on the Pi's loopback only; there is no Traefik route):
  * QUESTDB_URL set  -> plain HTTP, e.g. QUESTDB_URL=http://localhost:9000 when run on the
                        Pi, or through your own `ssh -L 9000:localhost:9000 halos` tunnel.
  * otherwise        -> `ssh $QUESTDB_SSH_HOST curl ...` on the Pi (default host "halos").

Data coverage: the QuestDB `signalk` table holds Signal K history from 2026-11-14
(signalk-questdb plugin enabled). Earlier ranges exist only in InfluxDB -- use the scripts in
the `influx-legacy/` folders for those.

Recording semantics to keep in mind: signalk-questdb is change-driven (>= 2 s apart per path)
and writes an UNCHANGED value only every ~5 min, so raw series can be sparse for slow signals.
`every=` aggregates with a mean per window (a window with no sample is simply absent, like
Flux `createEmpty: false`), and by default labels each window by its END to match Flux's
aggregateWindow(), so results line up with the old Influx pulls.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

QUESTDB_URL = os.environ.get("QUESTDB_URL", "").rstrip("/")
SSH_HOST = os.environ.get("QUESTDB_SSH_HOST", "halos")
HISTORY_START = datetime(2026, 11, 14, tzinfo=timezone.utc)

_PATH_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_EVERY_RE = re.compile(r"^(\d+)([smhd])$")
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def _ts(value) -> datetime:
    """Accept a datetime, an ISO-8601 string (Z or offset), or 'now'/'now()'."""
    if isinstance(value, datetime):
        dt = value
    elif str(value).strip().lower() in ("now", "now()"):
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _lit(dt: datetime) -> str:
    return "'" + dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ") + "'"


def _every(every: str) -> timedelta:
    m = _EVERY_RE.match(every)
    if not m:
        raise ValueError(f"every must look like 30s / 5m / 1h / 1d, got {every!r}")
    return timedelta(**{_UNIT[m.group(2)]: int(m.group(1))})


def query(sql: str) -> pd.DataFrame:
    """Run one SQL statement; return the result as a DataFrame (QuestDB /exp CSV)."""
    try:
        if QUESTDB_URL:
            url = f"{QUESTDB_URL}/exp?" + urllib.parse.urlencode({"query": sql})
            with urllib.request.urlopen(url, timeout=600) as resp:
                data = resp.read()
        else:
            # SQL goes in on stdin so it never meets a remote shell's quoting rules.
            proc = subprocess.run(
                ["ssh", SSH_HOST, "curl -sf -G http://localhost:9000/exp --data-urlencode 'query@-'"],
                input=sql.encode(), capture_output=True, check=True,
            )
            data = proc.stdout
    except (urllib.error.URLError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        raise RuntimeError(f"QuestDB query failed: {exc} {detail.decode(errors='replace')}") from exc
    if not data.strip():
        return pd.DataFrame()
    return pd.read_csv(io.BytesIO(data))


def fetch_series(path: str, start, stop="now", every: str | None = None,
                 label: str = "end", source: str | None = None,
                 context: str = "self") -> pd.Series:
    """One numeric Signal K path as a UTC-indexed Series named `path`.

    start/stop: datetime, ISO string, or 'now'. Range is [start, stop).
    every:      None for raw samples, else a mean per window ('30s', '5m', '1h', '1d').
    label:      'end' (Flux-compatible, default) or 'start' timestamp for each window.
    source:     restrict to one $source (the plugin only records the preferred source by default).
    """
    if not _PATH_RE.match(path) or (source and not _PATH_RE.match(source)):
        raise ValueError("path/source may only contain letters, digits and . _ -")
    t0, t1 = _ts(start), _ts(stop)
    if t0 < HISTORY_START:
        print(f"  NOTE: QuestDB has Signal K data only since {HISTORY_START:%Y-%m-%d}; "
              f"{t0:%Y-%m-%d} is earlier -- use the influx-legacy scripts for that range.",
              file=sys.stderr)
    where = (f"WHERE path = '{path}' AND context = {_lit_str(context)} "
             + (f"AND source = {_lit_str(source)} " if source else "")
             + f"AND ts >= {_lit(t0)} AND ts < {_lit(t1)}")
    if every:
        sql = f"SELECT ts, avg(value) AS value FROM signalk {where} SAMPLE BY {every} ALIGN TO CALENDAR"
        shift = _every(every) if label == "end" else timedelta(0)
    else:
        sql = f"SELECT ts, value FROM signalk {where} ORDER BY ts"
        shift = timedelta(0)
    df = query(sql)
    if df.empty:
        return pd.Series(dtype=float, name=path, index=pd.DatetimeIndex([], tz="UTC"))
    idx = pd.to_datetime(df["ts"], utc=True) + shift
    s = pd.Series(df["value"].astype(float).values, index=idx, name=path)
    return s.groupby(level=0).mean().sort_index() if every is None else s.sort_index()


def _lit_str(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def fetch_frame(paths: dict[str, str], start, stop="now", every: str | None = None,
                **kwargs) -> pd.DataFrame:
    """{column_name: signalk_path} -> outer-joined DataFrame of fetch_series() results."""
    return pd.DataFrame({col: fetch_series(p, start, stop, every, **kwargs)
                         for col, p in paths.items()})
