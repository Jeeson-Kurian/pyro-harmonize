# What should a fire calendar count when the satellite changes?

The calendar estimates how many grid cells Aqua MODIS would have reported as active. That choice sets a limit on every result below. Agreement with Aqua measures continuity with a historical instrument. Two instruments can agree and still miss a fire under cloud. The regional reports cover April 2018 through December 2024. Each uses its own calibration.

## From pixels to an observation

Suppose VIIRS reports eight hot spots along one front during an afternoon pass and Aqua reports one. If all nine points fall in the same grid cell and local half-day, each platform contributes one active cell. PyroHarmonize keeps the pixel counts as features, so the distinction between one detection and eight remains available to the model. Dividing time by local solar day and night also lets a night pass cross midnight without splitting it across two calendar dates. The implementation is in [add_keys and build_cell_table](../engine/gridding.py).

Gridding costs spatial detail. Two nearby fronts can share a cell, and detections on opposite sides of a cell edge can appear unmatched. Northern California gives a sense of the trade-off. At 5, 10 and 25 km, the Suomi-NPP seasonal model's median monthly errors were 14.6%, 13.2% and 11.4%. The coarsest grid scored best on that comparison. It also defines a larger unit of activity. The default 10 km cell is a working resolution, with a sensitivity check in the [California report](case_study/REPORT.md#sensitivity-to-the-grid-cell-size).

## What a missing observation means

Aqua and the VIIRS platforms sample a similar part of the day. Terra observes earlier. In northern California the median gap for matched Terra–Aqua observations was 190 minutes, compared with 23 minutes for Suomi-NPP–Aqua. Using Aqua as the reference gives the VIIRS conversion a closer comparison in time and retains the scale of the earlier MODIS record. A VIIRS-scale reconstruction of the earlier years would also need to estimate fires the coarser instrument missed.

A missing match has two possible interpretations. On a date covered by both platforms, a VIIRS-only cell supplies evidence about what Aqua reports. During an Aqua outage, the same VIIRS detection supplies no Aqua label. The matching code first restricts comparisons to dates covered by both, then retains cells seen by either. Coverage comes from download intervals where available. The fallback infers a span from detections, and neither source tells us which ground was visible through clouds. A covered date with zero detections means zero *reported* activity. See [platform_coverage and build_pairs](../engine/matching.py).

## When the simpler model wins

For California Suomi-NPP, a constant conversion ratio nearly matched Aqua's total over the held-out months. The table shows why that alone would be a poor basis for choosing a calendar model.

| Count method | Total bias | Median absolute monthly error |
|---|---:|---:|
| Grid only | +210.7% | 317.5% |
| Grid and constant ratio | +0.2% | 46.5% |
| Detection model with time of year | +1.8% | 13.2% |

Errors with opposite signs cancel across months. The seasonal model tracks the monthly pattern better even though its total bias is larger. For these count errors, the median uses months with more than five observed Aqua cells. The selection metric is held-out RMSE on square-root counts. The selector starts with the simplest available candidate and moves to a later one only when its score improves by more than 2% relative to the current choice. In the same region, the grid alone scored 1.972 for Terra and the ratio scored 1.946. That reduction was too small to trigger a switch. See the [selection code](../engine/harmonizer.py) and the [candidate scores](case_study/REPORT.md#cross-sensor-validation-held-out-data).

## What happens when Aqua disappears?

On a covered Aqua day, the record uses Aqua. Without Aqua, each available calibrated VIIRS platform produces an estimate on the Aqua scale. If two platforms each estimate ten active cells, the daily estimate is ten. Adding them would make the calendar jump merely because another satellite was available. Calibrated Terra is the last source in the daily sequence. When no source qualifies, the record keeps the date missing. The synthetic tests exercise both an outage and a covered quiet period. See the [pipeline](../engine/pipeline.py) and [harmonisation tests](../tests/test_harmonization.py).

The switch-off experiment removes both MODIS instruments from January 2023 onward and refits using the earlier overlap. Actual Aqua observations in 2023–24 are then available for scoring. Over 24 months, active-cell total bias was −6.0% in California and +2.9% in Portugal. Median absolute monthly errors were 13.4% and 14.5%. The same reconstruction underestimated total fire radiative power by 37.6% and 17.1%. Power is sampled at overpass time, and the California report records the median daytime Aqua–NOAA-20 gap growing from 24 minutes in 2022 to 45 in 2024. That makes a fixed FRP conversion harder to interpret. The experiment does not isolate the cause of the error. [California](case_study/REPORT.md#observing-system-check) · [Portugal](case_study_portugal/REPORT.md)

A separate experiment would be needed to test geographic transfer. One option is to freeze the California calibration, apply it in Portugal without refitting, then compare it with Portugal's locally fitted baseline. The current reports answer how each calibration behaves over time within its own region.

## Whiteboard walkthrough

Draw three columns for one cell and half-day: VIIRS pixels, Aqua pixels, and whether each platform had coverage. Start with eight VIIRS pixels and one Aqua pixel. Remove the Aqua pixel with coverage intact, then remove Aqua coverage altogether. Which cases enter calibration, and what is the Aqua label in each? Trace the answer from gridding through matching. Finally, hide Aqua for the last two years and explain which observations the pipeline can use for fitting and which it keeps for scoring.
