# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento conforme [SemVer](https://semver.org/lang/pt-BR/).

## [0.2.0] — 2026-06-18

### Adicionado

- Dashboard local em Flask (`print-monitor serve`) com painel de volume mensal.
- Filtros por mês, impressora, IP (parcial) e local (parcial) no relatório e no
  dashboard.
- Ranking das impressoras mais usadas e total mensal no painel.
- Exportação CSV do relatório mensal, via dashboard (`/export.csv`) e via CLI
  (`print-monitor export`).
- Listagem de impressoras no dashboard (`/printers`).
- Testes do dashboard, dos filtros e da exportação CSV.

## [0.1.0] — 2026-06-18

### Adicionado

- Estrutura inicial do projeto com layout `src/` e pacote `print_monitor`.
- Banco SQLite com tabelas de impressoras e leituras de contador.
- Cadastro de impressora por IP, com validação e bloqueio de duplicidade.
- Coleta simulada (mock) com contador determinístico por IP.
- Cálculo de volume por período/mês a partir da diferença entre leituras,
  robusto a reset de contador.
- Relatório mensal de volume por impressora e ranking das mais usadas.
- Interface de linha de comando (`init`, `add-printer`, `list-printers`,
  `collect`, `report`).
- Testes automatizados de cálculo e persistência.
- Documentação inicial (arquitetura, limitações por fabricante e notas Obsidian).
- Script de dados fictícios para demonstração.
