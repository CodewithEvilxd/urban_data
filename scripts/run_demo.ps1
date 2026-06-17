$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.13 -m venv .venv
    .\.venv\Scripts\pip install --upgrade pip
    .\.venv\Scripts\pip install -r requirements.txt
}

if (-not (Test-Path "node_modules")) {
    npm install
}

if (-not (Test-Path "data\processed\zones_delhi.json")) {
    Write-Host "Running data pipeline (fetch + LST + train)..."
    .\.venv\Scripts\python.exe scripts\fetch_landsat.py
    .\.venv\Scripts\python.exe scripts\calculate_lst.py
    .\.venv\Scripts\python.exe ml\train_classifier.py
}

Write-Host "Starting API on http://127.0.0.1:8095"
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8095" -WindowStyle Minimized

Start-Sleep -Seconds 2
Write-Host "Starting frontend on http://localhost:3000"
npm run dev
