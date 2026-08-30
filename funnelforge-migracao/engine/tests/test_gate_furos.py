"""Os furos dos portões — um teste por furo medido.

Cada furo desta suíte existia porque NENHUM teste o cobria: o portão estava
escrito, registrado em `VALIDATORS`, rodando em toda página — e não pegava o
caso. Um portão que não pega nada é pior que portão nenhum, porque compra
confiança sem entregar proteção.

Todos os testes abaixo FALHAM no código anterior à Frente 5.
"""
from __future__ import annotations

import pytest

from funnelforge.domain.models import FunnelPlan, Page, PageRole, RunState
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.enhancers.gutenberg import normalize_gutenberg
from funnelforge.pipeline.validators.checks import _cta_links, run_validators

_DOMINIO = "https://creditoup.com.br"


def _codes(nome: str, content: str, ctx: dict | None = None) -> set[str]:
    return {i.code for i in run_validators([nome], content, ctx or {})}


# ===========================================================================
# FURO 1 · o comentário de bloco aceita ATRIBUTOS
# ===========================================================================

def test_raw_html_com_atributos_nao_escapa_do_contrato() -> None:
    """`<!-- wp:html {"lock":...} -->` é HTML cru igual ao seco. A regex antiga
    exigia o comentário sem atributos, então bastava o modelo (ou o próprio
    editor do WordPress, que grava `lock`/`metadata` sozinho) declarar um
    atributo para o <p> dentro do bloco ficar invisível ao portão."""
    body = ('<!-- wp:html {"metadata":{"name":"Simulador"}} -->'
            '<div><p class="resultado">R$ 0,00</p></div>'
            '<!-- /wp:html -->')
    assert "paragraph_in_raw_html" in _codes("raw_html_contract", body)


def test_normalizador_nao_entra_em_raw_html_com_atributos() -> None:
    """O outro lado da MESMA regex: o "never touch raw html" do enhancer também
    não reconhecia o bloco com atributos — e então reescrevia <li> como
    `wp:list-item` e quebrava os <p> DENTRO do widget, corrompendo o markup que
    a bateria de sanitização tinha acabado de aprovar."""
    raw = ('<!-- wp:paragraph --><p>Abre o artigo aqui.</p><!-- /wp:paragraph -->\n'
           '<!-- wp:html {"lock":{"move":false}} -->\n'
           '<div><ul><li>manter</li></ul>'
           '<p>Uma frase. Outra frase. Terceira frase inteira aqui.</p></div>\n'
           '<!-- /wp:html -->')
    out = normalize_gutenberg(raw)
    assert "wp:list-item" not in out
    assert "<ul><li>manter</li></ul>" in out


# ===========================================================================
# FURO 2 · margem ZERO é margem declarada, mas não separa nada
# ===========================================================================

def test_margem_zero_entre_grupos_irmaos_nao_conta_como_margem() -> None:
    """A checagem era de SUBSTRING (`'\"margin\"' not in attrs`). Um estilo com
    margem zero contém a palavra e passava — e na tela os dois grupos seguiam
    colados, que é exatamente o defeito que a regra existe para pegar."""
    body = ('<!-- wp:group --><div></div><!-- /wp:group -->'
            '<!-- wp:group {"style":{"spacing":{"margin":{"top":"0px","bottom":"0"}}}} -->'
            '<div></div><!-- /wp:group -->')
    assert "adjacent_groups_without_margin" in _codes("raw_html_contract", body)


@pytest.mark.parametrize("margem", [
    '{"style":{"spacing":{"margin":{"top":"32px"}}}}',
    '{"style":{"spacing":{"margin":{"top":"var:preset|spacing|30"}}}}',
    '{"style":{"spacing":{"margin":{"bottom":"2rem"}}}}',
])
def test_margem_vertical_real_continua_passando(margem: str) -> None:
    """O aperto não pode virar falso positivo: margem de verdade passa."""
    body = ('<!-- wp:group --><div></div><!-- /wp:group -->'
            f'<!-- wp:group {margem} --><div></div><!-- /wp:group -->')
    assert "adjacent_groups_without_margin" not in _codes("raw_html_contract", body)


# ===========================================================================
# FURO 3 · um bloco decorativo no meio desfazia a adjacência
# ===========================================================================

