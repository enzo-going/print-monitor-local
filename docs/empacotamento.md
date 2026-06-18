# Empacotamento Windows (.exe)

O executável é gerado com PyInstaller a partir de `scripts/pm_entry.py`,
produzindo um único arquivo `dist\print-monitor.exe`.

## Gerar o executável

```powershell
.\build.ps1
```

O script:

1. cria um ambiente virtual isolado (`.build-venv`) com apenas as dependências
   necessárias (Flask), evitando que pacotes não relacionados do Python global
   entrem no pacote e mantendo o executável enxuto;
2. instala o PyInstaller nesse ambiente;
3. empacota em arquivo único, incluindo os templates do dashboard
   (`--add-data`).

Resultado: `dist\print-monitor.exe` (aproximadamente 12 MB).

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

# Duplo clique no .exe (sem argumentos): inicia o dashboard e abre o navegador
dist\print-monitor.exe
```

## Verificação

A execução foi validada de duas formas:

- via Python (`python -m print_monitor ...` e `python -m pytest`);
- via executável (`dist\print-monitor.exe`): CLI (`--help`, `init`,
  `add-printer`, `collect`, `report`) e dashboard (`/`, `/printers`,
  `/export.csv` respondendo 200).

## Observações

- O `.exe`, a pasta `build\`, o `.build-venv\` e o `print-monitor.spec` gerado
  não são versionados (ver `.gitignore`).
- O executável é específico para Windows x64. Para outras plataformas, gere o
  pacote no respectivo sistema.
- O arquivo único é descompactado em uma pasta temporária a cada execução, o que
  adiciona um pequeno atraso na inicialização; é o comportamento esperado do
  modo *one-file*.
