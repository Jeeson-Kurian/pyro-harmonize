"""
Build the online demo: a static copy of the dashboard with the analysis computed in advance.

    python scripts/build_static_site.py            # the three validated regions -> docs/index.html + docs/demo-data/
    python scripts/build_static_site.py --data-dir data/firms   # one region only

GitHub Pages can serve docs/ as a website (Settings -> Pages -> Deploy from a branch ->
main, /docs). Static hosting cannot run Python, so the page shows the full analysis of the
loaded data; choosing another area or period needs the full app (python app.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from engine.pipeline import (AnalysisConfig, dataset_meta, export_frame, load_dataset,  # noqa: E402
                             modis_switch_off_test, run_analysis)


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, allow_nan=False, separators=(",", ":"))


# Regions of the online demo. The first is the default and keeps the original paths
# (docs/demo-data/*.json); the others go to docs/demo-data/<id>/.
REGIONS = [
    {"id": "california", "label": "Northern California, USA (2000-2024)", "data": "data/firms", "dir": ""},
    {"id": "portugal", "label": "Portugal (2018-2024)", "data": "data/regions/portugal", "dir": "portugal"},
    {"id": "australia", "label": "Northern Australia, tropical savanna (2018-2024)", "data": "data/regions/australia",
     "dir": "australia"},
]


def build_region(data_dir: str | None, data_out: str) -> dict:
    """Pre-compute every API answer the page needs for one region into data_out."""
    detections, manifest, info = load_dataset(data_dir)
    if info["mode"] != "firms":
        raise SystemExit("No NASA FIRMS files found; the online demo is only built from real data.")
    analysis = run_analysis(detections, manifest, AnalysisConfig(), info)
    if analysis.summary.get("empty"):
        raise SystemExit(analysis.summary["message"])
    os.makedirs(data_out, exist_ok=True)

    _write_json(os.path.join(data_out, "meta.json"), dataset_meta(detections, manifest, info))
    _write_json(os.path.join(data_out, "analysis.json"), analysis.summary)
    # the map opens on the first 10 days of the month with the most harmonised activity,
    # exactly as the page chooses it
    busiest = analysis.monthly["cells"].fillna(0.0).idxmax()
    start = f"{busiest}-01"
    end = f"{busiest}-10"
    _write_json(os.path.join(data_out, "clusters.json"), analysis.clusters(start, end, 2.0))
    _write_json(os.path.join(data_out, "sensitivity.json"), analysis.radius_sensitivity())
    _write_json(os.path.join(data_out, "switch_off.json"), modis_switch_off_test(detections, manifest, analysis))
    for kind in ("daily", "monthly"):
        frame = export_frame(analysis, kind)
        frame.insert(0, "data_mode", "NASA FIRMS")
        frame.to_csv(os.path.join(data_out, f"{kind}.csv"), index=False)
    return {"map_window": [start, end], "files": sorted(f for f in os.listdir(data_out) if "." in f)}


def write_page(out_dir: str) -> None:
    with open(os.path.join(ROOT, "web", "index.html"), "r", encoding="utf-8") as handle:
        page = handle.read()
    marker = "<head>"
    if page.count(marker) != 1:
        raise SystemExit("web/index.html has an unexpected structure")
    page = page.replace(marker, marker + "\n<script>window.PYRO_STATIC = true;</script>", 1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(page)
    # GitHub Pages: serve files as they are (no Jekyll processing)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()


def build(data_dir: str | None, out_dir: str) -> dict:
    """One region (the original behaviour): data_dir -> docs/demo-data/."""
    result = build_region(data_dir, os.path.join(out_dir, "demo-data"))
    write_page(out_dir)
    return result


def build_all(out_dir: str) -> dict:
    """All demo regions, plus demo-data/regions.json that the page uses for its region menu."""
    results, listing = {}, []
    for region in REGIONS:
        data_out = os.path.join(out_dir, "demo-data", region["dir"]) if region["dir"] else os.path.join(out_dir, "demo-data")
        results[region["id"]] = build_region(os.path.join(ROOT, region["data"]), data_out)
        listing.append({"id": region["id"], "label": region["label"],
                        "path": "demo-data" + ("/" + region["dir"] if region["dir"] else ""),
                        "data": region["data"]})
        print(f"{region['label']}: map window {results[region['id']]['map_window'][0]} to {results[region['id']]['map_window'][1]}")
    _write_json(os.path.join(out_dir, "demo-data", "regions.json"), listing)
    write_page(out_dir)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the static online demo into docs/.")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--out", default=os.path.join(ROOT, "docs"))
    args = parser.parse_args(argv)
    if args.data_dir:
        result = build(args.data_dir, args.out)
        print(f"Wrote {args.out}/index.html and demo-data/ ({', '.join(result['files'])}); "
              f"map window {result['map_window'][0]} to {result['map_window'][1]}")
    else:
        build_all(args.out)
        print(f"Wrote {args.out}/index.html and demo-data/ for {len(REGIONS)} regions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
