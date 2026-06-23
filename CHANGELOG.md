# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento conforme [SemVer](https://semver.org/lang/pt-BR/).

## [1.0.0] — 2026-06-23

Primeira versão pública. As cinco fases do roadmap (base, dashboard, coleta SNMP,
descoberta e empacotamento Windows) estão disponíveis.

### Adicionado

- Integração contínua (GitHub Actions): a suíte de testes roda automaticamente em
  Python 3.11, 3.12 e 3.13 a cada push e pull request na `main`.
- Distribuição do executável Windows (`print-monitor.exe`) pela página de
  Releases.
- Badges de CI, versão de Python, licença e release no README.

### Alterado

- Licença alterada para MIT (antes restrita a uso interno).

## [0.7.2] — 2026-06-19

### Corrigido

- O arquivo `.env` passa a ser lido por um parser próprio (stdlib), sem depender
  de `python-dotenv`. No executável empacotado, a biblioteca não era incluída e
  o `.env` era ignorado — fazendo a coleta cair no backend `mock` em vez de
  `snmp`. Agora `PRINT_MONITOR_BACKEND=snmp` é respeitado também no `.exe`.

### Removido

- Extra opcional `env` (`python-dotenv`): não é mais necessário.

## [0.7.1] — 2026-06-19

### Corrigido

- **SNMP**: `snmp_get` passa a validar o *request-id* e o IP de origem da
  resposta, descartando pacotes tardios/duplicados. Sem isso, coletas
  sequenciais rápidas (`collect --all`) podiam atribuir a leitura de uma
  impressora a outra — ou gerar números para impressoras que não responderam.
  Validado contra impressoras reais (leituras consistentes entre coletas).

## [0.7.0] — 2026-06-19

### Adicionado

- Importação de impressoras a partir de planilha CSV, na interface (upload na
  página Impressoras) e na CLI (`import-printers --file`).
- Mapeamento flexível de colunas (SETOR, MARCA, MODELO, IP, N° SÉRIE), tolerante
  a acentos e ao separador `,` ou `;` (Excel pt-BR); IPs já cadastrados são
  ignorados.
- Exemplo fictício em `docs/exemplo-impressoras.csv` e testes da importação.

## [0.6.0] — 2026-06-18

### Adicionado

- Mini app de janela nativa: sem argumentos, o executável abre o painel em uma
  janela própria (pywebview/WebView2), sem navegador nem console.
- Ações de gestão na interface (sem linha de comando): cadastrar e remover
  impressoras, coletar leituras (mock/snmp) e descobrir impressoras na rede.
- Mensagens de status (flash) e nova página de descoberta no painel.
- `db.delete_printer`; rotas POST `/printers/add`, `/printers/<id>/delete`,
  `/collect` e `/discover` (GET/POST).
- Testes das novas ações da interface (cadastro, remoção, coleta, descoberta).

### Alterado

- `build.ps1` empacota em modo janela (`--windowed`) e inclui o pywebview no
  ambiente isolado de build.

### Corrigido

- No executável de janela, o modo linha de comando passa a anexar ao console do
  processo pai, garantindo a saída no terminal (`AttachConsole`).

## [0.5.0] — 2026-06-18

### Adicionado

- Empacotamento Windows com PyInstaller: `build.ps1` gera
  `dist\print-monitor.exe` (arquivo único) a partir de `scripts/pm_entry.py`.
- Build em ambiente isolado (`.build-venv`) para um executável enxuto (~12 MB),
  com os templates do dashboard incluídos no pacote.
- Experiência de duplo clique: sem argumentos, o executável inicia o dashboard
  e abre o navegador.
- Documentação de empacotamento em `docs/empacotamento.md`.

### Alterado

- `config.app_base_dir`: em modo empacotado (`sys.frozen`), o banco SQLite e o
  `.env` passam a ser resolvidos na pasta do executável, mantendo o banco
  **fora** do `.exe` e gravável.

## [0.4.0] — 2026-06-18

### Adicionado

- Descoberta de impressoras na rede (`print-monitor discover`) com abordagem
  segura: faixa CIDR explícita, limite de hosts, timeouts curtos, concorrência
  limitada e verificação de poucas portas (9100/631/515).
- Confirmação opcional via SNMP (`--snmp`) e cadastro automático dos hosts
  encontrados (`--register`).
- Documentação de riscos e responsabilidade em `docs/descoberta-rede.md`.
- Testes da descoberta (contagem de hosts, sondagem TCP via loopback, limite de
  segurança).

## [0.3.0] — 2026-06-18

### Adicionado

- Coleta SNMP (v1/v2c) real implementada em Python puro (BER sobre a biblioteca
  padrão), sem dependências nativas — facilita o empacotamento.
- Seleção de backend de coleta (`mock` ou `snmp`) por ambiente
  (`PRINT_MONITOR_BACKEND`) ou pela flag `--backend` do comando `collect`.
- Tratamento de impressoras incompatíveis/inacessíveis: a falha de uma não
  interrompe a coleta das demais; os erros são reportados ao final.
- Testes do SNMP (codificação BER, GET via loopback UDP, timeout) e da
  orquestração de coleta.

### Alterado

- O comando `collect` passa a informar o backend usado e a retornar código de
  saída diferente de zero quando há falhas.

### Removido

- Extra opcional `snmp` (pysnmp): a coleta SNMP não depende mais de bibliotecas
  externas.

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
