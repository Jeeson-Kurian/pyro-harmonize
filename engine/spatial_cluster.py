"""
Geodesic hot-spot clustering (for the map and for sensitivity diagnostics).

A "hot-spot cluster" is a group of detections from ONE platform in ONE overpass
that are chained together by great-circle distances of at most eps_km. It is a
description of what one sensor saw at one moment. It is not a confirmed fire:
one fire can appear as several clusters and several nearby fires can merge.

With min_samples=1, DBSCAN is exactly single-linkage grouping at distance eps:
every detection belongs to a cluster and an isolated detection is its own
cluster of size 1. That is intended and is why these are called clusters of
detections rather than fire events.

Distances use the haversine metric on a ball tree, so eps_km means the same
ground distance at every latitude.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from .schema import EARTH_RADIUS_KM

CLUSTER_COLUMNS = ["cluster_id", "platform", "sensor", "overpass", "time_utc", "local_date",
                   "slot", "centroid_lat", "centroid_lon", "n_pixels", "frp_sum_mw",
                   "frp_max_mw", "mean_scan_km", "processing"]


class OverpassClusterer:
    def __init__(self, eps_km: float = 2.0, min_samples: int = 1):
        if eps_km <= 0:
            raise ValueError("eps_km must be positive")
        self.eps_km = float(eps_km)
        self.eps_rad = self.eps_km / EARTH_RADIUS_KM
        self.min_samples = int(min_samples)

    def label(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Cluster labels for one set of simultaneous detections (-1 = noise if min_samples>1)."""
        if len(lat) == 0:
            return np.array([], dtype=int)
        if len(lat) == 1:
            return np.array([0])
        coords = np.radians(np.column_stack([lat, lon]))
        model = DBSCAN(eps=self.eps_rad, min_samples=self.min_samples,
                       metric="haversine", algorithm="ball_tree")
        return model.fit_predict(coords)

    def cluster(self, keyed: pd.DataFrame) -> pd.DataFrame:
        """
        keyed: detections with the columns added by engine.gridding.add_keys.
        Returns one row per hot-spot cluster.
        """
        if keyed.empty:
            return pd.DataFrame(columns=CLUSTER_COLUMNS)
        # label every overpass separately, then aggregate once
        labels = np.full(len(keyed), -1, dtype=np.int64)
        offset = 0
        lat = keyed["latitude"].values
        lon = keyed["longitude"].values
        for idx in keyed.groupby(["platform", "overpass"], sort=False).indices.values():
            local = self.label(lat[idx], lon[idx])
            valid = local >= 0
            labels[idx[valid]] = local[valid] + offset
            offset += int(local.max()) + 1 if valid.any() else 0
        g = keyed.assign(cluster_id=labels)
        g = g[g["cluster_id"] >= 0]
        if g.empty:
            return pd.DataFrame(columns=CLUSTER_COLUMNS)
        out = g.groupby("cluster_id").agg(
            platform=("platform", "first"),
            sensor=("sensor", "first"),
            overpass=("overpass", "first"),
            time_utc=("acq_datetime", "mean"),
            local_date=("local_date", "first"),
            slot=("slot", "first"),
            centroid_lat=("latitude", "mean"),
            centroid_lon=("longitude", "mean"),
            n_pixels=("frp", "size"),
            frp_sum_mw=("frp", lambda v: v.sum(min_count=1)),
            frp_max_mw=("frp", "max"),
            mean_scan_km=("scan_km", "mean"),
            processing=("processing", "first"),
        ).reset_index()
        return out[CLUSTER_COLUMNS]


def radius_sensitivity(keyed: pd.DataFrame,
                       radii_km: Sequence[float] = (0.5, 1.0, 2.0, 5.0)) -> List[Dict]:
    """
    How the number of clusters per sensor depends on the clustering radius.
    If the answer changes a lot with eps, cluster counts are not a stable metric
    and should not be compared across sensors. Reported, not hidden.
    """
    rows: List[Dict] = []
    for eps in radii_km:
        clusters = OverpassClusterer(eps_km=eps).cluster(keyed)
        for sensor in sorted(keyed["sensor"].unique()):
            n_det = int((keyed["sensor"] == sensor).sum())
            n_clu = int((clusters["sensor"] == sensor).sum())
            rows.append({"eps_km": float(eps), "sensor": sensor, "detections": n_det,
                         "clusters": n_clu,
                         "pixels_per_cluster": round(n_det / n_clu, 2) if n_clu else None})
    return rows
