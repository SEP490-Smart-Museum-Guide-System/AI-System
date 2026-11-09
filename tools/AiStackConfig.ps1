function Get-AiEnvValue {
    param([string[]]$Lines, [string]$Name)
    $matched = @($Lines | Where-Object { $_ -match ('^\s*' + [regex]::Escape($Name) + '\s*=') })
    if (!$matched.Count) { return '' }
    $value = ($matched[-1] -split '=', 2)[1].Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"')))) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Initialize-AiStackEnv {
    param([string]$Root)
    $envPath = Join-Path $Root '.env'
    if (!(Test-Path -LiteralPath $envPath)) { Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination $envPath }
    $lines = @(Get-Content -LiteralPath $envPath)
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $statePath = Join-Path $Root 'state'
    New-Item -ItemType Directory -Path $statePath -Force | Out-Null
    foreach ($item in @(
        @{ Name = 'AI_SERVICE_API_KEY'; File = '' },
        @{ Name = 'SCAN_SERVICE_API_KEY'; File = '' },
        @{ Name = 'AI_CHAT_SERVICE_KEY'; File = 'chat-service-key.txt' },
        @{ Name = 'TTS_SERVICE_API_KEY'; File = 'tts-service-key.txt' }
    )) {
        $value = Get-AiEnvValue $lines $item.Name
        $keepBlankTts = $item.Name -eq 'TTS_SERVICE_API_KEY' -and !$value
        $placeholder = !$value -or $value.StartsWith('replace-')
        if ($placeholder) {
            $keyPath = if ($item.File) { Join-Path $statePath $item.File } else { '' }
            $value = if ($keyPath -and (Test-Path -LiteralPath $keyPath)) { [IO.File]::ReadAllText($keyPath).Trim() } else { '' }
            if (!$value) {
                $random = [byte[]]::new(32)
                $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
                try { $generator.GetBytes($random) } finally { $generator.Dispose() }
                $value = [Convert]::ToBase64String($random)
            }
        }
        if ($value.Length -lt 32 -or $value -notmatch '^[A-Za-z0-9_+/=-]+$') { throw "Khóa $($item.Name) cần ít nhất 32 ký tự Base64/Base64URL. Không in khóa ra log." }
        # Blank TTS key keeps the existing local Visitor proxy compatible.
        if (!$keepBlankTts) {
            $pattern = '^\s*' + [regex]::Escape($item.Name) + '\s*='
            if (@($lines | Where-Object { $_ -match $pattern }).Count) { $lines = @($lines | ForEach-Object { if ($_ -match $pattern) { "$($item.Name)=$value" } else { $_ } }) }
            else { $lines += "$($item.Name)=$value" }
        }
        if ($item.File) { [IO.File]::WriteAllText((Join-Path $statePath $item.File), $value, $utf8) }
    }
    [IO.File]::WriteAllLines($envPath, [string[]]$lines, $utf8)
    $password = Get-AiEnvValue $lines 'AI_SYSTEM_DB_PASSWORD'
    if (!$password -or $password.StartsWith('replace-')) { throw 'Đã chuẩn bị .env và khóa nội bộ. Mở .env, điền AI_SYSTEM_DB_* giống PostgreSQL của BE rồi chạy lại lệnh này. Không cần tự tạo database mới.' }
    return ,$lines
}
