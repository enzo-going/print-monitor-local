# print-monitor-local

Ferramenta **local** para monitorar impressoras de rede, identificá-las por IP
e contabilizar o volume de impressão ao longo do tempo.

Impressoras de rede expõem um **contador acumulado** de páginas — não o volume
de um mês específico. Esta ferramenta coleta o contador total em leituras
periódicas, guarda o histórico em SQLite e calcula o volume de cada período
pela **diferença entre leituras**.

> Exemplo: contador `120000` em 01/06 e `124500` em 30/06 → **4500 impressões**.

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

# 4. Coletar leitura (backend simulado por padrão)
python -m print_monitor collect --all

#    Coletar via SNMP real (community/timeout vêm do ambiente ou do .env)
python -m print_monitor collect --all --backend snmp

# 5. Relatório mensal (volume por impressora)
python -m print_monitor report --year 2026 --month 6

# 6. Exportar o relatório mensal em CSV (filtros opcionais)
python -m print_monitor export --year 2026 --month 6 --location Financeiro --output relatorio.csv

# 7. Dashboard local (Flask) em http://127.0.0.1:5000
python -m print_monitor serve

# 8. Descobrir impressoras em uma sub-rede (abordagem segura)
python -m print_monitor discover --network 192.168.0.0/24 --snmp
```

> O dashboard exige o extra opcional `dashboard`: `pip install -e ".[dashboard]"`.
> Ele oferece filtros por mês, impressora, IP e local, total mensal, ranking das
> impressoras mais usadas e exportação CSV.

Para popular o banco com dados **fictícios** e ver relatórios imediatamente:

```powershell
python scripts/seed.py
python -m print_monitor report --year 2026 --month 6
```

## Coleta SNMP

A coleta real usa SNMP (v1/v2c) e é implementada em **Python puro** sobre a
biblioteca padrão (sem dependências nativas), o que simplifica o empacotamento.
Por padrão lê o OID `prtMarkerLifeCount` (Printer-MIB, RFC 3805). A *community
string* e os tempos de espera vêm do ambiente ou do `.env` (ver `.env.example`),
nunca do código.

Impressoras incompatíveis ou inacessíveis são registradas como falha sem
interromper a coleta das demais. O backend padrão é o simulado (`mock`); use
`--backend snmp` (ou `PRINT_MONITOR_BACKEND=snmp`) para a coleta real. Limitações
por fabricante/modelo: [`docs/limitacoes-fabricantes.md`](docs/limitacoes-fabricantes.md).

## Como o volume é calculado

Para um período, o volume é a soma das diferenças **positivas** entre leituras
consecutivas dentro do intervalo. Diferenças negativas (reset/troca de contador)
são descartadas, evitando valores incorretos.

Limitação conhecida: impressões ocorridas entre a última leitura de um período e
a primeira do período seguinte são atribuídas conforme o timestamp das leituras.
Leituras mais frequentes aumentam a precisão. Mais detalhes em
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
(cadastrar/remover impressoras, coletar, descobrir, relatórios, filtros e
exportação) são feitas pela interface. Com argumentos, funciona como CLI.
Detalhes em [`docs/empacotamento.md`](docs/empacotamento.md).

## Testes

```powershell
python -m pytest
```

## Configuração

Copie `.env.example` para `.env` e ajuste os valores. O `.env` e o banco em
`data/` não são versionados. Nenhuma credencial é armazenada no repositório.

## Licença

Uso interno / proprietário.
