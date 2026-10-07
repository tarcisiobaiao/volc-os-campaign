"""PATCHES DO REVISOR: o modelo propõe, o CÓDIGO decide o que pode mudar (B5).

Regras conferidas aqui, sem LLM:
- patch só em campo permitido (corpo editável, SEO, campos de texto da LP,
  rótulos de CTA); nunca em widget, aviso editorial, bloco, href, script;
- `antes` ocorre exatamente uma vez;
- sem URL, <a>, tag de bloco ou número novo (número só do inventário);
- limites de tamanho e de quantidade;
- estilo/nota nunca vira patch automático; achado sem evidência válida também não.
"""
from __future__ import annotations

import json
import re

import pytest

from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
from funnelforge.pipeline.revisao import (
    MAX_PATCHES_POR_RODADA,
    Documento,
    Referencias,
    RegrasDePatch,
    aplicar_patches,
    posicionar_aviso_canonico,
    recibo_sha256,
    validar_achados,
)

HREF_INTERNO = "https://site.exemplo.com.br/rec/como-pedir-p2"
HREF_OFICIAL = "https://servicos.exemplo.gov.br/consulta"
AVISO = (
    '<!-- wp:paragraph {"align":"center"} -->\n'
    f'<p class="has-text-align-center"><em>{COMPLIANCE_NOTICE_TEXT}</em></p>\n'
    "<!-- /wp:paragraph -->"
)
CORPO = f"""<!-- wp:paragraph -->
<p>Primeiro paragrafo com <strong>destaque</strong> e um trecho comum sobre a conta.</p>
<!-- /wp:paragraph -->

<!-- wp:heading -->
<h2>Quem tem direito ao desconto</h2>
<!-- /wp:heading -->

<!-- wp:paragraph -->
<p>Leia no <a href="{HREF_OFICIAL}">canal oficial da distribuidora</a> as regras de 65% de desconto.</p>
<!-- /wp:paragraph -->

<!-- wp:list -->
<ul class="wp-block-list"><!-- wp:list-item -->
<li>Conferir a inscricao no cadastro.</li>
<!-- /wp:list-item --></ul>
<!-- /wp:list -->

<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button -->
<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{HREF_INTERNO}">Fazer inscrição agora</a></div>
<!-- /wp:button --></div><!-- /wp:buttons -->

<!-- wp:html -->
<section class="vw-abc123" id="vw-abc123"><h3>Roteador</h3><p>Texto do widget exclusivo</p></section>
<!-- /wp:html -->

{AVISO}"""

LP = {
    "hero_title": "Tarifa social de energia",
    "hero_subtitle": "Quem tem direito e onde pedir",
    "article_title": "Tarifa social: quem tem direito",
    "intro": "<p>A conta pesa. Veja quem tem direito ao <strong>desconto</strong>.</p>",
    "sections": [{"title": "Quem pode", "body": "<p>A regra olha o cadastro social.</p>"},
                 {"title": "Como aparece", "body": "<p>O desconto é garantido para todos.</p>"},
                 {"title": "Onde pedir", "body": "<p>Na distribuidora.</p>"},
                 {"title": "Antes", "body": "<p>Tenha a conta em maos.</p>"}],
    "faq": [{"q": "Preciso pagar?", "a": "Nao. O pedido e gratuito."}],
    "transition": "<p>O proximo guia mostra o caminho.</p>",
    "cta_texts": ["Fazer inscrição", "Ver quem tem direito", "Ver o passo a passo"],
}


def _doc_gutenberg() -> Documento:
    return Documento(formato="gutenberg", corpo=CORPO,
                     seotitle="Tarifa social: quem tem direito",
                     metadescription="Veja quem tem direito ao desconto na conta de luz.")


def _doc_lp() -> Documento:
    return Documento(formato="lp_json", corpo=json.dumps(LP, ensure_ascii=False),
                     seotitle="Tarifa social", metadescription="Quem tem direito.")


def _refs() -> Referencias:
    return Referencias(fatos={"n1", "f1"}, fontes={"s1": HREF_OFICIAL},
                       politicas_bloqueantes={"ADS-MIS-04#A1", "ADS-MIS-06#A1"},
                       politicas_nota={"NE-03"}, destinos={"d1": "como-pedir-p2"})


