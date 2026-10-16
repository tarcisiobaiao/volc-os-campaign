# 05 — Arquitetura de coletores (frente B)

Estado (taxonomia do manifesto §7): o esqueleto de coletor seguro está **construído e testado
hermeticamente** (`volc_dil.fundacao.capacidade.coletor`, 17 testes). O inventário abaixo é
**leitura de repositório**, não leitura de produção: "ativo" significa "o documento/recibo de
15/10 diz ativo", não que esta frente viu o n8n.

Abreviações de evidência (toda citação é `ref:caminho:linha`, lida com `git show`):

- **J** = `wip/historico-joinads-20261015` (`192bc065`) — o ref mais completo para coleta.
- **M** = `main` (`104bb0d0`). **MS** = `wip/historico-measurement-20261015`.
- **P** = `.claude-ads/runs/google-ads-recovery-20261015T125729-0300` (existe em `043c77f5` e em
  todos os `wip/historico-*`; **não** existe em `main`).
- **EA** = `.claude-ads/runs/economic-attribution-20261015T1310-0300`.

## 1. Inventário de coletores

### 1.1 Canônicos (shadow, append-only, Supabase oficial)

| Coletor | ID n8n | Agenda (America/Sao_Paulo) | Janela | Destino | Idempotência | Evidência |
|---|---|---|---|---|---|---|
| Google Ads campanha D0 | `Ps9yLfQkHeaAbyZZ` | `7 6-23 * * *` | D0 | `google_ads_raw_batch` / `google_ads_observation` via RPC `volc_ingest_google_ads_batch_auto` | **por execução** (`workflow_id:execution_id`) | J:P/collector-inventory.json:102,109,119-121; J:scripts/instalar_coleta_canonica_google_ads_n8n.py:262 |
| Google Ads campanha D-1 | `7yxs1aOlzWkkkSf9` | `17 6,14 * * *` | D-1 | idem | idem | J:P/collector-inventory.json:127,134 |
| Google Ads termos + keywords | `TFlmThr4930oPneE` | `23 */4 * * *` | `LAST_7_DAYS` (D-7..D-1) | idem | idem | J:P/collector-inventory.json:152,159; J:scripts/instalar_coleta_termos_keywords_n8n.py:166-167,193 |
| JoinAds intraday v2 | `cpb6tNxt211UkAn2` | `15 6-22/2 * * *` | D0 | `joinads_raw_batch` / `joinads_observation` | **determinística** (janela/hora) | J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:17,26-28; J:n8n/joinads_v2_intraday.json:10 |
| JoinAds D1 v2 | `jDX397ViVcRQft4A` | `20 6 * * *` | D-7..D-1 | idem | determinística (repetição 58101 manteve 64 lotes/209 obs) | J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:18,77-85; J:n8n/joinads_v2_d1.json:10 |
| GTM VOLC Sensor v3 | container `GTM-N4KS27ZV` v35 | evento (push do navegador) | — | Edge Function `volc-ingest` → `raw_events` | upsert `onConflict sid,pid,event_name,ts_sec` | MS:docs/operations/VOLC-MEASUREMENT-V3-2026-10-15.md:16-19; MS:supabase/functions/volc-ingest/index.ts:6-7,161-163 |

Os três Google Ads usam API v25 e `googleAds:searchStream` (J:P/collector-inventory.json:8,118);
**nenhum tem error workflow** (J:P/collector-inventory.json:122,147,169); retry só na chamada ao
Google (500 ms), não na RPC de ingestão, exceto termos (3×, 2 s) (J:P/collector-inventory.json:121,168).

### 1.2 Legados ainda ativos (co-autoridade ou escrita no Supabase hospedado)

