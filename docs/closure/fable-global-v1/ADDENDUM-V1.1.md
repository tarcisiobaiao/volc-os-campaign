# ADDENDUM V1.1 — revalidação adversarial (2026-08-29, ~21h)

Revalida o pacote fable-global-v1 contra o Git real desta janela. Marcas:
**CONFIRMADA AGORA** (reverificada nesta janela) · **CONFIRMADA NO SNAPSHOT**
(válida às 23:21Z, não reverificada) · **SUPERADA POR EVENTO NOVO** ·
**EXIGE PROVA** · **EXIGE DECISÃO HUMANA**.

## 1. Revalidação das conclusões principais

| Afirmação do pacote | Marca | Evidência desta janela |
|---|---|---|
| main = e858651; FF da autonomous-closure possível | **CONFIRMADA AGORA** | `git rev-parse main`; `0 behind`; `merge-base --is-ancestor` = sim |
| autonomous-closure = 8 ahead, tip 951fe3f | **SUPERADA POR EVENTO NOVO** | agora **10 ahead, tip `bdf9e1c`**: +`222bd27` e `bdf9e1c` (fix venv dos gates + overlay legacy) |
| Defeito 1 do harness (gate chama venv inexistente) precisa ser corrigido no M-W1-05 | **SUPERADA POR EVENTO NOVO** | o fix existe em DUAS linhas patch-equivalentes (`git cherry` marca `-`): `7aa53aa`+`14fe1b4` (supervisor-continuo) ≡ `222bd27`+`bdf9e1c` (autonomous-closure). **O FF sozinho entrega a correção na main**; M-W1-05 perde esse item do escopo |
| Defeito 2 (escopo de leitura dos reviewers Gemini) sem correção | **SUPERADA POR EVENTO NOVO** (parcial) | `8380b2d` no tip de feat/harness-gemini-37-flash-v1 (15 ahead): leitura ancestral read-only, diff do candidato ao reviewer, ratchet revisa candidato preservado. **Não integrado** |
| "42 testes verdes" (7aa53aa) e "45 verdes" (8380b2d) | **EXIGE PROVA** | auto-relato; comando: `.venv-adk/bin/python -m pytest tools/agent-harness/tests -q` pós-merge (deps do venv podem faltar — F026) |
| Provas focais (ORAKUL 57+20, S0 123, DemandGen 228+27, pytest 33) | **EXIGE PROVA** | auto-relato dos writers/branches; teste focal verde ≠ integração aprovada; rodam nos gates das filas RQ |
| Manifestos de recuperação Search/PMax/Health "em preparação" | **EXIGE PROVA** | não localizados nesta janela — lacuna declarada |
| Candidatos Gemini 5eb6b38 / 656d72d existem, nunca revisados | **CONFIRMADA AGORA** | `git log -1` de ambos os SHAs completos confere |
| 6fc7923 (cancel/cleanup) segue fora de todas as linhas | **CONFIRMADA AGORA** | `merge-base --is-ancestor 6fc7923 feat/supervisor-continuo-v0` → NÃO |
| 4 frentes autônomas mortas/bloqueadas; writers com trabalho não-candidato | **CONFIRMADA AGORA** (corrigida) | as 4 worktrees estão preservadas com **mudanças NÃO COMMITADAS** (dirty: demand-gen 11 arquivos, orakul 31, creative-s0 5, pytest 1) sobre 8dfc78f/951fe3f — a colheita é de diff sujo, não de branch |
| 2 supervisores ainda vivos (watch ocioso) | **CONFIRMADA AGORA** | pids 72528 e 80004 em `ps`; nenhum writer codex rodando |
| origin/main = Initial commit; 411+ commits sem backup | **CONFIRMADA NO SNAPSHOT** | não re-medida; nada a empurrou (nenhum push ocorreu) |
| Webhook apply-bidding ativo sem auth; 13 flows no hosted legado; v12_01 sem consumidor; v10/v11_03 não aplicadas; canário Search real | **CONFIRMADA NO SNAPSHOT** | fontes documentais inalteradas nesta janela |
| P05-T04 a um clique; decisões D1–D13 | **EXIGE DECISÃO HUMANA** | inalteradas |

## 2. Correções ao pacote v1

1. **INTEGRATION-LEDGER §1 item 1**: alvo do FF passa de `951fe3f` para
   **`bdf9e1c`** (10 commits). O handoff do M-W1-03 deve conferir os 10.