def _achado(i="a1", *, campo="corpo", trecho="Fazer inscrição agora", severidade="bloqueante",
            categoria="congruencia_destino", tipo="destino", ref="d1") -> dict:
    return {"id": i, "severidade": severidade, "categoria": categoria, "campo": campo,
            "trecho": trecho, "motivo": "rótulo promete o que o destino não entrega",
            "evidencia": {"tipo": tipo, "ref": ref}}


def _aplicar(doc, patches, achados, numeros=frozenset({"65"})):
    validos = {a["id"]: a for a in validar_achados(achados, doc, _refs())}
    return aplicar_patches(doc, patches, validos, RegrasDePatch(numeros_permitidos=set(numeros)))


def _patch(antes, depois, *, campo="corpo", achado="a1") -> dict:
    return {"achado": achado, "campo": campo, "antes": antes, "depois": depois}


def _blocos(html: str) -> list[str]:
    return re.findall(r"<!--\s*/?wp:[^>]*-->", html)


def _hrefs(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html)


# ---------------------------------------------------------------------------
# o que PODE mudar
# ---------------------------------------------------------------------------

def test_patch_em_rotulo_de_cta_aplica_e_preserva_href_e_blocos():
    doc = _doc_gutenberg()
    novo, aplicados, recusados = _aplicar(
        doc, [_patch("Fazer inscrição agora", "Ver como pedir o desconto")], [_achado()])
    assert recusados == [] and len(aplicados) == 1
    assert "Ver como pedir o desconto" in novo.corpo
    assert "Fazer inscrição agora" not in novo.corpo
    assert _hrefs(novo.corpo) == _hrefs(doc.corpo)
    assert _blocos(novo.corpo) == _blocos(doc.corpo)


def test_patch_em_paragrafo_com_numero_do_inventario_aplica():
    doc = _doc_gutenberg()
    achado = _achado(trecho="um trecho comum sobre a conta", categoria="erro_factual",
                     tipo="fato", ref="n1", severidade="ajuste")
    novo, aplicados, recusados = _aplicar(
        doc, [_patch("um trecho comum sobre a conta",
                     "o desconto de <strong>65%</strong> na faixa mais baixa")], [achado])
    assert recusados == [] and aplicados
    assert "o desconto de <strong>65%</strong>" in novo.corpo


def test_patch_nos_campos_seo_e_nos_campos_da_lp():
    doc = _doc_lp()
    achados = [
        _achado("a1", campo="sections[1].body", trecho="garantido para todos",
                categoria="erro_factual", tipo="politica", ref="ADS-MIS-04#A1"),
        _achado("a2", campo="cta_texts[0]", trecho="Fazer inscrição"),
        _achado("a3", campo="seotitle", trecho="Tarifa social", severidade="ajuste",
                categoria="congruencia_destino", tipo="destino", ref="d1"),  # B8/R5
    ]
    patches = [
        _patch("garantido para todos", "aplicado a quem cumpre a regra do cadastro",
               campo="sections[1].body", achado="a1"),
        _patch("Fazer inscrição", "Ver se a familia tem direito", campo="cta_texts[0]",
               achado="a2"),
        _patch("Tarifa social", "Tarifa social: quem tem direito", campo="seotitle",
               achado="a3"),
    ]
    novo, aplicados, recusados = _aplicar(doc, patches, achados)
    assert recusados == [], recusados
    lp = json.loads(novo.corpo)
    assert lp["sections"][1]["body"] == "<p>O desconto é aplicado a quem cumpre a regra do cadastro.</p>"
    assert lp["cta_texts"][0] == "Ver se a familia tem direito"
    assert novo.seotitle == "Tarifa social: quem tem direito"
    assert set(lp) == set(LP)                               # nenhum campo criado ou removido
    assert len(lp["sections"]) == 4 and len(lp["cta_texts"]) == 3


# ---------------------------------------------------------------------------
# o que NÃO pode mudar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("antes,motivo", [
    ("Texto do widget exclusivo", "regiao_protegida"),       # widget vw-
    ("Aviso de Utilidade Pública", "regiao_protegida"),      # aviso editorial
    ("<!-- wp:heading", "regiao_protegida"),                 # comentário de bloco
    (f'href="{HREF_INTERNO}"', "regiao_protegida"),          # atributo/href
    ("canal oficial da distribuidora", "texto_de_link"),     # link em prosa
    ("<h2>Quem tem direito", "regiao_protegida"),            # tag de bloco
])
def test_patch_em_regiao_protegida_e_recusado(antes, motivo):
    doc = _doc_gutenberg()
    achado = _achado(trecho=antes)
    novo, aplicados, recusados = _aplicar(doc, [_patch(antes, "qualquer texto")], [achado])
    assert aplicados == []
    assert recusados and recusados[0]["motivo"] == motivo, recusados
    assert novo.corpo == doc.corpo


