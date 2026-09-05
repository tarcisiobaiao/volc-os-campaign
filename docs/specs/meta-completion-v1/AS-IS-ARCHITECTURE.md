# Meta Ads — arquitetura adjudicada no candidato

Veredito: **META_COMPLETION_SPEC_PARTIAL**. Base documental: `884393b0e99b5ee403a6f38e1e4225012705f942`, ainda sem adjudicação da Bia. O código existe; o canário remoto não está provado.

## Autoridade e limites

O inventário JSON contém 54 evidências com arquivo e linha. Código e schemas vivos prevalecem para existência; somente recibos reais provam o escopo remoto. A documentação oficial decide o contrato do provider, não a aceitação de um payload específico.

O metadado ignorado UPDATE_STATUS.json, lido somente na worktree de origem e não versionado na base, registra `1ad7b8a888adeae8d3b1d36d6b3a58d16360ca95`, anterior à base. Todas as consultas pedidas foram feitas com graphify; ambiguidades e conceitos sem correspondência foram resolvidos pela leitura do código/roadmap, não por inferência de arestas. O índice wiki não existe. Nenhum grafo foi atualizado.

Curadoria: `docs/volc-os-graph/curadoria-operacional.json:270`. Roadmap: `volc-os-workbook/ROADMAP-VIVO.json:1504`, `:1516`, `:1523`. P11-T03, P11-T05 e P11-T06 continuam partial. Trechos antigos “sem executor/rota” estão superados pelo código montado, não por prova remota.

## Caminho atual

```text
UI de criação real
  -> rotas locais admin/loopback
  -> plano estreito + resolução de conta/Page/imagem
  -> compilador e hash
  -> validate_only das raízes
  -> recibo durável candidato -> aprovação
  -> executor + ledger por passo -> POST PAUSED
  -> ID durável -> read-back
  -> reconciliação por leitura e recibo

UI de inventário/settings/dashboard
  -> majoritariamente demo, não o caminho acima

Leitura real -> snapshot -> RPC candidato -> read model
CAPI v21 legado -> fluxo independente, não mensuração governada de AdSet
```

Montagem: `backend/app/main.py:188`, `:191`, `:197`. As rotas de criação estão em `backend/app/routers/trafego_meta_criacao.py:351`, `:438`, `:517`, `:635`. Não há rota Meta de ativação montada.

O nome solicitado `MetaCrPage.tsx` não existe: a superfície real é `src/pages/trafego/MetaCriacaoPage.tsx:523`. Ela aprova/cria/reconcilia; inventário e detalhes ainda usam demonstração (`src/components/trafego/meta/MetaInventarioDemo.tsx:50`, `src/pages/trafego/MetaObjetoPage.tsx:42`). O dashboard canônico Meta usa dados demo (`src/pages/MetaCampaignInsightPage.tsx:50`).

## O que está comprovado

- Leitura histórica de quatro contas e suas hierarquias, Pages, Instagram e fontes/conversões: `docs/closure/meta-real-read-integration-v1/REAL-READ-PROOF.json:1`. Insights retornaram zero linhas naquele recorte; isso não prova ingestão positiva de métricas.
- Campaign e AdCreative estático passaram por validate_only histórico: `docs/closure/meta-creation-engine-operator-experience-v1/PROVA-VALIDATE-ONLY-REAL.md:66`. Cobertura INDEPENDENT_ROOTS_ONLY, zero objetos; AdSet e Ad pendentes. A prova é transcrição sanitizada anterior, não recibo durável novo desta base.
- Receita/hashes/flags/guards/SQL/testes existem no código. Gates históricos incluem testes herméticos e PostgreSQL descartável; não foram repetidos nesta missão. O relatório também registra falhas preexistentes, portanto não é prova de suíte integral verde.

Não inspecionamos segredo, flags de processos, schema oficial ou objetos Meta atuais. A ausência de migration/canário oficial é a declaração dos artefatos existentes; não foi atualizada por consulta externa.

## Decisões implementadas e lacunas

