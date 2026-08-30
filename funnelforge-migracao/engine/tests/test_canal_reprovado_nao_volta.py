"""A URL que a verificação ao vivo reprovou não pode voltar por proveniência.

## O defeito que estes testes travam

Com o fim da allowlist, a autorização de link externo passou a ter três camadas:
a URL precisa ter (1) aparecido na pesquisa daquela página, (2) respondido a uma
visita real e (3) passado na sonda anti-anúncio. `registrar_canais_oficiais` roda
as três UMA vez por página e guarda o veredito em `state.official_links`.

O veredito "nenhum candidato prestou" é gravado como lista vazia. E o consumo
fazia `state.official_links.get(n) or []` — que trata lista vazia e chave ausente
como a mesma coisa, e cai no recálculo OFFLINE, que só olha proveniência.

Resultado: a URL reprovada pela sonda voltava inteira. Ia para o prompt do
redator apresentada como "deep link real da pesquisa (já validado)", virava alvo
do CTA oficial, entrava no conjunto autorizado do `resolve_route` e ainda saía
como print embutido no artigo. As duas camadas novas eram contornadas EXATAMENTE
no caso em que elas existem para atuar.

Não é hipótese: o inventário do funil que foi ao ar achou 8 links de saída, 3
deles para um portal de conteúdo concorrente que monetiza o mesmo leitor. Numa
página cujo lucro é RPM menos CPC, isso é o clique comprado indo embora de graça.

O conserto é distinguir a CHAVE do VALOR:
    chave ausente  -> ninguém decidiu (checkpoint antigo, estado de teste)
                      -> fallback offline é o certo
    chave presente
    com lista []   -> decidiu-se que nenhum presta -> respeitar
"""
from __future__ import annotations

from funnelforge.config.settings import load_settings
from funnelforge.domain.models import FunnelPlan, Page, ResearchFacts, RunState
from funnelforge.pipeline import steps as st

CONCORRENTE = "https://portal-concorrente.com.br/guia-do-beneficio"


def _pagina() -> Page:
    return Page(
        page_number=3,
        page_type="SOLUTION",
        h1_title="Como pedir o benefício",
        slug="como-pedir-beneficio-p1",
        main_content_structure=["Quem tem direito", "Como pedir", "Prazos"],
    )


def _estado(page: Page) -> RunState:
    s = RunState(run_id="teste")
    s.plan = FunnelPlan(pages=[page], total_pages=1)
    # A pesquisa TROUXE a URL do concorrente — proveniência ela tem.
    s.facts[3] = ResearchFacts(
        resumo="resumo",
        fontes=[CONCORRENTE],
        dados_validados=[{"fonte": CONCORRENTE}],
    )
    return s


def test_lista_vazia_significa_reprovado_e_nao_recalcula(monkeypatch, config_files):
    """Chave presente com lista vazia = a sonda reprovou. Não ressuscitar."""
    page = _pagina()
    state = _estado(page)
    # É isto que `registrar_canais_oficiais` grava quando a verificação ao vivo
    # ou a sonda anti-anúncio derrubam todos os candidatos.
    state.official_links[3] = []

    chamou_o_recalculo = {"sim": False}
    original = st.build_official_links

    def espiao(*a, **k):
        chamou_o_recalculo["sim"] = True
        return original(*a, **k)

    monkeypatch.setattr(st, "build_official_links", espiao)

    ctx = st._write_ctx(state, page, _deps(config_files))

    assert chamou_o_recalculo["sim"] is False, (
        "recalculou por proveniência apesar de a página já ter veredito gravado — "
        "é assim que a URL reprovada volta"
    )
    assert ctx["official_links"] == []
    assert CONCORRENTE not in str(ctx.get("official_links"))


def test_chave_ausente_ainda_cai_no_fallback_offline(config_files):
    """Checkpoint antigo / estado montado à mão continuam funcionando."""
    page = _pagina()
    state = _estado(page)
    assert 3 not in state.official_links  # ninguém decidiu

    ctx = st._write_ctx(state, page, _deps(config_files))

    # Sem veredito gravado, a proveniência sozinha vale — é o modo degradado
    # declarado, para teste e para checkpoint anterior a esta mudança.
    assert ctx["official_links"] == [CONCORRENTE]


def _deps(config_files):
    """Deps mínimo para `_write_ctx`, com as settings da fixture do projeto.

    Sem `deps.screenshot`, `_verificadores` devolve verificadores nulos — que é
    exatamente o ambiente em que o fallback offline era acionado por engano.
    """
    settings = load_settings(config_files / ".env", config_files / "config.yaml")

    class _Deps:
        pass

    d = _Deps()
    d.settings = settings
    d.research = None
    d.screenshot = None
    return d
