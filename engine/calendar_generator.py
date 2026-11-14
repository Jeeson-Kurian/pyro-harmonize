"""
Burning Activity Calendar Generator
Synthesizes multi-decadal fire records into interactive 2D calendar matrices
(Year x Day-of-Year) and calculates key fire phenology metrics (season onset, peak, duration).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple


class BurningCalendarGenerator:
    """
    Transforms harmonized daily fire data into the 2D 'Burning Activity Calendar'
    and extracts fire phenology indicators over a 25-year climate baseline.
    """

    def __init__(self, start_year: int = 2000, end_year: int = 2025):
        self.start_year = start_year
        self.end_year = end_year
        self.years = list(range(start_year, end_year + 1))
        self.days_of_year = list(range(1, 366))

    def build_calendar_matrices(
        self,
        daily_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Creates dense 2D matrices:
        - raw_matrix: Unharmonized hotspot counts (with visible 2012 sensor step jump).
        - harmonized_matrix: Harmonized physical fire events (smooth multi-decadal record).
        - frp_matrix: Standardized Fire Radiative Energy (MW).
        """
        n_years = len(self.years)
        n_days = 365

        raw_grid = np.zeros((n_years, n_days))
        harm_grid = np.zeros((n_years, n_days))
        frp_grid = np.zeros((n_years, n_days))

        year_to_idx = {yr: i for i, yr in enumerate(self.years)}

        for _, row in daily_df.iterrows():
            yr = int(row["year"])
            doy = int(row["doy"])
            if yr in year_to_idx and 1 <= doy <= 365:
                yi = year_to_idx[yr]
                di = doy - 1
                raw_grid[yi, di] = row["raw_hotspot_count"]
                harm_grid[yi, di] = row["harmonized_fire_events"]
                frp_grid[yi, di] = row["harmonized_frp"]

        # Phenology statistics per year
        phenology_records = []
        for yi, yr in enumerate(self.years):
            daily_series = harm_grid[yi, :]
            total_events = float(daily_series.sum())
            total_frp = float(frp_grid[yi, :].sum())

            if total_events > 0:
                cum_energy = np.cumsum(daily_series) / total_events
                # 10% threshold = season onset
                start_doy = int(np.argmax(cum_energy >= 0.10) + 1)
                # Max fire day = peak
                peak_doy = int(np.argmax(daily_series) + 1)
                # 90% threshold = season end
                end_doy = int(np.argmax(cum_energy >= 0.90) + 1)
                duration = max(1, end_doy - start_doy)
            else:
                start_doy = 0
                peak_doy = 0
                end_doy = 0
                duration = 0

            raw_annual_count = int(raw_grid[yi, :].sum())
            harm_annual_count = int(round(total_events))

            phenology_records.append({
                "year": yr,
                "raw_hotspots": raw_annual_count,
                "harmonized_events": harm_annual_count,
                "total_frp_mw": round(total_frp, 1),
                "season_start_doy": start_doy,
                "season_peak_doy": peak_doy,
                "season_end_doy": end_doy,
                "season_duration_days": duration
            })

        phenology_df = pd.DataFrame(phenology_records)

        # Calculate climate trend: compare first decade (2000-2010) vs recent decade (2015-2025)
        early_mask = (phenology_df["year"] <= 2010)
        recent_mask = (phenology_df["year"] >= 2015)
        
        early_duration = phenology_df.loc[early_mask, "season_duration_days"].mean()
        recent_duration = phenology_df.loc[recent_mask, "season_duration_days"].mean()
        duration_change = float(recent_duration - early_duration)

        early_frp = phenology_df.loc[early_mask, "total_frp_mw"].mean()
        recent_frp = phenology_df.loc[recent_mask, "total_frp_mw"].mean()
        frp_pct_change = float(((recent_frp - early_frp) / max(1, early_frp)) * 100)

        climate_insights = {
            "early_baseline_duration_days": round(early_duration, 1),
            "recent_baseline_duration_days": round(recent_duration, 1),
            "fire_season_lengthening_days": round(duration_change, 1),
            "fire_intensity_increase_pct": round(frp_pct_change, 1)
        }

        return {
            "years": self.years,
            "days_of_year": self.days_of_year,
            "raw_matrix": raw_grid.tolist(),
            "harmonized_matrix": harm_grid.tolist(),
            "frp_matrix": frp_grid.tolist(),
            "phenology": phenology_records,
            "climate_insights": climate_insights
        }
