<#
.SYNOPSIS
    Registra (ou atualiza) uma tarefa diaria no Agendador do Windows que executa
    a coleta de contadores de todas as impressoras cadastradas.

.DESCRIPTION
    O volume de impressao e calculado pela diferenca entre leituras. Sem coletas
    periodicas, o historico nao acumula e os relatorios ficam em zero. Esta
    tarefa roda "print-monitor.exe collect --all" uma vez por dia.

    O diretorio de trabalho e a pasta do executavel, para que o .env e o banco
    (data\print_monitor.db) sejam resolvidos ao lado do .exe.

.PARAMETER ExePath
    Caminho do print-monitor.exe. Por padrao, procura em "dist\print-monitor.exe"
    na raiz do repositorio (um nivel acima deste script).

.PARAMETER Time
    Horario diario da coleta, no formato HH:mm. Padrao: 08:00.

.PARAMETER TaskName
    Nome da tarefa no Agendador. Padrao: PrintMonitor-Coleta.

.EXAMPLE
    .\scripts\agendar-coleta.ps1
    Registra a coleta diaria as 08:00 usando o exe em dist\.

.EXAMPLE
    .\scripts\agendar-coleta.ps1 -ExePath "C:\PrintMonitor\print-monitor.exe" -Time "07:30"
#>
[CmdletBinding()]
param(
    [string]$ExePath,
    [string]$Time = "08:00",
    [string]$TaskName = "PrintMonitor-Coleta"
)

$ErrorActionPreference = "Stop"

if (-not $ExePath) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $ExePath = Join-Path $repoRoot "dist\print-monitor.exe"
}

if (-not (Test-Path $ExePath)) {
    throw "Executavel nao encontrado em '$ExePath'. Gere-o com .\build.ps1 ou informe -ExePath."
}

$ExePath = (Resolve-Path $ExePath).Path
$workDir = Split-Path -Parent $ExePath

if ($Time -notmatch '^\d{2}:\d{2}$') {
    throw "Horario invalido '$Time'. Use o formato HH:mm, por exemplo 08:00."
}

Write-Host "Executavel : $ExePath"
Write-Host "Diretorio  : $workDir"
Write-Host "Horario    : $Time (diario)"
Write-Host "Tarefa     : $TaskName"

$action  = New-ScheduledTaskAction -Execute $ExePath -Argument "collect --all" -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Coleta diaria de contadores das impressoras (print-monitor)." `
    -Force | Out-Null

Write-Host ""
Write-Host "Tarefa registrada. Para conferir:  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para remover:                       Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
