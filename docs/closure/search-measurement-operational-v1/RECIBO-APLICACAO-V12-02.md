# RECIBO FACTUAL — aplicação da v12_02 no Supabase oficial

Este arquivo registra o que **de fato aconteceu**. Nada aqui é plano ou intenção.

---

## 1. Quando e onde

| campo | valor |
|---|---|
| início da aplicação | `2026-09-01T18:32:16Z` |
| fim da aplicação | `2026-09-01T18:32:18Z` |
| autoridade | `https://database.agenciavolc.com.br` (confirmada por `scripts/verificar_autoridade_supabase.py`) |
| host | `178.156.196.149` · container `supabase-db` · banco `postgres` |
| executor | `postgres` (via `docker exec`, nunca por PostgREST) |
| worktree | `/private/tmp/volc-global-closure-20260829` |
| branch | `volc-os-v2` |

## 2. SHA do código integrado

| momento | SHA |
|---|---|
| base antes da integração | `812ab0d4ab3091072e695f52db6e117f04aa2ce7` |
| HEAD da feature integrada | `99c6fae70c6a42fd67a9cc87d3fbd358013a8976` |
| integração | `git merge --ff-only` — **fast-forward**, sem merge commit |
| HEAD após o conserto pós-prova | `48fd4d1c855dfd6c86cf80a3438e9a966251e22e` |

## 3. Migration aplicada

| campo | valor |
|---|---|
| arquivo | `supabase/migrations/v12_02_plano_de_mensuracao.sql` (581 linhas) |
| sha256 | `6ea4da6283bb74529ebbb9e8b2ce540f89813c47160a8620daa9440a75715276` |
| comando | `psql -U postgres -v ON_ERROR_STOP=1`, por pipe do arquivo |
| **exit code** | **0** |
| último NOTICE | `v12_02 OK: 1 tabela, RLS forcada, 0 policies, 1 gatilho, 28 CHECKs, escrita so por funcao.` |
| rollback disponível | `v12_02_rollback.sql`, sha256 `f95da19eef129570432d5b226707893a5ecaa319b4cccc37f492e7cb94b5b79d` |

**Nenhuma outra migration foi aplicada.**

### Estado anterior (medido antes)
- `to_regclass('public.trafego_campanha')` → **not null** (v9_01 presente)
- `to_regclass('public.trafego_campanha_plano_de_mensuracao')` → **null**
- funções `trafego_plano_append_only` / `volc_registrar_plano_de_mensuracao` → **0**

### Estado posterior
- tabela criada, 1 gatilho, 28 CHECKs, RLS forçada, 0 policies
- **0 linhas** na tabela

## 4. Recibo do backup

| campo | valor |
|---|---|
| caminho absoluto | `/root/backups/pre-v12_02-20260901-183146Z.dump` |
| formato | `pg_dump -Fc` (custom, restaurável) |
| exit code | **0** |
| tamanho | **2.365.948 bytes** |
| sha256 | `a79aa22eee9e831aeb48855dff61a423fa149eca033c04db846ebff086a61c0f` |
| `pg_restore -l` exit | **0** |
| itens listados | **2234** |
| criado em | `2026-09-01T18:31:46Z` (antes da migration) |

## 5. Contraprovas pós-aplicação — 11 asserções, todas verdes

| # (nomenclatura do pacote) | prova | esperado | obtido |
|---|---|---|---|
| 4.1 | tabela criada | `1` | `1` ✅ |
| 4.2 | RLS ligada **e** forçada | `t` | `t` ✅ |
| 4.2 | zero policies | `0` | `0` ✅ |
| 4.3 | `anon`/`authenticated`/`PUBLIC` sem privilégio | `0` | `0` ✅ |
| 4.4 | `service_role` **lê** | `t` | `t` ✅ |
| 4.4 | `service_role` **sem** escrita direta | `0` | `0` ✅ |
| 4.5 | `anon` **não** executa a função | `f` | `f` ✅ |
| 4.5 | `service_role` executa a função | `t` | `t` ✅ |
| 4.6 | gatilho `trafego_plano_append_only_tg` presente | `1` | `1` ✅ |
| 4.7 | os 28 CHECKs | `28` | `28` ✅ |
| 4.8 | tabela nasce vazia | `0` | `0` ✅ |

