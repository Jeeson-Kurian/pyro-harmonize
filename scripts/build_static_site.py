"""
Build the online demo: a static copy of the dashboard with the analysis computed in advance.

    python scripts/build_static_site.py            # uses data/firms, writes docs/index.html + docs/demo-data/

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

from engine.pipeline import AnalysisConfig, dataset_meta, export_frame, load_dataset, run_analysis  # noqa: E402


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, allow_nan=False, separators=(",", ":"))


def build(data_dir: str | None, out_dir: str) -> dict:
    detections, manifest, info = load_dataset(data_dir)
    if info["mode"] != "firms":
        raise SystemExit("No NASA FIRMS files found; the online demo is only built from real data.")
    analysis = run_analysis(detections, manifest, AnalysisConfig(), info)
    if analysis.summary.get("empty"):
        raise SystemExit(analysis.summary["message"])
    data_out = os.path.join(out_dir, "demo-data")
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
    for kind in ("daily", "monthly"):
        frame = export_frame(analysis, kind)
        frame.insert(0, "data_mode", "NASA FIRMS")
        frame.to_csv(os.path.join(data_out, f"{kind}.csv"), index=False)

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
    return {"map_window": [start, end], "files": sorted(os.listdir(data_out))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the static online demo into docs/.")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--out", default=os.path.join(ROOT, "docs"))
    args = parser.parse_args(argv)
    result = build(args.data_dir, args.out)
    print(f"Wrote {args.out}/index.html and demo-data/ ({', '.join(result['files'])}); "
          f"map window {result['map_window'][0]} to {result['map_window'][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
