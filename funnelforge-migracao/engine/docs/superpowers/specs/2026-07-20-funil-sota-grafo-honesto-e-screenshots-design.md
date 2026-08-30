# Funil SOTA — Grafo Honesto + Screenshots Oficiais — Design Spec

> **Para workers agênticos:** design aprovado. Implementação via writing-plans →
> subagent-driven-development (TDD, commits frequentes).
>
> **Rev 2** — revisão adversarial dobrada: B1 (novo step de síntese, extractor
> segue mapeador), B2 (`ordinal` populado), B3 (LP render multi-href + guarda),
> I4–I10 (plumbing terminal/ctx, flags mortos, cap do fan-out, guarda de
> distinção reusada), M1–M4. Ver "Correções da revisão" ao fim.

**Goal:** Grafo de CTAs **honesto por construção** (elimina *navegação enganosa*
e *doorway/scaled-content*) + **prints reais das páginas oficiais** nas soluções.
De um briefing sai um funil compliance-blindado, ponta a ponta.

**Arquitetura:** clean architecture (domain ← ports ← adapters ← pipeline;
`cli.py` composition root). Dois workstreams: **A — Grafo honesto**, **B —
Screenshots oficiais**.

**Tech stack:** Python 3.11+, Pydantic v2, Jinja2, Playwright (extra
`screenshots`), Pillow, LiteLLM.

**Baseline já construído (NÃO reimplementar):** upgrade v1.1 de texto (gravata,
fan-out da pré-sell, `no_trailing_buttons`, links inline, `phrase_registry`/
`opening_line_unique`, featured/mid images, screenshot mobile atrás da flag) +
fix de coerção `int` no `funnel_schema`. 278 testes verdes, working tree.

---

## Global Constraints

- **Slug:** LP sem sufixo (`/r/`); pré-sells **`-pr1/-pr2/-pr3`**; soluções
  `-p1…-pN` (`/rec`).
- **Fail-closed** por página (grafo inválido bloqueia build+publish daquela
  página; funil segue nas válidas).
- **≥3 soluções por funil.**
- `allowed_external` inalterado: `[https://gov.br, https://www.gov.br,
  https://www.caixa.gov.br]`.
- **Ads no WP (Ad Inserter):** funnel-forge NÃO emite bloco de ad; obrigação:
  **corpo `/rec` nunca começa com `wp:buttons`** (reserva o marco-zero).
- **Diferenciação das pré-sells** garantida pelo `uniqueness_state_guard`
  existente (não um guard novo — ver A5/I7).

## Fluxo do pipeline (novo step em maiúsculas)

```
extract (mapeia, FIEL)  →  SYNTHESIZE_ANGLES (NOVO, criativo)  →  dedupe_slugs
  →  build_funnel_routes  →  por página: research/write/judge/image/SCREENSHOT/seo/build/publish
```

---

## O grafo-alvo

```
                          LANDING PAGE  (/r/)
        botão A                    botão B                    botão C
      (ângulo A)                 (ângulo B)                 (ângulo C)
          │                          │                          │
     PRÉ-SELL A (-pr1)          PRÉ-SELL B (-pr2)          PRÉ-SELL C (-pr3)
     lidera com p1              lidera com p2              lidera com p3
     [p1] p2  p3                p1 [p2] p3                 p1  p2 [p3]
          └──────────────────────┼──────────────────────┘
                                 ▼
             p1 ──▶ p2 ──▶ p3 ──▶ cross-funnel (sitemap)
           +oficial   +oficial     (só recircula)
          (tema p1)  (tema p2)
```

Reachability verificada (revisão): fan-out das pré-sells alcança toda solução;
terminal alcançável via aresta pré-sell→terminal; `reachable_slugs` anda só em
arestas `funnel`, então `cross_funnel` não cria loop detectável. DAG sem ciclo.

---

## Parte A — Grafo honesto

### A1. Slug (`domain/models.py`)
- `_ROLE_PRESELL_RE`: `-pr$` → **`-pr\d*$`** (verificado: hoje `-pr1`→LP; depois
  →PRESELL; sem colidir com `-p\d+$`, PRESELL checado antes).

