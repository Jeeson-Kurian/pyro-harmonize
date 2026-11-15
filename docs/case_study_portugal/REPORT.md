# PyroHarmonize validation report: Portugal

Data: NASA FIRMS active-fire detections (see the table of platforms below).

- Software version: 2.0.0
- Area (west, south, east, north): -9.600, 36.900, -6.100, 42.200
- Period: 2018-04-01 to 2024-12-31 (2,467 days, local solar dates)
- Grid: 10 km equal-area cells x day/night half-days
- Reference scale: Aqua MODIS
- Coverage basis: download manifest

## Platforms and coverage

| Platform | Orbit | Detections used | Coverage | Days covered | Days with detections | Processing |
|---|---|---:|---|---:|---:|---|
| Terra MODIS | morning | 6,668 | 2018-04-01 to 2024-12-31 | 2,467 | 872 | SP 6,668 |
| Aqua MODIS | afternoon | 6,630 | 2018-04-01 to 2024-12-31 | 2,467 | 862 | SP 6,630 |
| Suomi-NPP VIIRS | afternoon | 39,806 | 2018-04-01 to 2024-12-31 | 2,467 | 1,813 | SP 39,806 |
| NOAA-20 VIIRS | afternoon | 40,707 | 2018-04-01 to 2024-12-31 | 2,467 | 1,853 | SP 40,707 |

## Quality control

109,169 rows read, 93,811 used. Removed: 4,666 low-confidence, 10,692 non-vegetation hot spots, 0 duplicates, 0 without valid position or time, 0 from an unidentified platform. 0 rows had no `type` field and could not be screened for static sources.

## Cross-sensor validation (held-out data)

### Terra MODIS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 776 seen by both, 2,065 only by Terra MODIS, 2,087 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 216 min; 0 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +0.6 % | 24.3 % | 0.903 | 1.264 | +1.9 % |
| Common grid only (no calibration) **(used)** | -0.8 % | 20.6 % | 0.888 | 0.932 | -2.4 % |
| Common grid + one constant ratio | +0.1 % | 20.4 % | 0.886 | 0.939 | -2.3 % |
| Common grid + detection-probability model | +0.7 % | 30.4 % | 0.881 | 1.420 | +22.2 % |
| Common grid + detection model with time of year | -0.9 % | 32.4 % | 0.875 | 1.479 | +22.0 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -22.9 % | 41.4 % | 0.864 | 1.032 | -7.9 % |
| Common grid + one constant ratio **(used)** | +2.5 % | 52.4 % | 0.862 | 1.000 | +35.3 % |
| Detection model x log-log FRP regression | +9.9 % | 56.1 % | 0.846 | 1.097 | +27.0 % |
| Detection model x ridge FRP regression | +14.9 % | 58.0 % | 0.826 | 1.161 | +36.2 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.641, R2 0.383 (n = 776). Too few pairs within 15 min for a separate fit.

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.28 to +1.36.

### Suomi-NPP VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 1,884 seen by both, 8,113 only by Suomi-NPP VIIRS, 979 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 24 min; 37 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +500.4 % | 450.0 % | 0.937 | 13.362 | +630.2 % |
| Common grid only (no calibration) | +249.2 % | 307.7 % | 0.885 | 5.486 | +215.9 % |
| Common grid + one constant ratio | -0.1 % | 28.1 % | 0.885 | 1.378 | -12.7 % |
| Common grid + detection-probability model | +0.3 % | 16.6 % | 0.932 | 0.753 | +5.1 % |
| Common grid + detection model with time of year **(used)** | +0.3 % | 14.7 % | 0.937 | 0.704 | +5.2 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -33.0 % | 50.4 % | 0.955 | 0.798 | -28.8 % |
| Common grid + one constant ratio | +0.3 % | 99.8 % | 0.954 | 1.011 | +10.5 % |
| Detection model x log-log FRP regression **(used)** | -9.8 % | 58.0 % | 0.946 | 0.780 | -6.7 % |
| Detection model x ridge FRP regression | -9.5 % | 58.8 % | 0.947 | 0.780 | -5.8 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.771, R2 0.622 (n = 1,884). Pairs within 15 min only: slope 0.879, R2 0.768 (n = 690).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.09 to +0.94.

### NOAA-20 VIIRS converted to the Aqua MODIS scale

- Test design: leave-years-out, 5 folds over 7 years
- Matched cell half-days: 1,936 seen by both, 8,699 only by NOAA-20 VIIRS, 927 only by Aqua MODIS, over 81 months
- Median time between the two overpasses: 24 min; 36 % within 15 min
- Selection rule: simplest method whose held-out scaled RMSE is within 2 % of the best

