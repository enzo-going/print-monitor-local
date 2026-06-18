# Arquitetura

## Visão geral

O sistema é uma aplicação local em Python que coleta o contador total de páginas
de impressoras de rede, persiste cada leitura em SQLite e calcula o volume de
impressão por período a partir das diferenças entre leituras.

```
+-------------+      +------------+      +-----------+      +-----------+
|  Backend    | ---> | Collector  | ---> |    DB     | ---> | Reports   |
| (mock/SNMP) |      | (orquestra)|      | (SQLite)  |      | (cálculo) |
+-------------+      +------------+      +-----------+      +-----------+
                                              ^                  |
                                              |                  v
                                            CLI  <-----------  saída
```

## Módulos

| Módulo         | Responsabilidade                                              |
|----------------|--------------------------------------------------------------|
| `config.py`    | Resolve parâmetros do ambiente (`.env` opcional) e padrões.   |
| `models.py`    | `Printer` e `Reading` (dataclasses imutáveis).               |
| `db.py`        | Esquema e operações SQLite; (de)serialização de datas (UTC). |
| `printers.py`  | Validação de IP e cadastro sem duplicidade.                  |
| `collector.py` | Interface de backend, `MockBackend` e orquestração da coleta.|
| `snmp.py`      | Backend SNMP real (Fase 3) e OIDs de contador total.        |
| `reports.py`   | Cálculo de volume por período/mês, filtros e ranking.        |
| `exports.py`   | Serialização de relatórios para CSV.                        |
| `web/`         | Dashboard local (Flask): rotas, templates e exportação CSV. |
| `cli.py`       | Subcomandos de linha de comando.                            |

## Modelo de dados

**printers**: `id`, `name`, `ip` (único), `location`, `model`, `serial`,
`active`, `created_at`.

**readings**: `id`, `printer_id` (FK, cascade), `total_counter`, `collected_at`
(ISO 8601 UTC), `source` (`manual` | `mock` | `seed` | `snmp`).

Índice em `readings(printer_id, collected_at)` para consultas por período.

## Cálculo do volume

O contador da impressora é cumulativo. Para um intervalo `[início, fim]`:

1. selecionam-se as leituras dentro do intervalo, ordenadas por tempo;
2. somam-se as diferenças **positivas** entre leituras consecutivas;
3. diferenças negativas (reset/troca de contador) são descartadas.

Com 0 ou 1 leitura no intervalo, o volume é 0 — não há base de comparação.

### Por que diferença de leituras

A impressora informa apenas o total acumulado. Não há como recuperar o volume de
um mês passado sem leituras daquele mês. A precisão aumenta com a frequência de
coleta. Recomenda-se coletar pelo menos uma vez por dia (idealmente via tarefa
agendada), garantindo leituras próximas às bordas de cada mês.

## Decisões principais

- **SQLite**: zero configuração, arquivo único, adequado a uso local.
- **Backend plugável**: `MockBackend` na Fase 1; `SNMPBackend` na Fase 3,
  mesma interface (`read_total_counter`), troca sem afetar o restante.
- **Cálculo puro**: funções de `reports.py` operam sobre listas de `Reading`,
  isoladas de I/O — fáceis de testar.
- **UTC em tudo**: timestamps armazenados e comparados em UTC.

## Evolução planejada

- **Fase 2**: dashboard Flask, filtros, ranking, exportação CSV.
- **Fase 3**: coleta SNMP real com fallback mockado.
- **Fase 4**: descoberta de impressoras na rede (abordagem segura, sem varredura
  agressiva).
- **Fase 5**: empacotamento Windows com PyInstaller, banco fora do executável.
