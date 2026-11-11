[CmdletBinding()]
param([switch]$CheckOnly, [switch]$NoBuild, [switch]$SkipScan, [ValidateRange(60, 3600)][int]$WaitTimeoutSeconds = 1200)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AiStackConfig.ps1')
$stackRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Cần cài Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose (Linux).' }
& docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker chưa chạy. Mở Docker Desktop, chờ engine sẵn sàng rồi chạy lại.' }
$lines = Initialize-AiStackEnv $stackRoot
$selectedServices = @(Get-AiStackServices -SkipScan:$SkipScan)
$apiCount = if ($SkipScan) { 4 } else { 5 }
$compose = @('compose', '--project-directory', $stackRoot, '--env-file', (Join-Path $stackRoot '.env'), '-f', (Join-Path $stackRoot 'compose.yaml'))
& docker @compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Cấu hình Compose không hợp lệ. Kiểm tra .env; không chia sẻ nội dung có mật khẩu/khóa.' }
if ($CheckOnly) { Write-Host "PASS: cấu hình $apiCount API AI + bước tải model Chat hợp lệ. Dịch vụ được chọn: $($selectedServices -join ', '). Chưa khởi động dịch vụ."; exit 0 }
$owned = (& docker ps --filter 'label=com.docker.compose.project=smgs-ai' --format '{{.Ports}}') -join ' '
$ports = @{}
foreach ($entry in @(@('TTS', 'AI_TTS_PORT', 8000), @('Vision', 'AI_VISION_PORT', 8001), @('3D Scan', 'AI_SCAN_PORT', 8002), @('Chat / Xưởng AI', 'AI_CHAT_PORT', 8003), @('Tour cá nhân', 'AI_TOUR_PORT', 8004))) {
    if ($SkipScan -and $entry[1] -eq 'AI_SCAN_PORT') { continue }
    $configured = Get-AiEnvValue $lines $entry[1]
    $port = if ($configured) { 0 } else { [int]$entry[2] }
    if ($configured -and (![int]::TryParse($configured, [ref]$port) -or $port -lt 1024 -or $port -gt 65535)) { throw "Port $($entry[1]) không hợp lệ." }
    if ($ports.ContainsKey($port)) { throw 'Các dịch vụ cần dùng các port khác nhau.' }
    $ports[$port] = $entry[0]
    $client = [Net.Sockets.TcpClient]::new()
    try {
        try { $client.Connect('127.0.0.1', $port) } catch [Net.Sockets.SocketException] { }
        if ($client.Connected -and $owned -notmatch (':'+$port+'->')) { throw "Port $port đang được dịch vụ khác sử dụng. Dừng bản AI chạy riêng hoặc đổi $($entry[1]) trong .env. Script không tự tắt tiến trình khác." }
    } finally { $client.Dispose() }
}
Write-Host "Khởi động: $($selectedServices -join ', '). Lần đầu cần tải image/model; các lần sau dùng cache."
$recover = @(foreach ($service in $selectedServices) {
    & docker ps --filter 'label=com.docker.compose.project=smgs-ai' --filter "label=com.docker.compose.service=$service" --filter 'status=restarting' --format '{{.ID}}'
})
if ($recover.Count) {
    # Only failed processes owned by this stack; do not restart healthy workers/jobs.
    Write-Host 'Khởi động lại process AI của stack đang restart-loop sau lỗi dependency trước đó.'
    & docker restart @recover | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Chưa khởi động lại được process AI bị lỗi.' }
}
$up = @('up', '--detach', '--wait', '--wait-timeout', "$WaitTimeoutSeconds")
if (!$NoBuild) { $up += '--build' }
$up += $selectedServices
& docker @compose @up
if ($LASTEXITCODE -ne 0) {
    & docker @compose ps
    throw 'Một dịch vụ chưa ready. Chạy docker compose logs --tail 80 <tts|vision|scan|chat|chat-model|tour>; kiểm tra PostgreSQL, Internet, RAM và port. Những dịch vụ đã lên vẫn được giữ để xem log.'
}
foreach ($port in ($ports.Keys | Sort-Object)) { Write-Host "$($ports[$port]): http://127.0.0.1:$port/ready" }
Write-Host "Tất cả $apiCount API đã ready."
if ($SkipScan) { Write-Host 'Không build/start/restart Scan và không kiểm tra cổng 8002. Container Scan đã chạy từ trước được giữ nguyên; cờ này không tự dừng nó.' }
else { Write-Host 'API 3D ready không khẳng định dựng được mesh: dense reconstruction của pipeline hiện tại cần bản COLMAP hỗ trợ GPU/CUDA.' }
if ($SkipScan) { Write-Host 'Dừng riêng nhóm này: docker compose stop tts vision chat tour. Xem trạng thái: docker compose ps -a tts vision chat-model chat tour' }
else { Write-Host 'Dừng: docker compose down (giữ model/cache/job). Xem trạng thái: docker compose ps' }
