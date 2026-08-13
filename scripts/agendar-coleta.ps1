<#
.SYNOPSIS
    Registra (ou atualiza) uma tarefa diaria no Agendador do Windows que executa
    a coleta de contadores de todas as impressoras cadastradas.

.DESCRIPTION
    O volume de impressao e calculado pela diferenca entre leituras. Sem coletas
    periodicas, o historico nao acumula e os relatorios ficam em zero.

    O script descobre sozinho como executar a coleta, nesta ordem:
      1. o executavel informado em -ExePath;
      2. dist\print-monitor.exe, se o build ja foi feito;
      3. o Python do ambiente virtual .venv do repositorio;
      4. o Python do sistema.

    Assim ele funciona tanto para quem baixou o .exe pronto quanto para quem roda
    a partir do codigo-fonte -- que antes ficava sem opcao de agendamento, apesar
    de a coleta periodica ser justamente o que faz os relatorios existirem.

.PARAMETER ExePath
    Caminho do print-monitor.exe. Opcional; veja a ordem de deteccao acima.

.PARAMETER Time
    Horario diario da coleta, no formato HH:mm. Padrao: 08:00.

.PARAMETER TaskName
    Nome da tarefa no Agendador. Padrao: PrintMonitor-Coleta.

.PARAMETER Remover
    Remove a tarefa agendada em vez de criar.

.EXAMPLE
    .\scripts\agendar-coleta.ps1
    Registra a coleta diaria as 08:00.

.EXAMPLE
    .\scripts\agendar-coleta.ps1 -Time "07:30"

.EXAMPLE
    .\scripts\agendar-coleta.ps1 -Remover
#>
[CmdletBinding()]
param(
    [string]$ExePath,
    [string]$Time = "08:00",
    [string]$TaskName = "PrintMonitor-Coleta",
    [switch]$Remover
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if ($Remover) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Tarefa '$TaskName' removida."
    } catch {
        Write-Host "Nenhuma tarefa '$TaskName' encontrada."
    }
    return
}

if ($Time -notmatch '^\d{1,2}:\d{2}$') {
    throw "Horario invalido '$Time'. Use o formato HH:mm, por exemplo 08:00."
}

# Registrar uma tarefa que roda sem ninguem logado exige elevacao. Sem esta
# checagem, o Register-ScheduledTask estoura um "Acesso negado" cru no fim do
# script, depois de ja ter impresso que ia dar tudo certo.
$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$ehAdmin = (New-Object Security.Principal.WindowsPrincipal $identidade).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    throw @"
Este script precisa ser executado como administrador.

A coleta e registrada para rodar como SYSTEM, para funcionar mesmo sem ninguem
logado -- que e o ponto de uma coleta diaria. Isso exige elevacao.

Abra o PowerShell com "Executar como administrador" e rode de novo:
    cd '$repoRoot'
    .\scripts\agendar-coleta.ps1 -Time '$Time'
"@
}

# --- Descobre como executar a coleta -------------------------------------
$execute = $null
$argumento = $null
$workDir = $repoRoot

if ($ExePath) {
    if (-not (Test-Path $ExePath)) { throw "Executavel nao encontrado em '$ExePath'." }
    $execute = (Resolve-Path $ExePath).Path
    $argumento = "collect --all"
    $workDir = Split-Path -Parent $execute
}

if (-not $execute) {
    $dist = Join-Path $repoRoot "dist\print-monitor.exe"
    if (Test-Path $dist) {
        $execute = (Resolve-Path $dist).Path
        $argumento = "collect --all"
        $workDir = Split-Path -Parent $execute
    }
}

if (-not $execute) {
    # pythonw.exe roda sem abrir uma janela de console na cara do usuario todo
    # dia -- a coleta e uma rotina de fundo, nao algo a ser assistido.
    foreach ($candidato in @(
        (Join-Path $repoRoot ".venv\Scripts\pythonw.exe"),
        (Join-Path $repoRoot ".venv\Scripts\python.exe")
    )) {
        if (Test-Path $candidato) { $execute = (Resolve-Path $candidato).Path; break }
    }
    if (-not $execute) {
        $sistema = Get-Command pythonw.exe, python.exe -ErrorAction SilentlyContinue |
                   Select-Object -First 1
        if ($sistema) { $execute = $sistema.Source }
    }
    if (-not $execute) {
        throw "Nao encontrei nem o print-monitor.exe nem o Python. Gere o executavel com .\build.ps1 ou instale o Python."
    }
    $argumento = "-m print_monitor collect --all"
    # Roda a partir de src\ para que "print_monitor" seja importavel mesmo sem o
    # pacote instalado. O banco continua em <repo>\data, porque o caminho e
    # resolvido a partir do arquivo do modulo, nao do diretorio de trabalho.
    $workDir = Join-Path $repoRoot "src"
}

Write-Host "Executavel : $execute"
Write-Host "Argumentos : $argumento"
Write-Host "Diretorio  : $workDir"
Write-Host "Horario    : $Time (diario)"
Write-Host "Tarefa     : $TaskName"

$action = New-ScheduledTaskAction -Execute $execute -Argument $argumento -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: se o computador estiver desligado no horario, a coleta
# acontece assim que ele ligar -- sem isso o dia inteiro ficaria sem leitura.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Sem -User, o principal fica com LogonType Interactive: a tarefa so dispara
# enquanto aquele usuario estiver logado. Como a coleta e uma rotina de fundo --
# e num servidor ninguem fica logado --, ela roda como SYSTEM. O trabalho e todo
# local (SQLite e SNMP na LAN) e nao depende de compartilhamento de rede.
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -User "SYSTEM" -RunLevel Highest `
    -Description "Coleta diaria de contadores das impressoras (print-monitor)." `
    -Force | Out-Null

Write-Host ""
Write-Host "Tarefa registrada (roda como SYSTEM, mesmo sem ninguem logado)."
Write-Host "Para conferir:                     Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para testar agora:                 Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Para remover:                      .\scripts\agendar-coleta.ps1 -Remover"
