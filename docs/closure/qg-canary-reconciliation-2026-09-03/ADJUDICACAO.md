# Adjudicação do marco do canário Search pausado

Data: 2026-09-03

## Veredito

`P05-T11` está concluída como marco de nascimento controlado de campanha Search.

O estado anterior misturava o ato de criar o primeiro canário com lacunas de
observabilidade, vínculo editorial, mensuração e reconciliação que possuem donos
próprios no Roadmap Vivo. Essas lacunas não foram apagadas nem promovidas:

- vínculo editorial permanece em `P05-T04`;
- recibo e projeção no cockpit permanecem em `P05-T05`;
- plano de mensuração permanece em `P05-T12`;
- observabilidade de campanha pausada permanece em `P09-T14`.

## Evidência factual

- Em 28/08/2026, a API do Google Ads aceitou o primeiro canário Search real e a
  releitura confirmou campanha `PAUSED`, sem ativação.
- Em 01/09/2026, um novo canário Search nasceu pelo ledger v10 completo; o
  recibo foi fechado com sucesso e a releitura confirmou uma única campanha
  `PAUSED`, Search Partners desligado e zero alteração de metas.
- Em 03/09/2026, uma nova execução autorizada pelo proprietário confirmou de
  novo o caminho operacional: `validate_only` passou, uma única criação foi
  aceita e o read-back confirmou Search, `MANUAL_CPC`, orçamento diário de
  R$ 10, CPC máximo de R$ 1, quatro keywords em correspondência de frase,
  Search Partners e Display Network desligados e campanha `PAUSED`.
- A revisão de política dessa última campanha continuava em andamento. Isso não
  equivale a aprovação de política nem autoriza ativação.

A evidência de 03/09 foi recebida por handoff operacional sanitizado da
Bia/Hermes e não contém credenciais nem identificadores integrais de conta ou
campanha.

## Limite do aceite

Este fechamento prova nascimento pausado e ausência de ativação. Não prova
campanha pronta para gastar, mensuração pronta, Smart Bidding, vínculo editorial
correto, política aprovada, H0 completo ou reconciliação de caso indeterminado.

