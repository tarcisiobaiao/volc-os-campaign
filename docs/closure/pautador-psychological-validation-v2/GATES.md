# Gates

Base: `origin/volc-os-v2 @ b2af81f0a2018626c5d873574664991b16f7ce38`
Branch: `sprint/pautador-psychological-validation-v2`
Worktree: `/private/tmp/volc-pautador-psychological-validation-v2`
Interpretador: `backend/.venv/bin/python` (3.14.6, pytest 9.1.1) — do checkout
principal, porque o worktree não tem venv própria.

Nenhuma suíte completa rodou em paralelo com outra.

---

## Baseline, medido ANTES de tocar em qualquer código

```
backend/tests + backend/app/motor_pautas/testes
    -> 3601 passed, 112 skipped em 97,63s
focal (motor_pautas/testes + test_pautador_paid_keyword_counterproofs.py)
    -> 167 passed
tsc --noEmit -p tsconfig.app.json      -> 76 erros
vitest run                             -> 1361 passed, 3 skipped, 2 failed
```

---

## Fechamento

| gate | resultado |
|---|---|
| `backend/tests` + `motor_pautas/testes` | **3787 passed, 112 skipped** em 115,64s |
| contraprovas da Camada 2 | **34 passed** |
| priors Webgo não-decisórios (por mutação) | **93 passed** |
| score do LLM sem autoridade | **36 passed** |
| rota de teses | **5 passed** |
| regressões de persistência | **6 passed** |
| achados da revisão adversarial | **12 passed** |
| vitest focal (`src/components/pautador-pro`) | **15 passed** |
| `vite build` | **ok, 9,03s** |
| `git diff --check` | **limpo** |
| scanner de segredos sobre o diff | **0 ocorrências** (3 casamentos textuais são a palavra "token" no sentido de design token) |
| scanner de paths privados | **0 arquivos** |
| scanner de IDs / raw do benchmark | **0 arquivos** |
| JSONs do pacote | **4 válidos** |
| arquivos do benchmark versionados | **0** |
| screenshots versionados | **0** (ficaram em diretório temporário) |

### Delta desta lane

```
pytest   3601 -> 3787   (+186)   skipped 112 -> 112 (inalterado)
vitest   1361 -> 1376   (+15)    skipped   3 ->   3
tsc        76 ->   76   (zero erro novo)
```

---

## TypeScript — baseline herdado versus regressão nova

**76 erros, idênticos com e sem a branch.** Medido nos dois sentidos: com a
árvore atual, e com `git stash` de todas as mudanças. Nenhum dos 76 está em
arquivo tocado por esta lane — verificado por `grep` sobre a lista de erros
com os nomes dos arquivos alterados.

---

## Vitest — classificação factual

### `DELTA_GREEN_WITH_2_INHERITED_FAILURES`

Esta lane **não** deixa a suíte Vitest verde, e não é honesto dizer que deixa.
O que é verdade:

- **Delta desta lane: +15 passed, 0 failed.** Os 15 são
  `src/components/pautador-pro/entity/__tests__/tese-e-comparador.test.tsx`.
- **2 testes falhavam antes e continuam falhando**, ambos no mesmo arquivo,
  sem relação com o Pautador:
  1. `src/components/settings/meta-capi/__tests__/wizard-smoke.test.tsx > MetaCapiWizard > com a function no ar, a etapa Edge Function sai da trilha`
  2. `src/components/settings/meta-capi/__tests__/wizard-smoke.test.tsx > MetaCapiWizard > salvar a etapa 1 leva ao próximo passo, sem zerar o formulário`

**Prova de que aparecem com e sem a branch** — o mesmo arquivo, rodado dos dois
lados:

```
COM a branch (HEAD)                       -> Tests  2 failed | 7 passed (9)
SEM a branch (src/ restaurado do SHA base) -> Tests  2 failed | 7 passed (9)
```

Além disso, 7 *arquivos* de teste falham na coleta, todos em
`src/components/trafego/**`, com a mesma raiz: `src/lib/supabase.ts:7` exige
variável de ambiente ausente no worktree. Também herdados, também medidos dos
dois lados.

### Variabilidade observada dos skips — registrada, não interpretada

Em execuções sucessivas do MESMO código, a contagem de `skipped` do Vitest
oscilou entre **3 e 5**. A primeira medição de baseline leu 5; a remedição do
mesmo baseline leu 3; o fechamento leu 3.

Não transformo isso em conclusão. Não investiguei a causa, não sei se é
concorrência, timing ou skip condicional, e a variação existe no baseline sem
nenhuma mudança minha. Fica registrado como observação, e o delta de `passed`
(+15) é estável nas duas leituras.

---

## Replay

`scripts/replay_pautador_oportunidade.py` — **1152 casos**, produto cartesiano
do espaço de observáveis cruzado com 6 estados de proveniência de sensor e
**dois lados do piso de N** (2 e 4 perguntas).

```
priors que influenciaram algo decisório .. 0
ausente que virou zero ................... 0
índice que divergiu do motor anterior .... 0
reprovado antes -> aprovado depois ....... 0
apto antes -> inadequado depois .......... 160
```

Os 160 são **uniformemente** `(n=4, todas as perguntas fechadas pelo canal
oficial, veto disparado)`. É a mudança deliberada de comportamento: o motor
anterior CONTAVA `oficial_fecha_sozinho` e jogava fora.

⚠️ A primeira versão do replay fixava n=2, abaixo do piso de 3, e reportava
`apto->inadequado: 0`. Aquele zero era artefato de um corpus que só exercitava
um lado da fronteira.

---

## Revisão independente

Ambas rodaram sobre a árvore **congelada** em `983f782`. Nenhum arquivo foi
alterado enquanto qualquer revisor lia.

| revisor | modelo | escopo | resultado |
|---|---|---|---|
| Codex | `gpt-5.6-sol`, reasoning `high`, sandbox `read-only` | worktree completo | 7 afirmações testadas: **4 sustentadas, 3 refutadas** + 6 achados adicionais |
| Gemini | `gemini-3.7-flash`, `temperature 0.2` | pacote sanitizado (código da lane; sem raw do benchmark, sem paths, sem URLs) | 11 achados, **2 P0** |

Uma rodada corretiva focal, commit `8b816d2`. Adjudicação completa no HANDOFF.

**Limitação declarada da revisão do Codex:** ele não conseguiu rodar as suítes
(sem venv no worktree; cache do Vitest sob sandbox read-only). Os probes dele
foram execuções isoladas de módulo. Reproduzi cada achado eu mesmo antes de
aceitar.

---

## Mutação externa

| alvo | resultado |
|---|---|
| Google Ads (mutate ou validate-only) | **nenhuma chamada** |
| WordPress | **nenhuma** |
| n8n | **nenhuma** |
| deploy | **nenhum** |
| migration | **nenhuma** |
| Roadmap / curadoria / grafo | **não tocados nesta branch** |
| Supabase | ver abaixo |

**Supabase, dito com precisão.** O Validador escreve no Supabase **por
desenho**, e já escrevia antes desta lane. `_gravar_parcial` aumentou a
frequência de escrita dentro de uma run que o operador dispara, com o mesmo
upsert idempotente. **Nenhuma escrita ocorreu nesta sessão**: o worktree não
tem Supabase configurado, e todos os testes usam espiões em memória.

A afirmação inicial da lane — "nenhum caminho desta missão causa mutação
externa" — era ampla demais. A revisão adversarial (Codex A7) apontou, e a
afirmação foi corrigida para o que é verdade.