| Área | Implementado | Limite adjudicado |
|---|---|---|
| Compilação | Traffic/LPV, ABO/BRL, Campaign/AdSet/Ad PAUSED | Campos internos/defaults não equivalem a decisão explícita |
| Validação | Raízes independentes; dependentes no executor | Recibo condicionado às flags de criação |
| Aprovação | Ator/hash/conta/orçamento/expiração e recibo | Não sela manifesto criativo/content SHA |
| Ledger | Prepara antes do POST; ID antes do read-back | Ausência temporal não prova causalidade; adoção crossapproval |
| Read-back | Identidade/payload/status comparados | Ausência de Advantage aceita; máscara Creative e status herdados precisam correção |
| Reconciliação | Sem reenvio na rota | Só AMBIGUOUS, depende do inventário vivo e flags de criação |
| Persistência | Schemas/RPCs/read model candidatos | Sem prova oficial; escopo/ack/custódia/insights têm lacunas |
| CAPI | Roteador legado v21 | Evento/id defaults e privacidade não governados pela receita de Ads |

O journal antes de criar e a gravação do ID antes do read-back são decisões corretas que devem ser preservadas. O fechamento “verificado” precisa ser outro fato durável. Testes locais não provam o status que a Meta devolverá.

## Riscos críticos, com autoridade

1. `backend/app/routers/trafego_meta_validacao.py:86`: booleans omitidos viram false. A saída é conservadora, mas a escolha do operador foi inventada.
2. `backend/app/trafego/meta_execucao/compilador.py:197`: hash não inclui contratos da fábrica, bytes verificados ou política/expiração.
3. `backend/app/trafego/meta_execucao/executor.py:557`: read-back não exige presença de todas as decisões críticas; herança PAUSED legítima pode ser rejeitada. Creative não deve receber PAUSED.
4. `backend/app/trafego/meta_execucao/reconciliacao.py:166`: nome e data são indícios, não identidade causal. Creative sem created_time é inconclusivo quando encontrado; vazio ainda pode fechar ausência.
5. `supabase/migrations/20260904183418_meta_create_paused_executor.sql:749`: piso de120s não impede despacho tardio. Não substitui ownership persistente nem prova de não despacho.
6. `backend/app/routers/trafego_meta_criacao.py:517`: recovery depende de flags de criação e ativos resolvidos novamente; uma imagem removida pode impedir leitura de objetos já criados.
7. `backend/app/trafego/meta/adaptador.py:506`: LPV inclui ViewContent indevidamente. `:280`: atribuição pedida não vira parâmetros e breakdowns perdem valores reais.
8. `backend/app/trafego/meta/persistencia.py:163`: observado_em entra na chave do insight, multiplicando observações. Actions por ordinal não são chave semântica.
9. `backend/app/trafego/meta/read_model.py:36`: blacklist superficial não elimina todos os IDs; consulta por conta não é uniforme.
10. `supabase/migrations/v15_02_meta_ads_insights.sql:158`: descoberta marca custódia verificada sem decisão humana.
11. `src/components/trafego/meta/MetaConfiguracaoLocal.tsx:36`: onboarding transitório leva token ao estado React. “Token nunca no navegador” é objetivo futuro, não descrição factual completa.
12. `supabase/functions/capi-router/index.ts:32`: CAPI v21 independente; não presumir obsolescência pela expiração da Marketing API.

## Provider vigente

O [changelog v26](https://developers.facebook.com/docs/graph-api/changelog/version26.0/) declara lançamento em29/07/2026. A tabela resumida de versões ainda diverge para Marketing; o registro oficial detalhado prevalece. A versão efetivamente respondida pelo runtime não foi lida.

A mudança de destino para loja em criativos elegíveis e a expansão por defaults de placements exigem decisão explícita. O campo interno WEBSITE não pode ser copiado cegamente para destination_type do AdSet Traffic. O registro de fontes contém ambiguidades e provas mínimas necessárias, sem inventar payload.

A [referência de Creative](https://developers.facebook.com/docs/marketing-api/reference/ad-creative/) não oferece PAUSED. Pode reutilizar Creative existente e object_story_spec pode produzir post não publicado. Aprovação precisa cobrir esses efeitos; zero ativação refere-se aos três nós veiculáveis.

## Arquitetura de conclusão

P0 corrige somente a receita estática, selagem de intenção/ativo, receipt/approval/dispatch, concorrência, read-back/recovery e projeção mínima do recibo. P1 entrega operação confiável e métricas. P2 entrega mensuração/Leads/Sales/CAPI. P3 amplia formatos, controles e automação.

Creative é entidade de biblioteca associável a vários Ads; não redesenhar os engines de imagem/vídeo. O contrato compartilhado está em META-COMPLETION-SPEC e suas divergências permanecem em OPEN-CONTRACT-CONFLICTS.

Nenhuma migration, execução de produto ou mutação externa ocorreu nesta missão. O pacote é instrução para executores, não autorização para executá-la.
