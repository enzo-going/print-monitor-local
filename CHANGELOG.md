# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento conforme [SemVer](https://semver.org/lang/pt-BR/).

## [1.4.0] — 2026-08-12

### Adicionado

- Publicação no servidor por script: `scripts/publicar-no-servidor.ps1` monta o
  pacote e copia para o destino, e `scripts/instalar-no-servidor.ps1` faz a parte
  que precisa rodar lá dentro. O procedimento existia só na cabeça de quem
  instalou da primeira vez.

### Corrigido

- O diagnóstico de uma impressora que não responde passa a distinguir
  **equipamento desligado** de **SNMP desabilitado**. Antes, os dois casos
  recebiam "verifique se o equipamento está ligado" — conselho inútil para uma
  impressora que está ligada e atendendo na porta 9100, e que só precisa ter o
  SNMP habilitado no painel. Quando o SNMP silencia, a ferramenta testa as portas
  de impressão e web antes de concluir; se o host atende, a mensagem manda
  habilitar o SNMP, e se não atende, lembra que impressoras em DHCP trocam de
  endereço sozinhas.
- A mensagem estava duplicada em três lugares (coleta, teste de conexão na tela e
  comando `test`), então cada um dizia uma coisa. Agora sai de `diagnose_silence`.

## [1.3.1] — 2026-08-07

### Corrigido

- O aplicativo abre no navegador padrão quando a janela nativa não pode ser
  criada. A janela depende do runtime **WebView2**, que não vem instalado no
  Windows Server — onde a ferramenta costuma ficar, justamente por ser a máquina
  que fica ligada para a coleta diária. Antes, a falta do runtime só produzia uma
  caixa de erro e o encerramento: o programa estava inteiro e funcionando, mas
  não havia como chegar até ele sem linha de comando. A alternativa pelo
  navegador já existia para o caso de o pywebview não estar instalado; agora vale
  também quando ele está presente e mesmo assim não consegue abrir a janela.

## [1.3.0] — 2026-07-31

Foco no atrito de quem cadastra e diagnostica as impressoras, e em fazer a
leitura do contador funcionar em mais modelos.

### Adicionado

- Correção automática do endereço IP digitado: espaços e caracteres invisíveis
  colados de PDF ou Word, vírgula no lugar do ponto, a letra `O`/`l` no lugar de
  `0`/`1`, `http://` na frente, `:9100` no fim e zeros à esquerda. O que não dá
  para interpretar vira uma mensagem dizendo o que corrigir — “falta 1 número”,
  “o número 300 é maior que 255” — no lugar de um “IP inválido” seco.
- Aviso ao vivo no formulário mostrando como o endereço será salvo. A página
  consulta a mesma função usada no cadastro, para o aviso nunca discordar do que
  é gravado.
- Botão **Testar conexão**: consulta o IP na hora, informa se o equipamento
  responde e preenche nome, modelo, série e local com o que ele publica.
- Leitura do contador em OIDs proprietários de HP, Ricoh, Kyocera, Brother,
  Lexmark, Xerox, Samsung e Epson, tentados quando o `prtMarkerLifeCount` padrão
  responde que não é suportado. Modelos de entrada que não implementam a
  Printer-MIB completa deixam de ficar permanentemente sem contador.
- Identificação do equipamento por SNMP (`sysName`, `sysDescr`, `sysLocation`,
  modelo e número de série).
- Faixa de rede da própria máquina detectada e sugerida na tela de descoberta,
  que passa a aceitar formatos livres (`192.168.0`, `192.168.0.*`,
  `192.168.0.1-254`) além do CIDR.
- Resultados da descoberta com nome sugerido pelo próprio equipamento, marcação
  do que já está cadastrado, nível de confiança (confirmada / muito provável /
  possível) e seleção do que cadastrar — em vez de cadastrar tudo em bloco.
- Comando `test <ip>` na CLI, para separar “impressora desligada” de “IP errado”
  e de “SNMP desabilitado” sem precisar cadastrar nada antes.
- Página **Ajuda**, explicando em linguagem comum por que são necessárias duas
  leituras e o que verificar quando algo não funciona.

### Alterado

- `discover --register` cadastra com o nome, modelo e série informados pelo
  equipamento, em vez de “Impressora `<IP>`”.
- Os palpites de OID de fabricante usam tempo limite mais curto e sem tentativas
  extras: um agente real ignora em silêncio o OID que não conhece, e cada
  palpite custaria a espera inteira.

### Corrigido

- `collect --all` só retorna código de erro quando **nenhuma** impressora
  responde. Em um parque real sempre há alguma desligada, e o comportamento
  anterior marcaria a tarefa diária do Agendador do Windows como falha quase
  todo dia — um alarme que dispara sempre ensina a ser ignorado, justamente o
  alarme que deveria avisar quando a coleta parar de vez.
- A coleta agendada deixa de ser inacessível para quem roda a partir do código:
  `agendar-coleta.ps1` exigia `dist\print-monitor.exe` e falhava sem ele, embora
  a coleta periódica seja justamente o que faz os relatórios existirem. Agora
  localiza o Python do `.venv` ou do sistema, usa `pythonw` para não abrir uma
  janela de console todo dia e ganhou a opção `-Remover`.

## [1.2.0] — 2026-07-30

