"""
Download NASA FIRMS active-fire data for one area and period, reproducibly.

    export FIRMS_MAP_KEY=your_key        # free: https://firms.modaps.eosdis.nasa.gov/api/map_key/
    python data/download_nasa_firms.py --bbox -124,36,-119,41 --start 2012-01-20 --end 2024-12-31

Defaults follow NASA's guidance to use standard-processing (science quality)
data for historical work: MODIS_SP, VIIRS_SNPP_SP, VIIRS_NOAA20_SP,
VIIRS_NOAA21_SP. Near-real-time sources (*_NRT) can be requested explicitly
with --sources for dates that standard processing has not reached yet.

What the script guarantees
- Area requests use the documented endpoint
      /api/area/csv/[MAP_KEY]/[SOURCE]/[west,south,east,north]/[DAY_RANGE]/[DATE]
  The FIRMS page documents DAY_RANGE as 1..10. Requests are made in chunks of
  5 days by default (--chunk-days), which stays inside the limit with margin.
- Every chunk is cached on disk, so an interrupted run resumes where it stopped.
- Requests are retried with exponential back-off.
- Each source is clipped to the dates FIRMS says it has (/api/data_availability).
- data/firms/manifest.json records exactly which date intervals were retrieved
  successfully for each source. The analysis uses it to tell "observed, no fire
  reported" from "no data". Failed chunks are listed and are NOT treated as zero.
- The MAP_KEY is read from the environment and is never written to disk or logs.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

API_ROOT = "https://firms.modaps.eosdis.nasa.gov/api"
DEFAULT_SOURCES = ["MODIS_SP", "VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP"]
VALID_SOURCES = ["MODIS_SP", "MODIS_NRT", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT",
                 "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT"]
MAX_DAY_RANGE = 10


class FirmsError(RuntimeError):
    pass


def plan_chunks(start: date, end: date, chunk_days: int) -> List[Tuple[date, int]]:
    """Split [start, end] into consecutive (first_day, n_days) requests with no gaps or overlaps."""
    if not 1 <= chunk_days <= MAX_DAY_RANGE:
        raise ValueError(f"chunk_days must be between 1 and {MAX_DAY_RANGE}")
    if end < start:
        return []
    chunks = []
    day = start
    while day <= end:
        n = min(chunk_days, (end - day).days + 1)
        chunks.append((day, n))
        day += timedelta(days=n)
    return chunks


def merge_intervals(chunks: List[Tuple[date, int]]) -> List[List[str]]:
    """Merge consecutive successful chunks into [start, end] ISO date intervals."""
    intervals: List[List[date]] = []
    for first, n in sorted(chunks):
        last = first + timedelta(days=n - 1)
        if intervals and first <= intervals[-1][1] + timedelta(days=1):
            intervals[-1][1] = max(intervals[-1][1], last)
        else:
            intervals.append([first, last])
    return [[a.isoformat(), b.isoformat()] for a, b in intervals]


class FirmsLimitError(FirmsError):
    """The MAP_KEY transaction limit (5000 per 10 minutes) is exhausted for now."""


def _is_limit_message(text: str) -> bool:
    lowered = (text or "").lower()
    return "limit" in lowered or "exceed" in lowered or "too many" in lowered


def _get_text(session, url: str, retries: int, backoff: float, timeout: int = 90) -> str:
    """
    GET with retries. Error text never includes the URL, because the URL holds the key.
    FIRMS answers a used-up transaction limit with HTTP 400 or 429 and a short message;
    that case raises FirmsLimitError so the caller can wait and retry.
    """
    problem = "no attempt made"
    for attempt in range(retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.text
            message = " ".join(str(getattr(response, "text", "") or "").split())[:160]
            if response.status_code == 429 or _is_limit_message(message):
                raise FirmsLimitError(f"HTTP {response.status_code}: {message or 'transaction limit'}")
            problem = f"HTTP {response.status_code}" + (f": {message}" if message else "")
            if response.status_code in (400, 401, 403, 404):
                break
        except FirmsLimitError:
            raise
        except requests.RequestException as exc:
            problem = type(exc).__name__
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    raise FirmsError(f"request failed: {problem}")


def parse_firms_csv(text: str) -> pd.DataFrame:
    """
    FIRMS answers errors with HTTP 200 and a plain-text message (for example an
    invalid key or an exceeded transaction limit). Anything that is not a CSV
    with a latitude column is treated as an error, never as "no fires".
    """
    head = text.lstrip()[:200].lower()
    if not head.startswith("latitude"):
        message = " ".join(text.strip().split())[:160] or "empty response"
        raise FirmsError(f"FIRMS did not return CSV data: {message}")
    return pd.read_csv(io.StringIO(text), dtype={"satellite": str, "confidence": str,
                                                 "version": str, "acq_time": str})


def _fetch_csv_text(session, url: str, retries: int, backoff: float, limit_wait: float, log) -> str:
    """
    Fetch one chunk and make sure it is CSV before it is cached. If the MAP_KEY
    transaction limit is used up (it resets within 10 minutes), wait and try the
    same chunk again instead of recording it as failed.
    """
    for wait_round in range(15):
        try:
            text = _get_text(session, url, retries, backoff)
            parse_firms_csv(text)
            return text
        except FirmsError as exc:
            limited = isinstance(exc, FirmsLimitError) or _is_limit_message(str(exc))
            if limited and wait_round < 14:
                log(f"  FIRMS transaction limit reached ({exc}); waiting {limit_wait:.0f} s, then continuing")
                time.sleep(limit_wait)
                continue
            raise
    raise FirmsError("transaction limit still exceeded after waiting")


def data_availability(session, key: str, source: str, retries: int, backoff: float
                      ) -> Optional[Tuple[date, date]]:
    """(min_date, max_date) FIRMS holds for a source, or None if it cannot be determined."""
    url = f"{API_ROOT}/data_availability/csv/{key}/all"
    try:
        text = _get_text(session, url, retries, backoff)
        table = pd.read_csv(io.StringIO(text))
        table.columns = [c.lower().strip() for c in table.columns]
        row = table[table["data_id"].astype(str).str.upper() == source]
        if row.empty:
            return None
        return (date.fromisoformat(str(row["min_date"].iloc[0])[:10]),
                date.fromisoformat(str(row["max_date"].iloc[0])[:10]))
    except Exception:
        return None


def download(bbox: Tuple[float, float, float, float], start: date, end: date,
             sources: List[str], out_dir: str, key: str, chunk_days: int = 5,
             retries: int = 4, backoff: float = 2.0, pause: float = 0.25,
             limit_wait: float = 60.0, session=None, log=print) -> Dict:
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west,south,east,north inside -180,-90,180,90")
    for source in sources:
        if source not in VALID_SOURCES:
            raise ValueError(f"unknown source {source}; choose from {VALID_SOURCES}")
    session = session or requests.Session()
    area = f"{west:g},{south:g},{east:g},{north:g}"
    os.makedirs(out_dir, exist_ok=True)
    manifest: Dict = {
        "synthetic": False,
        "provider": "NASA FIRMS (Fire Information for Resource Management System), LANCE / EOSDIS",
        "api": f"{API_ROOT}/area/csv/[MAP_KEY]/[SOURCE]/{area}/[DAY_RANGE]/[DATE]",
        "bbox": [west, south, east, north],
        "requested": {"start": start.isoformat(), "end": end.isoformat()},
        "chunk_days": chunk_days,
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {},
        "platform_gaps": {},
    }
    for source in sources:
        cache_dir = os.path.join(out_dir, "_chunks", source, area.replace(",", "_"))
        os.makedirs(cache_dir, exist_ok=True)
        available = data_availability(session, key, source, retries, backoff)
        s, e = start, end
        if available:
            s, e = max(start, available[0]), min(end, available[1])
        entry = {"available_in_firms": [d.isoformat() for d in available] if available else None,
                 "coverage": [], "failed_chunks": [], "rows": 0}
        ok_chunks, frames = [], []
        chunks = plan_chunks(s, e, chunk_days)
        log(f"{source}: {len(chunks)} request(s) for {s} .. {e}" if chunks
            else f"{source}: no dates inside the requested period")
        for i, (first, n) in enumerate(chunks, 1):
            cache = os.path.join(cache_dir, f"{first.isoformat()}_{n}.csv")
            try:
                if os.path.exists(cache):
                    with open(cache, "r", encoding="utf-8") as handle:
                        text = handle.read()
                else:
                    url = f"{API_ROOT}/area/csv/{key}/{source}/{area}/{n}/{first.isoformat()}"
                    text = _fetch_csv_text(session, url, retries, backoff, limit_wait, log)
                    with open(cache, "w", encoding="utf-8") as handle:
                        handle.write(text)
                    time.sleep(pause)
                frames.append(parse_firms_csv(text))
                ok_chunks.append((first, n))
            except FirmsError as exc:
                entry["failed_chunks"].append({"start": first.isoformat(), "days": n, "error": str(exc)})
                log(f"  chunk {first} (+{n}d) failed: {exc}")
            if i % 50 == 0:
                log(f"  {i}/{len(chunks)} done")
        entry["coverage"] = merge_intervals(ok_chunks)
        frames = [f for f in frames if len(f)]
        table = pd.concat(frames, ignore_index=True).drop_duplicates() if frames else pd.DataFrame()
        if len(table):
            table.to_csv(os.path.join(out_dir, f"{source}.csv"), index=False)
            entry["rows"] = int(len(table))
        if available is None:
            # Without the availability table an empty answer for dates FIRMS has not
            # processed yet looks like "no fire". Be conservative: coverage stops at
            # the last date that actually returned a detection.
            entry["availability_unknown"] = True
            last = str(table["acq_date"].max())[:10] if len(table) else None
            entry["coverage"] = ([[a, min(b, last)] for a, b in entry["coverage"] if a <= last]
                                 if last else [])
            log(f"  warning: could not read FIRMS data availability for {source}; "
                f"coverage is limited to dates up to the last detection ({last}).")
        manifest["sources"][source] = entry
        log(f"{source}: {entry['rows']} rows, {len(entry['failed_chunks'])} failed chunk(s)")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


def _join_bbox(argv):
    """Let '--bbox -9.6,36.9,-6.1,42.2' work: argparse reads a value that starts with '-' as an option."""
    argv = list(sys.argv[1:] if argv is None else argv)
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--bbox" and i + 1 < len(argv):
            out.append("--bbox=" + argv[i + 1])
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Download NASA FIRMS active-fire data for an area and period.")
    parser.add_argument("--bbox", required=True, help="west,south,east,north in degrees, e.g. -124,36,-119,41")
    parser.add_argument("--start", required=True, help="first date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="last date, YYYY-MM-DD")
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES),
                        help=f"comma-separated FIRMS sources (default: {','.join(DEFAULT_SOURCES)})")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "firms"))
    parser.add_argument("--chunk-days", type=int, default=5, help="days per request, 1-10 (default 5)")
    args = parser.parse_args(_join_bbox(argv))

    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        print("Set the FIRMS_MAP_KEY environment variable first. A key is free: "
              "https://firms.modaps.eosdis.nasa.gov/api/map_key/", file=sys.stderr)
        return 2
    try:
        bbox = tuple(float(v) for v in args.bbox.split(","))
        if len(bbox) != 4:
            raise ValueError
    except ValueError:
        print("--bbox must be four numbers: west,south,east,north", file=sys.stderr)
        return 2
    manifest = download(bbox, date.fromisoformat(args.start), date.fromisoformat(args.end),
                        [s.strip() for s in args.sources.split(",") if s.strip()],
                        args.out, key, args.chunk_days)
    failed = sum(len(v["failed_chunks"]) for v in manifest["sources"].values())
    print(f"Wrote {args.out}/manifest.json. Failed chunks: {failed}."
          + (" Re-run the same command to retry only the failed ones." if failed else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())