"""
Shared constants: platforms, FIRMS sources, satellite codes, coverage dates.

Dates and codes below were checked against NASA FIRMS / Earthdata pages on
2026-11-14 (see docs/METHODS.md, "Sources"). They describe when data exist in
FIRMS, not when the spacecraft launched.
"""

from __future__ import annotations

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = 111.195  # 2*pi*R/360 for the mean Earth radius above

# platform -> properties. "orbit" matters: Aqua, S-NPP, NOAA-20 and NOAA-21 share
# the early-afternoon orbit (~13:30 / 01:30 local); Terra is the morning orbit
# (~10:30 / 22:30 local) and samples a different part of the fire diurnal cycle.
PLATFORMS = {
    "Terra": {"sensor": "MODIS", "orbit": "morning", "nadir_pixel_km": 1.0,
              "firms_start": "2000-11-01", "firms_end": None},
    "Aqua": {"sensor": "MODIS", "orbit": "afternoon", "nadir_pixel_km": 1.0,
             "firms_start": "2002-07-03", "firms_end": None},
    "SNPP": {"sensor": "VIIRS", "orbit": "afternoon", "nadir_pixel_km": 0.375,
             "firms_start": "2012-01-20", "firms_end": "2026-11-02"},
    "NOAA20": {"sensor": "VIIRS", "orbit": "afternoon", "nadir_pixel_km": 0.375,
               "firms_start": "2018-04-01", "firms_end": None},
    "NOAA21": {"sensor": "VIIRS", "orbit": "afternoon", "nadir_pixel_km": 0.375,
               "firms_start": "2023-03-01", "firms_end": None},
}

PLATFORM_LABELS = {
    "Terra": "Terra MODIS", "Aqua": "Aqua MODIS", "SNPP": "Suomi-NPP VIIRS",
    "NOAA20": "NOAA-20 VIIRS", "NOAA21": "NOAA-21 VIIRS",
}

# FIRMS "satellite" column values seen in API and archive downloads.
SATELLITE_CODES = {
    "T": "Terra", "TERRA": "Terra",
    "A": "Aqua", "AQUA": "Aqua",
    "N": "SNPP", "NPP": "SNPP", "SNPP": "SNPP", "SUOMI NPP": "SNPP", "SUOMI-NPP": "SNPP",
    "N20": "NOAA20", "1": "NOAA20", "J1": "NOAA20", "NOAA-20": "NOAA20", "NOAA20": "NOAA20",
    "N21": "NOAA21", "2": "NOAA21", "J2": "NOAA21", "NOAA-21": "NOAA21", "NOAA21": "NOAA21",
}

# FIRMS API source id -> what it contains.
FIRMS_SOURCES = {
    "MODIS_SP": {"sensor": "MODIS", "platforms": ["Terra", "Aqua"], "processing": "SP",
                 "product": "MODIS Collection 6.1 active fire (MCD14ML), standard processing"},
    "MODIS_NRT": {"sensor": "MODIS", "platforms": ["Terra", "Aqua"], "processing": "NRT",
                  "product": "MODIS Collection 6.1 active fire (MCD14DL), near real-time"},
    "VIIRS_SNPP_SP": {"sensor": "VIIRS", "platforms": ["SNPP"], "processing": "SP",
                      "product": "VIIRS S-NPP 375 m active fire (VNP14IMG family), standard processing"},
    "VIIRS_SNPP_NRT": {"sensor": "VIIRS", "platforms": ["SNPP"], "processing": "NRT",
                       "product": "VIIRS S-NPP 375 m active fire (VNP14IMGTDL_NRT), near real-time"},
    "VIIRS_NOAA20_SP": {"sensor": "VIIRS", "platforms": ["NOAA20"], "processing": "SP",
                        "product": "VIIRS NOAA-20 375 m active fire (VJ114IMG family), standard processing"},
    "VIIRS_NOAA20_NRT": {"sensor": "VIIRS", "platforms": ["NOAA20"], "processing": "NRT",
                         "product": "VIIRS NOAA-20 375 m active fire (VJ114IMGTDL_NRT), near real-time"},
    "VIIRS_NOAA21_SP": {"sensor": "VIIRS", "platforms": ["NOAA21"], "processing": "SP",
                        "product": "VIIRS NOAA-21 375 m active fire (VJ214IMG family), standard processing"},
    "VIIRS_NOAA21_NRT": {"sensor": "VIIRS", "platforms": ["NOAA21"], "processing": "NRT",
                         "product": "VIIRS NOAA-21 375 m active fire (VJ214IMGTDL_NRT), near real-time"},
}

# Standardised detection table produced by engine.data_loader.
STANDARD_COLUMNS = [
    "latitude", "longitude", "sensor", "platform", "acq_datetime", "acq_date",
    "frp", "confidence_raw", "confidence_class", "daynight", "scan_km", "track_km",
    "brightness", "type", "version", "processing", "source",
]

# The harmonised record is expressed on this platform's scale.
REFERENCE_PLATFORM = "Aqua"
