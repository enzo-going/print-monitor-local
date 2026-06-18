---
tags: [projeto/print-monitor-local, comandos]
tipo: nota
---

# Comandos úteis

## Ambiente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Executar sem instalar (via PYTHONPATH)

```powershell
$env:PYTHONPATH = "src"
python -m print_monitor --help
```

Ou pelo wrapper:

```powershell
.\scripts\run.ps1 --help
```

## Fluxo básico

```powershell
python -m print_monitor init
python -m print_monitor add-printer --name "HP Andar 1" --ip 192.168.0.50 --location "Financeiro"
python -m print_monitor list-printers
python -m print_monitor collect --all
python -m print_monitor report --year 2026 --month 6
```

## Dados fictícios para demonstração

```powershell
python scripts/seed.py
python -m print_monitor report --year 2026 --month 6
```

## Testes

```powershell
python -m pytest
python -m pytest -k reports     # apenas cálculo
```

## Ligações

- [[visão-geral]]
- [[roadmap]]
