# Descoberta de impressoras na rede

A descoberta procura, em uma faixa de IPs informada, hosts que aceitam conexão
TCP em portas típicas de impressão e, opcionalmente, confirma o equipamento
lendo o contador via SNMP.

## Abordagem segura (não agressiva)

A implementação é deliberadamente conservadora:

- **Faixa explícita**: exige um CIDR informado (`--network`); não varre redes
  inteiras por conta própria.
- **Limite de tamanho**: recusa faixas maiores que `--max-hosts` (padrão 1024),
  evitando varreduras amplas (ex.: `/16`, `/8`).
- **Sondagem leve**: apenas um pequeno conjunto de portas (9100 RAW/JetDirect,
  631 IPP, 515 LPD), com timeouts curtos e concorrência limitada.
- **Somente TCP connect**: estabelece e encerra a conexão; não envia payloads
  nem explora serviços.
- **Confirmação opcional**: com `--snmp`, tenta ler o contador total para
  distinguir impressoras de outros dispositivos com essas portas.

## Uso

```powershell
# Listar candidatos em uma sub-rede /24
python -m print_monitor discover --network 192.168.0.0/24

# Confirmar via SNMP (lê o contador) e cadastrar os encontrados
python -m print_monitor discover --network 192.168.0.0/24 --snmp --register

# Ajustes finos
python -m print_monitor discover --network 192.168.0.0/26 --ports 9100,631 --timeout 0.5 --workers 16
```

## Riscos e responsabilidade

- **Autorização**: execute apenas em redes que você administra ou está
  autorizado a inspecionar. Varredura não autorizada pode violar políticas
  internas ou a lei.
- **Falsos positivos**: outros dispositivos podem expor 9100/631/515. A
  confirmação por SNMP (`--snmp`) reduz, mas não elimina, ambiguidade.
- **Falsos negativos**: impressoras com firewall, em VLAN separada ou com essas
  portas desativadas não aparecem.
- **Impacto na rede**: mesmo conservadora, a sondagem gera conexões. Prefira
  faixas pequenas e horários de baixo uso; aumente `--max-hosts` apenas de forma
  consciente.
- **SNMP**: a *community string* vem do ambiente/`.env`. Não use credenciais
  reais em exemplos ou testes.
