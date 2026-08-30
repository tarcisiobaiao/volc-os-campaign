# funnel-forge

Um gerador de funis de arbitragem em **arquitetura limpa** (Python 3.11+): de
um briefing (`.docx`/`.txt`) sai um funil completo — **1 landing page
Elementor** + **1 pré-sell** + **N páginas de solução** em Gutenberg — cada
uma pesquisada, redigida, julgada por qualidade, com SEO (Yoast) e imagens,
publicada como **rascunho** no WordPress pronta pra revisar.

> Um "run" = um briefing → um funil inteiro no WordPress. Determinístico onde
> importa (roteamento, template, compliance), criativo onde agrega (copy,
> imagem, SEO).

---

## O funil vencedor (taxonomia + interlinks)

O tipo de cada página é derivado do **sufixo do slug** (`domain.models.derive_role`):

| Papel | Slug | Prompt | Formato |
|---|---|---|---|
| **LP** (landing) | sem sufixo | `redator_p1` (JSON) | Template Elementor (`templates/lp.json`) → post type `r`, rende em `/r/<slug>` |
| **PRESELL** (hub) | `-pr` | `redator_presell` | Gutenberg → post type `rec` |
| **SOLUTION** | `-p1` … `-pN` | `redator_pages` | Gutenberg → post type `rec` |

O grafo de CTAs (tipado, sem loop — `pipeline/routing.py`):

```
LP ──► presell (-pr)        botão 1   ← ~80% dos cliques
   ├─► p1                   botão 2
   └─► p2                   botão 3

presell ──► p1 · p2 · p3    fan-out completo (cada H2 prevê uma solução)
p1      ──► p2 · p3 + oficial
p2      ──► p3 + oficial
p3      ──► cross-funnel    terminal recircula
```

- **LP → 1 presell + as `lp_direct_solutions` primeiras soluções.** Medido em
  campo, **mais de 80% dos cliques da LP vão para o primeiro botão** — então
  ele leva ao hub qualificador, e os demais cortam caminho direto para a
  solução. `run.presell_hubs: 3` restaura o desenho antigo (três hubs clonados
  com rotação neutra); o caminho continua no código e testado.
- **presell → FAN-OUT**: 1 CTA por solução. É o hub que garante alcançabilidade
  das soluções que não ganharam botão direto na LP.
- **SOLUTION → FORWARD-ONLY**: fan-out para **todas as soluções de ordinal
  maior** (`p_i → {p_i+1..p_n}`) **+ 1 saída oficial externa**
  (`external_official`, allow-list). Nunca aresta para trás — aciclicidade por
  construção, não por verificação.
- **Solução terminal** para de avançar e recircula **cross-funnel** — uma URL
  **real** do `post-sitemap.xml` do site, "relacionada mas diversa" (nunca um
  slug inventado; `adapters/sitemap_http.py`).

`pipeline/taxonomy.py` guarda o contrato de referência e roda um *advisory*
não-bloqueante contra o grafo montado (fan-out completo, terminal com saída,
sem self-loop). `validate_funnel_graph` fecha o gate (páginas órfãs / terminal
sem saída bloqueiam build+publish).

---

## Otimizações que o runner aplica (v1.0)

**Landing page (Elementor):**
- Clona um template fixo de designer e só repopula conteúdo/imagem/hrefs —
  design 100% preservado (sem LLM re-serializando 30KB de JSON).
- **Canvas layout + "ocultar título"** garantidos (`template=elementor_canvas`,
  `_elementor_page_settings.hide_title=yes`).
- **Hero vertical 9:16** (imagem própria, prompt com gradiente preto nos 40%
  inferiores p/ o título/botões sobreporem — `image_prompt_lp.jinja`).
- Subtítulo com tamanho de fonte explícito; **botões de largura total**;
  **H2 em negrito (700)**; enumerações `1) 2) 3)` → **emojis 1️⃣ 2️⃣ 3️⃣**;
  parágrafos quebrados + `<strong>/<em>` (mobile-first).

