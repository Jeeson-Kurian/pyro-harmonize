"""Ingestion of the real FIRMS CSV layouts, and quality control."""

import io

import numpy as np
import pandas as pd
import pytest

from engine.data_loader import load_firms_csv, quality_filter, source_from_filename, standardize_firms

# Layout of the FIRMS area API for MODIS_SP (standard processing has a 'type' column).
MODIS_SP = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type
38.5412,-121.7401,325.6,1.1,1.0,2020-08-19,2123,A,MODIS,87,6.1,298.3,45.2,D,0
38.5412,-121.7401,325.6,1.1,1.0,2020-08-19,2123,A,MODIS,87,6.1,298.3,45.2,D,0
38.6001,-121.8002,312.4,2.9,1.6,2020-08-19,1845,T,MODIS,25,6.1,295.1,12.9,D,0
19.4101,-155.2801,340.0,1.0,1.0,2020-08-19,0935,T,MODIS,100,6.1,290.0,120.0,N,1
38.7000,-121.9000,318.0,1.3,1.1,2020-08-20,130,A,MODIS,55,6.1,292.0,-1.0,N,0
"""

# Layout of the FIRMS area API for VIIRS near-real-time data (letters for confidence, no 'type').
VIIRS_NRT = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
38.54100,-121.74100,338.2,0.41,0.37,2026-10-01,2118,N20,VIIRS,n,2.0NRT,295.4,6.3,D
38.54400,-121.74300,367.0,0.41,0.37,2026-10-01,2118,N20,VIIRS,h,2.0NRT,301.9,21.7,D
38.55000,-121.75000,331.0,0.52,0.42,2026-10-01,0940,N21,VIIRS,l,2.0NRT,290.4,1.1,N
38.56000,-121.76000,333.0,0.39,0.36,2026-10-01,2209,N,VIIRS,n,2.0NRT,291.4,3.3,D
"""


def read(text):
    return pd.read_csv(io.StringIO(text), dtype={"satellite": str, "confidence": str,
                                                 "version": str, "acq_time": str})


def test_modis_layout_is_parsed():
    df = standardize_firms(read(MODIS_SP), source="MODIS_SP")
    assert list(df["platform"]) == ["Aqua", "Aqua", "Terra", "Terra", "Aqua"]
    assert (df["sensor"] == "MODIS").all()
    assert df["acq_datetime"].iloc[0] == pd.Timestamp("2020-08-19 21:23")
    assert df["acq_datetime"].iloc[4] == pd.Timestamp("2020-08-20 01:30")      # '130' means 01:30 UTC
    assert list(df["confidence_class"]) == ["high", "high", "low", "high", "nominal"]
    assert (df["processing"] == "SP").all()
    assert df["scan_km"].iloc[2] == pytest.approx(2.9)                         # pixel size in km, not an angle


def test_viirs_layout_is_parsed():
    df = standardize_firms(read(VIIRS_NRT), source="VIIRS_NOAA20_NRT")
    assert list(df["platform"]) == ["NOAA20", "NOAA20", "NOAA21", "SNPP"]
    assert list(df["confidence_class"]) == ["nominal", "high", "low", "nominal"]
    assert (df["processing"] == "NRT").all()
    assert df["type"].isna().all()                                             # NRT files have no 'type'


def test_missing_optional_columns_do_not_crash_and_are_not_invented(tmp_path):
    # The original loader raised AttributeError here and filled missing FRP with 10.0.
    path = tmp_path / "VIIRS_SNPP_SP.csv"
    pd.DataFrame({"latitude": [1.0], "longitude": [2.0], "bright_ti4": [330.0],
                  "acq_date": ["2024-02-29"], "confidence": ["n"]}).to_csv(path, index=False)
    df = load_firms_csv(str(path))
    assert df["platform"].iloc[0] == "SNPP"            # taken from the single-platform source name
    assert np.isnan(df["frp"].iloc[0])                 # no made-up FRP
    assert pd.isna(df["acq_datetime"].iloc[0])         # no made-up overpass time
    clean, report = quality_filter(df)
    assert len(clean) == 0 and report["dropped_invalid_position_or_time"] == 1


def test_sensor_cannot_be_guessed_silently():
    with pytest.raises(ValueError):
        standardize_firms(pd.DataFrame({"latitude": [1.0], "longitude": [2.0], "acq_date": ["2020-01-01"]}))


def test_quality_filter_counts_add_up():
    df = standardize_firms(read(MODIS_SP), source="MODIS_SP")
    clean, report = quality_filter(df)
    assert report["input_rows"] == 5
    assert report["dropped_duplicates"] == 1
    assert report["dropped_non_vegetation_type"] == 1       # the volcano row (type 1)
    assert report["dropped_low_confidence"] == 1
    assert report["output_rows"] == len(clean) == 2
    assert report["frp_missing_or_nonpositive"] == 1        # FRP -1.0 becomes missing, detection kept
    removed = sum(report[k] for k in ("dropped_invalid_position_or_time", "dropped_unknown_platform",
                                      "dropped_duplicates", "dropped_non_vegetation_type",
                                      "dropped_low_confidence"))
    assert report["input_rows"] - removed == report["output_rows"]


def test_platform_code_that_contradicts_the_sensor_is_rejected():
    raw = read(VIIRS_NRT)
    raw.loc[0, "satellite"] = "A"                            # Aqua is not a VIIRS platform
    df = standardize_firms(raw, source="VIIRS_NOAA20_NRT")
    assert df["platform"].iloc[0] == "unknown"
    _, report = quality_filter(df)
    assert report["dropped_unknown_platform"] == 1


def test_synthetic_rows_stay_labelled(detections):
    assert set(detections["processing"]) == {"SYNTHETIC"}


def test_source_is_read_from_downloader_and_archive_file_names():
    assert source_from_filename("data/firms/VIIRS_NOAA20_SP.csv") == "VIIRS_NOAA20_SP"
    assert source_from_filename("fire_archive_M-C61_123456.csv") == "MODIS_SP"
    assert source_from_filename("fire_nrt_SV-C2_123456.csv") == "VIIRS_SNPP_NRT"
    assert source_from_filename("fire_archive_J1V-C2_99.csv") == "VIIRS_NOAA20_SP"
    assert source_from_filename("my_fires.csv") is None        # falls back to the columns


def test_archive_layout_with_full_satellite_names(tmp_path):
    path = tmp_path / "fire_archive_M-C61_1.csv"
    path.write_text("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,"
                    "confidence,version,bright_t31,frp,daynight,type\n"
                    "38.5,-121.7,325.6,1.1,1.0,2020-08-19,2123,Aqua,MODIS,87,6.1,298.3,45.2,D,0\n"
                    "38.6,-121.8,312.4,2.9,1.6,2020-08-19,1845,Terra,MODIS,45,6.1,295.1,12.9,D,0\n")
    df = load_firms_csv(str(path))
    assert list(df["platform"]) == ["Aqua", "Terra"] and set(df["source"]) == {"MODIS_SP"}
