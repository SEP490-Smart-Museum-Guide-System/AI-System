[CmdletBinding()]
param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AiStackConfig.ps1')
$scanStackRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$null = Initialize-AiStackEnv $scanStackRoot
$scanArgs = @('compose', '--project-directory', $scanStackRoot, '--env-file', (Join-Path $scanStackRoot '.env'), '-f', (Join-Path $scanStackRoot 'compose.yaml'), 'up', '-d', '--wait', '--wait-timeout', '180')
if (!$NoBuild) { $scanArgs += '--build' }
$scanArgs += 'scan'
& docker @scanArgs
if ($LASTEXITCODE -ne 0) { throw 'Scan chưa ready. Kiểm tra Docker, cấu hình PostgreSQL và docker compose logs scan.' }
Write-Host 'Scan CPU ready. Tiếp theo chạy Backend với AiScan:BaseUrl và AiScan:ServiceKey, rồi mở FE.'
