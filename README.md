# UrbanCool

Urban heat island detection and cooling advisory for Indian cities, built on Landsat 8/9 Collection 2 thermal imagery.

## Stack

- **Data / ML:** Python 3.11+ (tested on 3.13), FastAPI, rasterio, scikit-learn
- **Database:** PostgreSQL + PostGIS (SQLAlchemy + GeoAlchemy2)
- **Frontend:** Next.js 14, TypeScript, TailwindCSS, Leaflet, Recharts
- **Deploy:** Vercel (frontend), Render (API + Postgres)

## Prerequisites

- Python 3.11 or newer
- Node.js 18+
- PostgreSQL 14+ with PostGIS (or use `docker compose up -d`)
- Optional: USGS EarthExplorer account for alternative download path

## Setup

```bash
# Python environment
py -3.13 -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# Frontend
npm install
cp .env.example .env.local      # set NEXT_PUBLIC_API_URL
```

### PostgreSQL + PostGIS

```bash
docker compose up -d
# or manually:
# CREATE DATABASE urbancool;
# \c urbancool
# CREATE EXTENSION postgis;
```

Set `DATABASE_URL` in `.env` (backend only — never put this in `.env.local` or `NEXT_PUBLIC_*`).

```bash
python api/seed_db.py
```

### Area search

The dashboard search bar supports 25+ Delhi NCR localities (Connaught Place, Saket, Dwarka, Gurgaon, Noida, etc.). Type a name, click **Go** — the map flies there and opens the nearest heat zone from PostGIS.

### 2D + 3D visualization

- **2D view:** fast operational grid map (Leaflet).
- **3D view:** interactive heat volume extrusion (Deck.gl + MapLibre) where column height scales with LST.

## ML model (not LLMs)

Landsat pixels are trained with **scikit-learn** (Random Forest + Gradient Boosting ensemble), not LLMs. LLMs cannot replace radiometric LST math or spectral band processing. The improved model uses:

- 7 spectral/spatial features (NDVI, NDBI, built-up proxy, impervious fraction, water distance, lat/lon)
- Hyperparameter-tuned Random Forest + HistGradientBoosting voting ensemble
- 5-fold cross-validation metrics saved to `ml/models/model_metrics.json`

## Data pipeline (run in order)

Primary download uses **Microsoft Planetary Computer** (no credentials):

```bash
python scripts/fetch_landsat.py
python scripts/fetch_landsat.py --bbox 77.5,12.9,77.8,13.2   # other cities
python scripts/calculate_lst.py
python ml/train_classifier.py
python api/seed_db.py
```

One-command demo setup:

```bash
make pipeline    # fetch + LST + train
make seed        # load zones into PostGIS
```

Or on Unix: `bash scripts/setup.sh`

**Windows one-click demo:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1
```

### USGS M2M alternative

Free signup at [ers.cr.usgs.gov](https://ers.cr.usgs.gov). Set credentials:

```bash
export USGS_USERNAME=your_user
export USGS_PASSWORD=your_pass
python scripts/fetch_landsat.py --method usgs
# requires: pip install landsatxplore
```

## Run locally

```bash
# API (port 8000)
uvicorn api.main:app --reload

# Frontend (port 3000)
npm run dev
```

Open http://localhost:3000

Without PostgreSQL, the API serves zones from `data/processed/zones_delhi.json` (read-only fallback for local UI testing).

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/zones?city=delhi` | GeoJSON heat zone grid |
| GET | `/api/zones/{zone_id}` | Zone detail + interventions |
| POST | `/api/simulate` | NDVI what-if class prediction |
| POST | `/api/scenarios/optimize` | Budget-aware intervention portfolio (physics-informed AIML) |
| GET | `/api/zones/{zone_id}/drivers` | Top drivers (local attribution) for high/critical risk |
| GET | `/api/stats?city=delhi` | City summary + LST trend |

## Verified Delhi NCR run (2026-06-09 scene)

- Scene: `LC81470402026160LGN00` (Landsat 8, 0% cloud)
- Mean LST: **40.18°C** (range 30–49°C) — plausible for June Delhi
- Classifier accuracy: **88%** on held-out grid cells
- 11,039 grid cells at ~500 m resolution

## Deployment

**Render:** push repo, connect `render.yaml`, set `CORS_ORIGINS` to your Vercel URL.

**Vercel:** set `NEXT_PUBLIC_API_URL` to the Render API URL.

## Project structure

```
scripts/fetch_landsat.py    # Planetary Computer / USGS download
scripts/calculate_lst.py    # Single-channel LST from thermal radiance
ml/train_classifier.py      # Random Forest heat zone model
ml/recommend.py             # Rule-based cooling interventions
api/main.py                 # FastAPI endpoints
components/                 # Next.js dashboard
data/raw/                   # Downloaded Landsat bands
data/processed/             # LST GeoTIFF + zone JSON
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | For PostGIS | PostgreSQL connection string |
| `NEXT_PUBLIC_API_URL` | Frontend | API base URL |
| `USGS_USERNAME` | USGS path only | EarthExplorer username |
| `USGS_PASSWORD` | USGS path only | EarthExplorer password |
| `CORS_ORIGINS` | Production API | Comma-separated allowed origins |
