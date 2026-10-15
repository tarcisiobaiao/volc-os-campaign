# Experimentos do pesquisador A (14/10/2026)

Nenhum experimento usa credencial, cliente autenticado ou rede autenticada.
Rode da raiz do checkout `volc-os-campaign-qg-real-20261007`.

| Script | O que prova | Reprodução | Saída |
|---|---|---|---|
| `introspeccao_sdk_v25.py` | Campos, métodos e enums reais do SDK `google-ads` 33.0.0 (v25): Mutate, BatchJob, erros, ajustes de conversão, sazonalidade, experimentos, QS, ativos, placements, IP, value rules | `backend/.venv/bin/python -I <este dir>/introspeccao_sdk_v25.py > <este dir>/introspeccao_sdk_v25.out.txt` | `introspeccao_sdk_v25.out.txt` |
| `campos_compativeis_v25.py` | Segmentos e métricas permitidos com cada view no FROM, lidos das páginas públicas `/google-ads/api/fields/v25/<recurso>` | baixe as páginas com o `curl` do docstring do script para uma pasta de scratch e rode `python3 -I campos_compativeis_v25.py <pasta>` | `campos_compativeis_v25.out.json` |
| `validar_gaql_propostas.py` | As GAQLs propostas no relatório só usam campos existentes e selecionáveis no catálogo do repo (`volc_ads/google_ads_api/catalogo_gaql_v25.json`) | `python3 -I <este dir>/validar_gaql_propostas.py volc_ads/google_ads_api/catalogo_gaql_v25.json` | `validar_gaql_propostas.out.txt` (15 OK + 1 negativo esperado) |

Limite do terceiro script: o catálogo do repo não traz `selectable_with`. A
compatibilidade recurso × métrica foi conferida nas páginas públicas (segundo
script). Uma consulta pode passar aqui e ainda ser recusada pelo servidor
(por exemplo, `asset_group_top_combination_view` pode exigir filtro por grupo de
recursos). Prova final = `search` real somente leitura no canário do integrador.

Leituras de terceiros (clones `--depth 1` e wheel `google-ads-datamanager` 0.9.4,
sha256 `fff992827183e73ec7a9ab259c55a3a641b305febd08a52ac6a1c1b9bb4ec6f2`) ficaram no
scratch `.../scratchpad/A/clones` e `.../scratchpad/A/dl-datamanager`. Nada delas foi
executado. O `resultados.json` foi gerado por `scratchpad/A/gen/gerar_resultados.py`.
