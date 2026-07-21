# Phase 1 bronze: meta + sample station days
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    python -m venv .venv
    .\.venv\Scripts\pip.exe install -r requirements.txt
}

.\.venv\Scripts\python.exe -m src.ingest.download_ghcnd_meta
# Long-record USW/USC with TMAX+TMIN+PRCP; --list-only first if you only want to preview
.\.venv\Scripts\python.exe -m src.ingest.download_station_days --states SC,NC,GA --max-stations 15

Write-Host "Phase 1 bronze complete. See data/bronze and data/meta manifests."
