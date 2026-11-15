# PyroHarmonize validation report

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
| Common grid + detection-probability model **(used)** | +1.8 % | 18.5 % | 0.955 | 1.748 | -9.0 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -32.8 % | 37.8 % | 0.978 | 0.578 | -62.3 % |
| Common grid + one constant ratio | +3.3 % | 78.6 % | 0.977 | 0.769 | -46.0 % |
| Detection model x log-log FRP regression **(used)** | -1.5 % | 36.7 % | 0.982 | 0.509 | -50.3 % |
| Detection model x ridge FRP regression | +3.4 % | 56.1 % | 0.980 | 0.587 | -44.5 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.879, R2 0.736 (n = 11,273). Pairs within 15 min only: slope 0.923, R2 0.793 (n = 4,043).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.50 to +2.57.

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
| Common grid + detection-probability model **(used)** | +1.6 % | 17.8 % | 0.960 | 1.571 | -3.5 % |

Fire radiative power (monthly sum of overpass snapshots, MW):

| Method | Total bias | Median monthly error | Rank corr. | Scaled RMSE | Forward-test bias |
|---|---:|---:|---:|---:|---:|
| Target FRP as reported (no calibration) | -31.0 % | 38.7 % | 0.967 | 0.520 | -42.0 % |
| Common grid + one constant ratio | +2.6 % | 73.1 % | 0.964 | 0.718 | -17.1 % |
| Detection model x log-log FRP regression **(used)** | -5.5 % | 28.3 % | 0.971 | 0.417 | -24.8 % |
| Detection model x ridge FRP regression | -1.8 % | 38.9 % | 0.969 | 0.494 | -17.3 % |

Forward test: fitted on 2018 to 2022, tested on 2023 to 2024.

FRP log-log fit, all pairs: slope 0.884, R2 0.737 (n = 11,515). Pairs within 15 min only: slope 0.929, R2 0.796 (n = 4,031).

Empirical 90 % band for monthly cells (square-root scale, from 81 held-out months): -1.46 to +2.15.

## Sensitivity to the grid cell size

The whole analysis repeated with other cell sizes. Stable results across sizes mean the conclusion does not hinge on the 10 km choice.

| Cell size | Platform | Method used | Held-out total bias | Median monthly error |
|---:|---|---|---:|---:|
| 5 km | Terra | Common grid + one constant ratio | +0.6 % | 23.2 % |
| 5 km | SNPP | Common grid + detection-probability model | +2.4 % | 17.4 % |
| 5 km | NOAA20 | Common grid + detection-probability model | +2.1 % | 17.6 % |
| 10 km | Terra | Common grid only (no calibration) | +4.2 % | 26.3 % |
| 10 km | SNPP | Common grid + detection-probability model | +1.8 % | 18.5 % |
| 10 km | NOAA20 | Common grid + detection-probability model | +1.6 % | 17.8 % |
| 25 km | Terra | Common grid + one constant ratio | +0.2 % | 22.2 % |
| 25 km | SNPP | Common grid + detection-probability model | +1.0 % | 15.6 % |
| 25 km | NOAA20 | Common grid + detection-probability model | +1.0 % | 15.1 % |

## Sensitivity of cluster counts to the clustering radius

Busiest month in the selection (2020-09). Cluster counts change with the radius, which is why clusters are used for display only and not for the harmonised record.

| Radius | Sensor | Detections | Clusters | Pixels per cluster |
|---:|---|---:|---:|---:|
| 0.5 km | MODIS | 4,311 | 4,252 | 1.01 |
| 0.5 km | VIIRS | 36,332 | 9,011 | 4.03 |
| 1 km | MODIS | 4,311 | 3,482 | 1.24 |
| 1 km | VIIRS | 36,332 | 2,721 | 13.35 |
| 2 km | MODIS | 4,311 | 903 | 4.77 |
| 2 km | VIIRS | 36,332 | 1,461 | 24.87 |
| 5 km | MODIS | 4,311 | 428 | 10.07 |
| 5 km | VIIRS | 36,332 | 659 | 55.13 |

## Seasonality (observed, no cause assigned)

- Shortest stretch holding 80 % of typical yearly activity: day 192 to day 40 (214 days)
- Season length: not reported (6 usable fire years; at least 8 are needed)
- Yearly total: not reported (6 usable fire years; at least 8 are needed)

## Notes and limits

- Terra observes about three hours earlier in the day than Aqua. Terra-derived values are a statistical conversion across the fire diurnal cycle and are the least certain part of the record.
- Hot-spot files record detections only. They do not record where a satellite looked and saw nothing, or where cloud hid the ground.
- FRP values are instantaneous power at overpass time. They are not fire radiative energy.
- A result for one area does not validate the method for other regions or fire regimes.
