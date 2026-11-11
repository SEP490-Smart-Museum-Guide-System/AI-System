param([string]$Python = '', [int]$Port = 8004)
$ErrorActionPreference = 'Stop'
$tourRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!$Python) { $Python = Join-Path $tourRoot '.venv\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $Python)) { throw 'Cần Python environment; xem AI Tour/README.md.' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port không hợp lệ.' }
$tourKeyFile = Join-Path $tourRoot 'state\tour-service-key.txt'
if (!(Test-Path -LiteralPath $tourKeyFile)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $tourKeyFile) -Force | Out-Null
    $bytes = [byte[]]::new(32)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [IO.File]::WriteAllText($tourKeyFile, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
}
$previous = $env:AI_TOUR_SERVICE_KEY
Push-Location -LiteralPath (Join-Path $tourRoot 'AI Tour')
try {
    $env:AI_TOUR_SERVICE_KEY = [IO.File]::ReadAllText($tourKeyFile).Trim()
    if ($env:AI_TOUR_SERVICE_KEY.Length -lt 32) { throw 'Khóa nội bộ không hợp lệ.' }
    Write-Host "Gợi ý tour cá nhân: http://127.0.0.1:$Port/ready"
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Dịch vụ tour dừng do lỗi.' }
} finally { $env:AI_TOUR_SERVICE_KEY = $previous; Pop-Location }
