# P04-T07 PMAX REAL READ V1 — certificação factual

**Data:** 2026-09-01
**Branch:** `sprint/hermes-p04-t07-pmax-real-read-v1`
**Base:** `7eaa93faef9d9546b09462ee8380496dc5e679e8`
**Veredito:** `NO_ELIGIBLE_PMAX`

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
