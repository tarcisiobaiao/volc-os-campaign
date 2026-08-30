# funnelforge — o motor que escreve e publica o funil

Pacote de migração, empacotado em **15/08/2026**. Este é o motor que gera funis
de arbitragem inteiros e publica no WordPress: landing page em Elementor,
páginas de solução em Gutenberg, widget interativo, screenshot do destino
oficial, SEO e slots de anúncio.

Está aqui como **área de preparo**, fora de `backend/`, para você ligar no
sistema no seu ritmo. Nada foi integrado ainda.

```
funnelforge-migracao/
├── engine/          o motor (código, testes, prompts, templates, config)
├── referencia/      o funil que ele já gerou e está no ar, para comparar
└── docs/            estado, hardening e ordem de migração
```

---

## Ele funciona — e há prova de produção

O funil de FGTS que está no ar em `creditoup.com.br` **saiu deste motor**.

```
run  antecipacao-saque-aniversario-fgts-20260721-115510   ·  21/07/2026
     7 páginas · todas publicadas
```

A prova está em `referencia/run-fgts-producao/p1.elementor.json`: os rótulos dos
botões daquele run — *"Será que tenho direito ao saque? Ver"*, *"Como consultar
o saldo atualizado"*, *"Ver o passo a passo de liberação"* — são **exatamente**
os que estavam na LP em produção. Não é parecido: é o mesmo artefato.

```
520 testes passando · 36 módulos · 7.326 linhas de código-fonte
```

---

## O que o motor faz, de ponta a ponta

```
funnelforge run briefings/<tema>.txt --publish

extract → research → write(+judge) → seo → image → screenshot → build → widget → publish
```

| Etapa | O que entrega |
|---|---|
| `extract` | briefing em texto → `FunnelPlan` tipado (páginas, papéis, slugs, keywords) |
| `research` | fatos com procedência — `VerifiedFact` exige valor, unidade, fonte HTTPS, dispositivo, vigência e data de verificação. **Fail-closed**: sem fonte, a etapa falha e o redator não roda |
| `write` + `judge` | o texto, com um segundo modelo julgando |
| `seo` | título, meta e focus keyword do Yoast |
| `image` | imagem destacada gerada |
| `screenshot` | print do destino oficial que o próprio texto citou, em webp |
| `build` | Elementor JSON (LP) ou blocos Gutenberg (interiores) |
| `widget` | a ferramenta interativa da página de solução |
| `publish` | grava no WordPress via REST |

**A LP vai para o post type `r`** (`/r/<slug>`), em Elementor, com escrita em duas
fases: o WordPress devolve 500 se `_elementor_data` for gravado no INSERT, então
cria vazio, grava as settings e só então os dados — e apaga a entrada órfã se a
segunda escrita falhar. Template `elementor_canvas` e `hide_title` garantidos em
toda publicação.

**As demais vão para `rec`** (`/rec/<slug>`), em Gutenberg puro.

O **grafo do funil é validado duas vezes** — uma sobre o plano inicial e outra
sobre o plano final — e falha fechado: solução órfã, página terminal sem saída ou
link cru derrubam a publicação.

---

## O que tem em cada pasta

### `engine/`

O pacote Python. `src/funnelforge/` com adapters (WordPress, Elementor, LiteLLM,
Perplexity, Playwright, Pillow), o pipeline com os nove passos, os validadores,
o registro de frases e os treze prompts Jinja.

