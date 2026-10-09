# Oportunidade real: FGTS Saque-Aniversário

O fechamento anterior do redator foi salvo separadamente em `bdaa8c6`.
Esta rodada partiu da oportunidade real 65, entidade e cluster lidos por
SELECT no Supabase operacional. Não reutilizou um card fictício ou a
arquitetura congelada do canário anterior.

## Escopo real

O caminho foi pré-pesquisa → prompt atual do arquiteto do backend → arquitetura
tipada → complemento factual em lote → pacotes congelados → workers do motor
único, perfil `completo`, com três workers → revisão batelada → composição e
gates. O disparo foi pelo pipeline Python existente, não pela fila/rota HTTP
do Pautador. Não houve publisher, WordPress, escrita no Supabase ou Ads.

Todas as chamadas usaram `gpt-6.1-sol` pelo adaptador `chatgpt_plan` existente,
sem API key nem fallback faturado. O servidor não informa custo em dinheiro:
consumo de quota do plano não é custo zero comprovado.

Screenshots oficiais e widgets estavam ligados. A geração de imagem estava
desligada explicitamente porque não havia provedor de imagem faturado
autorizado/configurado nesta execução. Portanto esta prova **não cobre a
imagem obrigatória da LP nem publicação em lote**. JEV e mineração paga de
PAA não foram acionados; os termos vieram do cluster real já disponível.

## Primeiro canário e correção mínima

O arquiteto levou 369,901 s e produziu oito páginas. A execução completa
levou 1.002,959 s: dez chamadas genéricas de modelo (arquiteto, oito writers
e revisão) mais quatro chamadas nativas de pesquisa/estruturação. As duas
chamadas da pré-pesquisa reaparecem no dossiê como os mesmos response IDs:
foram contadas uma vez, não duas. Pico observado de redação: três.

Oito textos foram gerados, mas três writers falharam e só uma página chegou
ao gate final com OK. A prova real revelou dois defeitos corrigidos:

- **Link descartado vazando para o writer:** os pacotes traziam as rotas
  resolvidas e também `editorial.links` com slugs originais que o roteamento
  já descartara. A projeção do prompt agora apresenta somente hrefs internos
  realmente resolvidos. Não altera o pacote congelado, seu SHA nem o grafo.
- **Nome de comando confundido com percentual financeiro:** o rótulo oficial
  “Solicite seu saque 100% digital” estava em fato verificado do tipo processo,
  mas era recusado como uma promessa numérica. Agora só um rótulo literal
  completo entre aspas, presente no fato de processo e com a mesma fonte
  resolvida e citada, ancora esse uso. Isso não libera percentuais financeiros
  fora das aspas, rótulos inventados, fatos não citáveis ou fonte não resolvida.

Sete regressões: três falharam antes do delta; o recorte ficou 58/58 verde.
Suíte integral após as correções: **1.526 aprovados, 7 pulados, zero falhas**.
O ouro V1 continua aprovado. Não houve expansão do framework ou do fluxo.

## Retomada real limitada

Somente p6–p8 foram reescritas pelos workers originais: três chamadas em
paralelo e uma revisão batelada, 187,473 s. Nenhuma nova pesquisa/arquitetura.
Plano, briefings, fatos, pacotes/dossiê e textos p1–p5 ficaram idênticos por
SHA-256. Todas as três redações e seus gates finais passaram.

| Página | Estado final da prova |
| --- | --- |
| p1 · LP | Writer OK, revisor aprovou, gate final FAILED por `cta_editorial_execution` |
| p2 · Comparação de modalidade | Writer OK, revisão humana; rótulos de CTA precisam de conferência contextual |
| p3 · Consulta no aplicativo | Writer OK, revisão humana; não foi aprovado por decisão do operador |
| p4 · Valor anual | Writer OK, revisão humana; tabela/cálculo sem evidência suficiente, ferramenta desativada |
| p5 · Calendário | Revisão e gate final OK; não inclui datas atuais sem lastro |
| p6 · Solicitação pelo aplicativo | Retomada: revisão e gate final OK |
| p7 · Saldo retido | Retomada: revisão e gate final OK |
| p8 · Saque após demissão | Retomada: revisão e gate final OK |

Total desta prova: **18 requisições reais de modelo**, oito rascunhos locais,
quatro gates finais OK, zero publicações. Não se deve chamar “oito páginas
aprovadas” ou “motor pronto para publicar em lote” a esse resultado.

## Entrega e próximos ajustes

Scripts, snapshots, textos, recibos, pesquisas e imagens capturadas foram
preservados fora dos commits em
`/Users/mac/Desktop/VOLC-OS-CAMPAIGN/canarios/google-quatro-canais-real-20261009/`.
`entrega.md` contém os oito textos; `previews/` é apenas diagnóstico Chromium
local, com recibo e capturas. A imagem da LP, tema/PHP/Elementor/plugin/ads
em execução real e ferramentas sustentadas não estão certificados.
Foram renderizadas 16 vistas (oito páginas, mobile e desktop), sem overflow
horizontal nem erros JavaScript; os checks locais executados passaram. Seis
prints oficiais ficaram registrados como atuais e sem overlay, em quatro
páginas. Isso não prova que o tema em produção renderiza os mesmos assets.
Os caminhos absolutos internos dos recibos registram o local original da
execução; antes de retomar de novo, resolver os artefatos na pasta arquivada.

Próxima intervenção mínima: conferir contextualidade dos CTAs da LP/p2 e o
motivo da revisão de p3; fornecer evidência oficial vigente de tabela/cálculo
para p4 ou adequar sua promessa/entrega. Não regenerar pesquisa e oito páginas
às cegas, não inserir aprovação humana fictícia e não desligar gates.

P10-T22 permanece `partial`; nó `cap_funnel`. Não houve push, deploy,
migration, campanha nova, ativação, alteração financeira ou publicação.
