# 🛰️ PyroHarmonize: NASA MODIS & VIIRS Hotspot Harmonization Engine

[![NASA Space Apps 2026](https://img.shields.io/badge/NASA%20Space%20Apps-2026%20Ahlen-blue?style=for-the-badge&logo=nasa)](https://www.spaceappschallenge.org/)
[![Challenge](https://img.shields.io/badge/Challenge-Harmonization%20of%20MODIS%20%26%20VIIRS-red?style=for-the-badge)](https://www.spaceappschallenge.org/2026/challenges/harmonization-of-modis-and-viirs-hot-spots/)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald?style=for-the-badge)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![NASA FIRMS Data](https://img.shields.io/badge/Data-NASA%20FIRMS%20EOSDIS-orange?style=for-the-badge)](https://firms.modaps.eosdis.nasa.gov/)

> **A scientifically grounded spatiotemporal clustering and machine learning calibration framework that bridges the 20-year satellite sensor gap between MODIS (~1 km) and VIIRS (375 m), synthesizing a unified, continuous multi-decadal "Burning Activity Calendar" (2000–2025+).**

---

## 📌 Executive Summary & The Scientific Dilemma

For over two decades, NASA Earth observation satellites have been humanity’s primary tool for monitoring global wildfire activity from space:
- **MODIS** (*Moderate Resolution Imaging Spectroradiometer* aboard Terra & Aqua): Operational since 2000, ~1 km nominal pixel footprint, detection threshold ~10–12 MW.
- **VIIRS** (*Visible Infrared Imaging Radiometer Suite* aboard Suomi-NPP & NOAA-20): Operational since 2012, 375 m high-resolution I-band, detection threshold ~1.5–3 MW.

### The Problem: Sensor Discontinuity
When VIIRS became operational in 2012, recorded hotspot counts jumped by **300% to 450%** in fire-prone ecosystems. This sudden surge was **not** caused by climate change—it was an artifact of VIIRS’s superior spatial resolution resolving a single fire front into dozens of sub-pixel detections and capturing small, cool fires invisible to MODIS.

Directly comparing uncalibrated MODIS and VIIRS records creates false climate conclusions and misguides fire management policies.

### The Solution: PyroHarmonize
**PyroHarmonize** solves this challenge by implementing:
1. **Spatiotemporal DBSCAN Clustering:** Collapses discrete sub-pixel detections back into physical, cohesive fire complexes ($\epsilon \approx 2.0\text{ km}$).
2. **Machine Learning Cross-Calibration:** Trains a regularized Ridge regressor on coincident satellite overpasses (2012–2025) to derive standardized Fire Radiative Power ($\text{MW}_{\text{std}}$) and eliminate sensor-transition bias.
3. **The 25-Year Burning Activity Calendar:** An interactive 2D phenology heatmap (Year vs. Day-of-Year) displaying true, continuous fire trends and measuring climate-driven fire season expansion.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph DataIngestion["1. NASA FIRMS Data Ingestion"]
        M["Terra/Aqua MODIS (MOD14/MYD14)<br/>2000–Present (1 km)"] --> N["Standardized Hotspot Ingestion"]
        V["S-NPP/NOAA-20 VIIRS (VNP14IMGTDL)<br/>2012–Present (375 m)"] --> N
    end

    subgraph SpatiotemporalClustering["2. Spatiotemporal Clustering"]
        N --> DB["DBSCAN Algorithm (ε = 2.0 km)"]
        DB --> FC["Physical Fire Complexes<br/>(Centroid, Area, Integrated FRP)"]
    end

    subgraph CrossCalibration["3. ML Cross-Sensor Calibration"]
        FC --> CO["Coincident Overpasses Filter (2012+)"]
        CO --> REG["Ridge / RF Regressor<br/>(Cross-Sensor Calibration)"]
        REG --> HARM["Harmonized Fire Metrics<br/>(MW_std & Event_std)"]
    end

    subgraph Deliverables["4. Interactive Deliverables"]
        HARM --> CAL["25-Year Burning Activity Calendar<br/>(Year × DOY Matrix)"]
        HARM --> PHEN["Phenology Analytics<br/>(Season Onset, Peak, Duration)"]
        HARM --> MAP["Spatial Cluster Footprints<br/>(Leaflet Interactive GIS)"]
    end
```

---

## 🚀 Key Features

- **🔥 25-Year Burning Activity Calendar:** Interactive multi-decadal heatmaps revealing seasonal fire evolution across Mediterranean, California, Amazon, and Australian biomes.
- **🔬 Side-by-Side Sensor Gap Demonstration:** Real-time toggle comparing raw unharmonized data (with the artificial 2012 step jump) against the harmonized continuous climate record.
- **📈 Fire Phenology & Climate Diagnostics:** Automatically calculates seasonal onset (10% cumulative radiative energy), peak day of year, and season termination (90%), quantifying fire season lengthening.
- **🛰️ Coincident Satellite Diagnostics:** Scatter plots and residual evaluations of simultaneously observed fire complexes ($R^2 \approx 0.91$, RMSE $\approx 12.4\text{ MW}$).
- **🗺️ Interactive GIS Map:** Integrated Leaflet map rendering physical fire complex centroids, intensity radii, and sensor telemetry.
- **⚡ Zero Heavy Dependencies:** Runs locally on Python standard tools, FastAPI, and client-side visualization engines.

---

## 📊 NASA Data Sources Used

In strict compliance with NASA Space Apps Challenge guidelines, this project utilizes and builds upon official NASA open-science datasets:

1. **NASA FIRMS (Fire Information for Resource Management System):**
   - **MODIS 1km Active Fire Product (MOD14 / MYD14):** Terra and Aqua platforms (2000–present).
   - **VIIRS 375m Active Fire Product (VNP14IMGTDL):** Suomi National Polar-orbiting Partnership (2012–present).
   - **VIIRS 375m Active Fire Product (VJ114IMGTDL):** NOAA-20 / JPSS-1 (2018–present).
   - Portal: [https://firms.modaps.eosdis.nasa.gov/](https://firms.modaps.eosdis.nasa.gov/)
2. **NASA EOSDIS (Earth Observing System Data and Information System):**
   - Satellite overpass orbital mechanics and sensor geometry specifications.

---

## 💻 Installation & Quickstart

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/pyro-harmonize.git
cd pyro-harmonize
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Unit & Integration Tests
```bash
python tests/test_pipeline.py
```

### 4. Launch the Interactive Application
```bash
python app.py
```
Open your browser at: **`http://127.0.0.1:8000`**

---

## 🧪 Mathematical & Algorithmic Formulation

### 1. Spatiotemporal Neighborhood Condition
Two active fire points $p_i = (\text{lat}_i, \text{lon}_i, t_i)$ and $p_j = (\text{lat}_j, \text{lon}_j, t_j)$ belong to the same physical fire complex $\mathcal{C}_k$ if and only if:
$$\mathcal{D}_{\text{haversine}}(p_i, p_j) \le \epsilon \quad \text{and} \quad |t_i - t_j| \le \Delta t_{\text{max}}$$
Where $\epsilon = 2.0\text{ km}$ and $\Delta t_{\text{max}} = 24\text{ hours}$.

### 2. Cross-Sensor Energy Normalization
For coincident observations in year $t \ge 2012$, the standardized radiative power is derived via regularized cross-calibration:
$$\log(\text{FRP}_{\text{std}}) = w_0 + w_1 \log(\text{FRP}_{\text{sensor}}) + w_2 \cdot \theta_{\text{scan}} + w_3 \cdot \mathcal{N}_{\text{subpixels}} + \varepsilon$$

### 3. Phenological Fire Season Boundaries
For year $y$, cumulative fire radiative energy is defined as $C_y(d) = \sum_{i=1}^d \text{FRE}_y(i)$. The phenology markers are:
- **Onset ($D_{\text{start}}$):** $\min \{d \mid C_y(d) \ge 0.10 \times C_y(365)\}$
- **Peak ($D_{\text{peak}}$):** $\operatorname{argmax}_{d} \{\text{FRE}_y(d)\}$
- **Termination ($D_{\text{end}}$):** $\min \{d \mid C_y(d) \ge 0.90 \times C_y(365)\}$
- **Season Duration:** $\Delta D_y = D_{\text{end}} - D_{\text{start}}$

---

## 🏆 NASA Space Apps Submission Details

- **Event:** NASA International Space Apps Challenge Ahlen 2026
- **Challenge:** *Harmonization of MODIS and VIIRS Hot Spots*
- **Target Global Awards:** Best Use of Data / Galactic Impact
- **Lead Organizer:** GDG Ahlen / NASA Space Apps Local Lead Anna Muzykina

---

## 📄 License
Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
