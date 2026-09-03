# HANDOFF — Pautador · validação psicológica V2

Base `origin/volc-os-v2 @ b2af81f0a2018626c5d873574664991b16f7ce38`
Branch `sprint/pautador-psychological-validation-v2`

---

## 1 · O que a missão assumia, e o que era verdade

A missão pedia para corrigir um motor que pediria "uma nota psicológica" ao
LLM. **No caminho da validação isso já estava certo antes de eu chegar.**
`motor_pautas/prompts/ficha_de_resposta.md` proíbe o rótulo explicitamente
— *"Você não classifica nada"* — com justificativa medida: a versão com rótulo
ordinal teve **67% de estabilidade** entre execuções idênticas.

`motor_pautas/DECISOES.md` é um registro de refutações com números: oito ideias
plausíveis testadas e mortas, incluindo a regressão ajustada em lucro (o
`spend` sozinho previa o alvo com **AUC 0,971** — viés de seleção).

O defeito que a missão descreve **existe**, mas a montante, na **descoberta** —
e a prova de que ele não alcança esta lane está no item 5.

---

## 2 · O que faltava de verdade

Existia a **Camada 1** (medição: oito eixos com proveniência) e a **Camada 3**
(`paid_eligibility`, com fronteira já testada). Não existia a camada do meio:
nada respondia **"vale aprofundar, e por quê?"**, nada recomendava formato de
funil citando o observável que o gerou, nada propunha o próximo experimento, e
não havia comparação entre oportunidades.

`app/validacao/oportunidade.py` é essa camada. Ela **lê** o resumo que o
Validador já gravou e **nunca recalcula a medição** — a mesma regra que
`OpportunityEditorialDecision.do_resumo` já aplicava do lado pago.

Não é um score. É um vocabulário fechado de sete decisões mais **três conjuntos
disjuntos** — fatos, hipóteses, desconhecidos — porque o que falta ao operador
não é ordenar melhor, é saber **de que tipo** é cada coisa que ele lê.

---

## 3 · Defeitos reproduzidos no motor anterior

Todos verificados por execução, não por leitura de comentário.

| # | defeito | prova |
|---|---|---|
| D1 | a gravação **não** era incremental e dois docstrings afirmavam que era; o front sondava uma tabela vazia a cada 1,5s e chamava isso de progresso | `_gravar_eixos` tinha 2 call sites, ambos após toda a medição |
| D2 | revalidar gravava `ficha/tensao/portao: null` por cima de 3 passadas de LLM já pagas | cadeia `_marcar_ja_medidos` → `_passo_ficha` early-return → `_gravar_resumo` substitui a coluna |
| D3 | o selo de medição **nunca** aparecia no card do Kanban | hook grava `"42"`, board lê `"ent-42"`; era o único dos 19 sites fora da convenção |
| D4 | `economia` mistura demanda, economia e canal: **baixar o volume de busca faz o motor dizer "o mercado não paga"** | com demanda humana idêntica: `alvo` 0,767 → `audiencia_pobre` 0,553 |
| D5 | o board ordena por um `score` que pode ter vindo do LLM, em 4 faixas **por cor de texto**, com significado em `title` | `EntityKanbanBoard.tsx:280` |

D1, D2 e D3 foram corrigidos. D4 e D5 estão declarados em LIMITATIONS: ambos
exigem mexer fora do escopo ou remedir a base.

---

## 4 · O benchmark deu resultado NEGATIVO, e isso foi o mais útil

Verificado rodando os dados, não relatado:

- **46 pares de controle, só 10 de vencedora**; 78,3% são de perdedora e
  deterioração, e servem de comparador único das vencedoras.
- Um script do run intersecta com literal vazio (`& set()`): o `0` publicado é
  artefato de código.
- **O sinal de canal não é identificável** — a direção inverte conforme a
  janela de lucro: SEARCH abaixo de DISPLAY em 90d (28,1% vs 33,0%), acima em
  180d e all. Uma escolha do analista determina a resposta.