**Páginas /rec (Gutenberg):**
- Cota de **variedade de blocos** (tabela / colunas / pullquote obrigatórios,
  FAQ limitado) — `blocks_gutenberg.jinja`.
- **Imagem de destaque** (featured_media) + **imagem no meio do texto**
  (espaçada, AdSense-safe) — fluxo estilo n8n.
- **Prints das páginas oficiais** (opt-in `official_screenshots`): um adapter
  Playwright/Chromium captura cada `official_link` da página de solução
  (viewport mobile, acima da dobra), recorta determinístico, comprime pra webp
  e no publish insere logo após o parágrafo do link, com legenda de reprodução
  — best-effort, **nunca derruba a página** (v2: recorte por visão/OCR).
- **Distribuição de CTAs em rodízio** pela malha (irmãs + cross-funnel), sem
  concentrar num destino só; terminal favorece o cross-funnel.
- **Aviso de compliance** movido pro fim como **rodapé discreto** (itálico,
  fonte menor), não banner no topo.
- Sem divisor bugado entre botões; parágrafos curtos + negrito/itálico.
- Guarda de **tamanho mínimo** (`interior_min_length`): página truncada
  re-tenta em vez de publicar em branco.

**Compliance / doutrina** (`pipeline/doctrine.py`, fonte única):
- Proíbe medo/escassez fabricada, falsa oficialidade e verbo de execução de
  serviço nos CTAs (matching por `\b`, sem falso-positivo em "demitido").
- Ano corrente injetado nos prompts (nunca cita anos passados).
- Guarda de unicidade (Jaccard boilerplate-aware) entre páginas do mesmo run.

**SEO (Yoast):** título + meta description + focus keyword preenchidos por
página (`set_yoast` mapeia pras chaves `_yoast_wpseo_*`). **Requer registro
dos meta no site** — veja *Setup do WordPress* abaixo.

**Publicação:** sobe como **rascunho** (`run.publish_status`), com um
`set_status` como escrita final garantindo o status pretendido.

---

## Setup do WordPress (pré-requisitos do site)

1. **Post types**: `rec` (posts interiores) e `r` (LP Elementor, rende em
   `/r/<slug>`), ambos REST-enabled. Ajuste em `config.yaml` (`site.post_type`,
   `site.lp_post_type`) se seus slugs forem outros.
2. **Elementor** ativo (a LP entra como template Elementor).
3. **Yoast SEO** ativo **+ os meta expostos ao REST**. Por padrão o Yoast NÃO
   deixa escrever `_yoast_wpseo_*` via REST — rode o snippet
   [`docs/yoast-rest-meta.php`](docs/yoast-rest-meta.php) (mu-plugin, Code
   Snippets ou functions.php). Sem ele, a escrita de SEO é ignorada em silêncio.
4. **Application Password** do WordPress (usuário com permissão de editar/
   publicar), no `.env`.

---

## Install

```bash
cd funnel-forge
pip install -e ".[dev]"        # editable + pytest/pytest-mock/ruff
```

Python >= 3.11.

**Prints oficiais (opcional)** — só se você for ligar `run.official_screenshots`:

```bash
pip install -e ".[screenshots]"   # adiciona playwright
playwright install chromium       # baixa o browser headless
```

Sem esse extra (ou com a flag desligada) o pipeline roda exatamente como antes:
`step_screenshot` vira no-op e nada quebra.

## Configure

Dois arquivos, lidos do diretório atual:

**`.env`** (segredos — nunca commitado):

```bash
cp .env.example .env
```
```
OPENAI_API_KEY=        # imagens (gpt-image) + steps em gpt-4.1
GEMINI_API_KEY=        # redatores + pesquisa (web-search)
PERPLEXITY_API_KEY=    # (opcional) research adapter alternativo
WP_URL=https://seusite.com
WP_USER=
WP_APP_TOKEN=
```

