# Executa a CLI do print-monitor sem precisar instalar o pacote.
# Define o PYTHONPATH para "src" e repassa os argumentos recebidos.
#
# Exemplos:
#   .\scripts\run.ps1 init
#   .\scripts\run.ps1 add-printer --name "HP 1" --ip 192.168.0.50 --location TI
#   .\scripts\run.ps1 report --year 2026 --month 6

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
python -m print_monitor @args
