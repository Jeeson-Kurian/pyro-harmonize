"""
Does the harmonisation do what it claims? Tested on simulated worlds with a known truth.

The simulator (engine/synthetic.py) is independent of the harmoniser: it produces
FIRMS-layout tables from fires, pixel footprints, detection limits, cloud and orbits.
These tests show the code is correct and self-consistent. They are NOT evidence about
real satellites; that requires the real-data case study (scripts/run_case_study.py).
"""

import numpy as np
import pandas as pd
import pytest

from engine.pipeline import AnalysisConfig, run_analysis
from engine.synthetic import generate_synthetic_firms
from tests.conftest import standardize_world


def test_harmonised_beats_every_baseline_on_held_out_years(analysis):
    cal = analysis.summary["calibrations"]["SNPP"]
    assert cal["status"] == "calibrated"
    assert "leave-years-out" in cal["validation_design"]
    cv = cal["cross_validation"]["count"]
    chosen = cv[cal["selected_count_method"]]
    assert abs(cv["raw_hotspots"]["total_bias_pct"]) > 100          # raw counts are not comparable
    assert abs(cv["gridded_cells"]["total_bias_pct"]) > 50          # gridding alone is not enough
    assert abs(chosen["total_bias_pct"]) < 5
    assert chosen["median_abs_pct_error"] < 15
    assert chosen["scaled_rmse"] <= cv["gridded_cells"]["scaled_rmse"]
    assert chosen["scaled_rmse"] <= cv["ratio_scaled"]["scaled_rmse"] * 1.0001


def test_forward_in_time_test_also_holds(analysis):
    cal = analysis.summary["calibrations"]["SNPP"]
    fwd = cal["forward_in_time_test"]
    assert fwd is not None and fwd["train_periods"][1] < fwd["test_periods"][0]
    assert abs(fwd["count"][cal["selected_count_method"]]["total_bias_pct"]) < 10
    assert abs(fwd["frp"][cal["selected_frp_method"]]["total_bias_pct"]) < 15


def test_blind_test_viirs_reproduces_hidden_aqua_record(world, detections, analysis):
    """
    Hide Aqua completely after 2019 (as if the mission had ended), harmonise, and compare
    the VIIRS-derived record 2020-2023 with what Aqua really reported in the full data.
    """
    cutoff = "2019-12-31"
    hidden = detections[~((detections["platform"] == "Aqua") & (detections["acq_date"] > cutoff))]
    manifest = dict(world["manifest"])
    manifest["platform_gaps"] = {"Aqua": [["2020-01-01", "2023-12-31"]]}
    blind = run_analysis(hidden, manifest, AnalysisConfig())

    late = blind.daily.loc["2020-01-03":"2023-12-28"]
    assert set(late["source"].unique()) == {2}                     # all VIIRS-derived, none observed
    truth = analysis.daily.loc[late.index, "Aqua_cells"]
    predicted = late["harmonized_cells"]
    monthly_truth = truth.groupby(truth.index.to_period("M")).sum()
    monthly_pred = predicted.groupby(predicted.index.to_period("M")).sum()

    total_bias = 100 * (monthly_pred.sum() - monthly_truth.sum()) / monthly_truth.sum()
    assert abs(total_bias) < 8
    assert np.corrcoef(monthly_pred, monthly_truth)[0, 1] > 0.97
    # the 90 % interval should contain the hidden truth in most months
    m = blind.monthly.loc[monthly_truth.index.min():monthly_truth.index.max()]
    inside = (monthly_truth.values >= m["cells_low"].values - 1e-9) & (monthly_truth.values <= m["cells_high"].values + 1e-9)
    assert inside.mean() > 0.75
    # naive splicing of raw VIIRS hot spots would have been wrong by a large factor
    raw_viirs = blind.daily.loc[late.index, "SNPP_hotspots"].sum()
    raw_aqua = analysis.daily.loc[late.index, "Aqua_hotspots"].sum()
    assert raw_viirs / raw_aqua > 1.5


