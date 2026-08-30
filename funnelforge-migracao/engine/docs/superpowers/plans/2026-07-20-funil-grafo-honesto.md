# Plano A — Funil Grafo Honesto (3 pré-sells + forward-only)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use `- [ ]` checkboxes.
> Spec de referência: `docs/superpowers/specs/2026-07-20-funil-sota-grafo-honesto-e-screenshots-design.md`
> (leia a Parte A). Rev2 = revisão adversarial já dobrada.

**Goal:** LP com 3 botões congruentes → 3 pré-sells por ângulo → soluções
forward-only (p1→p2→p3) + oficial por-tema → terminal só cross-funnel. Grafo
honesto por construção, fail-closed.

**Architecture:** clean arch existente. Novo step criativo `synthesize_angles`
entre `extract` e `build_funnel_routes`; o extractor segue mapeador fiel.

**Tech stack:** Python 3.11+, Pydantic v2, Jinja2, LiteLLM, pytest, ruff.

## Global Constraints
- Slug: pré-sells `-pr1/-pr2/-pr3`; soluções `-p1…-pN`; LP sem sufixo.
- Fail-closed por página. **≥3 soluções por funil.**
- `enforce_pagespec` conta `cta` = kinds `funnel`+`cross_funnel` (external_official
  NÃO conta). `requires_external_official`/`requires_cross_funnel_exit` são campos
  MORTOS (ninguém lê) — não usar; apoiar em `required/forbidden_targets` +
  `validate_funnel_graph`.
- `/rec` nunca abre com `wp:buttons` (primeiro bloco do corpo = `wp:paragraph`).
- Diferenciação das pré-sells = `uniqueness_state_guard` existente (0.35), sem
  guard novo.
- ruff line-length 100; rodar `python3 -m pytest -q` e `ruff check src tests`.

---

### Task 1: derive_role reconhece `-pr1/-pr2/-pr3`

**Files:** Modify `src/funnelforge/domain/models.py:13`; Test `tests/test_models.py` (criar se não existir; senão adicionar a um test de role existente).

**Interfaces:** Produces: `derive_role("x-pr1") == PageRole.PRESELL`.

- [ ] **Step 1: Teste que falha**
```python
from funnelforge.domain.models import derive_role, PageRole
def test_derive_role_numbered_presell():
    for s in ("a-pr", "a-pr1", "a-pr2", "a-pr3"):
        assert derive_role(s) is PageRole.PRESELL, s
    for s in ("a-p1", "a-p12"):
        assert derive_role(s) is PageRole.SOLUTION, s
    assert derive_role("a") is PageRole.LP
```
- [ ] **Step 2:** Rodar → FAIL (`a-pr1` vira LP hoje).
- [ ] **Step 3:** Em models.py trocar `_ROLE_PRESELL_RE = re.compile(r"-pr$")` por
  `re.compile(r"-pr\d*$")`. (PRESELL já é checado antes de SOLUTION; `-p\d+$` não
  casa `-prN`.)
- [ ] **Step 4:** Rodar → PASS. `ruff check`.
- [ ] **Step 5:** Commit `feat(models): derive_role reconhece -pr1/-pr2/-pr3`.

---

### Task 2: Campos `angle` + `lead_solution_slug` em Page

**Files:** Modify `src/funnelforge/domain/models.py:83` (class Page); Test `tests/test_models.py`.

**Interfaces:** Produces: `Page(..., angle: str, lead_solution_slug: str)` (default `""`).

- [ ] **Step 1: Teste**
```python
from funnelforge.domain.models import Page
def test_page_angle_fields_default_empty():
    p = Page(page_number=2, page_type="HUB", h1_title="x", slug="a-pr1")
    assert p.angle == "" and p.lead_solution_slug == ""
    p2 = Page(page_number=2, page_type="HUB", h1_title="x", slug="a-pr1",
              angle="consultar cpf", lead_solution_slug="a-p1")
    assert p2.angle == "consultar cpf" and p2.lead_solution_slug == "a-p1"
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Adicionar em `class Page`: `angle: str = ""` e
  `lead_solution_slug: str = ""`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(models): Page.angle + lead_solution_slug`.

---

### Task 3: `assign_solution_ordinals` — popular `ordinal` do slug `-pN`

**Files:** Create helper em `src/funnelforge/pipeline/steps.py` (perto de `_plan_from_raw`); Test `tests/test_steps_ordinals.py`.

