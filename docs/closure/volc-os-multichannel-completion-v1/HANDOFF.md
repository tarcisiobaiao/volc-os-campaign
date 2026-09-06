# Handoff — VOLC OS Multichannel Completion

**Veredito geral:** `MULTICHANNEL_COMPLETION_PARTIAL`

Vereditos por faixa, cada um com a evidência que o sustenta:

| Veredito | Sustentado? | Por quê |
|---|---|---|
| `META_P0_LOCAL_CONTRACT_ACCEPTED` | **não** | C01 continua aberto. O canário Meta está bloqueado por `shop_redirect_proof`, e o bloqueio é a decisão certa — não a conclusão da tarefa. |
| `CREATIVE_SUPPLY_CHAIN_P0_LOCAL_ACCEPTED` | **parcial** | O núcleo existe e está ligado em Display. Demand Gen e PMax usam o mesmo seam e não foram ligados; falta o detector de pixel. |
| `GOOGLE_DISPLAY_LOCAL_READY_FOR_REMOTE_VALIDATION` | **sim, com ressalva** | Payload pronto e provado localmente. A ressalva: sem detector de pixel registrado, toda peça é bloqueada com `GATE_UNAVAILABLE`. |
| `GOOGLE_DEMAND_GEN_LOCAL_READY_FOR_REMOTE_VALIDATION` | **não** | T06 não implementado. Só as automações foram fechadas. |
| `GOOGLE_PMAX_LOCAL_READY_FOR_REMOTE_VALIDATION` | **não** | T08 não implementado; PMax segue fora da rota tipada. T09 está inteiro. |
| `MULTICHANNEL_OPERATOR_UI_LOCAL_ACCEPTED` | **não** | A UI não foi tocada. T13 permanece aberto. |

## Base e HEAD

- Base: `5cb654fbf1dbc226a995b0c60a37310c2aa4eb4c`
- HEAD: `316d2116f0eafe8ec7e0b9a6a115775b242187af`
- Branch: `execution/volc-os-operacao-80-20` · árvore limpa · **zero push**
- `origin` permanece em `5cb654f`

## O que foi feito, por tarefa

| Tarefa | Estado | Evidência |
|---|---|---|
| P0-RT-01 (C01 website-only/Shop) | **CONTRADITED → corrigido** | `5cb654f` emitia `destination_spec` não provado; removido do payload e da máscara, substituído por `shop_redirect_proof` por conta |
| P0-RT-02 (AssetSupplyManifest) | IMPLEMENTED | já em `5cb654f`; validado |
| P0-RT-03 (ambiguidade sem retry) | IMPLEMENTED | `resolver_ausente` levanta por construção |
| P0-RT-04 (separação de flags) | IMPLEMENTED + estendido | terceira autorização, por conta |
| P0-RT-05 (Page/Instagram/placements) | IMPLEMENTED | já em `5cb654f`; validado |
| T01 política por canal | **feito** | teto por canal; CPC/rede só Search; janela ≠ autorização |
| T02 paridade /provar × /subir | **feito** | mesmos montadores; portão pago só Search; `tcpa` em micros; teto/moeda no ledger |
| T03 Display PAUSED + control_spec | **feito** | 3 objetos PAUSED; dois booleanos `false` |
| T09 trava de URL PMax | **feito** | 5 automações OPTED_OUT; PAGE_FEED excluído |
| T12 gate de política | **feito para Display** | léxico, recibo HMAC, `supply_sha256` na chave |
| T06 Demand Gen | **parcial** | 3 automações OPTED_OUT; mutação não aberta |
| T04, T08, T13, T14 | **não feitos** | ver runbooks |
| T05, T07, T10, T11 | **externos** | RB-04 a RB-07 |

## Gates

| Gate | Resultado |
|---|---|
| pytest `backend/tests` + `volc_ads` | **4701 passam, 3 falham** — as 3 herdadas da base (baseline: 3893 passam, 3 falham) |
| TypeScript (`-p tsconfig.app.json`) | **77 erros = baseline**, ratchet mantido |
| Vitest | 16 falham / 1661 passam — **todas herdadas** (`src/` não foi tocado) |
| `npm run build` | ✅ |
| `git diff --check` | ✅ |
| `scripts/verificar_segredos.py` | ✅ nenhum padrão forte |
| `scripts/verificar_autoridade_supabase.py` | ✅ `https://database.agenciavolc.com.br` |
| Migration em PostgreSQL descartável | ✅ apply → uso → RLS/grants → rollback → reapply |
| Grafo `--check` | ✅ `current: true` em `dbedab2` |

**Falhas herdadas (idênticas antes e depois):** duas por dossiê congelado do
canário defasado, uma dependente de dados em `test_trafego.py`.

## Revisores

- **Codex `gpt-5.6-sol`** (read-only): 12 achados. 7 corrigidos, 3 refutados, 2
  registrados. Achado blocker real: a copy é lista e as listas sumiam do portão.
- **Gemini**: ⚠️ `gemini-3.1-pro` **não existe** neste endpoint (404). Usado
  `gemini-3-pro-preview`. A busca web devolveu HTTP 500 em todas as tentativas,
  então nenhuma citação foi aberta — as marcadas `COMPROVADA` foram lembradas,
  não verificadas. Achado útil aproveitado: `GENERATE_IMAGE_EXTRACTION`.

## Atos externos ainda necessários

Ver `RUNBOOKS-ATOS-EXTERNOS.md`. Em resumo: migration Meta, `validate_only`
real (⚠️ com plano novo — o recibo antigo ficou obsoleto), `create_paused`,
canários Display/Demand Gen/PMax, migration v12_03, e o detector de pixel.

## Confirmação literal

zero push · zero deploy · zero Meta/Google real · zero Supabase oficial ·
zero migration oficial · zero n8n · zero WordPress · zero ativação.
