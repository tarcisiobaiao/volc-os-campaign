# Prova de Concorrência — P10-T17 v12_04

## Contrato da prova

A prova não usa sequência disfarçada de concorrência. Ela cria:

- PostgreSQL real descartável (`postgres:16-alpine`);
- duas conexões `psql` independentes;
- transações sobrepostas;
- sessão A segurando a região crítica;
- sessão B observada bloqueada por `pg_stat_activity.wait_event_type='Lock'`;
- leitura final de fato e recibo.

Arquivo versionado:

```text
scripts/provar-concorrencia-v12_04.sh
```

## Baseline vermelho antes da correção

Resultado literal preservado no handoff:

```text
lock_wait_seen=1
session_b_rc=3
BASELINE_RED_CONFIRMED: true concurrent retry produced non-idempotent loser under observed Lock wait
```

Isto refutou a alegação de que os testes sequenciais bastavam para concorrência. O defeito aparecia somente com duas transações reais e bloqueio observável.

## Mecanismo de sincronização verde

A RPC usa locks transacionais cooperativos no PostgreSQL:

1. `pg_advisory_xact_lock(hashtextextended('v12_04:fato:' || identidade_canonica, 0))`
2. identidade canônica do fato: `customer_id | campaign_id | metric_date | segments_hash`
3. aquisição dos locks de fato em ordem determinística (`ORDER BY 1`) antes do lock de idempotência;
4. `pg_advisory_xact_lock(hashtextextended('v12_04:idempotencia:' || chave_idempotencia, 0))`
5. guarda explícita de isolamento: apenas `READ COMMITTED` é suportado.

## Provas verdes diretas

`bash scripts/provar-concorrencia-v12_04.sh`:

```text
ok   concorrência mesma chave+payload: Lock observado, B idempotente, sem duplicar
ok   mesma chave+payload divergente: recusa explícita sem overwrite
ok   precedência D0<D-1<backfill e empate determinístico deixam recibo
ok   empate total com conteúdo divergente é conflito explícito
ok   isolamento diferente de READ COMMITTED é recusado com nome
passaram 5 · falharam 0
```

## Semântica de empate

Empate total é resolvido de forma conservadora:

- se conteúdo é igual: primeira materialização permanece; a posterior deixa recibo coerente como preterida;
- se conteúdo diverge: a RPC recusa com `FATO_EMPATE_CONTEUDO_DIVERGENTE`;
- isto preserva a relação recibo→fato e evita reescrever silenciosamente uma linha já prometida por recibo anterior.

## Limitação explicitada

A garantia é da porta oficial `public.volc_registrar_gads_campanha_dia(jsonb)` em `READ COMMITTED`. Escritores manuais que ignorem a RPC continuam fora do contrato; a migration já revoga escrita direta para `service_role` e mantém RLS forçada, de modo que a porta operacional versionada é a RPC.