2. **M-W1-05 (convergência harness)**: escopo REDUZIDO — o fix do venv já
   entra pelo FF. Restam: merge dos 4 commits exclusivos do supervisor-continuo
   (`8de010d`, `061fdf8`, `9f72a13`, `5810036` — supervisor+ratchet+linhagem),
   merge do harness-gemini (15 commits, incl. `8380b2d`), revisão substituta do
   `6fc7923`, GEMINI_API_KEY fora do dotenv, README v2.
3. **M-W2-06 (colheita)**: comparar os diffs SUJOS das worktrees contra
   `bdf9e1c` (não 951fe3f); o material é uncommitted — **um `git clean` ou
   remoção de worktree destrói a colheita**. Preservação é prioridade.
4. **Alerta novo**: a worktree do pytest-writer modificou `pytest.ini` — a
   spec M-W2-03 proíbe exatamente isso; a colheita dessa frente deve ser
   confrontada com a missão antes de portar qualquer hunk.

## 3. Revisão adversarial das minhas próprias recomendações

| Checagem | Resultado |
|---|---|
| SHA inexistente? | Todos os SHAs citados resolvem (`7aa53aa`, `8380b2d`, `bdf9e1c`, `14fe1b4`, `222bd27`, `5eb6b38a65…`, `656d72df72…`, `6fc7923`) |
| Branch superada recomendada para merge? | `feat/supervisor-continuo-v0` tem 2 dos 6 commits JÁ patch-equivalentes na autonomous-closure — o merge pós-FF deve esperar `git cherry` mostrar só 4 `+`; se mostrar 6, PARE |
| FF realmente possível? | Sim agora (0 behind), mas os supervisores vivos podem avançar a branch DE NOVO — o FF deve mirar `bdf9e1c` explícito (`git merge --ff-only bdf9e1c`), não o nome da branch |
| Gate dependendo do venv errado? | Os gates das missions v1 usam caminho absoluto do repo principal — funcionam; a suite do harness ainda **EXIGE PROVA** de rodar no .venv-adk (deps) |
| Duas frentes nos mesmos arquivos? | SIM — supervisor-continuo × harness-gemini colidem em `mission.py`, `models.py`, `worktrees.py`, `supervisor*.py`, testes; e harness-gemini × autonomous-closure colidem em `mission.py`. Por isso a fila é ESTRITAMENTE serial: FF → supervisor-continuo → harness-gemini → 6fc7923, com gates entre cada um |
| Candidato com teste focal verde sem revisão independente? | `5eb6b38` (nunca revisado), `656d72d` (gates verdes, revisão crashou), `6fc7923` (changes_requested não resolvido), e os 4 diffs sujos — TODOS exigem revisão substituta antes de merge; nenhum entra "porque está verde" |
| Ação externa escondida? | Nenhuma na fila; push é o único item externo e está atrás de autorização explícita (RQ-11/D9) |
| "done" sem evidência? | Nenhuma promoção automática: o único toque em Roadmap/curadoria/grafo é o RQ-10, uma vez, com prova por item |

## 4. Tabela final

| EXECUTAR AGORA | EXECUTAR DEPOIS | DECISÃO HUMANA | NÃO EXECUTAR |
|---|---|---|---|
| RQ-01 snapshot preflight | RQ-04 merge supervisor-continuo | D9 destino do backup (libera RQ-11) | Instalar systemd / ativar workflows n8n |
| RQ-02 FF `bdf9e1c` + gates | RQ-05 merge harness-gemini | D1 aplicar v10 | Aplicar v10/v11_03/v13 nesta fila |
| RQ-03 preservar colheita (diffs sujos → patches) | RQ-06 revisão+merge `6fc7923` | D4+D10 janela de segurança | Tocar webhook/n8n/Supabase/Google Ads |
| M-W1-06 / M-W1-08 (read-only, harness) | RQ-07 revisão substituta candidatos Gemini | D5 validate_only real | `git clean`/remover worktrees antes do RQ-03 |
| M-W2-01 (diagnóstico, harness) | RQ-08 portar colheita via missões | H1 clique dos vínculos | Push sem D9 |
| | RQ-09 gates finais consolidados | D13 encerrar/reativar supervisores | `graphify update .` |
| | RQ-10 Roadmap/curadoria/grafo (uma vez) | | Promover tarefa por inferência |
| | RQ-11 push (pós-D9) | | Editar cópias de /private/tmp |
