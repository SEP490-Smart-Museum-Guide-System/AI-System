$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AiStackConfig.ps1')
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('smgs-launcher-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $withoutScan = @(Get-AiStackServices -SkipScan)
    if (($withoutScan -join ',') -ne 'tts,vision,chat-model,chat,tour' -or @(Get-AiStackServices).Count -ne 6) { throw 'Selected service list is incorrect.' }
    $example = @('AI_SYSTEM_DB_PASSWORD=''local test # $ value''', 'AI_SERVICE_API_KEY=replace-with-secret', 'SCAN_SERVICE_API_KEY=', 'TTS_SERVICE_API_KEY=', 'UNCHANGED_SETTING=keep-me')
    [IO.File]::WriteAllLines((Join-Path $testRoot '.env.example'), $example)
    $first = Initialize-AiStackEnv $testRoot
    $chat = Get-AiEnvValue $first 'AI_CHAT_SERVICE_KEY'
    $tour = Get-AiEnvValue $first 'AI_TOUR_SERVICE_KEY'
    if ($tour.Length -lt 32 -or $tour -eq $chat -or $tour -ne [IO.File]::ReadAllText((Join-Path $testRoot 'state/tour-service-key.txt'))) { throw 'Tour key did not sync or is not isolated.' }
    if ($chat.Length -lt 32 -or $chat -ne [IO.File]::ReadAllText((Join-Path $testRoot 'state/chat-service-key.txt'))) { throw 'Chat key did not sync.' }
    $second = Initialize-AiStackEnv $testRoot
    if ($chat -ne (Get-AiEnvValue $second 'AI_CHAT_SERVICE_KEY')) { throw 'Repeated start rotated keys.' }
    if ($tour -ne (Get-AiEnvValue $second 'AI_TOUR_SERVICE_KEY')) { throw 'Repeated start rotated tour key.' }
    if ((Get-AiEnvValue $second 'TTS_SERVICE_API_KEY') -ne '') { throw 'Legacy Visitor TTS compatibility changed.' }
    if ((Get-AiEnvValue $second 'AI_SYSTEM_DB_PASSWORD') -ne 'local test # $ value' -or $second -notcontains 'UNCHANGED_SETTING=keep-me') { throw 'Existing configuration was altered.' }
    if ((Get-AiEnvValue $second 'AI_SERVICE_API_KEY') -eq (Get-AiEnvValue $second 'SCAN_SERVICE_API_KEY')) { throw 'Distinct services share a generated key.' }
    Write-Host 'PASS: setup mới, giữ mật khẩu/cấu hình, khóa riêng, sync BE, chạy lại không đổi khóa và tương thích TTS local.'
} finally {
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ([IO.Path]::GetDirectoryName($resolved) -ne [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/') -or [IO.Path]::GetFileName($resolved) -notmatch '^smgs-launcher-[a-f0-9]{32}$') { throw 'Refusing cleanup outside generated test directory.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
