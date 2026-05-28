# Start the hotel voice assistant webhook server (demo + transcribe).
# Usage: .\scripts\start_server.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$listeners = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $listeners) {
    Write-Host "Stopping process $($c.OwningProcess) on port 8080..."
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

Write-Host "Starting server at http://127.0.0.1:8080/demo/"
python -m adk_spanish_hotel_voice_assistant --serve-webhook --production