- **Estrutura de página não discrimina**: medianas 894/927/902 palavras,
  6/6/6 CTAs, 1/1/1 formulários; **14 de 18 domínios servem mais de um grupo**.

**Correção minha:** minha primeira leitura da densidade de anúncio usou
*mediana* (5/5/8) e concluiu que não discriminava. A mediana escondia a cauda.
Por proporção o gradiente é real e monotônico (**14,8% / 38,9% / 68,4%**) — eu
estava errado e o investigador estava certo. Mesmo assim não vira peso: n
agrupado em ~18 domínios, medida de DOM do estado atual contra desfecho de
90-180 dias, e é monetização **paga**.

O uso mais valioso do benchmark foi **negativo**: ele decidiu o que **não**
entra. `OBSERVAVEIS_ACEITOS` exclui hero, CTA, selo, layout, template, design e
cor porque o corpus provou que isso é template.

Os quatro priors entram com `pode_decidir: False`, provado por **mutação** —
93 testes, 8 formas de adulteração (tabela vazia, confiança toda alta,
`pode_decidir=True`, afirmação invertida, peso numérico, replicada 7×, uma só,
lixo) × 9 casos, mais ranking e escolha do topo.

---

## 5 · O score do LLM: adjudicação

**NÃO ALCANÇÁVEL.** A missão autorizava ampliar ownership para
`entities/prompts.py` e `entities/scoring.py` **se** eles alcançassem a
validação/ranking desta lane. Não alcançam, provado em três pernas
(`test_llm_score_sem_autoridade.py`, 36 testes):

| perna | prova |
|---|---|
| valor | 17 scores arbitrários (`None`, `inf`, string, dict, `999999`) → tese byte-idêntica; 13 campos ordinais da descoberta idem; `score=999999` não reordena |
| transporte | a rota não seleciona `score`; e ignora mesmo se o banco devolver |
| código | AST: `score` não aparece como literal, atributo ou nome; nenhum import de `app.entities` |

**Portanto o ownership NÃO foi ampliado.** Os dois arquivos não foram tocados.
A dívida está registrada como `DIVIDA-DESCOBERTA-SCORE`, com um teste que falha
se alguém apagar o registro sem consertar a descoberta.

---

## 6 · Revisão independente — adjudicação de cada achado

Árvore congelada em `983f782`. Nenhum arquivo alterado enquanto liam.
**Codex refutou 3 das 7 afirmações da lane.**

| id | achado | veredito | ação |
|---|---|---|---|
| Codex A2 | booleano ausente virava `False` e o motor afirmava `oficial_fecha_sozinho em 0 de 3` como FATO; `bool("false") is True` | **CONFIRMADO** | `_bool_observado` → True/False/None; denominador é quem observou |
| Gemini P0 | abaixo do piso o veto deixava passar `aprofundar`, contra o que meu próprio comentário prometia | **CONFIRMADO** | roteador sempre veta quando tudo fecha; `_decidir` lê o piso |
| Gemini P0 | falha de leitura renderizava como "Cabe numa página · Considerar artigo único" | **CONFIRMADO** | novo estado `FALHA_NA_LEITURA` |
| Codex P1 | `cobertura=None` escapava da retenção | **CONFIRMADO** | desconhecido é o caso de retenção mais forte |
| Codex P1 | empate entre homônimos não determinístico | **CONFIRMADO** | `order=id.asc` + `opportunity_id` no desempate |
| Codex P1 | um resumo malformado derrubava o lote inteiro | **CONFIRMADO** | isolamento por card |
| Gemini P1 | instabilidade entre passadas classificada como hipótese "de fora" | **CONFIRMADO** | virou contradição |
| Gemini P2 | o experimento afirmava "o mais barato" a partir de ordem alfabética | **CONFIRMADO** | frase corrigida; lista todos os buracos |
| Codex A5 | presença de `cpc` move `densidade` e portanto o índice | **CONFIRMADO E DELIMITADO** | só quando a SERP não tem domínio comercial; só a presença, nunca o valor; **pré-existente** — congelado em teste, declarado |
| Codex A7 | "zero mutação externa" era afirmação ampla demais | **CONFIRMADO COMO ERRO MEU** | afirmação reescrita (ver GATES) |
| Codex A1/A3/A4/A6 | não-recálculo, priors, score, determinismo | **SUSTENTADAS** | — |
| Gemini P2 | `GUIA` nunca alcança `aprofundar` | **CONFIRMADO como assimetria não documentada** | documentado; não alterado |

