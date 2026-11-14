"""
Burning activity calendar, seasonality and trend statistics.

Conventions
- Calendar matrices are (year x 366). Day 366 exists only in leap years and is
  missing (None) otherwise. Days without data coverage are None, never 0.
- Dates are local solar dates (see engine.gridding).
- "Season" statistics are computed on FIRE YEARS: 12-month windows that start in
  the quietest part of the climatological year. A fire season that runs across
  New Year (southern-hemisphere summer, for example) is therefore not cut in two.
- Season boundaries are the days by which 10 %, 50 % and 90 % of the fire
  year's harmonised active-cell count has accumulated. They are count-based
  percentiles. They are not energy-based: FRP is an instantaneous power, and
  summing overpass snapshots does not give fire radiative energy.
- Trends are reported as observed changes (Theil-Sen slope, Mann-Kendall p).
  No cause is assigned. A change in a satellite record can come from fire
  activity, from land use, from the observing system, or from chance.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

MIN_FIRE_YEAR_COVERAGE = 0.90
MIN_FIRE_YEAR_TOTAL = 20.0
MIN_YEARS_FOR_TREND = 8


def _clean(values: np.ndarray, digits: int = 2) -> List[Optional[float]]:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in values]


def calendar_matrix(series: pd.Series, years: List[int], digits: int = 2) -> List[List[Optional[float]]]:
    """series: daily values indexed by date (NaN = no data) -> year x 366 nested list."""
    grid = np.full((len(years), 366), np.nan)
    index = pd.DatetimeIndex(series.index)
    row = {y: i for i, y in enumerate(years)}
    rows = np.array([row.get(y, -1) for y in index.year])
    ok = rows >= 0
    grid[rows[ok], index.dayofyear.values[ok] - 1] = series.values[ok]
    return [_clean(r, digits) for r in grid]


def monthly_table(daily: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly totals of the harmonised record with coverage.
    daily needs: harmonized_cells, harmonized_frp_mw, source (0 = no data).
    """
    period = pd.DatetimeIndex(daily.index).to_period("M")
    covered = daily["source"] > 0
    g = daily.assign(covered=covered).groupby(period)
    out = pd.DataFrame({
        "days": g.size(),
        "days_covered": g["covered"].sum(),
        "cells": g["harmonized_cells"].sum(min_count=1),
        "frp_mw_sum": g["harmonized_frp_mw"].sum(min_count=1),
        "days_reference_observed": g["source"].apply(lambda s: int((s == 1).sum())),
        "days_viirs_derived": g["source"].apply(lambda s: int((s == 2).sum())),
        "days_terra_derived": g["source"].apply(lambda s: int((s == 3).sum())),
    })
    out["coverage"] = out["days_covered"] / out["days"]
    out["year"] = out.index.year
    out["month"] = out.index.month
    return out


def climatology_by_doy(daily_values: pd.Series) -> np.ndarray:
    """Mean activity for each day of year 1..365 over covered days (day 366 folds into 365)."""
    index = pd.DatetimeIndex(daily_values.index)
    doy = np.minimum(index.dayofyear.values, 365)
    frame = pd.DataFrame({"doy": doy, "v": daily_values.values}).dropna()
    clim = frame.groupby("doy")["v"].mean().reindex(np.arange(1, 366)).fillna(0.0).values
    return clim


def _circular_smooth(values: np.ndarray, window: int) -> np.ndarray:
    half = window // 2
    padded = np.concatenate([values[-half:], values, values[:half]])
    return np.convolve(padded, np.ones(window) / window, mode="valid")[: len(values)]


def fire_year_start_doy(clim: np.ndarray) -> int:
    """Day of year in the middle of the quietest 61-day stretch of the climatology."""
    if clim.sum() <= 0:
        return 1
    return int(np.argmin(_circular_smooth(clim, 61))) + 1


def core_season(clim: np.ndarray, share: float = 0.80) -> Optional[Dict[str, Any]]:
    """Shortest (circular) run of days holding `share` of climatological activity."""
    total = clim.sum()
    if total <= 0:
        return None
    smooth = _circular_smooth(clim, 15)
    doubled = np.concatenate([smooth, smooth])
    csum = np.concatenate([[0.0], np.cumsum(doubled)])
    need = share * smooth.sum()
    best = None
    for start in range(365):
        end = np.searchsorted(csum, csum[start] + need, side="left")
        length = end - start
        if length <= 365 and (best is None or length < best[1]):
            best = (start, length)
    start, length = best
    return {"start_doy": start + 1, "end_doy": (start + length - 1) % 365 + 1,
            "length_days": int(length), "share_of_activity": share}


