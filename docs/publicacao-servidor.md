# Publicação em um servidor Windows

A ferramenta costuma ficar em um servidor, não na estação: é a máquina que fica
ligada, e a coleta diária é o que faz o histórico existir. Esta nota descreve o
procedimento de publicar uma versão nova sem perder o que já foi coletado.

## Por que são dois scripts

Copiar arquivo para o compartilhamento administrativo (`\\servidor\C$`) costuma
funcionar; **executar** comando remoto costuma estar bloqueado (WinRM fechado,
RPC negado). Então o trabalho é dividido:

| Script | Onde roda | O que faz |
|---|---|---|
| `scripts/publicar-no-servidor.ps1` | na estação | copia o código, preservando dados |
| `scripts/instalar-no-servidor.ps1` | no servidor, por RDP | ambiente Python, tarefas, painel |

## 1. Liberar o compartilhamento

A conta de domínio costuma receber acesso negado no `C$`; a conta **local** do
servidor funciona. Digite a senha você mesmo:

```powershell
$cred = Get-Credential 192.168.20.29\Administrador
New-PSDrive -Name S -PSProvider FileSystem -Root \\192.168.20.29\C$ -Credential $cred -Persist
```

A sessão SMB vale para todo o logon. Se o `net use` parecer travado ao pedir a
senha, é só ele não ecoar nada — o `Get-Credential` evita a confusão.

## 2. Copiar

```powershell
.\scripts\publicar-no-servidor.ps1 -Simular   # confere a lista primeiro
.\scripts\publicar-no-servidor.ps1
```

**O que é preservado:** a pasta `data\` (banco de contadores) e o `.env` do
servidor nunca são sobrescritos. Isso não é detalhe: o histórico de leituras é
irrecuperável, porque a impressora só informa o total acumulado de agora.

O script grava um `VERSAO-PUBLICADA.txt` no destino, para quem for mexer depois
saber o que está rodando sem abrir o código.

## 3. Instalar, pelo RDP

```powershell
powershell -ExecutionPolicy Bypass -File C:\PrintMonitor\scripts\instalar-no-servidor.ps1
```

Ele cria/atualiza o ambiente Python, registra as duas tarefas agendadas e
reinicia o painel na versão nova. Pode ser executado a cada atualização.

## Particularidades do servidor do CAMPS (192.168.20.29)

- **Porta 5056**, não 5000 — a 5000 é do Certificador ICP-Brasil.
- **Não tem WebView2** (Windows Server 2016), então o modo "janela nativa" não
  funciona ali. Desde a 1.3.1 o programa cai para o navegador padrão sozinho.
- O painel **não tem login** e por isso só aceita conexões de `localhost`. Ele
  se consulta pelo navegador dentro do próprio servidor; a porta aparecer
  fechada de fora é o comportamento esperado, não uma falha.
- O perfil ativo é `C:\Users\Administrador.WIN-GU00V3BG4E1` (nome antigo da
  máquina). Atalho colocado em `C:\Users\Administrador` não aparece para
  ninguém.
- A máquina é PDC do domínio, além de DHCP/DNS/IIS: nada de reiniciar serviço de
  borda fora de janela agendada.

## Conferir depois

```powershell
Get-ScheduledTaskInfo -TaskName PrintMonitor-Coleta    # LastTaskResult 0 = ok
Get-ScheduledTaskInfo -TaskName PrintMonitor-Painel
Start-ScheduledTask   -TaskName PrintMonitor-Coleta    # coletar agora
```

`LastTaskResult` só é diferente de zero quando **nenhuma** impressora respondeu;
com o parque parcialmente desligado a coleta ainda é considerada bem-sucedida.
