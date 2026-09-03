# P10-T17 — concorrência atômica da RPC v12_04 · handoff

**Branch:** `sprint/grok-p10-t17-v12-04-concurrency-v1`

**Worktree:** `/private/tmp/volc-grok-p10-t17-v12-04-concurrency-v1`

**Base:** `34dc7b41bce901bd8bebfdec0a01e293678cbf08` (`origin/volc-os-v2`, confirmado após `git fetch origin --prune`)

**Data:** 2026-09-03

**Veredito:** `P10_T17_LOCAL_CONCURRENCY_ACCEPTED`

**Push:** somente esta branch, após gates verdes desta microcorreção. **Merge:** não. **Main:** intocada. **Supabase oficial:** intocado.

`docs/closure/fable-sniper-plan-v2/PLANO-MESTRE.md` não existe nesta base. A procedência usada foi `ROADMAP-VIVO.json` (P10-T17), o contrato D0/D-1, a revisão focal P10-T16 e a migration v12_04.

---

## 1. O que fechou

A RPC `public.volc_registrar_gads_campanha_dia(jsonb)` deixava a precedência e a idempotência fora do UPSERT:

- `SELECT` do fato sem lock, depois `ON CONFLICT DO UPDATE` incondicional;
- `SELECT` do recibo sem lock, depois `INSERT`;
- fechamento lia o ledger em READ COMMITTED e podia fechar zero contra lote ainda não commitado.

A contraprova com duas sessões reais e barreiras por advisory lock reproduziu o rebaixamento: D0 commitado por último gravava `origem='D0'` por cima de D-1. A correção mínima permanece: UPSERT condicional atômico, locks transacionais, fato antes do recibo na mesma transação.

Microcorreção nesta mesma branch (sem nova arquitetura):

1. `git diff --check BASE..HEAD` medido contra a base, não contra working tree vazia; trailing whitespace removido.
2. Caso E observa em `pg_locks` que B espera o advisory classid 120405 da chave antes de A sair da barreira.
3. Empate total (mesma precedência + mesmo `colhida_em` + mesmo fato canônico): conteúdo persistível idêntico vira preterida; divergência recusa `FATO_EMPATE_CONTEUDO_DIVERGENTE`.
4. Isolamento diferente de READ COMMITTED recusa `ISOLAMENTO_NAO_SUPORTADO_V12_04` antes dos locks.

## 2. Causa

Hipótese confirmada por reprodução, não por leitura:

1. Duas transações fazem `SELECT` do fato vazio.
2. A superior (D-1 / backfill / `colhida_em` maior) insere e commita.
3. A inferior, já decidida a escrever, cai no `ON CONFLICT DO UPDATE` sem `WHERE` e rebaixa o fato.
4. Duas chamadas com a mesma `chave_idempotencia` passam do `SELECT` inicial; uma toma `23505` no `PRIMARY KEY` em vez de devolver `repetida` ou `CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE`.
5. Fechamento com zeros visíveis commita enquanto o lote de contas ainda está na barreira de escrita.
6. O caso E antigo só disparava duas threads; sem barreira posterior ao lock 120405, a sobreposição não era observada.
7. Empate total caía em preterida mesmo com conteúdo persistível divergente.
8. A premissa READ COMMITTED não era recusada nem provada como contrato da RPC.

## 3. Solução

- A RPC recusa `current_setting('transaction_isolation')` distinto de `read committed` com `ISOLAMENTO_NAO_SUPORTADO_V12_04` (SQLSTATE `0A000`) antes de tomar locks. PostgreSQL mapeia READ UNCOMMITTED para READ COMMITTED; nesse caso `current_setting` devolve `read committed` e a chamada segue.
- `pg_advisory_xact_lock(120405, hashtext('v12_04:idemp:' || chave_idempotencia))` e, em seguida, `pg_advisory_xact_lock(120404, hashtext('v12_04:exec:' || execucao_chave))`. Ordem global fixa. Locks de transação, nunca de sessão. Sem table lock.
- Depois dos locks, a leitura de idempotência e o `LOTE_JA_OCUPADO` nomeado.
- `INSERT ... ON CONFLICT DO UPDATE ... WHERE EXCLUDED.precedencia > g.precedencia OR (empate AND EXCLUDED.colhida_em > g.colhida_em)`, recusando overwrite da mesma execução.
- Miss do UPSERT + `SELECT ... FOR UPDATE`: se precedência e `colhida_em` empatam, compara o estado persistível do INSERT/UPDATE (segmentos, metadados da campanha, moeda, API, métricas, shares, percentuais, `metricas_extras`). Idêntico: `linhas_preteridas`. Divergente: `FATO_EMPATE_CONTEUDO_DIVERGENTE` e rollback da transação.
- Comparação exclui, documentado no SQL: `fato_id`; identidade já casada pelo índice (`customer_id`, `campaign_id`, `metric_date`, `segments_hash`); `execucao_id`; `colhida_em` (chave do empate); `origem_janela` / `janela_fechada` / `precedencia`; `atualizada_em`.
- `linhas_aceitas` / `linhas_preteridas` só depois de `FOUND` no UPSERT (ou da classificação sob `FOR UPDATE`).
- Linhas do lote ordenadas por identidade canônica.
- Sem retry interno, RPC única, RLS/FORCE, `SECURITY DEFINER`, `search_path` fixo e ledger append-only preservados.

## 4. Estado honesto de P10-T17

A concorrência atômica está **provada em Postgres descartável** (matriz A–Q). A migration **continua não aplicada** oficialmente (`supabase/migrations/README.md` nesta base ainda registra “não aplicada”; esta lane não consultou produção). Ativação n8n, canário e heartbeat continuam fora de escopo.

Proposta de curadoria: promover **somente P10-T17** para `done` com a prova local. P10-T16 permanece `partial`.

## 5. Limitações

- Colisão de `hashtext` pode serializar duas execuções distintas; não rebaixa fato nem mistura identidade.
- Páginas da mesma `execucao_chave` serializam entre si (lote vs lote vs fechamento). Fatos de execuções diferentes não serializam a tabela (caso L).
- O handler de `unique_violation` no INSERT do recibo é rede de segurança; o caminho feliz da idempotência é o lock 120405 + `SELECT`.
- `docs/closure/fable-sniper-plan-v2/PLANO-MESTRE.md` ausente nesta SHA.
- Gate n8n pulou 2 provas GAQL (SDK google-ads indisponível neste Python). Gate de agenda pulou systemd (`systemctl` fora do PATH) e a leitura viva (`REAL_N8N_READ_NOT_PROVEN`).
- Zero mutação externa: nenhum write em `database.agenciavolc.com.br`, n8n, Google Ads ou Data Manager.

## 6. Arquivos

| Arquivo | Natureza |
|---|---|
| `supabase/migrations/v12_04_gads_fato_canonico_dia.sql` | UPSERT condicional, locks 120405→120404, isolamento, empate |
| `scripts/provar-concorrencia-v12_04.py` | Runner A–Q, espera observada em 120405, SQLSTATE |
| `scripts/provas-v12_04.sql` | CP-25 isolamento; CP-26 empate sequencial |
| `docs/closure/grok-p10-t17-v12-04-concurrency-v1/**` | Handoff, contraprovas, gates, matriz, curadoria |

Rollback `v12_04_rollback.sql` não precisou mudar: continua dropando a função inteira.