```bash
cd engine
python -m venv .venv && .venv/bin/pip install -e '.[dev,screenshots]'
.venv/bin/playwright install chromium      # só se for usar screenshot
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Configuração em `config.yaml` (modelos por etapa, validadores, grafo, site) e
segredos em `.env` — que **já veio preenchido** com as chaves que estavam em uso,
e está coberto pelo `.gitignore` do próprio engine, então não entra em commit.

### `referencia/`

| Pasta | O que é |
|---|---|
| `run-fgts-producao/` | os 69 artefatos do run que gerou o funil no ar: plano, Elementor JSON, HTML de cada página, prompts renderizados, log e relatório |
| `funil-no-ar/` | as 7 páginas como estavam publicadas, com prosa limpa, widgets isolados e o inventário do que estava errado |
| `refatoracao-11-08/` | o que foi reescrito à mão em 11/08: base factual com fonte primária, os três widgets refeitos, `blocos.py` com o validador, e o mapa de botões da LP |
| `hardening-wordpress/` | o MU-plugin que blinda o tema (o filtro que apagava `<p>` vazio e levava o `id` junto), o CSS e o runbook |

### `docs/`

- **`MIGRACAO-PARA-VOLC-OS.md`** — leia primeiro. O diagnóstico completo e a
  ordem de migração.
- **`ESTADO-DO-ENGINE.md`** — o mapa do motor por arquivo.
- **`engine-hardening-2026-08-11.md`** — o contrato factual e os gates que
  entraram depois da auditoria.

---

## O que ainda não foi feito

Três coisas, em ordem de risco.

**1 · O motor nunca gerou um funil com o grafo atual.** O run de produção usou
**três** pré-sells (`pr1`, `pr2`, `pr3`) — a arquitetura que a auditoria
condenou, porque mais de 80% dos cliques vão no primeiro botão e os outros dois
destinos eram paráfrases. A configuração hoje é `presell_hubs: 1` e
`lp_direct_solutions: 2`, o desenho corrigido. **Isso está em código e teste, mas
nunca passou por um run inteiro.**

**2 · O template da LP foi trocado e nunca rodou.** `templates/lp.json` é o
template de dois heróis (mobile e desktop), e o anterior está ao lado como
`.bak`.

**3 · O sistema já tem outro construtor de funil.** `backend/app/agents/funnel_pro/`
faz architect → page factory → writingJobs, vindo do n8n. São dois motores para a
mesma coisa, e um precisa morrer antes de a integração começar — senão a próxima
pessoa não sabe qual é o verdadeiro.

---

## Uma oportunidade que apareceu na varredura

O `BriefingModel` de `backend/app/docx/briefing_model.py` já carrega, por página:
posição, papel, cabeçalho, slug, objetivo, introdução, fechamento e links
internos. **Isso é praticamente o `FunnelPlan` do motor.**

Converter `BriefingModel → FunnelPlan` direto **elimina a etapa `extract`
inteira**: uma chamada de LLM a menos, um ponto de falha a menos, e o plano passa
a ser exatamente o que foi aprovado no Pautador — não o que um modelo inferiu de
um texto livre.

---

## Compatibilidade

Testada contra o interpretador do backend.

```
backend/.venv   Python 3.14.6
engine          Python 3.13 (desenvolvido), roda no 3.14
```

Todas as dependências resolvem no 3.14: `litellm 1.96.2`, `orjson 3.12.0`,
`jinja2 3.1.6`, `tenacity 9.1.4`, `typer 0.27.1`. `pillow` e `python-docx` já
estão instalados no backend. O `httpx` pinado em `0.28.1` atende o `>=0.27` que o
motor pede.

Sem colisão de nomes: o backend tem `app/prompts.py`, o motor tem
`funnelforge/prompts/` — namespaces diferentes. Entrando como `app/funnelforge/`,
não há conflito.

---

## Ordem sugerida

```
1  commitar o motor como está (há trabalho de hardening ainda sem commit)
2  rodar um funil completo com presell_hubs=1, SEM publicar, e conferir
3  decidir entre funnelforge e agents/funnel_pro — um dos dois sai
4  adaptador BriefingModel → FunnelPlan (mata o step extract)
5  mover engine/src/funnelforge para backend/app/funnelforge
6  expor como rota do backend, com publish travado em draft
```

O passo 2 é o que não dá para pular. Tudo que a auditoria corrigiu à mão — hub
único, cor de botão por destino, widget sem `<p>`, CTA congruente com o destino,
fato com fonte — está no motor. Falta ver os cinco juntos, num funil inteiro,
antes de ele virar parte do sistema.
