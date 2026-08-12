<#
.SYNOPSIS
    Prepara o print-monitor no servidor: ambiente Python, coleta diaria e painel.

.DESCRIPTION
    Executa NO SERVIDOR, pelo RDP. E a contraparte de publicar-no-servidor.ps1,
    que ja copiou os arquivos: aqui ficam as acoes que exigem rodar codigo na
    maquina de destino, coisa que costuma estar bloqueada remotamente.

    E seguro rodar de novo a cada atualizacao: recria o ambiente se faltar algo,
    reescreve as tarefas e nunca toca no banco em data\.

.PARAMETER Porta
    Porta do painel. Padrao: 5056. NAO use 5000 no servidor do CAMPS -- e do
    Certificador ICP-Brasil.

.PARAMETER Horario
    Horario da coleta diaria (HH:mm). Padrao: 08:00.

.PARAMETER SemPainel
    Registra apenas a coleta diaria, sem deixar o painel no ar.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File C:\PrintMonitor\scripts\instalar-no-servidor.ps1
#>
[CmdletBinding()]
param(
    [int]$Porta = 5056,
    [string]$Horario = "08:00",
    [switch]$SemPainel
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

Write-Host "=== print-monitor: instalacao no servidor ==="
Write-Host "Pasta: $raiz"
if (Test-Path "$raiz\VERSAO-PUBLICADA.txt") { Get-Content "$raiz\VERSAO-PUBLICADA.txt" }
Write-Host ""

# --- 1. Ambiente Python --------------------------------------------------
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Criando ambiente virtual..."
    $base = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $base) { throw "Python nao encontrado no servidor. Instale o Python 3.11+ e rode de novo." }
    & $base.Source -m venv (Join-Path $raiz ".venv")
}
Write-Host "Instalando/atualizando dependencias do painel..."
& $python -m pip install --disable-pip-version-check -q --upgrade pip flask
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as dependencias." }

$versao = (& $python -c "import sys; sys.path.insert(0,'src'); import print_monitor; print(print_monitor.__version__)").Trim()
Write-Host "Versao instalada: $versao"

# --- 2. Banco ------------------------------------------------------------
# Roda a partir de src\ para o pacote ser importavel sem instalacao; o banco e
# resolvido pelo caminho do modulo, entao continua em <raiz>\data.
$src = Join-Path $raiz "src"
& $python -m print_monitor init
Write-Host ""

# --- 3. Coleta diaria ----------------------------------------------------
# pythonw evita abrir uma janela de console no servidor todo dia.
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$executavel = if (Test-Path $pythonw) { $pythonw } else { $python }

$acaoColeta = New-ScheduledTaskAction -Execute $executavel `
    -Argument "-m print_monitor collect --all" -WorkingDirectory $src
$gatilhoColeta = New-ScheduledTaskTrigger -Daily -At $Horario
# StartWhenAvailable: se o servidor estiver reiniciando no horario, a coleta
# acontece assim que ele voltar, em vez de perder o dia.
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "PrintMonitor-Coleta" -Action $acaoColeta `
    -Trigger $gatilhoColeta -Settings $config -RunLevel Highest `
    -Description "Coleta diaria dos contadores das impressoras." -Force | Out-Null
Write-Host "Tarefa PrintMonitor-Coleta registrada para as $Horario."

# --- 4. Painel -----------------------------------------------------------
if (-not $SemPainel) {
    # O painel nao tem login e so aceita conexoes locais por decisao de projeto:
    # quem for consultar abre o navegador dentro do proprio servidor.
    $acaoPainel = New-ScheduledTaskAction -Execute $executavel `
        -Argument "-m print_monitor serve --port $Porta --no-browser" -WorkingDirectory $src
    $gatilhoPainel = New-ScheduledTaskTrigger -AtStartup
    $configPainel = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName "PrintMonitor-Painel" -Action $acaoPainel `
        -Trigger $gatilhoPainel -Settings $configPainel -RunLevel Highest -User "SYSTEM" `
        -Description "Painel local do print-monitor (somente localhost)." -Force | Out-Null

    # Reinicia para o painel passar a servir a versao recem-publicada.
    Stop-ScheduledTask -TaskName "PrintMonitor-Painel" -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName "PrintMonitor-Painel"
    Write-Host "Tarefa PrintMonitor-Painel registrada e iniciada na porta $Porta."
}

# --- 5. Conferencia ------------------------------------------------------
Write-Host ""
Write-Host "=== Conferindo ==="
& $python -m print_monitor list-printers
if (-not $SemPainel) {
    Start-Sleep -Seconds 3
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Porta/" -UseBasicParsing -TimeoutSec 10
        Write-Host "Painel respondeu HTTP $($r.StatusCode) em http://127.0.0.1:$Porta/"
    } catch {
        Write-Warning "O painel ainda nao respondeu: $_"
        Write-Warning "Veja: Get-ScheduledTaskInfo -TaskName PrintMonitor-Painel"
    }
}

Write-Host ""
Write-Host "Pronto. O painel abre em http://127.0.0.1:$Porta/ aqui dentro do servidor."
Write-Host "Coletar agora, para nao esperar ate $Horario :"
Write-Host "    Start-ScheduledTask -TaskName PrintMonitor-Coleta"
