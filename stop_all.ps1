Set-Content -Path .\stop_all.ps1 -Encoding UTF8 -Value @'
<# 
  stop_all.ps1 — encerra processos do server e do ngrok iniciados pelo start_all.ps1
#>

param([string]$ProjectRoot = "C:\Users\Larissa Moura\Documents\meu_app")
$ErrorActionPreference = "SilentlyContinue"

function stop-by-pidfile($path){
  if (Test-Path $path) {
    $pid = Get-Content $path | ForEach-Object { $_.Trim() } | Select-Object -First 1
    if ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
      Write-Host "Finalizando PID $pid ..." -ForegroundColor Yellow
      Stop-Process -Id $pid -Force
    }
    Remove-Item $path -Force
  }
}

$stateDir = Join-Path $ProjectRoot ".run"
$serverPidFile = Join-Path $stateDir "server.pid"
$ngrokPidFile  = Join-Path $stateDir "ngrok.pid"

stop-by-pidfile $ngrokPidFile
stop-by-pidfile $serverPidFile

Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*\Documents\meu_app\*" } | Stop-Process -Force
Get-Process meu_app_server -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "[ OK ] Encerrado." -ForegroundColor Green
'@
