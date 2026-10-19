# Status operacional — tema, funil Senac e medição

Data: 19/10/2026. Escopo: consolidar o ponto de partida depois do cutover do
Belvedere, da reescrita Gutenberg das páginas internas do funil Senac e da
publicação do VOLC Measurement v3.3. Este documento é um painel de estado; os
recibos específicos continuam sendo a autoridade das respectivas mudanças.

## Veredito executivo

- O tema ativo é o Belvedere 1.39.5. O tema anterior e o MU-plugin de
  consentimento foram preservados no backup de rollback; o aviso nativo está
  ativo e o wrapper opcional do tema permanece desligado.
- O GTM live é a versão 38 (`VOLC Measurement v3.3 - 2026-10-19`). Os fontes
  publicados de `WEBS Wrapper v2` e `VOLC Sensor v3.3` conferem por hash com o
  repositório, estão ativos e sem requisito adicional de Consent Mode.
- As tags `GA4 - Pageview`, `Google Ads - Base - CreditUp`, as três conversões
  de ad view, `GA4 - adViewInterstitial` e o Conversion Linker continuam
  presentes, ativos e ligados aos triggers esperados. Esta prova confirma a
  configuração live; não inventa uma impressão nem uma conversão de anúncio.
- O caminho first-party está vivo: o heartbeat mais recente observado às
  15:15 BRT veio da LP Senac, versão de payload 3.1. REST anônimo de
  `raw_events` respondeu 401 e origem inválida foi recusada.
- Entre 14:00 e 15:15 BRT, o Supabase oficial recebeu 151 eventos distribuídos
  pelas cinco páginas do funil Senac. Houve `volc_sensor_ready` nas cinco,
  além de scroll, engajamento, clique interno, render e viewability GPT onde
  aplicável. Quatro eventos preservaram campanha e conteúdo numéricos.
- A pré-sell e as três soluções estão publicadas no novo padrão
  Gutenberg/Belvedere. A LP Elementor 2306 foi deliberadamente preservada.

## Funil Senac em produção

| Papel | Post | URL | Estado comprovado |
| --- | ---: | --- | --- |
| LP | 2306 | `/r/guia-cursos-senac/` | Publicada; Elementor preservado; não reescrita nesta rodada |
| Pré-sell | 2309 | `/rec/por-onde-comecar-senac-pr/` | Publicada; 5 botões; 0 link externo no conteúdo |
| Solução 1 | 2312 | `/rec/tipos-de-curso-senac-p1/` | Publicada; 2 botões; links oficiais externos permitidos |
| Solução 2 | 2315 | `/rec/bolsas-de-estudo-senac-p2/` | Publicada; 2 botões; diretório oficial das 27 UFs |
| Solução 3 | 2318 | `/rec/portal-do-senac-do-seu-estado-p3/` | Publicada; 2 botões; links oficiais externos permitidos |

Os títulos, slugs e IDs foram preservados. Os slots JoinAds `code-block-1` e
`code-block-2` continuam fora de grupos, colunas, cards ou fundos decorados;
isso evita que o conteúdo editorial passe a envelopar visualmente o anúncio.
Há revisão/backup por post para rollback. Os hashes do conteúdo implantado são:

- 2309: `ad84921b...`;
- 2312: `5dd760f1...`;
- 2315: `48bec726...`;
- 2318: `2ff58f8c...`.

## Prova de medição pós-mudança

Janela read-only: 19/10/2026, 14:00–15:15 BRT.

| Caminho | Eventos | Sinais observados |
| --- | ---: | --- |
| `/r/guia-cursos-senac/` | 13 | ready, scroll, engajamento, clique interno, render GPT |
| `/rec/por-onde-comecar-senac-pr/` | 55 | ready, scroll, engajamento, clique, dwell, render/viewability GPT |
| `/rec/tipos-de-curso-senac-p1/` | 13 | ready, scroll, dwell, render/viewability GPT |
| `/rec/bolsas-de-estudo-senac-p2/` | 37 | ready, scroll, engajamento, clique, dwell, render/viewability GPT |
| `/rec/portal-do-senac-do-seu-estado-p3/` | 33 | ready, scroll, engajamento, dwell, render/viewability GPT |

Interpretação honesta:

- provado: GTM v38 live, Sensor/Wrapper íntegros, eventos first-party chegando e
  campanha numérica preservada;
- configurado e ativo: tags GA4 e Google Ads e seus triggers;
- não forçado nesta auditoria: impressão/interstitial ou conversão artificial;
- ainda a observar: cobertura de campanha maior ou igual a 0,90 por sete dias
  e confirmação de recepção nas superfícies GA4/Google Ads, respeitando o atraso
  próprio dessas plataformas.

## Quadro de trabalho reconciliado

| Frente | Tarefa | Estado | Próxima prova que fecha o gap |
| --- | --- | --- | --- |
| Tema + publicação | P08-T13 | `partial` | codificar o padrão Belvedere/Gutenberg no motor e provar novo funil sem edição manual |
| Campanha → funil → URL | P08-T02 | `partial` | registrar o vínculo canônico da campanha ativa ao funil e às cinco URLs |
| Telemetria da jornada | P08-T07 | `partial` | owner/schedule/replay do agregador e `fact_funnel_daily` corrente |
| Campaign ID no Sensor | P08-T11 | `partial` | sete dias consecutivos com cobertura de atribuição maior ou igual a 0,90 |
| Consentimento operacional | P08-T12 | `done` | sem gap técnico; revisão jurídica continua externa |
| Destino pago | P05-T13 | `partial` | reauditar a LP `/r`, emitir recibo `paid_destination_ready` e só então retomar mídia |
| FunnelForge | P10-T22 | `partial` | transformar o padrão aprovado em saída repetível do engine e medir resultado real |
| Coleta Google | P06-T10 | `partial` | completar sete dias sem zero sintetizado e alinhar leitores históricos |
| Autoridade de ledger | P06-T11 | `todo` | ADR do owner e inventário de consumidores antes de desligar legados |
| Runs órfãos | P10-T28 | `partial` | migration `abandoned`, reaper efetivo, dead letter e sete dias sem órfãos |
| Inteligência Google Ads | P09-T14 | `partial` | consolidar coleta oficial e usar o read model na auditoria da campanha |
| Bia/Hermes | P09-T04 | `partial` | capability gateway único e prova governada de funil/campanha |

## Ordem curta recomendada

1. Monitorar P08-T11 e P06-T10 sem mudar o runtime durante a janela de sete
   dias.
2. Reauditar a LP 2306 e fechar P05-T13 antes de qualquer mudança de bidding ou
   retomada agressiva de mídia.
3. Registrar campanha → funil → cinco URLs, fechando o elo de P08-T02.
4. Auditar a campanha Senac com custo, receita, termos, palavras-chave,
   conversões e destinos já sobre o novo ponto de medição.
5. Só depois decidir lances, orçamento e experimento controlado.

## Fontes

- `docs/operations/VOLC-MEASUREMENT-V32-2026-10-19.md`
- `docs/operations/VOLC-MEASUREMENT-V33-CONSENT-BR-2026-10-19.md`
- `measurement/gtm/manifest.json`
- `volc-os-workbook/ROADMAP-VIVO.json`
- `docs/volc-os-graph/curadoria-operacional.json`
