# print-monitor-local

[![CI](https://github.com/enzo-going/print-monitor-local/actions/workflows/ci.yml/badge.svg)](https://github.com/enzo-going/print-monitor-local/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/enzo-going/print-monitor-local)](https://github.com/enzo-going/print-monitor-local/releases)

Ferramenta **local** para monitorar impressoras de rede, identificá-las por IP
e contabilizar o volume de impressão ao longo do tempo.

Impressoras de rede expõem um **contador acumulado** de páginas — não o volume
de um mês específico. Esta ferramenta coleta o contador total em leituras
periódicas, guarda o histórico em SQLite e calcula o volume de cada período
pela **diferença entre leituras**.

> Exemplo: contador `120000` em 01/06 e `124500` em 30/06 → **4500 impressões**.

![Dashboard do print-monitor-local com total mensal, ranking e filtros](docs/assets/dashboard.jpg)

<sub>Dashboard local com dados fictícios de demonstração.</sub>

> **In English** — Local tool to monitor network printers and measure print
> volume over time. Printers expose a **cumulative** page counter, not a monthly
> total, so the tool stores periodic readings in SQLite and computes each
> period's volume as the **difference between consecutive readings** (handling
> counter rollover). It reads counters over **SNMP** (pure Python, no native
> deps), ships a local **Flask** dashboard with filters/ranking/CSV export, does
> safe subnet **discovery**, and is packaged as a single **Windows .exe**.

## Status

| Fase | Conteúdo                                                        | Situação    |
|------|-----------------------------------------------------------------|-------------|
| 1    | Estrutura, banco, cadastro, coleta mockada, cálculo, relatório  | Disponível  |
| 2    | Dashboard local, filtros, ranking, exportação CSV               | Disponível  |
| 3    | Coleta SNMP real com fallback mockado                           | Disponível  |
| 4    | Descoberta de impressoras na rede (abordagem segura)            | Disponível  |
| 5    | Empacotamento Windows com PyInstaller                          | Disponível  |

## Requisitos

- Python 3.11 ou superior (testado em 3.13).
- Nenhuma dependência externa para a Fase 1 (apenas biblioteca padrão).

## Instalação (desenvolvimento)

```powershell
# Criar e ativar ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar ferramentas de teste (opcional)
pip install -e ".[dev]"
```

Sem instalar o pacote, é possível executar via módulo definindo o `PYTHONPATH`:

```powershell
$env:PYTHONPATH = "src"
python -m print_monitor --help
```

## Uso rápido (CLI)

```powershell
# 1. Inicializar o banco de dados
python -m print_monitor init

# 2. Cadastrar uma impressora por IP
python -m print_monitor add-printer --name "HP Andar 1" --ip 192.168.0.50 --location "Financeiro"

#    Ou importar várias de uma planilha CSV (colunas: SETOR, MARCA, MODELO, IP, N° SÉRIE)
python -m print_monitor import-printers --file docs/exemplo-impressoras.csv

# 3. Listar impressoras
python -m print_monitor list-printers

# 4. Coletar leitura via SNMP real (padrão)
python -m print_monitor collect --all

#    Usar dados simulados somente para demonstração ou testes
python -m print_monitor collect --all --backend mock

# 5. Relatório mensal (volume por impressora)
python -m print_monitor report --year 2026 --month 6

# 6. Exportar o relatório mensal em CSV (filtros opcionais)
python -m print_monitor export --year 2026 --month 6 --location Financeiro --output relatorio.csv

# 7. Dashboard local (Flask) em http://127.0.0.1:5000
python -m print_monitor serve

# 8. Descobrir impressoras em uma sub-rede (abordagem segura)
python -m print_monitor discover --network 192.168.0.0/24 --snmp

# 9. Diagnosticar um endereço: o que esta impressora responde?
python -m print_monitor test 192.168.0.50
```

> O dashboard exige o extra opcional `dashboard`: `pip install -e ".[dashboard]"`.
> Ele separa claramente o **contador acumulado** da **produção mensal**, mostra
> a cobertura observada, oferece histórico corrigível, filtros, ranking e CSV.
> O CSV baixado pela interface usa UTF-8 com BOM e separador `;` para abrir
> corretamente no Excel em português; a saída da CLI mantém o formato técnico
> padrão com vírgulas para integrações.
> Como não possui login, o servidor aceita somente `localhost`/loopback e não
> expõe os contadores e cadastros para outros computadores da rede.

Para popular o banco com dados **fictícios** e ver relatórios imediatamente:

```powershell
python scripts/seed.py
python -m print_monitor report --year 2026 --month 6
```

## Coleta SNMP

A coleta real usa SNMP (v1/v2c) e é implementada em **Python puro** sobre a
biblioteca padrão (sem dependências nativas), o que simplifica o empacotamento.
Por padrão usa SNMP v2c. Equipamentos antigos que aceitam somente v1 podem usar
`SNMP_VERSION=1`; os demais devem manter `SNMP_VERSION=2c`. A *community string*
e os tempos de espera vêm do ambiente ou do `.env` (ver `.env.example`), nunca do
código.

O contador é lido primeiro pelo OID padrão `prtMarkerLifeCount` (Printer-MIB,
RFC 3805). Quando o equipamento responde que não o implementa — comum em modelos
de entrada — a leitura tenta os OIDs proprietários de **HP, Ricoh, Kyocera,
Brother, Lexmark, Xerox, Samsung e Epson** antes de desistir. Se nem o OID padrão
responder, a busca para imediatamente: o equipamento está inacessível, e insistir
só faria o usuário esperar.

A ferramenta também lê `sysName`, modelo e número de série, o que permite à
descoberta sugerir “RICOH IM C3000 — Recepção” em vez de
“Impressora 192.168.20.31”.

Impressoras incompatíveis ou inacessíveis são registradas como falha sem
interromper a coleta das demais. As consultas rodam em paralelo (8 por padrão)
e as leituras bem-sucedidas são gravadas em uma única transação. Ajuste a
concorrência com `PRINT_MONITOR_WORKERS` ou `collect --workers`. O backend padrão
é o real (`snmp`); use `--backend mock` (ou
`PRINT_MONITOR_BACKEND=mock`) apenas para demonstrações e testes. Limitações por
fabricante/modelo:
[`docs/limitacoes-fabricantes.md`](docs/limitacoes-fabricantes.md).

A primeira coleta salva o contador acumulado como **linha de base**. Enquanto
não houver outro ponto para comparação, o painel mostra **“Aguardando
comparação”**, em vez de apresentar um zero que ainda não pode ser comprovado.
O histórico permite informar um contador anterior confiável e retirar uma
leitura incorreta dos cálculos sem apagá-la definitivamente.

## Coleta agendada (Windows)

Como o volume é a diferença entre leituras, é preciso coletar periodicamente —
sem isso o histórico não acumula e os relatórios ficam em zero. O script
[`scripts/agendar-coleta.ps1`](scripts/agendar-coleta.ps1) registra uma tarefa
diária no Agendador do Windows que executa `print-monitor.exe collect --all`:

```powershell
# Coleta diária às 08:00 (usa o executável em dist\)
.\scripts\agendar-coleta.ps1

# Horário e caminho do executável personalizados
.\scripts\agendar-coleta.ps1 -ExePath "C:\PrintMonitor\print-monitor.exe" -Time "07:30"
```

A tarefa roda com o diretório de trabalho na pasta do executável, para que o
`.env` e o banco (`data\print_monitor.db`) sejam resolvidos ao seu lado. Para
conferir ou remover:

```powershell
Get-ScheduledTask -TaskName "PrintMonitor-Coleta"
Unregister-ScheduledTask -TaskName "PrintMonitor-Coleta" -Confirm:$false
```

## Entrada tolerante a erro de digitação

Quem cadastra copia o IP de uma etiqueta, de um e-mail ou do painel do
equipamento, e no caminho aparecem erros previsíveis. O campo aceita o endereço
como estiver e corrige sozinho:

| Você digita             | É salvo como   |
|-------------------------|----------------|
| ` 192.168.0.10 `        | `192.168.0.10` |
| `192,168,0,10`          | `192.168.0.10` |
| `192.168.O.1O`          | `192.168.0.10` |
| `http://192.168.0.10`   | `192.168.0.10` |
| `192.168.0.10:9100`     | `192.168.0.10` |
| `192.168.020.005`       | `192.168.20.5` |

O que não dá para interpretar vira uma mensagem dizendo o que corrigir — “falta
1 número”, “o número 300 é maior que 255” — em vez de um “IP inválido” seco. O
formulário mostra a correção enquanto você digita, consultando a mesma função
usada no cadastro, para o aviso nunca discordar do que será salvo.

A mesma tolerância vale para a faixa da busca na rede: `192.168.0`,
`192.168.0.*` e `192.168.0.1-254` são aceitos além do CIDR clássico, e a tela já
vem preenchida com a faixa deste computador.

O botão **Testar conexão** consulta o endereço na hora e preenche nome, modelo e
número de série com o que o equipamento publicar — descobrir ali que o IP está
errado evita um mês inteiro de coletas vazias percebido só no fechamento.

## Como o volume é calculado

Para um período, o volume é a soma das diferenças **positivas** entre leituras
consecutivas. O cálculo inclui a última leitura válida anterior ao início do mês
como linha de base, evitando perder o primeiro intervalo mensal. Uma leitura
feita exatamente na abertura do mês tem precedência sobre a linha de base
anterior. Quando a linha de base antecede a abertura, o painel identifica a
**cobertura parcial** e mostra as datas realmente observadas. Diferenças
negativas (reset/troca de contador) são sinalizadas e o equipamento fica fora
do total consolidado até revisão.

Limitação conhecida: impressões ocorridas entre a última leitura de um período e
a primeira do período seguinte são atribuídas conforme o timestamp das leituras.
Leituras mais frequentes aumentam a precisão; por isso, o painel informa o
intervalo realmente observado e usa o fuso local do computador. Mais detalhes em
[`docs/arquitetura.md`](docs/arquitetura.md) e
[`docs/limitacoes-fabricantes.md`](docs/limitacoes-fabricantes.md).

## Estrutura do projeto

```
src/print_monitor/   código-fonte (config, db, models, printers, collector, snmp, reports, cli)
tests/               testes automatizados (cálculo e persistência)
docs/                documentação técnica
docs/obsidian/       notas em Markdown compatíveis com Obsidian
scripts/             execução e geração de dados fictícios
data/                banco SQLite local (ignorado pelo Git)
```

## Executável Windows (.exe)

Há um executável pronto na página de
[**Releases**](https://github.com/enzo-going/print-monitor-local/releases)
(não requer Python instalado). Basta baixar e executar.

Para gerar o executável a partir do código-fonte:

```powershell
.\build.ps1
```

O banco SQLite é criado em `data\print_monitor.db` **ao lado do executável**,
fora dele. Sem argumentos (duplo clique), o `.exe` abre o painel em uma **janela
nativa** (pywebview/WebView2), sem navegador nem console — todas as ações
(cadastrar ou pausar impressoras, coletar, revisar histórico, descobrir,
relatórios, filtros e exportação) são feitas pela interface. Com argumentos,
funciona como CLI.
Detalhes em [`docs/empacotamento.md`](docs/empacotamento.md).

## Testes

```powershell
ruff check src tests scripts
python -m pytest
```

## Configuração

Copie `.env.example` para `.env` e ajuste os valores. O `.env` e o banco em
`data/` não são versionados. Nenhuma credencial é armazenada no repositório.
O painel inclui proteção CSRF e cabeçalhos de segurança, mas continua sendo uma
ferramenta local: mantenha o host padrão `127.0.0.1` e não o exponha diretamente
à internet.

## Licença

Distribuído sob a licença [MIT](LICENSE).
