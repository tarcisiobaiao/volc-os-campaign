# 12 — Plano de promoção para produção

Princípio: cada degrau tem um critério de entrada provado, um responsável pela autorização, um rollback e uma
prova de saída. Nenhum degrau dá autonomia financeira. Estados conforme `00` §7.

## Degrau 0 — integrar o código (local → `main`)

| | |
|---|---|
| Entra | esta branch `lab/data-foundation-20261016` com suíte verde e revisão R2 respondida |
| Ação | merge revisado em `main` (só pelo dono; nesta missão é proibido), com squash se o histórico com ids reais não puder subir |
| Rollback | revert do merge |
| Sai | código e documentos em `main`; roadmap/curadoria atualizados pelo delta `handoffs/CURADORIA-DELTA-20261016.json`; grafo reconstruído e `--check` `current: true` |
| Autoriza | Tarcisio |

## Degrau 1 — replay com dado real (read-only)

| | |
|---|---|
| Entra | Degrau 0 ou autorização avulsa para exportar |
| Ação | exportar snapshot read-only sanitizado de `google_ads_observation` (campaign_day), `google_ads_collection_run` e o subconjunto JoinAds v2 (earnings, kv por campanha, pageviews) para `experiments/data-intelligence-lab/artifacts/` (fora do Git); rodar `scripts/fundacao_shadow.py --linhas-v21 … --linhas-joinads …` (comando em `06` §9) e o recibo de qualidade (`09`) |
| Rollback | apagar `artifacts/` |
| Sai | "testado em replay" para replay `as_of`, adaptadores v21/JoinAds v2, nowcast de custo D0 e health contracts |
| Autoriza | Tarcisio (a exportação foi bloqueada pelo classificador nesta sessão) |

## Degrau 2 — health contracts agendados (read-only)

| | |
|---|---|
| Entra | Degrau 1 sem achado bloqueante |
| Ação | agendar os SELECTs de `migrations_candidatas/views_qualidade/selects_somente_leitura.sql` (ou criar as views com `security_invoker` e grant só leitura) com um papel read-only; recibo diário; alerta só depois de 2 semanas de falso alarme medido |
| Rollback | `dq_01_views_qualidade.down.sql`; desligar a agenda |
| Sai | "rodando em shadow" para observabilidade |
| Autoriza | Tarcisio (cria objeto em produção) |

## Degrau 3 — corrigir as fontes (escrita externa autorizada, uma por vez)

Ordem por valor/risco, cada uma com teste de aceite já escrito no laboratório:

1. **Coletor Google**: `null` em vez de zero sintetizado; `customer.currency_code` na GAQL; reaper de runs
   presos; error workflow (n8n). Aceite: `dq_zero_sintetizado` cai para 0 sintetizado sem linha; moeda provada;
   `dq_runs_orfaos` vazio.
2. **Sensor/wrapper (GTM)**: isentar ids numéricos só em `utm_campaign`/`utm_content`. Aceite: vetor-ouro novo e
   `dq_cobertura_atribuicao_sensor` > 0,9 em sessões pagas depois da publicação.
3. **`raw_events`**: chave de dedup que não colapse eventos do mesmo segundo (migration com rollback).
4. **Autoridade única do ledger Google** (v12/v17 × v21) e aposentadoria dos gatilhos legados latest-wins.

Rollback: versão anterior do workflow/tag/migration. Autoriza: Tarcisio, item a item.

## Degrau 4 — ledger de observação e shadow diário

| | |
|---|---|
| Entra | Degraus 1–3 |
| Ação | aplicar `dil_obs_0001` (só para fontes sem tabela append-only: GTM/Sensor, GAM, AdSense) e rodar o shadow diário read-only (políticas `manter`, `regra_margem`, `guardiao_72h`) gravando só o ledger de decisões e o resultado maduro D+k |
| Rollback | `dil_obs_0001.down.sql` (recusa se houver dependentes) |
| Sai | "rodando em shadow" para decisões; nenhuma proposta executável |
| Autoriza | Tarcisio (migration em produção) |

## Degrau 5 — calibração

Depois de ≥ 8 semanas de shadow com ≥ 1 campanha ativa: recalibrar maturação, limiares de qualidade e
nowcast; reabrir os portões do surrogate e de alocação (gatilhos em `10-BACKLOG-OUROS.md`). Só então avaliar
qualquer proposta T1 com aprovação humana. Bandits e OPE exigem propensão logada antes de qualquer teste.

## O que precisa de autorização (lista objetiva)

1. Exportar o snapshot read-only sanitizado para `artifacts/` (Degrau 1).
2. Aplicar o delta de roadmap/curadoria e reconstruir o grafo (Degrau 0, parte local) — bloqueado pelo
   classificador nesta sessão.
3. Merge em `main` (Degrau 0).
4. Criar views/agenda read-only em produção (Degrau 2).
5. Alterar workflow n8n do coletor Google (Degrau 3.1).
6. Publicar GTM com a correção do filtro (Degrau 3.2).
7. Migration em `raw_events` (Degrau 3.3) e decisão de autoridade do ledger (Degrau 3.4).
8. Aplicar `dil_obs_0001` em produção (Degrau 4).
9. Leituras L6 (GTM API), L7/L8 (n8n API) e L13 (hash da Edge Function), que exigem credenciais de API.
