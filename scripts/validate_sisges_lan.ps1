param(
    [string]$FrontendUrl = "http://localhost:3001",
    [string]$BackendUrl = "http://localhost:3031",
    [string[]]$CorsOrigins = @(
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://192.168.0.109:3001",
        "http://10.67.171.173:3001"
    )
)

$ErrorActionPreference = "Stop"
$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Check,
        [string]$Status,
        [string]$Detail
    )

    $results.Add([pscustomobject]@{
        Check = $Check
        Status = $Status
        Detail = $Detail
    })
}

function Test-PortListening {
    param(
        [int]$Port,
        [string]$Name
    )

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        if ($listeners) {
            $pids = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ","
            Add-Result $Name "OK" "Porta ${Port} ouvindo. PID(s): $pids"
            return
        }
    } catch {
        Add-Result $Name "FAIL" "Porta ${Port} sem listener: $($_.Exception.Message)"
        return
    }

    Add-Result $Name "FAIL" "Porta ${Port} sem listener."
}

function Test-HttpGet {
    param(
        [string]$Uri,
        [string]$Name,
        [string]$ExpectedText = ""
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 10
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
            Add-Result $Name "FAIL" "HTTP $($response.StatusCode)"
            return
        }

        if ($ExpectedText -and -not ($response.Content -like "*$ExpectedText*")) {
            Add-Result $Name "FAIL" "HTTP $($response.StatusCode), mas texto esperado ausente: $ExpectedText"
            return
        }

        Add-Result $Name "OK" "HTTP $($response.StatusCode)"
    } catch {
        Add-Result $Name "FAIL" $_.Exception.Message
    }
}

function Test-CorsOrigin {
    param(
        [string]$Origin
    )

    try {
        $headers = @{
            Origin = $Origin
            "Access-Control-Request-Method" = "GET"
        }
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$BackendUrl/health" -Method Options -Headers $headers -TimeoutSec 10
        $allowed = $response.Headers["Access-Control-Allow-Origin"]

        if ($allowed -eq $Origin) {
            Add-Result "CORS $Origin" "OK" "Origem permitida."
            return
        }

        Add-Result "CORS $Origin" "FAIL" "Access-Control-Allow-Origin retornou '$allowed'."
    } catch {
        Add-Result "CORS $Origin" "FAIL" $_.Exception.Message
    }
}

Write-Host "SISGES - Validacao LAN"
Write-Host "Frontend: $FrontendUrl"
Write-Host "Backend:  $BackendUrl"
Write-Host ""

$frontendPort = [int]([uri]$FrontendUrl).Port
$backendPort = [int]([uri]$BackendUrl).Port

Test-PortListening -Port $frontendPort -Name "Frontend listener"
Test-PortListening -Port $backendPort -Name "Backend listener"
Test-HttpGet -Uri "$BackendUrl/health" -Name "Backend health" -ExpectedText '"status":"ok"'
Test-HttpGet -Uri "$BackendUrl/openapi.json" -Name "Backend OpenAPI" -ExpectedText "/folhas/geracao/semi-ok-parte1/process"
Test-HttpGet -Uri "$FrontendUrl/folhas" -Name "Frontend /folhas"

foreach ($origin in $CorsOrigins) {
    Test-CorsOrigin -Origin $origin
}

$results | Format-Table -AutoSize

$failed = $results | Where-Object { $_.Status -ne "OK" }
if ($failed) {
    Write-Host ""
    Write-Host "VALIDACAO LAN: FALHA"
    exit 1
}

Write-Host ""
Write-Host "VALIDACAO LAN: OK"
