# build.ps1 — gera o executavel Windows (print-monitor.exe) com PyInstaller.
#
# Uso:
#   .\build.ps1
#
# Resultado:
#   dist\print-monitor.exe   (arquivo unico)
#
# O build usa um ambiente virtual isolado (.build-venv) com apenas as
# dependencias necessarias (flask), evitando que pacotes nao relacionados do
# Python global sejam incluidos e mantendo o executavel enxuto.
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
    & $py -m pip install --disable-pip-version-check -q pyinstaller flask

    # Separador de --add-data no Windows e ";".
    $addData = "src/print_monitor/web/templates;print_monitor/web/templates"

    Write-Host "Empacotando com PyInstaller..."
    & $py -m PyInstaller --noconfirm --clean --onefile `
        --name print-monitor `
        --paths src `
        --add-data $addData `
        --hidden-import print_monitor.web `
        --exclude-module pytest `
        --exclude-module numpy `
        --exclude-module matplotlib `
        --exclude-module PIL `
        --exclude-module IPython `
        --exclude-module tkinter `
        scripts/pm_entry.py

    Write-Host ""
    Write-Host "Build concluido. Executavel em: dist\print-monitor.exe"
    Write-Host "Exemplos:"
    Write-Host "  dist\print-monitor.exe --help"
    Write-Host "  dist\print-monitor.exe init"
    Write-Host "  dist\print-monitor.exe         (duplo clique: abre o dashboard)"
}
finally {
    Pop-Location
}
