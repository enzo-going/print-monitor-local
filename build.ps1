# build.ps1 — gera o mini app Windows (print-monitor.exe) com PyInstaller.
#
# Uso:
#   .\build.ps1
#
# Resultado:
#   dist\print-monitor.exe   (arquivo unico, janela nativa)
#
# Sem argumentos (duplo clique), o executavel abre o painel em uma janela nativa
# (pywebview/WebView2). Com argumentos, funciona como CLI.
#
# O build usa um ambiente virtual isolado (.build-venv) com apenas as
# dependencias necessarias (flask, pywebview), evitando incluir pacotes nao
# relacionados do Python global e mantendo o executavel enxuto.
#
# O banco SQLite NAO fica dentro do executavel: em tempo de execucao ele e
# criado em "data\print_monitor.db" ao lado do .exe (ver config.app_base_dir).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "O comando '$FilePath' falhou com codigo de saida $LASTEXITCODE."
    }
}

Push-Location $root
try {
    $venv = Join-Path $root ".build-venv"
    if (-not (Test-Path $venv)) {
        Write-Host "Criando ambiente isolado de build..."
        Invoke-CheckedNative -FilePath "python" -ArgumentList @("-m", "venv", $venv)
    }
    $py = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $py -PathType Leaf)) {
        throw "Python do ambiente de build nao encontrado em '$py'."
    }

    Write-Host "Instalando dependencias de build no ambiente isolado..."
    Invoke-CheckedNative -FilePath $py -ArgumentList @(
        "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"
    )
    Invoke-CheckedNative -FilePath $py -ArgumentList @(
        "-m", "pip", "install", "--disable-pip-version-check", "-q", ".[build]"
    )

    # Separador de --add-data no Windows e ";".
    $templatesData = "src/print_monitor/web/templates;print_monitor/web/templates"
    $staticData = "src/print_monitor/web/static;print_monitor/web/static"
    $outputExe = Join-Path $root "dist\print-monitor.exe"

    # Impede que uma falha seja confundida com um executavel antigo.
    if (Test-Path -LiteralPath $outputExe) {
        Remove-Item -LiteralPath $outputExe -Force
    }

    Write-Host "Empacotando com PyInstaller..."
    Invoke-CheckedNative -FilePath $py -ArgumentList @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "print-monitor",
        "--paths", "src",
        "--add-data", $templatesData,
        "--add-data", $staticData,
        "--hidden-import", "print_monitor.web",
        "--collect-all", "webview",
        "--copy-metadata", "pywebview",
        "--exclude-module", "pytest",
        "--exclude-module", "numpy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",
        "--exclude-module", "IPython",
        "scripts/pm_entry.py"
    )

    if (-not (Test-Path -LiteralPath $outputExe -PathType Leaf)) {
        throw "O PyInstaller terminou sem gerar '$outputExe'."
    }
    if ((Get-Item -LiteralPath $outputExe).Length -le 0) {
        throw "O executavel gerado esta vazio: '$outputExe'."
    }

    Write-Host ""
    Write-Host "Build concluido. Executavel em: dist\print-monitor.exe"
    Write-Host "Uso:"
    Write-Host "  dist\print-monitor.exe            (abre o painel em janela nativa)"
    Write-Host "  dist\print-monitor.exe --help     (modo linha de comando)"
}
finally {
    Pop-Location
}
