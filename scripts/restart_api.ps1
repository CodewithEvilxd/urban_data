$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$port = 8095
Write-Host "Stopping any process on port $port..."
Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Write-Host "Starting UrbanCool API on http://127.0.0.1:$port"
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","api.main:app","--host","127.0.0.1","--port","$port" `
  -WindowStyle Normal

Start-Sleep -Seconds 4
try {
  $r = Invoke-RestMethod "http://127.0.0.1:$port/api/live?city=delhi"
  Write-Host "API OK - zones:" $r.zone_count "LST:" $r.mean_lst
} catch {
  Write-Host "API starting... refresh browser in a few seconds"
}
