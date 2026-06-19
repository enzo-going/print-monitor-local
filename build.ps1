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
Push-Location $root
try {
    $venv = Join-Path $root ".build-venv"
    if (-not (Test-Path $venv)) {
        Write-Host "Criando ambiente isolado de build..."
        python -m venv $venv
    }
    $py = Join-Path $venv "Scripts\python.exe"

    Write-Host "Instalando dependencias de build no ambiente isolado..."
    & $py -m pip install --disable-pip-version-check -q --upgrade pip
    & $py -m pip install --disable-pip-version-check -q pyinstaller flask pywebview

    # Separador de --add-data no Windows e ";".
    $addData = "src/print_monitor/web/templates;print_monitor/web/templates"

    Write-Host "Empacotando com PyInstaller..."
    & $py -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name print-monitor `
        --paths src `
        --add-data $addData `
        --hidden-import print_monitor.web `
        --collect-all webview `
        --copy-metadata pywebview `
        --exclude-module pytest `
        --exclude-module numpy `
        --exclude-module matplotlib `
        --exclude-module PIL `
        --exclude-module IPython `
        scripts/pm_entry.py

    Write-Host ""
    Write-Host "Build concluido. Executavel em: dist\print-monitor.exe"
    Write-Host "Uso:"
    Write-Host "  dist\print-monitor.exe            (abre o painel em janela nativa)"
    Write-Host "  dist\print-monitor.exe --help     (modo linha de comando)"
}
finally {
    Pop-Location
}
