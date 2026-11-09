param([string]$Python = '', [int]$Port = 8000, [switch]$GatewayOnly)
$ErrorActionPreference = 'Stop'
$ttsRepo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!$Python) { $Python = Join-Path $ttsRepo '.venv\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $Python)) { throw 'Chưa có Python environment. Xem TTS AI/README.md.' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port không hợp lệ.' }
$previousModelDir = $env:TTS_MODEL_DIR
$previousCacheDir = $env:TTS_CACHE_DIR
$previousServiceKey = $env:TTS_SERVICE_API_KEY
Push-Location -LiteralPath (Join-Path $ttsRepo 'TTS AI')
try {
    $env:TTS_MODEL_DIR = Join-Path $ttsRepo 'state\models\tts'
    $env:TTS_CACHE_DIR = Join-Path $ttsRepo 'state\tts-audio-cache'
    $ttsKeyFile = Join-Path $ttsRepo 'state\tts-service-key.txt'
    if (!(Test-Path -LiteralPath $ttsKeyFile)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $ttsKeyFile) -Force | Out-Null
        [System.IO.File]::WriteAllText($ttsKeyFile, [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)), [System.Text.UTF8Encoding]::new($false))
    }
    $ttsGatewayKey = [System.IO.File]::ReadAllText($ttsKeyFile).Trim()
    if ($ttsGatewayKey.Length -lt 32) { throw 'Khóa dịch vụ TTS local không hợp lệ.' }
    # Default retains the existing loopback FE/Flutter proxy. GatewayOnly requires BE.
    if ($GatewayOnly) { $env:TTS_SERVICE_API_KEY = $ttsGatewayKey }
    Write-Host "TTS tiếng Việt local: http://127.0.0.1:$Port (chỉ trên máy này)."
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Dịch vụ TTS dừng do lỗi.' }
} finally {
    if ($null -eq $previousModelDir) { Remove-Item Env:\TTS_MODEL_DIR -ErrorAction SilentlyContinue }
    else { $env:TTS_MODEL_DIR = $previousModelDir }
    if ($null -eq $previousCacheDir) { Remove-Item Env:\TTS_CACHE_DIR -ErrorAction SilentlyContinue }
    else { $env:TTS_CACHE_DIR = $previousCacheDir }
    if ($null -eq $previousServiceKey) { Remove-Item Env:\TTS_SERVICE_API_KEY -ErrorAction SilentlyContinue }
    else { $env:TTS_SERVICE_API_KEY = $previousServiceKey }
    Pop-Location
}
