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
| `netaddr.py`   | Normalização tolerante de IPs/faixas; detecção da rede local.|
| `printers.py`  | Cadastro, edição e validação sem duplicidade.                |
| `collector.py` | Interface de backend, `MockBackend` e orquestração da coleta.|
| `snmp.py`      | Cliente SNMP puro, OIDs de contador e identificação.         |
| `discovery.py` | Descoberta segura de impressoras na rede.                   |
| `reports.py`   | Cálculo de volume por período/mês, filtros e ranking.        |
| `exports.py`   | Serialização de relatórios para CSV.                        |
| `web/`         | Dashboard local (Flask): rotas, templates e exportação CSV. |
| `cli.py`       | Subcomandos de linha de comando.                            |

## Modelo de dados

**printers**: `id`, `name`, `ip` (único), `location`, `model`, `serial`,
`active`, `created_at`.

**readings**: `id`, `printer_id` (FK, cascade), `total_counter`, `collected_at`
(ISO 8601 UTC), `source` (`manual` | `mock` | `seed` | `snmp`).

**reading_ignores**: `reading_id` (PK/FK), `ignored_at`, `reason`. A tabela
permite retirar uma leitura dos cálculos sem apagar o registro original.

Índices em `readings(printer_id, collected_at)` e
`readings(collected_at, printer_id)` aceleram histórico, linha de base e
relatórios por período.

## Cálculo do volume

O contador da impressora é cumulativo. Para um intervalo `[início, fim]`:

1. selecionam-se as leituras válidas dentro do intervalo e a última leitura
   válida anterior ao início, usada como linha de base;
2. os pontos são ordenados por data e identificador;
3. somam-se as diferenças **positivas** entre leituras consecutivas;
4. uma diferença negativa sinaliza reset ou troca de equipamento e torna o
   resultado não mensurável até a revisão do histórico.

Uma leitura isolada não é apresentada como zero confirmado: o estado fica
`waiting_baseline`. Duas leituras iguais produzem um zero realmente medido
(`no_increase`). Quando a linha de base antecede a abertura do mês, o volume é
mostrado como cobertura parcial e acompanhado das datas efetivamente
observadas.

Os limites mensais são calculados no fuso local do computador e convertidos
para UTC antes da consulta. As datas continuam armazenadas em UTC.

### Por que diferença de leituras

A impressora informa apenas o total acumulado. Não há como recuperar o volume de
um mês passado sem leituras daquele mês. A precisão aumenta com a frequência de
coleta. Recomenda-se coletar pelo menos uma vez por dia (idealmente via tarefa
agendada), garantindo leituras próximas às bordas de cada mês.

## Decisões principais

- **SQLite**: zero configuração, arquivo único, adequado a uso local.
- **Backend plugável**: `MockBackend` e `SNMPBackend` usam a mesma interface
  (`read_total_counter`), permitindo testes sem afetar a coleta real.
- **Cálculo puro**: funções de `reports.py` operam sobre listas de `Reading`,
  isoladas de I/O — fáceis de testar.
- **UTC na persistência**: timestamps são armazenados em UTC e apresentados no
  fuso local.
- **Correção reversível**: leituras incorretas são ignoradas por referência, sem
  destruir o histórico auditável.

## Estado atual

- Dashboard Flask local com relatório mensal, filtros, ranking, histórico e CSV.
- Coleta SNMP real, backend simulado explícito para testes e execução concorrente.
- Descoberta de impressoras com limites de faixa, timeout e concorrência.
- Executável Windows em janela nativa, com banco e configuração fora do binário.
- Proteções CSRF, validação de `Host`, limite de upload e cabeçalhos de segurança.
