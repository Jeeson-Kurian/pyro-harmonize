"""Geodesic distances, equal-area cells, local half-days, overpass clustering."""

import numpy as np
import pandas as pd
import pytest

from engine.data_loader import standardize_firms
from engine.gridding import add_keys, build_cell_table, cell_index, haversine_km
from engine.spatial_cluster import OverpassClusterer


def frame(rows):
    cols = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "frp"]
    raw = pd.DataFrame(rows, columns=cols)
    raw["instrument"] = np.where(raw["satellite"].isin(["A", "T"]), "MODIS", "VIIRS")
    raw["confidence"] = np.where(raw["instrument"] == "MODIS", "80", "n")
    raw["scan"], raw["track"], raw["version"] = 1.0, 1.0, "TEST"
    parts = [standardize_firms(g, sensor=s) for s, g in raw.groupby("instrument")]
    return pd.concat(parts, ignore_index=True)


def test_haversine_known_distances():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(111.195, abs=0.01)
    assert haversine_km(60, 0, 60, 1) == pytest.approx(55.60, abs=0.01)       # 111.195 km x cos(60 deg)


def test_cells_have_the_same_ground_size_at_any_latitude():
    for lat in (0.0, 40.0, 65.0):
        ids, clat, clon = cell_index(np.array([lat, lat]), np.array([10.0, 10.0]), 10.0)
        # walk east until the cell id changes: the cell must be about 10 km wide
        lons = 10.0 + np.arange(0, 0.6, 0.0005)
        cid, _, _ = cell_index(np.full(len(lons), lat), lons, 10.0)
        change = np.flatnonzero(np.diff(cid) != 0)
        width = haversine_km(lat, lons[change[0] + 1], lat, lons[change[1] + 1])
        assert width == pytest.approx(10.0, rel=0.03)


def test_degree_based_clustering_bug_is_fixed():
    # 1.5 km apart east-west at 60 N is 0.027 degrees of longitude. The old code compared
    # degrees with eps = 2 km / 111 = 0.018 degrees and split these two detections.
    lon2 = 1.5 / (111.195 * np.cos(np.radians(60.0)))
    labels = OverpassClusterer(eps_km=2.0).label(np.array([60.0, 60.0]), np.array([0.0, lon2]))
    assert labels[0] == labels[1]
    # 2.5 km apart must stay separate at any latitude
    lon3 = 2.5 / (111.195 * np.cos(np.radians(60.0)))
    labels = OverpassClusterer(eps_km=2.0).label(np.array([60.0, 60.0]), np.array([0.0, lon3]))
    assert labels[0] != labels[1]


def test_overpass_straddling_utc_midnight_stays_in_one_half_day():
    # Night overpasses near 20 W happen around 00:00 UTC. Bucketing by UTC date would split them.
    df = frame([[14.0, -17.0, "2021-03-01", "2350", "A", 20.0],
                [14.0, -17.0, "2021-03-02", "0020", "N", 5.0]])
    keyed = add_keys(df)
    assert keyed["half_day"].nunique() == 1
    assert set(keyed["slot"]) == {"night"}
    assert keyed["local_date"].nunique() == 1


def test_day_and_night_slots_use_local_solar_time():
    df = frame([[38.0, -122.0, "2020-08-19", "2130", "A", 30.0],      # 13:22 local solar
                [38.0, -122.0, "2020-08-19", "0930", "A", 10.0]])     # 01:22 local solar
    keyed = add_keys(df).sort_values("acq_datetime")
    assert list(keyed["slot"]) == ["night", "day"]
    assert keyed["local_date"].astype(str).str[:10].tolist() == ["2020-08-19", "2020-08-19"]


def test_separate_overpasses_are_never_clustered_together():
    # same place, same platform, 100 minutes apart: two overpasses, two clusters
    df = frame([[38.0, -122.0, "2020-08-19", "2000", "N", 5.0],
                [38.0, -122.0, "2020-08-19", "2140", "N", 5.0],
                [38.001, -122.001, "2020-08-19", "2140", "N", 7.0]])
    clusters = OverpassClusterer(2.0).cluster(add_keys(df))
    assert len(clusters) == 2
    assert sorted(clusters["n_pixels"]) == [1, 2]


def test_cell_table_reports_power_not_a_sum_over_overpasses():
    # two overpasses in one half-day (possible at high latitude): FRP is the mean per overpass
    df = frame([[70.0, 20.0, "2020-07-01", "1000", "N", 10.0],
                [70.0, 20.0, "2020-07-01", "1140", "N", 30.0]])
    cells = build_cell_table(add_keys(df))
    assert len(cells) == 1
    assert cells["n_overpasses"].iloc[0] == 2
    assert cells["frp_mw"].iloc[0] == pytest.approx(20.0)
