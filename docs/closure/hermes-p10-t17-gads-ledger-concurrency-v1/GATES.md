# Gates — P10-T17 v12_04

## Comandos obrigatórios

| Comando | Resultado |
|---|---|
| `bash scripts/provar-ciclo-v12_04.sh` | verde: `passaram 110 · falharam 0` |
| `bash scripts/provar-concorrencia-v12_04.sh` | verde: `passaram 5 · falharam 0` |
| `python3 scripts/validar_workflows_n8n_gads.py` | verde: `passaram 339 · falharam 0 · pulados 0` |
| `node scripts/simular_gads_ledger_v12.mjs` | verde: `passaram 65 · falharam 0` |
| `python3 scripts/gate_agenda_unica_gads.py` | verde: `passaram 14 · falharam 0 · pulados 1` |
| `python3 -m pytest backend/tests/test_gads_workflows_n8n.py -q` | verde: `18 passed, 5 warnings` |
| `python3 scripts/verificar_autoridade_supabase.py` | verde: escrita oficial travada; 5 contraprovas focais passaram |
| `python3 scripts/gate_sem_mutacao_google.py` | verde: nenhuma mutação chamada sem recibo `em_voo` persistido antes |
| `git diff --check` | verde |
| `python3 scripts/verificar_segredos.py` | verde: nenhum padrão forte encontrado |

## Observações

- `gate_agenda_unica_gads.py` mantém 1 item pulado por desenho: leitura viva do n8n não foi provada nesta missão, e o usuário proibiu chamada/alteração viva de n8n. O gate versionado confirmou que nenhuma autoridade nova de agenda foi instalada/ativada no repositório.
- A verificação de autoridade Supabase foi somente leitura e não aplicou migration.
- A prova concorrente executou PostgreSQL descartável via Docker e descartou o container ao final.

## Contagens materiais

| Prova | Passaram | Falharam | Pulados |
|---|---:|---:|---:|
| Ciclo v12_04 com concorrência integrada | 110 | 0 | 0 |
| Concorrência atômica direta | 5 | 0 | 0 |
| Validador n8n | 339 | 0 | 0 |
| Simulador n8n offline | 65 | 0 | 0 |
| Agenda única | 14 | 0 | 1 |
| Pytest focal | 18 | 0 | 0 |
