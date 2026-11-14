"""
One command from an empty data folder to a real-data result:

    python scripts/make_submission.py
    python scripts/make_submission.py --bbox -9.6,36.9,-6.1,42.2 --start 2018-04-01 --end 2024-12-31

It (1) downloads NASA FIRMS standard-processing data for the area and period,
(2) runs the validation case study, (3) writes the real-data result into README.md.

The FIRMS MAP_KEY is read from the FIRMS_MAP_KEY environment variable, or asked
for without echo. It is never written to disk. Get a free key at
https://firms.modaps.eosdis.nasa.gov/api/map_key/

The download is resumable: if it is interrupted, run the same command again.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from data.download_nasa_firms import download          # noqa: E402
from scripts import run_case_study                      # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Download FIRMS data, validate, and fill the README result.")
    parser.add_argument("--bbox", default="-124,36,-119,41", help="west,south,east,north (default: northern California)")
    parser.add_argument("--start", default="2018-04-01", help="first date (default: start of NOAA-20 data)")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--sources", default="MODIS_SP,VIIRS_SNPP_SP,VIIRS_NOAA20_SP")
    parser.add_argument("--chunk-days", type=int, default=5)
    args = parser.parse_args(argv)

    try:
        bbox = tuple(float(v) for v in args.bbox.split(","))
        assert len(bbox) == 4
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    except (ValueError, AssertionError):
        print("Check --bbox (four numbers: west,south,east,north) and the dates (YYYY-MM-DD).", file=sys.stderr)
        return 2
    key = os.environ.get("FIRMS_MAP_KEY", "").strip() or getpass.getpass("FIRMS MAP_KEY (input hidden): ").strip()
    if not key:
        print("A MAP_KEY is required. It is free: https://firms.modaps.eosdis.nasa.gov/api/map_key/", file=sys.stderr)
        return 2

    out_dir = os.path.join(ROOT, "data", "firms")
    print("Step 1 of 3: downloading NASA FIRMS data (resumable; this can take 20 to 60 minutes)")
    manifest = download(bbox, start, end, [s.strip() for s in args.sources.split(",") if s.strip()],
                        out_dir, key, args.chunk_days)
    rows = sum(v["rows"] for v in manifest["sources"].values())
    failed = sum(len(v["failed_chunks"]) for v in manifest["sources"].values())
    if rows == 0:
        first_error = next((c["error"] for v in manifest["sources"].values() for c in v["failed_chunks"]), None)
        print("No data were retrieved." + (f" First error: {first_error}" if first_error else
                                           " The area and period contain no detections."), file=sys.stderr)
        return 1
    if failed:
        print(f"{failed} request(s) failed. They are recorded as gaps, not as zero fire. "
              "Run the same command again to retry only those.")

    print("Step 2 of 3: validation case study")
    code = run_case_study.main(["--data-dir", out_dir, "--out", os.path.join(ROOT, "docs", "case_study"),
                                "--update-readme"])
    if code != 0:
        return code
    print("Step 3 of 3: done. Next:")
    print("  python app.py                      # look at the real-data dashboard")
    print("  git add -A && git commit -m \"Real-data case study\" && git push")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
