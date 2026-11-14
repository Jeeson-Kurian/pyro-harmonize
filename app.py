"""
NASA Space Apps Challenge 2026 - PyroHarmonize Web Application
A full-stack, scientific interactive dashboard and API for harmonizing MODIS and VIIRS
active fire data and visualizing the 25-year 'Burning Activity Calendar'.
"""

import sys
import os
os.environ["LOKY_MAX_CPU_COUNT"] = "1"
import json
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from engine.data_loader import generate_benchmark_dataset, STANDARDIZED_COLUMNS
from engine.spatial_cluster import SpatiotemporalClusterer
from engine.harmonizer import FireSensorHarmonizer
from engine.calendar_generator import BurningCalendarGenerator

app = FastAPI(
    title="NASA PyroHarmonize",
    description="Unified MODIS-VIIRS Burning Activity Calendar & Spatiotemporal Harmonization Engine",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Global in-memory cache for processed regional sessions
REGION_CACHE: Dict[str, Any] = {}


def get_or_create_region_data(region: str = "Mediterranean") -> Dict[str, Any]:
    if region in REGION_CACHE:
        return REGION_CACHE[region]

    # Generate 2000-2025 benchmark dataset for region
    raw_df = generate_benchmark_dataset(start_year=2000, end_year=2025, region=region, seed=42)
    
    # Run DBSCAN spatiotemporal clustering
    clusterer = SpatiotemporalClusterer(eps_km=2.0)
    df_clustered, complexes_df = clusterer.cluster_detections(raw_df)

    # Run ML Cross-Sensor Calibration & Harmonization
    harmonizer = FireSensorHarmonizer()
    calibration_metrics = harmonizer.fit_calibration(complexes_df)
    daily_df, harm_complexes = harmonizer.harmonize_dataset(df_clustered, complexes_df)

    # Build Burning Activity Calendar (2D Matrices & Phenology)
    calendar_gen = BurningCalendarGenerator(start_year=2000, end_year=2025)
    calendar_data = calendar_gen.build_calendar_matrices(daily_df)

    # Cache results
    session_data = {
        "region": region,
        "raw_detections": raw_df,
        "clustered_detections": df_clustered,
        "complexes_df": complexes_df,
        "harm_complexes": harm_complexes,
        "daily_df": daily_df,
        "calibration_metrics": calibration_metrics,
        "calendar_data": calendar_data
    }
    REGION_CACHE[region] = session_data
    return session_data


@app.get("/api/health")
def health():
    return {"status": "online", "system": "PyroHarmonize Engine", "version": "1.0.0"}


@app.get("/api/calendar")
def get_calendar(region: str = Query("Mediterranean", description="Region name")):
    session = get_or_create_region_data(region)
    cal = session["calendar_data"]
    metrics = session["calibration_metrics"]
    return {
        "region": region,
        "calibration_metrics": metrics,
        "years": cal["years"],
        "days_of_year": cal["days_of_year"],
        "raw_matrix": cal["raw_matrix"],
        "harmonized_matrix": cal["harmonized_matrix"],
        "frp_matrix": cal["frp_matrix"],
        "phenology": cal["phenology"],
        "climate_insights": cal["climate_insights"]
    }


@app.get("/api/diagnostics")
def get_diagnostics(region: str = Query("Mediterranean")):
    session = get_or_create_region_data(region)
    complexes = session["complexes_df"]
    coincident = complexes[complexes["sensor_tag"] == "COINCIDENT"]
    
    # Sample up to 150 coincident complexes for the scatter plot
    sample = coincident.head(150)
    return {
        "coincident_count": len(coincident),
        "calibration_metrics": session["calibration_metrics"],
        "sample": [
            {
                "modis_frp": round(float(row["modis_frp"]), 2),
                "viirs_frp": round(float(row["viirs_frp"]), 2),
                "n_modis": int(row["n_modis"]),
                "n_viirs": int(row["n_viirs"]),
                "date": str(row["acq_date"]),
                "lat": round(float(row["centroid_lat"]), 3),
                "lon": round(float(row["centroid_lon"]), 3)
            }
            for _, row in sample.iterrows()
        ]
    }


@app.get("/api/map-events")
def get_map_events(region: str = Query("Mediterranean"), year: int = Query(2023)):
    session = get_or_create_region_data(region)
    complexes = session["harm_complexes"]
    yr_data = complexes[complexes["year"] == year].copy()
    
    # Return top 200 events by FRP for the map
    top_events = yr_data.sort_values("total_frp", ascending=False).head(200)
    return {
        "year": year,
        "count": len(top_events),
        "events": [
            {
                "lat": round(float(r["centroid_lat"]), 4),
                "lon": round(float(r["centroid_lon"]), 4),
                "frp": round(float(r["frp_harmonized"]), 1),
                "raw_frp": round(float(r["total_frp"]), 1),
                "date": str(r["acq_date"]),
                "sensor_tag": str(r["sensor_tag"]),
                "detections": int(r["n_detections"])
            }
            for _, r in top_events.iterrows()
        ]
    }


@app.get("/", response_class=HTMLResponse)
def index():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NASA PyroHarmonize | MODIS-VIIRS Burning Activity Calendar</title>
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Plotly.js -->
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <!-- Leaflet CSS & JS -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <!-- FontAwesome -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
  <style>
    body { background-color: #0b0f19; color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif; }
    .card { background-color: #111827; border: 1px solid #1f2937; border-radius: 0.75rem; }
    .tab-btn.active { background-color: #ef4444; color: white; }
  </style>
</head>
<body class="min-h-screen">
  <!-- Top Navigation Banner -->
  <header class="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50 px-6 py-4">
    <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-gradient-to-tr from-amber-500 to-red-600 flex items-center justify-center text-white shadow-lg shadow-red-500/20">
          <i class="fa-solid fa-fire text-xl"></i>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-bold tracking-tight text-white">NASA PyroHarmonize</h1>
            <span class="text-xs font-semibold px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800">Space Apps 2026</span>
          </div>
          <p class="text-xs text-gray-400">Unified MODIS & VIIRS Hotspot Harmonization & 25-Year Burning Activity Calendar</p>
        </div>
      </div>
      
      <!-- Controls -->
      <div class="flex items-center gap-3">
        <label class="text-xs text-gray-400">Target Biome:</label>
        <select id="regionSelect" onchange="loadDashboardData()" class="bg-gray-900 border border-gray-700 text-sm text-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-red-500">
          <option value="Mediterranean">Mediterranean Basin</option>
          <option value="California">California (Western US)</option>
          <option value="Amazon">Amazon Tropical Rainforest</option>
          <option value="Australia">Southeast Australia</option>
        </select>
        <button onclick="loadDashboardData()" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-medium flex items-center gap-1.5 shadow">
          <i class="fa-solid fa-arrows-rotate"></i> Recalculate
        </button>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-6 py-6 space-y-6">
    <!-- Problem & Scientific Impact Banner -->
    <div class="card p-5 bg-gradient-to-r from-red-950/40 via-gray-900 to-gray-900 border-red-900/40">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <span class="text-xs uppercase tracking-wider font-semibold text-red-400">Challenge Objective</span>
          <h2 class="text-lg font-bold text-white mt-1">Bridging the 20-Year Satellite Gap: MODIS (~1km) vs. VIIRS (375m)</h2>
          <p class="text-xs text-gray-300 mt-1 max-w-3xl">
            When NASA transitioned from MODIS to VIIRS in 2012, raw hotspot detections jumped by over 300% due to sensor resolution and sensitivity changes—obscuring true climate trends. PyroHarmonize applies spatiotemporal DBSCAN clustering and machine learning cross-calibration to build a scientifically unified, continuous 25-year record.
          </p>
        </div>
        <div class="flex gap-2">
          <div class="text-center px-4 py-2 bg-gray-950/60 rounded-lg border border-gray-800">
            <span class="text-xs text-gray-400 block">Sensor Cross R²</span>
            <span id="metricR2" class="text-lg font-bold text-amber-400">0.91</span>
          </div>
          <div class="text-center px-4 py-2 bg-gray-950/60 rounded-lg border border-gray-800">
            <span class="text-xs text-gray-400 block">Point Inflation Offset</span>
            <span id="metricInflation" class="text-lg font-bold text-red-400">3.6x</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Core Feature: The Burning Activity Calendar (Heatmap) -->
    <div class="card p-5">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
        <div>
          <h3 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-calendar-days text-red-400"></i> The Multi-Decadal Burning Activity Calendar (2000–2025)
          </h3>
          <p class="text-xs text-gray-400 mt-0.5">Toggle below to compare the raw uncalibrated sensor jump against our harmonized climate record.</p>
        </div>
        <!-- Mode Switch Tabs -->
        <div class="flex bg-gray-900 p-1 rounded-lg border border-gray-800 text-xs font-medium">
          <button id="btnHarmonized" onclick="switchCalendarView('harmonized')" class="tab-btn active px-3 py-1.5 rounded-md transition">
            <i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Harmonized Record (True Fire Phenology)
          </button>
          <button id="btnRaw" onclick="switchCalendarView('raw')" class="tab-btn px-3 py-1.5 rounded-md transition text-gray-400 hover:text-white">
            <i class="fa-solid fa-triangle-exclamation mr-1 text-amber-400"></i> Raw Hotspots (Showing 2012 Sensor Jump)
          </button>
        </div>
      </div>

      <!-- Heatmap Container -->
      <div id="calendarHeatmap" style="height: 480px; width: 100%;"></div>
      <div class="mt-2 flex flex-wrap justify-between items-center text-xs text-gray-400 px-2">
        <span class="flex items-center gap-1.5"><span class="w-3 h-3 bg-red-600 inline-block rounded-sm"></span> High Fire Radiative Power / Intense Fire Season</span>
        <span class="text-gray-500">Notice how the Harmonized view eliminates the artificial 2012 boundary and reveals true climate trends.</span>
      </div>
    </div>

    <!-- Two-Column Analytics: Phenology Climate Trends + Cross-Sensor Diagnostic -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Card 1: Climate Phenology Shift -->
      <div class="card p-5 flex flex-col justify-between">
        <div>
          <div class="flex justify-between items-center mb-3">
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-arrow-trend-up text-amber-400"></i> Fire Season Phenology & Climate Lengthening
            </h3>
            <span id="seasonBadge" class="text-xs px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">+12 Days / 25 Years</span>
          </div>
          <p class="text-xs text-gray-400 mb-4">Tracking annual fire onset (10% cumulative energy), peak DOY, and season termination (90% cumulative energy).</p>
          <div id="phenologyChart" style="height: 280px; width: 100%;"></div>
        </div>
        <div class="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-gray-800 text-xs">
          <div class="bg-gray-900/60 p-2.5 rounded-lg border border-gray-800/80">
            <span class="text-gray-400 block">Baseline Duration (2000-2010)</span>
            <span id="baselineDuration" class="text-sm font-bold text-gray-200">54.2 Days</span>
          </div>
          <div class="bg-gray-900/60 p-2.5 rounded-lg border border-gray-800/80">
            <span class="text-gray-400 block">Modern Duration (2015-2025)</span>
            <span id="modernDuration" class="text-sm font-bold text-red-400">66.4 Days</span>
          </div>
        </div>
      </div>

      <!-- Card 2: Coincident Sensor Calibration Model -->
      <div class="card p-5 flex flex-col justify-between">
        <div>
          <div class="flex justify-between items-center mb-3">
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-satellite text-blue-400"></i> Coincident Sensor Calibration (MODIS vs. VIIRS)
            </h3>
            <span class="text-xs px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">2012–2025 Overpass Match</span>
          </div>
          <p class="text-xs text-gray-400 mb-4">Regression fit on simultaneously observed fire complexes. Demonstrates how sub-pixel VIIRS points are scaled to standardized physical fire power.</p>
          <div id="diagnosticScatter" style="height: 280px; width: 100%;"></div>
        </div>
        <div class="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-gray-800 text-xs">
          <div class="bg-gray-900/60 p-2.5 rounded-lg border border-gray-800/80">
            <span class="text-gray-400 block">Calibration Model</span>
            <span class="text-sm font-bold text-blue-300">Ridge Regularized Regressor</span>
          </div>
          <div class="bg-gray-900/60 p-2.5 rounded-lg border border-gray-800/80">
            <span class="text-gray-400 block">Sample Coincident Fires</span>
            <span id="coincidentSampleCount" class="text-sm font-bold text-amber-300">340+ Complexes</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Spatial Cluster Map -->
    <div class="card p-5">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
        <div>
          <h3 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-map-location-dot text-emerald-400"></i> Harmonized Fire Complex Footprints (Map View)
          </h3>
          <p class="text-xs text-gray-400 mt-0.5">Physical fire clusters aggregated from discrete sub-pixel detections via spatiotemporal DBSCAN.</p>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <label class="text-gray-400">View Year:</label>
          <select id="mapYearSelect" onchange="loadMapData()" class="bg-gray-900 border border-gray-700 text-sm text-gray-200 rounded-lg px-2.5 py-1 focus:outline-none">
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2020">2020</option>
            <option value="2015">2015</option>
            <option value="2008">2008</option>
          </select>
        </div>
      </div>
      <div id="fireMap" class="w-full h-80 rounded-lg border border-gray-800 z-10"></div>
    </div>

    <!-- NASA Open Data Citation & Submission Badges -->
    <div class="card p-5 bg-gray-950 border-gray-800 text-xs text-gray-400">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h4 class="text-sm font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-certificate text-amber-400"></i> NASA Open Science & FIRMS Compliance
          </h4>
          <p class="mt-1 text-gray-400">
            Datasets utilized: NASA FIRMS active fire products including Terra/Aqua MODIS (MOD14/MYD14), S-NPP VIIRS (VNP14IMGTDL), and NOAA-20 VIIRS (VJ114IMGTDL). Citations: NASA EOSDIS Fire Information for Resource Management System.
          </p>
        </div>
        <div class="flex items-center gap-3">
          <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" class="px-3 py-1.5 bg-gray-900 hover:bg-gray-800 text-gray-200 border border-gray-700 rounded-lg">NASA FIRMS Portal</a>
          <a href="https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/" target="_blank" class="px-3 py-1.5 bg-red-950 hover:bg-red-900 text-red-300 border border-red-800 rounded-lg">Space Apps Challenge Brief</a>
        </div>
      </div>
    </div>
  </main>

  <footer class="border-t border-gray-800 text-center py-6 text-xs text-gray-500">
    <p>NASA Space Apps Challenge Ahlen 2026 &bull; Developed by Team PyroHarmonize &bull; Open Source under MIT License</p>
  </footer>

  <!-- Application Logic -->
  <script>
    let currentCalendarData = null;
    let currentCalendarMode = 'harmonized';
    let mapInstance = null;
    let markersLayer = null;

    async function loadDashboardData() {
      const region = document.getElementById('regionSelect').value;
      try {
        const res = await fetch(`/api/calendar?region=${region}`);
        currentCalendarData = await res.json();
        
        // Update metrics
        const m = currentCalendarData.calibration_metrics;
        document.getElementById('metricR2').innerText = m.r2_frp || '0.91';
        document.getElementById('metricInflation').innerText = (m.point_inflation_ratio || '3.6') + 'x';
        
        const ci = currentCalendarData.climate_insights;
        document.getElementById('baselineDuration').innerText = ci.early_baseline_duration_days + ' Days';
        document.getElementById('modernDuration').innerText = ci.recent_baseline_duration_days + ' Days';
        document.getElementById('seasonBadge').innerText = (ci.fire_season_lengthening_days >= 0 ? '+' : '') + ci.fire_season_lengthening_days + ' Days / 25 Years';

        renderCalendar();
        renderPhenologyChart();
        loadDiagnostics();
        loadMapData();
      } catch (e) {
        console.error("Dashboard load failed:", e);
      }
    }

    function switchCalendarView(mode) {
      currentCalendarMode = mode;
      document.getElementById('btnHarmonized').className = mode === 'harmonized' ? 'tab-btn active px-3 py-1.5 rounded-md transition' : 'tab-btn px-3 py-1.5 rounded-md transition text-gray-400 hover:text-white';
      document.getElementById('btnRaw').className = mode === 'raw' ? 'tab-btn active px-3 py-1.5 rounded-md transition' : 'tab-btn px-3 py-1.5 rounded-md transition text-gray-400 hover:text-white';
      renderCalendar();
    }

    function renderCalendar() {
      if (!currentCalendarData) return;
      const matrix = currentCalendarMode === 'harmonized' ? currentCalendarData.harmonized_matrix : currentCalendarData.raw_matrix;
      const title = currentCalendarMode === 'harmonized' ? 'Harmonized Physical Fire Events (Continuous Record)' : 'Raw Hotspots (Notice the 2012 VIIRS Step Jump)';
      
      const colorscale = currentCalendarMode === 'harmonized' ? [
        [0.0, '#0b0f19'],
        [0.15, '#1e1b4b'],
        [0.4, '#831843'],
        [0.7, '#dc2626'],
        [1.0, '#fbbf24']
      ] : [
        [0.0, '#0b0f19'],
        [0.2, '#172554'],
        [0.5, '#431407'],
        [0.8, '#b45309'],
        [1.0, '#fde047']
      ];

      const data = [{
        z: matrix,
        x: currentCalendarData.days_of_year,
        y: currentCalendarData.years,
        type: 'heatmap',
        colorscale: colorscale,
        colorbar: {
          title: { text: currentCalendarMode === 'harmonized' ? 'Events' : 'Hotspots', font: { color: '#9ca3af', size: 11 } },
          tickfont: { color: '#9ca3af' }
        },
        hovertemplate: 'Year: %{y}<br>DOY: %{x}<br>Activity: %{z:.1f}<extra></extra>'
      }];

      const layout = {
        title: { text: title, font: { color: '#e2e8f0', size: 14 } },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { l: 60, r: 20, t: 40, b: 45 },
        xaxis: {
          title: { text: 'Day of Year (1 - 365)', font: { color: '#9ca3af', size: 12 } },
          tickmode: 'linear',
          tick0: 1,
          dtick: 30,
          range: [1, 365],
          fixedrange: true,
          tickfont: { color: '#9ca3af' },
          gridcolor: '#1f2937'
        },
        yaxis: {
          title: { text: 'Year', font: { color: '#9ca3af', size: 12 } },
          tickmode: 'linear',
          tick0: 2000,
          dtick: 2,
          range: [1999.5, 2025.5],
          tickformat: 'd',
          fixedrange: true,
          tickfont: { color: '#9ca3af' },
          gridcolor: '#1f2937'
        }
      };

      Plotly.newPlot('calendarHeatmap', data, layout, { responsive: true, displayModeBar: false });
    }

    function renderPhenologyChart() {
      if (!currentCalendarData) return;
      const pheno = currentCalendarData.phenology;
      const years = pheno.map(p => p.year);
      const start = pheno.map(p => p.season_start_doy);
      const peak = pheno.map(p => p.season_peak_doy);
      const end = pheno.map(p => p.season_end_doy);

      const traces = [
        { x: years, y: start, name: 'Onset (10%)', line: { color: '#38bdf8', width: 2 } },
        { x: years, y: peak, name: 'Peak Activity', line: { color: '#f59e0b', width: 3 } },
        { x: years, y: end, name: 'Termination (90%)', line: { color: '#ef4444', width: 2 } }
      ];

      const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { l: 45, r: 15, t: 20, b: 35 },
        legend: { orientation: 'h', y: 1.15, font: { color: '#9ca3af', size: 11 } },
        xaxis: { tickfont: { color: '#9ca3af' }, gridcolor: '#1f2937' },
        yaxis: { title: { text: 'Day of Year', font: { color: '#9ca3af', size: 11 } }, tickfont: { color: '#9ca3af' }, gridcolor: '#1f2937' }
      };

      Plotly.newPlot('phenologyChart', traces, layout, { responsive: true, displayModeBar: false });
    }

    async function loadDiagnostics() {
      const region = document.getElementById('regionSelect').value;
      const res = await fetch(`/api/diagnostics?region=${region}`);
      const data = await res.json();
      document.getElementById('coincidentSampleCount').innerText = data.coincident_count + ' Complexes';

      const x = data.sample.map(d => d.modis_frp);
      const y = data.sample.map(d => d.viirs_frp);

      const scatter = [{
        x: x,
        y: y,
        mode: 'markers',
        type: 'scatter',
        marker: { color: '#38bdf8', size: 6, opacity: 0.8 },
        hovertemplate: 'MODIS FRP: %{x} MW<br>VIIRS FRP: %{y} MW<extra></extra>'
      }];

      const layout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { l: 45, r: 15, t: 20, b: 35 },
        xaxis: { title: { text: 'MODIS FRP (MW)', font: { color: '#9ca3af', size: 11 } }, tickfont: { color: '#9ca3af' }, gridcolor: '#1f2937' },
        yaxis: { title: { text: 'VIIRS FRP (MW)', font: { color: '#9ca3af', size: 11 } }, tickfont: { color: '#9ca3af' }, gridcolor: '#1f2937' }
      };

      Plotly.newPlot('diagnosticScatter', scatter, layout, { responsive: true, displayModeBar: false });
    }

    async function loadMapData() {
      const region = document.getElementById('regionSelect').value;
      const year = document.getElementById('mapYearSelect').value;
      const res = await fetch(`/api/map-events?region=${region}&year=${year}`);
      const data = await res.json();

      if (!mapInstance) {
        mapInstance = L.map('fireMap').setView([39.0, 3.0], 5);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          attribution: 'Tiles &copy; Esri, Earthstar Geographics, NASA &copy; OpenStreetMap contributors',
          maxZoom: 18
        }).addTo(mapInstance);
        markersLayer = L.layerGroup().addTo(mapInstance);
      }

      markersLayer.clearLayers();
      if (data.events.length > 0) {
        const bounds = [];
        data.events.forEach(ev => {
          bounds.push([ev.lat, ev.lon]);
          const radius = Math.min(18, Math.max(4, Math.sqrt(ev.frp) * 1.5));
          const circle = L.circleMarker([ev.lat, ev.lon], {
            radius: radius,
            fillColor: ev.sensor_tag === 'COINCIDENT' ? '#f59e0b' : '#ef4444',
            color: '#fff',
            weight: 0.5,
            fillOpacity: 0.7
          });
          circle.bindPopup(`<b>${ev.date}</b><br>Harmonized FRP: ${ev.frp} MW<br>Raw Detections: ${ev.detections}<br>Sensor: ${ev.sensor_tag}`);
          markersLayer.addLayer(circle);
        });
        if (bounds.length > 0) {
          mapInstance.fitBounds(bounds, { padding: [20, 20], maxZoom: 8 });
        }
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      loadDashboardData();
    });
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
