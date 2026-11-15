# PyroHarmonize validation report: Northern California, USA

Data: NASA FIRMS active-fire detections (see the table of platforms below).

- Software version: 2.0.0
- Area (west, south, east, north): -124.000, 36.000, -119.000, 41.000
- Period: 2018-04-01 to 2024-12-31 (2,467 days, local solar dates)
- Grid: 10 km equal-area cells x day/night half-days
- Reference scale: Aqua MODIS
- Coverage basis: download manifest

## Platforms and coverage

| Platform | Orbit | Detections used | Coverage | Days covered | Days with detections | Processing |
|---|---|---:|---|---:|---:|---|
| Terra MODIS | morning | 49,762 | 2018-04-01 to 2024-12-31 | 2,467 | 1,714 | SP 49,762 |
| Aqua MODIS | afternoon | 46,514 | 2018-04-01 to 2024-12-31 | 2,467 | 1,654 | SP 46,514 |
| Suomi-NPP VIIRS | afternoon | 401,886 | 2018-04-01 to 2024-12-31 | 2,467 | 2,332 | SP 401,886 |
| NOAA-20 VIIRS | afternoon | 409,870 | 2018-04-01 to 2024-12-31 | 2,467 | 2,354 | SP 409,870 |

## Quality control

982,543 rows read, 908,032 used. Removed: 43,856 low-confidence, 30,655 non-vegetation hot spots, 0 duplicates, 0 without valid position or time, 0 from an unidentified platform. 0 rows had no `type` field and could not be screened for static sources.

## Cross-sensor validation (held-out data)

### Terra MODIS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 6,898 seen by both, 7,146 only by Terra MODIS, 6,580 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 190 min; 0 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +7.0 % | 26.1 % | 0.915 | 3.230 | +3.2 % |
| Common grid only (no calibration) **(used)** | +4.2 % | 26.3 % | 0.873 | 1.972 | +2.4 % |
| Common grid + one constant ratio | +0.4 % | 24.0 % | 0.874 | 1.946 | -2.1 % |
| Common grid + detection-probability model | +2.5 % | 30.4 % | 0.855 | 2.706 | -21.1 % |
| Common grid + detection model with time of year | +2.2 % | 28.6 % | 0.873 | 2.845 | -23.1 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -15.3 % | 31.9 % | 0.927 | 0.566 | -25.1 % |
| Common grid + one constant ratio **(used)** | +2.9 % | 28.5 % | 0.929 | 0.523 | -12.6 % |
| Detection model x log-log FRP regression | +17.8 % | 38.5 % | 0.932 | 0.572 | -0.7 % |
| Detection model x ridge FRP regression | +18.5 % | 43.2 % | 0.921 | 0.670 | -5.0 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.782, R2 0.505 (n = 6,898). Too few pairs within 15 min for a separate fit.

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -2.83 to +2.97.

### Suomi-NPP VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 11,275 seen by both, 30,595 only by Suomi-NPP VIIRS, 2,203 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 23 min; 36 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +764.0 % | 664.2 % | 0.962 | 46.929 | +461.8 % |
| Common grid only (no calibration) | +210.7 % | 317.5 % | 0.887 | 10.577 | +313.1 % |
| Common grid + one constant ratio | +0.2 % | 46.5 % | 0.874 | 3.117 | +41.8 % |
| Common grid + detection-probability model | +1.8 % | 18.5 % | 0.955 | 1.748 | -9.0 % |
| Common grid + detection model with time of year **(used)** | +1.8 % | 13.2 % | 0.961 | 1.619 | -8.5 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -32.8 % | 37.8 % | 0.978 | 0.578 | -62.3 % |
| Common grid + one constant ratio | +3.3 % | 78.6 % | 0.977 | 0.769 | -46.0 % |
| Detection model x log-log FRP regression **(used)** | -1.5 % | 36.7 % | 0.982 | 0.509 | -50.3 % |
| Detection model x ridge FRP regression | +3.4 % | 56.1 % | 0.980 | 0.587 | -44.5 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.879, R2 0.736 (n = 11,273). Pairs within 15 min only: slope 0.923, R2 0.793 (n = 4,043).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.75 to +1.68.

### NOAA-20 VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 11,519 seen by both, 31,882 only by NOAA-20 VIIRS, 1,959 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 24 min; 35 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +781.2 % | 617.2 % | 0.959 | 47.533 | +584.2 % |
| Common grid only (no calibration) | +222.0 % | 335.3 % | 0.924 | 10.956 | +339.9 % |
| Common grid + one constant ratio | +0.3 % | 47.3 % | 0.915 | 3.097 | +46.8 % |
| Common grid + detection-probability model | +1.6 % | 17.8 % | 0.960 | 1.571 | -3.5 % |
| Common grid + detection model with time of year **(used)** | +1.6 % | 14.1 % | 0.975 | 1.406 | -3.5 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -31.0 % | 38.7 % | 0.967 | 0.520 | -42.0 % |
| Common grid + one constant ratio | +2.6 % | 73.1 % | 0.964 | 0.718 | -17.1 % |
| Detection model x log-log FRP regression **(used)** | -5.5 % | 28.3 % | 0.971 | 0.417 | -24.8 % |
| Detection model x ridge FRP regression | -1.8 % | 38.9 % | 0.969 | 0.494 | -17.3 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.884, R2 0.737 (n = 11,515). Pairs within 15 min only: slope 0.929, R2 0.796 (n = 4,031).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.48 to +1.57.

