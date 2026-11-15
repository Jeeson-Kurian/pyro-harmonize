# What should a fire calendar count when the satellite changes?

The calendar estimates how many grid cells Aqua MODIS would have reported as active. Agreement with Aqua therefore measures continuity with a historical instrument, not truth: two instruments can agree and still miss a fire under cloud. The regional results cover April 2018 to December 2024, and each region was calibrated and tested on its own data. Every number below links to the report it comes from.

## How these decisions were made

The first version ([`60ddc6c`](https://github.com/Jeeson-Kurian/pyro-harmonize/commit/60ddc6c), 14 November) counted DBSCAN "fire complexes" and converted VIIRS to MODIS with a point-inflation ratio, with a hard-coded default of 3.65. On 14 November, Jeeson Kurian asked ChatGPT to review the project from the perspective of a technical reviewer and a NASA Space Apps judge. ChatGPT wrote the audit and flagged issues including how observations were matched across sensors and how the models were validated. Jeeson then asked Claude to address the limitations in the audit he uploaded. Claude implemented the redesign in [`694a04b`](https://github.com/Jeeson-Kurian/pyro-harmonize/commit/694a04b) ("Scientific core v2"), which contains the three decisions below. It is not recorded whether the uploaded audit is exactly the version Jeeson reviewed, or where each decision was first proposed. The sections below therefore describe what the code does and what the evidence shows, without assigning the individual choices to a person.

## 1. The observation unit: one active cell per platform and local half-day

**Behaviour.** Detections are placed in 10 km equal-area cells and local solar half-days (day 06:00–18:00, night 18:00–06:00, labelled with the date the night ends). A cell is active for a platform in a half-day if that platform reported at least one detection there. The pixel count is kept as a model input, and cell FRP is the summed pixel FRP divided by the number of overpasses, the mean per overpass ([`gridding.py`](../engine/gridding.py)). If VIIRS reports eight hot spots along one front and Aqua reports one in the same cell and afternoon, each platform contributes one active cell, and the detection model still sees that VIIRS had eight pixels.

**What it replaced.** The DBSCAN complexes of the first version remain only on the map. The reports state that clusters are "used for display only and not for the harmonised record".

**Evidence.** A later finding shows how much a cluster count depends on its radius. For the same 181,404 VIIRS detections in September 2020, the count fell from 15,312 clusters at 1 km to 8,365 at 2 km (49,537 at 0.5 km, 3,676 at 5 km). This whole-month comparison was produced after the gridding code was in place ([California report](case_study/REPORT.md#sensitivity-of-cluster-counts-to-the-clustering-radius)). The cell definition has a cost of its own. Two fires in one cell count once, and a front on a cell edge can look unmatched. The cell size changes results less than the cluster radius changes counts. For Suomi-NPP the median monthly errors at 5, 10 and 25 km were 14.6, 13.2 and 11.4 % in California and 16.6, 14.7 and 14.6 % in Portugal ([California](case_study/REPORT.md#sensitivity-to-the-grid-cell-size), [Portugal](case_study_portugal/REPORT.md#sensitivity-to-the-grid-cell-size)). The 10 km default is a working resolution. Who chose it is not recorded.

## 2. What a missing Aqua match means

**Behaviour.** A platform is "covered" on a date when the download manifest lists that date as requested and returned for one of its sources. Without manifest intervals, coverage is inferred from the span between the first and last detection, and the provenance says so. Known gaps are removed, and one day is trimmed at each coverage edge ([`platform_coverage`](../engine/matching.py)). Cross-sensor pairs are built only on dates when both platforms are covered, and they keep cells seen by either ([`build_pairs`](../engine/matching.py)).

This gives a missing match two different meanings:

- **On a covered date**, a VIIRS-active cell without an Aqua detection means Aqua did not report that cell. It enters calibration as an Aqua "not detected" label.
- **On an uncovered date** there is no Aqua observation, so the cell is left out of calibration. In the record the day is missing, never zero, unless a calibrated VIIRS (or Terra) estimate exists. In that case the day's source is stored with it.

Neither case establishes whether a fire was present. Hot-spot files do not record cloud or what the satellite could see.

**Evidence.** For California NOAA-20, matching produced 11,519 cell half-days seen by both, 31,882 seen only by VIIRS and 1,959 only by Aqua, over 81 months ([report](case_study/REPORT.md#cross-sensor-validation-held-out-data)). The VIIRS-only rows are what the detection model learns from. The tests check that days outside coverage are missing rather than zero, that a failed download chunk becomes a gap, and that coverage never extends past the last detection when FIRMS availability is unknown ([test_harmonization.py](../tests/test_harmonization.py), [test_downloader.py](../tests/test_downloader.py)).

## 3. Model selection: held-out error decides, and the simpler method keeps its place

**Behaviour.** For each platform, the candidates are listed simplest first:
- counts: grid only, constant ratio, detection model, detection model with time of year;
- FRP: as reported, constant ratio, log-log, ridge.

Each candidate is scored on monthly totals in years it was not fitted on (leave-years-out, 5 folds over 7 years). The selection metric is scaled RMSE, on square-root counts and log FRP. The selector starts with the simplest available candidate and switches to a later one only if its scaled RMSE is more than 2 % lower than the current choice. A forward test (fit 2018–2022, predict 2023–24) is reported alongside ([`harmonizer.py`](../engine/harmonizer.py)).

**Why total bias cannot decide.** For California Suomi-NPP, the constant ratio nearly matches Aqua's total over the held-out months, yet its typical month is far off ([report](case_study/REPORT.md#cross-sensor-validation-held-out-data)):

| Count method | Total bias | Median monthly error | Scaled RMSE |
|---|---:|---:|---:|
| Grid only | +210.7 % | 317.5 % | 10.577 |
| Grid and constant ratio | +0.2 % | 46.5 % | 3.117 |
| Detection model with time of year (used) | +1.8 % | 13.2 % | 1.619 |

A single ratio is fitted to make the totals agree. Months it overestimates and months it underestimates then cancel in the total, while each month can still be wrong by about half. The selection metric scores every month, so the seasonal model wins. The median monthly error uses months with more than five observed Aqua cells.

**When the simpler method won.** For California Terra, the constant ratio lowered scaled RMSE from 1.972 (grid only) to 1.946, only 1.3 %. That is short of the 2 % threshold, so grid only was kept ([report](case_study/REPORT.md#cross-sensor-validation-held-out-data)). For FRP in Portugal NOAA-20, "as reported" scored 0.884. Every calibration scored worse (constant ratio 1.061, log-log 0.913, ridge 0.915), so no conversion was applied, even though the uncalibrated total is −31.2 % ([report](case_study_portugal/REPORT.md#cross-sensor-validation-held-out-data)). The rule picks the least-bad candidate. It does not make a weak FRP conversion good.

## The switch-off experiment: what it establishes and where it falls short

**Setup.** From 1 January 2023, every Terra and Aqua detection is removed and both are marked as not covered. Each region's calibrations are refitted on that region's 2018-04-01 to 2022-12-31 data only, and the record continues from VIIRS alone (Suomi-NPP and NOAA-20, averaged, never added). The result is compared with what Aqua actually reported in the 24 withheld months. A month counts only if every day has both values ([`modis_switch_off_test`](../engine/pipeline.py)).

| 2023–24, VIIRS-only record vs real Aqua | California | Portugal |
|---|---:|---:|
| Raw VIIRS hot spots, total difference | +523.0 % | +628.4 % |
| **Active cells:** total difference | −6.0 % | +2.9 % |
| Active cells: median monthly error | 13.4 % | 14.5 % |
| Active cells: rank correlation | 0.957 | 0.925 |
| Months inside the stated 90 % band | 96 % (23 of 24) | 92 % |
| **FRP:** total difference | −37.6 % | −17.1 % |
| FRP: median monthly error | 48.9 % | 88.4 % |

Sources: [California](case_study/REPORT.md#modis-switched-off-does-the-record-continue), [Portugal](case_study_portugal/REPORT.md#modis-switched-off-does-the-record-continue).

**What it establishes.** Within each region, a calibration fitted only on earlier years carried the active-cell record through two later years. The total stayed within 6 % of Aqua and the typical month within about 14 %. A plain switch to raw VIIRS counts would have added 523 % and 628 %.

**Where it falls short.**
- It measures agreement with Aqua, not with fire on the ground.
- It covers two regions and 24 months. Each region used its own calibration, so it says nothing about transferring a calibration between regions. A test of that would freeze the California calibration, apply it to Portugal without refitting, and compare it with Portugal's own fit.
- FRP does not continue reliably. Its monthly errors are large in both regions. Over the same years Aqua's orbit drifted: its median daytime detection time in California moved from 13:11 in 2022 to 13:43 in 2024, and the median gap to NOAA-20 grew from 24 to 45 minutes. A fixed FRP conversion meets that drift, but the experiment does not isolate the cause ([observing-system check](case_study/REPORT.md#observing-system-check)).
- NOAA-21 is not yet part of the continuation.

## One detection, end to end

Take one NOAA-20 detection in the Dixie Fire area on the afternoon of 5 August 2021.

1. **Gridding.** Its position puts it in a 10 km cell. Its UTC time and longitude put it in the 06:00–18:00 local solar slot. Alone it is one active cell-half-day with one pixel. With seven more NOAA-20 pixels in the same cell that afternoon, it is still one active cell-half-day, now with eight pixels. The row also keeps the overpass count, mean time, mean scan width, and FRP divided by the number of overpasses.
2. **Matching** (only on dates both platforms are covered):

   | Aqua side | What enters calibration |
   |---|---|
   | Aqua reported cell C that afternoon | Label 1. With positive FRP from both, the pair also trains the FRP regression. |
   | Aqua covered that date but reported nothing in cell C | Label 0, for "Aqua reports the cell". It says nothing about fire, cloud or bare ground. |
   | Aqua not covered that date | No label: not a calibration row. |

3. **Calibration.** The model learns p, the probability that Aqua also reports a NOAA-20-active cell, from pixel count, FRP, day/night and time of year. The row contributes (1 + ρ_day)·p Aqua-equivalent cells, and (1 + ρ_frp)·p·g(x) Aqua-equivalent FRP. In 2021 Aqua is covered, so the record uses Aqua's own count and the NOAA-20 estimate is not added to it.
4. **Cut-off test.** Dated 5 August 2023, the detection cannot enter fitting: Aqua's coverage is switched off from 1 January 2023, and pairs need both platforms. It is converted to Aqua-equivalent cells and averaged with the other VIIRS platform's estimate for that day. No single pixel is scored. The comparison is the month's total against Aqua's withheld total, and a month counts only if every day has both values. For California, August 2023 gave 67.9 continued against 74 observed active cell-half-days ([report data](case_study/report.json)).

## Use of AI

ChatGPT wrote the 14 November audit. Claude implemented the redesign in `694a04b` and the later changes and tests; from [`5199d46`](https://github.com/Jeeson-Kurian/pyro-harmonize/commit/5199d46) on, commits record Claude as co-author. Codex drafted PR #1's documentation. Claude revised this rationale from an interview with Jeeson Kurian. Claims about Jeeson's role are limited to what he confirmed: he requested the critique and asked for its findings to be addressed.
