# PyroHarmonize: method, validation and limits

This document describes exactly what the code in `engine/` does, why, and what it
cannot do. Where the text says "validated", it means "scored on data that were
not used for fitting", and the numbers come out of `scripts/run_case_study.py`.

## 1. The problem

MODIS (Terra since November 2000, Aqua since July 2002) and VIIRS (Suomi-NPP
2012 to 2 November 2026, NOAA-20 since 2018, NOAA-21 since 2023) all report
active-fire "hot spots", but their numbers are not comparable:

| | MODIS | VIIRS 375 m |
|---|---|---|
| Nominal pixel | 1 km, growing to about 2 x 4.8 km at the swath edge | 375 m, growing much less |
| One fire front | one or a few pixels | many pixels |
| Small or cool fires | often below the detection limit | more often detected |
| Platforms at once | 2 | up to 3 |
| Overpass (local time) | Terra about 10:30 / 22:30, Aqua about 13:30 / 01:30 | about 13:30 / 01:30 |

A plain count of hot spots therefore jumps when VIIRS data begin, and jumps again
with each added satellite, without any change in burning. Suomi-NPP stopped
delivering data on 2 November 2026 and Terra and Aqua are near the end of their
missions, so a record that continues on NOAA-20 and NOAA-21 has to be tied to
the MODIS record explicitly.

## 2. Data and quality control (`engine/data_loader.py`)

Input: NASA FIRMS CSV files, either from the area API (`data/download_nasa_firms.py`)
or from the FIRMS archive download tool. Standard-processing sources (`*_SP`) are the
default because NASA recommends them for historical analysis; near-real-time
sources work too and are labelled as such in every output.

Screening rules, each reported with the number of rows it removed:

1. no valid position or UTC time: removed (cannot be placed);
2. unidentified platform: removed (cannot be assigned an orbit);
3. exact duplicates of platform, time and position: removed;
4. `type` 1, 2 or 3 (volcano, other static land source, offshore): removed. The
   field exists only in standard-processing data, so near-real-time rows cannot be
   screened this way; the count of unscreened rows is reported;
5. low confidence (MODIS below 30 %, VIIRS class `l`): removed by default;
6. FRP that is missing or not positive: the detection is kept, the FRP is missing.

Nothing is filled in. A missing FRP or time stays missing.

`scan` and `track` in FIRMS files are pixel dimensions in km, not angles. They are
kept as `scan_km` and `track_km` and used as a proxy for view geometry.

## 3. A common unit (`engine/gridding.py`)

Every platform is reduced to the same unit before any comparison:

> **active fire cell** = one grid cell x one local half-day x one platform, with at
> least one detection.

- **Grid.** Latitude bands are `cell_km` tall (default 10 km). Inside a band the
  longitude step is widened by 1/cos(latitude), so a cell is about 10 x 10 km at
  any latitude. 10 km is wider than the largest MODIS pixel, so both sensors
  usually place the same fire in the same cell.
- **Half-day.** Local solar time = UTC + longitude / 15 h. Day slot 06:00 to
  18:00, night slot 18:00 to 06:00 (labelled with the date it ends on). Bucketing
  by UTC date would split a single overpass in regions where it happens near 00:00 UTC.
- **Cell FRP.** Sum of pixel FRP in the cell divided by the number of overpasses that
  contributed. This is the mean instantaneous radiative **power** (MW) at overpass
  time. It is not fire radiative energy; no time integration is attempted.

All distances use the haversine formula with a mean Earth radius of 6371.0088 km.

## 4. Coverage: "no fire reported" is not "no data" (`engine/matching.py`)

For each platform and local date the code decides whether the platform was
delivering data:

1. the platform's FIRMS availability window;
2. the download manifest: the date intervals that were requested **and returned
   successfully**. Failed requests are gaps;
3. without a manifest, the span between the first and last detection in the file
   (a weaker assumption, shown as such in the app);
4. known outages listed under `platform_gaps` in the manifest are removed.

Days outside coverage are missing in every table, chart and export. They are
never zero.

What coverage cannot capture: cloud, smoke and, near the equator, the gaps between
MODIS swaths. Hot-spot files do not record where a satellite looked and saw
nothing. This is the main limit of any method based on FIRMS point data.

## 5. Reference scale and matching

