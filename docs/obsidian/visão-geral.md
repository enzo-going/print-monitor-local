---
tags: [projeto/print-monitor-local]
tipo: nota
---

# Visão geral

Ferramenta local para monitorar impressoras de rede e contabilizar o volume de
impressão ao longo do tempo.

## Problema

Impressoras informam um **contador acumulado** de páginas, não o volume de um
mês. Sem histórico coletado, meses passados não podem ser recuperados.

## Abordagem

1. Ler o contador total atual em leituras periódicas.
2. Persistir cada leitura com timestamp (SQLite).
3. Calcular o volume de um período pela diferença entre leituras.

Exemplo: `120000` em 01/06 e `124500` em 30/06 → **4500 impressões**.

## O que já existe (Fase 1)

- Cadastro de impressora por IP.
- Banco SQLite com impressoras e leituras.
- Coleta simulada (mock).
- Cálculo de volume mensal e relatório por impressora.
- Testes automatizados de cálculo e persistência.

## Ligações

- [[decisões-tecnicas]]
- [[roadmap]]
- [[riscos-e-limitacoes]]
- [[comandos-uteis]]
