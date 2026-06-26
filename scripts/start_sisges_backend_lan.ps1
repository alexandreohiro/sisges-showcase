param(
    [int]$Port = 3031,
    [string]$HostAddress = "0.0.0.0",
    [string]$FrontendOrigins = "http://localhost:3001,http://127.0.0.1:3001,http://192.168.0.109:3001,http://10.67.171.173:3001",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python virtualenv nao encontrado em $Python"
}

Set-Location $ProjectRoot
$env:SISGES_FRONTEND_ORIGINS = $FrontendOrigins

$argsList = @(
    "-m",
    "uvicorn",
    "apps.web.app:app",
    "--host",
    $HostAddress,
    "--port",
    [string]$Port
)

if (-not $NoReload) {
    $argsList += "--reload"
}

Write-Host "SISGES backend"
Write-Host "Root: $ProjectRoot"
Write-Host "URL:  http://localhost:$Port"
Write-Host "LAN:  http://<ip-da-maquina>:$Port"
Write-Host "CORS: $FrontendOrigins"
& $Python @argsList
