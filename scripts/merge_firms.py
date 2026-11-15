"""
Merge FIRMS downloads of the SAME area into one data folder, e.g. an earlier period
downloaded later:

    python scripts/merge_firms.py --into data/firms data/extend/california_modis data/extend/california_snpp

For every source the detections are concatenated and exact duplicates removed, and the
manifest coverage intervals are joined (touching intervals become one, so no artificial
gap appears at the seam). Failed chunks stay recorded as gaps. Folders with a different
bounding box are refused: coverage is only meaningful for the area that was requested.
The result is written as <SOURCE>.csv.gz (the loader reads .csv and .csv.gz).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date, timedelta
from typing import Dict, List

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from engine.data_loader import source_from_filename  # noqa: E402


def join_intervals(intervals: List[List[str]]) -> List[List[str]]:
    """Sort and join overlapping or touching [start, end] date intervals (inclusive)."""
    out: List[List[date]] = []
    for a, b in sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in intervals):
        if out and a <= out[-1][1] + timedelta(days=1):
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[a.isoformat(), b.isoformat()] for a, b in out]


def _read_folder(folder: str):
    with open(os.path.join(folder, "manifest.json"), "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    files: Dict[str, List[str]] = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.csv")) + glob.glob(os.path.join(folder, "*.csv.gz"))):
        source = source_from_filename(path)
        if source is None:
            raise SystemExit(f"Cannot tell the FIRMS source of {path}")
        files.setdefault(source, []).append(path)
    return manifest, files


def merge(into: str, others: List[str], log=print) -> Dict:
    folders = [into] + list(others)
    parts = [_read_folder(f) for f in folders]
    bbox = [round(float(v), 6) for v in parts[0][0]["bbox"]]
    for folder, (manifest, _) in zip(folders[1:], parts[1:]):
        if [round(float(v), 6) for v in manifest["bbox"]] != bbox:
            raise SystemExit(f"{folder} covers {manifest['bbox']}, not {bbox}: refusing to merge different areas.")
        if manifest.get("synthetic"):
            raise SystemExit(f"{folder} holds synthetic data: refusing to merge it with real data.")

    merged = dict(parts[0][0])
    merged["requested"] = {"start": min(m["requested"]["start"] for m, _ in parts),
                           "end": max(m["requested"]["end"] for m, _ in parts)}
    merged["retrieved_utc"] = max(m["retrieved_utc"] for m, _ in parts)
    merged["merged_from"] = [{"folder": os.path.relpath(f, ROOT).replace(os.sep, "/"),
                              "requested": m["requested"], "retrieved_utc": m["retrieved_utc"],
                              "chunk_days": m.get("chunk_days")} for f, (m, _) in zip(folders, parts)]
    merged["chunk_days"] = sorted({m.get("chunk_days") for m, _ in parts if m.get("chunk_days")})
    merged["sources"], merged["platform_gaps"] = {}, {}
    for manifest, _ in parts:
        for platform, gaps in (manifest.get("platform_gaps") or {}).items():
            merged["platform_gaps"].setdefault(platform, []).extend(gaps)

    sources = sorted({s for _, files in parts for s in files} | {s for m, _ in parts for s in m["sources"]})
    tables = {}
    for source in sources:
        entries = [m["sources"][source] for m, _ in parts if source in m["sources"]]
        frames = [pd.read_csv(p, dtype=str) for _, files in parts for p in files.get(source, [])]
        table = pd.concat(frames, ignore_index=True).drop_duplicates() if frames else pd.DataFrame()
        tables[source] = table
        available = next((e["available_in_firms"] for e in entries if e.get("available_in_firms")), None)
        merged["sources"][source] = {
            "available_in_firms": available,
            "coverage": join_intervals([iv for e in entries for iv in e.get("coverage", [])]),
            "failed_chunks": [c for e in entries for c in e.get("failed_chunks", [])],
            "rows": int(len(table)),
        }
        if any(e.get("availability_unknown") for e in entries):
            merged["sources"][source]["availability_unknown"] = True
        log(f"{source}: {len(table):,} rows, coverage {merged['sources'][source]['coverage']}")

    # write only after everything was read and checked
    for source, table in tables.items():
        for old in glob.glob(os.path.join(into, f"{source}.csv")) + glob.glob(os.path.join(into, f"{source}.csv.gz")):
            os.remove(old)
        if len(table):
            table.to_csv(os.path.join(into, f"{source}.csv.gz"), index=False)
    with open(os.path.join(into, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2)
    return merged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Merge FIRMS downloads of the same area into one folder.")
    parser.add_argument("--into", required=True, help="folder that receives the merged data (e.g. data/firms)")
    parser.add_argument("folders", nargs="+", help="other download folders of the same area")
    args = parser.parse_args(argv)
    merge(args.into, args.folders)
    return 0


if __name__ == "__main__":
    sys.exit(main())
