# Handoff — P10-T17 · Concorrência Atômica do Ledger Google Ads v12_04

## Veredito

`P10_T17_ACCEPTED`

A migration `v12_04_gads_fato_canonico_dia.sql` ficou elegível para uma janela futura de aplicação oficial. Esta missão **não aplicou** a migration no Supabase oficial e **não executou** coleta Google Ads.

## Base e branch

- Repositório: `tarcisiobaiao/volc-os-campaign`
- Branch fonte validada: `origin/volc-os-v2`
- SHA base exigido e confirmado: `34dc7b41bce901bd8bebfdec0a01e293678cbf08`
- Branch de trabalho: `sprint/hermes-p10-t17-gads-ledger-concurrency-v1`
- Worktree isolada: `/root/work/volc-runs/hermes-p10-t17-gads-ledger-concurrency-v1`
- SHA final: resolvido por `git rev-parse HEAD` e confirmado por read-back remoto no relatório de conclusão da missão.

## Escopo alterado

- `supabase/migrations/v12_04_gads_fato_canonico_dia.sql`
- `scripts/provar-ciclo-v12_04.sh`
- `scripts/provar-concorrencia-v12_04.sh`
- `docs/closure/hermes-p10-t17-gads-ledger-concurrency-v1/**`

Nenhum arquivo `n8n/**`, Roadmap, curadoria global ou grafo foi alterado.

## Contraprova vermelha literal

Baseline medido antes da correção em PostgreSQL descartável real:

```text
lock_wait_seen=1
session_b_rc=3
BASELINE_RED_CONFIRMED: true concurrent retry produced non-idempotent loser under observed Lock wait
```

Interpretação: a prova sequencial já passava, mas duas sessões PostgreSQL independentes, disputando a mesma identidade de fato com transações sobrepostas, demonstraram que a perdedora observava `wait_event_type='Lock'` e ainda falhava de forma não-idempotente ao liberar a concorrência.

## Correção aplicada

A menor correção transacional ficou dentro da autoridade PostgreSQL:

1. Guarda de isolamento: a RPC recusa isolamento diferente de `READ COMMITTED` com erro nomeado.
2. Locks transacionais determinísticos por identidade canônica do fato, usando `pg_advisory_xact_lock` antes do lock de idempotência.
3. Lock transacional por chave de idempotência, também com `pg_advisory_xact_lock`.
4. Empate total declarado:
   - mesmo posto + mesmo `colhida_em` + mesmo conteúdo: primeira materialização vence e a posterior deixa recibo coerente como preterida;
   - mesmo posto + mesmo `colhida_em` + conteúdo divergente: erro explícito `FATO_EMPATE_CONTEUDO_DIVERGENTE`.

## Matriz A–K

| Item | Estado | Evidência |
|---|---|---|
| A. Duas execuções concorrendo pela mesma identidade de fato | provado | `scripts/provar-concorrencia-v12_04.sh` com duas sessões `psql` independentes |
| B. Mesma chave + mesmo payload | provado | lock observado, B retorna `repetida=true`, 1 fato, 1 recibo lógico |
| C. Mesma chave + payload divergente | provado | `CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE`, sem overwrite |
| D. Precedência D0 < D-1 < backfill | provado | prova concorrente e ciclo v12_04 |
| E. Empate | provado | empate idêntico preterido; empate divergente recusado |
| F. NULL permanece diferente de zero | provado | ciclo e testes n8n |
| G. Dinheiro permanece micros + moeda | provado | workflow/RPC/ciclo preservam `custo_micros` e `currency_code` |
| H. Fechamento somente depois da escrita do fato | provado | `FECHAMENTO_SEM_ESCRITA` e reconciliação contra fatos |
| I. Falha abertura/escrita/fechamento/retry | provado | falha sem recibo verde, retry idempotente, fechamento reconciliado |
| J. Rollback e reaplicação | provado | `apply → operate → rollback → reapply` verde |
| K. Preservação de recibo | provado | vencedor/perdedor deixam recibos coerentes; perdedor não some |

## Revisão focal independente

Claude Code Opus executou uma única revisão focal independente após o primeiro candidato verde.

- `session_id`: `c6c8c1fa-1da9-489f-af50-ccf4ec73c1a7`
- Achados confirmados/corrigidos:
  - risco de deadlock por locks em ordem não determinística;
  - premissa de isolamento não declarada;
  - empate total divergente precisava virar conflito explícito;
  - fragilidade de contrato em isolamento snapshot-fixo.
- Rodada corretiva: única, focal, aplicada nos pontos acima.

## Estado honesto de P10-T17

`P10_T17_ACCEPTED`: a concorrência atômica da RPC v12_04 foi provada com PostgreSQL real descartável, duas conexões independentes e `wait_event_type='Lock'` observável. A migration está elegível para futura janela oficial, mas ainda não aplicada ao Supabase oficial.

## Zero mutação externa

- zero Supabase oficial write;
- zero migration oficial;
- zero Google Ads call;
- zero Google Ads mutate/validate-only;
- zero Data Manager;
- zero n8n write/import/activation;
- zero systemd/timer;
- zero deploy;
- zero merge em `volc-os-v2` ou `main`;
- zero Roadmap/grafo.
