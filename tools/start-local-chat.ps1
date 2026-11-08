param([string]$Python = '', [int]$Port = 8003, [switch]$DownloadModel)
$ErrorActionPreference = 'Stop'
$chatRepo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!$Python) { $Python = Join-Path $chatRepo '.venv\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $Python)) { throw 'Chưa có Python environment. Xem AI Chat/README.md.' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port không hợp lệ.' }
Push-Location -LiteralPath $chatRepo
$previousChatKey = $env:AI_CHAT_SERVICE_KEY
try {
    if ($DownloadModel) {
        & $Python tools/download_chat_model.py
        if ($LASTEXITCODE -ne 0) { throw 'Không tải được model chatbot.' }
    }
    $keyFile = Join-Path $chatRepo 'state\chat-service-key.txt'
    if (!(Test-Path -LiteralPath $keyFile)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $keyFile) -Force | Out-Null
        $key = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
        [System.IO.File]::WriteAllText($keyFile, $key, [System.Text.UTF8Encoding]::new($false))
    }
    $env:AI_CHAT_SERVICE_KEY = [System.IO.File]::ReadAllText($keyFile).Trim()
    if ($env:AI_CHAT_SERVICE_KEY.Length -lt 32) { throw 'Khóa chatbot local không hợp lệ.' }
    Write-Host "Chatbot ONNX local: http://127.0.0.1:$Port (chỉ trên máy này; key không được in)."
    Set-Location -LiteralPath (Join-Path $chatRepo 'AI Chat')
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Dịch vụ chatbot dừng do lỗi.' }
} finally {
    if ($null -eq $previousChatKey) { Remove-Item Env:\AI_CHAT_SERVICE_KEY -ErrorAction SilentlyContinue }
    else { $env:AI_CHAT_SERVICE_KEY = $previousChatKey }
    Pop-Location
}
