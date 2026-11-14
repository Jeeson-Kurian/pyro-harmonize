# PyroHarmonize validation report

> **SYNTHETIC SELF-TEST. The data in this report are simulated (engine/synthetic.py).**
> It shows that the software recovers a known cross-sensor relationship. It is not
> evidence about real satellites or real fires.

- Software version: 2.0.0
- Area (west, south, east, north): -124.029, 35.965, -118.973, 41.030
- Period: 2001-01-01 to 2025-12-31 (9,131 days, local solar dates)
- Grid: 10 km equal-area cells x day/night half-days
- Reference scale: Aqua MODIS
- Coverage basis: download manifest

## Platforms and coverage

| Platform | Orbit | Detections used | Coverage | Days covered | Days with detections | Processing |
|---|---|---:|---|---:|---:|---|
| Terra MODIS | morning | 19,472 | 2001-01-01 to 2025-12-31 | 9,131 | 3,567 | SYNTHETIC 19,472 |
| Aqua MODIS | afternoon | 27,648 | 2002-07-03 to 2025-12-31 | 8,556 | 3,506 | SYNTHETIC 27,648 |
| Suomi-NPP VIIRS | afternoon | 50,632 | 2012-01-21 to 2025-12-31 | 5,094 | 2,443 | SYNTHETIC 50,632 |
| NOAA-20 VIIRS | afternoon | 27,646 | 2018-04-02 to 2025-12-31 | 2,831 | 1,401 | SYNTHETIC 27,646 |

## Quality control

132,696 rows read, 125,398 used. Removed: 5,967 low-confidence, 1,331 non-vegetation hot spots, 0 duplicates, 0 without valid position or time, 0 from an unidentified platform. 0 rows had no `type` field and could not be screened for static sources.

## Cross-sensor validation (held-out data)

### Terra MODIS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 24 years
- Matched cell half-days: 5,513 seen by both, 6,656 only by Terra MODIS, 9,951 only by Aqua MODIS, over 191 months
- Median time between the two overpasses: 179 min; 0 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | -33.5 % | 33.3 % | 0.988 | 2.362 | -34.4 % |
| Common grid only (no calibration) | -21.3 % | 21.5 % | 0.988 | 1.163 | -20.4 % |
| Common grid + one constant ratio **(used)** | +0.0 % | 9.8 % | 0.988 | 0.606 | +1.5 % |
| Common grid + detection-probability model | +0.0 % | 12.3 % | 0.985 | 0.689 | +0.1 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -48.5 % | 49.5 % | 0.991 | 0.912 | -48.8 % |
| Common grid + one constant ratio **(used)** | +0.0 % | 12.0 % | 0.991 | 0.631 | -0.7 % |
| Detection model x log-log FRP regression | +7.3 % | 15.6 % | 0.989 | 0.650 | +5.0 % |
| Detection model x ridge FRP regression | -1.3 % | 12.0 % | 0.990 | 0.659 | -2.3 % |

Forward test: fitted on 2002 to 2018, tested on 2019 to 2025.

FRP log-log fit, all pairs: slope 0.87, R2 0.542 (n = 5,513). Too few pairs within 15 min for a separate fit.

Empirical 90 % band for monthly cells (square-root scale, from 191 held-out months): -0.97 to +1.00.

### Suomi-NPP VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 14 years
- Matched cell half-days: 7,239 seen by both, 14,097 only by Suomi-NPP VIIRS, 1,556 only by Aqua MODIS, over 118 months
- Median time between the two overpasses: 22 min; 37 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +216.9 % | 221.6 % | 0.990 | 9.076 | +224.1 % |
| Common grid only (no calibration) | +142.6 % | 143.7 % | 0.990 | 4.862 | +149.7 % |
| Common grid + one constant ratio | -0.0 % | 8.0 % | 0.989 | 0.557 | +4.0 % |
| Common grid + detection-probability model **(used)** | +0.0 % | 6.4 % | 0.994 | 0.423 | +3.3 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | +28.1 % | 31.1 % | 0.994 | 0.699 | +29.2 % |
| Common grid + one constant ratio | -0.1 % | 9.7 % | 0.994 | 0.599 | +1.1 % |
| Detection model x log-log FRP regression **(used)** | -0.7 % | 9.5 % | 0.994 | 0.548 | +1.0 % |
| Detection model x ridge FRP regression | -1.4 % | 9.6 % | 0.994 | 0.566 | +1.1 % |

Forward test: fitted on 2012 to 2021, tested on 2022 to 2025.

