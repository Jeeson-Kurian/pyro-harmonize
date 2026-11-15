"""
End-to-end analysis: detections -> quality control -> common units -> coverage
-> cross-sensor calibration with held-out validation -> harmonised daily record
-> calendar, anomalies, critical periods, seasonality.

The harmonised record is "Aqua-MODIS-equivalent" and is assembled per local date
with a fixed priority, and the source of every day is kept:

    1  Aqua MODIS observed            (the reference itself)
    2  VIIRS-derived                  (mean of the calibrated VIIRS platforms that
                                       delivered data that day; several satellites
                                       are averaged, never added)
    3  Terra-derived                  (morning orbit converted to the afternoon
                                       reference; used only where 1 and 2 are absent)
    0  no data
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict, replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import anomaly as anomaly_mod
from . import calendar_generator as cal
from .data_loader import load_firms_directory, quality_filter, standardize_firms
from .gridding import add_keys, build_cell_table
from .harmonizer import METHOD_LABELS, TargetCalibration, _score, monthly_interval
from .matching import build_pairs, platform_coverage
from .schema import PLATFORM_LABELS, PLATFORMS, REFERENCE_PLATFORM
from .spatial_cluster import OverpassClusterer, radius_sensitivity

# Clustering 300,000 real detections takes about 2 s, so this keeps the map responsive.
MAX_MAP_DETECTIONS = 400_000

SOURCE_LABELS = {0: "no data", 1: "Aqua MODIS observed", 2: "VIIRS-derived (Aqua-equivalent)",
                 3: "Terra-derived (Aqua-equivalent)"}


@dataclass(frozen=True)
class AnalysisConfig:
    bbox: Optional[Tuple[float, float, float, float]] = None   # west, south, east, north
    start: Optional[str] = None
    end: Optional[str] = None
    cell_km: float = 10.0
    drop_low_confidence: bool = True
    vegetation_only: bool = True
    # Test scenario: treat MODIS (Terra and Aqua) as switched off from this local date.
    # Its detections and coverage are removed, so calibration can only learn from earlier
    # years and the record must continue from VIIRS alone. See modis_switch_off_test().
    modis_off_from: Optional[str] = None


def json_safe(obj: Any) -> Any:
    """Recursively convert numpy / pandas values; NaN and NaT become None."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [json_safe(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(obj) else pd.Timestamp(obj).strftime("%Y-%m-%d")
    if isinstance(obj, pd.Period):
        return str(obj)
    if obj is pd.NaT:
        return None
    return obj


# ------------------------------------------------------------------- data sources

