---
tags: [projeto/print-monitor-local, roadmap]
tipo: nota
---

# Roadmap

## Fase 1 — Base funcional ✅

- [x] Estrutura do projeto e documentação inicial.
- [x] Banco SQLite (impressoras e leituras).
- [x] Cadastro de impressora por IP.
- [x] Coleta simulada (mock).
- [x] Cálculo de volume mensal/por período.
- [x] Relatório mensal por impressora.
- [x] Testes automatizados (cálculo e persistência).

## Fase 2 — Dashboard e filtros ✅

- [x] Dashboard local (Flask).
- [x] Listagem de impressoras.
- [x] Filtros por mês, impressora, IP e local.
- [x] Total mensal e ranking das mais usadas.
- [x] Exportação CSV.
- [x] Testes básicos.

## Fase 3 — Coleta SNMP real ✅

- [x] Leitura SNMP real (`prtMarkerLifeCount`), em Python puro.
- [x] Fallback mockado (backend selecionável: `mock`/`snmp`).
- [x] Community string via `.env`.
- [x] Tratamento de impressoras incompatíveis (falha não interrompe as demais).
- [x] Documentar limitações por modelo.

## Fase 4 — Descoberta na rede ✅

- [x] Descoberta de impressoras (abordagem segura, sem varredura agressiva).
- [x] Teste controlado de portas/serviços (limite de hosts, timeouts curtos).
- [x] Documentar riscos (`docs/descoberta-rede.md`).

## Fase 5 — Empacotamento Windows ✅

- [x] Build com PyInstaller (arquivo único).
- [x] `build.ps1` (ambiente isolado para executável enxuto).
- [x] Banco SQLite fora do executável (`config.app_base_dir`).
- [x] Validar execução via Python e via `.exe` (CLI e dashboard).

## Ligações

- [[visão-geral]]
- [[riscos-e-limitacoes]]