@pytest.mark.parametrize("depois,motivo", [
    ("veja em https://golpe.exemplo.com agora", "url_nova"),
    ("veja em www.golpe.com.br", "url_nova"),
    ('veja <a href="/x">aqui</a>', "link_novo"),
    ("texto</p><p>outro bloco", "tag_nao_permitida"),
    ("<!-- wp:paragraph -->", "tag_nao_permitida"),
    ("desconto de 99% para todos", "numero_novo"),
    ("prazo de 30 dias", "numero_novo"),
])
def test_patch_que_altera_fato_link_ou_estrutura_e_recusado(depois, motivo):
    doc = _doc_gutenberg()
    novo, aplicados, recusados = _aplicar(
        doc, [_patch("um trecho comum sobre a conta", depois)],
        [_achado(trecho="um trecho comum sobre a conta", severidade="ajuste",
                 categoria="erro_factual", tipo="fato", ref="n1")])
    assert aplicados == []
    assert recusados[0]["motivo"] == motivo, recusados
    assert novo.corpo == doc.corpo


def test_antes_ausente_ou_duplicado_e_recusado():
    doc = Documento(formato="gutenberg", corpo=CORPO.replace(
        "e um trecho comum", "e um trecho comum e outro trecho comum"),
        seotitle="", metadescription="")
    achados = [_achado("a1", trecho="trecho comum"), _achado("a2", trecho="Primeiro paragrafo")]
    _novo, aplicados, recusados = _aplicar(
        doc, [_patch("trecho comum", "x", achado="a1"), _patch("nao existe", "y", achado="a2")],
        achados)
    assert aplicados == []
    assert [r["motivo"] for r in recusados] == ["antes_duplicado", "antes_ausente"]


def test_widget_e_somente_leitura_e_campo_desconhecido_e_recusado():
    doc = _doc_gutenberg()
    achados = [_achado("a1", campo="widget", trecho="Texto do widget exclusivo"),
               _achado("a2", campo="rodape", trecho="x")]
    _novo, aplicados, recusados = _aplicar(
        doc, [_patch("Texto do widget exclusivo", "outro", campo="widget", achado="a1"),
              _patch("x", "y", campo="rodape", achado="a2")], achados)
    assert aplicados == []
    assert {r["motivo"] for r in recusados} == {"campo_somente_leitura", "campo_inexistente"}


def test_limite_de_tamanho_e_de_quantidade():
    doc = _doc_gutenberg()
    grande = "a" * 206                     # antes = 5 caracteres -> teto max(7, 205)
    _n, aplicados, recusados = _aplicar(
        doc, [_patch("comum", grande)], [_achado(trecho="comum", severidade="ajuste",
                                                 categoria="erro_factual", tipo="fato",
                                                 ref="n1")])
    assert aplicados == [] and recusados[0]["motivo"] == "tamanho_excedido"

    lp = dict(LP, faq=[{"q": f"Pergunta {chr(65 + i)}?", "a": f"Resposta {chr(65 + i)}."}
                       for i in range(10)])
    doc_lp = Documento(formato="lp_json", corpo=json.dumps(lp, ensure_ascii=False))
    achados = [_achado(f"a{i}", campo=f"faq[{i}].a", trecho=f"Resposta {chr(65 + i)}",
                       severidade="ajuste", categoria="erro_factual", tipo="fato", ref="f1")
               for i in range(10)]
    patches = [_patch(f"Resposta {chr(65 + i)}", f"Resposta revisada {chr(65 + i)}",
                      campo=f"faq[{i}].a", achado=f"a{i}") for i in range(10)]
    validos = {a["id"]: a for a in validar_achados(achados, doc_lp, _refs())}
    _n, aplicados, recusados = aplicar_patches(doc_lp, patches, validos,
                                               RegrasDePatch(numeros_permitidos=set()))
    assert len(aplicados) == MAX_PATCHES_POR_RODADA == 8
    assert [r["motivo"] for r in recusados] == ["limite_de_patches"] * 2


