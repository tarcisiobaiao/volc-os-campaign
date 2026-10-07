# HANDOFF — traffic-operating-cockpit-v2

**Veredito: `TRAFFIC_OPERATING_COCKPIT_V2_PARTIAL`.**

Não é aceite, e o motivo principal é simples: **as rotas reais nunca foram
abertas em navegador** (exigem sessão Supabase), e **a revisão Gemini não
aconteceu** (sem método de autenticação na máquina). O briefing exige as duas.

- Base: `origin/volc-os-v2` @ `207e91f1da290130e8d02b78c3ba1c8e9a761111` — conferido.
- Branch: `sprint/traffic-operating-cockpit-v2`
- Worktree: `/private/tmp/volc-traffic-operating-cockpit-v2` (isolada, árvore limpa)
- **Zero mutação externa.** Nenhuma chamada ao Google Ads, nenhum `validate_only`
  real, nenhuma escrita no Supabase oficial, nenhum n8n, nenhum deploy.
  `main` e `volc-os-v2` intocados.

## O que esta sprint descobriu, e que mudou o plano

O domínio de tráfego é **muito mais maduro** do que o briefing supõe. O contrato
de capacidade por canal já existe em Python — 4 portões × 4 estados com
bloqueadores nomeados —, já é servido em `GET /api/trafego/canais` e já tem
consumidor no Hub.

⚠️ Um handoff anterior afirmava que "a superfície visual dos quatro canais NÃO foi
construída". **É falso no SHA da base**, e foi adjudicado pelo código conforme a
ordem de fontes do AGENTS.md.

Por isso a sprint deixou de ser "construir do zero" e passou a ser **fazer a
inteligência existente aparecer, e parar de mentir onde mentia**.

## O que mudou

| # | Commit | Superfície |
|---|---|---|
| 1 | `abdee86` | Manifesto de PMax parou de negar código que existe |
| 2 | `b507ce3` | Um objeto do servidor, um tipo — manifesto duplicado colapsado |
| 3 | `852b487` | Aba **Criar** passa a mostrar o veredito, e a jornada real |
| 4 | `a2dade2` | Bancada visual dos estados obrigatórios, provada fora do bundle |
| 5 | `9edf59e` | Página canônica deixa de custar recarga do documento |
| 6 | `dbb853b` | Adjudicação da revisão adversarial — três promessas falsas removidas |

Detalhe por superfície em `BEFORE-AFTER.md`.

## As duas lições que valem mais que o código

**1. Uma prova que lê a FONTE prova o mecanismo, não o resultado.**
A prova de que a bancada de QA não ia para produção passava lendo `App.tsx` e
confirmando o guarda `import.meta.env.DEV`. O `vite build` de verdade mostrou
`assets/BancadaVisual-*.js` no bundle. O Rollup monta o grafo a partir de cada
`import()` **antes** da eliminação de código morto: guardar a rota elimina o ramo,
guardar o `React.lazy` elimina a chamada, e nenhum dos dois elimina o chunk.

**2. Um teste que fixa a redação de um erro passa a defender o erro.**
Três testes fixavam afirmações falsas: a palavra "exceção" na recusa de PMax,
`'Começar campanha'` para Display, e dois casos que percorriam uma coleção vazia
e passavam sem executar uma asserção.

## Revisões independentes

**Codex** (`codex-cli 0.151.0`, `model_reasoning_effort=high`, escopo
`207e91f1..HEAD`) devolveu **REPROVADO** com 2 achados que bloqueavam o aceite e
6 de severidade alta/média. Todos verificados no código antes de agir:

| lente | achado | desfecho |
|---|---|---|
| 1 | ativação prometia um degrau inexistente | **corrigido** |
| 2 | conversa recalculava elegibilidade no navegador | **corrigido** |
| 3 | stale colapsava em "não sei nada" | **corrigido** |
| 4 | CTA convidava Display para uma porta que monta Search | **corrigido** |
| 5a | gramática do frontend repetia a mentira de PMax | **corrigido** |
| 5b | curadoria e grafo não reconciliados | **não é defeito** — o AGENTS.md manda a lane paralela emitir delta; ver `CURATION-HANDOFF.json` |
| 6 | mutação externa acidental | sem achado |
| 7 | "Lendo…" mudo para leitor de tela | **corrigido** |
| 8 | mobile sem disclosure | **aceito, não corrigido** — `REMAINING-RISKS.md` §4 |
| 9 | texto essencial abaixo de 14px | **corrigido** |
| 10 | dois testes vacuamente verdadeiros + prova de bundle skipped | **corrigidos** |

**Gemini: NÃO RODOU.**
```
gemini 0.57.0 · gemini -m gemini-2.5-flash -p "<prompt>"
→ "Please set an Auth method in your ~/.gemini/settings.json or specify one of
   the following environment variables: GEMINI_API_KEY, GOOGLE_GENAI_USE_VERTEXAI,
   GOOGLE_GENAI_USE_GCA"
```
Não foi substituído por outro modelo e nenhuma resposta foi inventada.

**Fable: não usado.** Nenhuma ambiguidade estrutural sobrou que Claude e Codex
não tenham adjudicado pelo código.

## Gates

`tsc` idêntico ao baseline herdado (comparação por `diff` de conjunto, não por
contagem) · vitest **1513 passed, 6 skipped** (eram 1481/5) · pytest das suítes
tocadas **99 passed** · gate de bundle **verde, e provado que falha** · 104
capturas com **0 overflow, 0 erro de console, 0 alvo < 40px**.

⚠️ Uma falha de pytest é **herdada** e reproduz na árvore intocada:
`test_provar_sem_copy_reprova_e_diz_por_que`. Detalhe em `GATES.md`.

## Para quem pega isto agora

1. Leia `REMAINING-RISKS.md` primeiro. Ele diz o que **não** foi feito.
2. O próximo ato mais barato: abrir
   `http://127.0.0.1:8091/trafego?aba=criar` com sessão real e conferir a aba
   Criar com dado do servidor. O ambiente sobe conforme `GATES.md`.
3. O próximo ato de maior valor: **M1** — serializar `bloqueado`/`bloqueios` em
   `projecao.cockpit` (duas linhas), tirando a decisão de gasto do navegador.
4. `CURATION-HANDOFF.json` tem o delta de curadoria. **Não foi aplicado**, e não
   deve ser aplicado por quem não está integrando.

## Artefatos

`AUDIT-BEFORE.md` · `UX-ARCHITECTURE.md` · `CHANNEL-CAPABILITY-MATRIX.json`
(gerado chamando o contrato Python direto, em 4 perfis de sessão) ·
`STATE-MATRIX.json` · `MOTION-MAP.md` · `BEFORE-AFTER.md` · `VISUAL-QA.md` ·
`SCREENSHOT-MANIFEST.json` · `CONTRAPROVAS.md` · `GATES.md` ·
`REMAINING-RISKS.md` · `CURATION-HANDOFF.json`