Active fire cells per month:

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Raw hot-spot counts (no harmonisation) | +514.0 % | 466.7 % | 0.944 | 13.541 | +626.7 % |
| Common grid only (no calibration) | +271.5 % | 341.5 % | 0.902 | 5.788 | +242.0 % |
| Common grid + one constant ratio | +0.1 % | 28.2 % | 0.902 | 1.295 | -10.6 % |
| Common grid + detection-probability model | -0.0 % | 18.2 % | 0.934 | 0.677 | +0.3 % |
| Common grid + detection model with time of year **(used)** | +0.1 % | 14.3 % | 0.935 | 0.647 | +0.6 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) **(used)** | -31.2 % | 57.0 % | 0.928 | 0.883 | -27.5 % |
| Common grid + one constant ratio | +0.2 % | 88.9 % | 0.930 | 1.060 | +9.0 % |
| Detection model x log-log FRP regression | +5.0 % | 81.0 % | 0.924 | 0.913 | +2.3 % |
| Detection model x ridge FRP regression | +4.8 % | 79.6 % | 0.924 | 0.915 | +3.3 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.759, R2 0.6 (n = 1,936). Pairs within 15 min only: slope 0.833, R2 0.727 (n = 699).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -0.97 to +1.04.

## Sensitivity to the grid cell size

The whole analysis repeated with other cell sizes. Stable results across sizes mean the conclusion does not hinge on the 10 km choice.

| Cell size | Platform | Method used | Held-out total bias | Median monthly error |
|---:|---|---|---:|---:|
| 5 km | Terra | Common grid only (no calibration) | -0.2 % | 20.0 % |
| 5 km | SNPP | Common grid + detection model with time of year | -0.3 % | 16.6 % |
| 5 km | NOAA20 | Common grid + detection model with time of year | -0.4 % | 16.6 % |
| 10 km | Terra | Common grid only (no calibration) | -0.8 % | 20.6 % |
| 10 km | SNPP | Common grid + detection model with time of year | +0.3 % | 14.7 % |
| 10 km | NOAA20 | Common grid + detection model with time of year | +0.1 % | 14.3 % |
| 25 km | Terra | Common grid only (no calibration) | +1.7 % | 19.7 % |
| 25 km | SNPP | Common grid + detection model with time of year | -0.2 % | 14.6 % |
| 25 km | NOAA20 | Common grid + detection model with time of year | +0.1 % | 15.9 % |

## Sensitivity of cluster counts to the clustering radius

Month with the most detections (2024-09; detections from 2024-09-01 to 2024-09-30). Cluster counts change with the radius, which is why clusters are used for display only and not for the harmonised record.

| Radius | Sensor | Detections | Clusters | Pixels per cluster |
|---:|---|---:|---:|---:|
| 0.5 km | MODIS | 2,529 | 2,466 | 1.03 |
| 0.5 km | VIIRS | 20,587 | 6,078 | 3.39 |
| 1 km | MODIS | 2,529 | 1,877 | 1.35 |
| 1 km | VIIRS | 20,587 | 2,011 | 10.24 |
| 2 km | MODIS | 2,529 | 697 | 3.63 |
| 2 km | VIIRS | 20,587 | 1,416 | 14.54 |
| 5 km | MODIS | 2,529 | 394 | 6.42 |
| 5 km | VIIRS | 20,587 | 924 | 22.28 |

## Observing-system check

Median local solar time of daytime detections, by platform and year. A change over the years means the satellite's orbit drifted, so it observes fires at a different time of day.

| Platform | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Aqua | 13:12 | 13:09 | 13:07 | 13:08 | 13:10 | 13:22 | 13:36 |
| NOAA20 | 13:02 | 12:56 | 12:56 | 12:55 | 13:01 | 13:06 | 12:32 |
| SNPP | 12:56 | 13:02 | 13:01 | 12:53 | 12:59 | 12:52 | 12:50 |
| Terra | 10:58 | 10:58 | 10:58 | 10:57 | 10:51 | 10:37 | 10:18 |

Daytime cells seen by both NOAA20 and Aqua: Aqua FRP divided by NOAA20 FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 119 | 22 | 2.28 |
| 2019 | 245 | 23 | 2.12 |
| 2020 | 183 | 25 | 2.18 |
| 2021 | 179 | 16 | 1.95 |
| 2022 | 283 | 21 | 2.45 |
| 2023 | 165 | 28 | 1.60 |
| 2024 | 174 | 44 | 1.58 |

Daytime cells seen by both SNPP and Aqua: Aqua FRP divided by SNPP FRP, and median minutes between the two overpasses.

| Year | Pairs | Minutes apart | Aqua / VIIRS FRP |
|---:|---:|---:|---:|
| 2018 | 109 | 26 | 1.84 |
| 2019 | 254 | 15 | 1.82 |
| 2020 | 188 | 24 | 1.90 |
| 2021 | 171 | 24 | 1.48 |
| 2022 | 246 | 23 | 2.02 |
| 2023 | 168 | 26 | 1.40 |
| 2024 | 186 | 29 | 1.91 |

If the FRP ratio varies a lot between years, a single FRP conversion cannot hold for every year, and harmonised FRP should be read as less certain than harmonised cell counts.

## Seasonality (observed, no cause assigned)

- Shortest stretch holding 80 % of typical yearly activity: day 24 to day 268 (245 days)
- Season length: not reported (6 usable fire years; at least 8 are needed)
- Yearly total: not reported (6 usable fire years; at least 8 are needed)

## Notes and limits

- Terra observes about three hours earlier in the day than Aqua. Terra-derived values are a statistical conversion across the fire diurnal cycle and are the least certain part of the record.
- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, or where cloud hid the ground.
- FRP values are instantaneous power at overpass time. They are not fire radiative energy.
- A result for one area does not validate the method for other regions or fire regimes.