def test_estilo_nota_e_evidencia_invalida_nunca_viram_patch_automatico():
    doc = _doc_gutenberg()
    achados = [
        _achado("a1", trecho="Fazer inscrição agora", categoria="estilo",
                severidade="bloqueante", tipo="briefing", ref="tom"),
        _achado("a2", trecho="um trecho comum sobre a conta", severidade="nota",
                categoria="oportunidade", tipo="briefing", ref="promessa_da_pagina"),
        _achado("a3", trecho="Primeiro paragrafo", categoria="risco_politica",
                tipo="politica", ref="REGRA-INVENTADA-99"),
        _achado("a4", trecho="Quem tem direito ao desconto", categoria="risco_politica",
                tipo="politica", ref="NE-03"),                   # C vira nota
    ]
    validos = validar_achados(achados, doc, _refs())
    por_id = {a["id"]: a for a in validos}
    assert por_id["a1"]["severidade"] == "nota" and por_id["a1"]["rebaixado"]
    assert por_id["a3"]["severidade"] == "nota" and por_id["a3"]["invalido"]
    assert por_id["a4"]["severidade"] == "nota" and por_id["a4"]["rebaixado"]
    patches = [_patch("Fazer inscrição agora", "Ver o passo a passo", achado="a1"),
               _patch("um trecho comum sobre a conta", "um trecho", achado="a2"),
               _patch("Primeiro paragrafo", "Paragrafo", achado="a3"),
               _patch("Quem tem direito ao desconto", "Quem pode ter", achado="a4"),
               _patch("destaque", "realce", achado="a99")]
    novo, aplicados, recusados = aplicar_patches(doc, patches, por_id,
                                                 RegrasDePatch(numeros_permitidos=set()))
    assert aplicados == []
    assert [r["motivo"] for r in recusados] == ["achado_nao_patchavel"] * 4 + ["achado_inexistente"]
    assert novo.corpo == doc.corpo


def test_trecho_que_nao_existe_no_campo_invalida_o_achado():
    doc = _doc_gutenberg()
    [a] = validar_achados([_achado(trecho="frase que o revisor inventou")], doc, _refs())
    assert a["invalido"] == "trecho_inexistente" and a["severidade"] == "nota"


# ---------------------------------------------------------------------------
# recibo e aviso canônico
# ---------------------------------------------------------------------------

def test_recibo_cobre_titulo_meta_e_corpo():
    base = recibo_sha256("<p>x</p>", "Titulo", "Meta")
    assert re.fullmatch(r"[0-9a-f]{64}", base)
    assert base != recibo_sha256("<p>y</p>", "Titulo", "Meta")
    assert base != recibo_sha256("<p>x</p>", "Titulo 2", "Meta")
    assert base != recibo_sha256("<p>x</p>", "Titulo", "Meta 2")
    assert base == _doc_sha("<p>x</p>", "Titulo", "Meta")


def _doc_sha(corpo, t, m) -> str:
    return Documento(formato="gutenberg", corpo=corpo, seotitle=t, metadescription=m).sha256()


def test_aviso_canonico_sai_so_pela_frase_exata_e_e_idempotente():
    legitimo = ("<!-- wp:paragraph -->\n<p>Cursos de primeiros socorros preparam para "
                "servicos de utilidade pública, como brigadas.</p>\n<!-- /wp:paragraph -->")
    inline = f"<!-- wp:paragraph -->\n<p>{COMPLIANCE_NOTICE_TEXT}</p>\n<!-- /wp:paragraph -->"
    corpo = f"{legitimo}\n\n{inline}\n\n<!-- wp:paragraph -->\n<p>Fim.</p>\n<!-- /wp:paragraph -->"
    novo, registro = posicionar_aviso_canonico(corpo)
    assert legitimo in novo                                   # o parágrafo legítimo fica
    assert novo.count(COMPLIANCE_NOTICE_TEXT) == 1           # um só aviso
    assert novo.rstrip().endswith("<!-- /wp:paragraph -->")
    assert novo.index("Fim.") < novo.index(COMPLIANCE_NOTICE_TEXT)
    assert registro["removidos"] == 1 and registro["acrescentado"] is True
    de_novo, registro2 = posicionar_aviso_canonico(novo)
    assert de_novo == novo and registro2["alterou"] is False