### A2. Step de síntese de ângulos (NOVO — `pipeline/steps.py`, `prompts/synthesize_angles.jinja`, `cli.py`)
- **O extractor permanece mapeador fiel** (não muda o contrato "SEMPRE 1 HUB /
  NUNCA invente"). Ele produz o plano mapeado com **1 pré-sell + N soluções**.
- **`step_synthesize_angles`** (criativo, roda após extract): do plano mapeado +
  briefing, sintetiza **3 ângulos distintos e honestos**, pareia cada um a uma
  **solução-líder distinta**, e **expande a única PRESELL em 3** (`-pr1/-pr2/-pr3`),
  cada `Page` PRESELL com `angle` + `lead_solution_slug`.
- **Pareamento:** 3 ângulos ↔ 3 soluções-líderes distintas. Se N>3, as demais
  entram só na cauda do fan-out. Se N<3, o step **re-tenta exigindo ≥3 soluções**.
- Modelo próprio no `config.yaml steps.synthesize_angles` (criativo, temp alta),
  fiado em `cli.build_deps`.

### A3. `ordinal` populado (B2 — `pipeline/steps.py`)
- Hoje `ordinal` **nunca é escrito** (sempre 0); os `sorted(key=ordinal)` só
  funcionam por acaso (sort estável = ordem do plano). **Fix raiz:** no
  `step_synthesize_angles` (ou normalização pós-extract), **preencher `ordinal`
  das SOLUÇÕES a partir do número do slug `-pN`** (p1→1, p2→2…). LP/pré-sells não
  usam ordinal. Assim `forward_only` e a detecção de terminal operam em dado real.
- **`Page.role` setado explicitamente** no mesmo passo (M2) — protege contra o
  `dedupe_slugs` que renomeia `x-pr1`→`x-pr1-2` e faria `derive_role` cair em LP.

### A4. Builder do grafo (`pipeline/routing.py` — `build_funnel_routes`)
- **LP:** emitir **3 rotas a 3 pré-sells distintas** (fim do `routes[0]` único),
  âncora congruente ao ângulo/H1 de cada pré-sell.
- **PRESELL (×3):** fan-out a todas as soluções, `lead_solution` no
  `placement="hero"`. **Cap (I8):** limitar a `cta_max`; se `#soluções > cta_max`,
  distribuir garantindo aresta de entrada pra toda solução (padrão do anel de
  irmãs já existente) — reachability preservada.
- **SOLUÇÃO miolo** (ordinal ≠ máx): **1 rota forward** `p_{i+1}` +
  `external_official`. **Remove** mesh e `cross_funnel`.
- **SOLUÇÃO terminal** (ordinal máx): **só** `cross_funnel`.
- Helper `is_terminal_solution(page, solutions)` = maior `ordinal`.

### A5. Pagespec / config (`config.yaml`, `pipeline/pagespec.py`, `config/settings.py`)

| Role | Novo |
|---|---|
| **LP** | `cta 3/3`, `distinct:true`; allowed `[funnel]`; forbidden `[self, bare_rec, external_official, cross_funnel]` |
| **PRESELL** | `distinct:true`; **`cta_max` parametrizado ≥ #soluções** (I8) |
| **SOLUTION** (miolo) | allowed `[funnel, external_official]`; required `[funnel, external_official]`; **forbidden `[self, bare_rec, cross_funnel]`**; `cta 1/1`; `distinct:true` |
| **SOLUTION_TERMINAL** (novo) | allowed `[cross_funnel]`; required `[cross_funnel]`; forbidden `[self, funnel, external_official, bare_rec]`; `cta 1/1` |

- **I4:** `pagespec_for(settings, role, *, terminal=False)` — quando `terminal`,
  busca a chave literal **`"SOLUTION_TERMINAL"`** no `routing` (o `PageRole` enum
  não ganha membro novo). `_write_ctx` calcula `terminal` a partir de
  `state.plan` (já monta a lista de soluções em `steps.py:524-526`).
- **I5 (flags mortos):** `requires_external_official`/`requires_cross_funnel_exit`
  **não são lidos por ninguém** — não confiar neles. A obrigatoriedade vem de
  `required_targets` + `forbidden_targets` (`enforce_pagespec`) e do check
  hardcoded de terminal em `validate_funnel_graph` (`routing.py:169`). O
  `forbidden:[cross_funnel]` no miolo faz `enforce_pagespec` reprovar miolo com
  cross-funnel.

### A6. Validators (`pipeline/validators/checks.py`, `pipeline/steps.py`)
- **`forward_only`** (per-página, fail-closed): SOLUÇÃO miolo — toda rota `funnel`
  aponta pra `ordinal` **maior** que o próprio. **I6:** `_write_ctx` passa a
  injetar `solution_order` (`{slug: ordinal}`) + `is_terminal` no ctx (espelho de
  como `h1_by_slug` já é montado). Terminal (sem rota funnel) passa trivialmente.
- **`no_leading_buttons`** (per-página, fail-closed): **M3 — o primeiro bloco do
  CORPO do draft `/rec` tem que ser `wp:paragraph`, nunca `wp:buttons`** (o H1 é o
  título do post WP, não vive no corpo; o primeiro heading do corpo é H2).
- **Distinção das pré-sells (I7):** **NÃO** criar `presell_angles_distinct`. O
  `uniqueness_state_guard` existente (`steps.py:146`) já compara cada draft
  (pré-sells incluídas) contra os anteriores por Jaccard boilerplate-aware
  (`jaccard_threshold` 0.35) e reprova near-duplicate — cobre o anti-doorway. Se
  quisermos rigor extra por ângulo, parametrizar um limiar de pré-sell no config;
  default: reusar o guard existente.

### A7. Prompts / template (`prompts/`, `pipeline/lp_template.py`, `templates/lp.json`)
- **`redator_p1` (LP):** 3 `cta_texts` congruentes (um por ângulo→pré-sell).
- **`redator_presell` (×3):** **I9 — `step_write` passa `angle` + `lead_solution`
  no `render(...)`** (hoje só passa `is_terminal`, `steps.py:527-546`); abre no
  parágrafo-gancho enviesado (nunca botão primeiro), fan-out liderando a sua.
- **`redator_pages`:** miolo "avança + oficial"; terminal "só recircula"; abre com
  parágrafo.
- **B3 — LP render:** `render_lp` passa a receber **lista ordenada de hrefs**
  (um por botão, de **todas** as `page.routes`, não `routes[0]`);
  `_fix_image_and_hrefs` aplica href **por slot**; `templates/lp.json` reduzido a
  **exatamente 3 slots** de botão. **Enforcement da LP:** hoje `write_p1` tem
  `validators:[]` → a config nova da LP seria letra morta; adicionar um check
  **fail-closed na LP** (rodar `pagespec` no `write_p1` **ou** um validator do
  Elementor renderizado exigindo 3 hrefs de pré-sell distintos).

### A8. Grafo — validações extra (`pipeline/routing.py`, `pipeline/taxonomy.py`)
- **I9:** `validate_funnel_graph` checa que os 3 `lead_solution_slug` são
  **distintos** e resolvem a SOLUÇÕES existentes.
- **M1:** atualizar `taxonomy.py` (`SUFFIX_TO_ROLE` inclui `-prN`; `INTERLINK_RULES`
  reflete LP→3 pré-sells / forward-only; `contract_advisories` **itera todas as
  pré-sells**, não só a primeira — `taxonomy.py:45`).

---

## Parte B — Screenshots oficiais produção-viáveis
(comprovado por smoke: mecanismo ok; desktop >> mobile; guards baratos pegam
spinner/404; valor depende de deep-links bons.)

### B1. Modo desktop + contrato de retorno (M4 — `adapters/screenshot_playwright.py`, `ports/services.py`)
- `capture(url, *, mode="desktop"|"mobile", ...)`: **desktop** = viewport
  `1366×768`, UA desktop honesto, `dsf=2` (default desktop p/ oficiais).
- **Muda o contrato de retorno** (hoje `-> bytes`): retornar um
  **`CaptureResult`** (dataclass: `png: bytes`, `status: int|None`,
  `is_error_page: bool`). `step_screenshot` (`steps.py:728`) passa a lidar com
  isso (guardas abaixo).

### B2. Crop desktop (`adapters/images_pillow.py`)
- `screenshot_to_webp(..., profile="desktop"|"mobile")`: **desktop** = downscale
  ~1200px largura, mantém a dobra (sem o crop mobile 800×1200 que espreme).

### B3. Guards de validade (`step_screenshot` em `pipeline/steps.py`)
- **Status/erro:** rejeita `status != 200` ou `is_error_page`.
- **Blank/under-render** (Pillow, sem OCR): faixas horizontais + std-dev; rejeita
  `blank_frac ≥ ~0.18` ou faixa contígua `≥ ~0.15`.
- **Retry 1×** (scroll + settle maior) no reject de blank; senão **pula** o print
  (fail-open — o `step_screenshot` já é try/except→SKIPPED).

### B4. Curadoria de deep-links (`pipeline/steps.py build_official_links`, `config.yaml`, `checks.py`)
- `build_official_links` **prefere deep-links da pesquisa verificados** (200 +
  não-erro); fallback = **mapa curado de páginas de entrada por host** (ex.:
  `meu.inss.gov.br`, home da Receita).
- **I10 — `official_link_density`:** endurecer só quando a pesquisa **de fato**
  rendeu ≥2 deep-links verificados; **manter o fail-open esparso** (mínimo 1
  quando a pesquisa não trouxe deep-links) pra não super-bloquear.

### B5. Config
- `run.official_screenshots` (flag; run SOTA liga), `screenshot.mode: desktop`,
  `screenshot.crop_profile: desktop`, limiares dos guards, URLs curadas por host.

---

## Testes
`derive_role` (`pr1/2/3`) · `step_synthesize_angles` (3 ângulos, pareamento,
ordinal, roles, ≥3 soluções) · builder (LP→3 distintas, líder no hero, forward,
terminal cross-only, cap do fan-out) · pagespec (LP 3/3, SOLUTION miolo/terminal
via `terminal=`) · `forward_only`, `no_leading_buttons` · reuso do
`uniqueness_state_guard` p/ pré-sells · `render_lp` multi-href + guarda da LP ·
`validate_funnel_graph` (lead_solutions distintos/resolvíveis) · screenshots
(desktop mock, perfis de crop, `CaptureResult`, guard status, guard blank, retry)
· **smoke e2e** com 3 pré-sells + screenshots.

## Fora de escopo
Crop-OCR v2 · Serasa/`.com.br` na allowlist · publish idempotente.

## Premissas
≥3 soluções · allowlist gov.br/caixa inalterada · ads no WP.

---

## Correções da revisão adversarial (rev 1 → rev 2)
- **B1** extractor não pode inventar → **novo `step_synthesize_angles`** (A2).
- **B2** `ordinal` nunca escrito → **populado do slug `-pN`** (A3); `forward_only`
  por ordinal real (A6).
- **B3** LP colapsa em `routes[0]` + `write_p1` sem validator → **`render_lp`
  multi-href + 3 slots + guarda fail-closed na LP** (A7).
- **I4** `SOLUTION_TERMINAL` sem membro no enum → **`pagespec_for(..., terminal=)`
  busca chave literal** (A5).
- **I5** `requires_*` são campos mortos → apoiar em `required/forbidden_targets`
  + `validate_funnel_graph` (A5).
- **I6** `forward_only` sem dados → **`solution_order`+`is_terminal` no ctx** (A6).
- **I7** guard de pré-sell redundante → **reusar `uniqueness_state_guard`** (A6).
- **I8** fan-out sem cap quebra >6 soluções → **cap + `cta_max` parametrizado**
  (A4/A5).
- **I9** `angle/lead_solution` não chegam no render + integridade → **render +
  validação de grafo** (A7/A8).
- **I10** endurecer `official_link_density` super-bloqueia → **manter fail-open
  esparso** (B4).
- **M1** `taxonomy.py` estale → atualizar + iterar todas as pré-sells (A8).
- **M2** `dedupe_slugs` estraga `-prN`/`-pN` → **`Page.role` explícito** (A3).
- **M3** "após o H1" ambíguo → **primeiro bloco do corpo = `wp:paragraph`** (A6).
- **M4** `capture()` muda contrato → **`CaptureResult` + fluxo no
  `step_screenshot`** (B1/B3).
