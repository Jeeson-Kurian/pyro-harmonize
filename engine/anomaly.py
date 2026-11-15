"""
Unusual conditions and critical periods.

Monthly anomaly: is this month's harmonised burning activity unusual for this
calendar month in this area? The target month is compared with the same
calendar month in the other years of the harmonised record (leave-one-out), so
a month never contributes to its own baseline.

The baseline uses the median and quartiles, not the mean, because fire activity
is strongly skewed: one extreme year would distort a mean-based baseline.

A result is only issued when the month itself and enough baseline months have
adequate data coverage. Otherwise the answer is "not enough data", not a number.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

MIN_MONTH_COVERAGE = 0.80
MIN_BASELINE_YEARS = 5
EXCEPTIONAL_Z = 3.0


def _category(percentile: float, robust_z: float) -> str:
    """
    Percentile rank alone is not enough with a short record: with six baseline
    years the lowest month is always at percentile 0. "Exceptionally" therefore
    also requires the month to lie at least 3 robust standard deviations from
    the median.
    """
    if percentile >= 95 and robust_z >= EXCEPTIONAL_Z:
        return "exceptionally high"
    if percentile >= 80:
        return "above normal"
    if percentile <= 5 and robust_z <= -EXCEPTIONAL_Z:
        return "exceptionally low"
    if percentile <= 20:
        return "below normal"
    return "near normal"


def monthly_anomalies(monthly: pd.DataFrame, value_column: str = "cells") -> pd.DataFrame:
    """
    monthly: output of calendar_generator.monthly_table (PeriodIndex).
    Adds baseline statistics and an anomaly classification for every month.
    """
    out = monthly.copy()
    usable = (out["coverage"] >= MIN_MONTH_COVERAGE) & out[value_column].notna()
    cols = {k: [] for k in ("baseline_n", "baseline_median", "baseline_q25", "baseline_q75",
                            "anomaly_pct", "anomaly_abs", "percentile", "robust_z", "category")}
    for period, row in out.iterrows():
        same = out[(out["month"] == row["month"]) & (out.index != period) & usable]
        base = same[value_column].values.astype(float)
        n = len(base)
        cols["baseline_n"].append(n)
        if not usable.loc[period] or n < MIN_BASELINE_YEARS:
            for key in ("baseline_median", "baseline_q25", "baseline_q75", "anomaly_pct",
                        "anomaly_abs", "percentile", "robust_z"):
                cols[key].append(np.nan)
            cols["category"].append("month coverage too low" if not usable.loc[period]
                                    else "baseline too short")
            continue
        value = float(row[value_column])
        median = float(np.median(base))
        mad = float(np.median(np.abs(base - median)))
        percentile = float(100.0 * (np.sum(base < value) + 0.5 * np.sum(base == value)) / n)
        cols["baseline_median"].append(median)
        cols["baseline_q25"].append(float(np.quantile(base, 0.25)))
        cols["baseline_q75"].append(float(np.quantile(base, 0.75)))
        cols["anomaly_abs"].append(value - median)
        cols["anomaly_pct"].append(100.0 * (value - median) / median if median > 0 else np.nan)
        cols["percentile"].append(percentile)
        # robust spread: 1.4826 x median absolute deviation, at least one active cell
        robust_z = (value - median) / max(1.4826 * mad, 1.0)
        cols["robust_z"].append(robust_z)
        cols["category"].append(_category(percentile, robust_z))
    for key, values in cols.items():
        out[key] = values
    return out


def weekly_climatology(daily: pd.DataFrame, value_column: str = "harmonized_cells") -> List[Dict[str, Any]]:
    """
    For each week of the year (52 bins of 7 days; the last bin takes the remainder):
    median, upper quartile and maximum weekly activity across fully covered years.
    """
    index = pd.DatetimeIndex(daily.index)
    week = np.minimum((index.dayofyear.values - 1) // 7, 51)
    frame = pd.DataFrame({"year": index.year, "week": week,
                          "v": daily[value_column].values, "covered": (daily["source"] > 0).values})
    g = frame.groupby(["year", "week"])
    weekly = pd.DataFrame({"total": g["v"].sum(min_count=1), "covered": g["covered"].mean()})
    weekly = weekly[weekly["covered"] >= 0.85].reset_index()
    rows = []
    for w in range(52):
        values = weekly.loc[weekly["week"] == w, "total"].dropna().values
        start = pd.Timestamp(2001, 1, 1) + pd.Timedelta(days=7 * w)
        rows.append({
            "week": w + 1, "starts": start.strftime("%b %d"), "n_years": int(len(values)),
            "median": round(float(np.median(values)), 2) if len(values) else None,
            "q75": round(float(np.quantile(values, 0.75)), 2) if len(values) else None,
            "max": round(float(values.max()), 2) if len(values) else None,
        })
    return rows


def critical_weeks(weekly: List[Dict[str, Any]], fraction_of_peak: float = 0.5) -> Dict[str, Any]:
    """Weeks whose typical (median) activity is at least half of the peak week's."""
    medians = np.array([w["median"] if w["median"] is not None else 0.0 for w in weekly])
    if medians.max() <= 0:
        return {"available": False, "reason": "no typical activity in any week"}
    flagged = [weekly[i] for i in np.flatnonzero(medians >= fraction_of_peak * medians.max())]
    peak = weekly[int(np.argmax(medians))]
    return {"available": True, "peak_week": peak["week"], "peak_week_starts": peak["starts"],
            "weeks": [w["week"] for w in flagged], "starts": [w["starts"] for w in flagged],
            "rule": f"median weekly activity >= {int(fraction_of_peak * 100)} % of the peak week"}