**4.9 — `/provar` continua read-only e declara `plano_persistido.persistido == false`:**
provado hermeticamente por `test_provar_nao_grava_plano_nenhum` e
`test_provar_diz_que_o_plano_nao_esta_persistido` (2 passed), com socket
bloqueado por fixture. Escolha deliberada: a prova hermética é **mais forte**
que uma chamada ao vivo (ela falha se qualquer socket abrir) e não consome cota
da conta do cliente.

## 6. Prova transacional da RPC oficial

Transação explícita no banco oficial, `set local role service_role`, fixture
sintética marcada `verification_only`, conta `000000000000` (não existe no
Google Ads), documento produzido pelo **tradutor real**
(`documento_de_plano_de_mensuracao` sobre `_plano_de_ignorancia`) — a mesma
costura que `RepositorioDePlanoDeMensuracao.registrar` usa.

| prova | esperado | obtido |
|---|---|---|
| contagem antes | `0` | `0` ✅ |
| INSERT aceito pela RPC governada | uuid | uuid ✅ |
| `plano_id` material e não nulo | `t` | `t` ✅ |
| releitura pelo mesmo `plano_id` | `t` | `t` ✅ |
| `impressao` coerente | `t` | `t` ✅ |
| `chave_intencao` coerente | `t` | `t` ✅ |
| idempotência pela impressão (2ª chamada = mesma linha) | `t` | `t` ✅ |
| escrita **direta** por `service_role` | recusada | `ERROR: permission denied for table` ✅ |
| `UPDATE`/`DELETE` por `service_role` | recusados | `permission denied` ✅ |
| `UPDATE`/`DELETE` por `postgres` (chega ao gatilho) | recusados | `ERROR: trafego_campanha_plano_de_mensuracao e append-only: UPDATE e DELETE recusados` ✅ |
| **`ROLLBACK` executado** | — | ✅ |
| contagem depois | `0` | `0` ✅ |

⚠️ **Nenhuma fixture sintética ficou na tabela.** Contagem final medida: **0**.

⚠️ Nota honesta: como `service_role` não tem grant de `UPDATE`/`DELETE`, essas
duas paravam em `permission denied` **antes** do gatilho. O gatilho append-only
foi exercitado à parte, como `postgres`, e recusou os dois com a mensagem dele.

### Veredito

```
SCHEMA_APPLIED_AND_RPC_PROVEN = true
REAL_CAMPAIGN_PLAN_PERSISTED  = false
```

O segundo é **falso** e continua falso: nenhuma campanha real recebeu plano nesta
etapa. O que foi provado é que o schema e a RPC funcionam no banco oficial.

## 7. Um defeito real encontrado por esta prova

A primeira execução da prova transacional **falhou** — e o defeito era do código,
não do schema.

`_plano_de_ignorancia` (o plano que `/subir` grava quando a leitura no Google não
completa) nascia com `metas_da_campanha_estado='nao_coletado'` e `campaign_id`
nulo. A **invariante 6** exige `inelegivel` nesse caso, e a RPC recusou com
`23514`.

O efeito em produção seria o oposto do desenho: uma leitura do Google que
falhasse impediria a criação da campanha, trocando uma indisponibilidade do
Google por uma indisponibilidade do VOLC.

Corrigido em `48fd4d1`, com duas contraprovas novas — uma sobre o documento e
outra sobre a rota inteira com a leitura falhando. A prova transacional foi
**refeita do zero** com a fixture corrigida, e é a que está registrada acima.

Nenhuma prova anterior pegava isso: as 52 contraprovas exercitavam a persistência
com um plano LIDO, e o dublê do repositório não tem os 28 CHECKs do schema.

## 8. Zero mutação externa

