<#
.SYNOPSIS
    Publica esta versao do print-monitor em um servidor Windows, copiando os
    arquivos por compartilhamento administrativo.

.DESCRIPTION
    Executa NA ESTACAO. Copia o codigo para o servidor **preservando os dados**:
    o banco em data\ e o .env do destino nunca sao tocados. Sem isso, uma
    publicacao apagaria o historico de contadores, que e justamente o que nao da
    para recuperar -- impressoras so informam o total acumulado atual.

    A parte que precisa rodar dentro do servidor (criar o ambiente Python,
    registrar as tarefas) fica em instalar-no-servidor.ps1, que este script
    copia junto. Execucao remota costuma estar bloqueada; ver
    docs\publicacao-servidor.md.

.PARAMETER Servidor
    IP ou nome do servidor. Padrao: 192.168.20.29.

.PARAMETER Destino
    Caminho do programa NO SERVIDOR. Padrao: C:\PrintMonitor.

.PARAMETER Simular
    Mostra o que seria copiado, sem copiar nada.

.EXAMPLE
    .\scripts\publicar-no-servidor.ps1 -Simular
    Confere a lista de arquivos antes de publicar de verdade.

.EXAMPLE
    .\scripts\publicar-no-servidor.ps1

.NOTES
    Se o compartilhamento pedir credencial, monte-o antes com a conta LOCAL do
    servidor (a de dominio costuma receber acesso negado):

        $cred = Get-Credential SERVIDOR\Administrador
        New-PSDrive -Name S -PSProvider FileSystem -Root \\SERVIDOR\C$ -Credential $cred -Persist
#>
[CmdletBinding()]
param(
    [string]$Servidor = "192.168.20.29",
    [string]$Destino = "C:\PrintMonitor",
    [switch]$Simular
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot

# O destino visto da estacao: C:\PrintMonitor vira \\servidor\C$\PrintMonitor.
$unidade = $Destino.Substring(0, 1)
$resto = $Destino.Substring(3)
$alvo = "\\$Servidor\$unidade`$\$resto"

Write-Host "Origem   : $raiz"
Write-Host "Servidor : $Servidor"
Write-Host "Destino  : $Destino  ($alvo)"
Write-Host ""

if (-not (Test-Path "\\$Servidor\$unidade`$")) {
    throw @"
Sem acesso a \\$Servidor\$unidade`$.
Monte o compartilhamento com a conta LOCAL do servidor e tente de novo:

    `$cred = Get-Credential $Servidor\Administrador
    New-PSDrive -Name S -PSProvider FileSystem -Root \\$Servidor\$unidade`$ -Credential `$cred -Persist
"@
}

# Versao publicada, para conferir depois se o destino recebeu o que se esperava.
$versao = (Select-String -Path "$raiz\pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Versao a publicar: $versao"

# O que o programa precisa para rodar. Deliberadamente enxuto: sem .git, sem
# .venv da estacao (o servidor cria o dele), sem testes.
$itens = @(
    @{ Origem = "src";            Tipo = "pasta"   },
    @{ Origem = "scripts";        Tipo = "pasta"   },
    @{ Origem = "pyproject.toml"; Tipo = "arquivo" },
    @{ Origem = "README.md";      Tipo = "arquivo" },
    @{ Origem = "CHANGELOG.md";   Tipo = "arquivo" },
    @{ Origem = ".env.example";   Tipo = "arquivo" }
)

foreach ($item in $itens) {
    $de = Join-Path $raiz $item.Origem
    $para = Join-Path $alvo $item.Origem
    if (-not (Test-Path $de)) { throw "Origem ausente: $de" }

    if ($Simular) {
        Write-Host "[simulacao] $($item.Origem) -> $para"
        continue
    }

    if ($item.Tipo -eq "pasta") {
        # /MIR espelha (remove no destino o que sumiu na origem), mas /XD data
        # protege o banco e /XF .env protege a configuracao local do servidor.
        $log = robocopy $de $para /MIR /XD data __pycache__ /XF .env *.pyc /NFL /NDL /NJH /NJS /R:2 /W:2
        if ($LASTEXITCODE -ge 8) {
            Write-Host $log
            throw "Falha ao copiar $($item.Origem) (robocopy $LASTEXITCODE)."
        }
    } else {
        $pastaPai = Split-Path -Parent $para
        if (-not (Test-Path $pastaPai)) { New-Item -ItemType Directory -Path $pastaPai -Force | Out-Null }
        Copy-Item $de $para -Force
    }
    Write-Host "ok  $($item.Origem)"
}

if ($Simular) {
    Write-Host ""
    Write-Host "Simulacao concluida. Nada foi copiado."
    return
}

# Marca a versao publicada em um arquivo simples, para o proximo a mexer saber o
# que esta rodando la sem precisar abrir o codigo.
$carimbo = "versao=$versao`npublicado_em=$(Get-Date -Format 's')`npublicado_de=$env:COMPUTERNAME`n"
Set-Content -Path (Join-Path $alvo "VERSAO-PUBLICADA.txt") -Value $carimbo -Encoding utf8

Write-Host ""
Write-Host "Arquivos publicados. O banco em $Destino\data e o .env nao foram tocados."
Write-Host ""
Write-Host "FALTA A PARTE QUE RODA NO SERVIDOR. Abra o RDP em $Servidor e execute:"
Write-Host "    powershell -ExecutionPolicy Bypass -File $Destino\scripts\instalar-no-servidor.ps1"
