$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$bindAddress = $env:UVICORN_HOST
if (-not $bindAddress) {
    $bindAddress = "127.0.0.1"
}

python -m uvicorn app.main:app --host $bindAddress --port 8000 --workers 1 --loop asyncio --ws-ping-interval 20 --ws-ping-timeout 20
exit $LASTEXITCODE
