# UrbanCool Quick Start

A minimal quick-start README for local development and running the app.

## 1. Create Python virtual environment

```powershell
cd c:\Users\Nishant Gaurav\Downloads\isro
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## 2. Install optional USGS fallback support

`landsatxplore` is only needed for `--method usgs`.

```powershell
.\.venv\Scripts\python -m pip install landsatxplore
```

## 3. Run the backend API

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload
```

Default API URL:

- http://localhost:8000

## 4. Run frontend locally

```powershell
npm install
npm run dev
```

Default frontend URL:

- http://localhost:3000

## 5. Run the Landsat data pipeline

### Planetary Computer download (default)

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/fetch_landsat.py
python scripts/calculate_lst.py
python ml/train_classifier.py
python api/seed_db.py
```

### USGS download fallback (optional)

Set credentials and run:

```powershell
$env:USGS_USERNAME="your_user"
$env:USGS_PASSWORD="your_pass"
.\.venv\Scripts\Activate.ps1
python scripts/fetch_landsat.py --method usgs
```

## 6. Quick run commands

```powershell
# Activate environment
.\.venv\Scripts\Activate.ps1

# Run API
uvicorn api.main:app --reload

# Run frontend
npm run dev

# Fetch Landsat + process pipeline
python scripts/fetch_landsat.py
python scripts/calculate_lst.py
python ml/train_classifier.py
python api/seed_db.py
```

## 7. Notes

- The default data download path is the **Microsoft Planetary Computer** STAC endpoint.
- `landsatxplore` is only required for the `usgs` method.
- Use Python 3.12 for the local `.venv` to avoid dependency issues with `landsatxplore` and `shapely`.
# New Folder Layout

Backend:
```powershell
cd backend
tools\python312\python.exe -m uvicorn api.main:app --reload
```

Frontend:
```powershell
cd frontend
npm run dev
```

Render uses root `render.yaml` with `rootDir: backend`.

Latest data refresh for all cities:
```powershell
cd backend
tools\python312\python.exe scripts\refresh_latest_data.py
```

Refresh and push changed data:
```powershell
cd backend
tools\python312\python.exe scripts\refresh_latest_data.py --push
```
