# Contraprovas concorrentes — P10-T17

Runner: `scripts/provar-concorrencia-v12_04.py`  
Sincronização: `pg_advisory_lock` de sessão no coordenador + `pg_advisory_xact_lock` nos triggers de barreira (`volc.p10t17_hold_origem` / `hold_campaign` / `hold_ledger`). Não é sleep-and-hope.  
`statement_timeout=25s`, `lock_timeout=20s`. SQLSTATE materializado em `volc_p10t17_out`. Cluster `volc-p10-t17-conc-<pid>`, cleanup só desse container.

## Vermelho (RPC anterior, postgres:16-alpine 16.14)

`passaram 4 · falharam 10`

| Caso | Resultado | Evidência |
|---|---|---|
| A | FALHOU | D0 commitado depois rebaixou D-1: `origem='D0' impressoes=10` (esperado D-1/99). Ambos `linhas_aceitas=1`. |
| B | FALHOU | D-1 rebaixou backfill: `origem='D-1' impressoes=20` (esperado backfill/77). |
| C | FALHOU | `colhida_em` menor venceu: `impressoes=1` (esperado 2). |
| D | FALHOU | Inferior iniciada antes/commitada depois: `origem='D0' impressoes=3` (esperado D-1/50). |
| E | FALHOU | Segunda chamada `23505` em `trafego_coleta_execucao_pkey` em vez de `repetida`. |
| F | FALHOU | Recusa `23505` no pkey, não `CHAVE_REUTILIZADA_CONTEUDO_DIVERGENTE`. |
| G | ok | Unique do slot + rollback já impediam órfão. |
| H | FALHOU | Recibos `aceitas=1` dos dois lados; fato ficou D0. |
| I | FALHOU | Fechamento com zeros commitou enquanto o lote ainda estava na barreira. |
| J | ok | CHECK do recibo já desfazia fato+recibo na mesma transação. |
| K | ok | Identidade inclui `customer_id`. |
| L | ok | Sem table lock na RPC antiga. |
| M | FALHOU | Repetiu A (rebaixamento), não deadlock `40P01`. |
| N | FALHOU | D0 rebaixou D-1; o NULL do superior não persistiu. |

## Verde (RPC corrigida)

| Imagem | Versão | A–N | Tempo |
|---|---|---|---|
| postgres:16-alpine | 16.14 | 14/0 (TOCTOU ×3) | 44.6s |
| postgres:15-alpine | 15.19 | 14/0 (TOCTOU ×2) | 41.8s |

Depois da correção, A/D/H: D-1 permanece; D0 devolve `linhas_preteridas=1`, `linhas_aceitas=0`. E: um `execucao_id`, um recibo, `[False, True]` em `repetida`. F: recusa nominal. I: fechamento zero não fecha sobre lote in-flight; fechamento honesto funciona depois do commit. L: fato B commita com A ainda na barreira. N: `conversoes IS NULL` e zeros medidos permanecem zero.

Uma rodada corretiva no runner: `int(impressoes or -1)` tratava `0` como ausente. A RPC já estava correta; o assert foi ajustado.
