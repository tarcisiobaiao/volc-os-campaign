# Prompt — M-W1-03 · Fast-forward da autonomous-closure + gates (Opus, integrador único)

> ⛓ Serializa: nenhuma outra escrita na main durante esta missão.
> Os supervisores em /private/tmp/volc-autonomous-closure podem estar vivos —
> eles escrevem na BRANCH deles, não na main; NÃO toque nos processos.

```text
Você é o integrador único do VOLC O.S. nesta janela. Missão: trazer
integration/autonomous-closure-20260829 (951fe3f) para a main por
fast-forward e provar o resultado pelos gates. Nada de replanejamento: a
análise já foi feita (docs/closure/fable-global-v1/INTEGRATION-LEDGER.md,
FACT-MATRIX F004/F005).

Fatos: main = e858651; a branch está 8 ahead / 0 behind; main é ancestral
dela (FF possível, sem conflito). Conteúdo: ORAKUL Predictive core
(services/orakul_predictive/ + 15 arquivos de teste), builder Demand Gen,
fronteira criativa S0, ratchets; 77 arquivos, +7205/−455, incluindo expansão
do ROADMAP (tarefas P04-T09/P14-T10/P17-T09/P01-T10 — confirme no diff).

Passos:
1. Registro prévio: git rev-parse main > /tmp/pre-ff-sha.txt (rollback).
2. git log --oneline main..integration/autonomous-closure-20260829 — confira
   os 8 commits esperados; qualquer commit extra além dos listados no ledger
   → PARE e reporte (os supervisores podem ter avançado a branch; nesse caso
   integre até 951fe3f exato: git merge --ff-only 951fe3f).
3. git merge --ff-only 951fe3f na main.
4. Gates pós-merge, TODOS com saída registrada:
   a. backend/.venv/bin/python -m pytest volc_ads -q            (esperado: ≥518, provável ~569 com demand_gen)
   b. backend/.venv/bin/python -m pytest backend/tests -q       (esperado: ≥1405)
   c. backend/.venv/bin/python -m pytest backend/tests/orakul_predictive -q  (novo: 36 funções)
   d. npx tsc --noEmit -p tsconfig.app.json | grep -c 'error TS' (esperado: 76, sem piora)
   e. npm run build                                             (verde)
5. Falha nova em qualquer gate → NÃO desfaça em pânico: registre a saída,
   compare com o baseline (falha herdada ≠ nova; consulte FACT-MATRIX F025/F026)
   e reporte antes de qualquer ação.
6. Rollback (apenas se o dono mandar): git reset --hard $(cat /tmp/pre-ff-sha.txt).

Proibições: nenhum outro merge; nenhuma poda; nenhum push; não editar
arquivos; não tocar nos supervisores nem nos bancos deles.

Handoff: SHA final da main, os 5 resultados de gate com contagens exatas,
confirmação de que o roadmap expandido entrou (grep P04-T09
volc-os-workbook/ROADMAP-VIVO.json), e a lista de refs que este FF tornou
supersedidas (feat/orakul-predictive-core-v1, aebbaef, 7174f1f/7bf4ecf,
8dfc78f) para o M-W1-09 podar.
```
