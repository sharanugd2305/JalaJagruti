# JalaJagruti AI 🌍💧
### CNN-LSTM-Based Groundwater Depletion Risk Prediction Using Satellite and Environmental Data

JalaJagruti AI is a deep-learning and GIS-based research project designed to analyze groundwater-level trends and estimate groundwater depletion risk across **243 BBMP wards in Bengaluru, Karnataka, India**.

The project combines groundwater monitoring data, satellite-derived environmental indicators, and climate variables using a Convolutional Neural Network–Long Short-Term Memory (CNN-LSTM) architecture. Its objective is to support ward-level groundwater assessment, temporal forecasting, and interactive geospatial visualization.

> **Research note:** Model predictions and risk categories are estimates, not direct groundwater measurements. Forecasts beyond the tested horizon are indicative and should be interpreted with appropriate caution.

## 📌 Project Overview

Groundwater is an essential resource for urban water security. Increasing water demand, urban expansion, changing rainfall patterns, and uneven monitoring coverage make regional groundwater assessment challenging.

JalaJagruti AI explores the integration of deep learning, remote sensing, environmental data, and GIS to estimate groundwater levels and visualize potential depletion risk at ward level.

### Key Features

- **CNN-LSTM architecture:** Combines spatial feature extraction with temporal sequence learning.
- **Groundwater analysis:** Uses groundwater observations from the supplied dataset.
- **Satellite indicators:** Incorporates Sentinel-2-derived NDVI and NDBI and NASA VIIRS night-time-light data, subject to data availability.
- **Environmental variables:** Integrates rainfall and temperature information.
- **Ward-level GIS:** Supports visualization of all 243 BBMP ward boundaries.
- **Groundwater forecasting:** Generates model-based estimates for future years where supported by the pipeline.
- **Risk visualization:** Displays project-specific groundwater-risk categories.
- **Data-quality awareness:** Distinguishes observed groundwater data, model estimates, and insufficient-data areas.

## 🎯 Objectives

1. Analyze historical groundwater-level observations across the study area.
2. Integrate satellite-derived and environmental features with groundwater data.
3. Develop a CNN-LSTM-based groundwater-level prediction model.
4. Evaluate model performance using appropriate regression metrics.
5. Estimate ward-level groundwater conditions while accounting for uneven monitoring coverage.
6. Visualize groundwater predictions and risk categories using an interactive GIS dashboard.
7. Investigate the limitations and uncertainty of longer-term groundwater forecasts.

## 🗺️ Study Area

**Location:** Bengaluru, Karnataka, India  
**Administrative coverage:** 243 BBMP wards under the selected ward-boundary version.

The project uses spatial ward boundaries to organize predictions and visualize groundwater conditions.

Reported monitoring coverage:

| Metric | Reported value |
|---|---:|
| Wards in study area | 243 |
| Wards containing an eligible groundwater well | 14 |
| Wards with an estimate in the reported 2030 run | 239 |
| Wards with insufficient data in the reported 2030 run | 4 |

These figures describe the reported pipeline run and should be reconfirmed against the final prediction exports before publication.

A ward without an eligible monitoring well may receive a spatially estimated value if the configured interpolation method has sufficient nearby observations. Such an estimate must not be interpreted as a direct groundwater measurement from that ward.

## 🛰️ Data Sources

