param([string]$Python = '', [switch]$IncludeDatabaseTests)

$ErrorActionPreference = 'Stop'
$aiRepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $aiRepoRoot '.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $Python)) { $Python = 'python' }
}
$previousDatabaseFlag = $env:AI_RUN_DB_TESTS
try {
    $env:AI_RUN_DB_TESTS = if ($IncludeDatabaseTests) { '1' } else { '0' }
    foreach ($aiService in @('TTS AI', 'AI Vision', '3D Scan', 'AI Chat')) {
        Write-Host "Kiểm thử: $aiService"
        Push-Location -LiteralPath (Join-Path $aiRepoRoot $aiService)
        try {
            & $Python -m unittest discover -s tests -v
            if ($LASTEXITCODE -ne 0) { throw "Kiểm thử $aiService thất bại." }
        } finally { Pop-Location }
    }
} finally {
    if ($null -eq $previousDatabaseFlag) { Remove-Item Env:\AI_RUN_DB_TESTS -ErrorAction SilentlyContinue }
    else { $env:AI_RUN_DB_TESTS = $previousDatabaseFlag }
}
