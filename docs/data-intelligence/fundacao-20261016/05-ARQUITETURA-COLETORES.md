# 05 — Arquitetura de coletores (frente B)

Estado (taxonomia do manifesto §7): o esqueleto de coletor seguro está **construído e testado
hermeticamente** (`volc_dil.fundacao.capacidade.coletor`, 26 testes; revisado após a R1 — F10, F11, F12,
ver `handoffs/HANDOFF-B.md` §8). O inventário abaixo é
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
| GTM VOLC Sensor v3 | container GTM do site (ID omitido, R1 F25), versão 35 | evento (push do navegador) | — | Edge Function `volc-ingest` → `raw_events` | upsert `onConflict sid,pid,event_name,ts_sec` | MS:docs/operations/VOLC-MEASUREMENT-V3-2026-10-15.md:16-19; MS:supabase/functions/volc-ingest/index.ts:6-7,161-163 |

Os três Google Ads usam API v25 e `googleAds:searchStream` (J:P/collector-inventory.json:8,118).
**Consultas por execução (R1 F7)**: D0 e D-1 fazem 1 `customer_client` (listagem do MCC, não escala
com contas) + **4 GAQL por conta** (`campaign`, `conversion_goal_campaign_config`, `campaign_budget`,
métricas da janela) — J:P/collector-inventory.json:111-117,136-142; termos/keywords fazem 1 GAQL por
recurso por conta (:161-163) mais a listagem de contas (inferida de `retry.account_query`, :168).
Na 1ª versão o modelo contava 1 consulta por conta e superestimava a capacidade em ~3×.
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
   impressões, cliques, conversões e custo idênticos — :54-59; valores omitidos), o que **autoriza planejar** a troca, não a faz sozinha.
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
                                      ├─ grava pelo Registro da frente A: versão se o estado muda, senão confirmação (D1/D2')
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
4. **Migração por vertical**: começar pelo coletor de termos (maior volume; 89,4% redundante medido com
   ~21 h de vida, 97,6% esperado em regime — `04-…` §3; já
   teve o defeito de RPC por linha) — não por campanha-dia, que é pequena e já reconcilia.

### 3.1 Contrato de execução `run_coleta`

```python
run_coleta(pedido: PedidoLeitura, *, adaptador: Adaptador, transporte: TransporteLeitura,
           sink: SinkMemoria | None = None, modo="dry_run", politica=PoliticaRetry(),
           relogio=None, dormir=None) -> ReciboRun
executar_lote(pedidos, *, paralelismo=1, ...)  # leitura serial ou paralela; gravação sempre serial, por slot
```

| Campo | Semântica |
|---|---|
| `PedidoLeitura(coletor, conta, janela_inicio, janela_fim, slot)` | `slot` = instante AGENDADO; `chave_execucao = sha256(coletor, conta, janela, slot)` |
| `Adaptador.ler(pedido, cliente)` | o adaptador **não guarda cliente**: recebe a cada leitura um `ClienteLeitura` cuja única operação é `consultar(ConsultaLeitura)` — GAQL `SELECT` único ou HTTP `GET` https |
| `TransporteLeitura.executar_leitura(consulta, timeout_s)` | injetado no **executor**, nunca no adaptador; recebe o prazo restante (timeout no cliente); não há transporte real neste módulo |
| `RespostaLeitura(linhas, contexto)` | linhas cruas + `ContextoFonte` (fonte, entidade, grão, janela, timezone, coletor, esquema, moeda só se provada) |
| `modo` | `dry_run` (padrão: lê e normaliza, **nada é gravado em lugar nenhum**, nem heartbeat) ou `gravar` (só em `SinkMemoria`, tipo exato) |
| `ReciboRun.status` | `concluido` · `dry_run` · `ja_concluido` (mesmo slot = no-op, nem lê) · `dead_letter` |
| contagens | `linhas_lidas`, `observacoes`, `inseridas`, `noop`, `rejeicoes`, `payloads_distintos`, `tentativas`, `erros[]` |
| observação | **`Observacao` canônica da frente A**, produzida por `volc_dil.fundacao.observacao.normalizar` (uma linha = um payload endereçado por conteúdo) e registrada pelo `Registro` da frente A: INSERIDO (versão) / CONFIRMADO / NOOP. Regras finais da frente A (HANDOFF-A §7.1–7.2): **D1** — vigente é a de maior `observed_at`; **D2'** — `observed_at` entra na chave da leitura; leitura com estado diferente do vigente vira versão, releitura com o mesmo estado vira **confirmação estreita** (`dil_obs.confirmacao`, 226 B medidos), retry = NOOP. `observed_at` = carimbo do transporte (`RespostaLeitura.observado_em`) ou fim da leitura — **nunca o slot** (uma execução atrasada ou de backfill lê o estado de quando roda); precisa ser ≤ `available_at`, senão dead letter `observado_em_invalido`. `available_at` = relógio monotônico do sink na gravação. Recibo: `inseridas`, `confirmadas`, `noop` |

### 3.2 Garantias do executor (todas testadas)

| Garantia | Como | Teste |
|---|---|---|
| Trava por capacidade | o adaptador só alcança `ClienteLeitura.consultar`; `ConsultaLeitura` recusa tudo que não seja `SELECT`/`GET` (inclusive `mutate`, `UPDATE`, `SELECT …; DELETE`, `http://`, `POST`); fachada imutável sem acesso ao transporte; consulta recusada vira dead letter sem tocar o transporte; destino de `gravar` só `SinkMemoria` exato (subclasse, `None` ou outro objeto recusados); o módulo não importa cliente HTTP, driver nem `subprocess`. Limite: Python não impede código hostil de abrir a própria conexão — a suíte bloqueia rede | `test_consulta_so_admite_leitura` (5), `test_adaptador_nao_alcanca_o_transporte…`, `test_trava_recusa_destino…` (4), `test_modulo_nao_tem_transporte_real_nem_driver` |
| dry_run nulo | sink recebido é ignorado: 0 heartbeats, 0 runs, 0 dead letters, 0 observações, inclusive em falha permanente | `test_dry_run_e_padrao_e_nao_toca_o_sink_nem_em_falha` |
| Timeout que não prende o processo | prazo propagado ao transporte + leitura em thread *daemon*; tentativa estourada é abandonada e seu resultado nunca é consumido | `test_timeout_retry_sucesso_sem_duplicar…`; `test_fonte_presa_nao_impede_o_processo_de_sair` (subprocesso com fonte presa 60 s e timeout 0,2 s: sai em < 10 s; a versão anterior levava 20 s, R1 `t_hang.py`) |
| Retry seguro | só `ErroTransitorio`; backoff exponencial com *full jitter* e teto, semente por chave | `test_backoff_exponencial_com_teto_e_deterministico` |
| Falha permanente / esgotamento | `ErroPermanente`, `TravaViolada` ou desconhecida → dead letter sem retry; transitório esgotado → dead letter; reprocesso não duplica | `test_falha_permanente…` (2), `test_transitorio_esgotado…` |
| Idempotência | slot repetido = `ja_concluido` sem leitura; retry/reentrega da mesma leitura (mesmo carimbo) = NOOP; releitura do mesmo valor em outra hora = 9 confirmações e 0 versões (D2'; o payload bruto continua deduplicado: 3 payloads) | `test_mesmo_slot_e_no_op_e_releitura_igual_em_outra_hora_e_confirmacao_d2_linha`, `test_retry_da_mesma_leitura_e_noop` |
| A→B→A | só o custo muda: 1 versão por leitura (10, 20, 10), impressões/conversões iguais viram confirmação ((3,0,0), (1,0,2), (1,0,2) em inseridas/noop/confirmadas); o `as_of` em cada corte mostra 10, 20, 10; gravar as mesmas leituras fora de ordem dá os mesmos estados registrados e o mesmo estado final | `test_a_b_a_e_preservado_como_leitura_nova`, `test_d1_gravacao_fora_de_ordem_nao_desfaz_a_leitura_mais_recente` |
| Ausência ≠ zero; dinheiro | `null` → `missing` (`valor_nulo_na_fonte`); `0` → `zero_confirmed`; decimal → micros; precisão acima de micros → `invalid` | `test_ausencia_vira_missing…`, `test_precisao_acima_de_micros…` |
| Serial × paralelo | semântica: **mesmas leituras ⇒ mesma história**. 18 pedidos embaralhados (6 contas × 3 slots, A→B→A, erros transitórios, latência aleatória), cada leitura com carimbo determinístico do transporte: conjunto de versões e de confirmações (chave, status, valor, `observed_at`), `as_of` nos 18 cortes de gravação e instantes de gravação idênticos ao serial em 8 rodadas. Sem o carimbo (observed = fim da leitura), o paralelo diverge — e é correto que divirja: leituras em instantes diferentes são leituras diferentes | `test_equivalencia_serial_paralelo_mesmas_leituras_mesma_historia` |

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
