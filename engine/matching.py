"""
Observation coverage and cross-sensor matching.

Two questions are answered here.

1. When was each platform actually delivering data for the area?  (coverage)
   A day with zero detections inside a platform's coverage means "observed, no
   fire reported" (cloud cover is unknown). A day outside coverage means
   "no data" and must never be shown or counted as zero.

2. Which observations of two platforms refer to the same place and time? (pairs)
   Two platforms are compared on identical units: the same grid cell in the
   same local half-day. For both-active cells the actual acquisition-time
   difference is kept, so near-simultaneous subsets can be analysed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .schema import FIRMS_SOURCES, PLATFORMS


def _mark(mask: np.ndarray, dates: np.ndarray, start: str, end: str, value: bool) -> None:
    lo = np.datetime64(start, "D")
    hi = np.datetime64(end, "D")
    mask[(dates >= lo) & (dates <= hi)] = value


def platform_coverage(dates: pd.DatetimeIndex, detections: pd.DataFrame,
                      manifest: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Boolean table (index = local date, columns = platform): was the platform
    delivering data on that date?

    Order of evidence:
      1. the platform's FIRMS availability window (engine.schema.PLATFORMS);
      2. the download manifest: date intervals that were requested AND returned
         successfully for a source that contains the platform;
      3. without a manifest: the span between the first and last detection in the
         file(s) of that source (a weaker assumption, flagged in the provenance);
      4. known gaps listed under manifest["platform_gaps"] are removed.
    One day is trimmed from every edge because local dates and the UTC dates of
    the download window can differ by up to a day.
    """
    day = dates.values.astype("datetime64[D]")
    present = set(detections["platform"].unique()) if len(detections) else set()
    out = {}
    for platform, info in PLATFORMS.items():
        mask = np.zeros(len(day), dtype=bool)
        sources = [s for s, meta in FIRMS_SOURCES.items() if platform in meta["platforms"]]
        intervals: List[List[str]] = []
        from_manifest = False
        if manifest and manifest.get("sources"):
            for src in sources:
                entry = manifest["sources"].get(src)
                if entry and entry.get("coverage"):
                    intervals.extend(entry["coverage"])
                    from_manifest = True
        if not from_manifest and platform in present:
            rows = detections[detections["source"].isin(sources)]
            if rows.empty:
                rows = detections[detections["platform"] == platform]
            intervals.append([rows["acq_date"].min(), rows["acq_date"].max()])
        for start, end in intervals:
            _mark(mask, day, start, end, True)
        # Trim one day inside every coverage edge. Beyond the ends of the analysed
        # date range the state is unknown, so the range ends are not treated as edges.
        padded = np.concatenate([mask[:1], mask, mask[-1:]])
        mask = padded[:-2] & padded[1:-1] & padded[2:]
        mask &= day >= np.datetime64(info["firms_start"], "D")
        if info["firms_end"]:
            mask &= day <= np.datetime64(info["firms_end"], "D")
        if manifest:
            for start, end in (manifest.get("platform_gaps") or {}).get(platform, []):
                _mark(mask, day, start, end, False)
        if platform not in present and not from_manifest:
            mask[:] = False
        out[platform] = mask
    return pd.DataFrame(out, index=dates)


def build_pairs(cells: pd.DataFrame, target: str, reference: str,
                coverage: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (cell, half-day) in which the target and/or the reference platform
    was active, restricted to dates when BOTH platforms were delivering data.
    """
    both_covered = coverage.index[(coverage[target] & coverage[reference]).values]
    columns = ["cell", "half_day", "slot", "local_date", "n_pixels", "frp_mw", "scan_km", "time_utc"]
    t = cells.loc[cells["platform"] == target, columns]
    r = cells.loc[cells["platform"] == reference, columns]
    merged = t.merge(r, on=["cell", "half_day"], how="outer", suffixes=("_t", "_r"))
    merged["slot"] = merged["slot_t"].fillna(merged["slot_r"])
    merged["local_date"] = merged["local_date_t"].fillna(merged["local_date_r"])
    merged = merged[merged["local_date"].isin(both_covered)]
    pairs = pd.DataFrame({
        "cell": merged["cell"].values,
        "half_day": merged["half_day"].values,
        "slot": merged["slot"].values,
        "local_date": merged["local_date"].values,
        "t_active": merged["n_pixels_t"].notna().values,
        "r_active": merged["n_pixels_r"].notna().values,
        "t_npix": merged["n_pixels_t"].fillna(0).astype(int).values,
        "r_npix": merged["n_pixels_r"].fillna(0).astype(int).values,
        "t_frp": merged["frp_mw_t"].values,
        "r_frp": merged["frp_mw_r"].values,
        "t_scan": merged["scan_km_t"].values,
        "r_scan": merged["scan_km_r"].values,
    })
    dt = (merged["time_utc_t"] - merged["time_utc_r"]).dt.total_seconds().abs() / 60.0
    pairs["dt_min"] = dt.values
    date = pd.DatetimeIndex(pairs["local_date"])
    pairs["year"] = date.year
    pairs["month"] = date.to_period("M").astype(str)
    return pairs.reset_index(drop=True)


def pair_summary(pairs: pd.DataFrame) -> Dict[str, Any]:
    """Counts and timing of matched observations, reported next to every calibration."""
    both = pairs["t_active"] & pairs["r_active"]
    dt = pairs.loc[both, "dt_min"].dropna()
    return {
        "cell_halfdays_total": int(len(pairs)),
        "both_active": int(both.sum()),
        "target_only": int((pairs["t_active"] & ~pairs["r_active"]).sum()),
        "reference_only": int((~pairs["t_active"] & pairs["r_active"]).sum()),
        "overlap_months": int(pairs["month"].nunique()),
        "overlap_years": int(pairs["year"].nunique()),
        "median_time_difference_min": round(float(dt.median()), 1) if len(dt) else None,
        "share_within_15_min": round(float((dt <= 15).mean()), 3) if len(dt) else None,
        "share_within_60_min": round(float((dt <= 60).mean()), 3) if len(dt) else None,
    }
