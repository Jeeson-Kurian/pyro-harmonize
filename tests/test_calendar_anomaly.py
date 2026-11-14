"""Calendar, leap years, fire years, anomalies and trends."""

import numpy as np
import pandas as pd
import pytest

from engine import anomaly as an
from engine import calendar_generator as cal
from engine.pipeline import AnalysisConfig, run_analysis
from engine.synthetic import generate_synthetic_firms
from tests.conftest import standardize_world


def make_daily(index, values, source=1):
    return pd.DataFrame({"harmonized_cells": values, "harmonized_frp_mw": np.asarray(values, float) * 10.0,
                         "source": source}, index=index)


def test_calendar_has_366_days_and_day_366_only_in_leap_years():
    index = pd.date_range("2019-01-01", "2020-12-31", freq="D")
    matrix = cal.calendar_matrix(pd.Series(1.0, index=index), [2019, 2020])
    assert len(matrix[0]) == len(matrix[1]) == 366
    assert matrix[0][365] is None            # 2019 has no day 366
    assert matrix[1][365] == 1.0             # 31 December 2020 is day 366 and is kept
    assert matrix[0][364] == 1.0


def test_missing_days_are_none_never_zero():
    index = pd.date_range("2021-01-01", "2021-01-10", freq="D")
    values = pd.Series([0, 0, np.nan, 3, np.nan, 0, 0, 0, 0, 0], index=index, dtype=float)
    row = cal.calendar_matrix(values, [2021])[0]
    assert row[0] == 0.0 and row[2] is None and row[3] == 3.0 and row[4] is None
    assert row[20] is None                    # outside the series: no data


def test_fire_year_follows_a_season_that_crosses_new_year():
    # peak in early January, like a southern-hemisphere summer season
    world = generate_synthetic_firms(start="2008-01-01", end="2020-12-31", seed=9, season_peak_doy=8,
                                     bbox=(146.0, -38.0, 151.0, -33.0), aqua_outage=None)
    result = run_analysis(standardize_world(world), world["manifest"], AnalysisConfig())
    season = result.summary["seasonality"]
    assert 120 <= season["fire_year_start_doy"] <= 250          # the fire year starts mid-year
    usable = [f for f in season["fire_years"] if f["usable"]]
    assert len(usable) >= 10
    for f in usable:
        assert "/" in f["fire_year"]                             # labelled like 2015/16
        mid = pd.Timestamp(f["p50_date"])
        assert mid.month in (12, 1, 2)                           # midpoint near New Year, not day 365
        assert f["season_length_days"] < 200
    core = season["core_season_80pct"]
    assert core["start_doy"] > core["end_doy"]                   # wraps around the end of the year


def test_phenology_uses_count_percentiles():
    index = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    values = np.zeros(len(index))
    values[100:200] = 1.0                                        # 100 active days, one cell each
    rec = [r for r in cal.phenology(make_daily(index, values), 1) if r["fire_year"] == "2021"][0]
    assert rec["usable"]
    assert rec["p10_day"] == 109 and rec["p50_day"] == 149 and rec["p90_day"] == 189
    assert rec["season_length_days"] == 80


def test_fire_year_with_poor_coverage_is_not_used():
    index = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    values = np.ones(len(index))
    source = np.ones(len(index), dtype=int)
    source[:60] = 0                                              # 60 days without data
    daily = make_daily(index, np.where(source > 0, values, np.nan), source)
    rec = [r for r in cal.phenology(daily, 1) if r["fire_year"] == "2021"][0]
    assert not rec["usable"] and "coverage" in rec["why_not_usable"]


def monthly_frame(values_by_year, month=8, coverage=1.0):
    periods = pd.PeriodIndex([f"{y}-{month:02d}" for y in values_by_year], freq="M")
    return pd.DataFrame({"cells": list(values_by_year.values()), "coverage": coverage,
                         "year": [p.year for p in periods], "month": month}, index=periods)


def test_anomaly_is_relative_to_the_other_years_only():
    data = {y: 10.0 for y in range(2010, 2020)}
    data[2020] = 30.0
    out = an.monthly_anomalies(monthly_frame(data))
    row = out.loc["2020-08"]
    assert row["baseline_n"] == 10                              # 2020 itself is excluded
    assert row["baseline_median"] == 10.0
    assert row["anomaly_pct"] == pytest.approx(200.0)
    assert row["percentile"] == 100.0
    assert row["category"] == "exceptionally high"
    assert out.loc["2015-08", "category"] == "near normal"


def test_anomaly_refuses_when_data_are_insufficient():
    short = an.monthly_anomalies(monthly_frame({y: 10.0 for y in range(2017, 2021)}))
    assert (short["category"] == "baseline too short").all() and short["anomaly_pct"].isna().all()
    frame = monthly_frame({y: 10.0 for y in range(2010, 2021)})
    frame.loc["2020-08", "coverage"] = 0.5
    out = an.monthly_anomalies(frame)
    assert out.loc["2020-08", "category"] == "month coverage too low"
    assert out.loc["2019-08", "baseline_n"] == 9                # the poorly covered month is not a baseline


def test_anomaly_with_zero_median_reports_no_percentage():
    data = {y: 0.0 for y in range(2010, 2020)}
    data[2020] = 4.0
    row = an.monthly_anomalies(monthly_frame(data)).loc["2020-08"]
    assert np.isnan(row["anomaly_pct"]) and row["anomaly_abs"] == 4.0 and row["category"] == "exceptionally high"


def test_trend_needs_enough_years_and_recovers_a_known_slope():
    years = np.arange(2000, 2020)
    out = cal.trend(years, 100 + 2.0 * (years - 2000), "days")
    assert out["available"] and out["slope_per_year"] == pytest.approx(2.0) and out["significant_at_5pct"]
    assert "No cause is assigned" in out["interpretation"]
    assert not cal.trend(years[:5], np.arange(5.0), "days")["available"]


def test_units_and_wording_do_not_claim_energy_or_causes(analysis):
    text = str(analysis.summary["units"]) + str(analysis.summary["seasonality"]["definition"])
    assert "not an energy" in text
    assert "climate" not in str(analysis.summary).lower()
