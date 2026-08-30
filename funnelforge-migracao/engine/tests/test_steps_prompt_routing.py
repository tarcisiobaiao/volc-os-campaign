from pathlib import Path

import pytest

from funnelforge.config.settings import SiteConfig, load_settings
from funnelforge.domain.models import (
    FunnelPlan, Page, PageDraft, PageRole, ResearchFacts, RunState, StepResult,
    StepStatus, effective_role,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.doctrine import doctrine_context
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from funnelforge.pipeline.steps import (
    _prompt_name_for, _write_ctx, build_official_links, build_platform_links,
)
from funnelforge.prompts import render
from tests.fakes import FakeLLM


def test_prompt_name_by_role():
    lp = Page(page_number=1, page_type="LANDING PAGE", h1_title="t", slug="fgts")
    pr = Page(page_number=2, page_type="PRESELL", h1_title="t", slug="fgts-pr")
    sol = Page(page_number=3, page_type="SOLUTION", h1_title="t", slug="fgts-p1")
    assert _prompt_name_for(lp) == "redator_p1"
    assert _prompt_name_for(pr) == "redator_presell"
    assert _prompt_name_for(sol) == "redator_pages"


def test_prompt_name_follows_role_not_raw_page_type():
    """A HUB-typed page whose slug derives PRESELL/SOLUTION must still get
    the matching interior prompt -- role (not page_type) drives selection,
    same as pagespec/routing already do."""
    hub_presell = Page(page_number=2, page_type="HUB", h1_title="t", slug="fgts-pr")
    hub_solution = Page(page_number=3, page_type="HUB", h1_title="t", slug="fgts-p1")
    assert _prompt_name_for(hub_presell) == "redator_presell"
    assert _prompt_name_for(hub_solution) == "redator_pages"


# ---------------------------------------------------------------------------
# CARD-0004: build_official_links -- os canais externos que ESTA página pode
# usar. NÃO existe mais allowlist de host: a autorização vem da PESQUISA
# daquela página, em três camadas -- proveniência (sempre), verificação ao vivo
# no Chromium (fail-closed quando há browser) e sonda anti-anúncio (só reprova
# em detecção positiva). `official_preference` só ORDENA e `blocked_hosts` é
# denylist opcional; nenhum dos dois autoriza nada.
# ---------------------------------------------------------------------------


def _site(**kw) -> SiteConfig:
    """O site do funil. Repare que não há campo de allowlist para preencher:
    o `allowed_external` morreu, e é de propósito que um funil de tema novo
    (iFood, Serasa, Shopee) rode sem ninguém cadastrar domínio nenhum."""
    return SiteConfig(domain="https://creditoup.com.br", **kw)


def test_build_official_links_deduplica_mantem_ordem_e_limita_em_quatro():
    """Higiene estrutural do que a pesquisa devolveu: só https, só host com TLD,
    nunca o próprio site (isso é recirculação, não link externo), duplicata
    some, a ordem da pesquisa é preservada e o corte é em 4."""
    facts = ResearchFacts(fontes=[
        "https://meu.inss.gov.br/atualizar",
        "http://meu.inss.gov.br/inseguro",             # não é https -> fora
        "https://meu.inss.gov.br/atualizar",           # duplicata -> deduplicada
        "https://semtld/consulta",                     # host sem TLD -> fora
        "https://creditoup.com.br/rec/a-p1",           # o próprio site -> não é externo
        "https://www.caixa.gov.br/fgts",
        "https://servicos.dataprev.gov.br/consulta",
        "https://www.gov.br/pt-br/servicos/inss",      # 4º aprovado, encosta no cap
        "https://outro.gov.br/quinto",                 # 5º aprovado -> cortado pelo cap
    ])
    assert build_official_links(facts, _site(), verify=lambda u: True) == [
        "https://meu.inss.gov.br/atualizar",
        "https://www.caixa.gov.br/fgts",
        "https://servicos.dataprev.gov.br/consulta",
        "https://www.gov.br/pt-br/servicos/inss",
    ]


def test_build_official_links_sem_browser_fica_so_na_proveniencia():
    """Modo DEGRADADO documentado (dry run / playwright ausente): sem `verify` e
    sem `ad_probe` vale apenas a camada 1, proveniência -- tudo que a busca
    devolveu entra, inclusive um blog. Isso é consciente: era a allowlist que
    barrava por host, e era ela que reprovava o canal oficial de todo tema não
    governamental."""
    facts = ResearchFacts(fontes=["https://blog.aleatorio.com/materia",
                                  "https://entregador.ifood.com.br/cadastro"])
    assert build_official_links(facts, _site()) == [
        "https://blog.aleatorio.com/materia",
        "https://entregador.ifood.com.br/cadastro",
    ]


def test_build_official_links_com_verificador_falha_fechado():
    """Camada 2: havendo browser, URL que o Chromium não confirmou como página
    viva NÃO sai -- e verificador que explode conta como não confirmado."""
    facts = ResearchFacts(fontes=["https://blog.aleatorio.com/materia",
                                  "https://entregador.ifood.com.br/cadastro"])
    vivas = {"https://entregador.ifood.com.br/cadastro"}
    assert build_official_links(facts, _site(), verify=lambda u: u in vivas) == [
        "https://entregador.ifood.com.br/cadastro"]

    def _chromium_caiu(url: str) -> bool:
        raise RuntimeError("browser indisponível")

    assert build_official_links(facts, _site(), verify=_chromium_caiu) == []


def test_build_official_links_sonda_de_anuncio_so_reprova_em_deteccao_positiva():
    """Camada 3: o discriminador que substitui a allowlist sem virar outra lista
    -- quem vive de display disputa a MESMA sessão que você comprou, logo não é
    canal oficial. Mas a dúvida (`None`) e o erro da sonda NUNCA derrubam
    candidato: um falso positivo não pode zerar a única URL oficial da página."""
    facts = ResearchFacts(fontes=["https://portal-concorrente.com/fgts",
                                  "https://www.caixa.gov.br/fgts"])
    monetizacao = {"https://portal-concorrente.com/fgts": True,
                   "https://www.caixa.gov.br/fgts": None}      # None = não sei
    assert build_official_links(facts, _site(), verify=lambda u: True,
                                ad_probe=monetizacao.get) == [
        "https://www.caixa.gov.br/fgts"]

    def _sonda_quebrada(url: str) -> bool:
        raise RuntimeError("sem rede")

    assert build_official_links(facts, _site(), verify=lambda u: True,
                                ad_probe=_sonda_quebrada) == [
        "https://portal-concorrente.com/fgts", "https://www.caixa.gov.br/fgts"]


def test_build_official_links_preferencia_ordena_e_nunca_autoriza():
    """`official_preference` recebe o `official_source` da entidade do VOLC O.S.
    -- que é um NOME ("iFood"), não uma URL. Efeito único: desempate. O canal
    preferido sobe na fila, o não-preferido continua na lista, e um preferido
    que a pesquisa NÃO trouxe não vira link nenhum."""
    facts = ResearchFacts(fontes=["https://sindicato-entregadores.org.br/filiacao",
                                  "https://entregador.ifood.com.br/cadastro"])
    # sem preferência: manda a ordem da pesquisa
    assert build_official_links(facts, _site(), verify=lambda u: True) == [
        "https://sindicato-entregadores.org.br/filiacao",
        "https://entregador.ifood.com.br/cadastro"]
    # com a preferência do card, o canal da empresa fura a fila -- e o sindicato
    # SEGUE na lista (preferência ordena, não trava)
    assert build_official_links(facts, _site(official_preference=["iFood"]),
                                verify=lambda u: True) == [
        "https://entregador.ifood.com.br/cadastro",
        "https://sindicato-entregadores.org.br/filiacao"]
    # preferir não é ter evidência: sem pesquisa, nada é inventado
    assert build_official_links(ResearchFacts(sparse=True),
                                _site(official_preference=["iFood"])) == []


def test_build_official_links_blocked_hosts_e_denylist_do_operador():
    """`blocked_hosts` é a escotilha para matar um portal específico que a sonda
    deixou passar. É DENYLIST: não estar nela não autoriza ninguém."""
    facts = ResearchFacts(fontes=["https://portal.concorrente.com/fgts",
                                  "https://www.caixa.gov.br/fgts"])
    assert build_official_links(facts, _site(blocked_hosts=["concorrente.com"]),
                                verify=lambda u: True) == [
        "https://www.caixa.gov.br/fgts"]


def test_build_official_links_sem_pesquisa_devolve_vazio():
    """Configuração é preferência, não evidência: sem URL vinda da busca a
    página fica sem canal oficial e falha FECHADA depois, por ausência de prova
    -- nunca por o host estar fora de uma lista."""
    assert build_official_links(ResearchFacts(sparse=True), _site()) == []
    assert build_official_links(
        ResearchFacts(fontes=["nao e url", "", "   "]), _site()) == []


def test_build_official_links_nunca_promove_url_que_a_pesquisa_nao_trouxe():
    """O risco real não é o host errado, é o redator inventar um CAMINHO
    plausível num host legítimo. A comparação é URL a URL: `gov.br` ter
    aparecido na pesquisa não libera nenhum outro caminho em `*.gov.br`, nem
    quando a preferência nomeia justamente aquele órgão."""
    cpf = ("https://servicos.receita.fazenda.gov.br/servicos/cpf/"
           "consultasituacao/consultapublica.asp")
    facts = ResearchFacts(fontes=["https://www.gov.br/pt-br/servicos"])
    out = build_official_links(facts, _site(official_preference=["Receita Federal"]),
                               verify=lambda u: True)
    assert out == ["https://www.gov.br/pt-br/servicos"]
    assert cpf not in out


# ---------------------------------------------------------------------------
# FIX-3c: build_platform_links -- deep links COMERCIAIS, verificados no
# chromium (fail-closed), excluindo os canais já escolhidos como oficiais
# DESTA página (`official_links`, não mais a allowlist) e o próprio site.
# ---------------------------------------------------------------------------
_PLAT_FACTS = ResearchFacts(
    fontes=["https://www.jeitto.com.br/", "https://gov.br/receita",
            "https://creditoup.com.br/algo", "https://supersim.com.br/emprestimo"],
    dados_validados=[{"fato": "x", "fonte": "https://velotax.com.br/"}])

# a escolha oficial DESTA página (o que `build_official_links` devolveu), que é
# o que agora separa "oficial" de "plataforma comercial"
_OFICIAIS = ["https://gov.br/receita"]


def test_build_platform_links_verified_only_excludes_official_and_site():
    out = build_platform_links(_PLAT_FACTS, _OFICIAIS, "https://creditoup.com.br",
                               verify=lambda u: True)
    # o canal oficial desta página e o host do próprio site saem; sobram as 3
    # plataformas, na ordem das fontes (fontes primeiro, depois dados_validados).
    assert [p["host"] for p in out] == [
        "www.jeitto.com.br", "supersim.com.br", "velotax.com.br"]


def test_build_platform_links_fail_closed_without_verifier():
    # No chromium verifier -> nothing is emitted (a link we cannot confirm is a
    # live page never gets linked -- the human's rule).
    assert build_platform_links(_PLAT_FACTS, _OFICIAIS, "https://creditoup.com.br") == []


def test_build_platform_links_drops_unverified_url():
    # verifier rejects supersim (e.g. 404/parking) -> only jeitto + velotax kept.
    out = build_platform_links(_PLAT_FACTS, _OFICIAIS, "https://creditoup.com.br",
                               verify=lambda u: "supersim" not in u)
    assert [p["host"] for p in out] == ["www.jeitto.com.br", "velotax.com.br"]


def test_build_platform_links_caps():
    facts = ResearchFacts(fontes=[f"https://p{i}.com.br/" for i in range(6)])
    out = build_platform_links(facts, [], "https://site.com", verify=lambda u: True, cap=4)
    assert len(out) == 4


def test_redator_pages_renders_verified_platform_links_block():
    plats = [{"host": "jeitto.com.br", "url": "https://jeitto.com.br/emprestimo"}]
    out = render("redator_pages", role="SOLUTION", headline="Empréstimo Pix",
                 objective="o", skeleton="- H2: a", keywords="pix", facts="{}",
                 domain="https://creditoup.com.br", author_name="Equipe",
                 author_credential="c", cnpj="00.000.000/0001-00",
                 platform_links=plats, **doctrine_context())
    assert "https://jeitto.com.br/emprestimo" in out
    assert "nofollow sponsored" in out
    low = out.lower()
    assert "acesse a plataforma da instituição parceira" in low  # named as the BANNED example
    # without platform links -> the "name only, never invent a URL" guidance
    out_empty = render("redator_pages", role="SOLUTION", headline="Empréstimo Pix",
                       objective="o", skeleton="- H2: a", keywords="pix", facts="{}",
                       domain="https://creditoup.com.br", author_name="Equipe",
                       author_credential="c", cnpj="00.000.000/0001-00",
                       platform_links=[], **doctrine_context())
    assert "nunca invente urls comerciais" in out_empty.lower()


# ---------------------------------------------------------------------------
# CARD-0004: redator_pages.jinja <links_oficiais> -- present vs empty.
# ---------------------------------------------------------------------------

_SOLUTION_RENDER_COMMON = dict(
    role="SOLUTION", headline="Saque-aniversário do FGTS", objective="o",
    skeleton="- H2: a", keywords="fgts", facts="{}",
    domain="https://creditoup.com.br", author_name="Equipe", author_credential="c",
    cnpj="00.000.000/0001-00",
    routes=[{"kind": "external_official", "anchor": "Consultar no canal oficial >>>",
             "href": "https://gov.br"}],
)


def test_redator_pages_renders_official_deep_links_when_present():
    out = render("redator_pages",
                 official_links=["https://meu.inss.gov.br/atualizacao-cadastral",
                                 "https://www.caixa.gov.br/fgts"],
                 **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    # each provided deep link is emitted verbatim for the writer to anchor
    assert "https://meu.inss.gov.br/atualizacao-cadastral" in out
    assert "https://www.caixa.gov.br/fgts" in out
    # inline-text CTA with a nominal descriptive anchor, never a button
    assert "descrição nominal" in low
    assert "nunca botões" in low
    assert "2 a 4 links oficiais" in low
    # official links do NOT replace the graph's external_official route
    assert "external_official" in out


def test_redator_pages_official_links_empty_keeps_current_behavior():
    out_empty = render("redator_pages", official_links=[],
                       **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low_empty = out_empty.lower()
    assert "sem deep links oficiais" in low_empty
    assert "congruência oficial" not in low_empty
    # omitted entirely (jinja default []) behaves like an explicit empty list
    out_missing = render("redator_pages", **_SOLUTION_RENDER_COMMON, **doctrine_context())
    assert "sem deep links oficiais" in out_missing.lower()


# ---------------------------------------------------------------------------
# CARD-0012 (REQ-3 + OVERRIDE-3): the passo a passo has to be "certeiro" --
# each pain-resolving numbered step states WHAT to do AND links WHERE to do
# it (the exact official deep link), not just a generic step-by-step gated
# only by a link count; and every SOLUTION page demands >=3 H2 sections so
# the CARD-0013 widget injector (positions before the 3rd H2) never falls
# through to the end of the page. Proven on the RENDER, never on LLM output.
# ---------------------------------------------------------------------------


def test_redator_pages_demands_pain_resolving_step_carries_exact_deep_link():
    out = render("redator_pages",
                 official_links=["https://meu.inss.gov.br/atualizacao-cadastral",
                                 "https://www.caixa.gov.br/fgts"],
                 **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    # the concrete "certeiro" doctrine: WHAT to do + WHERE to do it, together
    assert "passo certeiro" in low
    assert "o que fazer" in low
    assert "onde fazer" in low
    # nominal, substantive-first anchors stay intact, now also banning "clique aqui"
    assert "substantivo primeiro" in low
    assert "clique aqui" in low


def test_redator_pages_official_anchor_is_nominal_and_bans_execution_verbs():
    """Section-2 invariant (briefing 'DECISÕES JÁ FECHADAS'): the official-link
    anchor is a NOMINAL description of the destination, never opening with an
    execution verb ('Consultar', 'Solicitar', 'Acessar', ...) -- that ban is
    `banned_cta_execution` territory for buttons, and the writer doctrine
    mirrors the same rule for the inline official-link anchor specifically."""
    out = render("redator_pages",
                 official_links=["https://meu.inss.gov.br/atualizacao-cadastral"],
                 **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    assert "verbo de execução" in low
    assert "descrição nominal" in low
    assert "substantivo primeiro" in low


def test_redator_pages_requires_minimum_three_h2_sections():
    """OVERRIDE-3: the >=3 H2 structural floor is unconditional -- present
    even when this page has no official deep links to weave in."""
    out = render("redator_pages", official_links=[],
                 **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    assert "no mínimo 3 seções h2" in low


# ---------------------------------------------------------------------------
# Task 8: _write_ctx injects solution_order + is_terminal; the PRESELL writer
# receives angle + lead_solution.
# ---------------------------------------------------------------------------


def _forward_plan() -> FunnelPlan:
    return FunnelPlan(total_pages=5, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Consulta", slug="a"),
        Page(page_number=2, page_type="HUB", h1_title="Ja tenho direito?", slug="a-pr1",
             role=PageRole.PRESELL),
        Page(page_number=3, page_type="SOLUTION", h1_title="Passo 1", slug="a-p1", ordinal=1),
        Page(page_number=4, page_type="SOLUTION", h1_title="Passo 2", slug="a-p2", ordinal=2),
        Page(page_number=5, page_type="SOLUTION", h1_title="Passo 3", slug="a-p3", ordinal=3),
    ])


def _deps(config_files: Path, llm: FakeLLM) -> Deps:
    settings = load_settings(config_files / ".env", config_files / "config.yaml")
    runner = Runner(llm=llm, max_retries=0, runs_dir=config_files / "runs")
    return Deps(llm=llm, research=None, image_gen=None, image_proc=None,
                publisher=None, loader=None, settings=settings, runner=runner)


def test_write_ctx_solution_order_and_is_terminal(config_files: Path) -> None:
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan = _forward_plan()
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan
    by = {p.slug: p for p in plan.pages}

    mid_ctx = _write_ctx(state, by["a-p2"], deps)
    assert mid_ctx["solution_order"] == {"a-p1": 1, "a-p2": 2, "a-p3": 3}
    assert mid_ctx["is_terminal"] is False

    term_ctx = _write_ctx(state, by["a-p3"], deps)
    assert term_ctx["solution_order"] == {"a-p1": 1, "a-p2": 2, "a-p3": 3}
    assert term_ctx["is_terminal"] is True


def test_presell_write_receives_qualifier_lens_and_questions_not_angle(
        config_files: Path, monkeypatch) -> None:
    """CARD-0009: `step_write`'s presell branch stops passing `angle`/
    `lead_solution` and instead passes a NEUTRAL `qualifier_lens` (fixed by the
    -prN index) + `qualifier_questions` derived from the plan's solutions in the
    hub's rotated route order."""
    from funnelforge.pipeline.routing import build_funnel_routes

    # write_page returns valid gutenberg; judge approves.
    llm = FakeLLM(responses=[
        "<!-- wp:paragraph -->\n<p>Texto.</p>\n<!-- /wp:paragraph -->",
        '{"approved": true}',
    ])
    deps = _deps(config_files, llm)
    plan = _forward_plan()
    build_funnel_routes(plan, deps.settings)   # populate rotated routes
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan

    calls: list[tuple[str, dict]] = []
    real_render = st.render

    def _capture(name: str, **kw):
        calls.append((name, kw))
        return real_render(name, **kw)

    monkeypatch.setattr(st, "render", _capture)

    presell = {p.slug: p for p in plan.pages}["a-pr1"]
    # PRÉ-VOO (Frente 3): `pagespec` roda agora ANTES da redação, sobre as rotas.
    # Os H1s sintéticos "Passo N" não têm nenhum token significativo ("passo" é
    # palavra de parada), então NENHUMA âncora os descreve e `anchor_congruent`
    # reprova -- reprovação de ROTA, que reescrever nunca conserta. Este teste é
    # sobre a FIAÇÃO DO PROMPT, então dá ao grafo H1s e âncoras válidos.
    h1_por_slug = {"a-p1": "Consultar o Saldo", "a-p2": "Solicitar o Saque",
                   "a-p3": "Prazos do Pagamento"}
    for p in plan.pages:
        if p.slug in h1_por_slug:
            p.h1_title = h1_por_slug[p.slug]
    for r in presell.routes:
        if r.target in h1_por_slug:
            r.anchor = f"Ver: {h1_por_slug[r.target]}"

    st.step_write(state, presell, deps)

    presell_calls = [kw for name, kw in calls if name == "redator_presell"]
    assert presell_calls, "redator_presell prompt was not rendered"
    kw = presell_calls[0]
    # the removed angle/lead_solution kwargs are gone
    assert "angle" not in kw
    assert "lead_solution" not in kw
    # neutral qualifier lens fixed by index (-pr1 -> first lens)
    assert kw["qualifier_lens"] == "qual é a sua situação hoje?"
    # qualifier questions derived from the solutions, in the hub's route order
    questions = kw["qualifier_questions"]
    assert [q["solucao"] for q in questions] == [
        "Consultar o Saldo", "Solicitar o Saque", "Prazos do Pagamento"]
    assert all(q["caso"] for q in questions)


# ---------------------------------------------------------------------------
# CARD-0009: expand_presell_hubs -- mechanical, deterministic expansion of the
# single mapped PRESELL into 3 NEUTRAL hubs (-pr1/-pr2/-pr3). Replaces the
# removed creative synthesize_angles step (Opção A). No LLM, no random.
# ---------------------------------------------------------------------------


def _mapped_plan(n_solutions: int = 3) -> FunnelPlan:
    pages = [
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Consulta FGTS",
             slug="consulta-fgts"),
        Page(page_number=2, page_type="HUB", h1_title="Guia FGTS", slug="consulta-fgts-pr"),
    ]
    for i in range(1, n_solutions + 1):
        pages.append(Page(page_number=2 + i, page_type="SOLUTION",
                          h1_title=f"Solucao {i}", slug=f"consulta-fgts-p{i}"))
    return FunnelPlan(total_pages=len(pages), pages=pages)


def test_expand_presell_hubs_creates_three_neutral_distinct_hubs(config_files: Path) -> None:
    deps = _deps(config_files, FakeLLM(responses=[]))
    deps.settings.run.presell_hubs = 3          # modo antigo, explícito
    state = RunState(run_id="consulta-fgts-20260720-101010", briefing_text="brief")
    state.plan = _mapped_plan(3)

    st.expand_presell_hubs(state, deps)

    presells = [p for p in state.plan.pages if effective_role(p) is PageRole.PRESELL]
    assert {p.slug for p in presells} == {
        "consulta-fgts-pr1", "consulta-fgts-pr2", "consulta-fgts-pr3"}
    # h1 variants are materially distinct (anti-doorway: never 3 identical H1s)
    h1s = [p.h1_title for p in presells]
    assert len(set(h1s)) == 3, h1s
    # roles set explicitly + ordinals populated on the real solutions
    by = {p.slug: p for p in state.plan.pages}
    assert by["consulta-fgts-pr1"].role is PageRole.PRESELL
    assert by["consulta-fgts-p1"].ordinal == 1 and by["consulta-fgts-p3"].ordinal == 3
    # the single old PRESELL was replaced, page numbers stay unique
    assert "consulta-fgts-pr" not in {p.slug for p in state.plan.pages}
    nums = [p.page_number for p in state.plan.pages]
    assert len(nums) == len(set(nums))
    # no angle/lead subsystem residue on the clones
    for p in presells:
        assert not hasattr(p, "angle")
        assert not hasattr(p, "lead_solution_slug")


def test_expand_presell_hubs_raises_when_fewer_than_three_solutions(
        config_files: Path) -> None:
    deps = _deps(config_files, FakeLLM(responses=[]))
    deps.settings.run.presell_hubs = 3          # a trava de >=3 é do modo 3 hubs
    state = RunState(run_id="x-20260720-101010", briefing_text="brief")
    state.plan = _mapped_plan(2)
    with pytest.raises(ValueError):
        st.expand_presell_hubs(state, deps)


# ---------------------------------------------------------------------------
# HUB ÚNICO (run.presell_hubs=1, o padrão): não clona nada. A LP passa a abrir
# com o hub no primeiro botão e mandar os demais direto para as soluções.
# ---------------------------------------------------------------------------


def test_hub_unico_nao_clona_e_normaliza_o_slug(config_files: Path) -> None:
    deps = _deps(config_files, FakeLLM(responses=[]))
    assert deps.settings.run.presell_hubs == 1, "o padrão precisa ser 1 hub"
    state = RunState(run_id="consulta-fgts-20260720-101010", briefing_text="brief")
    state.plan = _mapped_plan(3)

    st.expand_presell_hubs(state, deps)

    presells = [p for p in state.plan.pages if effective_role(p) is PageRole.PRESELL]
    assert [p.slug for p in presells] == ["consulta-fgts-pr"]
    # nenhum clone -pr1/-pr2/-pr3 foi criado
    assert not [p for p in state.plan.pages if p.slug.rstrip("0123456789").endswith("-pr")
                and p.slug != "consulta-fgts-pr"]
    # ordinais das soluções continuam populados
    by = {p.slug: p for p in state.plan.pages}
    assert by["consulta-fgts-p1"].ordinal == 1 and by["consulta-fgts-p3"].ordinal == 3
    nums = [p.page_number for p in state.plan.pages]
    assert len(nums) == len(set(nums))


def test_hub_unico_aceita_duas_solucoes_mas_nao_uma(config_files: Path) -> None:
    """Com 3 hubs eram necessárias >=3 soluções (um destino por hub). Com hub
    único bastam 2: uma para avançar e uma terminal."""
    deps = _deps(config_files, FakeLLM(responses=[]))
    state = RunState(run_id="x-20260720-101010", briefing_text="brief")
    state.plan = _mapped_plan(2)
    st.expand_presell_hubs(state, deps)          # não levanta
    assert len([p for p in state.plan.pages
                if effective_role(p) is PageRole.SOLUTION]) == 2

    state.plan = _mapped_plan(1)
    with pytest.raises(ValueError):
        st.expand_presell_hubs(state, deps)


def test_expand_presell_hubs_is_deterministic(config_files: Path) -> None:
    """No LLM, no random -> two runs on identical input yield identical slugs
    AND identical h1 variants (resume-safe)."""
    deps = _deps(config_files, FakeLLM(responses=[]))

    def _run():
        state = RunState(run_id="consulta-fgts-20260720-101010")
        state.plan = _mapped_plan(3)
        st.expand_presell_hubs(state, deps)
        return [(p.slug, p.h1_title) for p in state.plan.pages
                if effective_role(p) is PageRole.PRESELL]

    assert _run() == _run()


# ---------------------------------------------------------------------------
# CARD-0009: presell_hub_distinction_guard -- state hook comparing the run's 3
# presell drafts. Fails the write when two hubs are materially identical (their
# qualifier+preview body, not just the first line) OR when the SAME solution
# opens the choice block of every hub (hero not neutral).
# ---------------------------------------------------------------------------


def _hub_plan_and_state() -> tuple[FunnelPlan, RunState]:
    plan = FunnelPlan(total_pages=7, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Consulta", slug="a"),
        Page(page_number=2, page_type="PRESELL", h1_title="Hub 1", slug="a-pr1"),
        Page(page_number=3, page_type="PRESELL", h1_title="Hub 2", slug="a-pr2"),
        Page(page_number=4, page_type="PRESELL", h1_title="Hub 3", slug="a-pr3"),
        Page(page_number=5, page_type="SOLUTION", h1_title="Passo 1", slug="a-p1", ordinal=1),
        Page(page_number=6, page_type="SOLUTION", h1_title="Passo 2", slug="a-p2", ordinal=2),
        Page(page_number=7, page_type="SOLUTION", h1_title="Passo 3", slug="a-p3", ordinal=3),
    ])
    state = RunState(run_id="a-20260720-101010")
    state.plan = plan
    for n in (2, 3, 4):
        state.step_status[f"write_p{n}"] = StepResult(
            step=f"write_p{n}", status=StepStatus.OK, attempts=1)
    return plan, state


def _hub_draft(n: int, opener: str, body: str) -> PageDraft:
    content = (f"<!-- wp:paragraph -->\n<p><strong>{opener}</strong></p>\n"
               f"<!-- /wp:paragraph -->\n{body}")
    return PageDraft(page_number=n, page_type="PRESELL", format="gutenberg",
                     content=content, word_count=1)


def test_presell_hub_distinction_guard_fails_near_identical_hubs(
        config_files: Path) -> None:
    """3 hubs identical EXCEPT the opening CTA line -> the qualifier+preview
    body is materially identical -> the write fails (guard sees past line 1)."""
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan, state = _hub_plan_and_state()
    shared_body = (
        "<!-- wp:list -->\n<ul class=\"wp-block-list\">"
        "<li>Passo detalhado sobre consulta de saldo, calendario e prazos oficiais.</li>"
        "<li>Explicacao clara sobre bancos, regras e quitacao do beneficio informado.</li>"
        "</ul>\n<!-- /wp:list -->\n")
    for n, opener in ((2, "Toque na opcao certa e comece um."),
                      (3, "Toque na opcao certa e comece dois."),
                      (4, "Toque na opcao certa e comece tres.")):
        state.drafts[n] = _hub_draft(n, opener, shared_body)

    st.presell_hub_distinction_guard(state, plan.pages[3], deps)   # last hub (a-pr3)

    res = state.step_status["write_p4"]
    assert res.status is StepStatus.FAILED
    assert "hub_not_distinct" in {i.code for i in res.issues}


def test_presell_hub_distinction_guard_passes_distinct_hubs(config_files: Path) -> None:
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan, state = _hub_plan_and_state()
    for n, topic in ((2, "consulta"), (3, "bancos"), (4, "prazos")):
        uniq = " ".join(f"exclusivo{topic}{i:03d}" for i in range(40))
        body = (f"<!-- wp:list -->\n<ul class=\"wp-block-list\"><li>{uniq}</li></ul>\n"
                "<!-- /wp:list -->\n")
        state.drafts[n] = _hub_draft(n, f"Toque na opcao certa {topic}.", body)

    st.presell_hub_distinction_guard(state, plan.pages[3], deps)

    assert state.step_status["write_p4"].status is StepStatus.OK


def test_presell_hub_distinction_guard_honors_hub_threshold(config_files: Path) -> None:
    """FGTS outage fix: 3 NEUTRAL hubs preview the SAME 3 solutions and SHARE that
    vocabulary by design -- not a doorway. The guard must judge them by the
    dedicated hub_distinction_threshold, NOT the strict 0.35 (which blocked pr3 on
    the all-FGTS funnel). Proven threshold-relative: the SAME hub pair passes just
    ABOVE its Jaccard and fails just BELOW, so the lenient default (0.6) passes a
    real ~0.4 neutral pair while a near-identical copy-paste hub still fails."""
    from funnelforge.pipeline.uniqueness import jaccard
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan, state = _hub_plan_and_state()
    shared = " ".join(f"solucaovocab{i:03d}" for i in range(40))  # shared preview vocab
    for n, fr in ((2, "aaa"), (3, "bbb"), (4, "ccc")):
        uniq = " ".join(f"{fr}frame{i:03d}" for i in range(12))   # distinct framing
        body = (f"<!-- wp:list -->\n<ul class=\"wp-block-list\">"
                f"<li>{shared} {uniq}</li></ul>\n<!-- /wp:list -->\n")
        state.drafts[n] = _hub_draft(n, f"Toque {fr}.", body)
    j = jaccard(state.drafts[3].content, state.drafts[4].content)
    assert j > 0.1, f"setup: neutral hubs must share vocabulary, got jaccard {j}"
    # threshold ABOVE the pair's Jaccard -> PASS (the lenient hub bar)
    deps.settings.uniqueness.hub_distinction_threshold = j + 0.1
    st.presell_hub_distinction_guard(state, plan.pages[3], deps)
    assert state.step_status["write_p4"].status is StepStatus.OK
    # SAME content, threshold BELOW the Jaccard -> FAIL (proves the knob governs)
    plan2, state2 = _hub_plan_and_state()
    for n in (2, 3, 4):
        state2.drafts[n] = state.drafts[n]
    deps.settings.uniqueness.hub_distinction_threshold = max(0.01, j - 0.1)
    st.presell_hub_distinction_guard(state2, plan2.pages[3], deps)
    assert state2.step_status["write_p4"].status is StepStatus.FAILED


def test_presell_hub_distinction_guard_fails_when_same_solution_opens_all(
        config_files: Path) -> None:
    """Distinct bodies, but EVERY hub opens its choice block with a-p1 -> hero
    is not neutral -> the write fails."""
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan, state = _hub_plan_and_state()
    for n, topic in ((2, "consulta"), (3, "bancos"), (4, "prazos")):
        uniq = " ".join(f"exclusivo{topic}{i:03d}" for i in range(40))
        body = (
            "<!-- wp:buttons --><div class=\"wp-block-buttons\">"
            "<a href=\"https://creditoup.com.br/rec/a-p1\">um</a>"
            "<a href=\"https://creditoup.com.br/rec/a-p2\">dois</a>"
            "<a href=\"https://creditoup.com.br/rec/a-p3\">tres</a>"
            "</div><!-- /wp:buttons -->\n"
            f"<!-- wp:list -->\n<ul class=\"wp-block-list\"><li>{uniq}</li></ul>\n"
            "<!-- /wp:list -->\n")
        state.drafts[n] = _hub_draft(n, f"Toque {topic}.", body)

    st.presell_hub_distinction_guard(state, plan.pages[3], deps)

    res = state.step_status["write_p4"]
    assert res.status is StepStatus.FAILED
    assert "hub_hero_not_neutral" in {i.code for i in res.issues}


# ---------------------------------------------------------------------------
# CARD-0011 REQ-2: step_write feeds the writer the H1/theme of EACH forward
# destination (next_solutions, mid) / the cross_funnel label (terminal), and
# _write_ctx exposes sibling_h1s so cta_destination_congruent can compute the
# distinctive token by subtraction. redator_pages demands a pre-CTA bridge +
# copy that ANNOUNCES the real destination, and drops the incongruent exemplar.
# ---------------------------------------------------------------------------


def _fanout_plan() -> FunnelPlan:
    """1 LP + 3 neutral presell hubs + 3 SOLUTION with distinctive H1s and
    objectives, so build_funnel_routes gives the mid solution a fan-out forward
    graph and the terminal a cross_funnel exit."""
    return FunnelPlan(total_pages=7, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Consulta FGTS", slug="a"),
        Page(page_number=2, page_type="PRESELL", h1_title="Hub 1", slug="a-pr1",
             role=PageRole.PRESELL),
        Page(page_number=3, page_type="PRESELL", h1_title="Hub 2", slug="a-pr2",
             role=PageRole.PRESELL),
        Page(page_number=4, page_type="PRESELL", h1_title="Hub 3", slug="a-pr3",
             role=PageRole.PRESELL),
        Page(page_number=5, page_type="SOLUTION", h1_title="Consultar o saldo pelo app",
             slug="a-p1", ordinal=1, emotional_objective="clareza sobre o saldo"),
        Page(page_number=6, page_type="SOLUTION", h1_title="Saque-rescisao apos demissao",
             slug="a-p2", ordinal=2, emotional_objective="entender a rescisao"),
        Page(page_number=7, page_type="SOLUTION", h1_title="Saque-aniversario antecipado",
             slug="a-p3", ordinal=3, emotional_objective="antecipar o aniversario"),
    ])


def test_write_ctx_exposes_sibling_h1s(config_files: Path) -> None:
    """_write_ctx exposes sibling_h1s = H1 of ALL solutions of the funnel, so
    the congruence validator can subtract the siblings to find the distinctive
    token of each destination."""
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan = _fanout_plan()
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan
    ctx = _write_ctx(state, {p.slug: p for p in plan.pages}["a-p1"], deps)
    assert ctx["sibling_h1s"] == {
        "a-p1": "Consultar o saldo pelo app",
        "a-p2": "Saque-rescisao apos demissao",
        "a-p3": "Saque-aniversario antecipado",
    }


def test_write_ctx_presell_gets_lenient_uniqueness_threshold(config_files: Path) -> None:
    """FGTS outage (3rd site): the `uniqueness` VALIDATOR compares to prior drafts
    at ctx['jaccard_threshold']. A PRESELL hub only collides with the OTHER
    neutral hubs (shared solution vocabulary by design), so _write_ctx hands it
    the lenient hub_distinction_threshold; SOLUTION/LP keep the strict one -- so
    the validator can't block a 0.36 hub pair the state guards already accept."""
    deps = _deps(config_files, FakeLLM(responses=[]))
    plan, state = _hub_plan_and_state()
    by = {p.slug: p for p in plan.pages}
    hub_ctx = _write_ctx(state, by["a-pr2"], deps)
    sol_ctx = _write_ctx(state, by["a-p1"], deps)
    assert hub_ctx["jaccard_threshold"] == deps.settings.uniqueness.hub_distinction_threshold
    assert sol_ctx["jaccard_threshold"] == deps.settings.uniqueness.jaccard_threshold
    assert hub_ctx["jaccard_threshold"] > sol_ctx["jaccard_threshold"]


def _capture_render(monkeypatch) -> list:
    calls: list = []
    real_render = st.render

    def _capture(name: str, **kw):
        calls.append((name, kw))
        return real_render(name, **kw)

    monkeypatch.setattr(st, "render", _capture)
    return calls


def test_step_write_mid_solution_passes_next_solutions_to_render(
        config_files: Path, monkeypatch) -> None:
    from funnelforge.pipeline.routing import build_funnel_routes

    llm = FakeLLM(responses=[
        "<!-- wp:paragraph -->\n<p>Texto.</p>\n<!-- /wp:paragraph -->",
        '{"approved": true}',
    ])
    deps = _deps(config_files, llm)
    plan = _fanout_plan()
    build_funnel_routes(plan, deps.settings)
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan

    calls = _capture_render(monkeypatch)
    mid = {p.slug: p for p in plan.pages}["a-p1"]
    # O PRÉ-VOO barra a escrita quando não há canal oficial: `official_link_density`
    # seria impossível de satisfazer e escrever custaria até 3 redações por uma
    # reprovação que não depende do texto. Este teste é sobre outra coisa, então
    # entregamos o insumo que a pesquisa entregaria.
    state.facts[mid.page_number] = ResearchFacts(
        resumo="base", fontes=["https://www.gov.br/pagina-oficial"])
    state.official_links[mid.page_number] = ["https://www.gov.br/pagina-oficial"]
    st.step_write(state, mid, deps)

    pages_calls = [kw for name, kw in calls if name == "redator_pages"]
    assert pages_calls, "redator_pages prompt was not rendered"
    kw = pages_calls[0]
    ns = kw["next_solutions"]
    # ordered forward destinations, each {slug, h1, objective}
    assert [s["slug"] for s in ns] == ["a-p2", "a-p3"]
    assert [s["h1"] for s in ns] == ["Saque-rescisao apos demissao", "Saque-aniversario antecipado"]
    assert ns[0]["objective"] == "entender a rescisao"
    assert all({"slug", "h1", "objective"} <= set(s) for s in ns)


def test_step_write_solution_keeps_has_script_gate_with_widgets_enabled(
        config_files: Path) -> None:
    """CARD-0015 widget-isolation coverage: turning `run.widgets_enabled` ON
    must NOT loosen the WRITER's own write-time `has_script` gate. The widget
    subsystem's separate, sanitized <script> path (step_widget, gated after
    build) is fully isolated from step_write's validator battery -- a raw
    <script> the writer sneaks into the article body is still rejected."""
    from funnelforge.pipeline.routing import build_funnel_routes

    scripted = ("<!-- wp:paragraph -->\n<p>Texto.</p>\n<!-- /wp:paragraph -->"
                "<script>alert(1)</script>")
    llm = FakeLLM(responses=[scripted, '{"approved": true}'])
    deps = _deps(config_files, llm)
    deps.settings.run.widgets_enabled = True
    plan = _fanout_plan()
    build_funnel_routes(plan, deps.settings)
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan

    mid = {p.slug: p for p in plan.pages}["a-p1"]
    # Insumo mínimo para a página passar do PRÉ-VOO e chegar ao assunto DESTE
    # teste. Sem canal oficial ela falharia antes de escrever, por
    # `official_link_density`, e o `has_script` nunca seria exercido — o teste
    # continuaria verde medindo outra coisa, que é o pior desfecho possível.
    state.facts[mid.page_number] = ResearchFacts(
        resumo="base", fontes=["https://www.gov.br/pagina-oficial"])
    state.official_links[mid.page_number] = ["https://www.gov.br/pagina-oficial"]
    st.step_write(state, mid, deps)

    res = state.step_status[f"write_p{mid.page_number}"]
    assert res.status is StepStatus.FAILED
    assert any(i.code == "has_script" for i in res.issues)


def test_step_write_solution_passes_objective_facts_and_official_links_together(
        config_files: Path, monkeypatch) -> None:
    """CARD-0012 AC2: the dor(pain)->deep-link mapping the 'passo certeiro'
    doctrine needs is already wired end-to-end -- `objective` (the page's
    declared pain/goal), `facts` (research resumo/passo_a_passo) and
    `official_links` (the vetted deep links from build_official_links) all
    reach the SAME redator_pages render call, so the writer can bind each
    pain-resolving step to its matching official destination. No new route,
    no touching build_funnel_routes/the graph."""
    from funnelforge.pipeline.routing import build_funnel_routes

    llm = FakeLLM(responses=[
        "<!-- wp:paragraph -->\n<p>Texto.</p>\n<!-- /wp:paragraph -->",
        '{"approved": true}',
    ])
    deps = _deps(config_files, llm)
    plan = _fanout_plan()
    build_funnel_routes(plan, deps.settings)
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan
    state.facts[5] = ResearchFacts(
        resumo="Consulta de saldo do FGTS pelo aplicativo oficial.",
        passo_a_passo=["Abra o app FGTS", "Toque em Extrato"],
        fontes=["https://www.caixa.gov.br/fgts"])

    calls = _capture_render(monkeypatch)
    mid = {p.slug: p for p in plan.pages}["a-p1"]
    # O canal oficial que a pesquisa DESTE teste trouxe, registrado como
    # `registrar_canais_oficiais` faria — sem isto o pré-voo barra a escrita por
    # `official_link_density`, que é impossível de satisfazer sem canal.
    state.official_links[mid.page_number] = ["https://www.caixa.gov.br/fgts"]
    st.step_write(state, mid, deps)

    kw = [kw for name, kw in calls if name == "redator_pages"][0]
    assert kw["objective"] == "clareza sobre o saldo"
    assert "Consulta de saldo do FGTS" in kw["facts"]
    assert kw["official_links"] == ["https://www.caixa.gov.br/fgts"]


def test_step_write_terminal_solution_passes_cross_funnel_label_to_render(
        config_files: Path, monkeypatch) -> None:
    from funnelforge.pipeline.routing import build_funnel_routes

    llm = FakeLLM(responses=[
        "<!-- wp:paragraph -->\n<p>Texto.</p>\n<!-- /wp:paragraph -->",
        '{"approved": true}',
    ])
    deps = _deps(config_files, llm)
    plan = _fanout_plan()
    build_funnel_routes(plan, deps.settings)
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan

    calls = _capture_render(monkeypatch)
    terminal = {p.slug: p for p in plan.pages}["a-p3"]
    st.step_write(state, terminal, deps)

    kw = [kw for name, kw in calls if name == "redator_pages"][0]
    # terminal recirculates cross-funnel -> the writer gets the cross_funnel
    # label; there is no forward destination to announce.
    assert kw["next_solutions"] == []
    assert kw["cross_funnel_label"]
    cross = next(r for r in terminal.routes if r.kind == "cross_funnel")
    assert kw["cross_funnel_label"] == cross.anchor


def test_redator_pages_demands_bridge_and_destination_announce(config_files: Path) -> None:
    """AC3: the prompt surfaces each destination H1, demands a pre-CTA bridge +
    button copy that announces the real destination, and no longer ships the
    incongruent open-loop exemplar."""
    out = render(
        "redator_pages", is_terminal=False,
        next_solutions=[
            {"slug": "a-p2", "h1": "Saque-rescisao apos demissao", "objective": "x"},
            {"slug": "a-p3", "h1": "Saque-aniversario antecipado", "objective": "y"}],
        official_links=[], **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    # each real destination H1 is surfaced so the writer CAN name it
    assert "saque-rescisao apos demissao" in low
    assert "saque-aniversario antecipado" in low
    # bridge + announce doctrine present
    assert "ponte" in low
    assert "anuncia" in low
    assert "termo distintivo" in low
    # the incongruent open-loop exemplar is GONE (it framed the CURRENT page)
    assert "quase todo mundo pula" not in low


def test_redator_pages_terminal_frames_cross_funnel_bridge(config_files: Path) -> None:
    out = render(
        "redator_pages", is_terminal=True, next_solutions=[],
        cross_funnel_label="Ver outro guia completo >>>",
        official_links=[], **_SOLUTION_RENDER_COMMON, **doctrine_context())
    low = out.lower()
    # terminal gets an honest bridge that frames a DIVERSE guide, not a funnel step
    assert "ponte" in low
    assert "cross_funnel" in low
    assert "diverso" in low


def test_step_write_lp_passa_os_destinos_reais_ao_prompt(
        config_files: Path, monkeypatch) -> None:
    """O prompt da LP falava em "3 HUBS QUALIFICADORES" -- um desenho que a
    config nao produz mais. Agora os destinos entram por DADO, na ordem em que
    build_funnel_routes os montou, com o PAPEL de cada um: o redator sabe que o
    primeiro botao abre um hub neutro e os seguintes abrem solucoes especificas,
    e escreve convites diferentes para cada natureza."""
    from funnelforge.pipeline.routing import build_funnel_routes

    llm = FakeLLM(responses=lambda model, messages: "{}")
    deps = _deps(config_files, llm)
    deps.settings.run.presell_hubs = 1
    deps.settings.run.lp_direct_solutions = 2
    plan = FunnelPlan(total_pages=5, pages=[
        Page(page_number=1, page_type="LANDING PAGE", h1_title="Cartao", slug="a"),
        Page(page_number=2, page_type="PRESELL", h1_title="Qual e o seu caso",
             slug="a-pr", role=PageRole.PRESELL, emotional_objective="qualificar"),
        Page(page_number=3, page_type="SOLUTION", h1_title="Analise sem consulta ao biro",
             slug="a-p1", ordinal=1, emotional_objective="entender a analise"),
        Page(page_number=4, page_type="SOLUTION", h1_title="Limite garantido por deposito",
             slug="a-p2", ordinal=2, emotional_objective="comparar limites"),
        Page(page_number=5, page_type="SOLUTION", h1_title="Portabilidade da divida",
             slug="a-p3", ordinal=3, emotional_objective="reduzir juros"),
    ])
    build_funnel_routes(plan, deps.settings)
    state = RunState(run_id="a-20260720-101010", briefing_text="brief")
    state.plan = plan

    calls = _capture_render(monkeypatch)
    st.step_write(state, plan.pages[0], deps)

    lp_calls = [kw for name, kw in calls if name == "redator_p1"]
    assert lp_calls, "o prompt redator_p1 nao foi renderizado"
    destinos = lp_calls[0]["lp_destinations"]
    assert [d["slug"] for d in destinos] == ["a-pr", "a-p1", "a-p2"]
    assert [d["role"] for d in destinos] == ["PRESELL", "SOLUTION", "SOLUTION"]
    assert destinos[0]["h1"] == "Qual e o seu caso"
    assert destinos[1]["objective"] == "entender a analise"
    assert "hub qualificador" in destinos[0]["role_label"]
    assert "solução" in destinos[1]["role_label"]
