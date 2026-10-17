# Item 5 — coletores legados paralelos: inventário e plano (NADA desativado)

Leitura: `GET /workflows?active=true` em 2026-10-17 ~22:00 UTC (74 workflows ativos; só metadados, credenciais e
parâmetros descartados em memória). Escritores e consumidores: `05-ARQUITETURA-COLETORES.md:43-47` e
`01-INVENTARIO-ATUAL.md:120,126,153,163,169` (evidência de repositório; o DDL das tabelas legadas não é versionado).
A desativação de qualquer item abaixo exige autorização posterior do dono.

## Inventário e sobreposição

| Legado (id) | Agenda (BRT) | Escreve | Sobrepõe o canônico | Fato / grão | Consumidores conhecidos | Error workflow |
|---|---|---|---|---|---|---|
| G ADS - REPORT (`hN15…`) | `0 6,12,18,23` | `daily_campaign_metrics` (latest-wins) via `process_google_ads_campaign` | Google D0 (`7 6-23`) | custo/cliques/impressões campanha-dia, dia corrente | front legado, gatilho JoinAds → `daily_campaign_metrics` | não |
| G ADS REPORT - DAY BEFORE OFICIAL (`tKUI…`) | diário 06h | `daily_campaign_metrics` | Google D-1 (`17 6,14`) | campanha-dia, D-1 | idem | não |
| GADS REPORT (`33cQ…`) | `0 6,12,18,23` | `daily_campaign_metrics` no Supabase **hospedado** (consumidor legado a aposentar pelo ADR de autoridade) | Google D0 | campanha-dia | desconhecido fora do hospedado | não |
| GADS REPORT - DAY BEFORE OFICIAL (`fwMK…`) | diário 06h | idem (hospedado) | Google D-1 | campanha-dia, D-1 | idem | não |
| JOIN ADS - REPORT - INTRA DAY (`U0jE…`) | `0 6,12,18,23` | `joinads_metrics` + `daily_project_metrics` (upsert, latest-wins) → gatilho `sync_joinads_revenue_to_daily_metrics` → `daily_campaign_metrics` | JoinAds intradiário (`15 6-22/2`) | receita campanha-dia e domínio-dia | `volc_ads/economia/job.py` (wip), front, `v17_04` | não |
| JOIN ADS - REPORT - DAY BEFORE (`RpxB…`) | `0 6` (D-3..D-1) | idem | JoinAds D-1 (`20 6`, D-7..D-1) | idem | idem | não |
| FORCE UPDATE GADS (`rb3I…`) | sem agenda (webhook) | dispara relatório Google sob demanda | D0/D-1 sob demanda | campanha-dia | botão/rotina do front | não |

Não há colisão de escrita: canônicos gravam só no ledger append-only v21/JoinAds v2; legados gravam nas tabelas
latest-wins. A sobreposição é de **autoridade** (dois números para o mesmo fato), não de linha.

## Plano futuro de cutover (proposta; depende de P06-T11 e de autorização)

1. **Paridade (≥ 7 dias):** comparar por dia e campanha o custo canônico (`google_ads_observation`, última observação
   de run `completed`, `metric_row_status='present'`) com `daily_campaign_metrics`, e a receita JoinAds v2 com
   `joinads_metrics` (USD × taxa do dia), com a mesma consulta read-only do item 5. Critério: diferença ≤ 1% em
   dias maduros e nenhuma campanha só de um lado.
2. **Consumidores primeiro:** inventariar e apontar `economia/job.py`, front e `v17_04` para o ledger canônico
   (ou uma view de compatibilidade) antes de pausar qualquer legado.
3. **Ordem de pausa reversível (uma por vez, com 48 h de observação):** `33cQ…` e `fwMK…` (hospedado, fora da
   autoridade) → `hN15…` → `tKUI…` → `U0jE…` → `RpxB…` → `FORCE UPDATE GADS`. Pausar = `POST /workflows/<id>/deactivate`.
4. **Rollback:** `POST /workflows/<id>/activate` do mesmo id (definição intacta); as tabelas legadas não são apagadas.
5. **Dono de cada legado:** operação VOLC (Tarcisio); nenhum outro dono registrado no Mapa Vivo.
