---
tags: [projeto/print-monitor-local, riscos]
tipo: nota
---

# Riscos e limitações

## Limitações do método

- **Sem histórico, sem passado**: meses anteriores ao início da coleta não podem
  ser recuperados — só existe o contador acumulado atual.
- **Precisão depende da frequência**: impressões entre a última leitura de um mês
  e a primeira do mês seguinte são atribuídas conforme o timestamp das leituras.
  Coletas diárias reduzem o erro nas bordas do mês.
- **Reset/troca de contador**: substituição do equipamento ou zeragem derruba o
  valor; o cálculo descarta diferenças negativas, mas o volume daquele intervalo
  fica subestimado.

## Limitações por equipamento

- Nem toda impressora expõe o contador via SNMP (ver
  `docs/limitacoes-fabricantes.md`).
- Color/mono e frente/verso podem ser contabilizados de formas diferentes.
- OIDs proprietários exigem mapeamento por modelo.

## Riscos operacionais

- **Coleta na rede** (Fase 3/4): evitar varredura agressiva; preferir alvos
  cadastrados e testes controlados de portas/serviços.
- **Credenciais**: community string e segredos ficam no `.env` (não versionado).
- **Dados**: o banco com leituras reais não é versionado; exemplos e seeds usam
  apenas dados fictícios.

## Mitigações adotadas

- Cálculo robusto a *rollover*.
- Backend plugável com fallback mockado.
- Configuração por ambiente, sem segredos no código.

## Ligações

- [[roadmap]]
- [[decisões-tecnicas]]
