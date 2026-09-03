# Gates — P10-T17

Todos locais. Nenhum gate comparou diff contra o próprio HEAD. Nenhum contato com produção.

## Baseline (antes da correção)

`bash scripts/provar-ciclo-v12_04.sh` → **107 passaram · 0 falharam** em 10.08s, postgres:16-alpine 16.14.  
Concorrência contra a RPC antiga → **4 passaram · 10 falharam** (matriz em COUNTERPROOFS.md).

## Depois da correção

| Gate | Resultado |
|---|---|
| `python3 scripts/provar-concorrencia-v12_04.py --image postgres:16-alpine --repeat-toctou 3` | 14/0, 16.14, 44.6s |
| `python3 scripts/provar-concorrencia-v12_04.py --image postgres:15-alpine --repeat-toctou 2` | 14/0, 15.19, 41.8s |
| `bash scripts/provar-ciclo-v12_04.sh` | 107/0, 5.91s, apply→operate→rollback→reapply |
| `python3 scripts/validar_workflows_n8n_gads.py` | 337/0/2 (2 pulados: SDK google-ads ausente neste Python) |
| `node scripts/simular_gads_ledger_v12.mjs` | 65/0 |
| `python3 scripts/gate_agenda_unica_gads.py` | 10/0/2 (systemctl fora do PATH; `REAL_N8N_READ_NOT_PROVEN`) |
| `pytest backend/tests/test_gads_workflows_n8n.py -q` | 18 passed |
| `python3 scripts/gate_sem_mutacao_google.py` | 3/3 ok (5 contraprovas da rota) |
| `git diff --check` | limpo |
| `python3 scripts/verificar_segredos.py` | nenhum padrão forte |

Imagens exercitadas (já locais, nada baixado): `postgres:16-alpine` (16.14) e `postgres:15-alpine` (15.19). `postgres:16` e `postgres:15` também existem no host e não foram necessárias.

## Revisão focal única

Procurado e não encontrado no diff final: TOCTOU SELECT→UPSERT na decisão de precedência; lock em ordem variável; `LOCK TABLE`; retorno de escrita sem `FOUND`; contador incrementado antes do UPSERT; retry interno; chave divergente aceita; exceção absorvida; recibo/fato órfão no caminho J; rollback que deixa função (ciclo prova o drop); teste só com sleep; gate tautológico contra HEAD.

Achado reproduzido e corrigido numa rodada: assert do caso N com zero Python-falsy. Sem segunda rodada de SQL.
