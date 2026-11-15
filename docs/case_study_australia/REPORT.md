# PyroHarmonize validation report: Northern Australia (tropical savanna)

Data: NASA FIRMS active-fire detections (see the table of platforms below).

- Software version: 2.0.0
- Area (west, south, east, north): 131.000, -16.000, 135.000, -12.000
- Period: 2018-04-01 to 2024-12-31 (2,467 days, local solar dates)
- Grid: 10 km equal-area cells x day/night half-days
- Reference scale: Aqua MODIS
- Coverage basis: download manifest

## Platforms and coverage

| Platform | Orbit | Detections used | Coverage | Days covered | Days with detections | Processing |
|---|---|---:|---|---:|---:|---|
| Terra MODIS | morning | 68,732 | 2018-04-01 to 2024-12-31 | 2,467 | 1,802 | SP 68,732 |
| Aqua MODIS | afternoon | 115,598 | 2018-04-01 to 2024-12-31 | 2,467 | 1,799 | SP 115,598 |
| Suomi-NPP VIIRS | afternoon | 848,358 | 2018-04-01 to 2024-12-31 | 2,467 | 2,044 | SP 848,358 |
| NOAA-20 VIIRS | afternoon | 840,251 | 2018-04-01 to 2024-12-31 | 2,467 | 2,099 | SP 840,251 |

## Quality control

2,079,816 rows read, 1,872,941 used. Removed: 206,538 low-confidence, 335 non-vegetation hot spots, 2 duplicates, 0 without valid position or time, 0 from an unidentified platform. 0 rows had no `type` field and could not be screened for static sources.

## Cross-sensor validation (held-out data)

### Terra MODIS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 11,540 seen by both, 20,812 only by Terra MODIS, 37,600 only by Aqua MODIS, over 80 months
- Median time between the two overpasses: 173 min; 0 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | -40.5 % | 47.3 % | 0.908 | 11.261 | -47.6 % |
| Common grid only (no calibration) | -34.2 % | 38.3 % | 0.951 | 6.122 | -42.3 % |
| Common grid + one constant ratio **(used)** | -0.4 % | 39.1 % | 0.947 | 4.496 | -16.6 % |
| Common grid + detection-probability model | -0.2 % | 39.0 % | 0.925 | 5.069 | -23.4 % |
| Common grid + detection model with time of year | -0.4 % | 38.0 % | 0.938 | 4.675 | -25.0 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -51.9 % | 57.1 % | 0.848 | 1.400 | -57.3 % |
| Common grid + one constant ratio | -0.1 % | 44.8 % | 0.849 | 1.081 | -15.1 % |
| Detection model x log-log FRP regression **(used)** | -6.6 % | 32.4 % | 0.895 | 0.965 | -24.4 % |
| Detection model x ridge FRP regression | -0.7 % | 31.9 % | 0.890 | 0.995 | -23.3 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.412, R2 0.159 (n = 11,540). Too few pairs within 15 min for a separate fit.

Empirical 90 % band for monthly cells (square-root scale, from 80 held-out months): -6.18 to +7.07.

### Suomi-NPP VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 40,861 seen by both, 107,236 only by Suomi-NPP VIIRS, 8,279 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 27 min; 32 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +633.9 % | 660.4 % | 0.981 | 64.847 | +591.6 % |
| Common grid only (no calibration) | +201.4 % | 206.1 % | 0.987 | 18.321 | +180.6 % |
| Common grid + one constant ratio | -0.1 % | 7.9 % | 0.986 | 2.103 | -9.5 % |
| Common grid + detection-probability model | -0.1 % | 12.1 % | 0.985 | 2.184 | -8.2 % |
| Common grid + detection model with time of year **(used)** | -0.1 % | 5.8 % | 0.989 | 1.798 | -8.5 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | +25.7 % | 32.1 % | 0.973 | 0.767 | +24.5 % |
| Common grid + one constant ratio **(used)** | +0.0 % | 13.4 % | 0.974 | 0.680 | -1.3 % |
| Detection model x log-log FRP regression | -6.0 % | 12.8 % | 0.963 | 0.693 | -8.2 % |
| Detection model x ridge FRP regression | -5.8 % | 14.2 % | 0.962 | 0.705 | -8.1 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.605, R2 0.44 (n = 40,859). Pairs within 15 min only: slope 0.691, R2 0.537 (n = 13,267).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.35 to +1.95.

### NOAA-20 VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 41,825 seen by both, 110,424 only by NOAA-20 VIIRS, 7,315 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 27 min; 32 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +626.9 % | 634.2 % | 0.984 | 64.312 | +607.7 % |
| Common grid only (no calibration) | +209.8 % | 215.2 % | 0.990 | 18.862 | +198.3 % |
| Common grid + one constant ratio | -0.2 % | 9.7 % | 0.990 | 1.745 | -5.2 % |
| Common grid + detection-probability model | -0.1 % | 12.4 % | 0.989 | 1.840 | -3.8 % |
| Common grid + detection model with time of year **(used)** | +0.1 % | 6.2 % | 0.992 | 1.506 | -4.2 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | +25.3 % | 31.1 % | 0.982 | 0.743 | +29.1 % |
| Common grid + one constant ratio **(used)** | +0.3 % | 12.5 % | 0.982 | 0.648 | +4.2 % |
| Detection model x log-log FRP regression | -6.8 % | 15.7 % | 0.970 | 0.652 | -4.5 % |
| Detection model x ridge FRP regression | -6.1 % | 14.5 % | 0.970 | 0.664 | -3.6 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.62, R2 0.455 (n = 41,823). Pairs within 15 min only: slope 0.713, R2 0.546 (n = 13,602).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.52 to +1.47.