@pytest.mark.parametrize("meio", [
    '<!-- wp:separator --><hr class="wp-block-separator"/><!-- /wp:separator -->',
    '<!-- wp:spacer {"height":"40px"} --><div style="height:40px"></div>'
    '<!-- /wp:spacer -->',
    '<!-- wp:spacer {"height":"40px"} /-->',
])
def test_decorativo_entre_grupos_de_botoes_nao_desfaz_a_adjacencia(meio: str) -> None:
    """A regra exigia adjacência LITERAL, então qualquer bloco no meio a
    desligava. Um separador entre duas pilhas de botões não é prosa: continua
    sendo saturação de CTA, agora com um traço no meio."""
    body = ('<!-- wp:buttons --><div></div><!-- /wp:buttons -->'
            + meio +
            '<!-- wp:buttons --><div></div><!-- /wp:buttons -->')
    assert "adjacent_button_groups" in _codes("raw_html_contract", body)


def test_prosa_entre_grupos_de_botoes_continua_valida() -> None:
    """Prosa entre os grupos é o que a regra PEDE — não pode virar falso
    positivo junto com o aperto acima."""
    body = ('<!-- wp:buttons --><div></div><!-- /wp:buttons -->'
            '<!-- wp:paragraph --><p>Se o seu caso for o segundo, o caminho muda.</p>'
            '<!-- /wp:paragraph -->'
            '<!-- wp:buttons --><div></div><!-- /wp:buttons -->')
    assert "adjacent_button_groups" not in _codes("raw_html_contract", body)


# ===========================================================================
# FURO 4 · a âncora "^" e o formato marcador
# ===========================================================================

@pytest.mark.parametrize("rotulo", [
    "Quero consultar no App FGTS",
    "Agora consulte o saldo no app da Caixa",
    "Clique e baixe o aplicativo do FGTS",
])
def test_promessa_de_execucao_no_meio_do_rotulo_e_pega(rotulo: str) -> None:
    """A regra estava ancorada em `^`: só olhava a PRIMEIRA palavra. Bastava um
    prefixo ("Quero", "Agora", "Clique e") para o botão prometer executar o
    serviço num destino externo, apontar para um artigo interno, e passar."""
    body = ('<!-- wp:buttons --><div class="wp-block-buttons">'
            f'<a href="{_DOMINIO}/rec/modalidade-p2">{rotulo}</a>'
            '</div><!-- /wp:buttons -->')
    codes = _codes("cta_style", body, {"role": PageRole.SOLUTION, "domain": _DOMINIO})
    assert "cta_destination_mismatch" in codes


@pytest.mark.parametrize("rotulo", [
    "Ver como consultar no App FGTS",
    "Veja como sacar pelo app da Caixa",
    "Entenda quando solicitar no portal",
])
def test_curiosidade_continua_valida(rotulo: str) -> None:
    """O que separa promessa de curiosidade não é a POSIÇÃO da palavra, é o
    ENQUADRAMENTO: um interrogativo antes do verbo transforma execução em
    explicação, e aí o clique não mente sobre o destino."""
    body = ('<!-- wp:buttons --><div class="wp-block-buttons">'
            f'<a href="{_DOMINIO}/rec/modalidade-p2">{rotulo}</a>'
            '</div><!-- /wp:buttons -->')
    codes = _codes("cta_style", body, {"role": PageRole.SOLUTION, "domain": _DOMINIO})
    assert "cta_destination_mismatch" not in codes


def test_botao_em_formato_marcador_entra_no_portao_de_destino() -> None:
    """`_cta_links` só lia âncoras dentro de `wp:buttons` — e a LANDING PAGE
    inteira fala MARCADOR (`Texto:`/`Link:`). O portão de congruência
    CTA↔destino, que é o que impede um botão de mentir sobre para onde vai,
    era inteiramente inaplicável na única página que compra clique."""
    body = ("=== WIDGET: BOTÃO ===\n"
            "Texto: Consultar o saldo no app da Caixa\n"
            "Cor: marca\n"
            f"Link: {_DOMINIO}/rec/saldo-fgts-p2\n")
    assert _cta_links(body) == [
        ("Consultar o saldo no app da Caixa", f"{_DOMINIO}/rec/saldo-fgts-p2")]
    codes = _codes("cta_style", body, {"role": PageRole.LP, "domain": _DOMINIO})
    assert "cta_destination_mismatch" in codes


# ===========================================================================
# FUROS 5 e 6 · o portão visual desligando em silêncio, e a escala binária
# ===========================================================================