**Interfaces:** Produces `assign_solution_ordinals(plan: FunnelPlan) -> None` — muta
`page.ordinal` das SOLUÇÕES a partir do número em `-pN`; seta `page.role`
explicitamente (via `derive_role`) em TODAS as páginas (protege contra dedupe).

- [ ] **Step 1: Teste**
```python
from funnelforge.domain.models import FunnelPlan, Page, PageRole
from funnelforge.pipeline.steps import assign_solution_ordinals
def test_assign_ordinals_from_slug():
    plan = FunnelPlan(pages=[
        Page(page_number=1, page_type="LP", h1_title="", slug="base"),
        Page(page_number=2, page_type="HUB", h1_title="", slug="base-pr1"),
        Page(page_number=3, page_type="SOLUTION", h1_title="", slug="base-p1"),
        Page(page_number=4, page_type="SOLUTION", h1_title="", slug="base-p2"),
    ])
    assign_solution_ordinals(plan)
    by = {p.slug: p for p in plan.pages}
    assert by["base-p1"].ordinal == 1 and by["base-p2"].ordinal == 2
    assert by["base-p1"].role is PageRole.SOLUTION
    assert by["base-pr1"].role is PageRole.PRESELL
    assert by["base"].role is PageRole.LP
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar: para cada page, `page.role = derive_role(page.slug)`;
  se SOLUTION, extrair `N` de `-p(\d+)$` no slug e setar `page.ordinal = N`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(pipeline): assign_solution_ordinals + role explícito`.

---

### Task 4: Step `synthesize_angles` (prompt + step)

**Files:** Create `src/funnelforge/prompts/synthesize_angles.jinja`; Modify
`src/funnelforge/pipeline/steps.py` (novo `step_synthesize_angles`); Modify
`config.yaml` (`steps.synthesize_angles`); Test `tests/test_synthesize_angles.py`
(com `FakeLLM`).

**Interfaces:**
- Consumes: `FunnelPlan` mapeado (1 PRESELL + N≥3 SOLUTION), briefing, `LLMClient`.
- Produces: plano com a única PRESELL **substituída por 3** (`-pr1/-pr2/-pr3`),
  cada uma com `angle` + `lead_solution_slug` (3 slugs distintos, cada um uma
  SOLUÇÃO existente). Chama `assign_solution_ordinals` ao final. Se N<3, levanta
  erro claro (`ValueError("funil precisa de >=3 soluções")`) — fail-closed.

- [ ] **Step 1: Teste** (FakeLLM devolve 3 ângulos+pares; asserta 3 PRESELL com
  slugs `-pr1/2/3`, angles preenchidos, lead_solution_slug distintos e ∈ soluções,
  e que <3 soluções levanta ValueError).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `synthesize_angles.jinja`: instrui a sintetizar 3 ângulos
  distintos e honestos do tema + parear cada um a uma solução-líder (por slug),
  saída JSON `{"angles":[{"angle","h1","lead_solution_slug"}, x3]}`.
  `step_synthesize_angles`: renderiza, chama LLM, valida (3 itens, leads distintos
  ∈ soluções, ≥3 soluções), constrói 3 `Page` PRESELL (base do slug original +
  `-pr1/2/3`), remove a PRESELL antiga, chama `assign_solution_ordinals`.
  `config.yaml steps.synthesize_angles: { model: <criativo>, temperature: 0.8 }`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(pipeline): step_synthesize_angles (3 ângulos congruentes)`.

---

### Task 5: Wiring do step no pipeline + cli

**Files:** Modify `src/funnelforge/pipeline/pipeline.py` (chamar `step_synthesize_angles`
após `step_extract`, antes de `dedupe_slugs`/`build_funnel_routes`); Modify
`src/funnelforge/cli.py` (`build_deps` já provê `LLMClient`); Test: estender
`tests/test_smoke_e2e.py` para o plano pós-synthesize ter 3 PRESELL.

**Interfaces:** Consumes Task 4. Produces: o pipeline real gera 3 pré-sells.

- [ ] **Step 1:** Teste no smoke: após o extract+synthesize, `len([p for p in plan.pages if effective_role(p) is PageRole.PRESELL]) == 3`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Inserir a chamada no `run_pipeline` (fora do loop por-página, junto
  do extract). Garantir ordem: extract → synthesize → dedupe → build_funnel_routes.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(pipeline): fia synthesize_angles no run_pipeline`.

---

