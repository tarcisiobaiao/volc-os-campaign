"""ESTRUTURA GUTENBERG NO RAMO NOVO — o artefato do p5 (canário de 30/09) que passou.

A redação do p5 veio truncada: o modelo escreveu raciocínio em inglês como texto
corrido, o fim da resposta cortou um `wp:group` no meio dos atributos, e a página
só tinha 2 parágrafos contáveis. O gate `unbalanced` não viu nada (a abertura
truncada não tem `-->`), SEO, widget, revisor e imagem foram pagos, e só o
content_gate final barrou pelo slot do Ad Inserter.

Agora, no ramo novo:
- logo depois da redação, a resposta tem de ser SÓ blocos Gutenberg balanceados
  e os slots configurados do Ad Inserter têm de caber no fluxo principal;
- o gate final refaz a conferência de estrutura sobre o HTML depois de widget,
  screenshot e composição.
Nada é inserido nem consertado pelo código: a página falha e não gasta mais.
"""
from __future__ import annotations

import json
from pathlib import Path

from funnelforge.domain.models import StepStatus
from funnelforge.pipeline.validators.checks import run_validators
from tests.cenario_editorial import (
    arquitetura_base,
    congelar_data,
    ordem_do_run,
    responder_v2,
    rodar_cenario,
    settings_do_cenario,
    texto_da_mensagem,
)

CTX = {"ad_paragraph_anchors": [1, 3]}

# Fixture reduzida do artefato real do p5 (resposta de write_p5, 2ª tentativa).
ARTEFATO_P5 = (
    'aluno Senac"\n'
    '    - `https://creditoup.com.br/credito-do-trabalhador-o-que-perguntar-antes-de-aceitar-a-oferta-no-app/`'
    ' -> "Ver outro guia completo >>>"\n\n'
    "    All look completely correct. The HTML structure is extremely clean and matches exactly what is"
    " required. Ready to output."
    '<!-- wp:heading {"level":2} -->\n<h2>Por que não existe um endereço único para todos os estados?</h2>\n'
    "<!-- /wp:heading -->\n\n"
    '<!-- wp:group {"style":{"color":{"background":"#f1f5f9"},"spacing":{"padding":{"top":"24px",'
)


def _p(texto: str) -> str:
    return f"<!-- wp:paragraph -->\n<p>{texto}</p>\n<!-- /wp:paragraph -->\n\n"


def _h2(texto: str) -> str:
    return f"<!-- wp:heading -->\n<h2>{texto}</h2>\n<!-- /wp:heading -->\n\n"


TRES = _p("O Senac é organizado por estado.") + _p("Cada regional tem portal próprio.") + \
    _p("Confira o endereço oficial do seu estado antes de se inscrever.")


def _codigos_redacao(texto: str) -> list[str]:
    return [i.code for i in run_validators(["estrutura_da_redacao"], texto, CTX)]


def _codigos_finais(texto: str) -> list[str]:
    return [i.code for i in run_validators(["composicao_editorial"], texto, CTX)]


def test_artefato_real_do_p5_e_reprovado_logo_apos_a_redacao():
    codigos = _codigos_redacao(ARTEFATO_P5)
    assert "texto_fora_dos_blocos" in codigos
    assert "bloco_malformado" in codigos
    assert "ad_slot_inseguro" in codigos


def test_texto_cru_fora_dos_blocos_e_bloqueado():
    meta = "All look completely correct. Ready to output.\n"
    assert "texto_fora_dos_blocos" in _codigos_redacao(TRES + meta + _h2("Como conferir"))
    assert "texto_fora_dos_blocos" in _codigos_redacao(TRES + _h2("Fim") + meta)


def test_group_sem_fechamento_e_bloqueado():
    aberto = ('<!-- wp:group -->\n<div class="wp-block-group">'
              + _p("Atenção ao endereço.") + "</div>\n")
    assert "bloco_sem_fechamento" in _codigos_redacao(TRES + _h2("Atenção") + aberto)


def test_dois_paragrafos_top_level_bloqueiam_logo_apos_a_redacao():
    dois = _p("O Senac é organizado por estado.") + _p("Cada regional tem portal próprio.")
    assert "ad_slot_inseguro" in _codigos_redacao(dois + _h2("Como conferir"))


