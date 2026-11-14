"""
Ingestion and quality control for NASA FIRMS active-fire CSV files.

Reads the CSV layout returned by the FIRMS area API and by FIRMS archive
downloads (MODIS Collection 6.1 and VIIRS 375 m, standard or near-real-time
processing) and converts it to one standard table. Nothing is invented: a value
that is absent from the file stays missing (NaN), it is never replaced by a
default number.

The synthetic generator lives in engine/synthetic.py. It writes the same FIRMS
layout, tagged version="SYNTHETIC", so simulated rows can never be mistaken for
satellite observations after ingestion.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .schema import FIRMS_SOURCES, PLATFORMS, SATELLITE_CODES, STANDARD_COLUMNS

_STRING_COLUMNS = {"satellite": str, "confidence": str, "version": str,
                   "acq_time": str, "daynight": str, "instrument": str}


def _infer_sensor(columns: List[str], instrument: Optional[pd.Series]) -> str:
    if instrument is not None and instrument.notna().any():
        value = str(instrument.dropna().iloc[0]).upper()
        if "VIIRS" in value:
            return "VIIRS"
        if "MODIS" in value:
            return "MODIS"
    if "bright_ti4" in columns or "bright_ti5" in columns:
        return "VIIRS"
    if "bright_t31" in columns:
        return "MODIS"
    raise ValueError(
        "Cannot tell whether this file is MODIS or VIIRS: it has no 'instrument', "
        "'bright_ti4' or 'bright_t31' column. Pass sensor='MODIS' or sensor='VIIRS'."
    )


def _parse_datetime(acq_date: pd.Series, acq_time: Optional[pd.Series]) -> pd.Series:
    """FIRMS acq_date (YYYY-MM-DD) + acq_time (HHMM, UTC) -> naive UTC timestamp."""
    date = pd.to_datetime(acq_date, errors="coerce")
    if acq_time is None:
        return pd.Series(pd.NaT, index=acq_date.index, dtype="datetime64[ns]")
    digits = acq_time.astype(str).str.replace(":", "", regex=False).str.strip()
    digits = digits.str.extract(r"^(\d{1,4})", expand=False).str.zfill(4)
    hours = pd.to_numeric(digits.str[:2], errors="coerce")
    minutes = pd.to_numeric(digits.str[2:], errors="coerce")
    bad = (hours > 23) | (minutes > 59)
    stamp = date + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(minutes, unit="m")
    stamp[bad | hours.isna() | minutes.isna()] = pd.NaT
    return stamp.astype("datetime64[ns]")


def _confidence_class(sensor: str, raw: pd.Series) -> pd.Series:
    """
    Common three-level confidence class.
    MODIS reports 0-100 %: <30 low, 30-80 nominal, >=80 high (MODIS fire user guide).
    VIIRS 375 m reports l / n / h directly.
    """
    out = pd.Series("unknown", index=raw.index, dtype=object)
    text = raw.astype(str).str.strip().str.lower()
    letters = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal",
               "h": "high", "high": "high"}
    mapped = text.map(letters)
    out[mapped.notna()] = mapped[mapped.notna()]
    numeric = pd.to_numeric(text, errors="coerce")
    is_num = numeric.notna() & mapped.isna()
    if sensor == "MODIS" or is_num.any():
        out[is_num & (numeric < 30)] = "low"
        out[is_num & (numeric >= 30) & (numeric < 80)] = "nominal"
        out[is_num & (numeric >= 80)] = "high"
    return out


def _processing_level(version: pd.Series) -> pd.Series:
    text = version.astype(str).str.strip().str.upper()
    out = pd.Series("SP", index=version.index, dtype=object)
    out[text.str.contains("SYNTH", na=False)] = "SYNTHETIC"
    out[text.str.endswith("URT", na=False)] = "URT"
    out[text.str.endswith("RT", na=False) & ~text.str.endswith("NRT", na=False)
        & ~text.str.endswith("URT", na=False)] = "RT"
    out[text.str.endswith("NRT", na=False)] = "NRT"
    out[text.isin(["", "NAN", "NONE"])] = "unknown"
    return out


def standardize_firms(raw: pd.DataFrame, sensor: Optional[str] = None,
                      source: Optional[str] = None) -> pd.DataFrame:
    """Convert one FIRMS-layout table to the standard detection table."""
    df = raw.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    for required in ("latitude", "longitude", "acq_date"):
        if required not in df.columns:
            raise ValueError(f"FIRMS file is missing the required column '{required}'.")

    if sensor is None and source in FIRMS_SOURCES:
        sensor = FIRMS_SOURCES[source]["sensor"]
    if sensor is None:
        sensor = _infer_sensor(list(df.columns), df.get("instrument"))
    sensor = sensor.upper()

    n = len(df)
    out = pd.DataFrame(index=df.index)
    out["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    out["sensor"] = sensor

    if "satellite" in df.columns:
        code = df["satellite"].astype(str).str.strip().str.upper()
        platform = code.map(SATELLITE_CODES)
    else:
        platform = pd.Series(np.nan, index=df.index, dtype=object)
    if platform.isna().any() and source in FIRMS_SOURCES:
        candidates = FIRMS_SOURCES[source]["platforms"]
        if len(candidates) == 1:  # VIIRS sources are single-platform
            platform = platform.fillna(candidates[0])
    platform = platform.fillna("unknown")
    # A platform code that contradicts the sensor is a data error, not a guess to fix.
    known = platform.map(lambda p: PLATFORMS.get(p, {}).get("sensor"))
    platform[(known.notna()) & (known != sensor)] = "unknown"
    out["platform"] = platform

    out["acq_datetime"] = _parse_datetime(df["acq_date"], df.get("acq_time"))
    out["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["frp"] = pd.to_numeric(df["frp"], errors="coerce") if "frp" in df.columns else np.nan
    raw_conf = df["confidence"] if "confidence" in df.columns else pd.Series("", index=df.index)
    out["confidence_raw"] = raw_conf.astype(str).str.strip()
    out["confidence_class"] = _confidence_class(sensor, raw_conf)
    out["daynight"] = (df["daynight"].astype(str).str.strip().str.upper().str[:1]
                       if "daynight" in df.columns else "")
    # FIRMS 'scan' and 'track' are the pixel dimensions in km (they grow toward the
    # swath edge). They are sizes, not angles.
    out["scan_km"] = pd.to_numeric(df["scan"], errors="coerce") if "scan" in df.columns else np.nan
    out["track_km"] = pd.to_numeric(df["track"], errors="coerce") if "track" in df.columns else np.nan
    bright_col = "bright_ti4" if "bright_ti4" in df.columns else "brightness"
    out["brightness"] = (pd.to_numeric(df[bright_col], errors="coerce")
                         if bright_col in df.columns else np.nan)
    # 'type' (0 vegetation fire, 1 volcano, 2 other static land source, 3 offshore)
    # exists only in standard-processing files.
    out["type"] = pd.to_numeric(df["type"], errors="coerce") if "type" in df.columns else np.nan
    version = df["version"] if "version" in df.columns else pd.Series("", index=df.index)
    out["version"] = version.astype(str).str.strip()
    out["processing"] = _processing_level(version)
    out["source"] = source or f"{sensor}_file"
    assert len(out) == n
    return out[STANDARD_COLUMNS].reset_index(drop=True)


# File-name fragments used by the FIRMS archive download tool (best effort; if a
# name is not recognised the sensor and platform are still read from the columns).
_ARCHIVE_CODES = {"M-C61": "MODIS", "M6": "MODIS", "SV-C2": "VIIRS_SNPP", "J1V-C2": "VIIRS_NOAA20",
                  "J2V-C2": "VIIRS_NOAA21"}


def source_from_filename(filepath: str) -> Optional[str]:
    """MODIS_SP.csv (downloader) or fire_archive_SV-C2_12345.csv (FIRMS archive) -> source id."""
    stem = os.path.splitext(os.path.basename(filepath))[0].upper()
    for name in sorted(FIRMS_SOURCES, key=len, reverse=True):
        if stem.startswith(name):
            return name
    level = "NRT" if "_NRT_" in stem else "SP" if "_ARCHIVE_" in stem else None
    if level:
        for code, family in _ARCHIVE_CODES.items():
            if f"_{code}_" in stem or stem.endswith(f"_{code}"):
                candidate = f"{family}_{level}"
                return candidate if candidate in FIRMS_SOURCES else None
    return None


def load_firms_csv(filepath: str, sensor: Optional[str] = None,
                   source: Optional[str] = None) -> pd.DataFrame:
    """Load one FIRMS CSV file (API or archive layout) into the standard table."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    raw = pd.read_csv(filepath, dtype=_STRING_COLUMNS, low_memory=False)
    if source is None:
        source = source_from_filename(filepath)
    return standardize_firms(raw, sensor=sensor, source=source)


