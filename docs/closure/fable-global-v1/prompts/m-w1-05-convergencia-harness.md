# Prompt — M-W1-05 · Convergência do harness v2 + correção dos 2 defeitos (Codex escreve, Opus revisa)

> ⛓ Após M-W1-04. Trabalhe numa branch nova a partir da main
> (`feat/harness-v2-convergencia`); o merge final é do integrador.
> As cópias de /private/tmp são FONTE DE LEITURA, nunca destino de edição.

```text
Missão: trazer o harness v2 para a main e corrigir os dois defeitos que
mataram as frentes de 29/08. A investigação já foi feita — não redescubra
(docs/closure/fable-global-v1/FACT-MATRIX.json F011-F014, F038, F041; cluster
CL-14).

Fontes:
- main: tools/agent-harness (v1, contrato MissionSpec em src/volc_agent_harness/models.py).
- feat/harness-gemini-37-flash-v1 (e92793e): 14 commits — provider gemini,
  gemini_worker.py, fila Gemini ADS.
- feat/supervisor-continuo-v0 (5810036) + 6fc7923: supervisor contínuo
  (supervisor.py, supervisor_store.py, supervisor_models.py) + cancelamento/
  cleanup conservador (6fc7923 estava changes_requested por wall_budget — a
  revisão anterior tem ressalvas; leia o review-result do run em
  /private/tmp/volc-supervisor-continuo-v0/tools/agent-harness/runs/).

Entregas (nesta ordem, commits separados):
1. MERGE das duas pontas na sua branch (reconcilie: o harness-gemini NÃO
   contém 6fc7923).
2. DEFEITO 1 (gates): no load da missão (cli.py/mission.py), valide
   fail-fast que argv[0] de cada gate existe e é executável (os.access);
   erro claro citando o caminho. Cobertura: teste com gate inexistente.
3. DEFEITO 2 (escopo de leitura): reviewers/investigators Gemini ganham
   LEITURA repo-wide (a escrita continua bloqueada pelo ownership); a
   PermissionError de leitura fica restrita a writers fora do allowed_paths.
   Cobertura: teste de reviewer lendo fora do escopo sem crash.
4. GEMINI_API_KEY: remover a leitura via dotenv de .env.local
   (gemini_worker.py); a chave vem do ambiente do processo supervisor.
   Documente no README a variável esperada.
5. README do harness: documentar o v2 inteiro (task_ids, ratchet, supervisor,
   provider gemini, run_id com hash, limites) — hoje a única doc é o código.
6. Ambiente de teste: garanta que a suite do harness roda com
   .venv-adk/bin/python -m pytest tools/agent-harness/tests (adicione pytest
   e jsonschema ao requirements/pyproject do harness; instale no .venv-adk).

Gates (rode e registre contagens):
- .venv-adk/bin/python -m pytest tools/agent-harness/tests -q
- backend/.venv/bin/python -m pytest volc_ads -q  (não pode regredir)
- python3 -c "import json;json.load(open('tools/agent-harness/missions/search-intelligence-vertical-max.json'))" (missões v1 continuam válidas)

Proibições: não tocar nos processos/bancos dos supervisores vivos; não editar
as cópias de /private/tmp; não mudar o contrato MissionSpec de forma que
missões v1 existentes quebrem (extras v2 são opcionais com default); zero
segredo.

Handoff: SHAs dos commits, contagens dos gates, diff-resumo por entrega,
ressalvas do 6fc7923 que você acatou/rejeitou (com motivo), e o delta de
curadoria proposto (nó concept:agentic-recovery-runtime e afins).
```
