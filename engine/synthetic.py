"""
SYNTHETIC active-fire simulator. NOT satellite data.

Purpose: (1) automated tests with a known ground truth, (2) a clearly labelled
demo mode for when no NASA FIRMS files have been downloaded yet.

The simulator is deliberately independent of the harmonisation code. It models
the observation process (fires with sub-pixel structure, a diurnal cycle,
pixel footprints that grow toward the swath edge, per-pixel detection limits,
cloud, sensor outages, separate morning and afternoon orbits) and then writes
ordinary FIRMS-layout tables. The pipeline has to recover the cross-sensor
relationship from those tables the same way it would from real files.

Every simulated row carries version="SYNTHETIC", which the loader turns into
processing="SYNTHETIC", so the label travels with the data into every export.

There is NO built-in trend unless trend_per_year is set explicitly. Nothing a
user sees in synthetic mode says anything about real fire activity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .schema import KM_PER_DEG_LAT, PLATFORMS

_SAT_CODE = {"Terra": "T", "Aqua": "A", "SNPP": "N", "NOAA20": "N20", "NOAA21": "N21"}
_SOURCE = {"Terra": "MODIS_SP", "Aqua": "MODIS_SP", "SNPP": "VIIRS_SNPP_SP",
           "NOAA20": "VIIRS_NOAA20_SP", "NOAA21": "VIIRS_NOAA21_SP"}
# local solar overpass hours (day, night)
_ORBIT_HOURS = {"morning": (10.5, 22.5), "afternoon": (13.5, 1.5)}


def _diurnal(local_hour: np.ndarray) -> np.ndarray:
    """Relative fire intensity through the day, peaking mid-afternoon."""
    delta = (local_hour - 14.5 + 12.0) % 24.0 - 12.0
    return 0.15 + 0.85 * np.exp(-0.5 * (delta / 3.0) ** 2)


def generate_synthetic_firms(
    start: str = "2001-01-01",
    end: str = "2025-12-31",
    bbox: Tuple[float, float, float, float] = (-124.0, 36.0, -119.0, 41.0),
    seed: int = 7,
    fires_per_year: float = 450.0,
    trend_per_year: float = 0.0,
    season_peak_doy: int = 225,
    season_width_days: float = 38.0,
    platforms: Tuple[str, ...] = ("Terra", "Aqua", "SNPP", "NOAA20"),
    aqua_outage: Optional[Tuple[str, str]] = ("2016-08-10", "2016-09-05"),
) -> Dict[str, Any]:
    """
    Returns {"frames": {source: FIRMS-layout DataFrame}, "manifest": dict, "truth": DataFrame}.
    bbox is (west, south, east, north).
    """
    rng = np.random.default_rng(seed)
    west, south, east, north = bbox
    day0 = np.datetime64(start, "D")
    day1 = np.datetime64(end, "D")
    n_days = int((day1 - day0).astype(int)) + 1
    years = (day0 + np.arange(n_days)).astype("datetime64[Y]").astype(int) + 1970
    year_list = np.unique(years)

    # ---- fires -----------------------------------------------------------------
    fire_start, fire_dur, fire_peak, fire_lat, fire_lon, fire_radius = [], [], [], [], [], []
    for k, year in enumerate(year_list):
        expected = fires_per_year * (1.0 + trend_per_year) ** k * rng.lognormal(0.0, 0.18)
        n = int(rng.poisson(expected))
        jan1 = np.datetime64(f"{year}-01-01", "D")
        doy = np.round(rng.normal(season_peak_doy, season_width_days, n)).astype(int)
        start_day = (jan1 + (doy - 1).astype("timedelta64[D]") - day0).astype(int)
        fire_start.append(start_day)
        fire_dur.append(np.minimum(1 + rng.geometric(0.42, n) - 1, 12))
        fire_peak.append(rng.lognormal(np.log(22.0), 1.25, n))
        fire_lat.append(rng.uniform(south, north, n))
        fire_lon.append(rng.uniform(west, east, n))
    fire_start = np.concatenate(fire_start)
    fire_dur = np.maximum(np.concatenate(fire_dur), 1)
    fire_peak = np.concatenate(fire_peak)
    fire_lat = np.concatenate(fire_lat)
    fire_lon = np.concatenate(fire_lon)
    fire_radius = np.minimum(0.25 + 0.22 * np.sqrt(fire_peak / 10.0), 4.0)

    # ---- fire-days -------------------------------------------------------------
    fid = np.repeat(np.arange(len(fire_start)), fire_dur)
    day_in_fire = np.concatenate([np.arange(d) for d in fire_dur]) if len(fire_dur) else np.array([], int)
    fd_day = fire_start[fid] + day_in_fire
    inside = (fd_day >= 0) & (fd_day < n_days)
    fid, day_in_fire, fd_day = fid[inside], day_in_fire[inside], fd_day[inside]
    growth = np.where(fire_dur[fid] > 1,
                      np.sin(np.pi * (day_in_fire + 0.5) / fire_dur[fid]), 1.0)
    n_fd = len(fid)

    truth = (pd.DataFrame({"day": fd_day, "frp": fire_peak[fid] * growth * _diurnal(np.array([13.5]))[0]})
             .groupby("day").agg(true_active_fires=("frp", "size"), true_afternoon_frp_mw=("frp", "sum"))
             .reindex(np.arange(n_days), fill_value=0).reset_index())
    truth["local_date"] = day0 + truth["day"].values.astype("timedelta64[D]")
    truth = truth.drop(columns="day")

    # shared (all platforms) randomness per fire-day and slot: weather and fire behaviour
    shared_cloud = rng.random((n_fd, 2)) < 0.12
    shared_noise = rng.lognormal(0.0, 0.20, (n_fd, 2))

    frames: Dict[str, list] = {}
    coverage: Dict[str, list] = {}
    platform_gaps: Dict[str, list] = {}

    for platform in platforms:
        info = PLATFORMS[platform]
        sensor = info["sensor"]
        p_start = max(day0, np.datetime64(info["firms_start"], "D"))
        p_end = day1 if info["firms_end"] is None else min(day1, np.datetime64(info["firms_end"], "D"))
        if p_start > p_end:
            continue
        source = _SOURCE[platform]
        coverage.setdefault(source, [])
        operating = (fd_day >= int((p_start - day0).astype(int))) & (fd_day <= int((p_end - day0).astype(int)))
        if platform == "Aqua" and aqua_outage is not None:
            o0 = int((np.datetime64(aqua_outage[0], "D") - day0).astype(int))
            o1 = int((np.datetime64(aqua_outage[1], "D") - day0).astype(int))
            if o1 >= 0 and o0 < n_days:
                operating &= ~((fd_day >= o0) & (fd_day <= o1))
                platform_gaps["Aqua"] = [[aqua_outage[0], aqua_outage[1]]]
        prng = np.random.default_rng([seed, sum(map(ord, platform))])
        hours = _ORBIT_HOURS[info["orbit"]]
        pieces = []
        for slot, base_hour in enumerate(hours):  # 0 = day, 1 = night
            jitter = prng.normal(0.0, 0.40, n_days)            # one overpass time per date
            local_hour = (base_hour + jitter[fd_day] + prng.normal(0, 0.03, n_fd)) % 24.0
            power = (fire_peak[fid] * growth * _diurnal(local_hour)
                     * shared_noise[:, slot] * prng.lognormal(0.0, 0.15, n_fd))
            seen = operating & ~shared_cloud[:, slot] & (prng.random(n_fd) > 0.06)
            rows = np.flatnonzero(seen)
            if rows.size == 0:
                continue
            power_r = power[rows]
            # sub-pixel structure: each fire is a set of burning elements
            n_el = np.clip(1 + prng.poisson(power_r / 8.0), 1, 60)
            owner = np.repeat(np.arange(rows.size), n_el)
            weight = prng.gamma(1.0, 1.0, owner.size)
            weight /= np.bincount(owner, weights=weight)[owner]
            el_frp = power_r[owner] * weight
            radius = fire_radius[fid[rows]][owner]
            x = prng.normal(0.0, radius)                         # km east of fire centre
            y = prng.normal(0.0, radius)                         # km north of fire centre
            # pixel footprint grows toward the swath edge
            u = prng.random(rows.size)
            if sensor == "MODIS":
                scan = 1.0 + 3.8 * u ** 3
                track = 1.0 + 1.0 * u ** 3
                per_area_limit = np.where(slot == 0, 6.0, 3.5)
                gain, sensor_sigma = 1.0, 0.12
            else:
                scan = 0.375 + 0.42 * u ** 2
                track = 0.375 + 0.40 * u ** 2
                per_area_limit = np.where(slot == 0, 6.0, 2.5)
                gain, sensor_sigma = 0.90, 0.18
            ox = prng.random(rows.size) * scan
            oy = prng.random(rows.size) * track
            ix = np.floor((x + ox[owner]) / scan[owner]).astype(np.int64)
            iy = np.floor((y + oy[owner]) / track[owner]).astype(np.int64)
            pix = (pd.DataFrame({"o": owner, "ix": ix, "iy": iy, "frp": el_frp})
                   .groupby(["o", "ix", "iy"], sort=False)["frp"].sum().reset_index())
            o = pix["o"].values
            pixel_frp = pix["frp"].values * gain * prng.lognormal(0.0, sensor_sigma, len(pix))
            limit = per_area_limit * scan[o] * track[o]
            p_detect = 1.0 / (1.0 + np.exp(-(np.log(pixel_frp) - np.log(limit)) / 0.25))
            hit = prng.random(len(pix)) < p_detect
            pix, o, pixel_frp = pix[hit], o[hit], pixel_frp[hit]
            if len(pix) == 0:
                continue
            px = (pix["ix"].values + 0.5) * scan[o] - ox[o]
            py = (pix["iy"].values + 0.5) * track[o] - oy[o]
            f = fid[rows][o]
            lat = fire_lat[f] + py / KM_PER_DEG_LAT
            lon = fire_lon[f] + px / (KM_PER_DEG_LAT * np.cos(np.radians(fire_lat[f])))
            # local solar time -> UTC
            lh = local_hour[rows][o]
            local_day = fd_day[rows][o]
            utc_minutes = np.round(local_day * 1440.0 + lh * 60.0 - lon * 4.0).astype(np.int64)
            stamp = day0.astype("datetime64[m]") + utc_minutes.astype("timedelta64[m]")
            pieces.append(pd.DataFrame({
                "latitude": np.round(lat, 5), "longitude": np.round(lon, 5),
                "scan": np.round(scan[o], 2), "track": np.round(track[o], 2),
                "stamp": stamp, "frp": np.round(pixel_frp, 2),
                "daynight": np.where((lh >= 6) & (lh < 18), "D", "N"),
            }))
        if not pieces:
            continue
        table = pd.concat(pieces, ignore_index=True)
        n = len(table)
        stamp = pd.to_datetime(table.pop("stamp"))
        table["acq_date"] = stamp.dt.strftime("%Y-%m-%d")
        table["acq_time"] = stamp.dt.strftime("%H%M")
        table["satellite"] = _SAT_CODE[platform]
        table["instrument"] = sensor
        table["version"] = "SYNTHETIC"
        table["type"] = np.where(prng.random(n) < 0.01, 2, 0)
        brightness = np.round(310.0 + 12.0 * np.log1p(table["frp"].values) + prng.normal(0, 3, n), 1)
        if sensor == "MODIS":
            conf = np.clip(np.round(55 + 12 * np.log1p(table["frp"].values) + prng.normal(0, 18, n)), 0, 100)
            table["brightness"] = brightness
            table["confidence"] = conf.astype(int).astype(str)
            table["bright_t31"] = np.round(brightness - prng.uniform(10, 30, n), 1)
            cols = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
                    "satellite", "instrument", "confidence", "version", "bright_t31", "frp",
                    "daynight", "type"]
        else:
            table["bright_ti4"] = brightness
            table["confidence"] = prng.choice(["l", "n", "h"], size=n, p=[0.07, 0.85, 0.08])
            table["bright_ti5"] = np.round(brightness - prng.uniform(10, 30, n), 1)
            cols = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time",
                    "satellite", "instrument", "confidence", "version", "bright_ti5", "frp",
                    "daynight", "type"]
        frames.setdefault(source, []).append(table[cols])
        interval = [str(p_start), str(p_end)]
        if interval not in coverage[source]:
            # a source covers the union of its platforms (MODIS_SP = Terra + Aqua)
            if coverage[source]:
                coverage[source] = [[min(coverage[source][0][0], interval[0]),
                                     max(coverage[source][0][1], interval[1])]]
            else:
                coverage[source] = [interval]

    out_frames = {src: pd.concat(parts, ignore_index=True) for src, parts in frames.items()}
    manifest = {
        "synthetic": True,
        "note": "SIMULATED data from engine/synthetic.py. Not satellite observations.",
        "bbox": list(bbox),
        "requested": {"start": start, "end": end},
        "sources": {src: {"coverage": coverage.get(src, []), "rows": int(len(df))}
                    for src, df in out_frames.items()},
        "platform_gaps": platform_gaps,
        "generator": {"seed": seed, "fires_per_year": fires_per_year,
                      "trend_per_year": trend_per_year, "season_peak_doy": season_peak_doy},
    }
    return {"frames": out_frames, "manifest": manifest, "truth": truth}