### Adicionado

- Edição de nome, IP, local, modelo e número de série sem apagar o histórico
  nem alterar o estado ativo ou pausado da impressora.
- Configuração `SNMP_VERSION`, com suporte explícito a equipamentos SNMP v1 e
  v2c, além de transporte IPv4 e IPv6.
- Workflow de Release que valida a versão, constrói o executável em um runner
  Windows limpo e publica o `.exe` acompanhado do checksum SHA-256.
- Validação de wheel e do executável Windows no CI.

### Alterado

- O horário de cada leitura passa a representar a chegada da resposta do
  equipamento, preservando a ordem correta em coletas simultâneas.
- O painel diferencia linha de base ausente, reset e leituras conflitantes no
  mesmo horário, mantendo resultados não consolidados fora do total.
- A exportação baixada pelo painel usa UTF-8 com BOM e separador `;`, facilitando
  a abertura direta no Excel em português.
- Cadastro e edição compartilham normalização e limites de tamanho dos campos.

### Corrigido

- Pausar ou remover uma impressora durante a consulta deixa de reverter as
  leituras válidas das demais impressoras do lote.
- Contadores fora do intervalo aceito pelo SQLite são recusados com mensagem
  controlada, sem causar erro 500 ou perder outras leituras.
- A coleta SNMP rejeita respostas de outra porta ou com OID divergente.
- Contadores diferentes registrados no mesmo instante deixam de produzir um
  volume mensal falso.
- Filtros de impressora, IP e local são preservados depois de coletar.
- Dezembro de 9999 deixa de causar estouro no cálculo dos limites mensais.
- A importação informa linhas preenchidas sem IP, arquivos vazios e os primeiros
  detalhes de erro diretamente na interface.
- O build Windows interrompe imediatamente em falhas nativas, remove artefatos
  antigos e só anuncia sucesso após validar o novo executável.

## [1.1.0] — 2026-07-29

### Adicionado

- Histórico de leituras na interface, com cadastro de linha de base manual,
  diferença desde a leitura anterior e filtro por impressora.
- Correção reversível: uma leitura pode ser ignorada nos cálculos e restaurada
  depois, preservando a auditoria.
- Cobertura do relatório por impressora, distinguindo resultado medido,
  cobertura parcial, contador sem aumento, espera por linha de base e reset.
- Coleta em lote concorrente, configurável por `PRINT_MONITOR_WORKERS` ou
  `collect --workers`, mantendo a gravação SQLite em uma única transação.
- Proteção CSRF, limite de upload, validação do cabeçalho `Host` e cabeçalhos de
  segurança no dashboard local; o servidor sem autenticação recusa exposição
  fora dos endereços de loopback.
- Ruff na suíte de desenvolvimento e no GitHub Actions.
- Validação de limites de descoberta e testes para pacotes SNMP malformados.

### Alterado

- Interface reorganizada em torno da produção mensal, com nomes dos meses,
  atalhos de período, contador acumulado claramente identificado, horário local,
  estados vazios explicativos e proteção contra clique duplo na coleta.
- CSV e CLI distinguem um zero efetivamente medido de um período ainda sem
  intervalo suficiente; o CSV inclui estado e cobertura.
- Pausar uma impressora substitui a exclusão como ação principal e preserva
  todo o seu histórico; a exclusão definitiva exige confirmação.
- O modo simulado foi movido para opções de teste para reduzir o risco de
  contaminar relatórios reais.
- A coleta SNMP real passa a ser o padrão; o backend simulado continua
  disponível explicitamente para demonstrações e testes.
- O dashboard agora mostra impressoras ativas, quantidade de leituras, última
  coleta e o último contador salvo por impressora.
- Relatórios mensais passam a carregar as leituras do período em uma consulta,
  eliminando o padrão N+1 para parques com muitas impressoras.
- SQLite passa a usar WAL, espera por bloqueios e índice por período para
  permitir leitura do dashboard durante coletas.
- Configurações numéricas do ambiente agora aceitam timeout decimal e produzem
  erros claros para valores inválidos.

### Corrigido

- O relatório mensal agora usa a última leitura válida anterior ao início do
  mês como linha de base, sem perder o primeiro delta do período; intervalos
  que começam antes da abertura são identificados como cobertura parcial.
- Uma única leitura deixa de ser apresentada como zero mensal confirmado e
  passa a indicar que ainda não há intervalo suficiente.
- Limites de mês e horários do dashboard passam a respeitar o fuso local do
  computador.
- Contadores negativos, booleanos ou não inteiros retornados por um backend são
  rejeitados antes de qualquer gravação no histórico.
- Meses com queda/reset de contador deixam de entrar no total consolidado até
  revisão da leitura, e exportações CSV neutralizam fórmulas de planilha em
  campos importados.
- A ação "Coletar agora" orienta o cadastro quando não há impressoras ativas e
  explica que a primeira leitura cria a linha de base do cálculo.
- A coleta pelo painel respeita o backend configurado, e ações de ignorar ou
  restaurar uma leitura preservam o mês e os filtros em uso.
- O timestamp devolvido por uma coleta individual agora é exatamente o mesmo
  persistido no banco.
- O parser BER/SNMP agora rejeita mensagens truncadas de forma controlada.

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