| superfície | estado |
|---|---|
| Google Ads mutate | **nenhum** — `FORGE_PERMITIR_ESCRITA` não definida; `gate_sem_mutacao_google.py` 3/3 |
| criação/ativação/pausa/alteração de campanha | **nenhuma** |
| meta ou ConversionAction | **nenhuma alteração** |
| Data Manager upload | **nenhum**, nem `validateOnly` |
| GTM / GA4 | **nenhuma mutação** |
| n8n | **nenhuma mutação** |
| deploy | **nenhum** |
| outras migrations | **nenhuma** |
| dados existentes apagados | **nenhum** |

## 9. Rollback

**NÃO executado.** As condições que o autorizariam não ocorreram: nenhuma
contraprova pós-aplicação falhou, e a tabela está no estado esperado (vazia).
O backup do §4 continua disponível e validado.

## 10. Gates depois de tudo

| gate | resultado |
|---|---|
| `pytest backend/tests volc_ads -q` | **2736 passed · 30 skipped · 0 failed** |
| `npx vitest run` | **1173 passed · 3 skipped · 0 failed** |
| focais (plano persistido, ledger, persistência, domínio) | 233 passed · 1 skipped |
| focais de front (canais, lançamento, lib) | 105 passed |
| `npx tsc --noEmit -p tsconfig.app.json` | **76** (baseline; zero no ownership) |
| `bash scripts/provar-ciclo-v12_02.sh` | **55 · 0** |
| `npm run build` | verde |
| `git diff --check` | limpo |
| `scripts/verificar_segredos.py` | nenhum padrão forte |
| `scripts/gate_sem_mutacao_google.py` | **3/3** |

## 11. Mapa Vivo

Reconstruído **pelo pipeline oficial** (`scripts/atualizar_grafo_volc_os.py`),
nunca por `graphify update .`.

| campo | valor |
|---|---|
| `--check` | **`current: true`** · razão: `insumos idênticos` |
| `generated_at` | `2026-09-01T15:43:35-03:00` |
| `built_at_commit` | `48fd4d1c855dfd6c86cf80a3438e9a966251e22e` |
| `input_sha256` | `eef6de3c80f737799cd98ff2eb8177da…` |
| `input_file_count` | 1335 |
| nós operacionais | 455 |
| arestas operacionais | 701 |
| nós híbridos | 20.848 |
| arestas híbridas | 49.889 |

**Nós operacionais afetados:**
- `concept:campaign_measurement_plan` — segue `partial`; evidência atualizada com
  a costura produtiva, a aplicação da v12_02 e a prova transacional
- `concept:tracking_control_plane` — segue `partial`; registra que o schema do
  inventário passou a existir no banco oficial e que **Data Manager continua não
  provado**
- duas arestas novas: `campaign_measurement_plan → tracking_control_plane`
  (`depende_de`) e `campaign_measurement_plan → media_hub` (`governa`) — o
  conceito não tinha nenhuma aresta antes

**Tarefas do Roadmap afetadas:** `P05-T12` (segue **`partial`**).

⚠️ **Data Manager NÃO foi marcado como pronto.** ⚠️ **P05-T12 NÃO foi marcada
como done.** Nenhum arquivo gerado foi editado à mão.

## 12. O que continua aberto

- **plano real durável de campanha nova:** não existe. A tabela está vazia; a
  primeira linha real nascerá no primeiro `/subir` autorizado.
- **Data Manager:** não provado em operação. Nenhum evento, nem `validateOnly`.
- **Tracking Control Plane:** não construído.
- **portões de ativação / Smart Bidding:** G3 continua avaliado só por `/provar`;
  o caminho de escrita não tem portão (`volc_ads/campanha/search.py:57` permite
  `MAXIMIZE_CONVERSIONS`). Risco contido porque a campanha nasce `PAUSED` por
  literal e não existe função de ativação no engine.
- **coleta PMax:** não implementada; os dois bloqueios seguem independentes.

Por isso **P05-T12 permanece `partial`**.
