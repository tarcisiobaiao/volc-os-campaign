# Harness V3 — Mission Compiler, Evidence Ledger e Recovery Ratchet

*Base `297757a` · branch `feat/harness-v3-mission-compiler-ratchet`*

## O problema, medido

Nove execuções na rodada anterior. **Cinco falharam por especificação ou
coordenação, zero por infraestrutura.** O harness gastou writers caros para
descobrir defeitos que um compilador teria recusado em milissegundos.

| Incidente | Custo | O que teria evitado |
|---|---|---|
| B3: gate apontava para teste inexistente | **39 min de writer** | `--collect-only` no preflight |
| A1: ownership ignorou `volc_ads/campanha/` | 1 writer | descoberta de call sites |
| A2: `projecao.py` serializa o selo e ficou fora | 1 writer | idem |
| B1/B2: nomes de arquivo prescritos sem serem obrigatórios | 2 writers | `produced_paths` declarados |
| A3: 403 virou 409 num aceite já provado | 1 writer + revisão | regression gate de precedência |
| B4: colheita pronta, faltava só o gate certo | validação manual | modo validation-only |

## A tese

> Uma missão declarativa não pode chegar ao writer. Ela precisa **compilar**.

Compilar significa: provar que os gates são executáveis, que o ownership cobre os
call sites reais, que os aceites existem, e que os comportamentos já provados
continuam verdes — **tudo antes de chamar o primeiro modelo.**

## Pipeline

```text
mission source → schema → base/lineage → ownership discovery
  → gate compilation → baseline preflight → compiled mission → writer
```

Nenhum modelo é chamado enquanto a missão não compilar.

## As dez camadas

| # | Camada | Responsabilidade |
|---|---|---|
| 1 | **Mission Compiler** | orquestra o pipeline, emite `compiled-mission.json` |
| 2 | **Acceptance IDs** | aceite atômico; já provado vira regressão obrigatória |
| 3 | **Ownership Discovery** | call sites reais, não inferência por nome |
| 4 | **Gate Compiler** | gate só existe se for executável; emite `gate-plan.json` |
| 5 | **Baseline Ratchet** | comportamento provado tem precedência sobre novo |
| 6 | **Evidence Ledger** | prova válida não se repete; digest governa |
| 7 | **Typed Failure Classifier** | nove classes; cada uma com destino próprio |
| 8 | **Harvest & Resume** | colheita é ponto de partida, não lixo |
| 9 | **Reviewer Adjudication** | contraprova executável vence checklist |
| 10 | **Worktree Registry** | um writer por worktree, transacional |

## Precedência de evidência

```
contraprova executável > teste de propriedade > evidência file:line
  > revisão sem execução > aprovação por checklist
```

Gemini aprova e Sol produz contraprova executável ⇒ **CORRIGIR**.

## Classes de falha e destino

| Classe | Destino | Writer relançado? |
|---|---|---|
| `SPEC_ERROR` | compiler | **não** |
| `OWNERSHIP_ERROR` | ownership discovery | **não** |
| `INFRASTRUCTURE_ERROR` | gatekeeper | **não** |
| `BASELINE_ERROR` | reconciliação | **não** |
| `MERIT_FAILURE` | mesmo writer ou colheita | sim, ≤2 |
| `REVIEW_FINDING` | exige contraprova | sim, ≤2 |
| `TIMEOUT` | inspeção | sim, ≤1 |
| `TRANSIENT_PROVIDER_ERROR` | retry | sim, ≤1 |
| `AUTHORIZATION_BLOCK` | humano | **nunca** |

`exit 4` do pytest é `SPEC_ERROR`, jamais `MERIT_FAILURE`. Foi a confusão que
custou 39 minutos na B3.

## Reuso de evidência

Uma prova é reutilizável somente se **todos** os inputs materiais mantiverem o
digest. Estados: `REUSED_WITH_VALID_DIGEST`, `REEXECUTED_INPUT_CHANGED`,
`INVALIDATED`, `NEW_EVIDENCE`.

Nunca reutilizáveis, por definição: gate final de integração, scanner de segredo,
diff-check, prova de árvore limpa, equivalência material, build final.

## Privacidade

Nenhum agente recebe `.env`, segredo, arquivo não rastreado, dado de produção,
credencial, token ou workflow n8n bruto. Provider só vê `allowed_paths`. DeepSeek
só recebe spans sanitizados. Nenhum valor de segredo é logado, contado ou
persistido.

## Escopo desta missão

Somente `tools/agent-harness/**`, docs do harness e testes do próprio harness.
Nenhuma tarefa funcional é executada; o smoke usa adapters stubados.