Cada credencial é opcional na fiação (`cli.build_deps` só liga o adapter que
tem chave): sem `WP_*` o run fica local (`runs/`), sem `OPENAI_API_KEY` a
imagem não é gerada (o *prompt* ainda sai).

**`config.yaml`** — comportamento do run, site, taxonomia de rotas (`routing`),
ads, index e **modelo por step** (`steps`). Trocar de modelo é só editar
`steps.<nome>.model`/`fallbacks` — nada no código muda (`litellm` resolve
`gpt-*`, `gemini/*`, `claude-*`, `perplexity/*`). Rode `funnelforge models`
pra ver a config atual. Flags principais em `run`:

```yaml
run:
  publish_status: draft    # funil sobe como rascunho
  hero_image: true         # LP: gera hero vertical
  featured_image: true     # /rec: featured_media + imagem no meio
  official_screenshots: false   # /rec SOLUTION: prints reais das oficiais (requer extra .[screenshots])
  screenshots_max_per_page: 2   # cap de prints por página (sobre os official_links)
```

## Comandos

```bash
funnelforge run briefing.docx            # roda local (runs/<run_id>/), não publica
funnelforge run briefing.docx --publish  # publica cada página no WordPress (rascunho)
funnelforge run briefing.docx --only p1  # só a landing page
funnelforge resume <run_id>              # retoma um run checkpointado
funnelforge models                       # imprime modelo+fallbacks de cada step
```

`<run_id>` = slug da LP (ex.: `serasa-limpa-nome-2026`). O `state.json` é
gravado a cada step (write-then-rename atômico), então um run interrompido
sempre dá pra retomar sem refazer o que já ficou `OK`.

## Arquitetura (clean architecture)

- **`domain/`** — modelos Pydantic puros (`FunnelPlan`, `Page`, `RunState`…),
  sem I/O. `derive_role`/`resolve_route` (taxonomia + same-domain law).
- **`ports/`** — interfaces (`LLMClient`, `ResearchProvider`, `ImageGenerator`,
  `ImageProcessor`, `Publisher`, `SitemapProvider`, `ScreenshotProvider`,
  `BriefingLoader`).
- **`adapters/`** — implementações concretas (LiteLLM, Perplexity/Gemini,
  OpenAI images, Pillow, WordPress REST, sitemap HTTP, Playwright screenshots,
  docx).
- **`pipeline/`** — `steps.py` (1 função por step), `pipeline.py`
  (`run_pipeline` orquestra por página + checkpoints + `report.md`),
  `runner.py` (retry-com-feedback + fallback + telemetria de custo),
  `routing.py` / `taxonomy.py` (grafo do funil), `doctrine.py` (doutrina de
  copy), `lp_template.py` (injetor Elementor), `validators/` (checks
  plugáveis nomeados no `config.yaml`), `enhancers/gutenberg.py`
  (normalização + rodapé de compliance + strip de divisor).
- **`cli.py`** — Typer CLI + composition root (`build_deps`): único lugar que
  monta os adapters concretos em `Deps`.

## Artefatos (`runs/<run_id>/`)

`funnel_plan.json`, `state.json` (checkpoint resumível), `report.md`
(tabela de status + custo/COGS por step), `p1.elementor.json` +
`p1.preview.html`, `p<N>.<slug>.gutenberg.html`, `p<N>.webp`.

## Testes

```bash
python3 -m pytest -q               # 210 testes
python3 -m ruff check src tests    # lint
```

`tests/fakes.py` traz `FakeLLM` (scriptável por lista ou por
`responder(model, messages)`), usado no `test_smoke_e2e.py` p/ um run
completo sem depender da ordem exata de chamadas ao LLM.

## Notas do site (creditoup)

- **Slug collision**: re-rodar sem apagar rascunhos antigos faz o WP criar
  slugs `-2`, quebrando interlinks. Apague/limpe o funil antigo antes, ou
  implemente publish idempotente (update-by-slug) — pendente.
- **Status**: um `publish` num post de funil provavelmente é intencional
  (revisão). O runner só garante que o funil NOVO nasce rascunho.