def phenology(daily: pd.DataFrame, start_doy: int) -> List[Dict[str, Any]]:
    """Per fire year: totals and the 10/50/90 % accumulation days of harmonised cells."""
    index = pd.DatetimeIndex(daily.index)
    if len(index) == 0:
        return []
    records = []
    for year in range(index.year.min() - 1, index.year.max() + 1):
        begin = pd.Timestamp(year, 1, 1) + pd.Timedelta(days=start_doy - 1)
        finish = pd.Timestamp(year + 1, 1, 1) + pd.Timedelta(days=start_doy - 2)
        window = daily[(index >= begin) & (index <= finish)]
        n_days = (finish - begin).days + 1
        covered = int((window["source"] > 0).sum())
        label = str(year) if start_doy <= 31 else f"{year}/{(year + 1) % 100:02d}"
        record: Dict[str, Any] = {
            "fire_year": label, "start_date": begin.strftime("%Y-%m-%d"),
            "end_date": finish.strftime("%Y-%m-%d"),
            "coverage": round(covered / n_days, 3), "usable": False,
        }
        if covered == 0:
            continue
        values = window["harmonized_cells"].fillna(0.0).values
        total = float(values.sum())
        record["total_cells"] = round(total, 1)
        frp = window["harmonized_frp_mw"]
        record["frp_mw_sum"] = None if frp.notna().sum() == 0 else round(float(frp.sum()), 1)
        if covered / n_days >= MIN_FIRE_YEAR_COVERAGE and total >= MIN_FIRE_YEAR_TOTAL:
            cum = np.cumsum(values) / total
            offsets = pd.DatetimeIndex(window.index)
            def day_at(q):
                return int(np.argmax(cum >= q))
            i10, i50, i90 = day_at(0.10), day_at(0.50), day_at(0.90)
            record.update({
                "usable": True,
                "p10_date": offsets[i10].strftime("%Y-%m-%d"),
                "p50_date": offsets[i50].strftime("%Y-%m-%d"),
                "p90_date": offsets[i90].strftime("%Y-%m-%d"),
                "p10_day": int((offsets[i10] - begin).days),
                "p50_day": int((offsets[i50] - begin).days),
                "p90_day": int((offsets[i90] - begin).days),
                "season_length_days": int((offsets[i90] - offsets[i10]).days),
            })
            sources = window.loc[window["source"] > 0, "source"]
            record["dominant_source"] = int(sources.mode().iloc[0])
        else:
            record["why_not_usable"] = ("coverage below 90 %" if covered / n_days < MIN_FIRE_YEAR_COVERAGE
                                        else "too little activity for stable percentiles")
        records.append(record)
    return records


def trend(years: np.ndarray, values: np.ndarray, unit: str) -> Dict[str, Any]:
    """Theil-Sen slope with 95 % interval and Mann-Kendall (Kendall tau) p-value."""
    years = np.asarray(years, dtype=float)
    values = np.asarray(values, dtype=float)
    ok = np.isfinite(values)
    years, values = years[ok], values[ok]
    if len(values) < MIN_YEARS_FOR_TREND:
        return {"available": False,
                "reason": f"{len(values)} usable fire years; at least {MIN_YEARS_FOR_TREND} are needed"}
    slope, intercept, low, high = stats.theilslopes(values, years, 0.95)
    tau_value, p_value = stats.kendalltau(years, values)
    return {
        "available": True, "n_years": int(len(values)), "unit": unit,
        "slope_per_year": round(float(slope), 4),
        "slope_95ci": [round(float(low), 4), round(float(high), 4)],
        "slope_per_decade": round(float(slope * 10), 3),
        "kendall_tau": round(float(tau_value), 3),
        "p_value": round(float(p_value), 4),
        "significant_at_5pct": bool(p_value < 0.05),
        "interpretation": ("Observed change in this satellite record. No cause is assigned: it can "
                           "reflect fire activity, land use, the observing system, or chance."),
    }


def season_trends(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    usable = [r for r in records if r.get("usable")]
    years = np.array([int(r["fire_year"][:4]) for r in usable], dtype=float)
    return {
        "season_length": trend(years, np.array([r["season_length_days"] for r in usable], float), "days"),
        "season_start": trend(years, np.array([r["p10_day"] for r in usable], float),
                              "days after fire-year start"),
        "annual_total": trend(years, np.array([r["total_cells"] for r in usable], float),
                              "harmonised active cells"),
    }
