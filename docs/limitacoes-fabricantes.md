# Limitações por fabricante/modelo

A leitura de contadores depende do suporte da impressora a SNMP e da exposição
do contador total. Esta nota reúne pontos de atenção a confirmar em campo
durante a Fase 3.

## Padrão de referência

O OID mais portável entre fabricantes é o **Printer-MIB** (RFC 3805):

- `prtMarkerLifeCount` — `1.3.6.1.2.1.43.10.2.1.4.1.1`
  (contador total de páginas do marcador 1).

Quando disponível, deve ser a primeira opção.

## Pontos de atenção comuns

| Tema                      | Observação                                                        |
|---------------------------|-------------------------------------------------------------------|
| SNMP desabilitado         | Muitas impressoras vêm com SNMP desligado; exige habilitar.       |
| Versão SNMP               | v1/v2c usam *community string*; v3 exige usuário/credenciais.     |
| Community string          | Padrão `public` costuma ser alterado por segurança.               |
| Color vs. mono            | Alguns modelos separam contadores por cor; o total pode diferir.  |
| Frente/verso              | Contagem por página física pode diferir de "impressões lógicas".  |
| OIDs proprietários        | Alguns fabricantes só expõem o total em OIDs próprios.            |
| Reset/troca de contador   | Substituição ou zeragem causa queda no valor (tratada no cálculo).|
| Firmware                  | OIDs e comportamento podem variar entre versões de firmware.      |

## OIDs alternativos tentados

Vários equipamentos de entrada não implementam a Printer-MIB completa, mas
expõem o total em um ramo próprio. Quando o OID padrão responde que não o
suporta, a ferramenta tenta, nesta ordem (`snmp.VENDOR_TOTAL_COUNTER_OIDS`):

| Fabricante               | OID                                        |
|--------------------------|--------------------------------------------|
| Printer-MIB (marcador 2) | `1.3.6.1.2.1.43.10.2.1.4.1.2`              |
| HP                       | `1.3.6.1.4.1.11.2.3.9.4.2.1.4.1.2.5.0`     |
| Ricoh                    | `1.3.6.1.4.1.367.3.2.1.2.19.5.1.9.1`       |
| Kyocera                  | `1.3.6.1.4.1.1347.42.2.1.1.1.6.1.1`        |
| Brother                  | `1.3.6.1.4.1.2435.2.3.9.4.2.1.5.4.5.1.0`   |
| Samsung/HP               | `1.3.6.1.4.1.236.11.5.1.1.1.1.0`           |
| Lexmark                  | `1.3.6.1.4.1.641.2.1.5.1.9.1`              |
| Xerox                    | `1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.1`     |
| Epson                    | `1.3.6.1.4.1.1248.1.2.2.27.1.1.5.1.1`      |

São **tentativas**, não garantias: variam com modelo e firmware. Por isso só
entram depois do padrão, sem tentativas extras e com tempo limite mais curto —
um agente real apenas ignora em silêncio o OID que não conhece, então cada
palpite custaria uma espera inteira.

## Identificação do equipamento

Além do contador, a ferramenta lê, quando disponível:

| Dado          | OID                          |
|---------------|------------------------------|
| `sysDescr`    | `1.3.6.1.2.1.1.1.0`          |
| `sysName`     | `1.3.6.1.2.1.1.5.0`          |
| `sysLocation` | `1.3.6.1.2.1.1.6.0`          |
| Modelo        | `1.3.6.1.2.1.25.3.2.1.3.1`   |
| Nº de série   | `1.3.6.1.2.1.43.5.1.1.17.1`  |

Campos ausentes ficam vazios; nenhum é obrigatório para a coleta funcionar. É o
que permite à descoberta cadastrar “RICOH IM C3000 — Recepção” em vez de
“Impressora 192.168.20.31”.

## Estratégia adotada

1. Tentar `prtMarkerLifeCount` (padrão Printer-MIB), com as tentativas extras
   configuradas em `SNMP_RETRIES`.
2. Se ele **expirar**, parar: o equipamento está inacessível ou com SNMP
   desligado, e percorrer o resto da lista só faria o usuário esperar.
3. Se ele responder “não suportado”, tentar os OIDs de fabricante em ordem.
4. Se nada funcionar, registrar a falha com a explicação correspondente e seguir
   com as outras impressoras. A distinção importa: “não respondeu” e “respondeu
   mas não publica o contador” pedem ações corretivas diferentes.
5. Documentar abaixo os OIDs confirmados por modelo, à medida que forem
   validados em campo.

## Modelos validados

> A preencher com modelo, firmware e OID confirmado.

| Fabricante | Modelo | Firmware | OID do total | Observações |
|------------|--------|----------|--------------|-------------|
| —          | —      | —        | —            | —           |
