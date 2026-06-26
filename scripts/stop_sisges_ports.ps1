param(
    [int[]]$Ports = @(3001, 3031)
)

$ErrorActionPreference = "SilentlyContinue"

foreach ($port in $Ports) {
    $listeners = Get-NetTCPConnection -LocalPort $port |
        Where-Object { $_.State -eq "Listen" } |
        Select-Object -ExpandProperty OwningProcess -Unique

    if (-not $listeners) {
        Write-Host "Porta ${port}: nenhum listener encontrado."
        continue
    }

    foreach ($pidValue in $listeners) {
        $process = Get-Process -Id $pidValue
        if (-not $process) {
            Write-Host "Porta ${port}: PID $pidValue aparece no netstat, mas nao existe no tasklist."
            continue
        }

        Write-Host "Parando porta ${port}: PID $pidValue ($($process.ProcessName))"
        Stop-Process -Id $pidValue -Force
    }
}
