"""
End-to-End Pipeline Unit Tests for PyroHarmonize
Validates data ingestion, DBSCAN spatiotemporal clustering, Ridge calibration,
and Burning Activity Calendar generation.
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from engine.data_loader import generate_benchmark_dataset, STANDARDIZED_COLUMNS
from engine.spatial_cluster import SpatiotemporalClusterer
from engine.harmonizer import FireSensorHarmonizer
from engine.calendar_generator import BurningCalendarGenerator


class TestPyroHarmonizePipeline(unittest.TestCase):

    def test_benchmark_data_generation(self):
        df = generate_benchmark_dataset(start_year=2010, end_year=2015, region="Mediterranean", seed=42)
        self.assertFalse(df.empty)
        self.assertIn("sensor", df.columns)
        self.assertTrue(set(df["sensor"].unique()).issubset({"MODIS", "VIIRS"}))
        self.assertIn("frp", df.columns)
        self.assertTrue((df["frp"] > 0).all())
        # Check that VIIRS exists for >= 2012
        viirs_years = df[df["sensor"] == "VIIRS"]["year"].unique()
        self.assertTrue(all(yr >= 2012 for yr in viirs_years))

    def test_spatiotemporal_clustering(self):
        df = generate_benchmark_dataset(start_year=2013, end_year=2014, region="Mediterranean", seed=42)
        clusterer = SpatiotemporalClusterer(eps_km=2.0)
        df_clustered, complexes_df = clusterer.cluster_detections(df)

        self.assertIn("cluster_id", df_clustered.columns)
        self.assertFalse(complexes_df.empty)
        self.assertIn("centroid_lat", complexes_df.columns)
        self.assertIn("centroid_lon", complexes_df.columns)
        self.assertIn("sensor_tag", complexes_df.columns)
        tags = set(complexes_df["sensor_tag"].unique())
        self.assertTrue("COINCIDENT" in tags or "MODIS" in tags or "VIIRS" in tags)

    def test_harmonization_and_calibration(self):
        df = generate_benchmark_dataset(start_year=2011, end_year=2014, region="Mediterranean", seed=42)
        clusterer = SpatiotemporalClusterer(eps_km=2.0)
        df_clustered, complexes_df = clusterer.cluster_detections(df)

        harmonizer = FireSensorHarmonizer()
        metrics = harmonizer.fit_calibration(complexes_df)
        self.assertTrue(harmonizer.is_fitted)
        self.assertIn("point_inflation_ratio", metrics)

        daily_df, harm_complexes = harmonizer.harmonize_dataset(df_clustered, complexes_df)
        self.assertFalse(daily_df.empty)
        self.assertIn("raw_hotspot_count", daily_df.columns)
        self.assertIn("harmonized_fire_events", daily_df.columns)
        self.assertTrue((daily_df["harmonized_fire_events"] >= 0).all())

    def test_calendar_matrix_generation(self):
        df = generate_benchmark_dataset(start_year=2000, end_year=2024, region="Mediterranean", seed=42)
        clusterer = SpatiotemporalClusterer(eps_km=2.0)
        df_clustered, complexes_df = clusterer.cluster_detections(df)

        harmonizer = FireSensorHarmonizer()
        daily_df, _ = harmonizer.harmonize_dataset(df_clustered, complexes_df)

        calendar_gen = BurningCalendarGenerator(start_year=2000, end_year=2024)
        cal_data = calendar_gen.build_calendar_matrices(daily_df)

        self.assertEqual(len(cal_data["years"]), 25)
        self.assertEqual(len(cal_data["days_of_year"]), 365)
        raw_mat = np.array(cal_data["raw_matrix"])
        harm_mat = np.array(cal_data["harmonized_matrix"])

        self.assertEqual(raw_mat.shape, (25, 365))
        self.assertEqual(harm_mat.shape, (25, 365))
        self.assertIn("climate_insights", cal_data)
        self.assertIn("phenology", cal_data)


if __name__ == "__main__":
    unittest.main()