## Sensitivity to the grid cell size

The whole analysis repeated with other cell sizes. Stable results across sizes mean the conclusion does not hinge on the 10 km choice.

| Cell size | Platform | Method used | Held-out total bias | Median monthly error |
|---:|---|---|---:|---:|
| 5 km | Terra | Common grid + one constant ratio | -0.4 % | 40.9 % |
| 5 km | SNPP | Common grid + detection model with time of year | -0.2 % | 5.9 % |
| 5 km | NOAA20 | Common grid + detection model with time of year | +0.1 % | 6.1 % |
| 10 km | Terra | Common grid + one constant ratio | -0.4 % | 39.1 % |
| 10 km | SNPP | Common grid + detection model with time of year | -0.1 % | 5.8 % |
| 10 km | NOAA20 | Common grid + detection model with time of year | +0.1 % | 6.2 % |
| 25 km | Terra | Common grid + one constant ratio | -0.4 % | 28.2 % |
| 25 km | SNPP | Common grid + detection model with time of year | -0.0 % | 6.5 % |
| 25 km | NOAA20 | Common grid + detection model with time of year | +0.1 % | 5.8 % |

## Sensitivity of cluster counts to the clustering radius

Month with the most detections (2018-05; detections from 2018-05-01 to 2018-05-31). Cluster counts change with the radius, which is why clusters are used for display only and not for the harmonised record.

| Radius | Sensor | Detections | Clusters | Pixels per cluster |
|---:|---|---:|---:|---:|
| 0.5 km | MODIS | 11,576 | 11,554 | 1.0 |
| 0.5 km | VIIRS | 116,546 | 58,341 | 2.0 |
| 1 km | MODIS | 11,576 | 10,339 | 1.12 |
| 1 km | VIIRS | 116,546 | 32,614 | 3.57 |
| 2 km | MODIS | 11,576 | 6,130 | 1.89 |
| 2 km | VIIRS | 116,546 | 23,377 | 4.99 |
| 5 km | MODIS | 11,576 | 4,420 | 2.62 |
| 5 km | VIIRS | 116,546 | 14,224 | 8.19 |

## MODIS switched off: does the record continue?

Both MODIS instruments (Terra and Aqua) are removed from 2023-01-01. Every calibration is refitted on 2018-04-01 to 2022-12-31 only, and the record is continued from SNPP and NOAA20 VIIRS alone (731 of 731 days). The result is compared with what Aqua MODIS really observed in 24 months, which the test never saw.

| | Total difference from real Aqua MODIS | Median monthly error | Rank correlation |
|---|---:|---:|---:|
| Raw VIIRS hot spots (mean of the VIIRS satellites) | +599.7 % | | |
| Record continued from VIIRS, active cells | -6.3 % | 7.1 % | 0.992 |
| Record continued from VIIRS, FRP | +1.4 % | 14.9 % | 0.990 |

Real Aqua monthly values inside the stated 90 % band: 83 % of months.

## Observing-system check

Median local solar time of daytime detections, by platform and year. A change over the years means the satellite's orbit drifted, so it observes fires at a different time of day.

| Platform | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aqua | 13:43 | 13:42 | 13:43 | 13:41 | 13:47 | 13:58 | 14:19 |
| NOAA20 | 13:34 | 13:35 | 13:32 | 13:34 | 13:35 | 13:36 | 13:34 |
| SNPP | 13:34 | 13:35 | 13:36 | 13:35 | 13:37 | 13:35 | 13:34 |
| Terra | 10:23 | 10:25 | 10:22 | 10:23 | 10:14 | 09:58 | 09:38 |

Daytime cells seen by both NOAA20 and Aqua: Aqua FRP divided by NOAA20 FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 6,517 | 22 | 1.20 |
| 2019 | 5,917 | 27 | 1.33 |
| 2020 | 4,241 | 26 | 1.15 |
| 2021 | 5,382 | 24 | 1.16 |
| 2022 | 5,321 | 24 | 1.25 |
| 2023 | 5,469 | 26 | 1.17 |
| 2024 | 5,365 | 43 | 1.13 |

Daytime cells seen by both SNPP and Aqua: Aqua FRP divided by SNPP FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 6,470 | 22 | 1.16 |
| 2019 | 5,843 | 23 | 1.29 |
| 2020 | 4,184 | 22 | 1.10 |
| 2021 | 5,307 | 23 | 1.18 |
| 2022 | 5,060 | 21 | 1.29 |
| 2023 | 5,533 | 28 | 1.18 |
| 2024 | 4,870 | 44 | 1.09 |

If the FRP ratio varies a lot between years, a single FRP conversion cannot hold for every year, and harmonised FRP should be read as less certain than harmonised cell counts.

## Seasonality (observed, no cause assigned)

- Shortest stretch holding 80 % of typical yearly activity: day 108 to day 260 (153 days)
- Season length: not reported (5 usable fire years; at least 8 are needed)
- Yearly total: not reported (5 usable fire years; at least 8 are needed)

## Notes and limits

- Terra observes about three hours earlier in the day than Aqua. Terra-derived values are a statistical conversion across the fire diurnal cycle and are the least certain part of the record.
- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, or where cloud hid the ground.
- FRP values are instantaneous power at overpass time. They are not fire radiative energy.
- A result for one area does not validate the method for other regions or fire regimes.