### Task 6: config.yaml routing + pagespec_for terminal

**Files:** Modify `config.yaml` (`routing:`); Modify `src/funnelforge/config/settings.py`
(se o schema de routing precisar da chave nova); Modify
`src/funnelforge/pipeline/pagespec.py:26` (`pagespec_for` ganha `terminal`); Test
`tests/test_pagespec.py`.

**Interfaces:** Produces `pagespec_for(settings, PageRole.SOLUTION, terminal=True)`
→ spec da chave `SOLUTION_TERMINAL`.

- [ ] **Step 1: Teste**
```python
def test_pagespec_terminal_key(settings):  # settings da fixture config_files
    mid = pagespec_for(settings, PageRole.SOLUTION)
    term = pagespec_for(settings, PageRole.SOLUTION, terminal=True)
    assert "cross_funnel" in term.required_targets       # terminal EXIGE cross
    assert "cross_funnel" not in term.forbidden_targets  # ...logo não o proíbe
    assert "funnel" in term.forbidden_targets            # terminal proíbe forward
    assert "cross_funnel" in mid.forbidden_targets       # miolo proíbe cross
    assert "external_official" in mid.required_targets
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** config `routing:`:
  - `LP: { allowed_targets:[funnel], required_targets:[funnel], forbidden_targets:[self,bare_rec,external_official,cross_funnel], cta_min:3, cta_max:3, distinct_targets:true, anchor_congruent:true }`
  - `PRESELL: { ..., cta_min:2, cta_max:8, distinct_targets:true }` (cta_max ≥ #soluções esperado)
  - `SOLUTION: { allowed_targets:[funnel,external_official], required_targets:[funnel,external_official], forbidden_targets:[self,bare_rec,cross_funnel], cta_min:1, cta_max:1, distinct_targets:true }`
  - `SOLUTION_TERMINAL: { allowed_targets:[cross_funnel], required_targets:[cross_funnel], forbidden_targets:[self,funnel,external_official,bare_rec], cta_min:1, cta_max:1, distinct_targets:false }`
  - `pagespec_for(settings, role, *, terminal=False)`: se `terminal`, `cfg = settings.routing.get("SOLUTION_TERMINAL")`; senão `role.value`. Retorna `PageTypeSpec(role=role, **cfg)`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(routing): specs LP 3/3, SOLUTION miolo/terminal`.

---

### Task 7: build_funnel_routes — LP 3 distintas, presell líder, forward, terminal

**Files:** Modify `src/funnelforge/pipeline/routing.py:29` (`build_funnel_routes`);
add helper `is_terminal_solution`; Test `tests/test_routing.py`.

**Interfaces:** Consumes Tasks 3,4,6. Produces `page.routes` do grafo-alvo.

- [ ] **Step 1: Testes** (montar um plano com 1 LP, 3 PRESELL c/ `lead_solution_slug`,
  3 SOLUTION `-p1/2/3` ordinais 1/2/3; rodar build_funnel_routes; asserir):
  - LP: 3 rotas, targets = os 3 slugs de pré-sell, **distintos**.
  - Cada PRESELL: `routes[0].target == lead_solution_slug` (líder no hero); fan-out
    cobre todas as soluções.
  - p1: 1 rota funnel → `-p2` (forward) + 1 `external_official`; **sem** cross_funnel/mesh.
  - p3 (terminal): só 1 rota `cross_funnel`; **sem** funnel/oficial.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Reescrever os ramos:
  - `LP`: `presells = sorted(PRESELL by ordinal-or-slug)`; `routes = [Route(hero/inline, "funnel", target=pr.slug, anchor=_anchor_for(pr.h1_title,i)) for i,pr in enumerate(presells)]`.
  - `PRESELL`: fan-out a todas as soluções, ordenando `lead_solution_slug` primeiro
    (`placement="hero"`); cap a `spec.cta_max` preservando cobertura (usar a lógica
    de anel já existente se `#soluções > cta_max`).
  - `SOLUTION`: `terminal = is_terminal_solution(page, solutions)`. Se terminal →
    só `Route(footer,"cross_funnel",cross[...])`. Senão → `Route(inline,"funnel",
    target=next_solution.slug)` (a de ordinal +1) + `Route(inline,"external_official",
    ext[...])`.
  - `is_terminal_solution(page, solutions)`: `page.ordinal == max(s.ordinal for s in solutions)`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(routing): LP→3 pré-sells, presell líder, solução forward-only`.

---

### Task 8: `_write_ctx` injeta solution_order + is_terminal + angle/lead

**Files:** Modify `src/funnelforge/pipeline/steps.py` (`_write_ctx` ~:433 e o
`render(...)` da pré-sell ~:527); Test `tests/test_steps_prompt_routing.py`.

**Interfaces:** Produces ctx com `solution_order: {slug:int}`, `is_terminal: bool`,
e (pré-sell) `angle`/`lead_solution` passados ao render.

- [ ] **Step 1:** Teste: para uma SOLUÇÃO miolo, `ctx["solution_order"]` mapeia
  slugs→ordinal e `ctx["is_terminal"] is False`; para a terminal, `True`. Para uma
  PRESELL, o `render` recebe `angle` e `lead_solution` não-vazios.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Em `_write_ctx` montar `solution_order` a partir de
  `state.plan` (como `h1_by_slug` já é montado) + `is_terminal` via
  `is_terminal_solution`. No ramo pré-sell do `step_write`, passar `angle=page.angle`,
  `lead_solution=page.lead_solution_slug` ao `render`.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(pipeline): ctx com solution_order/is_terminal/angle`.

