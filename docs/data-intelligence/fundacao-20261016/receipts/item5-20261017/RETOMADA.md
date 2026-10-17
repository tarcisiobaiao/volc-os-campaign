# Retomada do item 5 — ponto seguro de parada (2026-10-17 ~12:40 UTC)

Parada pedida pelo dono (desligar o Mac para viajar). Nenhum cutover ficou pela metade.

## Estado em produção (n8n)

| Workflow | Estado | Versão | Error workflow |
|---|---|---|---|
| Google D0 (`Ps9yLfQkHeaAbyZZ`) | **implantado e validado** (canário 09:07 BRT ok) | `54242243…` (antes `cf965a87…`) | ligado |
| JoinAds intradiário (`cpb6tNxt211UkAn2`) | **implantado, canário ainda não conferido** | `7b93d17b…` (antes `904cfcb3…`) | ligado |
| Google D-1 (`7yxs1aOlzWkkkSf9`) | intocado | `23735272…` | não |
| Google termos (`TFlmThr4930oPneE`) | intocado | `609ef5b9…` | não |
| JoinAds D-1 (`jDX397ViVcRQft4A`) | intocado | `47c58073…` | não |
| Error workflow comum (`fvqy0sZXFoAV2U0Y`) | novo, ativo, sem webhook de teste | `f7cd937f…` | — |
| Reaper shadow (`4V7w8vmCYH8QPq2T`) | novo, ativo, só lê (cron `41 * * * *`) | `1d8798fb…` | ligado ao comum |

Cron, timezone e cadência de todos os coletores: inalterados. Legados: intocados. Runs órfãos: intactos
(o schema não aceita `abandoned`; reaper só aponta). Nenhuma migration, nenhum push/merge.

Por que é seguro deixar assim: os dois coletores implantados têm error workflow que só finaliza run ainda
`running` (idempotente, sem repetir escrita); a JoinAds D-1 continua na versão antiga e relê D-7..D-1, então
mesmo uma falha do intradiário não perde receita do dia anterior.

## Pendente na volta

1. Conferir o canário do JoinAds intradiário de 10:15 BRT (e os seguintes, 12:15, 14:15…):
   `docs/.../item5-20261017/verificar.sh 2026-10-17T13:00:00Z` → `j_run` com `collector_version 5`, status
   `completed`, `j_obs` com `escala_max_* <= 6`, `quantizadas = com_receita`, `st_moeda = attested`, sem `j_dup`.
   Se falhar: rollback imediato (abaixo).
2. Cutover, um por vez, nesta ordem: JoinAds D-1 (canário pelo webhook do próprio workflow), termos (roda
   `23 */4` BRT), Google D-1 (06:17 e 14:17 BRT). Antes de cada um: `construir_item5.py` + `validar_item5.py`
   com o id do error workflow; depois `cutover.py <chave>` e `esperar_execucao.py` + `verificar.sh`.
3. Segunda execução do reaper idêntica à primeira (prova de idempotência); três órfãos seguem `running`.
4. Replay estrito com as observações novas; roadmap/curadoria só na branch; rebuild do grafo e `--check`;
   veredito único com os 12 pontos.

## Rollback exato

```
python3 docs/data-intelligence/fundacao-20261016/receipts/item5-20261017/cutover.py --rollback <chave> \
  experiments/data-intelligence-lab/artifacts/item5-20261017/rollback \
  experiments/data-intelligence-lab/artifacts/item5-20261017/implantado
```

Chaves: `google_d0`, `joinads_intraday` (as únicas alteradas). Exports de rollback (0600, fora do Git, contêm
configuração sensível do workflow; não versionar) com sha256: google_d0 `13f6bd0def50a1ca…`, google_d1
`1d2409a0804841fb…`, google_termos `d2282714b894b532…`, joinads_d1 `186f61262d2c2f4b…`, joinads_intraday
`40567044237745cb…`. Error workflow e reaper: desativar pela API (`POST /workflows/<id>/deactivate`) se preciso.

## Achados já registrados (entram no veredito)

- Cotação USD/BRL do VOLC = 5,25, parada desde 18/02/2026; funções caem em 5,2/5,5 em silêncio; o legado
  recalcula todo o histórico quando a taxa muda. Três linhas reais reconciliadas: USD × 5,25 = BRL persistido.
- Os três runs órfãos têm execução n8n `success` terminada em 15/10 (versão anterior do workflow).
- O workflow Google guarda developer token em nó Set em texto puro (não alterado; recomendação: credencial).