def load_dataset(data_dir: Optional[str] = None, force_synthetic: bool = False
                 ) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Real NASA FIRMS files are used whenever they exist in the data directory
    (default: data/firms, or the PYRO_DATA_DIR environment variable).
    Only if none exist, or PYRO_DEMO=1 is set, the synthetic simulator is used,
    and the result is labelled as simulated everywhere.
    """
    data_dir = data_dir or os.environ.get("PYRO_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "firms")
    force_synthetic = force_synthetic or os.environ.get("PYRO_DEMO", "") == "1"
    has_files = os.path.isdir(data_dir) and any(f.lower().endswith((".csv", ".csv.gz")) for f in os.listdir(data_dir))
    if has_files and not force_synthetic:
        detections, provenance = load_firms_directory(data_dir)
        info = {"mode": "firms", "data_dir": data_dir, "files": provenance["files"]}
        return detections, provenance["manifest"], info
    from .synthetic import generate_synthetic_firms
    sim = generate_synthetic_firms()
    frames = [standardize_firms(frame, source=source) for source, frame in sim["frames"].items()]
    detections = pd.concat(frames, ignore_index=True)
    info = {"mode": "synthetic", "data_dir": None,
            "files": [{"file": "(generated in memory)", "source": s, "rows": int(len(f))}
                      for s, f in sim["frames"].items()],
            "why": ("PYRO_DEMO=1 is set" if force_synthetic
                    else "no FIRMS CSV files were found in the data folder (data/firms by default)")}
    return detections, sim["manifest"], info


def dataset_meta(detections: pd.DataFrame, manifest: Optional[Dict[str, Any]],
                 info: Dict[str, Any]) -> Dict[str, Any]:
    """What data are loaded: real FIRMS files or the synthetic demo. Used by /api/meta."""
    from . import __version__
    bbox = (manifest or {}).get("bbox")
    if not bbox and len(detections):
        bbox = [float(detections["longitude"].min()), float(detections["latitude"].min()),
                float(detections["longitude"].max()), float(detections["latitude"].max())]
    requested = (manifest or {}).get("requested") or {}
    return json_safe({
        "version": __version__,
        "mode": info["mode"],
        "synthetic": info["mode"] == "synthetic",
        "why_synthetic": info.get("why"),
        "files": info.get("files", []),
        "bbox": bbox,
        "start": requested.get("start") or (detections["acq_date"].min() if len(detections) else None),
        "end": requested.get("end") or (detections["acq_date"].max() if len(detections) else None),
        "rows": int(len(detections)),
        "manifest": {k: v for k, v in (manifest or {}).items() if k in
                     ("provider", "api", "retrieved_utc", "requested", "bbox", "sources", "note", "platform_gaps")},
    })


# ------------------------------------------------------------------------ analysis

class Analysis:
    """Result of one run. `summary` is JSON-ready; the frames back the CSV exports."""

    def __init__(self) -> None:
        self.config: Optional[AnalysisConfig] = None
        self.summary: Dict[str, Any] = {}
        self.detections = pd.DataFrame()
        self.cells = pd.DataFrame()
        self.daily = pd.DataFrame()
        self.monthly = pd.DataFrame()
        self.calibrations: Dict[str, TargetCalibration] = {}
        self.coverage = pd.DataFrame()

    # -- lazily computed extras ---------------------------------------------------
    def clusters(self, start: str, end: str, eps_km: float = 2.0, limit: int = 600) -> Dict[str, Any]:
        d = self.detections
        if d.empty:
            return {"clusters": [], "total_clusters": 0, "detections": 0}
        window = d[(d["local_date"] >= np.datetime64(start)) & (d["local_date"] <= np.datetime64(end))]
        if len(window) > MAX_MAP_DETECTIONS:
            return {"error": f"{len(window):,} detections in this window; choose a shorter period "
                             f"(the limit for the map is {MAX_MAP_DETECTIONS:,})."}
        clusters = OverpassClusterer(eps_km=eps_km).cluster(window)
        total = len(clusters)
        top = clusters.sort_values("n_pixels", ascending=False).head(limit)
        rows = [{
            "lat": round(float(r.centroid_lat), 4), "lon": round(float(r.centroid_lon), 4),
            "platform": r.platform, "sensor": r.sensor,
            "time_utc": pd.Timestamp(r.time_utc).strftime("%Y-%m-%d %H:%M"),
            "local_date": pd.Timestamp(r.local_date).strftime("%Y-%m-%d"), "slot": r.slot,
            "n_pixels": int(r.n_pixels),
            "frp_sum_mw": None if not np.isfinite(r.frp_sum_mw) else round(float(r.frp_sum_mw), 1),
            "processing": r.processing,
        } for r in top.itertuples()]
        return {"clusters": rows, "total_clusters": int(total), "shown": len(rows),
                "detections": int(len(window)), "eps_km": eps_km,
                "note": "A cluster is a group of adjacent hot-spot pixels from one platform in one "
                        "overpass. It is not a confirmed fire."}

    def radius_sensitivity(self) -> Dict[str, Any]:
        d = self.detections
        if d.empty:
            return {"rows": []}
        month = pd.DatetimeIndex(d["local_date"]).to_period("M")
        busiest = month.value_counts().idxmax()
        sample = d[month == busiest]
        if len(sample) > MAX_MAP_DETECTIONS:   # keep it fast: first 7 days of that month
            sample = sample[sample["local_date"] <= sample["local_date"].min() + np.timedelta64(6, "D")]
        first = pd.Timestamp(sample["local_date"].min()).strftime("%Y-%m-%d")
        last = pd.Timestamp(sample["local_date"].max()).strftime("%Y-%m-%d")
        return {"sample_month": str(busiest), "sample_period": f"{first} to {last}",
                "detections": int(len(sample)), "rows": radius_sensitivity(sample)}


def _daily_by_platform(cells: pd.DataFrame, dates: pd.DatetimeIndex, value: str, how: str) -> pd.DataFrame:
    if cells.empty:
        return pd.DataFrame(index=dates)
    grouped = cells.groupby(["local_date", "platform"])[value]
    table = (grouped.size() if how == "size" else grouped.sum(min_count=1)).unstack("platform")
    return table.reindex(dates)


def run_analysis(detections: pd.DataFrame, manifest: Optional[Dict[str, Any]] = None,
                 config: Optional[AnalysisConfig] = None,
                 dataset_info: Optional[Dict[str, Any]] = None) -> Analysis:
    config = config or AnalysisConfig()
    result = Analysis()
    result.config = config
    notes: List[str] = []

    # 1. subset -------------------------------------------------------------------
    data = detections
    # The area for which data were obtained. Outside it nothing is known, so a
    # selection is clipped to it: an area that was never downloaded must not be
    # reported as "observed, no fire".
    data_bbox = (manifest or {}).get("bbox")
    if not data_bbox and len(detections):
        data_bbox = [float(detections["longitude"].min()), float(detections["latitude"].min()),
                     float(detections["longitude"].max()), float(detections["latitude"].max())]
    bbox = tuple(data_bbox) if data_bbox else None
    if config.bbox is not None:
        west, south, east, north = config.bbox
        if not (west < east and south < north):
            raise ValueError("bbox must be west,south,east,north with west < east and south < north")
        if data_bbox:
            clipped = (max(west, data_bbox[0]), max(south, data_bbox[1]),
                       min(east, data_bbox[2]), min(north, data_bbox[3]))
            if not (clipped[0] < clipped[2] and clipped[1] < clipped[3]):
                result.summary = json_safe({
                    "empty": True, "config": asdict(config),
                    "message": "The selected area lies outside the area for which data were loaded "
                               f"({', '.join(f'{v:g}' for v in data_bbox)}; west, south, east, north)."})
                return result
            if clipped != (west, south, east, north):
                notes.append("The selected area extends beyond the loaded data area and was clipped to it.")
            west, south, east, north = clipped
        bbox = (west, south, east, north)
        data = data[data["longitude"].between(west, east) & data["latitude"].between(south, north)]
    if config.start:
        data = data[data["acq_date"] >= (pd.Timestamp(config.start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]
    if config.end:
        data = data[data["acq_date"] <= (pd.Timestamp(config.end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")]

    # 2. quality control and keys -----------------------------------------------------
    clean, qc = quality_filter(data, config.drop_low_confidence, config.vegetation_only)
    keyed = add_keys(clean, config.cell_km) if len(clean) else clean.assign(
        cell=[], half_day=[], slot=[], local_date=[], overpass=[])

    requested = (manifest or {}).get("requested") or {}
    range_start = config.start or requested.get("start") or (
        str(keyed["local_date"].min())[:10] if len(keyed) else None)
    range_end = config.end or requested.get("end") or (
        str(keyed["local_date"].max())[:10] if len(keyed) else None)
    if range_start is None or range_end is None or pd.Timestamp(range_start) > pd.Timestamp(range_end):
        result.summary = json_safe({"empty": True, "message": "No detections in the selected area and period.",
                                    "quality_control": qc, "config": asdict(config)})
        return result
    dates = pd.date_range(range_start, range_end, freq="D").as_unit("ns")
    if len(keyed):
        keyed = keyed[(keyed["local_date"] >= dates[0]) & (keyed["local_date"] <= dates[-1])].reset_index(drop=True)

    # 3. coverage and common units ----------------------------------------------------
    modis = [p for p, info in PLATFORMS.items() if info["sensor"] == "MODIS"]
    if config.modis_off_from and len(keyed):
        off = pd.Timestamp(config.modis_off_from)
        keyed = keyed[~(keyed["platform"].isin(modis) & (keyed["local_date"] >= off))].reset_index(drop=True)
    coverage = platform_coverage(dates, keyed, manifest)
    if config.modis_off_from:
        coverage.loc[coverage.index >= pd.Timestamp(config.modis_off_from), modis] = False
    coverage_basis = ("download manifest" if manifest and manifest.get("sources")
                      else "assumed: between first and last detection in each file")
    cells = build_cell_table(keyed)
    present = [p for p in PLATFORMS if p in set(cells["platform"])]

    # 4. calibration of every other platform onto the reference ---------------------
    reference = REFERENCE_PLATFORM
    # coverage, not detections, decides: a covered period without fire is a valid zero
    reference_ok = bool(coverage[reference].any())
    calibrations: Dict[str, TargetCalibration] = {}
    if reference_ok:
        for target in present:
            if target == reference:
                continue
            pairs = build_pairs(cells, target, reference, coverage)
            calibrations[target] = TargetCalibration(target, reference).fit_validate(pairs)
    else:
        notes.append("Aqua MODIS (the reference platform) has no data in this selection, so no "
                     "harmonised record can be built. Raw per-sensor counts are still shown.")

    # 5. daily tables -------------------------------------------------------------------
    hotspots = _daily_by_platform(cells, dates, "n_pixels", "sum")
    obs_cells = _daily_by_platform(cells, dates, "n_pixels", "size")
    obs_frp = _daily_by_platform(cells, dates, "frp_mw", "sum")
    daily = pd.DataFrame(index=dates)
    for platform in PLATFORMS:
        covered = coverage[platform].values
        for name, table in (("hotspots", hotspots), ("cells", obs_cells), ("frp_mw", obs_frp)):
            column = table[platform].values if platform in table else np.full(len(dates), np.nan)
            if name != "frp_mw":
                column = np.where(np.isnan(column), 0.0, column)
            else:
                # a covered day without detections has zero reported FRP; a day with
                # detections whose FRP is missing keeps a missing FRP
                n_cells = (np.nan_to_num(obs_cells[platform].values) if platform in obs_cells
                           else np.zeros(len(dates)))
                column = np.where(np.isnan(column) & (n_cells == 0), 0.0, column)
            daily[f"{platform}_{name}"] = np.where(covered, column, np.nan)
    for sensor in ("MODIS", "VIIRS"):
        cols = [f"{p}_hotspots" for p, info in PLATFORMS.items() if info["sensor"] == sensor]
        daily[f"{sensor.lower()}_hotspots"] = daily[cols].sum(axis=1, min_count=1)

    derived_cells, derived_frp = {}, {}
    for target, calib in calibrations.items():
        if calib.status != "calibrated":
            continue
        rows = cells[cells["platform"] == target]
        eq = calib.apply(rows)
        tmp = rows[["local_date"]].assign(eq_cells=eq["eq_cells"].values, eq_frp=eq["eq_frp_mw"].values)
        g = tmp.groupby("local_date")
        covered = coverage[target].values
        c = g["eq_cells"].sum().reindex(dates).fillna(0.0).values
        derived_cells[target] = np.where(covered, c, np.nan)
        if calib.frp_method:
            f = g["eq_frp"].sum().reindex(dates).fillna(0.0).values
            derived_frp[target] = np.where(covered, f, np.nan)
        daily[f"{target}_aqua_equivalent_cells"] = derived_cells[target]
        if target in derived_frp:
            daily[f"{target}_aqua_equivalent_frp_mw"] = derived_frp[target]

    def _nanmean(arrays: List[np.ndarray]) -> np.ndarray:
        if not arrays:
            return np.full(len(dates), np.nan)
        stack = np.vstack(arrays)
        count = np.isfinite(stack).sum(axis=0)
        total = np.nansum(stack, axis=0)
        return np.where(count > 0, total / np.maximum(count, 1), np.nan)

    viirs_targets = [t for t in derived_cells if PLATFORMS[t]["sensor"] == "VIIRS"]
    viirs_cells = _nanmean([derived_cells[t] for t in viirs_targets])
    viirs_frp = _nanmean([derived_frp[t] for t in viirs_targets if t in derived_frp])
    terra_cells = derived_cells.get("Terra", np.full(len(dates), np.nan))
    terra_frp = derived_frp.get("Terra", np.full(len(dates), np.nan))
    if reference_ok:
        ref_cov = coverage[reference].values
        ref_cells = daily[f"{reference}_cells"].values
        ref_frp = daily[f"{reference}_frp_mw"].values
    else:
        ref_cov = np.zeros(len(dates), dtype=bool)
        ref_cells = ref_frp = np.full(len(dates), np.nan)
    has_viirs = np.isfinite(viirs_cells)
    has_terra = np.isfinite(terra_cells)
    source = np.where(ref_cov, 1, np.where(has_viirs, 2, np.where(has_terra, 3, 0)))
    daily["harmonized_cells"] = np.select([source == 1, source == 2, source == 3],
                                          [ref_cells, viirs_cells, terra_cells], np.nan)
    daily["harmonized_frp_mw"] = np.select([source == 1, source == 2, source == 3],
                                           [ref_frp, viirs_frp, terra_frp], np.nan)
    daily["source"] = source
    daily.index.name = "local_date"

    # 6. monthly record, uncertainty band, anomalies ---------------------------------------
    monthly = cal.monthly_table(daily)
    period = pd.DatetimeIndex(daily.index).to_period("M")

    def _primary(targets: List[str]) -> Optional[str]:
        best = [(calibrations[t].summary.get("both_active", 0), t) for t in targets]
        return max(best)[1] if best else None

    primary_viirs = _primary(viirs_targets)
    for kind, column in (("count", "harmonized_cells"), ("frp", "harmonized_frp_mw")):
        part = {s: daily[column].where(daily["source"] == s).groupby(period).sum(min_count=1)
                .reindex(monthly.index).fillna(0.0).values for s in (1, 2, 3)}
        lo = part[1].copy()
        hi = part[1].copy()
        for s, target in ((2, primary_viirs), (3, "Terra" if "Terra" in derived_cells else None)):
            used = part[s] > 0
            if not used.any():
                continue
            interval = calibrations[target].interval[kind] if target else None
            l, h = monthly_interval(part[s], interval)
            lo = np.where(used, lo + l, lo)
            hi = np.where(used, hi + h, hi)
        name = "cells" if kind == "count" else "frp_mw_sum"
        has_value = monthly[name].notna().values
        monthly[f"{name}_low"] = np.where(has_value, lo, np.nan)
        monthly[f"{name}_high"] = np.where(has_value, hi, np.nan)
    monthly = anomaly_mod.monthly_anomalies(monthly, "cells")

    # 7. calendar, seasonality, critical periods ----------------------------------------
    years = sorted(set(dates.year))
    clim = cal.climatology_by_doy(daily["harmonized_cells"])
    start_doy = cal.fire_year_start_doy(clim)
    pheno = cal.phenology(daily, start_doy)
    weekly = anomaly_mod.weekly_climatology(daily)

    calendar = {
        "years": years,
        "days_of_year": list(range(1, 367)),
        "modis_hotspots": cal.calendar_matrix(daily["modis_hotspots"], years, 0),
        "viirs_hotspots": cal.calendar_matrix(daily["viirs_hotspots"], years, 0),
        "harmonized_cells": cal.calendar_matrix(daily["harmonized_cells"], years, 2),
        "harmonized_frp_mw": cal.calendar_matrix(daily["harmonized_frp_mw"], years, 1),
        "source": cal.calendar_matrix(daily["source"].where(daily["source"] > 0).astype(float), years, 0),
        "source_labels": SOURCE_LABELS,
    }

    # 8. provenance -----------------------------------------------------------------
    platform_rows = []
    for platform in PLATFORMS:
        rows = keyed[keyed["platform"] == platform] if len(keyed) else keyed
        cov = coverage[platform]
        if len(rows) == 0 and not cov.any():
            continue
        covered_dates = cov.index[cov.values]
        levels = rows["processing"].value_counts().to_dict() if len(rows) else {}
        platform_rows.append({
            "platform": platform, "label": PLATFORM_LABELS[platform],
            "sensor": PLATFORMS[platform]["sensor"], "orbit": PLATFORMS[platform]["orbit"],
            "detections": int(len(rows)),
            "first_detection": str(rows["local_date"].min())[:10] if len(rows) else None,
            "last_detection": str(rows["local_date"].max())[:10] if len(rows) else None,
            "coverage_start": covered_dates[0].strftime("%Y-%m-%d") if len(covered_dates) else None,
            "coverage_end": covered_dates[-1].strftime("%Y-%m-%d") if len(covered_dates) else None,
            "days_covered": int(cov.sum()),
            "days_with_detections": int(rows["local_date"].nunique()) if len(rows) else 0,
            "processing_levels": {str(k): int(v) for k, v in levels.items()},
        })
    levels_all = keyed["processing"].value_counts().to_dict() if len(keyed) else {}
    synthetic = bool((manifest or {}).get("synthetic")) or "SYNTHETIC" in levels_all
    if not synthetic and any(k in levels_all for k in ("NRT", "RT", "URT")):
        notes.append("Some rows are near-real-time (NRT/RT/URT) data. NASA recommends standard-processing "
                     "(SP) data for historical analysis; NRT rows lack the 'type' screening.")
    if "Terra" in calibrations and calibrations["Terra"].status == "calibrated":
        notes.append("Terra observes about three hours earlier in the day than Aqua. Terra-derived values "
                     "are a statistical conversion across the fire diurnal cycle and are the least certain "
                     "part of the record.")
    if synthetic:
        notes.insert(0, "SYNTHETIC DATA. Simulated detections from engine/synthetic.py. "
                        "Nothing shown here describes real fire activity.")

    bbox = list(bbox) if bbox else None

    best = _primary([t for t in viirs_targets]) or (_primary(list(derived_cells)) if derived_cells else None)
    headline = None
    if best:
        cv = calibrations[best].cv_scores["count"]
        headline = {
            "target": best, "target_label": PLATFORM_LABELS[best],
            "held_out_months": cv[calibrations[best].count_method].get("months"),
            "raw_hotspot_bias_pct": cv["raw_hotspots"].get("total_bias_pct"),
            "gridded_only_bias_pct": cv["gridded_cells"].get("total_bias_pct"),
            "harmonised_bias_pct": cv[calibrations[best].count_method].get("total_bias_pct"),
            "harmonised_median_abs_pct_error": cv[calibrations[best].count_method].get("median_abs_pct_error"),
            "method": calibrations[best].count_method,
            "method_label": METHOD_LABELS[calibrations[best].count_method],
            "validation_design": calibrations[best].validation_design,
        }

    monthly_out = monthly.reset_index(names="period")
    monthly_out["period"] = monthly_out["period"].astype(str)

    result.summary = json_safe({
        "empty": False,
        "synthetic": synthetic,
        "dataset": dataset_info or {},
        "config": asdict(config),
        "area": {"bbox_west_south_east_north": bbox, "cell_km": config.cell_km,
                 "active_cells_ever": int(cells["cell"].nunique()) if len(cells) else 0},
        "period": {"start": dates[0], "end": dates[-1], "days": len(dates),
                   "date_convention": "local solar date; day slot 06-18 h, night slot 18-06 h"},
        "platforms": platform_rows,
        "coverage_basis": coverage_basis,
        "quality_control": qc,
        "reference_platform": reference,
        "harmonisation_available": bool(derived_cells) or reference_ok,
        "headline_validation": headline,
        "calibrations": {t: c.report() for t, c in calibrations.items()},
        "calendar": calendar,
        "monthly": monthly_out.to_dict(orient="list"),
        "seasonality": {
            "fire_year_start_doy": start_doy,
            "core_season_80pct": cal.core_season(clim, 0.80),
            "fire_years": pheno,
            "trends": cal.season_trends(pheno),
            "definition": "10 %, 50 % and 90 % accumulation days of harmonised active cells per fire year",
        },
        "critical_periods": {"weekly_climatology": weekly,
                             "critical_weeks": anomaly_mod.critical_weeks(weekly)},
        "units": {
            "hotspots": "number of fire pixels reported by the sensor (not comparable between sensors)",
            "harmonized_cells": f"Aqua-MODIS-equivalent active fire cells per day "
                                f"({config.cell_km:g} km cells x day/night half-days)",
            "harmonized_frp_mw": "sum over active cells of Aqua-MODIS-equivalent fire radiative POWER at "
                                 "overpass time, MW. An instantaneous snapshot, not an energy.",
        },
        "notes": notes,
    })
    result.detections = keyed
    result.cells = cells
    result.daily = daily
    result.monthly = monthly
    result.calibrations = calibrations
    result.coverage = coverage
    return result


# ------------------------------------------------------------------ MODIS switched off

def default_switch_off_date(analysis: Analysis) -> Optional[str]:
    """1 January of the second-to-last year, so the last two calendar years are withheld.
    Needs at least four calendar years, so that three or more remain for calibration."""
    period = analysis.summary.get("period") or {}
    if analysis.summary.get("empty") or not period.get("start"):
        return None
    first, last = pd.Timestamp(period["start"]).year, pd.Timestamp(period["end"]).year
    return f"{last - 1}-01-01" if last - first >= 3 else None


def modis_switch_off_test(detections: pd.DataFrame, manifest: Optional[Dict[str, Any]],
                          full: Analysis, cutoff: Optional[str] = None) -> Dict[str, Any]:
    """
    What happens to the record when MODIS ends? Both MODIS instruments are removed from
    `cutoff` on, every calibration is refitted on the earlier years only, and the record
    is continued from VIIRS alone. The continuation is then compared with what Aqua MODIS
    really observed after `cutoff`, which the scenario never saw.
    Months are compared only where every day has both the real Aqua value and a
    continued value, so a gap in either can never look like agreement.
    """
    cutoff = cutoff or default_switch_off_date(full)
    if cutoff is None:
        return json_safe({"available": False,
                          "reason": "The selection needs at least four calendar years: the last two are "
                                    "withheld and the rest are used for calibration."})
    scenario = run_analysis(detections, manifest, replace(full.config, modis_off_from=cutoff))
    if scenario.summary.get("empty") or "harmonized_cells" not in scenario.daily:
        return json_safe({"available": False, "cutoff": cutoff, "reason": "No data in the selection."})
    after = full.daily.index >= pd.Timestamp(cutoff)
    truth, cont = full.daily.loc[after], scenario.daily.loc[after]
    viirs = [p for p, info in PLATFORMS.items() if info["sensor"] == "VIIRS" and f"{p}_hotspots" in truth
             and truth[f"{p}_hotspots"].notna().any()]
    usable = (truth["Aqua_cells"].notna() & cont["harmonized_cells"].notna()
              & (cont["source"] == 2)).values
    if not usable.any():
        return json_safe({"available": False, "cutoff": cutoff,
                          "reason": "After the cut-off no day has both real Aqua data and a VIIRS-derived value."})
    month = pd.DatetimeIndex(truth.index).to_period("M")
    complete = pd.Series(usable, index=month).groupby(level=0).all()
    months = complete.index[complete.values]
    keep = np.isin(month, months)

    def monthly(frame: pd.DataFrame, column: str) -> np.ndarray:
        return frame.loc[keep, column].groupby(month[keep]).sum(min_count=1).reindex(months).values

    obs_cells, cont_cells = monthly(truth, "Aqua_cells"), monthly(cont, "harmonized_cells")
    obs_frp, cont_frp = monthly(truth, "Aqua_frp_mw"), monthly(cont, "harmonized_frp_mw")
    sm = scenario.monthly.reindex(months)
    low, high = sm["cells_low"].values, sm["cells_high"].values
    raw_viirs = (truth.loc[keep, [f"{p}_hotspots" for p in viirs]].mean(axis=1)
                 .groupby(month[keep]).sum().reindex(months).values) if viirs else None
    raw_aqua = monthly(truth, "Aqua_hotspots")
    count = _score(cont_cells, obs_cells, "count")
    frp_ok = np.isfinite(obs_frp).all() and np.isfinite(cont_frp).all()
    inside = (obs_cells >= low) & (obs_cells <= high)
    calibs = {t: {"count_method": c.count_method, "frp_method": c.frp_method,
                  "trained_on_months": c.summary.get("overlap_months")}
              for t, c in scenario.calibrations.items() if c.status == "calibrated"}
    first = pd.Timestamp(full.summary["period"]["start"]).strftime("%Y-%m-%d")
    return json_safe({
        "available": True,
        "cutoff": cutoff,
        "calibration_period": [first, (pd.Timestamp(cutoff) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")],
        "withheld_period": [cutoff, pd.Timestamp(full.summary["period"]["end"]).strftime("%Y-%m-%d")],
        "months": [str(m) for m in months],
        "months_excluded": int((~complete.values).sum()),
        "aqua_observed_cells": np.round(obs_cells, 1),
        "continued_cells": np.round(cont_cells, 1),
        "continued_cells_low": np.round(low, 1),
        "continued_cells_high": np.round(high, 1),
        "aqua_observed_frp_mw": np.round(obs_frp, 1),
        "continued_frp_mw": np.round(cont_frp, 1),
        "scores": {"count": count, "frp": _score(cont_frp, obs_frp, "frp") if frp_ok else {"available": False}},
        "raw_viirs_hotspot_bias_pct": (round(float(100.0 * (raw_viirs.sum() - raw_aqua.sum()) / raw_aqua.sum()), 1)
                                       if raw_viirs is not None and raw_aqua.sum() > 0 else None),
        "inside_90pct_band_pct": round(float(100.0 * inside.mean()), 1) if np.isfinite(low).all() else None,
        "days_viirs_derived": int((scenario.daily.loc[after, "source"] == 2).sum()),
        "days_after_cutoff": int(after.sum()),
        "calibrations": calibs,
        "viirs_platforms": viirs,
        "calendar": {k: scenario.summary["calendar"][k] for k in ("years", "source", "harmonized_cells", "source_labels")},
    })


# ------------------------------------------------------------- calibration transfer

def calibration_transfer_test(source: Analysis, target: Analysis, platform: str) -> Dict[str, Any]:
    """
    Apply the calibration fitted in one region (`source`, all of its years) unchanged to
    another region (`target`) and compare the result with what Aqua MODIS really observed
    there. The target region's data are never used for fitting. Only days on which both
    the platform and Aqua are covered in the target region are used, and a month counts
    only if every one of its days qualifies.
    """
    calib = source.calibrations.get(platform)
    if calib is None or calib.status != "calibrated":
        return json_safe({"available": False, "reason": f"{platform} is not calibrated in the source region."})
    if target.summary.get("empty") or platform not in target.coverage or "Aqua" not in target.coverage:
        return json_safe({"available": False, "reason": f"No {platform} or Aqua data in the target region."})
    dates = target.daily.index
    usable = (target.coverage[platform].reindex(dates).fillna(False).values
              & target.coverage["Aqua"].reindex(dates).fillna(False).values)
    rows = target.cells[target.cells["platform"] == platform]
    eq = calib.apply(rows)
    per_day = (rows[["local_date"]].assign(c=eq["eq_cells"].values, f=eq["eq_frp_mw"].values)
               .groupby("local_date")[["c", "f"]].sum().reindex(dates).fillna(0.0))
    month = pd.DatetimeIndex(dates).to_period("M")
    complete = pd.Series(usable, index=month).groupby(level=0).all()
    months = complete.index[complete.values]
    keep = np.isin(month, months) & usable

    def monthly(values: np.ndarray) -> np.ndarray:
        return pd.Series(values[keep]).groupby(month[keep]).sum().reindex(months).values

    obs_c, obs_f = monthly(target.daily["Aqua_cells"].values), monthly(target.daily["Aqua_frp_mw"].values)
    pred_c, pred_f = monthly(per_day["c"].values), monthly(per_day["f"].values)
    raw_t, raw_a = monthly(target.daily[f"{platform}_hotspots"].values), monthly(target.daily["Aqua_hotspots"].values)
    own = target.calibrations.get(platform)
    own_cv = (own.cv_scores["count"][own.count_method] if own is not None and own.status == "calibrated" else None)
    own_frp = (own.cv_scores["frp"][own.frp_method] if own is not None and own.status == "calibrated"
               and own.frp_method else None)
    return json_safe({
        "available": True,
        "platform": platform,
        "source_method": {"count": calib.count_method, "frp": calib.frp_method},
        "months": len(months),
        "raw_hotspot_bias_pct": round(float(100.0 * (raw_t.sum() - raw_a.sum()) / raw_a.sum()), 1) if raw_a.sum() else None,
        "count": _score(pred_c, obs_c, "count"),
        "frp": _score(pred_f, obs_f, "frp") if calib.frp_method else {"available": False},
        "own_region_held_out": {
            "count": {k: own_cv.get(k) for k in ("total_bias_pct", "median_abs_pct_error")} if own_cv else None,
            "frp": {k: own_frp.get(k) for k in ("total_bias_pct", "median_abs_pct_error")} if own_frp else None,
        },
    })


# ----------------------------------------------------------------------------- exports

def export_frame(analysis: Analysis, kind: str) -> pd.DataFrame:
    """Tables behind the CSV downloads. Every table carries its provenance columns."""
    if kind == "detections":
        cols = ["latitude", "longitude", "sensor", "platform", "acq_datetime", "acq_date", "local_date",
                "slot", "frp", "confidence_raw", "confidence_class", "daynight", "scan_km", "track_km",
                "type", "version", "processing", "source", "cell"]
        frame = analysis.detections
        return frame[[c for c in cols if c in frame.columns]].rename(
            columns={"frp": "frp_mw", "acq_datetime": "acq_datetime_utc", "source": "firms_source"})
    if kind == "daily":
        frame = analysis.daily.reset_index()
        frame["source_label"] = frame["source"].map(SOURCE_LABELS)
        return frame
    if kind == "monthly":
        frame = analysis.monthly.reset_index(names="period")
        frame["period"] = frame["period"].astype(str)
        return frame
    if kind == "cells":
        return analysis.cells
    raise ValueError("kind must be one of: detections, daily, monthly, cells")
