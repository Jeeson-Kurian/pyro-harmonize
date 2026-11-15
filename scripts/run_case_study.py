"""
Reproducible case study: run the whole analysis and write a validation report.

    python scripts/run_case_study.py                       # real FIRMS files in data/firms
    python scripts/run_case_study.py --bbox -123,37,-120,40 --start 2012-02-01 --end 2024-12-31
    python scripts/run_case_study.py --demo --out docs/synthetic_selftest   # simulator self-test

Outputs (in --out, default docs/case_study):
    REPORT.md     human-readable validation report
    report.json   every number in the report, machine-readable
    daily.csv, monthly.csv   the harmonised record

The report states plainly whether it is based on NASA FIRMS data or on simulated data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import __version__                                              # noqa: E402
from engine.pipeline import (AnalysisConfig, export_frame, load_dataset,   # noqa: E402
                             modis_switch_off_test, run_analysis)


def _pct(v):
    return "n/a" if v is None else f"{v:+.1f} %"


def _num(v, digits=1):
    return "n/a" if v is None else f"{v:,.{digits}f}"


def _method_table(scores, forward, labels, selected):
    lines = ["| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, s in scores.items():
        if not s.get("available"):
            continue
        f = (forward or {}).get(key) or {}
        name = labels.get(key, key) + (" **(used)**" if key == selected else "")
        err = "n/a" if s["median_abs_pct_error"] is None else f"{s['median_abs_pct_error']:.1f} %"
        lines.append(f"| {name} | {_pct(s['total_bias_pct'])} | {err} | {_num(s['spearman_r'], 3)} | "
                     f"{_num(s['scaled_rmse'], 3)} | {_pct(f.get('total_bias_pct')) if f.get('available') else 'n/a'} |")
    return "\n".join(lines)


def observing_system_check(analysis):
    """
    Two checks of the observing system itself, from the data:
    1. median local solar time of daytime detections per platform and year
       (shows orbit drift of Terra and Aqua);
    2. per year, for cells seen by both a VIIRS platform and Aqua in daytime:
       Aqua FRP divided by VIIRS FRP, and the minutes between the two overpasses.
    """
    import pandas as pd
    from engine.matching import build_pairs
    d = analysis.detections
    if d.empty:
        return None
    day = d[d["slot"] == "day"]
    years = pd.DatetimeIndex(day["local_date"]).year
    times = day.groupby([day["platform"], years])["local_hour"].median().unstack()
    ratios = {}
    for target in ("NOAA20", "SNPP"):
        if target not in set(analysis.cells["platform"]) or "Aqua" not in set(analysis.cells["platform"]):
            continue
        pairs = build_pairs(analysis.cells, target, "Aqua", analysis.coverage)
        both = pairs[pairs["t_active"] & pairs["r_active"] & (pairs["slot"] == "day")
                     & (pairs["t_frp"] > 0) & (pairs["r_frp"] > 0)]
        if both.empty:
            continue
        g = both.groupby("year")
        ratios[target] = pd.DataFrame({"pairs": g.size(), "minutes_apart": g["dt_min"].median(),
                                       "aqua_over_viirs_frp": g["r_frp"].sum() / g["t_frp"].sum()})
    return {"overpass_time": times, "frp_ratio": ratios}


def _observing_section(check):
    if not check:
        return []
    def hhmm(h):
        if h != h:
            return "n/a"
        minutes = int(round(h * 60))
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    times = check["overpass_time"]
    years = list(times.columns)
    out = ["## Observing-system check", "",
           "Median local solar time of daytime detections, by platform and year. A change over the "
           "years means the satellite's orbit drifted, so it observes fires at a different time of day.", "",
           "| Platform | " + " | ".join(str(y) for y in years) + " |",
           "|---|" + "---:|" * len(years)]
    for platform, row in times.iterrows():
        out.append(f"| {platform} | " + " | ".join(hhmm(row[y]) for y in years) + " |")
    for target, table in check["frp_ratio"].items():
        out += ["", f"Daytime cells seen by both {target} and Aqua: Aqua FRP divided by {target} FRP, "
                    "and median minutes between the two overpasses.", "",
                "| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |", "|---:|---:|---:|---:|"]
        for year, r in table.iterrows():
            out.append(f"| {year} | {int(r.pairs):,} | {r.minutes_apart:.0f} | {r.aqua_over_viirs_frp:.2f} |")
    out += ["", "If the FRP ratio varies a lot between years, a single FRP conversion cannot hold for every "
                "year, and harmonised FRP should be read as less certain than harmonised cell counts.", ""]
    return out


def _switch_off_section(so) -> list:
    if not so:
        return []
    out = ["## MODIS switched off: does the record continue?", ""]
    if not so.get("available"):
        return out + [f"Not run: {so.get('reason')}", ""]
    c, f = so["scores"]["count"], so["scores"]["frp"]
    out += [f"Both MODIS instruments (Terra and Aqua) are removed from {so['cutoff']}. Every calibration is "
            f"refitted on {so['calibration_period'][0]} to {so['calibration_period'][1]} only, and the record is "
            f"continued from {' and '.join(so['viirs_platforms'])} VIIRS alone ({so['days_viirs_derived']:,} of "
            f"{so['days_after_cutoff']:,} days). The result is compared with what Aqua MODIS really observed in "
            f"{len(so['months'])} months, which the test never saw"
            + (f" ({so['months_excluded']} month(s) with a gap in either series left out)" if so["months_excluded"] else "")
            + ".", "",
            "| | Total difference from real Aqua MODIS | Median monthly error | Rank correlation |",
            "|---|---:|---:|---:|",
            f"| Raw VIIRS hot spots (mean of the VIIRS satellites) | {_pct(so['raw_viirs_hotspot_bias_pct'])} | | |",
            f"| Record continued from VIIRS, active cells | {_pct(c['total_bias_pct'])} | "
            f"{_num(c['median_abs_pct_error'])} % | {_num(c['spearman_r'], 3)} |"]
    if f.get("available"):
        out.append(f"| Record continued from VIIRS, FRP | {_pct(f['total_bias_pct'])} | "
                   f"{_num(f['median_abs_pct_error'])} % | {_num(f['spearman_r'], 3)} |")
    if so.get("inside_90pct_band_pct") is not None:
        out += ["", f"Real Aqua monthly values inside the stated 90 % band: {so['inside_90pct_band_pct']:.0f} % of months."]
    return out + [""]


def build_report(summary, sensitivity, radius, check=None, switch_off=None) -> str:
    s = summary
    out = ["# PyroHarmonize validation report" + (f": {s['label']}" if s.get("label") else ""), ""]
    if s["synthetic"]:
        out += ["> **SYNTHETIC SELF-TEST. The data in this report are simulated (engine/synthetic.py).**",
                "> It shows that the software recovers a known cross-sensor relationship. It is not",
                "> evidence about real satellites or real fires.", ""]
    else:
        out += ["Data: NASA FIRMS active-fire detections (see the table of platforms below).", ""]
    bbox = s["area"]["bbox_west_south_east_north"]
    out += [f"- Software version: {__version__}",
            f"- Area (west, south, east, north): {', '.join(f'{v:.3f}' for v in bbox)}",
            f"- Period: {s['period']['start']} to {s['period']['end']} ({s['period']['days']:,} days, local solar dates)",
            f"- Grid: {s['area']['cell_km']:g} km equal-area cells x day/night half-days",
            f"- Reference scale: {s['reference_platform']} MODIS",
            f"- Coverage basis: {s['coverage_basis']}", ""]

    out += ["## Platforms and coverage", "",
            "| Platform | Orbit | Detections used | Coverage | Days covered | Days with detections | Processing |",
            "|---|---|---:|---|---:|---:|---|"]
    for p in s["platforms"]:
        cov = f"{p['coverage_start']} to {p['coverage_end']}" if p["coverage_start"] else "none"
        levels = ", ".join(f"{k} {v:,}" for k, v in p["processing_levels"].items())
        out.append(f"| {p['label']} | {p['orbit']} | {p['detections']:,} | {cov} | {p['days_covered']:,} | "
                   f"{p['days_with_detections']:,} | {levels} |")
    q = s["quality_control"]
    out += ["", "## Quality control", "",
            f"{q['input_rows']:,} rows read, {q['output_rows']:,} used. Removed: {q['dropped_low_confidence']:,} "
            f"low-confidence, {q['dropped_non_vegetation_type']:,} non-vegetation hot spots, "
            f"{q['dropped_duplicates']:,} duplicates, {q['dropped_invalid_position_or_time']:,} without valid "
            f"position or time, {q['dropped_unknown_platform']:,} from an unidentified platform. "
            f"{q['rows_without_type_field']:,} rows had no `type` field and could not be screened for static sources.", ""]

    out += ["## Cross-sensor validation (held-out data)", ""]
    if not s["calibrations"]:
        out += ["No calibration was possible: " + " ".join(s["notes"]), ""]
    for target, c in s["calibrations"].items():
        label = next((p["label"] for p in s["platforms"] if p["platform"] == target), target)
        out += [f"### {label} converted to the Aqua MODIS scale", ""]
        if c["status"] != "calibrated":
            out += [f"**Not calibrated and not used in the harmonised record.** Reason: {c['reason']}.", ""]
            continue
        m = c["matching"]
        out += [f"- Test design: {c['validation_design']}",
                f"- Matched cell half-days: {m['both_active']:,} seen by both, {m['target_only']:,} only by {label}, "
                f"{m['reference_only']:,} only by Aqua MODIS, over {m['overlap_months']} months",
                f"- Median time between the two overpasses: {_num(m['median_time_difference_min'], 0)} min; "
                f"{_num(100 * m['share_within_15_min'], 0) if m['share_within_15_min'] is not None else 'n/a'} % within 15 min",
                f"- Selection rule: {c['selection_rule']}", "",
                "Active fire cells per month:", "",
                _method_table(c["cross_validation"]["count"], (c["forward_in_time_test"] or {}).get("count"),
                              c["method_labels"], c["selected_count_method"]), "",
                "Fire radiative power (monthly sum of overpass snapshots, MW):", "",
                _method_table(c["cross_validation"]["frp"], (c["forward_in_time_test"] or {}).get("frp"),
                              c["method_labels"], c["selected_frp_method"]), ""]
        fw = c["forward_in_time_test"]
        if fw:
            out += [f"Forward test: fitted on {fw['train_periods'][0]} to {fw['train_periods'][1]}, "
                    f"tested on {fw['test_periods'][0]} to {fw['test_periods'][1]}.", ""]
        d = c["diagnostics"]
        if d.get("frp_fit_all_pairs"):
            a, n15 = d["frp_fit_all_pairs"], d.get("frp_fit_within_15_min")
            out += [f"FRP log-log fit, all pairs: slope {a['slope']}, R2 {a['r2']} (n = {a['n']:,}). "
                    + (f"Pairs within 15 min only: slope {n15['slope']}, R2 {n15['r2']} (n = {n15['n']:,})."
                       if n15 else "Too few pairs within 15 min for a separate fit."), ""]
        iv = c["monthly_interval"]["count"]
        if iv:
            out += [f"Empirical 90 % band for monthly cells (square-root scale, from {iv['months']} held-out months): "
                    f"{iv['q05']:+.2f} to {iv['q95']:+.2f}.", ""]

    if sensitivity:
        out += ["## Sensitivity to the grid cell size", "",
                "The whole analysis repeated with other cell sizes. Stable results across sizes mean the "
                "conclusion does not hinge on the 10 km choice.", "",
                "| Cell size | Platform | Method used | Held-out total bias | Median monthly error |",
                "|---:|---|---|---:|---:|"]
        for row in sensitivity:
            out.append(f"| {row['cell_km']:g} km | {row['target']} | {row['method']} | {_pct(row['bias'])} | "
                       f"{'n/a' if row['error'] is None else str(row['error']) + ' %'} |")
        out.append("")
    if radius and radius.get("rows"):
        out += ["## Sensitivity of cluster counts to the clustering radius", "",
                f"Month with the most detections ({radius['sample_month']}; detections from "
                f"{radius['sample_period']}). Cluster counts change with the radius, "
                "which is why clusters are used for display only and not for the harmonised record.", "",
                "| Radius | Sensor | Detections | Clusters | Pixels per cluster |", "|---:|---|---:|---:|---:|"]
        for r in radius["rows"]:
            out.append(f"| {r['eps_km']:g} km | {r['sensor']} | {r['detections']:,} | {r['clusters']:,} | {r['pixels_per_cluster']} |")
        out.append("")

    out += _switch_off_section(switch_off)
    out += _observing_section(check)
    season = s["seasonality"]
    out += ["## Seasonality (observed, no cause assigned)", ""]
    core = season["core_season_80pct"]
    if core:
        out.append(f"- Shortest stretch holding 80 % of typical yearly activity: day {core['start_doy']} to day "
                   f"{core['end_doy']} ({core['length_days']} days)")
    for key, title in (("season_length", "Season length"), ("annual_total", "Yearly total")):
        t = season["trends"][key]
        if t["available"]:
            out.append(f"- {title}: {t['slope_per_decade']:+.2f} {t['unit']} per decade, 95 % interval "
                       f"{t['slope_95ci'][0] * 10:+.2f} to {t['slope_95ci'][1] * 10:+.2f}, p = {t['p_value']:.3f}, "
                       f"{t['n_years']} fire years")
        else:
            out.append(f"- {title}: not reported ({t['reason']})")
    out += ["", "## Notes and limits", ""] + [f"- {n}" for n in s["notes"]] + [
        "- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, "
        "or where cloud hid the ground.",
        "- FRP values are instantaneous power at overpass time. They are not fire radiative energy.",
        "- A result for one area does not validate the method for other regions or fire regimes.", ""]
    return "\n".join(out)


README_START = "<!-- CASE_STUDY:START -->"
README_END = "<!-- CASE_STUDY:END -->"


def readme_block(summary, report_path: str = "docs/case_study/REPORT.md") -> str:
    """Short real-data result for one region, built only from numbers in the report."""
    s = summary
    bbox = ", ".join(f"{v:g}" for v in s["area"]["bbox_west_south_east_north"])
    label = s.get("label") or f"Area {bbox}"
    lines = [f"**{label}** (west, south, east, north: {bbox}). Period: {s['period']['start']} to "
             f"{s['period']['end']}. Data: NASA FIRMS, {sum(p['detections'] for p in s['platforms']):,} "
             f"detections after quality control. Full report: [{report_path}]({report_path}).", "",
             "| Platform compared with Aqua MODIS (held-out months) | Raw hot spots | Common grid only | "
             "After harmonisation | Median monthly error | Forward-in-time test | Method used |",
             "|---|---:|---:|---:|---:|---:|---|"]
    rows = 0
    for target, c in s["calibrations"].items():
        label = next((p["label"] for p in s["platforms"] if p["platform"] == target), target)
        if c["status"] != "calibrated":
            lines.append(f"| {label} | not calibrated: {c['reason']} | | | | | |")
            continue
        cv = c["cross_validation"]["count"]
        used = cv[c["selected_count_method"]]
        fw = ((c["forward_in_time_test"] or {}).get("count") or {}).get(c["selected_count_method"]) or {}
        err = "n/a" if used["median_abs_pct_error"] is None else f"{used['median_abs_pct_error']:.1f} %"
        lines.append(f"| {label} ({used['months']} months) | {_pct(cv['raw_hotspots']['total_bias_pct'])} | "
                     f"{_pct(cv['gridded_cells']['total_bias_pct'])} | {_pct(used['total_bias_pct'])} | {err} | "
                     f"{_pct(fw.get('total_bias_pct')) if fw.get('available') else 'n/a'} | "
                     f"{c['method_labels'][c['selected_count_method']]} |")
        rows += 1
    if not s["calibrations"]:
        lines.append("| (no second platform could be compared with Aqua MODIS in this selection) | | | | | | |")
    so = s.get("modis_switch_off") or {}
    if so.get("available"):
        c = so["scores"]["count"]
        f = so["scores"]["frp"]
        lines += ["", f"MODIS switched off from {so['cutoff']} (calibration on earlier years only): raw VIIRS hot spots "
                      f"{_pct(so['raw_viirs_hotspot_bias_pct'])}; record continued from VIIRS {_pct(c['total_bias_pct'])} "
                      f"against what Aqua MODIS really observed, median monthly error {_num(c['median_abs_pct_error'])} %, "
                      f"{so['inside_90pct_band_pct']:.0f} % of months inside the 90 % band"
                      + (f"; FRP {_pct(f['total_bias_pct'])}." if f.get("available") else ".")]
    return "\n".join(lines)


def readme_block_all(root: str) -> str:
    """README result for every case study in docs/ (docs/case_study and docs/case_study_<name>)."""
    import glob
    paths = sorted(glob.glob(os.path.join(root, "docs", "case_study*", "report.json")),
                   key=lambda p: (os.path.basename(os.path.dirname(p)) != "case_study", p))
    blocks = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if summary.get("synthetic"):
            continue
        rel = os.path.relpath(os.path.join(os.path.dirname(path), "REPORT.md"), root).replace(os.sep, "/")
        blocks.append(readme_block(summary, rel))
    if not blocks:
        return ""
    note = ("Percentages are total differences from what Aqua MODIS reported in months that were not used for "
            "fitting. " + ("Each region was fitted and tested on its own data." if len(blocks) > 1 else
                           "This is one area; it does not validate the method elsewhere."))
    return "\n\n".join(blocks) + "\n\n" + note


def update_readme(path: str, block: str) -> bool:
    """Replace the text between the CASE_STUDY markers. Returns False if the markers are missing."""
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    if README_START not in text or README_END not in text:
        return False
    head, rest = text.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(head + README_START + "\n" + block + "\n" + README_END + tail)
    return True


def _join_bbox(argv):
    """Let '--bbox -9.6,36.9,-6.1,42.2' work: argparse reads a value that starts with '-' as an option."""
    argv = list(sys.argv[1:] if argv is None else argv)
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--bbox" and i + 1 < len(argv):
            out.append("--bbox=" + argv[i + 1])
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyroHarmonize case study and write a validation report.")
    parser.add_argument("--data-dir", default=None, help="folder with FIRMS CSV files (default data/firms)")
    parser.add_argument("--demo", action="store_true", help="use the synthetic simulator instead of real files")
    parser.add_argument("--bbox", default=None, help="west,south,east,north")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--cell-km", type=float, default=10.0)
    parser.add_argument("--out", default=os.path.join("docs", "case_study"))
    parser.add_argument("--no-sensitivity", action="store_true", help="skip the 5 / 25 km repeat runs")
    parser.add_argument("--label", default=None, help="name of the area for the report, e.g. 'Portugal'")
    parser.add_argument("--update-readme", action="store_true",
                        help="write the real-data result into README.md (never done for synthetic data)")
    args = parser.parse_args(_join_bbox(argv))

    detections, manifest, info = load_dataset(args.data_dir, force_synthetic=args.demo)
    if info["mode"] == "synthetic" and not args.demo:
        print("No FIRMS files found. Download real data first (data/download_nasa_firms.py) or pass --demo "
              "to run the simulator self-test.", file=sys.stderr)
        return 2
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    config = AnalysisConfig(bbox=bbox, start=args.start, end=args.end, cell_km=args.cell_km)
    analysis = run_analysis(detections, manifest, config, info)
    if analysis.summary.get("empty"):
        print(analysis.summary["message"], file=sys.stderr)
        return 1
    if args.label:
        analysis.summary["label"] = args.label

    sensitivity = []
    if not args.no_sensitivity:
        for cell_km in sorted({5.0, args.cell_km, 25.0}):
            run = analysis if cell_km == args.cell_km else run_analysis(
                detections, manifest, replace(config, cell_km=cell_km), info)
            for target, c in run.summary["calibrations"].items():
                if c["status"] != "calibrated":
                    continue
                score = c["cross_validation"]["count"][c["selected_count_method"]]
                sensitivity.append({"cell_km": cell_km, "target": target,
                                    "method": c["method_labels"][c["selected_count_method"]],
                                    "bias": score["total_bias_pct"], "error": score["median_abs_pct_error"]})
    radius = analysis.radius_sensitivity()

    os.makedirs(args.out, exist_ok=True)
    check = observing_system_check(analysis)
    switch_off = modis_switch_off_test(detections, manifest, analysis)
    report = build_report(analysis.summary, sensitivity, radius, check, switch_off)
    with open(os.path.join(args.out, "REPORT.md"), "w", encoding="utf-8") as handle:
        handle.write(report)
    slim = {k: v for k, v in analysis.summary.items() if k != "calendar"}
    slim["cell_size_sensitivity"] = sensitivity
    slim["radius_sensitivity"] = radius
    slim["modis_switch_off"] = {k: v for k, v in switch_off.items() if k != "calendar"}
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(slim, handle, indent=1)
    label = "SYNTHETIC - not satellite data" if analysis.summary["synthetic"] else "NASA FIRMS"
    for kind in ("daily", "monthly"):
        frame = export_frame(analysis, kind)
        frame.insert(0, "data_mode", label)
        frame.to_csv(os.path.join(args.out, f"{kind}.csv"), index=False)
    print(f"Wrote {args.out}/REPORT.md, report.json, daily.csv, monthly.csv")
    if args.update_readme:
        readme = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
        if analysis.summary["synthetic"]:
            print("README not changed: synthetic results are never written into the real-data section.")
        elif update_readme(readme, readme_block_all(os.path.dirname(readme))):
            print("README.md updated with the real-data result.")
        else:
            print("README.md has no CASE_STUDY markers; it was not changed.")
    head = analysis.summary["headline_validation"]
    if head:
        print(f"{head['target_label']} -> Aqua MODIS scale, {head['held_out_months']} held-out months: raw hot-spot "
              f"difference {_pct(head['raw_hotspot_bias_pct'])}, after harmonisation {_pct(head['harmonised_bias_pct'])}, "
              f"median monthly error {head['harmonised_median_abs_pct_error']} %.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
