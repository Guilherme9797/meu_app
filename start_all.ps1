cd "C:\Users\Larissa Moura\Documents\meu_app"
Set-Content -Path .\start_all.ps1 -Encoding UTF8 -Value @'
<# 
  start_all.ps1
  Sobe server (python ou exe), abre ngrok com domínio reservado, checa /health e configura webhook da Z-API.
  Use:
    Set-ExecutionPolicy -Scope Process Bypass
    .\start_all.ps1 -AdminApiKey "SUA_CHAVE" -NgrokDomain "mouramartinsadvogados.ngrok.pro"
#>

param(
  [string]$ProjectRoot = "C:\Users\Larissa Moura\Documents\meu_app",
  [switch]$UseExe = $false,
  [int]$Port = 5000,
  [string]$NgrokDomain = "mouramartinsadvogados.ngrok.pro",
  [string]$NgrokToken = "",
  [string]$AdminApiKey = "",
  [string]$DeliveryWebhook = ""
)

$ErrorActionPreference = "Stop"
function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg){ Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Write-Warn($msg){ Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[ERR ] $msg" -ForegroundColor Red }

$stateDir = Join-Path $ProjectRoot ".run"
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$serverPidFile = Join-Path $stateDir "server.pid"
$ngrokPidFile  = Join-Path $stateDir "ngrok.pid"

if ($UseExe) {
  $exePath = Join-Path (Join-Path $ProjectRoot "dist") "meu_app_server.exe"
  if (-not (Test-Path $exePath)) { Write-Err "EXE não encontrado: $exePath"; exit 1 }
} else {
  $serverPy = Join-Path $ProjectRoot "server.py"
  if (-not (Test-Path $serverPy)) { Write-Err "server.py não encontrado em $ProjectRoot"; exit 1 }
}

Write-Info "Iniciando servidor na porta $Port ..."
Push-Location $ProjectRoot
try {
  if ($UseExe) {
    $serverProc = Start-Process -FilePath (Join-Path $ProjectRoot "dist\meu_app_server.exe") -PassThru
  } else {
    $serverProc = Start-Process -FilePath "python" -ArgumentList "server.py" -WorkingDirectory $ProjectRoot -PassThru
  }
  $serverProc.Id | Out-File -FilePath $serverPidFile -Encoding ascii
  $ok = $false
  for ($i=0; $i -lt 40; $i++){
    try { $res = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2; if ($res) { $ok = $true; break } }
    catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $ok) { Write-Err "Servidor não respondeu em http://127.0.0.1:$Port/health"; throw "No health" }
  Write-Ok "Servidor OK em http://127.0.0.1:$Port"
} catch {
  Pop-Location
  Write-Err "Falha ao iniciar o servidor. Detalhe: $($_.Exception.Message)"
  if ($serverProc) { try { Stop-Process -Id $serverProc.Id -Force } catch {} }
  exit 1
}
Pop-Location

Write-Info "Abrindo ngrok com domínio $NgrokDomain → porta $Port ..."
try {
  if ($NgrokToken) { & ngrok config add-authtoken $NgrokToken | Out-Null }
  $ngrokArgs = @("http", "--domain=$NgrokDomain", "$Port")
  $ngrokProc = Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs -PassThru
  $ngrokProc.Id | Out-File -FilePath $ngrokPidFile -Encoding ascii

  $public = "https://$NgrokDomain"
  $ok = $false
  for ($i=0; $i -lt 40; $i++){
    try { $res = Invoke-RestMethod "$public/health" -TimeoutSec 3; if ($res) { $ok = $true; break } }
    catch { Start-Sleep -Milliseconds 750 }
  }
  if (-not $ok) { Write-Err "Endpoint público ainda offline: $public/health"; throw "Ngrok offline" }
  Write-Ok "Público OK em $public"
} catch {
  Write-Err "Falha ao iniciar/validar ngrok. Detalhe: $($_.Exception.Message)"
  Write-Warn "Verifique se o domínio $NgrokDomain está reservado para sua conta no dashboard do ngrok."
  Write-Warn "Você pode deixar o server rodando localmente; execute manualmente: ngrok http --domain=$NgrokDomain $Port"
}

if (-not $AdminApiKey) {
  Write-Warn "AdminApiKey não fornecida. Pulei a configuração automática do webhook."
} else {
  Write-Info "Configurando webhook Z-API para received_url=$public/zapi/webhook/received ..."
  try {
    $headers = @{ "X-API-Key" = $AdminApiKey }
    $body = @{ received_url = "$public/zapi/webhook/received" }
    if ($DeliveryWebhook) { $body["delivery_url"] = $DeliveryWebhook }
    $json = $body | ConvertTo-Json
    $resp = Invoke-RestMethod -Method POST -Uri "$public/zapi/configure-webhooks" -Headers $headers -ContentType "application/json" -Body $json -TimeoutSec 10
    Write-Ok "Webhook configurado: $(($resp | ConvertTo-Json -Depth 5))"
  } catch {
    Write-Err "Falha ao configurar webhook Z-API. Detalhe: $($_.Exception.Message)"
    Write-Warn "Cheque a ADMIN_API_KEY do .env e tente:"
    Write-Warn 'Invoke-RestMethod -Method POST -Uri "'+$public+'/zapi/configure-webhooks" -Headers @{ "X-API-Key" = "SUA_CHAVE" } -ContentType "application/json" -Body ( @{ received_url = "'+$public+'/zapi/webhook/received" } | ConvertTo-Json )'
  }
}

Write-Host ""
Write-Ok "Tudo pronto!"
Write-Host "  Local:   http://127.0.0.1:$Port/health"
Write-Host "  Público: https://$NgrokDomain/health"
Write-Host "  Server PID: $(Get-Content $serverPidFile)"
if (Test-Path $ngrokPidFile) { Write-Host "  Ngrok  PID: $(Get-Content $ngrokPidFile)" }
Write-Host ""
Write-Host "Para encerrar, rode: .\stop_all.ps1" -ForegroundColor Yellow
'@