| Dataset | Purpose | Source |
|---|---|---|
| Groundwater-level observations | Historical groundwater target variable | User-supplied `GroundWaterDataset/` |
| Sentinel-2 Level-2A | Vegetation and built-up indicators | [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) |
| VIIRS VNP46A3 | Night-time radiance as an urban-activity proxy | [NASA LAADS DAAC](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3) |
| ERA5-Land | Rainfall and temperature variables | [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/) |
| BBMP ward boundaries | Spatial analysis and ward-level mapping | [BBMP official website](https://bbmp.gov.in/) |

### Environmental Indicators

- **NDVI:** Indicates vegetation conditions.
- **NDBI:** Indicates built-up or urbanized characteristics.
- **VIIRS night-time lights:** Serves as a proxy for human activity and urban intensity.
- **Rainfall:** Represents precipitation conditions.
- **Temperature:** Represents atmospheric thermal conditions.
- **Groundwater level:** The principal prediction target, interpreted according to the source dataset's units and measurement convention.

Satellite indicators and environmental variables are indirect predictors. They do not independently measure groundwater depth.

## 🧠 Model Architecture

The proposed model combines CNN-based spatial feature extraction with LSTM-based temporal learning.

```text
Groundwater Observations ──┐
Rainfall and Temperature ──┼──> Temporal Preprocessing
                           │             │
                           │             ▼
                           │        LSTM Branch
                           │             │
                           ▼             │
Satellite Indicators ──> CNN Branch      │
                           │             │
                           └──────┬──────┘
                                  ▼
                           Feature Fusion
                                  │
                                  ▼
                        Groundwater Regression
                                  │
                                  ▼
                     Ward-Level Risk Estimation
                                  │
                                  ▼
                         GIS Dashboard
```

The diagram describes the intended high-level pipeline. The final implementation, input dimensions, training configuration, and model layers should be confirmed against the actual source code.

### CNN Branch

The CNN extracts spatial patterns from available satellite-derived features, such as NDVI, NDBI, and night-time radiance.

### LSTM Branch

The LSTM learns temporal patterns in groundwater observations and environmental variables.

### Feature Fusion

The extracted spatial and temporal representations are combined to estimate groundwater levels.

### Outputs

- Groundwater-level predictions.
- Ward-level estimates where input coverage is sufficient.
- Project-specific groundwater-risk categories.
- Future forecasts when generated by the configured prediction pipeline.

## ⚙️ Methodology

1. **Data collection:** Load the supplied groundwater dataset and acquire other datasets through their supported APIs.
2. **Data inspection:** Identify file formats, column names, units, station coordinates, observation periods, and missing values.
3. **Preprocessing:** Standardize dates and units, assess data quality, and align temporal observations.
4. **Satellite processing:** Derive NDVI and NDBI from appropriate Sentinel-2 bands and process VIIRS radiance data.
5. **Climate processing:** Extract and align rainfall and temperature data.
6. **Spatial association:** Assign monitoring wells to wards using point-in-polygon analysis.
7. **Model training:** Train and validate the CNN-LSTM model using an appropriate temporal evaluation strategy.
8. **Evaluation:** Compare predictions with held-out observations using metrics such as MAE, RMSE, and R².
9. **Spatial estimation:** Estimate groundwater conditions for wards without eligible wells only when the configured interpolation procedure has sufficient nearby observations.
10. **Visualization:** Present ward-level predictions and data-coverage status in the GIS dashboard.

### Missing-Data and Spatial-Estimation Policy

The reported methodology linearly interpolates gaps of up to two months for model inputs only, with interpolated values flagged. Prediction targets are restricted to observed months.

For wards without eligible monitoring wells, the reported pipeline uses inverse-distance weighting (IDW), with up to four nearby wells, power parameter 2, and a maximum radius of 20 km. Distances are computed in UTM Zone 43N. Wards with no eligible wells within the configured radius are marked as having insufficient data.

## 📊 Reported Forecast Summary

The following values were reported for a particular pipeline run and are not independently validated by this README.

| Metric | Reported result |
|---|---:|
| Wards with estimates in 2030 | 239 |
| Wards with insufficient data in 2030 | 4 |
| Critical risk wards in 2030 | 5 |
| High risk wards in 2030 | 17 |
| Medium-High risk wards in 2030 | 55 |
| Medium risk wards in 2030 | 26 |
| Low-Medium risk wards in 2030 | 118 |
| Safe wards in 2030 | 18 |
| Mean forecast depth in 2030 | 35.5 m, wards with data |

The six reported risk classes sum to 239 wards.

**Forecast interpretation:**
- **2025:** Reported as an out-of-sample prediction.
- **2026:** Reported as a forecast within a tested 12-month horizon.
- **2027–2030:** Indicative forecasts beyond the tested horizon.

These forecast statuses should be confirmed from the actual evaluation records. Longer-term projections are subject to uncertainty and assumptions about future environmental conditions.

## 🚦 Risk Categories

The dashboard uses project-specific groundwater-risk categories. These are not official CGWB groundwater assessment classifications.

| Risk category | Score range | Suggested display color |
|---|---:|---|
| Critical | 85–100 | `#8B0000` |
| High | 70–84 | `#D32F2F` |
| Medium-High | 55–69 | `#F57C00` |
| Medium | 40–54 | `#FBC02D` |
| Low-Medium | 25–39 | `#8BC34A` |
| Safe | 0–24 | `#2E7D32` |
| No Data | Not applicable | `#6B7280` |

The score calculation and classification must be consistent with the actual implementation. The labels indicate model-defined risk bands, not guaranteed future groundwater outcomes.

## 🖥️ Technology Stack

The following technologies are intended for the project. Verify the actual versions and installed dependencies before publishing the final environment details.

| Component | Technology |
|---|---|
| Programming language | Python |
| Deep learning | CNN-LSTM |
| Deep-learning framework | Confirm from the implemented environment |
| Data processing | Pandas, NumPy |
| Geospatial analysis | GeoPandas, Shapely, Rasterio, PyProj |
| Scientific data processing | Xarray, h5py, NetCDF4, where required |
| Machine-learning evaluation | Scikit-learn |
| API backend | FastAPI, Uvicorn |
| Frontend | React, Vite, JavaScript |
| Mapping | Leaflet / React Leaflet |
| Charts | Recharts |
| Configuration | Python dotenv |

## 📁 Project Structure

```text
jalajagruti-ai/
├── GroundWaterDataset/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── api/
│   ├── services/
│   ├── ml/
│   └── utils/
├── data/
│   ├── raw/
│   │   ├── sentinel2/
│   │   ├── viirs/
│   │   └── era5/
│   ├── processed/
│   ├── wards/
│   └── predictions/
├── models/
├── frontend/
│   ├── src/
│   └── package.json
├── .env.example
├── .gitignore
└── README.md
```

This is a suggested structure. Adjust it to match the actual repository rather than creating empty folders solely to match this example.

## 🔑 API Configuration

Create a `.env` file in the project root or in the location expected by your application.

```env
COPERNICUS_CLIENT_ID=
COPERNICUS_CLIENT_SECRET=
NASA_EARTHDATA_TOKEN=
CDS_API_KEY=
```

The groundwater dataset is supplied manually in `GroundWaterDataset/`; no groundwater API key is required by this configuration.

### Configuration steps

1. Obtain Copernicus Data Space credentials if required by your selected download API.
2. Configure a NASA Earthdata token for the selected VIIRS download method.
3. Configure Copernicus Climate Data Store access for ERA5-Land.
4. Keep credentials private and out of Git.

Do not commit `.env`, API tokens, passwords, or private datasets to a public repository.

## 🚀 Getting Started

The commands below are a general setup guide. Adapt paths and entry points to the actual project files.

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd jalajagruti-ai
```

### 2. Create a Python virtual environment

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\activate
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

### 3. Install backend dependencies

```bash
pip install -r backend/requirements.txt
```

If your repository uses a different dependency file or Python version, follow its actual setup instructions.

### 4. Add the groundwater dataset

Place your supplied files under:

```text
GroundWaterDataset/
```

Inspect the dataset before training. Confirm its date columns, groundwater variable, units, station coordinates, and quality flags.

### 5. Configure the APIs

Create the `.env` file with the required credentials. Run the data-acquisition pipeline only after verifying that the API configuration and download endpoints match your implementation.

### 6. Start the backend

If `backend/main.py` exposes a FastAPI application named `app`, run:

```bash
uvicorn main:app --reload
```

Run this command from the `backend/` directory. If the application uses a different entry point, replace it with the actual module path.

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the local development URL printed by Vite.

## 📈 Model Evaluation

Use actual held-out predictions and observations to evaluate the model.

- **MAE:** Mean Absolute Error.
- **RMSE:** Root Mean Squared Error.
- **R²:** Coefficient of determination.

Recommended comparisons include persistence and relevant LSTM or CNN baselines, where implemented and scientifically appropriate.

Report the train, validation, and test periods, the number of evaluated stations, and station-level results where possible. Avoid relying solely on pooled metrics because differences in average groundwater depth between wells can affect the interpretation of R².

Do not report metrics unless they are generated by the actual evaluation pipeline.

## ⚠️ Limitations

- Groundwater monitoring stations do not necessarily cover every ward.
- Satellite indicators are indirect proxies and cannot replace direct groundwater measurements.
- Ward-level estimates depend on station coverage and the validity of the interpolation method.
- Longer-term forecasts are subject to model and environmental uncertainty.
- A predicted risk category is not a guarantee of future groundwater depletion.
- The reported forecast counts and mean depth should be rechecked against the final exported results.
- The actual model framework, software versions, and evaluation metrics should be documented from the experimental environment.

## 🔬 Future Work

- Expand the groundwater monitoring dataset.
- Evaluate generalization using held-out stations.
- Quantify prediction uncertainty.
- Compare CNN-LSTM against additional suitable baselines.
- Investigate the contribution of individual environmental and satellite features.
- Improve future environmental-input forecasting.
- Validate predictions against independent observations and other study regions.

## 📚 References and Data Attribution

Cite the research papers, data portals, satellite products, and software documentation used by the implementation. Add the full bibliographic details of the selected base paper and any additional references to the project's paper and documentation.

- [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)
- [NASA VIIRS VNP46A3](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3)
- [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/)
- [National Water Data Portal — Karnataka groundwater telemetry](https://www.nwdp.nwic.gov.in/en/dataset/ground-water-level-telemetry-hourly-karnataka-ground-water-department)
- [BBMP official website](https://bbmp.gov.in/)

Follow the applicable dataset licenses, access conditions, and attribution requirements.

## 👨‍💻 Author

**Project:** JalaJagruti AI  
**Domain:** Deep Learning, Groundwater Prediction, Remote Sensing, GIS  
**Study Area:** Bengaluru, Karnataka, India

## 📄 Disclaimer

JalaJagruti AI is a research and decision-support project. Its predictions and risk maps are intended to support analysis and further investigation, not replace field measurements, official groundwater assessments, or professional water-resource management decisions.

---

*Please verify all reported results, source links, software versions, and project commands against the final repository before publication.*