def test_more_satellites_do_not_mean_more_fire(world, detections):
    """Adding NOAA-20 must not raise the VIIRS-derived level (platforms are averaged, not added)."""
    manifest = dict(world["manifest"])
    manifest["platform_gaps"] = {"Aqua": [["2020-01-01", "2023-12-31"]]}
    no_aqua_late = detections[~((detections["platform"] == "Aqua") & (detections["acq_date"] > "2019-12-31"))]
    both = run_analysis(no_aqua_late, manifest, AnalysisConfig())
    snpp_only = run_analysis(no_aqua_late[no_aqua_late["platform"] != "NOAA20"], manifest, AnalysisConfig())
    a = both.daily.loc["2020-02-01":"2023-11-30", "harmonized_cells"].sum()
    b = snpp_only.daily.loc["2020-02-01":"2023-11-30", "harmonized_cells"].sum()
    assert a == pytest.approx(b, rel=0.08)


def test_no_trend_is_invented(analysis):
    """The simulated world has no trend. The harmonised record must not show a significant one."""
    trends = analysis.summary["seasonality"]["trends"]
    assert trends["season_length"]["available"]
    assert not trends["season_length"]["significant_at_5pct"]
    low, high = trends["annual_total"]["slope_95ci"]
    assert low <= 0 <= high


def test_a_real_trend_is_recovered():
    world = generate_synthetic_firms(start="2008-01-01", end="2023-12-31", seed=5, trend_per_year=0.06,
                                     aqua_outage=None)
    result = run_analysis(standardize_world(world), world["manifest"], AnalysisConfig())
    t = result.summary["seasonality"]["trends"]["annual_total"]
    assert t["available"] and t["slope_per_year"] > 0 and t["significant_at_5pct"]


def test_too_little_overlap_gives_no_numbers_instead_of_invented_ones():
    world = generate_synthetic_firms(start="2012-01-01", end="2012-04-30", seed=3, fires_per_year=40,
                                     season_peak_doy=60, aqua_outage=None)
    result = run_analysis(standardize_world(world), world["manifest"], AnalysisConfig())
    cal = result.summary["calibrations"]["SNPP"]
    assert cal["status"] == "not_calibrated"
    assert "need" in cal["reason"]
    assert cal["cross_validation"] == {} and cal["selected_count_method"] is None
    assert "fitted_parameters" not in cal
    assert result.summary["headline_validation"] is None or result.summary["headline_validation"]["target"] != "SNPP"
    assert "SNPP_aqua_equivalent_cells" not in result.daily.columns    # not used in the record


def test_without_the_reference_platform_no_harmonised_record_is_claimed(world, detections):
    no_aqua = detections[detections["platform"] != "Aqua"]
    result = run_analysis(no_aqua, None, AnalysisConfig())
    assert result.summary["calibrations"] == {}
    assert result.daily["harmonized_cells"].isna().all()
    assert (result.daily["source"] == 0).all()
    assert any("reference platform" in n for n in result.summary["notes"])
    assert result.daily["viirs_hotspots"].notna().any()             # raw counts still available


def test_days_outside_coverage_are_missing_not_zero(analysis):
    daily = analysis.daily
    # S-NPP data start on 2012-01-20: before that its columns are missing, not zero
    assert daily.loc[:"2012-01-19", "SNPP_hotspots"].isna().all()
    assert daily.loc["2012-03-01":"2012-12-31", "SNPP_hotspots"].notna().all()
    assert daily.loc[:"2012-01-19", "viirs_hotspots"].isna().all()
    cal = analysis.summary["calendar"]
    row_2011 = cal["viirs_hotspots"][cal["years"].index(2011)]
    assert all(v is None for v in row_2011)


def test_sensor_outage_is_filled_from_viirs_and_flagged():
    world = generate_synthetic_firms(start="2012-06-01", end="2020-12-31", seed=4,
                                     aqua_outage=("2016-08-10", "2016-09-05"))
    result = run_analysis(standardize_world(world), world["manifest"], AnalysisConfig())
    gap = result.daily.loc["2016-08-11":"2016-09-04"]
    assert (gap["source"] == 2).all()                               # VIIRS-derived, not zero, not Aqua
    assert gap["Aqua_cells"].isna().all()
    assert gap["harmonized_cells"].sum() > 0
    assert (result.daily.loc["2016-07-01":"2016-08-08", "source"] == 1).all()


