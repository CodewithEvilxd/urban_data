# Daily Data Automation

This folder is for scheduled satellite refresh jobs.

## What it does

`daily_update.py` runs the existing city pipeline:

1. Downloads the latest available Landsat scene for each city.
2. Rebuilds LST and `data/processed/zones_<city>.json`.
3. Optionally retrains the India-wide ML model.
4. Writes `data/processed/daily_update_state.json`.
5. Commits changed data files.
6. Optionally pushes the commit to GitHub.

Landsat is not daily for every place. If no newer clear scene exists, the job may run successfully with no meaningful data change.

## Local run

```powershell
tools\python312\python.exe automation\daily_update.py --cities greater-noida noida new-delhi --retrain-model
```

Friendly all-city command:

```powershell
tools\python312\python.exe scripts\refresh_latest_data.py
```

Push changes after the run:

```powershell
tools\python312\python.exe automation\daily_update.py --cities greater-noida noida new-delhi --retrain-model --push
```

## Render Cron

Use `automation/render-cron.yaml` as the Render cron service example.

Required environment variables on Render:

- `GITHUB_TOKEN`: GitHub personal access token with repository contents read/write access.
- `GITHUB_REPOSITORY`: repo name in `owner/repo` format.
- `GIT_BRANCH`: branch to push, usually `main`.
- `DAILY_CITIES`: optional comma-separated city slugs. Leave unset/blank to process every city in `data/city_registry.json`.
- `PUSH_CHANGES`: set to `true`.

Optional:

- `RETRAIN_MODEL=true`: retrain India model after refresh.
- `INCLUDE_RASTERS=true`: force-add raw `.TIF` and LST rasters to git.
- `SKIP_SEED=true`: skip DB seeding during cron.

## Raw Raster Warning

Raw Landsat `.TIF` files can be very large. GitHub rejects normal files over 100 MB. Keep `INCLUDE_RASTERS=false` unless you use Git LFS or a separate object store.

Recommended default for GitHub:

- Commit `data/processed/*.json`.
- Commit model metrics/summary files.
- Do not commit raw `.TIF` rasters.

## All Cities Automatically

Do not set `DAILY_CITIES` if you want automatic coverage. The cron job will read
`data/city_registry.json` on every run, so any city added later is included
without changing the automation config.

## Free Render Web Service Mode

If Render Cron is not available on your plan, deploy the full repo as a Render
Web Service using the root `render.yaml`. It points Render at the `backend`
folder.

Use these settings:

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Set these Render env vars:

```text
DATA_BACKEND=json
GITHUB_REPOSITORY=CodewithEvilxd/urban_data
GIT_BRANCH=main
PUSH_CHANGES=true
RETRAIN_MODEL=true
SKIP_SEED=true
INCLUDE_RASTERS=false
GITHUB_TOKEN=<your token>
AUTOMATION_SECRET=<make a long random secret>
```

Manual update endpoints:

- Trigger daily data update manually when needed:
  `https://YOUR-RENDER-APP.onrender.com/api/automation/daily-update?secret=YOUR_AUTOMATION_SECRET`
- Check update status:
  `https://YOUR-RENDER-APP.onrender.com/api/automation/status?secret=YOUR_AUTOMATION_SECRET`

Do not share the automation URL publicly because it can start a heavy data job.
