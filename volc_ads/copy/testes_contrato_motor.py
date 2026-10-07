"""Teste de contrato entre as trilhas (B8, 30/09/2026): motor × volc_ads.

O contrato entre as trilhas fixa DOIS formatos que cruzam a fronteira:
- o vocabulário fechado de tipos de fato (decisão 2);
- o JSON `TermosDeBusca` ("mesmo JSON nos dois lados; cada lado valida o seu;
  teste de contrato compara").

Cada lado tem a sua implementação (dataclass aqui, pydantic no motor). Este
teste importa as duas e prova que o que um emite o outro aceita, sem perda.
Não fala com rede nem com LLM.

Rodar:
    PYTHONPATH=. backend/.venv/bin/python -m pytest volc_ads/copy/testes_contrato_motor.py -q
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

_MOTOR_SRC = Path(__file__).resolve().parents[2] / "funnelforge-migracao" / "engine" / "src"
if str(_MOTOR_SRC) not in sys.path:
    sys.path.insert(0, str(_MOTOR_SRC))

motor = pytest.importorskip("funnelforge.domain.models")

from volc_ads import pautador_ponte as ponte  # noqa: E402
from volc_ads.copy import contrato  # noqa: E402
from volc_ads.inteligencia_google import modelo  # noqa: E402

VOCABULARIO_DO_CONTRATO = {"numero", "prazo", "data", "mudanca", "condicao",
                           "orgao", "fonte_legal", "processo", "contexto"}
SHA = "a" * 64


def test_vocabulario_de_tipos_de_fato_e_o_mesmo_dos_dois_lados():
    assert set(motor.TIPOS_DE_FATO) == VOCABULARIO_DO_CONTRATO
    usados_aqui = set().union(*contrato.HABILITA_MECANICA.values()) | set(contrato.SO_NOMEIA)
    assert usados_aqui <= set(motor.TIPOS_DE_FATO), usados_aqui - set(motor.TIPOS_DE_FATO)
    assert contrato.SO_NOMEIA == frozenset({"contexto"})


@pytest.mark.parametrize("grafia", ["Fonte legal", "fonte-legal", "Condição", "MUDANÇA",
                                    " numero ", "Órgão"])
def test_grafia_canonica_do_tipo_e_a_mesma(grafia):
    assert ponte._canon_tipo(grafia) == motor.canon_tipo_de_fato(grafia)


def test_estados_e_fonte_de_termos_sao_os_mesmos():
    campo = motor.TermosDeBusca.model_fields["estado"].annotation
    assert set(campo.__args__) == set(modelo.ESTADOS_TERMOS)
    assert motor._FONTE_DE_TERMOS_RE.pattern == modelo._FONTE_TERMOS.pattern


def _janela():
    return modelo.JanelaDeTermos(date(2026, 9, 1), date(2026, 9, 29))


@pytest.mark.parametrize("termos", [
    modelo.TermosDeBusca(
        estado="presente", janela=_janela(), coletado_em="2026-09-30T10:00:00-03:00",
        fonte="search_term_view",
        termos=(modelo.TermoDeBusca("cursos gratuitos senac", 120, 9, 4.5),
                modelo.TermoDeBusca("senac inscrição", 40, 2, None))),
    modelo.TermosDeBusca(
        estado="vazio_confirmado", janela=_janela(),
        coletado_em="2026-09-30T10:00:00-03:00", fonte=f"arquivo:{SHA}"),
    modelo.TermosDeBusca(estado="ausente", motivo_ausencia="funil novo, sem campanha"),
], ids=["presente", "vazio_confirmado", "ausente"])
def test_termos_de_busca_ida_e_volta_sem_perda(termos):
    emitido = termos.para_json()
    aceito = motor.TermosDeBusca.model_validate(emitido)
    devolvido = aceito.model_dump(mode="json")
    assert set(devolvido) == set(emitido)
    assert devolvido["estado"] == emitido["estado"]
    assert devolvido["termos"] == emitido["termos"]
    assert devolvido["janela"] == emitido["janela"]
    assert modelo.TermosDeBusca.de_json(devolvido).para_json() == emitido


@pytest.mark.parametrize("ruim", [
    {"estado": "ausente", "termos": [{"termo": "x", "impressoes": 1, "cliques": 0,
                                      "custo": None}], "motivo_ausencia": "m"},
    {"estado": "presente", "termos": [], "janela": None, "coletado_em": None,
     "fonte": "search_term_view"},
    {"estado": "vazio_confirmado", "janela": {"inicio": "2026-09-01", "fim": "2026-09-29",
                                              "fuso": "America/Sao_Paulo"},
     "coletado_em": "2026-09-30", "fonte": "planilha", "termos": []},
])
def test_o_que_um_lado_recusa_o_outro_tambem_recusa(ruim):
    with pytest.raises(Exception):
        motor.TermosDeBusca.model_validate(ruim)
    with pytest.raises(Exception):
        modelo.TermosDeBusca.de_json(ruim)


# ── S2 · item 5: a regra de LEGADO da tipagem é UMA só (30/09/2026) ─────────
#
# Antes, o motor procurava a norma em qualquer ponto da unidade (e "leitura"
# casava "lei"); a ponte ancorava no começo e conhecia "Dispositivo Legal". O
# mesmo fato sem `tipo` saía com tipos diferentes nos dois lados. Agora os dois
# usam o MESMO arquivo; estes testes provam isso por origem e por comportamento.

inventario = pytest.importorskip("funnelforge.pipeline.inventario")

from volc_ads import tipagem_de_fatos as regra_do_volc_ads  # noqa: E402

UNIDADES = [
    "Lei Ordinária", "Lei Complementar", "Dispositivo Legal",
    "dispositivo legal de instituição", "Portaria", "Decreto-Lei", "Lei Federal (LDB)",
    "número do Decreto-Lei que autorizou a criação do Senac", "Resolução", "Ley",
    "horas de leitura obrigatória", "salários mínimos (conforme a Lei 8.213)",
    "%", "Data Limite", "reais por mês", "", "   ",
    "percentual da Receita de Contribuição Compulsória Líquida",
]


def test_a_regra_de_legado_mora_num_arquivo_so():
    arquivo = regra_do_volc_ads.ARQUIVO.resolve()
    assert Path(inventario.tipo_pela_regra_de_legado.__code__.co_filename).resolve() == arquivo
    assert Path(ponte.tipo_pela_regra_de_legado.__code__.co_filename).resolve() == arquivo
    # nenhuma cópia da regra sobrou nos dois lados
    fonte_ponte = Path(ponte.__file__).read_text(encoding="utf-8")
    fonte_inv = Path(inventario.__file__).read_text(encoding="utf-8")
    assert "_UNIDADE_E_NORMA" not in fonte_ponte
    assert "_REFERENCIA_LEGAL_RE" not in fonte_inv


@pytest.mark.parametrize("unidade", UNIDADES)
def test_mesmo_fato_sem_tipo_recebe_o_mesmo_tipo_nos_dois_lados(unidade):
    """Comportamento de ponta: o fato passa pelo `_fatos` da ponte e pelo
    `_fatos` do inventário do motor, e sai com o mesmo tipo e a mesma origem."""
    verificado = {"valor": "10", "unidade": unidade or "x",
                  "fonte_primaria": "https://www.planalto.gov.br/a.htm",
                  "dispositivo": "Art. 1º do Decreto nº 6.633", "vigente_desde": "2008-11-05",
                  "verificado_em": "2026-09-17"}
    if not unidade.strip():
        verificado["unidade"] = unidade or " "
    dado = {"fato": "O Senac tem 27 Departamentos Regionais.", "fonte": "https://s.br"}
    p1 = {"dados_validados": [dado], "fatos_verificados": [verificado]}

    _resumo, da_ponte = ponte._fatos({"facts": {"1": p1}}, 1)
    facts = motor.ResearchFacts(dados_validados=[dado], fatos_verificados=[
        motor.VerifiedFact(**{**verificado, "unidade": verificado["unidade"]})])
    do_motor = inventario._fatos(facts)

    assert [(f.id, f.tipo, f.tipo_origem) for f in da_ponte] == \
           [(f.id, f.tipo, f.tipo_origem) for f in do_motor]
    assert {f.tipo_origem for f in do_motor} == {"regra_legado"}


def test_a_regra_acerta_os_casos_que_divergiam():
    r = regra_do_volc_ads.tipo_pela_regra_de_legado
    assert r("fatos_verificados", "Dispositivo Legal") == "fonte_legal"   # o motor dizia numero
    assert r("fatos_verificados", "horas de leitura obrigatória") == "numero"  # o motor dizia lei
    assert r("fatos_verificados", "salários mínimos (conforme a Lei 8.213)") == "numero"
    assert r("dados_validados", "Lei Ordinária") == "contexto"