| Coletor | ID | Agenda | Destino | Situação | Evidência |
|---|---|---|---|---|---|
| G ADS - REPORT (D0) | `hN15qFAVOqH0135q` | `0 6,12,18,23 * * *` | `daily_campaign_metrics` (latest-wins), `process_google_ads_campaign` | co-autoridade do D0 | J:P/collector-inventory.json:17-36; J:P/collector-overlap-map.json:7-16 |
| G ADS REPORT - DAY BEFORE OFICIAL | `tKUItcd0AoD9mozV` | diário 06h | `daily_campaign_metrics` | co-autoridade do D-1 | J:P/collector-inventory.json:41-60; overlap :19-28 |
| custo-gads-report D0 / D-1 | `33cQyqJLsL7LJzUI` / `fwMKXA2EFxQ3jQQo` | `0 6,12,18,23` / 06h | `daily_campaign_metrics` no Supabase **hospedado** | consumidor legado a aposentar (ADR de autoridade) | J:EA/writer-reader-map.json:97,101,514 |
| JOIN ADS - REPORT - INTRA DAY | `U0jEfGt30HqbUq1o` | `0 6,12,18,23 * * *` | `daily_project_metrics`, `joinads_metrics` | ativo ao lado do v2 | J:n8n/joinads_report_intraday.json:10; J:docs/audits/JOINADS-COLETA-CANONICA-2026-10-15.md:24 |
| JOIN ADS - REPORT - DAY BEFORE | `RpxB9ppefxZWujEV` | `0 6 * * *` | idem | ativo ao lado do v2 | J:n8n/joinads_report_day_before.json:10,90,108 |
| GAM/AdSense (projetos, campanha, placements) | `m4raVVEXGqRA956U`, `AJnsRGPFwMdc6Rho`, `Mklpt0em3vb7LHLB`, `azK8XrXY2noYtHP0`, `AeeKyqMYwgg0GM0a`, `BGsqwhbWCXQ6luGN` | `0 6,12,18,23` / 06h | `daily_project_metrics`, `gam_metrics`, `adsense_metrics` (hospedado) | legados sem versão canônica | J:docs/volc-os-graph/volc-os-graph.json:3355-3487; J:EA/writer-reader-map.json:173,216,240 |
| GAM ECPM HOURLY | `HeKrxGT6qQGJEVIk` | de hora em hora (`0 30 * * * *`) | `hourly_stats` (hospedado) | único coletor horário 24 h do inventário | J:docs/volc-os-graph/volc-os-graph.json:3399; J:EA/writer-reader-map.json:251-254 |

### 1.3 Preparados e não instalados / inativos

- Python `volc_ads.coleta` (timers systemd D0 `06,12,18,23:05`, D-1 `06:30`, recoleta `07:15`):
  "Nada aqui está instalado no Hetzner" — M:deploy/gads-coleta/README.md:1-24.
- Python `volc_ads/inteligencia_google` (`frequente` a cada 4 h, `completa` 06:15): "ainda não
  escolhida nem instalada" — J:deploy/google-intelligence/README.md:3-15.
- n8n v12 "VOLC · Google Ads campanha-dia D0/D-1" (inativos) — M:n8n/volc_gads_campanha_dia_d0.json:10.
- Meta insights D-1 `0 7 * * *` (inativo) — M:n8n/volc_meta_insights_dia_d1.json:10.
- Mutadores inativos: `svJWqv5r1NSxB8MO` (KW search terms), `Q6IunKtTI0gY0KgX` (ORAKUL auto adjust) —
  J:P/collector-inventory.json:65-96. **Fora de qualquer desenho de coleta.**
- GA4: nenhum coletor agendado encontrado em J nem M.

### 1.4 O que o inventário mostra

1. **Duas autoridades por verdade** hoje: campanha-dia D0 e D-1 têm um legado latest-wins e um
   canônico append-only escrevendo o mesmo fato em tabelas diferentes (J:P/collector-overlap-map.json:7-28,
   `coauthority: true`). JoinAds idem. A reconciliação D-1 de 14/10 bateu exatamente (5 campanhas,
   R$ 50,02 — :54-59), o que **autoriza planejar** a troca, não a faz sozinha.
2. **Idempotência desigual**: JoinAds v2 tem chave determinística por janela/hora; Google Ads v21
   usa `workflow_id:execution_id` como chave do run e `UNIQUE (run_id, observation_key)`
   (J:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:130). Re-executar o mesmo slot pelo
   n8n gera **outro run e outra cópia** de todas as observações. Não perde dado, mas infla volume e
   obriga o leitor a escolher entre cópias.
3. **Sem dedup entre leituras**: cada execução regrava tudo da janela. No modelo calibrado, 95,7% das
   linhas lidas pelo coletor de termos e 75,6% das do D0 são repetição (`04-…` §2).
4. **Sem error workflow nem dead letter**: falha antes do primeiro lote só aparece no histórico do
   n8n (J:docs/audits/GOOGLE-ADS-COLETA-CANONICA-2026-10-15.md, "Limites e próxima vertical").

## 2. Matriz de decisão n8n × Python

Notas 0–3 (3 = melhor). Critério de peso: o que dá prova e reversibilidade, não preferência.

