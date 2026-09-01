# P04-T07 PMAX REAL READ V1 — certificação factual

**Data:** 2026-09-01
**Branch:** `sprint/hermes-p04-t07-pmax-real-read-v1`
**Base:** `7eaa93faef9d9546b09462ee8380496dc5e679e8`
**Veredito da 1ª rodada:** `NO_ELIGIBLE_PMAX`
**Veredito da 2ª rodada (topologia corrigida):** `REAL_READ_PARTIAL` — ver §11

> As seções 1 a 10 descrevem a **primeira** rodada e continuam valendo como o
> registro dela: a leitura forçava `login_customer_id`, 9 de 13 contas
> responderam `USER_PERMISSION_DENIED` e nenhum alvo PMax foi encontrado. Elas
> não foram reescritas. A partir da §11 está a rodada corretiva, que achou alvo
> real e expôs o que a v25 recusa.

## 1. Escopo executado

A missão retomou na worktree já criada e executou leitura Google Ads API real **somente read-only**, usando o arquivo canônico `/root/google-ads.yaml` sem imprimir, copiar ou versionar conteúdo de credencial.

Nenhuma chamada Supabase foi executada. Nenhuma mutation Google Ads foi executada. Nenhum schema, Roadmap, grafo, n8n ou deploy foi tocado.

## 2. Credencial e ambiente

Validações feitas sem expor valores:

| Item | Resultado |
|---|---|
| `/root/google-ads.yaml` | presente |
| owner | `root:root` |
| modo | `600` |
| tamanho | maior que zero |
| `GoogleAdsClient.load_from_storage(..., version="v25")` | OK |
| SDK | `google-ads 31.4.0` |
| API | `v25` |
| variáveis de escrita Google/Supabase/FORGE | ausentes/desarmadas |

## 3. Guarda objetiva de zero mutate

Métodos chamados registrados no artefato sanitizado:

- `CustomerService.ListAccessibleCustomers` — prova mínima de autenticação/escopo;
- `GoogleAdsService.SearchStream` — descoberta read-only de campanhas PMax.

Bloqueio local configurado no runner: qualquer serviço/método contendo `mutate`, `create`, `update`, `remove`, `upload` ou `apply` abortaria antes da rede. Nenhuma tentativa bloqueada ocorreu.

## 4. Descoberta PMax real

Consulta mínima executada, hash no `REAL-READ-SUMMARY.json`:

```sql
SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type
FROM campaign
WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
  AND campaign.status != 'REMOVED'
```

Resultado sanitizado:

| Medida | Resultado |
|---|---|
| contas acessíveis via credencial | 13 pseudônimos |
| contas com query verde e zero PMax | 4 |
| contas que recusaram acesso na consulta de campanha | 9 (`USER_PERMISSION_DENIED`, sanitizado) |
| campanhas PMax elegíveis encontradas | 0 |

Como nenhuma campanha PMax elegível foi encontrada nas contas consultáveis dentro do escopo autorizado, a missão parou sem inventar fixture real e sem ampliar carteira. O veredito `NO_ELIGIBLE_PMAX` deve ser lido com esta cobertura: **4/13 contas responderam verde sem PMax; 9/13 não foram inspecionadas por negativa de permissão e não foram transformadas em zero**.

## 5. Sete famílias PMax

Não foram executadas porque não houve alvo PMax real elegível. Estados por família:

