"""
Spatiotemporal Fire Event Clustering Module
Reconciles sub-pixel detection disparities by aggregating discrete satellite detections
into coherent, physical Fire Complexes using DBSCAN / spatial neighborhood trees.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from sklearn.cluster import DBSCAN


class SpatiotemporalClusterer:
    """
    Groups discrete satellite active fire detections occurring on the same acquisition date
    into coherent physical fire complexes. This eliminates the 3x-4x point artifact caused
    by VIIRS's higher spatial resolution (375m) breaking a single fire into multiple detections.
    """
    def __init__(self, eps_km: float = 2.0, min_samples: int = 1):
        """
        :param eps_km: Spatial neighborhood threshold in kilometers (default ~2.0 km).
                       Converted to approximate degrees (~0.018 deg).
        :param min_samples: Minimum points to form a cluster (1 allows single isolated hotspots).
        """
        self.eps_km = eps_km
        # 1 degree latitude ~ 111 km
        self.eps_deg = eps_km / 111.0
        self.min_samples = min_samples

    def cluster_detections(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Takes raw standardized detections and returns:
        1. Original detections with assigned `cluster_id`.
        2. Aggregated `fire_complexes` DataFrame (one row per physical fire event).
        """
        if df.empty:
            return df.copy(), pd.DataFrame()

        df_out = df.copy()
        df_out["cluster_id"] = -1

        complex_records = []
        cluster_offset = 0

        # Cluster date by date to preserve temporal separation
        for date_val, day_group in df_out.groupby("acq_date"):
            coords = day_group[["latitude", "longitude"]].values
            
            if len(coords) == 1:
                labels = np.array([0])
            else:
                db = DBSCAN(eps=self.eps_deg, min_samples=self.min_samples, metric="euclidean")
                labels = db.fit_predict(coords)
                # Unassigned noise (-1) gets unique individual IDs
                noise_mask = (labels == -1)
                if np.any(noise_mask):
                    max_label = labels.max() if len(labels) > 0 and labels.max() >= 0 else 0
                    labels[noise_mask] = np.arange(max_label + 1, max_label + 1 + np.sum(noise_mask))

            global_labels = labels + cluster_offset
            df_out.loc[day_group.index, "cluster_id"] = global_labels
            cluster_offset += (labels.max() + 1 if len(labels) > 0 else 1)

            # Build aggregated complex summary for each cluster on this date
            day_group = day_group.copy()
            day_group["cluster_id"] = global_labels

            for cid, c_data in day_group.groupby("cluster_id"):
                sensors = set(c_data["sensor"].unique())
                sensor_tag = "COINCIDENT" if len(sensors) > 1 else list(sensors)[0]
                
                modis_pts = c_data[c_data["sensor"] == "MODIS"]
                viirs_pts = c_data[c_data["sensor"] == "VIIRS"]
                
                complex_records.append({
                    "cluster_id": cid,
                    "acq_date": date_val,
                    "year": int(c_data["year"].iloc[0]),
                    "doy": int(c_data["doy"].iloc[0]),
                    "centroid_lat": float(c_data["latitude"].mean()),
                    "centroid_lon": float(c_data["longitude"].mean()),
                    "total_frp": float(c_data["frp"].sum()),
                    "max_frp": float(c_data["frp"].max()),
                    "n_detections": len(c_data),
                    "n_modis": len(modis_pts),
                    "n_viirs": len(viirs_pts),
                    "modis_frp": float(modis_pts["frp"].sum()) if not modis_pts.empty else 0.0,
                    "viirs_frp": float(viirs_pts["frp"].sum()) if not viirs_pts.empty else 0.0,
                    "sensor_tag": sensor_tag
                })

        complexes_df = pd.DataFrame(complex_records)
        return df_out, complexes_df