| Critério | n8n | Python (worker/job) | Leitura |
|---|---|---|---|
| Agenda | **3** — cron nativo com timezone, já em produção | 2 — precisa de systemd/pg_cron/runner; timers prontos não instalados (M:deploy/gads-coleta) | n8n agenda bem |
| Orquestração (fan-out por conta, ordem, finalização) | 2 — loops funcionam, mas o fechamento explícito do run foi um defeito real (v21_03) | **3** — controle explícito, `finally`, transações | Python para lógica de run |
| Paginação/stream | 2 — searchStream achatado em Code node | **3** — `search_stream` do cliente oficial (J:volc_ads/gads/client.py:139) | empate prático em volume baixo |
| Backfill (janelas longas, 90 d) | 1 — `MAX_DIAS_POR_RUN`, timeouts de execução | **3** — iteração por janela com checkpoint | Python |
| Replay (reprocessar bruto → observação) | 0 — reprocessar exige re-chamar a API | **3** — normalizador puro sobre `raw_batch` | Python |
| Normalização / contrato (null≠0, micros, moeda) | 1 — JS em Code node, testes herméticos possíveis mas fora do pytest | **3** — contrato tipado do lab, mesmo código do replay | Python |
| Volume (×100/×1000) | 1 — memória/execução por workflow; termos já abortou com RPC por linha | **3** | Python |
| Testes | 1 — `n8n/testes_joinads_v2.py` testa o JSON gerado, não a execução | **3** — pytest, fakes, mutação | Python |
| Observabilidade | 2 — histórico de execução bom para humano, ruim para SQL | 2 — o que for construído (heartbeat/run no banco) | ambos precisam do ledger no banco |
| Credenciais | **3** — credencial dedicada no n8n, já higienizada | 1 — novo segredo no host (risco) | n8n |
| Custo de mudança hoje | **3** — já roda | 1 — instalar runner, deploy, rollback | n8n agora |

## 3. Arquitetura híbrida proposta (UM autor por verdade)

```text
 n8n (agenda + credencial)          Python (contrato + regra)                 Postgres (verdade)
 ─────────────────────────          ─────────────────────────                 ──────────────────
 cron ── dispara run_coleta(slot) ─▶ executor seguro ─ adaptador read-only ─▶ API (Ads/JoinAds)
        (webhook/HTTP interno)        │ timeout · retry backoff · dead letter
                                      ├─ grava lote bruto (hash por linha, linhas novas em lote)
                                      ├─ grava observações que MUDARAM (chave lógica + valor)
                                      ├─ heartbeat + recibo do run (status, contagens, erros)
                                      └─ dead letter (pedido + motivo) ──────────▶ reprocesso
 GTM (navegador) ── lote 10 s/20 ev ─▶ volc-ingest (Edge) ─▶ raw_events (append, upsert idempotente)
```

Regras:

1. **Um autor por verdade**: cada (fonte, granularidade, janela) tem exatamente um coletor dono.
   O legado vira leitor de compatibilidade (view sobre o canônico) com data de aposentadoria; não
   há dois escritores do mesmo fato. A troca exige o inventário de consumidores de
   `daily_campaign_metrics` (pendência J:P/collector-overlap-map.json:77-80).
2. **n8n fica com o que faz bem**: agenda, credencial, alerta humano. Ele chama `run_coleta` com o
   slot agendado (não o instante real) e não escreve fato de negócio.
3. **Python fica com o contrato**: leitura read-only, normalização, idempotência, gravação. O mesmo
   normalizador roda sobre o bruto guardado (replay) — sem re-chamar a API.
4. **Migração por vertical**: começar pelo coletor de termos (maior volume, 95,7% redundante, já
   teve o defeito de RPC por linha) — não por campanha-dia, que é pequena e já reconcilia.

### 3.1 Contrato de execução `run_coleta`

```python
run_coleta(pedido: PedidoLeitura, *, adaptador: AdaptadorFonte, sink: Sink,
           modo="dry_run", politica=PoliticaRetry(), relogio=..., dormir=...) -> ReciboRun
```

| Campo | Semântica |
|---|---|
| `PedidoLeitura(coletor, conta, janela_inicio, janela_fim, slot)` | `slot` = instante AGENDADO; `chave_execucao = sha256(coletor, conta, janela, slot)` |
| `modo` | `dry_run` (padrão: lê, normaliza, conta, não grava) ou `gravar` (só em sink com `externo=False`) |
| `ReciboRun.status` | `concluido` · `dry_run` · `ja_concluido` (mesmo slot repetido = no-op) · `dead_letter` |
| contagens | `linhas_lidas`, `observacoes`, `gravadas_novas`, `repetidas`, `payloads_distintos`, `tentativas`, `erros[]` |
| `ObservacaoColetada` | chave lógica estrita, métrica, valor inteiro (micros) ou `None` com estado `nao_informado` — nunca 0; `disponivel_em` = instante da coleta |

