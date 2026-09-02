# Revisão focal — P10-T16

Revisão executada depois do candidato commitado. `codex` e `gemini` não estavam disponíveis no host; fallback autorizado: duas sessões frescas de Claude Opus, somente leitura, com diff sanitizado por foco.

## Revisor 1 — concorrência/dados

**Resultado:** reprovou para ativação imediata, aprovou o artefato apenas como inativo. Principais achados:

- risco de `ON CONFLICT DO UPDATE` rebaixar precedência em concorrência real;
- fechamento conta fatos pelo `execucao_id` atual do fato, sensível a sobrescrita posterior;
- projeção preserva `roas/rps/ecpm` legados enquanto muda spend/clicks/impressions;
- linha com identidade ausente caía no detector de duplicata antes da recusa semântica;
- vários caminhos de erro abortam transação sem recibo, por desenho fail-closed.

**Correções aplicadas nesta rodada:**

- detector de duplicata agora usa `coalesce` em todos os campos da chave e deixa a validação semântica nomear identidade ausente;
- RPC adicionou `trafego_coleta_execucao_ok_sem_recusa` e degrada lote `ok` com rejeições para `parcial`/`falhou` antes de gravar o recibo;
- default de `projetar_compat` ficou fechado (`false`) para documentos manuais incompletos; os workflows novos declaram explicitamente `true`;
- hashes da migration foram atualizados e o ciclo descartável foi reexecutado verde.

**Não corrigido nesta lane:** concorrência real entre execuções com a mesma chave de fato continua uma limitação de desenho a ser validada antes de ativação. Como a missão não ativa nada e exige canário/autorização posterior, fica declarado como risco de ativação, não como prova operacional verde.

## Revisor 2 — n8n/Google

**Resultado:** reprovou para ativação imediata, aprovou permanência inativa com correções. Principais achados:

- header `developer-token` tentava usar `$credentials`, que não é mecanismo seguro/provado em expressão de workflow;
- respostas vazias de inventário poderiam terminar o fluxo sem o Code node lançar falha fechada;
- pareamento por `Merge` ainda precisa de prova contra n8n real para o ramo de erro;
- fechamento ignorava `linhas_rejeitadas` no rótulo de saúde;
- notas sobre fuso da conta Google Ads, limites do inventário, retenção de execução e colisão de horários 06:00.

**Correções aplicadas nesta rodada:**

- removida a expressão `$credentials.developerToken`; o fluxo deixa OAuth/developer token sob responsabilidade da credencial Google Ads/preflight de autorização, sem segredo no JSON;
- `Contas autorizadas` e `Campanhas conhecidas` agora têm `alwaysOutputData: true` para manter a falha fechada quando o PostgREST retorna `[]`;
- classificador de erro também inspeciona `error` string, preservando 401/403/429/5xx quando o HTTP Request entregar erro textual;
- fechamento passou a considerar `linhas_rejeitadas` como `parcial`/`falhou`, não `ok`.

**Não corrigido nesta lane:** prova contra n8n real, resolução real da credencial Google Ads/developer-token e fuso da conta Google Ads. Todos permanecem pré-condições no pacote de autorização.

## Revalidação depois da rodada corretiva

- `bash scripts/provar-ciclo-v12_04.sh` → `passaram 107 · falharam 0`;
- `bash scripts/provar-ponta-a-ponta-gads.sh` → `passaram 12 · falharam 0`;
- `python3 scripts/validar_workflows_n8n_gads.py` → `passaram 339 · falharam 0 · pulados 0`;
- `node scripts/simular_gads_ledger_v12.mjs` → `passaram 65 · falharam 0`;
- `python3 -m pytest backend/tests/test_gads_workflows_n8n.py -q` → `18 passed`;
- `python3 scripts/gate_agenda_unica_gads.py` → `passaram 14 · falharam 0 · pulados 1`;
- `python3 scripts/verificar_segredos.py` → nenhum padrão forte;
- `git diff --check` → sem saída.
