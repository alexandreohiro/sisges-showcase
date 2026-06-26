param(
    [string]$FrontendRoot = $(if ($env:SISGES_FRONTEND_PATH) { $env:SISGES_FRONTEND_PATH } else { "..\web-sisges-v0" }),
    [string]$FrontendUrl = "http://localhost:3001",
    [string]$BackendUrl = "http://localhost:3031",
    [switch]$Build,
    [switch]$AuthSmoke
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )

    $results.Add([pscustomobject]@{
        Name = $Name
        Status = $Status
        Detail = $Detail
    })
}

function Invoke-Step {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command,
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "==> $Name"
    Write-Host "$Command $($Arguments -join ' ')"

    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            Add-Result $Name "FAIL" "Exit code $LASTEXITCODE"
            throw "$Name falhou com exit code $LASTEXITCODE"
        }
        Add-Result $Name "OK" "Concluido"
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $Python)) {
    throw "Python virtualenv nao encontrado em $Python"
}

if (-not (Test-Path $FrontendRoot)) {
    throw "FrontendRoot nao encontrado em $FrontendRoot"
}

Write-Host "SISGES - Gate Operacional Fullstack"
Write-Host "Backend root:  $ProjectRoot"
Write-Host "Frontend root: $FrontendRoot"
Write-Host "Frontend URL:  $FrontendUrl"
Write-Host "Backend URL:   $BackendUrl"

Invoke-Step `
    -Name "LAN health/CORS/routes" `
    -WorkingDirectory $ProjectRoot `
    -Command "powershell" `
    -Arguments @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ".\scripts\validate_sisges_lan.ps1",
        "-FrontendUrl",
        $FrontendUrl,
        "-BackendUrl",
        $BackendUrl
    )

Invoke-Step `
    -Name "Backend lint Folhas" `
    -WorkingDirectory $ProjectRoot `
    -Command $Python `
    -Arguments @(
        "-m",
        "ruff",
        "check",
        "apps\web\app.py",
        "apps\web\routes\folhas.py"
    )

Invoke-Step `
    -Name "Backend tests Folhas" `
    -WorkingDirectory $ProjectRoot `
    -Command $Python `
    -Arguments @(
        "-m",
        "pytest",
        "tests\test_complete_folha_semi_ok_parte1.py",
        "tests\test_documents_semi_ok_parte1_route.py",
        "tests\test_folhas_workflow.py",
        "tests\test_folhas_document_update.py"
    )

Invoke-Step `
    -Name "Backend tests Gestao" `
    -WorkingDirectory $ProjectRoot `
    -Command $Python `
    -Arguments @(
        "-m",
        "pytest",
        "tests\test_operational_crud.py",
        "tests\test_inspect_militar_trash_archive.py",
        "tests\test_tempo_servico_context.py",
        "tests\unit\test_gestao_pessoal_compilador_context.py",
        "tests\unit\test_gestao_pessoal_pdf_importer.py"
    )

Invoke-Step `
    -Name "Frontend operational contracts" `
    -WorkingDirectory $FrontendRoot `
    -Command "npm.cmd" `
    -Arguments @("run", "validate:operational")

Invoke-Step `
    -Name "Frontend local routes" `
    -WorkingDirectory $FrontendRoot `
    -Command "npm.cmd" `
    -Arguments @("run", "validate:routes:local", "--", "--base-url=$FrontendUrl")

if ($AuthSmoke) {
    Invoke-Step `
        -Name "Folhas authenticated smoke" `
        -WorkingDirectory $FrontendRoot `
        -Command "npm.cmd" `
        -Arguments @("run", "validate:folhas-auth-smoke")
}

if ($Build) {
    Invoke-Step `
        -Name "Frontend build" `
        -WorkingDirectory $FrontendRoot `
        -Command "npm.cmd" `
        -Arguments @("run", "build")
}

Write-Host ""
$results | Format-Table -AutoSize

$failed = $results | Where-Object { $_.Status -ne "OK" }
if ($failed) {
    Write-Host ""
    Write-Host "GATE OPERACIONAL: FALHA"
    exit 1
}

Write-Host ""
Write-Host "GATE OPERACIONAL: OK"
