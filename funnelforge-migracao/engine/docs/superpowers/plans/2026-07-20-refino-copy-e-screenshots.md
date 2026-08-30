# Plano — Refino de copy (legibilidade/congruência) + Plano B (screenshots)

> REQUIRED SUB-SKILL: subagent-driven-development. Steps `- [ ]`.
> Base: branch `feat/sota-honest-funnel` (grafo honesto já pronto, 314 verdes).
> Screenshots: seguir a **Parte B** de
> `docs/superpowers/specs/2026-07-20-funil-sota-grafo-honesto-e-screenshots-design.md`.
> Origem: review do usuário sobre o funil SOTA publicado (Empréstimo Negativado).

**Goal:** (A) matar paredões de texto e endireitar CTAs/legibilidade nas /rec e
LP; (B) soluções entregam o "ouro" (passo a passo + hyperlinks reais + prints
oficiais). Depois: re-rodar SOTA com screenshots e publicar como rascunho.

**Tech:** Python 3.11+, Pydantic, Jinja2, Playwright (extra screenshots),
Pillow. ruff 100. Rodar `python3 -m pytest -q` + `ruff check src tests`.

## Global Constraints
- Grafo honesto (Plano A) é INTOCÁVEL — não mexer em routing/pagespec/forward_only.
- Todo /rec abre em `wp:paragraph` (já garantido pelo enhancer) — manter.
- Screenshots atrás da flag `run.official_screenshots` (o run SOTA liga).
- allowed_external = gov.br + caixa.gov.br (inalterado).
- Fail-closed onde já era; guards de screenshot são fail-open (SKIPPED).

---

### Task 1: Enhancer que quebra paredão de texto (determinístico)

**Files:** Modify `src/funnelforge/pipeline/enhancers/gutenberg.py`; Test `tests/test_enhancers.py`.

**Interfaces:** `_split_long_paragraphs(content: str) -> str` — dentro de cada
bloco `<!-- wp:paragraph --><p>...</p>`, se o texto tem **≥3 frases** OU **>~300
chars**, divide em múltiplos blocos `wp:paragraph` (1-2 frases cada). Preserva
`<strong>/<em>/<a>` inline; NÃO toca em listas, tabelas, headings, buttons,
wp:html. Wire em `normalize_gutenberg` (aplicar a cada part não-html).

- [ ] Step 1: teste — um `<p>` com 3 frases vira 3 blocos `wp:paragraph`; um `<p>`
  curto (1 frase) fica intacto; `<strong>` inline preservado; wp:html intocado.
- [ ] Step 2: FAIL.
- [ ] Step 3: implementar `_split_long_paragraphs` (regex por bloco wp:paragraph;
  split por sentença via `. ` respeitando abreviações simples e não quebrando
  dentro de `<a>`); wire em `normalize_gutenberg` (antes do `_wrap_leading_bare_line`).
- [ ] Step 4: PASS + ruff. Rodar suíte inteira.
- [ ] Step 5: commit `feat(enhancer): quebra paredão de texto em parágrafos curtos`.

---

### Task 2: redator_p1 — CTA da LP sem jargão técnico

**Files:** Modify `src/funnelforge/prompts/redator_p1.jinja`; Test `tests/test_prompts.py`.

