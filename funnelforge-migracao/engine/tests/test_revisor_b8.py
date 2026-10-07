"""B8 · correções dos achados da revisão adversarial (B7) no revisor do motor.

- R1: a coerência de "aprovado" vale para QUALQUER forma do JSON (severidade com
  caixa/espaço, afirmações como strings ou objeto, achados fora de lista);
- R3: bloqueante declarado pelo modelo (mesmo rebaixado por evidência inválida)
  precisa ser resolvido pelo patch da única rodada para aprovar;
- R4: patch não troca magnitude/unidade de número, não põe número por extenso
  novo, domínio novo de qualquer TLD (nem com ponto disfarçado), nem atributo em
  tag inline (texto oculto);
- R5: evidência que o código não resolve (briefing, identidade, intenção genérica)
  nunca vira patch automático;
- R6: fato `contexto` não sustenta número de patch.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from funnelforge.pipeline.revisao import validar_achados
from tests.test_revisor_decisao import (
    A_PROMESSA,
    P_PROMESSA,
    _resposta,
    _rodar,
)
from tests.test_revisor_patches import _achado, _aplicar, _doc_gutenberg, _patch, _refs

import json


# --------------------------------------------------------------------------- R1

def _bruto(**kw) -> str:
    base = {"versao": "revisao-v1", "decisao": "aprovado", "achados": [], "patches": [],
            "afirmacoes_nao_verificadas": [], "preservado": [],
            "notas": {"compliance": 9, "cta_discipline": 8, "useful_delivery": 8,
                      "destination_relevance": 8}}
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


@pytest.mark.parametrize("resposta", [
    _bruto(afirmacoes_nao_verificadas=["Toda familia recebe o desconto automaticamente"]),
    _bruto(afirmacoes_nao_verificadas={"corpo": "Toda familia recebe o desconto"}),
    _bruto(afirmacoes_nao_verificadas="Toda familia recebe o desconto"),
    _bruto(achados=[dict(A_PROMESSA, severidade="Bloqueante")]),
    _bruto(achados=[dict(A_PROMESSA, severidade="bloqueante ")]),
    _bruto(achados={"a1": A_PROMESSA}),
    _bruto(decisao=" Aprovado ", achados=[dict(A_PROMESSA, severidade="BLOQUEANTE")]),
], ids=["afirm_strings", "afirm_objeto", "afirm_texto", "sev_Bloqueante",
        "sev_espaco", "achados_objeto", "decisao_caixa"])
def test_r1_aprovado_incoerente_em_qualquer_forma_nao_aprova(tmp_path, resposta):
    r, _ = _rodar([resposta], tmp_path)
    assert r.decisao == "revisao_humana", r.registro["motivos"]
    assert "automaticamente" in r.documento.corpo


def test_r1_controle_aprovado_limpo_continua_aprovando(tmp_path):
    r, _ = _rodar([_bruto(decisao=" Aprovado ")], tmp_path)
    assert r.decisao == "aprovado"


def test_r1_severidade_normalizada_no_registro():
    doc = _doc_gutenberg()
    a = validar_achados([_achado(severidade=" Bloqueante ")], doc, _refs())[0]
    assert a["severidade"] == "bloqueante" and a["invalido"] is None


# --------------------------------------------------------------------------- R3

def test_r3_bloqueante_rebaixado_nao_some_depois_do_patch(tmp_path):
    invalido = dict(A_PROMESSA, id="a9", evidencia={"tipo": "fato", "ref": "n99"})
    ajuste = {"id": "a2", "severidade": "ajuste", "categoria": "congruencia_destino",
              "campo": "corpo", "trecho": "Fazer inscrição",
              "motivo": "o destino é um guia", "evidencia": {"tipo": "destino", "ref": "d1"}}
    p = {"achado": "a2", "campo": "corpo", "antes": "Fazer inscrição",
         "depois": "Ver como pedir"}
    r, llm = _rodar([_resposta("ajustar", [invalido, ajuste], [p]), _resposta()], tmp_path)
    assert len(llm.calls) == 1
    assert r.decisao == "revisao_humana"
    assert "bloqueante_nao_resolvido:a9" in r.registro["motivos"]


def test_r3_controle_bloqueante_resolvido_aprova(tmp_path):
    r, _ = _rodar([_resposta("ajustar", [A_PROMESSA], [P_PROMESSA]), _resposta()], tmp_path)
    assert r.decisao == "aprovado"


# --------------------------------------------------------------------------- R4

TRECHO = "um trecho comum sobre a conta"


@pytest.mark.parametrize("antes,depois,motivo", [
    ("prazo de 30 dias", "prazo de quarenta e cinco dias", "numero_novo"),
    ("valor de R$ 1.518 por mes", "valor de R$ 15,18 por mes", "numero_alterado"),
    ("prazo de 30 dias", "prazo de 30 meses", "numero_alterado"),
    (TRECHO, "veja em tarifa-facil.xyz", "url_nova"),
    (TRECHO, "use o pix.click agora", "url_nova"),
    (TRECHO, "veja em golpe․com․br", "url_nova"),
    (TRECHO, 'texto <em style="display:none">oculto</em> aqui', "tag_nao_permitida"),
])
def test_r4_patch_nao_muda_numero_dominio_ou_esconde_texto(antes, depois, motivo):
    doc = _doc_gutenberg()
    corpo = doc.corpo.replace(TRECHO, antes, 1)
    assert antes in corpo
    doc = type(doc)(formato=doc.formato, corpo=corpo, seotitle=doc.seotitle,
                    metadescription=doc.metadescription)
    novo, aplicados, recusados = _aplicar(
        doc, [_patch(antes, depois)],
        [_achado(trecho=antes, severidade="ajuste", categoria="erro_factual",
                 tipo="fato", ref="n1")], numeros=frozenset({"65", "30", "1518"}))
    assert aplicados == [], aplicados
    assert recusados[0]["motivo"] == motivo, recusados
    assert novo.corpo == doc.corpo


def test_r4_dominio_novo_no_seotitle_e_recusado():
    doc = _doc_gutenberg()
    novo, aplicados, recusados = _aplicar(
        doc, [_patch("quem tem direito", "veja em tarifa-facil.xyz", campo="seotitle")],
        [_achado(campo="seotitle", trecho="quem tem direito", severidade="ajuste",
                 categoria="erro_factual", tipo="fato", ref="n1")])
    assert aplicados == [] and recusados[0]["motivo"] == "url_nova"


@pytest.mark.parametrize("antes,depois", [
    ("prazo de 30 dias", "prazo de 30 dias corridos"),
    (TRECHO, "um trecho <strong>claro</strong> sobre a conta"),
    (TRECHO, "um trecho comum sobre a conta. Veja abaixo."),
])
def test_r4_controle_patch_legitimo_continua_aplicando(antes, depois):
    doc = _doc_gutenberg()
    corpo = doc.corpo.replace(TRECHO, antes, 1)
    doc = type(doc)(formato=doc.formato, corpo=corpo, seotitle=doc.seotitle,
                    metadescription=doc.metadescription)
    _novo, aplicados, recusados = _aplicar(
        doc, [_patch(antes, depois)],
        [_achado(trecho=antes, severidade="ajuste", categoria="erro_factual",
                 tipo="fato", ref="n1")])
    assert aplicados and not recusados, recusados


# --------------------------------------------------------------------------- R5

@pytest.mark.parametrize("tipo,ref", [("briefing", "qualquer"), ("identidade", "voz"),
                                      ("intencao", "tensao-inventada")])
def test_r5_evidencia_nao_resolvivel_nao_vira_patch(tipo, ref):
    doc = _doc_gutenberg()
    novo, aplicados, recusados = _aplicar(
        doc, [_patch("Fazer inscrição agora", "Ver como pedir")],
        [_achado(severidade="ajuste", tipo=tipo, ref=ref)])
    assert aplicados == [], aplicados
    assert recusados and recusados[0]["motivo"] == "achado_nao_patchavel", recusados
    assert novo.corpo == doc.corpo


def test_r5_controle_evidencia_resolvida_continua_patchavel():
    doc = _doc_gutenberg()
    _n, aplicados, _r = _aplicar(doc, [_patch("Fazer inscrição agora", "Ver como pedir")],
                                 [_achado(severidade="ajuste", tipo="destino", ref="d1")])
    assert aplicados


# --------------------------------------------------------------------------- R6

def test_r6_fato_de_contexto_nao_sustenta_numero_de_patch():
    from funnelforge.pipeline.steps import numeros_permitidos_no_patch

    fatos = [
        SimpleNamespace(tipo="numero", citavel=True, texto="65% de desconto",
                        dispositivo="", vigente_desde=None),
        SimpleNamespace(tipo="contexto", citavel=True, texto="8.621 familias atendidas",
                        dispositivo="", vigente_desde=None),
        SimpleNamespace(tipo="numero", citavel=False, texto="99 casos",
                        dispositivo="", vigente_desde=None),
        SimpleNamespace(tipo="fonte_legal", citavel=True, texto="Lei da tarifa social",
                        dispositivo="Lei 12.212", vigente_desde=None),
        SimpleNamespace(tipo="condicao", citavel=True, texto="renda de ate meio salario",
                        dispositivo="art. 777", vigente_desde="2031-01-01"),
    ]
    ok = numeros_permitidos_no_patch(fatos)
    assert "65" in ok and "12212" in ok
    assert "8621" not in ok and "99" not in ok
    assert "777" not in ok and "2031" not in ok
