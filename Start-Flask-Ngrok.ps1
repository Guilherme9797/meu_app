param(
  [int]$Port = 5000,
  [string]$Domain = "mouramartinsadvogados.ngrok.pro",
  [string]$PythonExe = "python",
  [string]$AdminApiKey = $env:ADMIN_API_KEY
)

function Import-DotEnv([string]$path = ".env") {
  if (-not (Test-Path $path)) { return }
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith("#")) { return }
    $kv = $line -split "=", 2
    if ($kv.Count -eq 2) {
      $name = $kv[0].Trim()
      $val  = $kv[1].Trim().Trim("'`"").Trim()
      [Environment]::SetEnvironmentVariable($name, $val, "Process")
    }
  }
}

Write-Host "== Starting Flask on port $Port =="

# 0) carrega .env (para OPENAI_API_KEY, ADMIN_API_KEY, ZAPI_*)
Import-DotEnv ".env"

# 1) mata ngrok e flask antigos (se houver)
Get-Process ngrok, python -ErrorAction SilentlyContinue | Stop-Process -Force

# 2) sobe o Flask
$flask = Start-Process -FilePath $PythonExe -ArgumentList @(".\server.py") -WorkingDirectory (Get-Location) -PassThru -NoNewWindow

# 3) espera /health local
$ok = $false
for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 4
    if ($h.status -eq "ok" -or $h.checks) { $ok = $true; break }
  } catch {}
}
if (-not $ok) {
  Write-Error "Flask não subiu na porta $Port."
  exit 1
}

# 3.1) inicia ngrok com domínio reservado
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force
$ng = Start-Process ngrok -ArgumentList @("http","--domain=$Domain","$Port") -NoNewWindow -PassThru

# 4) testa /health público (evita ERR_NGROK_8012)
$publicOk = $false
for ($i=0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $pub = Invoke-RestMethod "https://$Domain/health" -TimeoutSec 4
    if ($pub.status -ne $null -or $pub.checks) { $publicOk = $true; break }
  } catch {}
}
if (-not $publicOk) {
  Write-Error "ngrok online, mas upstream falhou (ERR_NGROK_8012). Verifique se o Flask segue rodando e a porta é $Port."
  Write-Host "Dica: abra http://127.0.0.1:4040 para ver os detalhes."
  exit 2
}
Write-Host "🌐 Público OK: https://$Domain/health"

# 5) configura webhooks da Z-API (opcional)
if ($AdminApiKey) {
  try {
    $body = @{ received_url = "https://$Domain/zapi/webhook/received" } | ConvertTo-Json
    Invoke-RestMethod -Method POST `
      -Uri "http://127.0.0.1:$Port/zapi/configure-webhooks" `
      -Headers @{ "X-API-Key" = $AdminApiKey } `
      -ContentType "application/json" `
      -Body $body | Out-Null
    Write-Host "✅ Webhooks configurados em https://$Domain/zapi/webhook/received"
  } catch {
    Write-Warning "Não foi possível configurar webhooks automaticamente: $($_.Exception.Message)"
  }
} else {
  Write-Host "ℹ️  Pulei configuração de webhooks (ADMIN_API_KEY ausente)."
}

Write-Host "Pronto. Flask PID=$($flask.Id) | ngrok PID=$($ng.Id)"
