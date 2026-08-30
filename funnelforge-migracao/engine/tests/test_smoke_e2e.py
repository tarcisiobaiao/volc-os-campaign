"""End-to-end smoke test: a full funnel dry-run through `run_pipeline`.

Scripts `FakeLLM` with a callable responder keyed on distinguishing text in
each prompt template (extractor / synthesize_angles / research / redator_p1 /
redator_presell / redator_pages / judge / seo / image_prompt) rather than
positional list indices, so the script doesn't depend on the exact call count
-- only on which *kind* of step is being asked for. This mirrors
`steps.py`'s actual branching (T1D: by the page's EFFECTIVE role, not its raw
page_type): the `image` step only fires for the LANDING PAGE (P1); interior
pages never get an image LLM call.

The extractor maps 1 LP + 1 HUB(presell) + 3 SOLUTION (5 pages); Task 5 wires
`step_synthesize_angles` right after extract, which EXPANDS that single
mapped presell into 3 angle bridges (-pr1/-pr2/-pr3) -- so the funnel that
actually runs end to end is 1 LP + 3 PRESELL + 3 SOLUTION = 7 pages.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from funnelforge.adapters.briefing_docx import DocxBriefingLoader
from funnelforge.adapters.elementor import build_elementor  # noqa: F401 (import graph)
from funnelforge.adapters.images_pillow import PillowImageProcessor
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import PageRole, StepStatus, effective_role
from funnelforge.pipeline.pipeline import Deps, run_pipeline
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM, FakeScreenshotProvider

_SPANISH_MARKERS = ("Ingreso", "¿Cómo", "colombia.eleicoes.org")

PLAN_JSON = json.dumps(
    {
        "funnel_strategy": {
            "avatar_summary": "Trabalhador CLT buscando antecipar o FGTS.",
            "tone_voice": "calmo, editorial, factual",
            "total_pages": 5,
        },
        "pages": [
            {
                "page_number": 1,
                "page_type": "LANDING PAGE",
                "h1_title": "Saque FGTS Aniversário: Como Funciona",
                "slug": "saque-fgts",
                "emotional_objective": "clareza e alívio prático",
                "main_content_structure": ["H2: O que é", "H2: Como funciona"],
                "hook_to_next_page": "Ver quem tem direito",
                "next_page_slug": "quem-tem-direito-pr",
                "target_keywords": ["fgts", "saque aniversario"],
            },
            {
                "page_number": 2,
                "page_type": "HUB",
                "h1_title": "Guia Completo do FGTS",
                "slug": "quem-tem-direito-pr",
                "emotional_objective": "organização e confiança",
                "main_content_structure": ["H2: Índice do guia"],
                "hook_to_next_page": "Como consultar o saldo",
                "next_page_slug": "como-consultar-saldo-p1",
                "target_keywords": ["fgts guia"],
            },
            {
                "page_number": 3,
                "page_type": "SOLUTION",
                "h1_title": "Como Consultar o Saldo do FGTS",
                "slug": "como-consultar-saldo-p1",
                "emotional_objective": "orientação passo a passo",
                "main_content_structure": ["H2: Passo a passo"],
                "hook_to_next_page": "Como sacar o FGTS",
                "next_page_slug": "como-sacar-p2",
                "target_keywords": ["consultar saldo fgts"],
            },
            {
                "page_number": 4,
                "page_type": "SOLUTION",
                "h1_title": "Como Sacar o FGTS Aniversário",
                "slug": "como-sacar-p2",
                "emotional_objective": "orientação passo a passo",
                "main_content_structure": ["H2: Passo a passo"],
                "hook_to_next_page": "Prazos de pagamento",
                "next_page_slug": "prazos-pagamento-p3",
                "target_keywords": ["sacar fgts"],
            },
            {
                "page_number": 5,
                "page_type": "SOLUTION",
                "h1_title": "Prazos de Pagamento do FGTS Aniversário",
                "slug": "prazos-pagamento-p3",
                "emotional_objective": "previsibilidade",
                "main_content_structure": ["H2: Calendário de pagamentos"],
                "hook_to_next_page": "",
                "next_page_slug": "",
                "target_keywords": ["prazo fgts"],
            },
        ],
    },
    ensure_ascii=False,
)

ANGLES_JSON = json.dumps(
    {
        "angles": [
            {"angle": "consultar pelo cpf", "h1": "Já tenho direito ao saque?",
             "lead_solution_slug": "como-consultar-saldo-p1"},
            {"angle": "onde recebo mais rápido", "h1": "Onde receber mais rápido",
             "lead_solution_slug": "como-sacar-p2"},
            {"angle": "prazos e regras de quem foi demitido", "h1": "Prazos e regras 2026",
             "lead_solution_slug": "prazos-pagamento-p3"},
        ]
    },
    ensure_ascii=False,
)

# O deep link oficial que a PESQUISA de cada SOLUTION devolve. É ELE, e não uma
# lista de hosts na configuração, que autoriza o canal oficial desta run:
# `registrar_canais_oficiais` guarda a escolha em `state.official_links` e
# `bind_official_route` liga a aresta `external_official` com essa URL exata.
_OFFICIAL_URL = "https://www.gov.br/fgts"

RESEARCH_JSON = json.dumps(
    {
        "resumo": "Panorama factual do tema com base em fontes oficiais.",
        "dados_validados": [],
        "passo_a_passo": ["Acessar o aplicativo", "Conferir o extrato"],
        "fontes": [_OFFICIAL_URL],
    },
    ensure_ascii=False,
)

P1_MARKERS = (
    "=== WIDGET: TÍTULO (H1) ===\n"
    "Saque FGTS Aniversário: Como Funciona\n"
    "---\n"
    "=== WIDGET: TEXTO ===\n"
    + ("conteúdo informativo verificado " * 500).strip()
    + "\n---\n"
    "=== WIDGET: BOTÃO ===\n"
    "Texto: Como consultar seu saldo\n"
    "Cor: vermelho\n"
    "Link: ignorado\n"
    "---\n"
    "=== WIDGET: FAQ ===\n"
    "1. O que é o Saque-Aniversário? É uma modalidade de saque do FGTS.\n"
    "2. Quem pode aderir? Qualquer titular de conta ativa do FGTS.\n"
    "---\n"
    "=== WIDGET: BOTÃO ===\n"
    "Texto: Ver o passo a passo completo\n"
    "Cor: azul\n"
    "Link: ignorado\n"
    "---\n"
    "=== WIDGET: BYLINE ===\n"
    "Equipe Crédito Up\n"
    "Redação de jornalismo de serviço.\n"
    "---\n"
    "=== WIDGET: RODAPE ===\n"
    "Sobre o Site. Conteúdo de utilidade pública mantido via Google Adsense.\n"
)

_HEADLINE_RE = re.compile(r"Tema/headline: (.+)")


def _filler(slug: str, n: int = 60) -> str:
    """`n` per-slug-unique tokens (no two slugs ever share a token) so the
    generated pages' word *sets* barely overlap -- boilerplate phrasing
    alone sits well under the 0.35 Jaccard threshold either uniqueness guard
    enforces: T0E's `uniqueness_state_guard` state hook (steps.py) AND T1C's
    static `pipeline.uniqueness.jaccard` validator -- both now share the
    SAME boilerplate-aware algorithm (word-boundary regex
    `[a-z0-9à-ü]{4,}`, which does NOT treat '-' as a word character, minus
    the fixed compliance/nav/byline token set). Each token is a single
    hyphen-free alphanumeric run so neither tokenizer fragments it into
    common Portuguese words shared by every page. This fake-response filler
    is deliberately zero-overlap (unlike real drafts, which legitimately
    share a compliance/nav/byline kit that `pipeline.uniqueness.jaccard` now
    discounts) -- it only needs to keep this scripted smoke test's synthetic
    pages apart; the boilerplate-aware-similarity behavior itself is
    exercised directly in `tests/test_uniqueness.py`."""
    tag = re.sub(r"[^a-z0-9]", "", slug.lower())
    return " ".join(f"exclusivo{tag}{i:03d}" for i in range(n))


def _page_html_for(content: str) -> str:
    """Distinct HTML per interior page (T0E/T1D): each page's content must
    differ enough (by Jaccard similarity) that `uniqueness_state_guard`
    doesn't flag near-duplicate boilerplate. Real drafts always differ
    because they're topic-specific -- this keys off the `Tema/headline:`
    line both `redator_pages.jinja` and `redator_presell.jinja` embed in
    their TAREFA block (the per-page `page.h1_title`), to mirror that in
    the fake responses."""
    headline_match = _HEADLINE_RE.search(content)
    headline = headline_match.group(1).strip() if headline_match else "pagina"
    topic = headline.lower()
    return (
        "<!-- wp:paragraph -->\n"
        f"<p>Conteúdo de utilidade pública sobre {headline}, trazendo orientações "
        f"claras, diretas e verificadas a respeito de {topic} para o leitor "
        f"brasileiro. {_filler(headline)}</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:list -->\n"
        f'<ul class="wp-block-list"><li>Primeiro passo sobre {topic}, explicado '
        "com clareza.</li>"
        f"<li>Segundo passo sobre {topic}, detalhado para facilitar a leitura "
        "do leitor.</li></ul>\n"
        "<!-- /wp:list -->\n"
    )

JUDGE_JSON = json.dumps(
    {
        "approved": True,
        "blocking": False,
        "scores": {
            "single_destination": 9,
            "proof_and_authority": 8,
            "compliance": 9,
            "cta_discipline": 8,
        },
        "feedback": [],
    }
)

SEO_JSON = json.dumps(
    {
        "seotitle": "FGTS Aniversário: entenda como funciona",
        "metadescription": "Saiba como funciona o saque-aniversário do FGTS.",
        "keywordfocus": "fgts aniversario",
        "slug": "saque-fgts",
    },
    ensure_ascii=False,
)

IMAGE_PROMPT = (
    "A bright vertical 9:16 editorial photograph of a relieved Brazilian worker "
    "checking a government app, warm golden-hour light, heavy dark gradient fade "
    "at the bottom third, no text, no worried expressions."
)


# The LP is now STRUCTURED JSON that fills the Elementor template (not markers).
P1_JSON = json.dumps({
    "hero_title": "Saque-Aniversário FGTS",
    "hero_subtitle": "Antecipação, regras e valores em 2026 -- toque abaixo e veja "
                      "como consultar o seu saldo",
    "article_title": "Saque-Aniversário do FGTS: como funciona a antecipação",
    "intro": "<p>Segundo a Caixa Econômica Federal (CAIXA), o Fundo de Garantia (FGTS) "
             "permite antecipar o saque anual.</p>",
    "sections": [
        {"title": "O que é a antecipação?", "body": "<p>Explicação factual.</p>"},
        {"title": "3 pontos importantes", "body": "<p>1) a 2) b 3) c</p>"},
        {"title": "Quem tem direito?", "body": "<ul><li>Requisito</li></ul>"},
        {"title": "Regras e valores em 2026", "body": "<ul><li>Regra, segundo a CAIXA</li></ul>"},
    ],
    "faq": [
        {"q": "Posso antecipar negativado?", "a": "Sim."},
        {"q": "Qual o valor mínimo?", "a": "Depende."},
        {"q": "Quando o dinheiro cai?", "a": "Depende."},
        {"q": "Como faço a adesão?", "a": "Pelo aplicativo oficial."},
        {"q": "É seguro?", "a": "Sim."},
    ],
    "transition": "<p>Agora veja quem tem direito no próximo passo.</p>",
    # 3 CTAs, um por destino real (hub + as 2 soluções diretas da LP).
    "cta_texts": ["Como consultar meu saldo »", "Ver o passo a passo »",
                  "Como fazer a adesão »"],
}, ensure_ascii=False)


def _responder(model: str, messages: list[dict]) -> str:
    """Dispatch a canned response by matching distinguishing text in the
    prompt itself, so the script is independent of call order/count."""
    content = messages[-1]["content"]
    if "BRIEFING_DE_ENTRADA" in content:
        return PLAN_JSON
    if "ESTRATEGISTA-CHEFE" in content:
        return ANGLES_JSON
    if "Pesquise e retorne SOMENTE um objeto JSON" in content:
        return RESEARCH_JSON
    if "PÁGINA DE POUSO" in content:
        return P1_JSON
    if "PÁGINA INTERNA" in content or "PÁGINA PRÉ-SELL" in content:
        return _page_html_for(content)
    if "JUIZ DE QUALIDADE" in content:
        return JUDGE_JSON
    if "YOAST SEO" in content:
        return SEO_JSON
    if "VISUAL STRATEGIST" in content:
        return IMAGE_PROMPT
    raise AssertionError(f"unscripted prompt (no responder match): {content[:200]!r}")


def test_full_5_page_funnel_dry_run(tmp_path: Path, config_files: Path) -> None:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    llm = FakeLLM(responses=_responder)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    deps = Deps(
        llm=llm,
        research=None,
        image_gen=None,
        image_proc=None,
        publisher=None,
        loader=DocxBriefingLoader(),
        settings=settings,
        runner=runner,
    )
    briefing = tmp_path / "briefing.txt"
    briefing.write_text("Briefing completo do funil FGTS Saque-Aniversário.", encoding="utf-8")

    state = run_pipeline(briefing, deps, only=None, publish=False)

    # --- HUB ÚNICO (run.presell_hubs=1, o padrão): `expand_presell_hubs` não
    # clona nada, só normaliza o slug da pré-sell mapeada para `-pr`.
    # 1 LP + 1 PRESELL + 3 SOLUTION = 5 páginas.
    assert state.plan is not None
    presells = [p for p in state.plan.pages if effective_role(p) is PageRole.PRESELL]
    assert len(presells) == 1, presells
    assert presells[0].slug.endswith("-pr"), presells[0].slug

    # --- a LP abre com o hub e manda os 2 botões seguintes direto às soluções
    lp = next(p for p in state.plan.pages if effective_role(p) is PageRole.LP)
    alvos = [r.target for r in lp.routes if r.kind == "funnel"]
    solucoes = sorted((p for p in state.plan.pages
                       if effective_role(p) is PageRole.SOLUTION), key=lambda p: p.ordinal)
    assert alvos == [presells[0].slug, solucoes[0].slug, solucoes[1].slug], alvos

    # --- toda solução continua alcançável: o hub faz fan-out para TODAS
    hub_alvos = {r.target for r in presells[0].routes if r.kind == "funnel"}
    assert hub_alvos == {s.slug for s in solucoes}, hub_alvos

    # --- the run completed and produced a plan for all 5 pages -----------
    assert len(state.plan.pages) == 5
    assert len(state.drafts) == 5
    for key, res in state.step_status.items():
        assert res.status != StepStatus.FAILED, f"{key} failed: {res.issues}"
    assert not any(k.startswith("page_") for k in state.step_status), (
        "a page-level exception was swallowed by run_pipeline's try/except"
    )

    run_dir = tmp_path / "runs" / state.run_id

    # --- required artifacts exist -----------------------------------------
    assert (run_dir / "funnel_plan.json").exists()
    assert (run_dir / "p1.elementor.json").exists()
    assert (run_dir / "p1.preview.html").exists()
    assert (run_dir / "report.md").exists()
    assert (run_dir / "state.json").exists()

    gutenberg_files = sorted(run_dir.glob("p*.gutenberg.html"))
    # 1 hub + 3 soluções (a LP é Elementor, não Gutenberg)
    assert len(gutenberg_files) == 4, gutenberg_files
    non_p1 = [f for f in gutenberg_files if not f.name.startswith("p1.")]
    assert non_p1, "expected at least one non-P1 *.gutenberg.html artifact"

    # --- no Spanish leakage anywhere in the produced artifacts -------------
    all_text = "\n".join(
        p.read_text(encoding="utf-8") for p in run_dir.iterdir() if p.is_file()
    )
    for marker in _SPANISH_MARKERS:
        assert marker not in all_text, f"found Spanish marker {marker!r} in artifacts"

    # --- P1 elementor: the 3 buttons carry the 3 DISTINCT pre-sell -----------
    # destinations (honest funnel: one congruent CTA per angle, not the same
    # /rec link cloned onto every button).
    # (the template nests widgets inside inner containers -> walk recursively)
    elementor = json.loads((run_dir / "p1.elementor.json").read_text(encoding="utf-8"))

    def _walk(nodes):
        for n in nodes:
            if isinstance(n, dict):
                if n.get("widgetType"):
                    yield n
                yield from _walk(n.get("elements", []) or [])

    button_links = [w["settings"]["link"]["url"]
                    for w in _walk(elementor) if w.get("widgetType") == "button"]
    # DOIS HERÓIS: 6 widgets de botão para 3 destinos. O herói mobile mostra 2
    # acima da dobra, o desktop mostra 3, e o corpo repete o terceiro -- por
    # isso a lista repete, mas o CONJUNTO de destinos é exatamente 3.
    assert len(button_links) == 6, f"expected 6 LP buttons, got {button_links}"
    assert len(set(button_links)) == 3, f"devem existir 3 destinos: {button_links}"
    for href in button_links:
        assert "/rec" in href
    # HUB ÚNICO: o 1º botão de CADA herói leva ao hub (`-pr`) — >80% dos cliques
    # ficam no primeiro botão, então ele tem que ser o qualificador.
    assert button_links[0].rstrip("/").endswith("-pr"), button_links   # mobile
    assert button_links[1].rstrip("/").endswith("-p1"), button_links
    assert button_links[2].rstrip("/").endswith("-pr"), button_links   # desktop
    assert button_links[3].rstrip("/").endswith("-p1"), button_links
    assert button_links[4].rstrip("/").endswith("-p2"), button_links
    assert button_links[5].rstrip("/").endswith("-p2"), button_links   # corpo

    # --- SOLUTION chain is FORWARD-ONLY; the terminal only recirculates ------
    # The honest interior graph never loops back: each mid SOLUTION advances to
    # a HIGHER-ordinal solution and links the official channel (no cross-funnel
    # escape), while the LAST solution stops advancing and carries a single
    # cross_funnel exit -- no forward funnel edge, no external_official.
    solutions = sorted(
        (p for p in state.plan.pages if effective_role(p) is PageRole.SOLUTION),
        key=lambda p: p.ordinal,
    )
    assert [p.ordinal for p in solutions] == [1, 2, 3], solutions
    ordinal_by_slug = {p.slug: p.ordinal for p in solutions}
    *mids, terminal = solutions

    for page in mids:
        kinds = [r.kind for r in page.routes]
        assert "cross_funnel" not in kinds, (page.slug, kinds)      # mids never recirculate
        assert "external_official" in kinds, (page.slug, kinds)     # mids cite the official channel
        # E o canal oficial é o DEEP LINK QUE A PESQUISA DESTA PÁGINA TROUXE --
        # ligado tarde por `bind_official_route`, depois do step_research. Antes,
        # com a allowlist, o alvo vinha da configuração e um funil de outro tema
        # ganhava um CTA "canal oficial" apontando para o host genérico da lista.
        oficiais = [r.target for r in page.routes if r.kind == "external_official"]
        assert oficiais == [_OFFICIAL_URL], (page.slug, oficiais)
        funnel_edges = [r for r in page.routes if r.kind == "funnel"]
        assert funnel_edges, (page.slug, kinds)
        for route in funnel_edges:                                  # every funnel edge ADVANCES
            assert ordinal_by_slug[route.target] > page.ordinal, (page.slug, route.target)

    assert [r.kind for r in terminal.routes] == ["cross_funnel"], terminal.routes

    # --- ground-zero of every interior ad = a paragraph, never a button ------
    # `/rec` bodies must open with editorial copy (no CTA at the "marco-zero"
    # of the ad); the first Gutenberg block is always wp:paragraph.
    for gut in gutenberg_files:
        body = gut.read_text(encoding="utf-8").lstrip()
        assert body.startswith("<!-- wp:paragraph"), (gut.name, body[:80])
        first_block = body.split("<!-- /wp:", 1)[0]
        assert "wp:buttons" not in first_block, (gut.name, first_block[:80])


# --------------------------------------------------------------------------- #
# Task 10 (Parte B / B5): full run WITH official screenshots on
# --------------------------------------------------------------------------- #
def _solution_html_with_official_link(content: str) -> str:
    """SOLUTION body that weaves the OFFICIAL deep link inline (mirrors the real
    redator_pages "ensina o caminho com link real"), so step_screenshot has a
    URL to shoot AND step_publish has an anchor to embed the print right after.
    Opens with a wp:paragraph (marco-zero) and keeps per-slug-unique filler so
    uniqueness_state_guard never flags near-duplicate boilerplate."""
    headline_match = _HEADLINE_RE.search(content)
    headline = headline_match.group(1).strip() if headline_match else "pagina"
    topic = headline.lower()
    return (
        "<!-- wp:paragraph -->\n"
        f"<p>Conteúdo de utilidade pública sobre {headline}, com orientações "
        f"claras e verificadas sobre {topic} para o leitor. {_filler(headline)}</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:paragraph -->\n"
        f'<p>Confira no canal oficial: <a href="{_OFFICIAL_URL}">portal do '
        f"governo</a>.</p>\n"
        "<!-- /wp:paragraph -->\n\n"
        "<!-- wp:list -->\n"
        f'<ul class="wp-block-list"><li>Primeiro passo sobre {topic}, explicado '
        "com clareza.</li>"
        f"<li>Segundo passo sobre {topic}, detalhado para o leitor.</li></ul>\n"
        "<!-- /wp:list -->\n"
    )


def _responder_with_screenshots(model: str, messages: list[dict]) -> str:
    """Same scripted dispatch as `_responder`, but SOLUTION bodies (redator_pages
    -> 'PÁGINA INTERNA') carry the official deep link inline so the screenshot
    embed has a real anchor. PRESELL bodies keep the generic fake HTML."""
    content = messages[-1]["content"]
    if "PÁGINA INTERNA" in content:
        return _solution_html_with_official_link(content)
    return _responder(model, messages)


class _RecordingPublisher:
    """Fake WP publisher that records every created post/page and serves uploaded
    media a stable URL, so the smoke can assert the official screenshot was
    uploaded AND embedded after the matching link in the published SOLUTION body."""

    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.posts: list[dict] = []
        self.elementor_pages: list[dict] = []

    def upload_media(self, data, filename, mime="image/webp", alt=""):
        self.uploaded.append({"filename": filename, "mime": mime, "alt": alt})
        return {"id": 900 + len(self.uploaded),
                "source_url": f"https://creditoup.com.br/wp-content/uploads/{filename}"}

    def create_post(self, title, content, slug, status, post_type, featured_media=None):
        self.posts.append({"slug": slug, "content": content, "status": status})
        return {"id": 100 + len(self.posts)}

    def create_elementor_page(self, title, slug, elementor, status, post_type,
                              page_settings=None):
        self.elementor_pages.append({"slug": slug, "status": status})
        return {"id": 1}

    def set_yoast(self, post_id, post_type, fields, status=None):
        return {}

    def set_status(self, post_id, post_type, status):
        return {}


def test_full_funnel_publishes_with_official_screenshots(
    tmp_path: Path, config_files: Path
) -> None:
    """End-to-end WITH the Plano B screenshots on: flag `official_screenshots`
    plus a fake provider -> every SOLUTION captures its official deep link, and
    at publish the print is embedded right AFTER the official link in the post
    body -- all WITHOUT breaking the honest graph (still 1 LP + 3 PRESELL + 3
    SOLUTION, forward-only, terminal cross-only)."""
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    settings.run.official_screenshots = True
    settings.run.featured_image = False  # keep the interior image path out of the way
    llm = FakeLLM(responses=_responder_with_screenshots)
    runner = Runner(llm=llm, max_retries=settings.run.max_retries, runs_dir=tmp_path / "runs")
    publisher = _RecordingPublisher()
    deps = Deps(
        llm=llm,
        research=None,
        image_gen=None,
        image_proc=PillowImageProcessor(),
        publisher=publisher,
        loader=DocxBriefingLoader(),
        settings=settings,
        runner=runner,
        screenshot=FakeScreenshotProvider(),
    )
    briefing = tmp_path / "briefing.txt"
    briefing.write_text("Briefing completo do funil FGTS Saque-Aniversário.", encoding="utf-8")

    state = run_pipeline(briefing, deps, only=None, publish=True)

    # --- honest graph is intact: no step FAILED, still 7 pages / 3 pre-sells ---
    for key, res in state.step_status.items():
        assert res.status != StepStatus.FAILED, f"{key} failed: {res.issues}"
    assert not any(k.startswith("page_") for k in state.step_status), (
        "a page-level exception was swallowed by run_pipeline's try/except"
    )
    assert state.plan is not None
    assert len(state.plan.pages) == 5  # LP + 1 hub + 3 soluções
    presells = [p for p in state.plan.pages if effective_role(p) is PageRole.PRESELL]
    assert len(presells) == 1, presells
    solutions = [p for p in state.plan.pages if effective_role(p) is PageRole.SOLUTION]
    assert len(solutions) == 3, solutions

    # --- every SOLUTION captured its official deep link into a webp asset -------
    for sol in solutions:
        # A autorização do print é a pesquisa daquela página, guardada no estado
        # por `registrar_canais_oficiais` -- não existe mais lista no config.
        assert state.official_links.get(sol.page_number) == [_OFFICIAL_URL]
        shots = state.screenshots.get(sol.page_number) or []
        assert shots, f"solution {sol.slug} captured no official screenshot"
        assert shots[0]["url"] == _OFFICIAL_URL
        assert Path(shots[0]["path"]).exists()
        assert state.step_status[f"screenshot_p{sol.page_number}"].status is StepStatus.OK

    # --- the official screenshot was UPLOADED to WP media ----------------------
    assert publisher.uploaded, "official screenshot(s) should be uploaded to WP media"
    assert any(u["filename"].startswith("p") and u["filename"].endswith(".webp")
               for u in publisher.uploaded)

    # --- and EMBEDDED right after the official link in the published body -------
    sol_slugs = {p.slug for p in solutions}
    published_solutions = [p for p in publisher.posts if p["slug"] in sol_slugs]
    assert len(published_solutions) == 3, published_solutions
    embedded = [p for p in published_solutions if "wp:image" in p["content"]]
    assert embedded, "no SOLUTION post embedded the official screenshot"
    for post in embedded:
        body = post["content"]
        assert "Reprodução: site oficial (www.gov.br)" in body
        # the print lands AFTER the block that links to the official URL
        assert body.index(_OFFICIAL_URL) < body.index("wp:image"), post["slug"]