FRP log-log fit, all pairs: slope 0.733, R2 0.655 (n = 7,239). Pairs within 15 min only: slope 0.729, R2 0.655 (n = 2,654).

Empirical 90 % band for monthly cells (square-root scale, from 118 held-out months): -0.77 to +0.48.

### NOAA-20 VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 8 years
- Matched cell half-days: 3,983 seen by both, 7,986 only by NOAA-20 VIIRS, 835 only by Aqua MODIS, over 65 months
- Median time between the two overpasses: 21 min; 37 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +221.6 % | 224.7 % | 0.983 | 9.180 | +231.1 % |
| Common grid only (no calibration) | +148.4 % | 145.7 % | 0.990 | 5.012 | +150.9 % |
| Common grid + one constant ratio | +0.0 % | 7.9 % | 0.990 | 0.579 | +1.3 % |
| Common grid + detection-probability model **(used)** | +0.1 % | 7.3 % | 0.993 | 0.430 | +4.1 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | +29.9 % | 31.2 % | 0.992 | 0.730 | +32.9 % |
| Common grid + one constant ratio | +0.0 % | 8.6 % | 0.991 | 0.614 | +3.0 % |
| Detection model x log-log FRP regression **(used)** | -0.8 % | 9.5 % | 0.993 | 0.502 | +2.8 % |
| Detection model x ridge FRP regression | -1.4 % | 9.5 % | 0.993 | 0.508 | +1.9 % |

Forward test: fitted on 2018 to 2023, tested on 2024 to 2025.

FRP log-log fit, all pairs: slope 0.73, R2 0.661 (n = 3,983). Pairs within 15 min only: slope 0.716, R2 0.644 (n = 1,479).

Empirical 90 % band for monthly cells (square-root scale, from 65 held-out months): -0.67 to +0.63.

## Sensitivity to the grid cell size

The whole analysis repeated with other cell sizes. Stable results across sizes mean the conclusion does not hinge on the 10 km choice.

| Cell size | Platform | Method used | Held-out total bias | Median monthly error |
|---:|---|---|---:|---:|
| 5 km | Terra | Common grid + one constant ratio | +0.0 % | 10.5 % |
| 5 km | SNPP | Common grid + detection-probability model | -0.0 % | 6.5 % |
| 5 km | NOAA20 | Common grid + detection-probability model | +0.1 % | 6.5 % |
| 10 km | Terra | Common grid + one constant ratio | +0.0 % | 9.8 % |
| 10 km | SNPP | Common grid + detection-probability model | +0.0 % | 6.4 % |
| 10 km | NOAA20 | Common grid + detection-probability model | +0.1 % | 7.3 % |
| 25 km | Terra | Common grid + one constant ratio | -0.0 % | 9.2 % |
| 25 km | SNPP | Common grid + detection-probability model | -0.0 % | 5.4 % |
| 25 km | NOAA20 | Common grid + detection-probability model | +0.1 % | 6.4 % |

## Sensitivity of cluster counts to the clustering radius

Busiest month in the selection (2021-08). Cluster counts change with the radius, which is why clusters are used for display only and not for the harmonised record.

| Radius | Sensor | Detections | Clusters | Pixels per cluster |
|---:|---|---:|---:|---:|
| 0.5 km | MODIS | 781 | 781 | 1.0 |
| 0.5 km | VIIRS | 2,983 | 2,662 | 1.12 |
| 1 km | MODIS | 781 | 761 | 1.03 |
| 1 km | VIIRS | 2,983 | 1,760 | 1.69 |
| 2 km | MODIS | 781 | 480 | 1.63 |
| 2 km | VIIRS | 2,983 | 1,067 | 2.8 |
| 5 km | MODIS | 781 | 360 | 2.17 |
| 5 km | VIIRS | 2,983 | 908 | 3.29 |

## Seasonality (observed, no cause assigned)

- Shortest stretch holding 80 % of typical yearly activity: day 178 to day 276 (99 days)
- Season length: +1.82 days per decade, 95 % interval -2.14 to +6.92, p = 0.337, 25 fire years
- Yearly total: -49.91 harmonised active cells per decade, 95 % interval -108.89 to +12.14, p = 0.088, 25 fire years

## Notes and limits

- SYNTHETIC DATA. Simulated detections from engine/synthetic.py. Nothing shown here describes real fire activity.
- Terra observes about three hours earlier in the day than Aqua. Terra-derived values are a statistical conversion across the fire diurnal cycle and are the least certain part of the record.
- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, or where cloud hid the ground.
- FRP values are instantaneous power at overpass time. They are not fire radiative energy.
- A result for one area does not validate the method for other regions or fire regimes.
