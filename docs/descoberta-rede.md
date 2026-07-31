# Descoberta de impressoras na rede

A descoberta procura, em uma faixa de IPs informada, hosts que aceitam conexão
TCP em portas típicas de impressão e, opcionalmente, confirma o equipamento
lendo o contador via SNMP.

## Abordagem segura (não agressiva)

A implementação é deliberadamente conservadora:

- **Faixa explícita**: exige uma faixa informada (`--network`); não varre redes
  inteiras por conta própria. A tela sugere a faixa da própria máquina, mas quem
  confirma é o usuário.
- **Limite de tamanho**: recusa faixas maiores que `--max-hosts` (padrão 1024),
  evitando varreduras amplas (ex.: `/16`, `/8`).
- **Sondagem leve**: apenas um pequeno conjunto de portas (9100 RAW/JetDirect,
  631 IPP, 515 LPD), com timeouts curtos e concorrência limitada.
- **Somente TCP connect**: estabelece e encerra a conexão; não envia payloads
  nem explora serviços.
- **Somente leitura SNMP**: com `--snmp`, lê o contador e a identificação para
  distinguir impressoras de outros dispositivos com essas portas. Nenhuma
  escrita, nenhuma alteração no equipamento.

## Formatos de faixa aceitos

Exigir CIDR de quem nunca ouviu falar em CIDR era o maior obstáculo desta tela.
`netaddr.normalize_network` aceita:

| Você escreve      | Vira             |
|-------------------|------------------|
| `192.168.0.0/24`  | `192.168.0.0/24` |
| `192.168.0`       | `192.168.0.0/24` |
| `192.168.0.*`     | `192.168.0.0/24` |
| `192.168.0.1-254` | `192.168.0.0/24` |
| `192.168.0.35`    | `192.168.0.0/24` |

Faixas ambíguas demais (`192.168`) são recusadas com uma mensagem explicando o
que falta.

## Confiança nos resultados

Cada candidato recebe um rótulo, porque outros dispositivos também abrem
631/515 e sem isso o usuário não tem como julgar o que vale cadastrar:

- **Confirmada** — respondeu ao SNMP e informou o contador;
- **Muito provável** — porta 9100 (impressão direta) aberta;
- **Possível** — apenas IPP ou LPD.

O que já está cadastrado aparece marcado, e o cadastro é feito apenas sobre os
itens selecionados, com nome e setor editáveis.

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