def quality_filter(df: pd.DataFrame, drop_low_confidence: bool = True,
                   vegetation_only: bool = True) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Apply documented screening rules and report how many rows each rule removed.

    - rows without a valid position or UTC time are unusable and removed;
    - rows from an unidentified platform are removed (they cannot be assigned an orbit);
    - exact duplicates (platform, time, position) are removed;
    - non-vegetation hot spots (type 1-3: volcano, static source, offshore) are
      removed where the 'type' field exists (standard processing only);
    - low-confidence detections are removed by default;
    - a non-positive FRP is treated as missing; the detection itself is kept.
    """
    report: Dict[str, Any] = {"input_rows": int(len(df))}
    keep = df.copy()

    valid = (keep["latitude"].between(-90, 90) & keep["longitude"].between(-180, 180)
             & keep["acq_datetime"].notna())
    report["dropped_invalid_position_or_time"] = int((~valid).sum())
    keep = keep[valid]

    known = keep["platform"].isin(PLATFORMS.keys())
    report["dropped_unknown_platform"] = int((~known).sum())
    keep = keep[known]

    dup = keep.duplicated(subset=["platform", "acq_datetime", "latitude", "longitude"])
    report["dropped_duplicates"] = int(dup.sum())
    keep = keep[~dup]

    has_type = keep["type"].notna()
    report["rows_without_type_field"] = int((~has_type).sum())
    if vegetation_only:
        non_veg = has_type & (keep["type"] != 0)
        report["dropped_non_vegetation_type"] = int(non_veg.sum())
        keep = keep[~non_veg]
    else:
        report["dropped_non_vegetation_type"] = 0

    if drop_low_confidence:
        low = keep["confidence_class"] == "low"
        report["dropped_low_confidence"] = int(low.sum())
        keep = keep[~low]
    else:
        report["dropped_low_confidence"] = 0

    keep = keep.copy()
    bad_frp = keep["frp"].notna() & (keep["frp"] <= 0)
    keep.loc[bad_frp, "frp"] = np.nan
    report["frp_missing_or_nonpositive"] = int(keep["frp"].isna().sum())
    report["output_rows"] = int(len(keep))
    report["rules"] = {"drop_low_confidence": drop_low_confidence,
                       "vegetation_only": vegetation_only}
    return keep.reset_index(drop=True), report


def load_firms_directory(directory: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Load every FIRMS CSV in a directory, plus manifest.json if the downloader wrote one.
    Returns (standard table, provenance).
    """
    files = sorted(glob.glob(os.path.join(directory, "*.csv")))
    if not files:
        raise FileNotFoundError(f"No FIRMS CSV files found in {directory}")
    manifest = None
    manifest_path = os.path.join(directory, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)

    frames, file_info = [], []
    for path in files:
        table = load_firms_csv(path)
        frames.append(table)
        file_info.append({
            "file": os.path.basename(path),
            "source": str(table["source"].iloc[0]) if len(table) else "empty",
            "rows": int(len(table)),
            "date_min": table["acq_date"].min() if len(table) else None,
            "date_max": table["acq_date"].max() if len(table) else None,
        })
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=STANDARD_COLUMNS)
    provenance = {"directory": directory, "files": file_info, "manifest": manifest}
    return data, provenance
