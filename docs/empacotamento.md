# Empacotamento Windows (.exe)

O executável é gerado com PyInstaller a partir de `scripts/pm_entry.py`,
produzindo um único arquivo `dist\print-monitor.exe`.

## Gerar o executável

```powershell
.\build.ps1
```

O script:

1. cria um ambiente virtual isolado (`.build-venv`) com apenas as dependências
   necessárias, evitando que pacotes não relacionados do Python global entrem
   no pacote;
2. instala o extra `build` declarado no `pyproject.toml`, que centraliza Flask,
   PyInstaller e pywebview;
3. empacota em arquivo único, incluindo templates, CSS e JavaScript do
   dashboard (`--add-data`).

Resultado: `dist\print-monitor.exe`.

Cada comando nativo tem seu código de saída verificado. Antes do empacotamento,
o executável anterior é removido; assim, uma falha não pode ser confundida com
um artefato antigo. O script também confirma que o novo `.exe` existe e não está
vazio antes de anunciar sucesso.

## Banco de dados fora do executável

Em modo empacotado (`sys.frozen`), a aplicação resolve o diretório base como a
**pasta do executável** (ver `config.app_base_dir`). O banco é criado em
`data\print_monitor.db` ao lado do `.exe`, permanecendo gravável e **fora** do
executável. O `.env` (se houver) também é lido dessa pasta.

## Uso do executável

```powershell
# Ajuda e subcomandos
dist\print-monitor.exe --help

# Inicializar o banco (cria dist\data\print_monitor.db)
dist\print-monitor.exe init

# Cadastrar, coletar e relatar
dist\print-monitor.exe add-printer --name "HP 1" --ip 192.168.0.50
dist\print-monitor.exe collect --all
dist\print-monitor.exe report --year 2026 --month 6

# Duplo clique no .exe (sem argumentos): abre o dashboard em uma janela nativa
dist\print-monitor.exe
```

## Atualização segura

O histórico não fica dentro do executável. Ao instalar uma nova versão,
substitua somente o `.exe` e preserve `data\print_monitor.db` e o `.env`.

Exemplo com uma pasta de instalação genérica:

```powershell
$installDir = "C:\PrintMonitor"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $installDir "backup\$stamp"

# Feche a janela do aplicativo antes de copiar os arquivos.
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item (Join-Path $installDir "data\print_monitor.db") $backupDir
if (Test-Path (Join-Path $installDir ".env")) {
    Copy-Item (Join-Path $installDir ".env") $backupDir
}

Copy-Item ".\dist\print-monitor.exe" $installDir -Force
```

Depois da atualização, abra o aplicativo e confira a visão mensal e o
histórico. Se houver problema, feche-o e restaure o banco salvo no backup.

## Verificação

A execução foi validada de duas formas:

- via Python (`python -m print_monitor ...` e `python -m pytest`);
- via executável (`dist\print-monitor.exe`): CLI (`--help`, `init`,
  `add-printer`, `collect`, `report`) e dashboard (`/`, `/readings`,
  `/printers`, `/static/app.css` e `/export.csv` respondendo 200).

O workflow de CI repete os testes e a verificação de formato, gera e instala o
wheel e, em um runner Windows, executa `build.ps1` e um teste rápido do `.exe`.
Essas etapas têm limite de tempo para evitar execuções presas.

## Publicar uma versão

O workflow `Release` é acionado por uma tag no formato `vX.Y.Z`. Antes de
publicar, ele exige que a versão da tag seja igual às versões do
`pyproject.toml` e de `print_monitor.__version__` e que o commit pertença à
`main`. Em seguida, executa lint, formatação e testes e constrói o executável em
um runner Windows limpo.

Com tudo aprovado, o workflow cria a GitHub Release por meio do GitHub CLI e
anexa somente:

- `print-monitor.exe`;
- `SHA256SUMS`, com o checksum SHA-256 do executável.

Antes de enviar a tag, atualize a versão e o changelog na `main`, aguarde o CI
ficar verde e então execute, substituindo o número pelo release desejado:

```powershell
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

## Observações

- O `.exe`, a pasta `build\`, o `.build-venv\` e o `print-monitor.spec` gerado
  não são versionados (ver `.gitignore`).
- O executável é específico para Windows x64. Para outras plataformas, gere o
  pacote no respectivo sistema.
- O arquivo único é descompactado em uma pasta temporária a cada execução, o que
  adiciona um pequeno atraso na inicialização; é o comportamento esperado do
  modo *one-file*.
