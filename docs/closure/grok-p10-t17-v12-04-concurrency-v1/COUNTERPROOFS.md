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

## Verde (RPC corrigida, matriz A–N)

| Imagem | Versão | A–N | Tempo |
|---|---|---|---|
| postgres:16-alpine | 16.14 | 14/0 (TOCTOU ×3) | 44.6s |
| postgres:15-alpine | 15.19 | 14/0 (TOCTOU ×2) | 41.8s |

Depois da correção, A/D/H: D-1 permanece; D0 devolve `linhas_preteridas=1`, `linhas_aceitas=0`. F: recusa nominal. I: fechamento zero não fecha sobre lote in-flight. L: fato B commita com A ainda na barreira. N: `conversoes IS NULL` e zeros medidos permanecem zero.

O caso E dessa rodada só comprovava duas threads próximas. Não observava waiter em `pg_locks`.

## Verde (microcorreção, matriz A–Q)

| Imagem | Versão | A–Q | Tempo | comando |
|---|---|---|---|---|
| postgres:16-alpine | 16.14 | 17/0 (TOCTOU ×3 em A–D/H/N/O/P) | 59.9s | `python3 scripts/provar-concorrencia-v12_04.py --image postgres:16-alpine --repeat-toctou 3` |
| postgres:15-alpine | 15.19 | 17/0 (TOCTOU ×2) | 52.4s | `python3 scripts/provar-concorrencia-v12_04.py --image postgres:15-alpine --repeat-toctou 2` |

E (16.14, observação em `pg_locks` **antes** de liberar a barreira de A):

```
EVIDENCIA_E={"classid": 120405, "hashtext": 451675352, "holders": 1, "locks": [{"application_name": "a", "granted": true, "objsubid": 2, "pid": 1058}, {"application_name": "b", "granted": false, "objsubid": 2, "pid": 1079}], "objid": "451675352", "waiters": 1}
```

A (`application_name=a`) tem o advisory 120405 granted; B (`application_name=b`) está `granted=false` no mesmo `classid`/`objid` (`hashtext('v12_04:idemp:' || 'E-same|1')`). Só então a barreira 120417/12 é liberada. Resultado: um recibo, mesmo `execucao_id`, `repetida` `[false, true]`, nenhum `23505`, um fato.

A mesma espera reapareceu nas três voltas do caso M e na matriz 15.19 (`holders=1`, `waiters=1`, `classid=120405`, `objsubid=2`).

O (empate idêntico, TOCTOU): first-writer permanece; a outra execução grava recibo com `linhas_preteridas=1`.

P (empate divergente em `campaign_name` + `search_click_share` + `metricas_extras`, impressões iguais): `FATO_EMPATE_CONTEUDO_DIVERGENTE`; zero recibo do perdedor; fato intacto.

Q: `REPEATABLE READ` e `SERIALIZABLE` recusam `ISOLAMENTO_NAO_SUPORTADO_V12_04` sem persistir; READ COMMITTED de controle persiste.

Uma rodada corretiva anterior no runner: `int(impressoes or -1)` tratava `0` como ausente. A RPC já estava correta; o assert foi ajustado.
