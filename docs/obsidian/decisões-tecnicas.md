---
tags: [projeto/print-monitor-local, decisoes]
tipo: nota
---

# Decisões técnicas

Registro objetivo das escolhas e seus motivos.

## Linguagem e dependências

- **Python ≥ 3.11** (testado em 3.13).
- Fase 1 **sem dependências externas** (apenas biblioteca padrão) — roda offline
  e simplifica os testes.
- Dependências futuras declaradas como *extras* opcionais no `pyproject.toml`
  (`snmp`, `dashboard`, `build`, `dev`).

## Banco

- **SQLite**: arquivo único, zero configuração, adequado a uso local.
- Datas em **UTC**, persistidas em ISO 8601.
- Índice em `readings(printer_id, collected_at)` para consultas por período.

## Cálculo de volume

- **Soma de diferenças positivas** entre leituras consecutivas no intervalo.
- Diferenças negativas (reset/troca de contador) são descartadas → robustez a
  *rollover*.
- Funções de cálculo **puras** (sem I/O) → fáceis de testar.

## Coleta

- **Backend plugável** via interface `read_total_counter(printer)`.
- Fase 1: `MockBackend` determinístico por IP.
- Fase 3: `SNMPBackend` real, mesma interface, com fallback mockado.

## Dashboard

- Adiado para a **Fase 2**. Quando entrar, será **Flask** (mais simples e
  suficiente para um painel local).

## Empacotamento

- **PyInstaller** na Fase 5, com o banco SQLite mantido **fora** do executável.

## Ligações

- [[arquitetura]] (ver também `docs/arquitetura.md`)
- [[roadmap]]
