"""
Common observation units shared by every sensor.

Hot-spot counts are not comparable between MODIS (1 km pixels that grow to about
2 x 4.8 km at the swath edge) and VIIRS (375 m pixels): one fire front produces
one MODIS pixel and many VIIRS pixels. Before any comparison, both sensors are
reduced to the same unit:

    active fire cell  =  one grid cell (about 10 x 10 km, equal-area)
                         x one local half-day (day or night)
                         x one platform

A cell is "active" when the platform reported at least one detection in it.
The count of active cells is far less sensitive to pixel size than the count of
hot spots, and the same cell definition applies to every sensor and every year.

Time is bucketed by LOCAL SOLAR half-day, not by UTC date, so that one satellite
overpass never straddles a bucket boundary:
    day   slot = local solar time 06:00-18:00
    night slot = local solar time 18:00-06:00 (labelled with the date it ends on)
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from .schema import EARTH_RADIUS_KM, KM_PER_DEG_LAT

HALF_DAY_SECONDS = 43200
OVERPASS_GAP_MINUTES = 20  # detections further apart than this are separate overpasses


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (inputs in degrees, scalars or arrays)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def cell_index(lat, lon, cell_km: float = 10.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Equal-area-style grid. Latitude bands are cell_km tall; within a band the
    longitude step is widened by 1/cos(latitude) so every cell is about
    cell_km x cell_km on the ground at any latitude.
    Returns (cell_id, centre_lat, centre_lon).
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    dlat = cell_km / KM_PER_DEG_LAT
    i = np.floor((lat + 90.0) / dlat).astype(np.int64)
    centre_lat = (i + 0.5) * dlat - 90.0
    dlon = dlat / np.maximum(np.cos(np.radians(centre_lat)), 0.01)
    j = np.floor((lon + 180.0) / dlon).astype(np.int64)
    centre_lon = (j + 0.5) * dlon - 180.0
    cell_id = i * 10_000_000 + j
    return cell_id, centre_lat, centre_lon


def add_keys(df: pd.DataFrame, cell_km: float = 10.0) -> pd.DataFrame:
    """Add grid cell, local-solar half-day, local date and overpass id to detections."""
    out = df.copy()
    cell_id, clat, clon = cell_index(out["latitude"].values, out["longitude"].values, cell_km)
    out["cell"] = cell_id
    out["cell_lat"] = clat
    out["cell_lon"] = clon

    utc_seconds = (out["acq_datetime"].values.astype("datetime64[s]").astype(np.int64))
    local_seconds = utc_seconds + np.round(out["longitude"].values * 240.0).astype(np.int64)
    half_day = np.floor_divide(local_seconds + HALF_DAY_SECONDS // 2, HALF_DAY_SECONDS)
    out["half_day"] = half_day
    out["slot"] = np.where(half_day % 2 == 0, "night", "day")
    local_day = np.floor_divide(half_day, 2)
    out["local_date"] = (np.datetime64("1970-01-01") + local_day.astype("timedelta64[D]")).astype("datetime64[ns]")
    out["local_hour"] = (local_seconds % 86400) / 3600.0

    # Overpass id: per platform, a new overpass starts after a gap in acquisition time.
    out = out.sort_values(["platform", "acq_datetime"], kind="stable")
    gap = out.groupby("platform")["acq_datetime"].diff() > pd.Timedelta(minutes=OVERPASS_GAP_MINUTES)
    out["overpass"] = gap.groupby(out["platform"]).cumsum().astype(np.int64)
    return out.reset_index(drop=True)


def build_cell_table(keyed: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (platform, cell, half-day):
      n_pixels            number of hot-spot pixels
      n_overpasses        how many separate overpasses contributed (>1 at high latitude)
      frp_mw              summed pixel FRP divided by n_overpasses, i.e. the mean
                          instantaneous radiative POWER (MW) of the cell at overpass
                          time. It is not an energy.
      scan_km             mean along-scan pixel size (proxy for view angle)
    """
    if keyed.empty:
        return pd.DataFrame(columns=["platform", "sensor", "cell", "half_day", "slot",
                                     "local_date", "cell_lat", "cell_lon", "n_pixels",
                                     "n_overpasses", "frp_mw", "scan_km", "time_utc"])
    grouped = keyed.groupby(["platform", "cell", "half_day"], sort=False)
    table = grouped.agg(
        sensor=("sensor", "first"),
        slot=("slot", "first"),
        local_date=("local_date", "first"),
        cell_lat=("cell_lat", "first"),
        cell_lon=("cell_lon", "first"),
        n_pixels=("frp", "size"),
        n_frp=("frp", "count"),
        frp_sum=("frp", "sum"),
        n_overpasses=("overpass", "nunique"),
        scan_km=("scan_km", "mean"),
        time_utc=("acq_datetime", "mean"),
    ).reset_index()
    table["frp_mw"] = np.where(table["n_frp"] > 0, table["frp_sum"] / table["n_overpasses"], np.nan)
    return table.drop(columns=["n_frp", "frp_sum"])
