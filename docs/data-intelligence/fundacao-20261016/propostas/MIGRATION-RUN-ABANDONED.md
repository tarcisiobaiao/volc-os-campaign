# Proposta — migration candidata running → abandoned (item 5, não aplicada)

Estado: **candidata**, testada só em PostgreSQL 16 descartável sobre a reconstrução literal do catálogo de produção
(`item5_base_producao_reconstruida.sql`, lida read-only em 17/10/2026). Aplicar só com autorização nominal e o sha256.

| Arquivo | sha256 |
|---|---|
| `item5_0001_google_ads_run_abandoned.sql` | `9440d3ff208144e59c28d910a6289250fbbe54b749ec6168adbd7182717f49c9` |
| `item5_0001_google_ads_run_abandoned.down.sql` | `a90d4e189359e932161164c7b3b987b61ce7eb2d53c9967d7e752d1ee5c641d4` |
| `item5_0002_cotacao_usd_brl.sql` (proposta de câmbio) | `fa57dbd876403a0790b190e0e0388024e734ceb718ea69d4ce4d58233cef8b90` |
| `item5_0002_cotacao_usd_brl.down.sql` | `ed764e7fd38dae794ad557eb369f2788f4f8d4748bab558b63810e64e1973a24` |

## O que faz

- `status` passa a aceitar `abandoned` (o CHECK de `finished_at` continua: abandoned exige fim).
- `google_ads_run_abandonment`: um evento append-only por run, com motivo, limite, minutos sem atividade, última
  atividade (relógio do banco), estado da execução n8n informado pelo reaper, evidência e autor.
- `volc_abandon_google_ads_run(run, status_n8n, autor, evidência, limite=60)`: única porta; idempotente; trava o run;
  só age em `running`; exige mais de 60 min sem lote ou observação; recusa execução n8n ativa ou desconhecida.
- Guarda contra conclusão tardia: `volc_finish_google_ads_run` faz `ON CONFLICT … SET status = EXCLUDED.status`, então
  sem proteção um finish atrasado desfaria o abandono. O gatilho mantém `abandoned` e registra a tentativa em
  `receipt.late_activity`; lote tardio mantém os contadores verdadeiros e também fica registrado.
- Rollback: o `.down.sql` recusa se já houver abandono (seria reescrever histórico); o rollback seguro passa a ser
  `REVOKE EXECUTE` da função.

## Provas (`test_item5_migration_abandoned.py`, 8 testes)

idempotência (1 evento em 2 chamadas); job longo com lote recente não é órfão; recusa `running` no n8n e limite < 60;
run concluído não muda; conclusão tardia pela RPC real não desfaz o abandono; UPDATE direto para `abandoned` é recusado;
evento append-only; `anon` sem permissão e `service_role` com; rollback recusado com abandono e limpo sem.

## Depois de aplicada (exige autorização própria)

1. Atualizar o reaper (`4V7w…`) para chamar a função só com `status_n8n` lido da API do n8n; manter shadow por um
   ciclo comparando a decisão com a função em modo leitura.
2. Releitura imediata dos três órfãos de termos (15/10, execuções n8n `58041`, `58042`, `58044`), recibo
   sanitizado e uma chamada por run.
3. JoinAds: mesmo padrão em `joinads_collection_run` numa candidata separada (o guard atual já permite mudar status).
4. `dq_runs_orfaos = 0` por 7 dias.
