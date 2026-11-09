$ErrorActionPreference = 'Stop'
$stackRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
& docker compose --project-directory $stackRoot --env-file (Join-Path $stackRoot '.env') -f (Join-Path $stackRoot 'compose.yaml') down
if ($LASTEXITCODE -ne 0) { throw 'Chưa dừng được stack AI.' }
