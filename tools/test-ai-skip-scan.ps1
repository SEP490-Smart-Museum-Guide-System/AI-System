$ErrorActionPreference = 'Stop'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('smgs-skip-scan-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $testRoot 'tools') -Force | Out-Null
$dockerCalls = [Collections.Generic.List[object]]::new()
try {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'start-ai.ps1'), (Join-Path $PSScriptRoot 'AiStackConfig.ps1') -Destination (Join-Path $testRoot 'tools')
    [IO.File]::WriteAllLines((Join-Path $testRoot '.env.example'), @(
        'AI_SYSTEM_DB_PASSWORD=fixture-only', 'AI_SERVICE_API_KEY=', 'SCAN_SERVICE_API_KEY=',
        'AI_CHAT_SERVICE_KEY=', 'AI_TOUR_SERVICE_KEY=', 'TTS_SERVICE_API_KEY=',
        'AI_TTS_PORT=59170', 'AI_VISION_PORT=59171', 'AI_SCAN_PORT=invalid-scan-port',
        'AI_CHAT_PORT=59173', 'AI_TOUR_PORT=59174'
    ))
    Set-Item -Path Function:\docker -Value ({
        $parts = @($args | ForEach-Object { [string]$_ })
        $dockerCalls.Add($parts)
        $global:LASTEXITCODE = 0
        if ($parts[0] -eq 'info') { return 'fixture-docker' }
        if ($parts[0] -eq 'ps' -and ($parts -join ' ') -match 'status=restarting' -and ($parts -join ' ') -match 'service=chat\s') { return 'mock-chat-id' }
    }.GetNewClosure())
    & (Join-Path $testRoot 'tools/start-ai.ps1') -SkipScan -NoBuild
    $up = @($dockerCalls | Where-Object { $_[0] -eq 'compose' -and $_ -contains 'up' })
    if ($up.Count -ne 1) { throw 'Expected one Compose up command.' }
    $selected = @('tts', 'vision', 'chat-model', 'chat', 'tour')
    $tail = @($up[0] | Select-Object -Last 5)
    if (($tail -join ',') -ne ($selected -join ',') -or $up[0] -contains 'scan' -or $up[0] -contains '--build') { throw 'Unexpected service selection or build flag.' }
    if (@($dockerCalls | Where-Object { ($_ -join ' ') -match 'service=scan|mock-scan-id' }).Count) { throw 'Scan was queried or restarted.' }
    if (!@($dockerCalls | Where-Object { $_[0] -eq 'restart' -and $_ -contains 'mock-chat-id' }).Count) { throw 'Selected service recovery was skipped.' }
    Write-Host 'PASS: mocked Docker commands start exactly four APIs plus chat-model, exclude Scan recovery/port, and honor NoBuild.'
} finally {
    Remove-Item -LiteralPath Function:\docker -ErrorAction SilentlyContinue
    $resolved = [IO.Path]::GetFullPath($testRoot)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
    if ([IO.Path]::GetDirectoryName($resolved) -ne $tempRoot -or [IO.Path]::GetFileName($resolved) -notmatch '^smgs-skip-scan-[a-f0-9]{32}$') { throw 'Refusing unsafe test cleanup.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
