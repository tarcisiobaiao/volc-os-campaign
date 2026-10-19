# VOLC Measurement v3.2 — IDs numéricos de atribuição

Data: 19/10/2026  
Site: `creditoup.com.br`  
Tarefa: `P08-T11`

## Resultado

A versão 37 do container `GTM-N4KS27ZV`, `VOLC Measurement v3.2 -
2026-10-19`, foi publicada a partir da versão 36. Somente duas tags foram
alteradas:

- `VOLC Sensor v3.2`;
- `WEBS Wrapper v2`.

IDs numéricos de 6 a 20 dígitos agora passam somente em `utm_campaign` e
`utm_content`. Os demais campos continuam sob o filtro anti-PII. O Wrapper
também deixou de herdar a campanha anterior quando uma nova UTM está presente,
mas é inválida. Nenhuma tag de conversão, acionador ou consentimento foi
alterado.

O protocolo enviado ao `volc-ingest` continua `3.1`; não houve mudança de
schema, Edge Function ou banco.

## Provas

- 19 testes focados verdes, incluindo execução do JavaScript real das tags;
- CPF formatado, e-mail e sequência numérica fora das chaves liberadas seguem
  bloqueados;
- quick preview do GTM: zero erro de compilação;
- releitura da versão live: v37, nomes, HTML, triggers e consentimentos iguais
  ao manifesto versionado;
- canário público sem clique em anúncio e com endpoints de conversão bloqueados:
  `utm_campaign=987654321098` e `utm_content=876543210987` persistiram da LP
  para a pré-sell;
- duas linhas `volc_sensor_ready` foram relidas em `raw_events`, uma por página,
  ambas com os IDs numéricos e `paid=1`;
- canário de valor inválido provou que a campanha antiga não é reaproveitada.

Os eventos sintéticos foram identificados por `utm_source` começando em
`volc_qa_v32_`; nenhum anúncio foi clicado e nenhuma campanha foi modificada.

## Rollback

Republicar a versão 36 do container. Ela permanece intacta e corresponde a
`VOLC Measurement v3.1 - 2026-10-16`.

## Limite restante

A correção operacional está provada. A tarefa permanece `partial` até a métrica
`dq_cobertura_atribuicao_sensor` ficar em pelo menos 0,90 por sete dias. Click
IDs continuam fora de `raw_events` por desenho.