### 3.2 Garantias do executor (todas testadas)

| Garantia | Como | Teste |
|---|---|---|
| Trava de escrita externa | adaptador precisa declarar `somente_leitura=True` e não pode ter método `mutate/escrever/post/put/patch/delete/update/insert/upsert/publicar/ativar`; sink precisa declarar `externo=False`; modo fora de `{dry_run, gravar}` é recusado; o módulo não importa cliente HTTP nem driver de banco | `test_trava_recusa_escrita_externa` (5 casos), `test_modulo_nao_tem_cliente_de_rede_nem_banco` |
| Timeout | leitura numa thread com `result(timeout)`; resultado tardio é descartado, nunca consumido | `test_timeout_retry_sucesso_sem_duplicar` (espera a tentativa lenta terminar e confere 1 escrita) |
| Retry seguro | só `ErroTransitorio` (timeout, 429, 5xx); backoff exponencial com *full jitter* e teto, semente determinística por chave | `test_backoff_exponencial_com_teto_e_deterministico` |
| Falha permanente | `ErroPermanente` ou exceção desconhecida → dead letter na 1ª tentativa (não martela a API) | `test_falha_permanente_vai_para_dead_letter_sem_retry` |
| Esgotamento | transitório além de `max_tentativas` → dead letter `tentativas_esgotadas`; reprocessar depois dá sucesso sem duplicar | `test_transitorio_que_esgota_tentativas_vai_para_dead_letter` |
| Idempotência | slot repetido = `ja_concluido`; reler valor igual não cria linha; valor diferente cria versão nova (append-only) | `test_mesmo_slot_repetido_e_no_op…`, `test_valor_diferente_cria_nova_versao_append_only` |
| Ausência ≠ zero | `None` vira `nao_informado`; float é contrato inválido (dinheiro em micros) | `test_ausencia_vira_nao_informado_nunca_zero`, `test_valor_nao_inteiro_e_contrato_invalido` |
| Heartbeat/recibo | heartbeat em início, cada retry e fim; recibo do run gravado em `gravar` e em dead letter | asserts nos testes acima |
| Serial × paralelo | 18 pedidos (6 contas × 3 slots) com erros transitórios intercalados: conjunto final idêntico, 54 observações, 18 runs; repetir o lote em paralelo não muda nada | `test_equivalencia_serial_paralelo` |

### 3.3 Heartbeat, dead letter e backfill no banco (proposta, não aplicada)

- **Heartbeat**: a view `google_ads_collection_health` já existe (J:supabase/migrations/v21_01_google_ads_coleta_canonica.sql:295-302).
  Falta o alarme: "run `running` > 30 min é suspeito" está só em texto (J:docs/operations/google-ads-coleta-canonica.md:57-60).
  Proposta: o recibo do run grava `iniciado/retry_n/terminal`; um watchdog (pg_cron 15 min, desenho já em
  J:docs/PRD-ARBITRAGEM.md:108-116) alerta quando o último heartbeat de um coletor ativo passa de
  2× o intervalo da agenda.
- **Dead letter**: tabela `coleta_dead_letter(chave_execucao, pedido jsonb, motivo, erro, tentativas, instante, reprocessado_em)`;
  reprocessar = chamar `run_coleta` com o mesmo pedido (idempotente).
- **Backfill**: `run_coleta` com `slot` sintético `backfill:<janela>` e janela de 1 dia por pedido; o
  executor em paralelo é seguro (provado). Limite real é quota (§4 do `04-`), não o banco.
- **Idempotência do v21**: trocar a chave do run de `workflow_id:execution_id` para
  `coletor:conta:janela:slot` (como o JoinAds v2) é a mudança de menor risco e maior efeito. É
  mudança de migration/workflow operacional — decisão do integrador, não aplicada aqui.

## 4. O que não foi feito

Nenhum adaptador real (Google Ads, JoinAds) foi escrito: o executor só conhece fakes. Nenhum sink
Postgres foi escrito. Ligar o executor a produção exige: adaptador read-only revisado, sink do lab
revisado, e decisão do integrador sobre a fonte append-only (FINAL-REPORT da 1ª execução, "menor
próximo passo").