## Sensitivity to the grid cell size

The whole analysis repeated with other cell sizes. Stable results across sizes mean the conclusion does not hinge on the 10 km choice.

| Cell size | Platform | Method used | Held-out total bias | Median monthly error |
|---:|---|---|---:|---:|
| 5 km | Terra | Common grid + one constant ratio | +0.6 % | 23.2 % |
| 5 km | SNPP | Common grid + detection model with time of year | +2.3 % | 14.6 % |
| 5 km | NOAA20 | Common grid + detection model with time of year | +2.1 % | 14.8 % |
| 10 km | Terra | Common grid only (no calibration) | +4.2 % | 26.3 % |
| 10 km | SNPP | Common grid + detection model with time of year | +1.8 % | 13.2 % |
| 10 km | NOAA20 | Common grid + detection model with time of year | +1.6 % | 14.1 % |
| 25 km | Terra | Common grid + one constant ratio | +0.2 % | 22.2 % |
| 25 km | SNPP | Common grid + detection model with time of year | +0.8 % | 11.4 % |
| 25 km | NOAA20 | Common grid + detection model with time of year | +0.8 % | 12.0 % |

## Sensitivity of cluster counts to the clustering radius

Month with the most detections (2020-09; detections from 2020-09-01 to 2020-09-30). Cluster counts change with the radius, which is why clusters are used for display only and not for the harmonised record.

| Radius | Sensor | Detections | Clusters | Pixels per cluster |
|---:|---|---:|---:|---:|
| 0.5 km | MODIS | 18,544 | 18,070 | 1.03 |
| 0.5 km | VIIRS | 181,404 | 49,537 | 3.66 |
| 1 km | MODIS | 18,544 | 14,835 | 1.25 |
| 1 km | VIIRS | 181,404 | 15,312 | 11.85 |
| 2 km | MODIS | 18,544 | 4,286 | 4.33 |
| 2 km | VIIRS | 181,404 | 8,365 | 21.69 |
| 5 km | MODIS | 18,544 | 2,108 | 8.8 |
| 5 km | VIIRS | 181,404 | 3,676 | 49.35 |

## MODIS switched off: does the record continue?

Both MODIS instruments (Terra and Aqua) are removed from 2023-01-01. Every calibration is refitted on 2018-04-01 to 2022-12-31 only, and the record is continued from SNPP and NOAA20 VIIRS alone (731 of 731 days). The result is compared with what Aqua MODIS really observed in 24 months, which the test never saw.

| | Total difference from real Aqua MODIS | Median monthly error | Rank correlation |
|---|---:|---:|---:|
| Raw VIIRS hot spots (mean of the VIIRS satellites) | +523.0 % | | |
| Record continued from VIIRS, active cells | -6.0 % | 13.4 % | 0.957 |
| Record continued from VIIRS, FRP | -37.6 % | 48.9 % | 0.975 |

Real Aqua monthly values inside the stated 90 % band: 96 % of months.

## Observing-system check

Median local solar time of daytime detections, by platform and year. A change over the years means the satellite's orbit drifted, so it observes fires at a different time of day.

| Platform | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aqua | 13:11 | 13:10 | 13:06 | 13:08 | 13:11 | 13:25 | 13:43 |
| NOAA20 | 12:58 | 12:56 | 13:00 | 13:01 | 12:57 | 12:56 | 12:56 |
| SNPP | 13:05 | 12:58 | 13:00 | 13:00 | 12:56 | 12:55 | 12:55 |
| Terra | 10:59 | 10:57 | 11:00 | 10:58 | 10:47 | 10:35 | 10:17 |

Daytime cells seen by both NOAA20 and Aqua: Aqua FRP divided by NOAA20 FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 1,080 | 27 | 1.93 |
| 2019 | 666 | 24 | 2.38 |
| 2020 | 2,372 | 23 | 1.79 |
| 2021 | 1,890 | 24 | 2.17 |
| 2022 | 789 | 24 | 1.66 |
| 2023 | 787 | 27 | 1.47 |
| 2024 | 639 | 45 | 2.91 |

Daytime cells seen by both SNPP and Aqua: Aqua FRP divided by SNPP FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 1,099 | 22 | 1.90 |
| 2019 | 647 | 23 | 2.32 |
| 2020 | 2,355 | 23 | 1.72 |
| 2021 | 1,828 | 24 | 2.10 |
| 2022 | 779 | 25 | 1.71 |
| 2023 | 760 | 26 | 1.35 |
| 2024 | 583 | 48 | 2.28 |

If the FRP ratio varies a lot between years, a single FRP conversion cannot hold for every year, and harmonised FRP should be read as less certain than harmonised cell counts.

## Seasonality (observed, no cause assigned)

- Shortest stretch holding 80 % of typical yearly activity: day 192 to day 40 (214 days)
- Season length: not reported (6 usable fire years; at least 8 are needed)
- Yearly total: not reported (6 usable fire years; at least 8 are needed)

## Notes and limits

- Terra observes about three hours earlier in the day than Aqua. Terra-derived values are a statistical conversion across the fire diurnal cycle and are the least certain part of the record.
- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, or where cloud hid the ground.
- FRP values are instantaneous power at overpass time. They are not fire radiative energy.
- A result for one area does not validate the method for other regions or fire regimes.