The harmonised record is expressed on the **Aqua MODIS** scale ("what Aqua MODIS
would have reported"):

- a coarse sensor cannot be upgraded to see fires it missed between 2002 and
  2011, but a fine sensor can be degraded to the coarse one;
- Aqua, Suomi-NPP, NOAA-20 and NOAA-21 share the early-afternoon orbit, so they
  sample the same part of the fire diurnal cycle. Terra does not.

For a target platform T (for example NOAA-20) and the reference R (Aqua), a
**pair** is a (cell, half-day) in which T and/or R was active, on a date covered by
both. Each pair records whether each platform was active, its pixel count, FRP
and mean pixel size, and, when both were active, the real time difference between
the two acquisitions. The report gives the number of pairs in each class and the
distribution of time differences, and repeats the FRP fit on the subset within
15 minutes.

Because the estimand is "what Aqua reports", effects such as the Aqua swath gaps
and the few tens of minutes between overpasses are part of the target and are
learned from the pairs rather than assumed away.

## 6. Calibration (`engine/harmonizer.py`)

For the cells where the target is active, with features x = (log10 FRP, log10
pixel count, night flag):

```
E[ Aqua active cells ]  =  (1 + rho)      * sum over target-active cells of  p(x)
E[ Aqua FRP          ]  =  (1 + rho_frp)  * sum over target-active cells of  p(x) * g(x)
```

- `p(x)`: probability that Aqua also reports the cell (logistic regression);
- `g(x)`: expected Aqua FRP given that both report it. Fitted in log-log space and
  transformed back with Duan's smearing factor so that the mean is not biased.
  Two versions: ordinary least squares on log FRP only, and ridge regression that
  also uses pixel count, night flag and pixel size;
- `rho`, `rho_frp`: Aqua-active cells (and their FRP) that the target did not
  report, relative to the shared ones, estimated separately for day and night.

Candidates, from simplest to most complex:

| Quantity | Candidates |
|---|---|
| Active cells | common grid only; grid + one constant ratio; grid + detection model |
| FRP | as reported; one constant ratio; detection model x log-log fit; detection model x ridge |

Raw hot-spot counts are scored as well, as the "do nothing" reference.

## 7. Validation and method selection

- **Leave-years-out cross-validation.** Pairs are grouped by year (by month if
  fewer than three overlap years exist, flagged as a weaker test). Up to five
  folds. Every candidate is fitted on the training years and predicts the held-out
  years. Predictions are summed by month and compared with what Aqua reported.
- **Forward-in-time test.** Fit on the earliest 70 % of the overlap, predict the
  rest. This is the situation the tool will be used in after MODIS ends.
- **Scores.** Total bias, median absolute monthly error, Spearman rank
  correlation, and a scaled RMSE (square-root scale for counts, log scale for FRP,
  so that a few extreme months do not decide everything).
- **Selection rule.** The simplest candidate whose held-out scaled RMSE is within
  2 % of the best is used. If a baseline wins, the baseline is used and the app
  says so.
- **Minimum evidence.** At least 200 target-active cells, 50 shared cells and 6
  overlap months. Below that the platform is reported as "not calibrated" with
  the reason, and it is left out of the harmonised record. There are no default or
  fallback coefficients anywhere in the code.

## 8. Building the harmonised record (`engine/pipeline.py`)

Per local date, in this order, with the source of every day kept:

1. **Aqua MODIS observed** (the reference itself);
2. **VIIRS-derived**: the mean of the Aqua-equivalent estimates of all calibrated
   VIIRS platforms delivering data that day. Platforms are averaged, never added,
   so more satellites cannot look like more fire;
3. **Terra-derived**: used only where 1 and 2 are absent (before July 2002 and in
   Aqua gaps before 2012). Terra observes about three hours earlier, so this is a
   statistical conversion across the diurnal cycle and the least certain part of
   the record;
4. otherwise **no data**.

**Uncertainty.** For sensor-converted months, a 90 % band is taken from the
out-of-fold monthly errors of the selected method (5th and 95th percentile of the
error on the square-root scale for counts, log scale for FRP). It is an empirical
band from held-out months of the same area, it needs at least 12 such months, and
it is not a formal confidence interval.

## 9. Calendar, seasonality, anomalies

- **Calendar.** Year x 366 days. Day 366 exists only in leap years.
- **Fire years.** Twelve-month windows that start in the middle of the quietest
  61-day stretch of the climatology, so a season crossing New Year is not cut.
- **Season timing.** Days by which 10 %, 50 % and 90 % of the fire year's
  harmonised active cells had accumulated. These are count-based percentiles. A
  fire year needs 90 % coverage and at least 20 cells.
- **Trends.** Theil-Sen slope with 95 % interval and the Mann-Kendall test, only
  with 8 or more usable fire years. Reported as observed change. No cause is
  assigned, and the record mixes sources, which the app shows.
- **Monthly anomaly.** A month is compared with the same calendar month in the
  other years (leave-one-out): median, quartiles, percentile rank, robust z.
  It requires 80 % coverage of the month and at least five baseline years;
  otherwise the answer is "not enough data".
- **Critical periods.** Weekly medians and upper quartiles across years; weeks
  reaching half of the peak week's median; the shortest stretch that holds 80 %
  of typical yearly activity.

## 10. Hot-spot clusters (`engine/spatial_cluster.py`)

For the map only. Detections of one platform in one overpass are grouped by
DBSCAN with the haversine metric (`min_samples = 1`, which is single-linkage
grouping at distance eps). A cluster is a description of what one sensor saw at
one moment, not a confirmed fire. The app reports how the number of clusters
changes for eps = 0.5, 1, 2 and 5 km; because it changes a lot, clusters are not
used for the harmonised record.

## 11. Limits

- **One area is not a global validation.** Detection limits and FRP relations
  differ between biomes, fire sizes and view angles. Every area needs its own run.
- **Observation opportunity is only partly known** (section 4).
- **Orbit drift.** Terra and Aqua have been drifting from their original orbits
  in recent years, which shifts their local observation time. A calibration fitted
  on the whole overlap averages over this. The analysed period can be restricted
  with `--start` and `--end` to check how much the result depends on it.
- **FRP.** VIIRS 375 m FRP is retrieved with the help of 750 m data and MODIS FRP
  depends strongly on view angle (Li et al., 2018). FRP comparisons carry more
  uncertainty than cell counts.
- **Cell boundaries.** A fire on a cell edge can fall in different cells for the
  two sensors. The effect is the same at fit time and at apply time, and the
  case-study report repeats the analysis for 5, 10 and 25 km cells.
- **Near-real-time data** lack the `type` screening and have less accurate
  geolocation for Aqua.
- **Not for operational fire-fighting decisions.**

## 12. Sources

NASA pages (checked on 14 November 2026):

- FIRMS area API, sources and DAY_RANGE: <https://firms.modaps.eosdis.nasa.gov/api/area/>
- Attribute definitions for MODIS and VIIRS active-fire data:
  <https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs>
- FIRMS FAQ (NRT versus standard data, confidence):
  <https://www.earthdata.nasa.gov/data/tools/firms/faq>
- MODIS layer description with Terra and Aqua coverage dates:
  <https://firms.modaps.eosdis.nasa.gov/descriptions/FIRMS_MODIS_Firehotspots.html>
- End of Suomi-NPP data delivery (2 November 2026):
  <https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know>
- Terra and Aqua orbit drift:
  <https://www.earthdata.nasa.gov/news/feature-articles/viirs-instruments-become-more-essential-terra-aqua-drift-traditional-orbits>

Literature:

- Giglio, L., Schroeder, W., Justice, C. O. (2016). The collection 6 MODIS active fire
  detection algorithm and fire products. Remote Sensing of Environment, 178, 31-41.
  doi:10.1016/j.rse.2016.02.054
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014). The New VIIRS 375 m active
  fire detection data product: Algorithm description and initial assessment. Remote
  Sensing of Environment, 143, 85-96. doi:10.1016/j.rse.2013.12.008
- Li, F., Zhang, X., Kondragunta, S., Csiszar, I. (2018). Comparison of Fire Radiative
  Power Estimates From VIIRS and MODIS Observations. Journal of Geophysical Research:
  Atmospheres, 123(9), 4545-4563. doi:10.1029/2017JD027823
- Li, F., Zhang, X., Kondragunta, S. (2020). Biomass Burning in Africa: An Investigation
  of Fire Radiative Power Missed by MODIS Using the 375 m VIIRS Active Fire Product.
  Remote Sensing, 12(10), 1561. doi:10.3390/rs12101561
- Fire Radiative Power Correction and Spatiotemporal Fusion Based on MYD14 and
  VNP14IMG (2026). Remote Sensing, 18, 1650. doi:10.3390/rs18101650