def test_selection_by_area_and_period(detections, world):
    cfg = AnalysisConfig(bbox=(-123.0, 37.0, -120.0, 40.0), start="2014-01-01", end="2019-12-31")
    result = run_analysis(detections, world["manifest"], cfg)
    assert result.summary["period"]["start"] == "2014-01-01"
    assert result.summary["period"]["end"] == "2019-12-31"
    d = result.detections
    assert d["longitude"].between(-123.0, -120.0).all() and d["latitude"].between(37.0, 40.0).all()
    with pytest.raises(ValueError):
        run_analysis(detections, world["manifest"], AnalysisConfig(bbox=(10.0, 0.0, 5.0, 1.0)))
    empty = run_analysis(detections, None, AnalysisConfig(bbox=(100.0, 0.0, 101.0, 1.0)))
    assert empty.summary["empty"] is True


def test_area_outside_the_loaded_data_is_never_reported_as_zero_fire(world, detections):
    outside = run_analysis(detections, world["manifest"], AnalysisConfig(bbox=(10.0, 10.0, 11.0, 11.0)))
    assert outside.summary["empty"] is True and "outside" in outside.summary["message"]
    partly = run_analysis(detections, world["manifest"], AnalysisConfig(bbox=(-121.0, 39.0, -110.0, 50.0)))
    assert partly.summary["area"]["bbox_west_south_east_north"] == [-121.0, 39.0, -119.0, 41.0]
    assert any("clipped" in n for n in partly.summary["notes"])


def test_quiet_period_inside_coverage_is_zero_not_missing(world, detections):
    quiet = run_analysis(detections, world["manifest"], AnalysisConfig(start="2015-01-05", end="2015-02-20"))
    d = quiet.daily
    assert (d["source"] == 1).all()                    # Aqua delivered data on every day
    assert d["harmonized_cells"].notna().all()
    assert d["harmonized_frp_mw"].notna().all()
    assert d["harmonized_cells"].sum() < 5             # outside the simulated fire season


def test_map_handles_a_busy_window_without_refusing(analysis):
    from engine.pipeline import MAX_MAP_DETECTIONS
    assert MAX_MAP_DETECTIONS >= 300_000
    result = analysis.clusters("2008-01-01", "2023-12-31", 2.0)   # the whole simulated record
    assert "error" not in result and result["total_clusters"] >= result["shown"] > 0


def test_modis_switched_off_record_continues_from_viirs_without_seeing_aqua(world, detections, analysis):
    from engine.pipeline import modis_switch_off_test
    result = modis_switch_off_test(detections, world["manifest"], analysis)
    assert result["available"] and result["cutoff"] == "2022-01-01"
    assert result["withheld_period"] == ["2022-01-01", "2023-12-31"]
    # every day after the cut-off is VIIRS-derived: no MODIS value leaks into the continuation
    assert result["days_viirs_derived"] == result["days_after_cutoff"] == 730
    years = result["calendar"]["years"]
    for row in (years.index(2022), years.index(2023)):
        assert {v for v in result["calendar"]["source"][row] if v is not None} == {2}
    # the calibrations behind it were fitted on months before the cut-off only
    assert all(c["trained_on_months"] <= 14 * 12 for c in result["calibrations"].values())
    count = result["scores"]["count"]
    assert abs(count["total_bias_pct"]) < 10 and count["spearman_r"] > 0.9
    assert result["raw_viirs_hotspot_bias_pct"] > 100          # raw counts would not continue the record
    assert len(result["months"]) == len(result["aqua_observed_cells"]) == len(result["continued_cells"]) == 24


def test_switch_off_needs_enough_years(world, detections):
    from engine.pipeline import AnalysisConfig, modis_switch_off_test, run_analysis
    short = run_analysis(detections, world["manifest"], AnalysisConfig(start="2021-01-01", end="2023-12-31"))
    result = modis_switch_off_test(detections, world["manifest"], short)
    assert result["available"] is False and "four calendar years" in result["reason"]


def test_calibration_transfer_scores_a_borrowed_calibration_against_real_aqua(analysis):
    from engine.pipeline import calibration_transfer_test
    result = calibration_transfer_test(analysis, analysis, "NOAA20")
    assert result["available"] and result["months"] > 12
    assert result["raw_hotspot_bias_pct"] > 100                  # raw counts are far off
    assert abs(result["count"]["total_bias_pct"]) < 10            # applied in its own region: close to Aqua
    assert result["own_region_held_out"]["count"]["median_abs_pct_error"] is not None
    assert calibration_transfer_test(analysis, analysis, "NOAA21")["available"] is False
