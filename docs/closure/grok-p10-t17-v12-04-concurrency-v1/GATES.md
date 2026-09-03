# Gates — P10-T17

Todos locais. Nenhum contato com produção.

O `git diff --check` desta lane **não** é o da working tree vazia (`git diff --check` sem range). O comando exigido é contra a base:

```
git diff --check 34dc7b41bce901bd8bebfdec0a01e293678cbf08..HEAD
```

Na publicação anterior esse check falhava: trailing whitespace em `COUNTERPROOFS.md` (L3–L4), `GATES.md` (L7) e `HANDOFF.md` (L3–L7). Os resíduos eram os dois espaços de quebra Markdown. Foram removidos nestes arquivos.

## Baseline (antes da correção)

`bash scripts/provar-ciclo-v12_04.sh` → **107 passaram · 0 falharam** em 10.08s, postgres:16-alpine 16.14.

Concorrência contra a RPC antiga → **4 passaram · 10 falharam** (matriz em COUNTERPROOFS.md).

## Depois da correção atômica (A–N)

| Gate | Resultado |
|---|---|
| concorrência postgres:16-alpine `--repeat-toctou 3` | 14/0, 16.14, 44.6s |
| concorrência postgres:15-alpine `--repeat-toctou 2` | 14/0, 15.19, 41.8s |
| `bash scripts/provar-ciclo-v12_04.sh` | 107/0 |

## Depois da microcorreção (A–Q, isolamento, empate, diff-check real)

| Gate | Resultado |
|---|---|
| `python3 scripts/provar-concorrencia-v12_04.py --image postgres:16-alpine --repeat-toctou 3` | 17/0, 16.14, 59.9s. E observou waiter classid 120405 (`holders=1 waiters=1`, A granted / B not granted) antes de soltar a barreira. |
| `python3 scripts/provar-concorrencia-v12_04.py --image postgres:15-alpine --repeat-toctou 2` | 17/0, 15.19, 52.4s. Mesma evidência de 120405. |
| `bash scripts/provar-ciclo-v12_04.sh` | 116/0, 8.24s, postgres:16-alpine 16.14, apply→operate→rollback→reapply. Inclui CP-25 (isolamento) e CP-26 (empate). Rollback apagou 17 fatos e 25 recibos com declaração de perda. |
| `python3 scripts/validar_workflows_n8n_gads.py` | 337/0/2 (2 pulados: SDK google-ads ausente neste Python) |
| `node scripts/simular_gads_ledger_v12.mjs` | 65/0 |
| `python3 scripts/gate_agenda_unica_gads.py` | 10/0/2 (systemctl fora do PATH; `REAL_N8N_READ_NOT_PROVEN`) |
| `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/backend/.venv/bin/python -m pytest backend/tests/test_gads_workflows_n8n.py -q` | 18 passed |
| mesmo interpretador em `scripts/gate_sem_mutacao_google.py` | 3/3 ok (5 contraprovas da rota) |
| `python3 scripts/verificar_segredos.py` | nenhum padrão forte |
| `git diff --check 34dc7b41bce901bd8bebfdec0a01e293678cbf08..HEAD` | executado após os commits desta microcorreção; ver relatório da lane. Não usar `git diff --check` sem range. |

Imagens exercitadas (já locais, nada baixado): `postgres:16-alpine` (16.14) e `postgres:15-alpine` (15.19). Nenhum container `volc-p10-t17-*` / `volc-v1204-*` residual depois das provas.

## Revisão focal única

Procurado e não encontrado no diff desta microcorreção: TOCTOU SELECT→UPSERT na decisão de precedência; lock em ordem variável; `LOCK TABLE`; retorno de escrita sem `FOUND`; contador incrementado antes do UPSERT; retry interno; chave divergente aceita; exceção absorvida; recibo/fato órfão no caminho J; rollback que deixa função (ciclo prova o drop); teste de idempotência só com sleep; gate tautológico contra HEAD vazio; empate divergente preterido em silêncio; isolamento alienígena aceito.

Achado reproduzido na publicação anterior: assert do caso N com zero Python-falsy (corrigido então). Achado desta microcorreção no gate publicado: `git diff --check` vacuamente verde contra working tree vazia (corrigido: range `BASE..HEAD` e whitespace removido). Caso E agora falha se B não aparecer como waiter de 120405.