---

### Task 9: validator `forward_only`

**Files:** Modify `src/funnelforge/pipeline/validators/checks.py` (nova fn +
registro em VALIDATORS); Modify `config.yaml` (write_page.validators += forward_only);
Test `tests/test_validators.py`.

**Interfaces:** `forward_only(content, ctx) -> list[Issue]` — usa `ctx["parsed"]["routes"]`,
`ctx["slug"]`, `ctx["solution_order"]`, `ctx["is_terminal"]`.

- [ ] **Step 1: Teste**
```python
def test_forward_only_flags_backlink():
    ctx = {"slug":"a-p2","solution_order":{"a-p1":1,"a-p2":2,"a-p3":3},
           "is_terminal":False,"parsed":{"routes":[{"placement":"inline","kind":"funnel","target":"a-p1","anchor":"x"}]}}
    assert any(i.code=="not_forward" for i in run_validators(["forward_only"],"",ctx))
def test_forward_only_passes_advance():
    ctx = {"slug":"a-p2","solution_order":{"a-p1":1,"a-p2":2,"a-p3":3},
           "is_terminal":False,
           "parsed":{"routes":[{"placement":"inline","kind":"funnel","target":"a-p3","anchor":"x"}]}}
    assert run_validators(["forward_only"],"",ctx) == []   # ordinal 3 > 2 = avança
def test_forward_only_terminal_noop():
    ctx = {"slug":"a-p3","solution_order":{"a-p1":1,"a-p2":2,"a-p3":3},
           "is_terminal":True,
           "parsed":{"routes":[{"placement":"footer","kind":"cross_funnel",
                                "target":"https://creditoup.com.br/x","anchor":"z"}]}}
    assert run_validators(["forward_only"],"",ctx) == []
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar: se `is_terminal` → `[]`. Senão, para cada route
  `kind=="funnel"`, se `solution_order.get(target,0) <= solution_order.get(slug,0)`
  → `Issue("not_forward", ...)`. Registrar em VALIDATORS + config.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(validators): forward_only`.

---

### Task 10: validator `no_leading_buttons`

**Files:** Modify `checks.py` (nova fn, espelho de `no_trailing_buttons`) + registro;
`config.yaml` write_page.validators += no_leading_buttons; Test `tests/test_validators.py`.

**Interfaces:** `no_leading_buttons(content, ctx)` — reprova se o **primeiro bloco
do corpo** for `wp:buttons` (deve ser `wp:paragraph`).

