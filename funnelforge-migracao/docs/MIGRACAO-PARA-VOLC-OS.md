# O redator está pronto? — varredura de 15/08/2026

## Veredito

**Está pronto, e há prova de produção.** O funil FGTS que está no ar hoje saiu
deste engine.

```
run  antecipacao-saque-aniversario-fgts-20260721-115510   ·  21/07/2026
     7 páginas, todas OK ou RETRIED, todas publicadas
```

A prova é literal: os rótulos dos botões em `p1.elementor.json` daquele run —
*"Será que tenho direito ao saque? Ver"*, *"Como consultar o saldo atualizado"*,
*"Ver o passo a passo de liberação"* — são **exatamente** os que estavam na LP
2064 antes de eu trocá-los em 11/08. Não é semelhança: é o mesmo artefato.

E o report explica o que eu tinha estranhado na auditoria:

```
widget_p5   SKIPPED  [widget_rejected]   ← por isso P1 não tinha ferramenta
widget_p6   OK       5.829 tokens        ← o "Simulador de Rota"
widget_p7   OK       6.560 tokens        ← o "Termômetro de Prontidão"
```

## O que ele faz de ponta a ponta

```
funnelforge run briefings/<tema>.txt --publish

extract → research → write(+judge) → seo → image → screenshot → build → widget → publish
```

- **LP Elementor** no post type `r` → `/r/<slug>`. Escrita em duas fases porque o
  WordPress devolve 500 se `_elementor_data` for gravado no INSERT; template
  `elementor_canvas` e `hide_title` garantidos em toda publicação, com deleção da
  entrada órfã se a segunda escrita falhar.
- **Páginas `/rec`** em Gutenberg.
- **Widget interativo** por solução, injetado entre build e publish.
- **Screenshot do destino oficial** que o próprio redator citou, em webp,
  embutido depois do link correspondente.
- **Imagem destacada**, **Yoast**, **admanifest** de slots de anúncio.
- **Grafo validado duas vezes**, fail-closed.

```
520 testes passando · 26 runs no histórico · 7.326 linhas de src
```

## Cinco coisas antes de migrar

### 1 · Há trabalho não commitado, e é grande

```
32 arquivos · 2.008 inserções · 1.341 remoções
```

É o hardening de 11/08 (`docs/engine-hardening-2026-08-11.md`): `VerifiedFact`
tipado e fail-closed, contratos determinísticos de bloco por engajamento,
`cta_destination_mismatch`, proibição de `<p>` em `wp:html`, gate sobre o
artefato exato que vai ao REST.

**Migrar agora é migrar um estado que não existe no git.** Commitar primeiro, em
commits que contem a história — não um `wip`.

### 2 · O template da LP foi trocado e nunca rodou

`templates/lp.json` tem **1.253 linhas removidas** e um `lp.json.bak` ao lado. É
o template de dois heróis. **Nenhum run usou.**

### 3 · O grafo mudou de 3 hubs para 1 e nunca rodou assim

O run de produção usou **três** pré-sells (`pr1`, `pr2`, `pr3`) — foi exatamente
a arquitetura que a auditoria condenou. A config hoje é `presell_hubs=1` e
`lp_direct_solutions=2`, o desenho que validamos na mão.

**O engine nunca gerou um funil com o grafo novo.** Esse é o maior risco da
migração: mover para o sistema um motor cuja configuração atual nunca produziu um
funil inteiro.

### 4 · O sistema já tem OUTRO construtor de funil

```
backend/app/agents/funnel_pro/
    orchestrator.py   252   FunnelArchitect (Gemini) → PageFactory → writingJobs
    page_factory.py   118
    reviewer.py       220
```

Veio do fluxo n8n. **São dois motores para a mesma coisa.** Migrar sem decidir
qual vence cria dívida imediata: dois caminhos de geração, duas doutrinas, e a
próxima pessoa não sabe qual é o verdadeiro.

### 5 · O briefing tem dois formatos — e isso é uma oportunidade

```
VOLC-OS      BriefingModel (tipado) → DOCX
funnel-forge texto livre → step_extract (LLM) → FunnelPlan
```

O `BriefingModel` **já sabe** posição, papel, cabeçalho, slug, objetivo,
introdução, fechamento e links internos de cada página. Isso é praticamente o
`FunnelPlan`.

**Converter `BriefingModel` → `FunnelPlan` direto elimina o `step_extract`
inteiro** — uma chamada de LLM a menos, um ponto de falha a menos, e o plano
passa a ser aquilo que o humano aprovou no Pautador, não o que um modelo inferiu
de um texto.

## Compatibilidade: sem bloqueio

```
destino       Python 3.14.6   (backend/.venv)
funnel-forge  Python 3.13.0
```

Testei a instalação real das dependências no interpretador do destino:

```
litellm 1.96.2 · orjson 3.12.0 · jinja2 3.1.6 · tenacity 9.1.4 · typer 0.27.1
pillow e python-docx JÁ instalados
```

Todas resolvem no 3.14. `httpx` do destino está pinado em `0.28.1` e o forge pede
`>=0.27` — compatível. Sem colisão de nome se entrar como `app/funnelforge/`
(o destino tem `app/prompts.py`, o forge tem `funnelforge/prompts/` — namespaces
diferentes).

## Ordem que eu seguiria

```
1  commitar o hardening, com a história certa
2  RODAR um funil completo com presell_hubs=1 e o template novo,
   sem publicar, e conferir os artefatos            ← o teste que falta
3  decidir: funnel-forge OU agents/funnel_pro. Uma morre.
4  adaptador BriefingModel → FunnelPlan (mata o step_extract)
5  mover o pacote para app/funnelforge/ e ligar as deps
6  expor como rota/serviço no backend, com a trava de publish fechada
```

O passo 2 é o que não dá para pular. Tudo o que a auditoria de 11/08 corrigiu à
mão — hub único, botões coloridos por destino, widget sem `<p>`, CTA congruente —
está no engine em **código e teste**, mas nunca passou por um run inteiro junto.
Migrar antes disso é levar para o sistema um motor que a gente acredita que
funciona.
