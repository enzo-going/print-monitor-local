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

## Fase 3 — Coleta SNMP real

- [ ] Leitura SNMP real (`prtMarkerLifeCount`).
- [ ] Fallback mockado para testes.
- [ ] Community string via `.env`.
- [ ] Tratamento de impressoras incompatíveis.
- [ ] Documentar limitações por modelo.

## Fase 4 — Descoberta na rede

- [ ] Descoberta de impressoras (abordagem segura, sem varredura agressiva).
- [ ] Teste controlado de portas/serviços.
- [ ] Documentar riscos.

## Fase 5 — Empacotamento Windows

- [ ] Build com PyInstaller.
- [ ] `build.ps1`.
- [ ] Banco SQLite fora do executável.
- [ ] Validar execução via Python e via `.exe`.

## Ligações

- [[visão-geral]]
- [[riscos-e-limitacoes]]