- [ ] **Step 1: Teste**: corpo começando com `<!-- wp:buttons -->…` → Issue
  `leading_buttons`; começando com `<!-- wp:paragraph -->…` → `[]`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar analisando o primeiro bloco não-vazio do conteúdo
  (reusar helpers de parsing de bloco de `no_trailing_buttons`); registrar.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(validators): no_leading_buttons (marco-zero do ad)`.

---

### Task 11: render_lp multi-href + lp.json 3 slots + guarda da LP

**Files:** Modify `src/funnelforge/pipeline/lp_template.py` (`render_lp`,
`_fix_image_and_hrefs`); Modify `src/funnelforge/templates/lp.json` (3 slots de
botão); Modify `src/funnelforge/pipeline/steps.py` (~:837-868 — passar lista de
hrefs de TODAS as `page.routes`; guarda fail-closed na LP); Test
`tests/test_lp_template.py`.

**Interfaces:** `render_lp(template, content, funnel_hrefs: list[str], ...)` — aplica
href por slot de botão na ordem.

- [ ] **Step 1: Testes**: `render_lp` com 3 hrefs distintos → os 3 botões do
  Elementor têm os 3 hrefs distintos (não o mesmo); guarda reprova (FAILED) se as
  rotas da LP não forem 3 pré-sells distintas.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `render_lp` recebe `funnel_hrefs: list[str]`; percorrer os slots
  de botão em ordem aplicando `funnel_hrefs[i]` (fallback ao último se faltar).
  `templates/lp.json` reduzido a 3 slots de botão. Em `step_publish`/`step_write`
  da LP, montar `hrefs = [resolve_route(r,...) for r in page.routes]` e passar;
  adicionar guarda: se `len({r.target for r in page.routes}) < 3` → StepStatus.FAILED.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(lp): render multi-href + 3 slots + guarda 3 destinos`.

---

### Task 12: prompts redator (p1, presell, pages)

**Files:** Modify `src/funnelforge/prompts/redator_p1.jinja`,
`redator_presell.jinja`, `redator_pages.jinja`; Test `tests/test_prompts.py`
(assert de conteúdo dos prompts renderizados).

**Interfaces:** Consome `angle`/`lead_solution`/`is_terminal`/`solution_order` no ctx.

- [ ] **Step 1: Testes** (render + grep): `redator_p1` pede **3** cta_texts
  congruentes; `redator_presell` usa `angle`+`lead_solution` e manda abrir com
  parágrafo (nunca botão) liderando a solução; `redator_pages` miolo="avança+oficial",
  terminal="só recircula", abre com parágrafo.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Editar os 3 templates conforme A7 da spec.
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(prompts): LP 3 botões, pré-sell por ângulo, solução forward`.

---

### Task 13: validate_funnel_graph + taxonomy.py

**Files:** Modify `src/funnelforge/pipeline/routing.py:157` (`validate_funnel_graph`);
Modify `src/funnelforge/pipeline/taxonomy.py`; Test `tests/test_routing.py`,
`tests/test_taxonomy.py`.

**Interfaces:** `validate_funnel_graph` passa a reprovar se os `lead_solution_slug`
das pré-sells não forem **3 distintos** e resolvíveis a SOLUÇÕES.

- [ ] **Step 1: Testes**: plano com 2 pré-sells apontando o mesmo lead → Issue
  `lead_not_distinct`; lead inexistente → `lead_unresolved`; `contract_advisories`
  itera TODAS as pré-sells (não só a 1ª).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Em `validate_funnel_graph` coletar os `lead_solution_slug` das
  PRESELL, checar distintos + ∈ slugs de SOLUÇÃO. Atualizar `taxonomy.py`:
  `SUFFIX_TO_ROLE` inclui `-prN`; `INTERLINK_RULES` reflete LP→3/forward-only;
  `contract_advisories` itera todas as pré-sells (`taxonomy.py:45`).
- [ ] **Step 4:** PASS + ruff.
- [ ] **Step 5:** Commit `feat(routing): valida lead_solutions + taxonomy atualizada`.

---

### Task 14: Smoke e2e com 3 pré-sells

**Files:** Modify `tests/test_smoke_e2e.py`, `tests/fakes.py` (FakeLLM cobre o novo
step synthesize + 3 pré-sells).

**Interfaces:** Consome tudo. Produces: run completo (sem publish) gera 1 LP + 3
PRESELL + ≥3 SOLUTION com o grafo-alvo, todos os validators passando.

- [ ] **Step 1:** Estender `FakeLLM` para responder ao `synthesize_angles` e às 3
  pré-sells; assert final: 3 pré-sells, LP com 3 destinos distintos, soluções
  forward-only, terminal cross-only, sem CTAs no marco-zero.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Ajustar fakes + fixtures.
- [ ] **Step 4:** PASS. **Rodar suíte inteira + ruff.**
- [ ] **Step 5:** Commit `test(e2e): smoke com 3 pré-sells + grafo honesto`.

---

## Execução
Após todas as tasks: rodar um funil real (local, sem publish) com um briefing de
crédito e inspecionar os artefatos (LP 3 botões distintos, 3 pré-sells por ângulo,
soluções forward-only). Depois: **Plano B (screenshots)**.
