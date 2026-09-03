"""WEBGO_PRIORS_NON_DECISIONAL_PROVEN — por mutação, não por flag.

Testar `pode_decidir is False` prova apenas que alguém escreveu `False` num
dicionário. Este arquivo prova o comportamento: **mutando arbitrariamente os
priors** — valores, confiança, sinal, quantidade, até invertendo a afirmação —
e verificando que, com a entrada operacional idêntica, nada muda em:

    decisão · veredito/estado · formato recomendado · fatos · desconhecidos
    contradições · próximo experimento · índice citado · cobertura
    comparabilidade · ORDEM do ranking · oportunidade escolhida

Priors podem aparecer em `hipoteses` — é para isso que existem. O teste separa
essas duas coisas explicitamente: a lista de hipóteses PODE mudar; tudo o que
decide, NÃO.
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List

import pytest

import app.validacao.oportunidade as mod
from app.validacao.oportunidade import comparar, tese_do_resumo


def _resumo(indice=0.72, cobertura=1.0, ramos=3, condicoes=3,
            engajamento="sustenta", fecha=False, **over) -> Dict[str, Any]:
    base = {
        "apto": True, "motivo": None, "indice": indice, "cobertura": cobertura,
        "perfil": "alvo", "portoes_disparados": [], "alertas": [],
        "eixos": {
            "volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None},
            "engajamento": {"nivel": engajamento, "proveniencia": "julgado", "motivo_ausencia": None},
            "ignorancia": {"nivel": "nao_sei_se_sirvo", "proveniencia": "julgado", "motivo_ausencia": None},
        },
        "ficha": {
            "share_dado_unico": 0.25, "n_perguntas": 2,
            "perguntas": [
                {"pergunta": "Quem tem direito?", "ramos": ramos, "condicoes": condicoes,
                 "decide_depois": True, "oficial_fecha_sozinho": fecha},
                {"pergunta": "Quando cai?", "ramos": 1, "condicoes": 0,
                 "decide_depois": False, "oficial_fecha_sozinho": True},
            ],
        },
    }
    base.update(over)
    return base


# ── o que conta como DECISÓRIO ───────────────────────────────────────────────

CAMPOS_DECISORIOS = (
    "decisao", "porque", "formato_de_funil", "observaveis_do_formato",
    "fatos", "desconhecidos", "contradicoes", "proximo_experimento",
    "indice_citado", "cobertura", "perfil_citado", "comparavel",
    "motivo_incomparavel", "versao_do_contrato",
)


def _decisorio(t) -> tuple:
    return tuple(getattr(t, c) for c in CAMPOS_DECISORIOS)


# ── as mutações arbitrárias ──────────────────────────────────────────────────

def _priors_mutados(estilo: str):
    """Devolve uma tabela de priors deliberadamente adulterada."""
    base = [dict(p) for p in mod.PRIORS_WEBGO]
    if estilo == "vazio":
        return ()
    if estilo == "confianca_alta":
        for p in base:
            p["confianca"] = "alta"
        return tuple(base)
    if estilo == "pode_decidir_true":
        # A adulteração mais agressiva: alguém liga o interruptor.
        for p in base:
            p["pode_decidir"] = True
        return tuple(base)
    if estilo == "afirmacao_invertida":
        for p in base:
            p["afirmacao"] = "O OPOSTO: " + str(p["afirmacao"])
            p["tem_controle"] = "nao"
        return tuple(base)
    if estilo == "peso_numerico":
        # Um peso numérico, que é exatamente o que o benchmark NÃO pode dar.
        for i, p in enumerate(base):
            p["peso"] = 10.0 ** i
            p["multiplicador"] = -999
        return tuple(base)
    if estilo == "multiplicado":
        return tuple(base * 7)
    if estilo == "um_so":
        return (base[0],)
    if estilo == "lixo":
        return ({"id": "x", "afirmacao": None, "confianca": "alta",
                 "tem_controle": "sim", "pode_decidir": True, "uso": None},)
    raise AssertionError(estilo)


ESTILOS = ["vazio", "confianca_alta", "pode_decidir_true", "afirmacao_invertida",
           "peso_numerico", "multiplicado", "um_so", "lixo"]

CASOS = {
    "vencedor": _resumo(),
    "perdedor": _resumo(indice=0.0, engajamento="dado_unico",
                        portoes_disparados=["engajamento"], apto=False,
                        motivo="portao_engajamento", perfil="descartar"),
    "deterioracao": _resumo(indice=0.41, ramos=2, condicoes=1),
    "oficial_fecha": _resumo(fecha=True),
    "sem_cobertura": _resumo(cobertura=0.2),
    "resposta_unica": _resumo(ramos=1, condicoes=0),
    "extremo_alto": _resumo(indice=1.0, cobertura=1.0),
    "extremo_baixo": _resumo(indice=0.0001, cobertura=0.51),
    "sem_validacao": None,
}


@pytest.mark.parametrize("estilo", ESTILOS)
@pytest.mark.parametrize("caso", sorted(CASOS))
def test_mutar_priors_nao_muda_nada_decisorio(monkeypatch, estilo, caso):
    resumo = CASOS[caso]
    referencia = _decisorio(tese_do_resumo(resumo, tema=caso, aplicar_priors=True))

    monkeypatch.setattr(mod, "PRIORS_WEBGO", _priors_mutados(estilo))
    mutado = _decisorio(tese_do_resumo(resumo, tema=caso, aplicar_priors=True))

    assert mutado == referencia, (
        f"priors mutados ({estilo}) mudaram a decisão do caso {caso!r}"
    )


@pytest.mark.parametrize("estilo", ESTILOS)
def test_mutar_priors_nao_reordena_o_ranking(monkeypatch, estilo):
    """A oportunidade ESCOLHIDA não pode depender do que o benchmark diz."""
    def ranking():
        teses = [tese_do_resumo(CASOS[k], tema=k, aplicar_priors=True)
                 for k in sorted(CASOS)]
        aptos, fora = comparar(teses)
        return [t.tema for t in aptos], [t.tema for t in fora]

    antes = ranking()
    monkeypatch.setattr(mod, "PRIORS_WEBGO", _priors_mutados(estilo))
    depois = ranking()
    assert depois == antes, f"priors mutados ({estilo}) reordenaram o ranking"


@pytest.mark.parametrize("estilo", ESTILOS)
def test_mutar_priors_nao_muda_a_escolha_do_topo(monkeypatch, estilo):
    def topo():
        teses = [tese_do_resumo(CASOS[k], tema=k, aplicar_priors=True)
                 for k in sorted(CASOS)]
        aptos, _ = comparar(teses)
        return aptos[0].tema if aptos else None

    antes = topo()
    monkeypatch.setattr(mod, "PRIORS_WEBGO", _priors_mutados(estilo))
    assert topo() == antes, f"priors mutados ({estilo}) trocaram a oportunidade escolhida"


def test_ligar_e_desligar_priors_nao_muda_nada_decisorio():
    """O interruptor `aplicar_priors` só acende contexto."""
    for caso, resumo in CASOS.items():
        desligado = tese_do_resumo(resumo, tema=caso, aplicar_priors=False)
        ligado = tese_do_resumo(resumo, tema=caso, aplicar_priors=True)
        assert _decisorio(ligado) == _decisorio(desligado), caso


def test_priors_APARECEM_como_hipotese_quando_ligados():
    """A contraprova da contraprova: se ligar os priors não mudasse NADA
    observável, o teste acima passaria vacuamente — ele estaria provando que a
    feature não existe, não que ela é não-decisória."""
    t_off = tese_do_resumo(_resumo(), tema="t", aplicar_priors=False)
    t_on = tese_do_resumo(_resumo(), tema="t", aplicar_priors=True)
    assert not t_off.hipoteses
    assert len(t_on.hipoteses) == len(mod.PRIORS_WEBGO)
    for h in t_on.hipoteses:
        assert "prior" in h and "confiança" in h and "controle" in h, (
            "o prior precisa viajar com procedência visível"
        )


def test_hipoteses_e_fatos_nunca_se_misturam_com_priors_ligados():
    t = tese_do_resumo(_resumo(), tema="t", aplicar_priors=True)
    assert not (set(t.fatos) & set(t.hipoteses))
    assert not (set(t.hipoteses) & set(t.desconhecidos))
    for h in t.hipoteses:
        assert h not in t.fatos


def test_nenhum_prior_pode_decidir_no_codigo_entregue():
    """A flag, que sozinha não bastaria — mas somada às mutações acima fecha."""
    assert mod.PRIORS_WEBGO, "a tabela não pode estar vazia: seria prova vazia"
    for p in mod.PRIORS_WEBGO:
        assert p["pode_decidir"] is False, p["id"]
        assert p["confianca"] in ("baixa", "media", "alta")
        assert p["tem_controle"] in ("sim", "nao", "parcial")


def test_a_densidade_de_anuncio_entra_como_hipotese_e_nao_como_peso():
    """O único padrão do corpus com gradiente monotônico e controle. Ele é
    economia paga e não pode virar peso editorial."""
    d = [p for p in mod.PRIORS_WEBGO if p["id"] == "webgo/densidade-de-anuncio"]
    assert d, "o prior precisa continuar registrado"
    assert d[0]["pode_decidir"] is False
    assert d[0]["confianca"] == "baixa"
    # e ele não pode aparecer entre os observáveis aceitos
    assert not any("densidade_de_anuncio" in o or "anuncio" in o
                   for o in mod.OBSERVAVEIS_ACEITOS)
