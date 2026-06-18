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

## Estratégia adotada

1. Tentar `prtMarkerLifeCount` (padrão Printer-MIB).
2. Se indisponível, registrar a impressora como **incompatível** e seguir sem
   interromper a coleta das demais.
3. Documentar aqui os OIDs específicos confirmados por modelo, à medida que
   forem validados em campo.

## Modelos validados

> A preencher durante a Fase 3, com modelo, firmware e OID confirmado.

| Fabricante | Modelo | Firmware | OID do total | Observações |
|------------|--------|----------|--------------|-------------|
| —          | —      | —        | —            | —           |
