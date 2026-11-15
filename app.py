"""
PyroHarmonize web application (NASA Space Apps 2026, "Harmonization of MODIS and
VIIRS Hot Spots").

Run:   python app.py        then open http://127.0.0.1:8000

Data:  real NASA FIRMS files in data/firms/ are used whenever they exist
       (see data/download_nasa_firms.py). Without them the app starts in a
       clearly labelled SYNTHETIC demo mode. Set PYRO_DEMO=1 to force demo mode,
       PYRO_DATA_DIR=/path to use another folder.

This file only exposes the engine over HTTP. All science lives in engine/.
"""

from __future__ import annotations

import io
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Iterator, Optional, Tuple

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from engine import __version__
from engine.pipeline import Analysis, AnalysisConfig, dataset_meta, export_frame, load_dataset, run_analysis

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_SIZE = 8

app = FastAPI(
    title="PyroHarmonize",
    description="MODIS / VIIRS active-fire harmonisation and burning activity calendar (NASA FIRMS data).",
    version=__version__,
)

_lock = threading.Lock()
_dataset: Optional[Tuple[Any, Any, Dict[str, Any]]] = None
_cache: "OrderedDict[AnalysisConfig, Analysis]" = OrderedDict()


def get_dataset():
    """Load the detections once per process."""
    global _dataset
    with _lock:
        if _dataset is None:
            _dataset = load_dataset()
        return _dataset


def make_config(west: Optional[float], south: Optional[float], east: Optional[float],
                north: Optional[float], start: Optional[str], end: Optional[str],
                cell_km: float) -> AnalysisConfig:
    corners = [west, south, east, north]
    given = [c is not None for c in corners]
    if any(given) and not all(given):
        raise HTTPException(status_code=400, detail="Give all four of west, south, east, north, or none.")
    bbox = None
    if all(given):
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise HTTPException(status_code=400,
                                detail="Area must satisfy -180 <= west < east <= 180 and -90 <= south < north <= 90.")
        bbox = (round(west, 4), round(south, 4), round(east, 4), round(north, 4))
    for label, value in (("start", start), ("end", end)):
        if value:
            try:
                import datetime as _dt
                _dt.date.fromisoformat(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"{label} must be a date in the form YYYY-MM-DD.")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start must not be after end.")
    if not 2.0 <= cell_km <= 50.0:
        raise HTTPException(status_code=400, detail="cell_km must be between 2 and 50.")
    return AnalysisConfig(bbox=bbox, start=start or None, end=end or None, cell_km=float(cell_km))


def get_analysis(config: AnalysisConfig) -> Analysis:
    """Bounded least-recently-used cache of analyses."""
    with _lock:
        if config in _cache:
            _cache.move_to_end(config)
            return _cache[config]
    detections, manifest, info = get_dataset()
    analysis = run_analysis(detections, manifest, config, info)
    with _lock:
        _cache[config] = analysis
        _cache.move_to_end(config)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return analysis


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/meta")
def meta():
    """What data the server holds: real FIRMS files or the synthetic demo."""
    detections, manifest, info = get_dataset()
    return dataset_meta(detections, manifest, info)


@app.get("/api/analysis")
def analysis(west: Optional[float] = None, south: Optional[float] = None,
             east: Optional[float] = None, north: Optional[float] = None,
             start: Optional[str] = None, end: Optional[str] = None, cell_km: float = 10.0):
    """Full analysis for an area (west, south, east, north in degrees) and period (YYYY-MM-DD)."""
    config = make_config(west, south, east, north, start, end, cell_km)
    return JSONResponse(content=get_analysis(config).summary)


@app.get("/api/clusters")
def clusters(date_from: str, date_to: str, eps_km: float = 2.0,
             west: Optional[float] = None, south: Optional[float] = None,
             east: Optional[float] = None, north: Optional[float] = None,
             start: Optional[str] = None, end: Optional[str] = None, cell_km: float = 10.0):
    """Hot-spot clusters (geodesic DBSCAN per overpass) for a short window, for the map."""
    config = make_config(west, south, east, north, start, end, cell_km)
    make_config(None, None, None, None, date_from, date_to, 10.0)
    if not 0.2 <= eps_km <= 20.0:
        raise HTTPException(status_code=400, detail="eps_km must be between 0.2 and 20.")
    return JSONResponse(content=get_analysis(config).clusters(date_from, date_to, eps_km))


@app.get("/api/sensitivity")
def sensitivity(west: Optional[float] = None, south: Optional[float] = None,
                east: Optional[float] = None, north: Optional[float] = None,
                start: Optional[str] = None, end: Optional[str] = None, cell_km: float = 10.0):
    """How cluster counts depend on the clustering radius (0.5, 1, 2, 5 km)."""
    config = make_config(west, south, east, north, start, end, cell_km)
    return JSONResponse(content=get_analysis(config).radius_sensitivity())


def _csv_chunks(frame, mode_label: str) -> Iterator[str]:
    frame = frame.copy()
    frame.insert(0, "data_mode", mode_label)
    step = 50000
    for i in range(0, max(len(frame), 1), step):
        buffer = io.StringIO()
        frame.iloc[i:i + step].to_csv(buffer, index=False, header=(i == 0))
        yield buffer.getvalue()


@app.get("/api/export/{kind}")
def export(kind: str, west: Optional[float] = None, south: Optional[float] = None,
           east: Optional[float] = None, north: Optional[float] = None,
           start: Optional[str] = None, end: Optional[str] = None, cell_km: float = 10.0):
    """
    CSV download: kind = detections | daily | monthly | cells.
    Every row carries data_mode ("NASA FIRMS" or "SYNTHETIC - not satellite data");
    detections also carry the FIRMS source, product version and processing level.
    """
    kind = kind[:-4] if kind.endswith(".csv") else kind
    if kind not in ("detections", "daily", "monthly", "cells"):
        raise HTTPException(status_code=404, detail="kind must be detections, daily, monthly or cells")
    config = make_config(west, south, east, north, start, end, cell_km)
    result = get_analysis(config)
    if result.summary.get("empty"):
        raise HTTPException(status_code=404, detail="No data in the selected area and period.")
    label = "SYNTHETIC - not satellite data" if result.summary.get("synthetic") else "NASA FIRMS"
    frame = export_frame(result, kind)
    return StreamingResponse(_csv_chunks(frame, label), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="pyroharmonize_{kind}.csv"'})


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(ROOT, "web", "index.html"), "r", encoding="utf-8") as handle:
        return HTMLResponse(content=handle.read())


def _warm_up() -> None:
    """Run the default analysis once at start-up so the first visitor does not wait."""
    try:
        get_analysis(AnalysisConfig())
    except Exception as exc:  # the page still works; the error shows on first request
        print(f"Warm-up failed: {exc}")


if __name__ == "__main__":
    threading.Thread(target=_warm_up, daemon=True).start()
    # Pass the app object (not "app:app") so the server uses this module, whose
    # cache the warm-up thread fills.
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