| Família | Estado |
|---|---|
| `PMAX_CAMPANHA` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_ASSET_GROUPS` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_ASSET_GROUP_ASSETS` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_ASSETS` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_DESEMPENHO_ASSET_GROUP` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_SINAIS` | `inelegivel` — sem alvo PMax autorizado |
| `PMAX_RECOMENDACOES_FORCA` | `inelegivel` — sem alvo PMax autorizado |

## 6. `asset_group_asset.performance_label`

Não adjudicado nesta execução porque a regra da missão manda parar ao não encontrar alvo PMax real. O próximo run com alvo PMax elegível deve executar, nesta ordem:

1. `GoogleAdsFieldService` para `asset_group_asset.performance_label`;
2. query GAQL mínima real contendo `asset_group_asset.performance_label` no alvo PMax.

Estado literal desta missão: `INCONCLUSIVE`, causa medida: `NO_ELIGIBLE_PMAX`.

## 7. Artefato sanitizado

`REAL-READ-SUMMARY.json` contém somente:

- pseudônimos de contas;
- hashes de query;
- estados semânticos;
- contagens;
- request ids hasheados;
- versão API/SDK;
- erros sanitizados.

Não contém conteúdo do YAML, tokens, IDs crus de conta/campanha, nomes de campanha ou payload bruto de produção.

## 8. Runbook para futura certificação com alvo elegível

1. Garantir que uma das contas autorizadas consultáveis pela credencial tenha campanha `PERFORMANCE_MAX` `ENABLED` ou `PAUSED` e `status != REMOVED`.
2. Reexecutar a missão nesta branch ou em nova lane factual, sem Supabase.
3. Selecionar alvo determinístico: preferir `PAUSED`, depois ordem por hash estável.
4. Executar separadamente as sete famílias PMax.
5. Adjudicar `asset_group_asset.performance_label` por FieldService + query real.
6. Só então classificar `REAL_READ_PROVEN` ou `REAL_READ_PARTIAL`.

## 9. Revisão factual fresca

Revisão Claude Opus de contexto fresco sobre os artefatos sanitizados: **APROVAR**, sem achados bloqueantes.

Achados não bloqueantes preservados:

- o runner de certificação foi externo à árvore; a evidência durável fica nos artefatos sanitizados versionados;
- `NO_ELIGIBLE_PMAX` é veredito de cobertura parcial: 4 contas verdes sem PMax, 9 contas com `USER_PERMISSION_DENIED` sanitizado;
- `performance_label` permanece `INCONCLUSIVE` porque não houve alvo PMax para executar FieldService + query mínima.

## 10. Confirmações

- zero Google Ads mutate;
- zero validate mutate;
- zero create/update/remove/upload/apply;
- zero Supabase read/write;
- zero migration;
- zero n8n;
- zero deploy;
- zero Roadmap/grafo;
- zero dados brutos versionados;
- zero segredo versionado.

---

# 2ª rodada — topologia corrigida e alvo real

## 11. O que a correção de topologia mudou

Testar as contas **diretamente**, sem forçar `login_customer_id`, eliminou as
negativas de permissão da §4. A mesma credencial, a mesma consulta mínima, outra
topologia de chamada:

| Medida | 1ª rodada | 2ª rodada |
|---|---|---|
| contas acessíveis | 13 | 13 |
| verdes com PMax | 0 | **1** (12 campanhas) |
| vazio confirmado | 4 | **12** |
| `USER_PERMISSION_DENIED` confirmado | 9 | **0** |
| topologia não resolvida | — | 0 |
| falhou | — | 0 |

Alvo determinístico selecionado: preferir `PAUSED`, depois hash estável. Alvo
escolhido `PAUSED`, pseudônimos e hashes no `REAL-READ-SUMMARY.json`.

O veredito `NO_ELIGIBLE_PMAX` da 1ª rodada não era um fato sobre a carteira: era
um fato sobre **como a leitura estava sendo feita**. Registrar as 9 negativas em
vez de tratá-las como zero foi o que permitiu descobrir isso.

## 12. As sete famílias contra a v25 real

| Família | Estado na leitura real | Causa |
|---|---|---|
| `PMAX_CAMPANHA` | `com_dados` | 1 linha |
| `PMAX_ASSET_GROUPS` | `falhou` | `UNRECOGNIZED_FIELD` em 4 campos de `asset_coverage` |
| `PMAX_ASSET_GROUP_ASSETS` | `falhou` | `UNRECOGNIZED_FIELD` em 3 campos de `primary_status_details` |
| `PMAX_ASSETS` | `vazio_confirmado` ❌ | sem asset ids — **por causa da família anterior ter falhado** |
| `PMAX_DESEMPENHO_ASSET_GROUP` | `com_dados` | 4 linhas na janela |
| `PMAX_SINAIS` | `vazio_confirmado` ❌ | sem asset group ids — **mesma dependência falha** |
| `PMAX_RECOMENDACOES_FORCA` | `falhou` | `UNRECOGNIZED_FIELD` em 2 campos da recomendação |

Os dois ❌ são erro de contrato, não de API: uma família cuja consulta prerequisita
falhou não observou vazio nenhum. Corrigido nesta rodada.

## 13. `asset_group_asset.performance_label` — adjudicado

`NOT_SUPPORTED_IN_V25`, por `GoogleAdsFieldService` (0 linhas) mais GAQL mínima
real (recusada com `UNRECOGNIZED_FIELD`). O `INCONCLUSIVE` da §6 está fechado.
O campo permanece fora das consultas e nomeado em `CAMPOS_NAO_SUPORTADOS_V25`.

## 14. Correção aplicada

Detalhe completo, campo a campo, em **`LINHAGEM-CORRECAO-V25.md`**. Em resumo:

- os nove campos recusados saíram da projeção, **sem substituto**, com a perda
  de cobertura declarada por campo no recibo de cada família e no resumo
  sanitizado que o CLI imprime;
- `assert_sem_campos_recusados()` impede a reintrodução, inclusive vinda do
  builder da outra lane;
- família dependente de leitura que caiu passou a ser `falhou` com causa
  estruturada `DEPENDENCIA_FALHOU:<familia>`, e a decisão mora na projeção — não
  só no coletor, que era por onde o runner da leitura real escapava dela.

Commits: `23fbcf3` (evidência), `5e935f5` (contraprovas, 13 falhando),
`808e940` (correção, 70 passando).

## 15. Runbook para fechar `REAL_READ_PROVEN`

A correção é provada **sem rede**, contra um dublê que reproduz o erro real. Ela
não substitui uma certificação real. Para fechar:

1. reexecutar a leitura real no mesmo alvo, com a topologia da §11;
2. confirmar `PMAX_ASSET_GROUPS`, `PMAX_ASSET_GROUP_ASSETS` e
   `PMAX_RECOMENDACOES_FORCA` verdes, e `PMAX_ASSETS`/`PMAX_SINAIS` com estado
   observado de verdade;
3. só então classificar `REAL_READ_PROVEN`.

Enquanto isso não acontecer, o veredito honesto é `REAL_READ_PARTIAL`.
---

# 3ª rodada — pós-correção, leitura real certificada

## 16. Resultado final pós-correção

Após os commits `5e935f5` e `808e940`, a leitura real foi reexecutada no mesmo critério determinístico de alvo (`PAUSED`, depois hash estável), sem Supabase e com a topologia corrigida (`direct_without_login_customer_id`).

**Veredito final do artefato:** `REAL_READ_PROVEN`.

Cobertura final de contas:

| Classe | Contagem |
|---|---:|
| `verde_com_pmax` | 1 |
| `vazio_confirmado` | 12 |
| `permission_denied_confirmado` | 0 |
| `topologia_nao_resolvida` | 0 |
| `falhou` | 0 |

Alvo final sanitizado: campanha `PAUSED`, canal `PERFORMANCE_MAX`, com `customer_pseudo`, `campaign_pseudo` e `campaign_name_hash` no `REAL-READ-SUMMARY.json`.

## 17. Estados finais das sete famílias

| Família | Estado final | Contagem sanitizada |
|---|---|---:|
| `PMAX_CAMPANHA` | `com_dados` | 1 |
| `PMAX_ASSET_GROUPS` | `com_dados` | 4 |
| `PMAX_ASSET_GROUP_ASSETS` | `com_dados` | 137 |
| `PMAX_ASSETS` | `com_dados` | 123 |
| `PMAX_DESEMPENHO_ASSET_GROUP` | `com_dados` | 4 |
| `PMAX_SINAIS` | `com_dados` | 4 |
| `PMAX_RECOMENDACOES_FORCA` | `vazio_confirmado` | 0 |

Nenhuma família terminou `falhou` por incompatibilidade conhecida. `PMAX_RECOMENDACOES_FORCA` verde com zero recomendações ficou `vazio_confirmado`, não falha.

## 18. Campos removidos/substituídos

Nenhum dos nove campos recusados ganhou substituto sem prova. Todos foram removidos da projeção da coleta e nomeados em `CAMPOS_RECUSADOS_PELA_API_V25` com cobertura perdida.

Adicionalmente, a rodada final consultou `GoogleAdsFieldService` para os nove campos recusados: todos voltaram `not_found` (`row_count=0`) na metadata v25. Isso reforça a decisão de não reintroduzir nem substituir os campos.

## 19. `asset_group_asset.performance_label`

Adjudicação literal final: `NOT_SUPPORTED_IN_V25`.

Provas:

- `GoogleAdsFieldService.SearchGoogleAdsFields`: `vazio_confirmado`, `row_count=0` para `asset_group_asset.performance_label`;
- GAQL mínima real: falhou com `UNRECOGNIZED_FIELD` para `asset_group_asset.performance_label`;
- nenhum valor real observado, porque o campo não é reconhecido na v25 desta conta/API.

## 20. Zero mutate final

Métodos chamados na certificação final, sanitizados:

- `CustomerService.ListAccessibleCustomers`;
- `GoogleAdsService.SearchStream`;
- `GoogleAdsFieldService.SearchGoogleAdsFields`.

Nenhum método chamado contém `mutate`, `create`, `update`, `remove`, `upload` ou `apply`. Nenhuma tentativa proibida ocorreu.

## 21. Estado da missão após a 3ª rodada

- `REAL_READ_PROVEN` para a observabilidade read-only PMax, com alvo real `PAUSED`;
- `performance_label` fechado como `NOT_SUPPORTED_IN_V25`;
- a evidência vermelha da 2ª rodada permanece preservada em `lineage.first_incompatible_read` dentro de `REAL-READ-SUMMARY.json` e em `LINHAGEM-CORRECAO-V25.md`;
- a lacuna v12_03 permanece: esta missão não criou migration nem escreveu no Supabase.