**Dois dos meus testes passavam vacuamente**, e os revisores acharam:

1. `test_abaixo_do_piso...` usava `ramos=1/condicoes=0` e nunca chegava ao ramo
   que dizia proteger.
2. o "empate" do replay usava cards `sem_validacao`, fora do ranking, com temas
   diferentes.

E eu mesmo encontrei um terceiro antes deles: o probe de contraste media um DOM
vazio e reportava `0 medidos, 0 abaixo do piso` — aprovação de nada.

---

## 7 · Replay

**1152 casos**, produto cartesiano do espaço de observáveis × 6 estados de
proveniência × dois lados do piso de N.

```
priors que influenciaram algo decisório .. 0
ausente que virou zero ................... 0
índice que divergiu do motor anterior .... 0
reprovado antes -> aprovado depois ....... 0
apto antes -> inadequado depois .......... 160
```

Os 160 são uniformemente `(n=4, todas as perguntas fechadas pelo canal oficial,
veto disparado)` — a mudança deliberada: o motor anterior contava
`oficial_fecha_sozinho` e jogava fora.

⚠️ A primeira versão do replay fixava n=2, **abaixo** do piso, e reportava
`apto->inadequado: 0`. Aquele zero era artefato do corpus.

---

## 8 · Interface

Recibo reproduzível em UX-READOUT. Números medidos, não opinados:

```
viewport=1430  scrollWidth=1430  body_rola_horizontal=false
elementos_fora_de_scroller_que_estouram=0
contraste: 208 medidos, 0 abaixo do piso WCAG
```

O probe errou **três vezes** antes de ser confiável (timing do React →
media DOM vazio; sem composição de alfa → 26 reprovações falsas; correto → 50
reprovações **reais**, minhas). Cada correção deixou o gate mais rigoroso.
Progressão **50 → 5 → 0**.

---

## 9 · Estados de aceite

| estado | veredito |
|---|---|
| `PSYCHOLOGICAL_VALIDATION_LAYER_ACCEPTED` | ✅ |
| `WEBGO_PRIORS_NON_DECISIONAL_PROVEN` | ✅ |
| `LLM_SCORE_HAS_ZERO_DECISION_AUTHORITY` | ✅ |
| `VALIDATION_UI_ACCEPTED` | ⚠️ **PARCIAL** |

`VALIDATION_UI_ACCEPTED` fica **parcial**, e o motivo é honesto: o fluxo real
de arrastar o card não foi exercitado ponta a ponta, porque a página exige o
Supabase oficial, que esta missão está proibida de tocar. O que foi exercitado
está em vitest, nos testes de rota e no recibo de navegador com componentes
reais. Tema escuro não foi medido; leitor de tela real não foi testado.

---

## 10 · O que fica de dívida

Detalhe em LIMITATIONS. Em uma linha cada:

1. **CPC → densidade → índice**: acoplamento pré-existente, delimitado e
   congelado em teste. Corrigir exige remedir a base.
2. **DIVIDA-DESCOBERTA-SCORE**: a descoberta ensina a fórmula ao LLM e confia
   no score dele. Provado não-alcançável; fora do ownership.
3. **Nondeterminismo**: `temperature: 0.9` fixa, sem seed, sem JSON Schema.
   `refazer=True` não é determinístico.
4. **Custo do LLM** fora da contabilidade.
5. **~800 linhas de prompt morto** e as funções sem chamador de `portao.py`.
6. **`psique.ler`** infla na ambiguidade (82/91) — vive no grafo, proibido aqui.