**Instrução exata:** os `cta_texts` da LP devem ser **compreensíveis pela grande
massa** — PROIBIDO números técnicos em CTA (taxas "%", "a.m.", "a.a.", valores de
juros). Use curiosidade/benefício em linguagem simples (ex.: em vez de
"Como antecipar o FGTS a partir de 1,24% a.m.", algo como "Tenho FGTS parado?
Como adiantar »" / "Como pegar meu dinheiro do FGTS antes »"). Regra no prompt:
"CTA nunca cita taxa/percentual/número técnico; fala a língua de quem não sabe o
que é '% ao mês'."

- [ ] Step 1: teste — render de `redator_p1` contém a instrução anti-jargão (grep
  por termos como "sem taxa/percentual" e a diretriz de linguagem simples).
- [ ] Step 2: FAIL.
- [ ] Step 3: editar o bloco de CTA do redator_p1.jinja.
- [ ] Step 4: PASS + ruff + suíte.
- [ ] Step 5: commit `feat(prompt): LP CTA sem jargão técnico (nível da massa)`.

---

### Task 3: redator_presell — fan-out CTA como PONTE congruente + parágrafos curtos

**Files:** Modify `src/funnelforge/prompts/redator_presell.jinja`; Test `tests/test_prompts.py`.

**Instrução exata:** cada CTA de fan-out deve (a) descrever o **destino**
(congruência — já é o caso via anchor_congruent) E (b) fazer **sentido saindo do
ângulo desta pré-sell** — uma PONTE. Ex.: numa pré-sell de tema FGTS, o CTA para
a solução "celular como garantia" não pode ser seco/incongruente ("Como funciona
o uso do celular como garantia"); tem que pontear ("Não tem FGTS liberado? Veja
como usar o celular como garantia »"). Regra: "todo botão de outra trilha começa
reconhecendo o contexto do leitor e ponteia para o destino; nunca um CTA solto
que ignora onde o leitor está." Manter parágrafos curtos (1-2 frases).

- [ ] Step 1: teste — render contém a diretriz de "ponte/congruência com o
  contexto" + "parágrafos curtos".
- [ ] Step 2: FAIL.
- [ ] Step 3: editar redator_presell.jinja.
- [ ] Step 4: PASS + ruff + suíte.
- [ ] Step 5: commit `feat(prompt): fan-out CTA como ponte congruente`.

---

### Task 4: redator_pages — soluções entregam o OURO

**Files:** Modify `src/funnelforge/prompts/redator_pages.jinja`; Test `tests/test_prompts.py`.

**Instrução exata:** a página de solução tem que entregar o passo a passo REAL,
não texto genérico:
- **Passo a passo numerado e concreto** ("Passo 1: abra o app X e toque em Y…").
- **Hyperlinks REAIS** para os canais oficiais (os `official_links` resolvidos),
  inline no meio do passo, levando o leitor de fato ao lugar.
- Os **prints oficiais** (Plano B) entram ancorados ao passo/link correspondente.
- Parágrafos curtos (1-2 frases), mobile-first.
- Regra: "cada solução ENSINA o caminho exato com links reais e o print da tela;
  nada de parágrafo genérico/paredão."

- [ ] Step 1: teste — render contém "passo a passo numerado", "hyperlinks reais",
  "parágrafos curtos".
- [ ] Step 2: FAIL.
- [ ] Step 3: editar redator_pages.jinja.
- [ ] Step 4: PASS + ruff + suíte.
- [ ] Step 5: commit `feat(prompt): soluções entregam passo a passo + links reais`.

---

### Task 5: Screenshot desktop mode + CaptureResult (Parte B / B1)

**Files:** Modify `src/funnelforge/adapters/screenshot_playwright.py`,
`src/funnelforge/ports/services.py`; Test `tests/test_step_screenshot.py`.

Seguir spec B1: `capture(url, *, mode="desktop"|"mobile", ...)` (desktop = viewport
1366x768, UA desktop honesto, dsf=2, default desktop). Retorno vira `CaptureResult`
(dataclass: `png: bytes`, `status: int|None`, `is_error_page: bool`). Guardas https/
allowlist ANTES do import do playwright (mantido). Ver protótipo validado em
scratchpad `shot_desktop.py` para o UA/viewport.

- [ ] TDD com mock do playwright (sem rede); commit `feat(screenshot): modo desktop + CaptureResult`.

---

### Task 6: Crop desktop profile (Parte B / B2)

**Files:** Modify `src/funnelforge/adapters/images_pillow.py`; Test `tests/test_images.py` (ou onde screenshot_to_webp é testado).

`screenshot_to_webp(..., profile="desktop"|"mobile")`: desktop = downscale ~1200px
largura, mantém a dobra (sem crop mobile 800x1200). Ver protótipo validado.

- [ ] TDD; commit `feat(screenshot): crop profile desktop`.

---

### Task 7: Guards de validade + retry (Parte B / B3)

**Files:** Modify `src/funnelforge/pipeline/steps.py` (step_screenshot); Test `tests/test_step_screenshot.py`.

- Guard status/erro: rejeita status != 200 ou is_error_page.
- Guard blank/under-render (Pillow, sem OCR): faixas + std-dev; rejeita
  `blank_frac >= 0.18` ou faixa contígua `>= 0.15`. Ver protótipo `validate_shot.py`.
- Retry 1x (scroll + settle maior) no reject de blank; senão pula (SKIPPED, fail-open).

- [ ] TDD com bytes de imagem sintéticos (blank vs cheio); commit `feat(screenshot): guards status/blank + retry`.

---

### Task 8: Curadoria de deep-links oficiais (Parte B / B4)

**Files:** Modify `src/funnelforge/pipeline/steps.py` (build_official_links),
`config.yaml` (mapa curado por host), `src/funnelforge/pipeline/validators/checks.py`
(official_link_density fail-open esparso). Test `tests/test_steps_*`, `tests/test_validators.py`.

- `build_official_links` prefere deep-links da pesquisa verificados; fallback = mapa
  curado de páginas de entrada por host (ex.: `meu.inss.gov.br`, home Receita,
  `caixa.gov.br/beneficios-trabalhador/fgts`) — URLs que renderizam bem p/ print E
  são hyperlink real útil.
- `official_link_density`: exigir interseção só quando a pesquisa rendeu >=2 deep
  links verificados; manter fail-open esparso (não super-bloquear).

- [ ] TDD; commit `feat(screenshot): curadoria de deep-links oficiais`.

---

### Task 9: Wiring + config + embed (Parte B / B5)

**Files:** Modify `config.yaml` (screenshot.mode desktop, crop_profile, limiares,
URLs curadas), `src/funnelforge/cli.py` (build_deps liga provider desktop quando flag on),
`src/funnelforge/pipeline/steps.py` (embed do print ancorado ao link oficial correspondente). Test smoke.

- [ ] TDD; commit `feat(screenshot): wiring desktop + embed ancorado ao passo`.

---

### Task 10: Smoke e2e com screenshots + suíte verde

**Files:** Modify `tests/test_smoke_e2e.py`, `tests/fakes.py` (FakeScreenshot provider).

- [ ] Smoke: com flag on + provider fake, solução recebe print embutido após o link
  oficial; sem quebrar o grafo honesto. Rodar suíte inteira + ruff.
- [ ] commit `test(e2e): smoke com screenshots nas soluções`.

## Execução
Após tudo: instalar playwright chromium se necessário, re-rodar o funil de
Empréstimo Negativado com `--publish` (flag official_screenshots on), validar 7/7
+ prints nas soluções, entregar as URLs de edição.