@pytest.mark.parametrize("rotulo", ["sustenta", "condicionall", "Dado Unico!"])
def test_rotulo_declarado_que_nao_resolve_nao_desliga_o_portao_em_silencio(
        rotulo: str) -> None:
    """Antes, QUALQUER rótulo fora do mapa devolvia `[]` — ou seja, "aprovado" —
    enquanto `widget_archetype_for`, lendo o MESMO campo, aplicava
    `infer_engajamento` e seguia. Um lado inferia, o outro desistia calado."""
    codes = _codes("visual_contract", "",
                   {"role": PageRole.SOLUTION, "engajamento": rotulo})
    assert codes == {"engajamento_nao_resolvido"}


def test_ausencia_de_rotulo_e_fail_open_declarado() -> None:
    """A contrapartida: `""` é estado legítimo (`declarar_engajamento` nem roda
    sem `steps.engajamento` na config). Reprovar aqui exigiria INFERIR, e
    inferir para BLOQUEAR é o que este portão não pode fazer."""
    assert run_validators(["visual_contract"], "",
                          {"role": PageRole.SOLUTION, "engajamento": ""}) == []


def test_acento_no_rotulo_nao_e_rotulo_invalido() -> None:
    """`.strip().lower()` não dobra acento: `Dado Único` não caía no mapa e o
    portão se desligava. Canonizado, ele volta a EXIGIR o que exige — e o corpo
    completo continua passando."""
    ctx = {"role": PageRole.SOLUTION, "engajamento": "Dado Único"}
    so_details = '<!-- wp:details --><details></details><!-- /wp:details -->'
    assert "missing_semantic_block" in _codes("visual_contract", so_details, ctx)
    completo = so_details + '<!-- wp:table --><figure></figure><!-- /wp:table -->'
    assert run_validators(["visual_contract"], completo, ctx) == []


def _solucao(**campos) -> Page:
    base = dict(page_number=3, page_type="SOLUTION", h1_title="Solucao",
                slug="tema-p1", ordinal=1, role=PageRole.SOLUTION)
    base.update(campos)
    return Page(**base)


def _estado(page: Page) -> RunState:
    s = RunState(run_id="furo-6")
    s.plan = FunnelPlan(total_pages=1, pages=[page])
    return s


def test_dado_unico_com_acento_continua_significando_sem_widget() -> None:
    """O rótulo que MANDA não construir widget não pode ser perdido por um til:
    `Dado Único` virava rótulo desconhecido, a inferência escolhia outra forma,
    e a página ganhava um enfeite ao lado do anúncio."""
    # o H1 é de PROPÓSITO um que a inferência classificaria como `comparativo`:
    # se o rótulo com acento for jogado fora, a página ganha um Comparador de
    # Rotas — enfeite ao lado de anúncio numa página cuja resposta é um número.
    page = _solucao(engajamento="Dado Único",
                    h1_title="Compare os bancos que antecipam o FGTS")
    assert st.widget_archetype_for(_estado(page), page) is None


def test_sustenta_da_escala_binaria_vira_forma_de_pergunta() -> None:
    """O eixo `engajamento` do motor de pautas COLAPSOU para dois níveis
    (`sustenta`/`dado_unico`). `sustenta` afirma "há o que ler", mas não diz
    QUAL forma — então é refinado pela inferência sobre o conteúdo da página, e
    nunca vira `dado_unico` (isso contradiria a própria declaração)."""
    page = _solucao(engajamento="sustenta",
                    h1_title="Qual banco compara melhor: Caixa ou digital")
    assert st.engajamento_declarado(page) == "comparativo"
    assert st.widget_archetype_for(_estado(page), page) == "Comparador de Rotas"

    # o caso que o refinamento tem de proteger: a inferência devolveria
    # `dado_unico` ("quanto"/"valor"), o que apagaria o widget de uma página que
    # o motor de pautas declarou ter o que ler.
    numerica = _solucao(engajamento="sustenta",
                        h1_title="Quanto vale o limite e qual o prazo")
    assert st.engajamento_declarado(numerica) == "sequencial"
    assert st.widget_archetype_for(_estado(numerica), numerica) is not None


def test_o_ctx_de_escrita_entrega_o_rotulo_ja_traduzido() -> None:
    """A ponte inteira num único ponto: o que chega no ctx (e portanto no
    portão visual) é a forma JÁ traduzida, nunca `sustenta` cru — senão o furo 6
    reapareceria como o furo 5 em toda página vinda de card novo."""
    page = _solucao(engajamento="sustenta",
                    h1_title="Compare as rotas de antecipacao")
    assert st.engajamento_declarado(page) in st.ENGAJAMENTO_PARA_ARQUETIPO