def test_tres_paragrafos_top_level_validos_passam():
    assert _codigos_redacao(TRES + _h2("Como conferir") + _p("Passo a passo.")) == []


def test_paragrafo_dentro_de_columns_ou_blockquote_nao_conta():
    dois = _p("O Senac é organizado por estado.") + _p("Cada regional tem portal próprio.")
    colunas = ('<!-- wp:columns -->\n<div class="wp-block-columns"><!-- wp:column -->\n'
               '<div class="wp-block-column">' + _p("Dentro da coluna.") + "</div>\n"
               "<!-- /wp:column --></div>\n<!-- /wp:columns -->\n\n")
    citacao = ('<!-- wp:quote -->\n<blockquote class="wp-block-quote">'
               + _p("Dentro da citação.") + "</blockquote>\n<!-- /wp:quote -->\n\n")
    assert "ad_slot_inseguro" in _codigos_redacao(dois + colunas)
    assert "ad_slot_inseguro" in _codigos_redacao(dois + citacao)


def test_paragrafo_dentro_de_group_nao_conta_no_html_final():
    """Na redação, a normalização (já existente) desfaz o group da abertura e o
    parágrafo vira top-level de verdade; no HTML final, sem normalização, um
    parágrafo dentro de group não conta para o slot."""
    dois = _p("O Senac é organizado por estado.") + _p("Cada regional tem portal próprio.")
    grupo = ('<!-- wp:group -->\n<div class="wp-block-group">' + _p("Dentro do grupo.")
             + "</div>\n<!-- /wp:group -->\n\n")
    assert "ad_slot_inseguro" in _codigos_finais(dois + grupo)


def test_composicao_que_quebra_blocos_e_bloqueada_no_gate_final():
    bom = TRES + _h2("Como conferir") + _p("Passo a passo.")
    assert _codigos_finais(bom) == []
    widget_quebrado = '<!-- wp:html -->\n<div class="vw">ferramenta</div>\n'   # sem /wp:html
    assert "bloco_sem_fechamento" in _codigos_finais(bom + widget_quebrado)
    assert "texto_fora_dos_blocos" in _codigos_finais(bom + "comentário solto do compositor\n")
    assert "bloco_malformado" in _codigos_finais(bom + '<!-- wp:group {"style":{"x":1\n' + _p("fim"))


def test_redacao_reprovada_nao_paga_seo_widget_revisao_nem_imagem(tmp_path: Path, monkeypatch):
    """Página interna com 2 parágrafos contáveis: falha na redação (com as
    retentativas configuradas) e o pipeline não gasta mais nada com ela."""
    def responder(model, messages):
        # a retentativa traz o feedback como última mensagem; o pedido é a primeira
        if "PÁGINA INTERNA" in texto_da_mensagem(messages[0]):
            return (_p("Primeiro parágrafo da página interna, com orientação útil.")
                    + _p("Segundo parágrafo da página interna, com o caminho oficial.")
                    + _h2("Como seguir") + "<!-- wp:list -->\n<ul class=\"wp-block-list\">"
                    "<li>Um passo.</li></ul>\n<!-- /wp:list -->\n")
        return responder_v2(model, messages)

    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    settings.run.widgets_enabled = True
    settings.run.featured_image = True
    state, deps, _llm = rodar_cenario(tmp_path, arquitetura_base(), settings, responder=responder)
    chamadas = ordem_do_run(deps.runner.runs_dir, state.run_id, state)["chamadas_llm"]
    internas = [p.page_number for p in state.plan.pages if p.page_type == "SOLUTION"]
    assert internas
    for n in internas:
        escrita = state.step_status[f"write_p{n}"]
        assert escrita.status is StepStatus.FAILED, n
        assert "ad_slot_inseguro" in {i.code for i in escrita.issues}, n
        assert escrita.attempts == deps.settings.run.max_retries + 1, n
        assert state.step_status[f"blocked_p{n}"].status is StepStatus.FAILED, n
        for caro in ("seo", "widget", "revisor", "image", "image_review"):
            assert not any(c.startswith(f"{caro}_p{n}#") for c in chamadas), (n, caro)
        assert f"image_gen_p{n}" not in state.step_status, n
    json.dumps(chamadas)
