"""Proveniência pela autoridade emissora (não só pelo host), hints do operador
conferidos no documento e o fato derivado `2 × 1621 = 3242` com linhagem."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from funnelforge.domain.models import DerivacaoDeclarada
from funnelforge.pipeline.dossie import RespostaDaPesquisa, fatos_da_resposta
from funnelforge.pipeline.proveniencia import proveniencia_do_documento
from tests.test_dossie_factual import (
    FATOS_COMPLETOS,
    RENDA,
    _compilar,
    _estado,
    _n,
    _Pesquisa,
    _Verificador,
    CITADAS,
)

DN = "https://www.dn.senac.br/portalpsg/assets/arquivos/diretrizes-psg-10.pdf"
ES = "https://es.senac.br/assets/docs/diretrizes-psg-10.pdf"
MA = "https://ma.senac.br/wp-content/uploads/2026/03/EDITAL-PSG-No-56.2026.pdf"
DEC = "https://planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12797.htm"
HOJE = date(2026, 10, 7)

DIRETRIZES = ("SENAC Departamento Nacional. Programa Senac de Gratuidade — Diretrizes. Versão 10. "
              "O PSG destina-se a pessoas de baixa renda cuja renda familiar mensal per capita "
              "não ultrapasse 2 (dois) salários mínimos federais. O cálculo soma a renda bruta "
              "dos membros e divide pelo número de pessoas do grupo familiar.")
DECRETO = ("Presidência da República. Casa Civil. DECRETO Nº 12.797, DE 23 DE DEZEMBRO DE 2025. "
           "O PRESIDENTE DA REPÚBLICA, no uso da atribuição... Art. 1º A partir de 1º de janeiro "
           "de 2026, o salário mínimo será de R$ 1.621,00 (mil seiscentos e vinte e um reais).")
EDITAL_MA = ("SENAC Departamento Regional no Maranhão. Edital PSG nº 56/2026. Conforme diretrizes "
             "do Conselho Nacional, a renda familiar per capita de até 02 (dois) salários "
             "mínimos federais.")

DOCS = {DN: DIRETRIZES, ES: DIRETRIZES, MA: EDITAL_MA, DEC: DECRETO}


def ler(url):
    if url not in DOCS:
        return {"ok": False, "motivo": "HTTP 404", "status": 404}
    return {"ok": True, "motivo": "", "status": 200, "content_type": "application/pdf",
            "sha256": f"sha-{len(DOCS[url])}", "titulo": "", "texto": DOCS[url]}


HINT_REGRA = {"url": DN, "requisitos": [RENDA], "paginas": ["renda"], "tipo": "condicao",
              "valor": "2", "unidade": "salários mínimos federais",
              "afirmacao": "A renda familiar mensal per capita não pode ultrapassar dois "
                           "salários mínimos federais"}
HINT_SM = {"url": DEC, "requisitos": ["salario_minimo.vigente"], "paginas": ["renda"],
           "tipo": "numero", "valor": "1.621,00", "unidade": "R$", "vigente_desde": "2026-01-01",
           "afirmacao": "A partir de 1º de janeiro de 2026 o salário mínimo será de R$ 1.621,00"}
SEM_RENDA = [f for f in FATOS_COMPLETOS
             if not set(f["requisitos"]) & {RENDA, "renda.valor_vigente", "salario_minimo.vigente"}]


def _dossie(hints, vivas=None, fatos=SEM_RENDA, hoje=HOJE):
    from funnelforge.pipeline.dossie import compilar_dossie
    from tests.test_dossie_factual import _Deps, _registrar_canais
    state = _estado()
    citadas = CITADAS + list(DOCS)
    dossie = compilar_dossie(state, _Deps(_Verificador(vivas=vivas or citadas)),
                             _Pesquisa(fatos, [], [], citacoes=citadas),
                             registrar_canais=_registrar_canais, hoje=hoje,
                             hints=hints, ler_documento=ler)
    return state, dossie


def _renda(state, dossie):
    return dossie.pagina(_n(state, "renda"))


# --- proveniência -----------------------------------------------------------

def test_documento_nacional_em_dominio_nacional():
    p = proveniencia_do_documento(DN, ler(DN))
    assert (p["issuer"], p["issuer_scope"], p["jurisdiction"]) == (
        "Senac — Departamento Nacional", "national", "BR")
    assert p["canonica"] and not p["espelho"] and p["document_version"] == "10"
    assert "departamento nacional" in p["trecho_de_autoria"] and p["content_sha256"]
    d = proveniencia_do_documento(DEC, ler(DEC))
    assert (d["issuer"], d["issuer_scope"], d["effective_from"]) == (
        "Presidência da República", "national", "2026-01-01")


def test_espelho_regional_com_autoria_nacional_comprovada_e_canonica_preferida():
    p = proveniencia_do_documento(ES, ler(ES))
    assert p["issuer_scope"] == "national" and p["espelho"] and not p["canonica"]
    hint_es = dict(HINT_REGRA, url=ES)
    state, dossie = _dossie([hint_es, HINT_REGRA, HINT_SM])
    regra = next(v for v in _renda(state, dossie).cobertura.vinculos if v["papel"] == "regra")
    assert regra["url"] == DN and regra["emissor"] == "Senac — Departamento Nacional"


def test_pagina_regional_sem_autoria_nacional_e_recusada_como_regra():
    p = proveniencia_do_documento(MA, ler(MA))
    assert (p["issuer_scope"], p["jurisdiction"]) == ("regional", "MA")   # "Conselho Nacional" citado depois
    hint_ma = dict(HINT_REGRA, url=MA, valor="2",
                   afirmacao="renda familiar per capita de até dois salários mínimos federais")
    state, dossie = _dossie([hint_ma, HINT_SM])
    cob = _renda(state, dossie).cobertura
    assert not cob.ready_to_write
    assert any("sem fonte NACIONAL oficial" in b for b in cob.blockers)


# --- hints --------------------------------------------------------------------

def test_hint_e_conferido_no_documento_e_nao_vira_fato_sem_sustentacao():
    errado = dict(HINT_SM, valor="1.700,00",
                  afirmacao="A partir de 1º de janeiro de 2026 o salário mínimo será de R$ 1.700,00")
    state, dossie = _dossie([HINT_REGRA, errado])
    fatos = {f.source_url: f for f in dossie.fatos if f.origem == "hint_do_operador"}
    assert fatos[DN].status == "verified" and fatos[DN].proveniencia["issuer_scope"] == "national"
    assert fatos[DEC].status == "unverified"
    assert fatos[DEC].motivo_do_status.startswith("hint não sustentado")
    sem_doc = dict(HINT_REGRA, url="https://www.dn.senac.br/nao-existe.pdf")
    _, d2 = _dossie([sem_doc])
    assert next(f for f in d2.fatos if f.origem == "hint_do_operador").motivo_do_status \
        .startswith("hint não lido")


# --- derivados ----------------------------------------------------------------

def test_derivacao_2_x_1621_e_3242_com_linhagem():
    state, dossie = _dossie([HINT_REGRA, HINT_SM])
    renda = _renda(state, dossie)
    assert renda.cobertura.ready_to_write, renda.cobertura.blockers
    derivado = next(f for f in dossie.fatos if f.origem == "derivado")
    d = derivado.derivacao
    assert (derivado.valor, derivado.unidade, d["formula"]) == ("3.242,00", "R$", "2 × 1621")
    assert d["metodo"] == "deterministic_multiplication" and d["jurisdicao"] == "BR"
    premissas = {f.fact_id: f for f in dossie.fatos if f.fact_id in d["premissas"]}
    assert {f.source_url for f in premissas.values()} == {DN, DEC}
    assert derivado.vigente_desde == date(2026, 1, 1) and derivado.source_url == ""
    assert "não é valor publicado literalmente" in derivado.afirmacao
    valor = next(v for v in renda.cobertura.vinculos if v["papel"] == "valor_vigente")
    assert valor["fact_id"] == derivado.fact_id and valor["formula"] == "2 × 1621"
    # a projeção para o redator mostra a conta, não uma "fonte" do 3.242
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    proj = projecao_para_o_prompt(dossie.model_dump(mode="json"), renda.page_number)
    item = next(f for f in proj["fatos"] if f["id"] == derivado.fact_id)
    assert item["derivacao"] == "2 × 1621" and set(item["premissas"]) == set(d["premissas"])


def test_mudanca_de_vigencia_ou_de_premissa_invalida_o_derivado():
    _, base = _dossie([HINT_REGRA, HINT_SM])
    original = next(f for f in base.fatos if f.origem == "derivado")
    futuro = dict(HINT_SM, vigente_desde="2027-01-01",
                  afirmacao="A partir de 1º de janeiro de 2027 o salário mínimo será de R$ 1.621,00")
    DOCS[DEC + "?v=2027"] = DECRETO.replace("2026", "2027")
    try:
        state, dossie = _dossie([HINT_REGRA, dict(futuro, url=DEC + "?v=2027")],
                                vivas=CITADAS + list(DOCS))
    finally:
        DOCS.pop(DEC + "?v=2027")
    assert not [f for f in dossie.fatos if f.origem == "derivado"]
    assert any("premissa ainda não vigente" in b for b in _renda(state, dossie).cobertura.blockers)
    # premissa com outro valor -> outro derivado (o antigo não sobrevive)
    DOCS[DEC + "?v=b"] = DECRETO.replace("1.621,00", "1.700,00")
    try:
        _, outro = _dossie([HINT_REGRA, dict(HINT_SM, url=DEC + "?v=b", valor="1.700,00",
                            afirmacao="A partir de 1º de janeiro de 2026 o salário mínimo será "
                                      "de R$ 1.700,00")], vivas=CITADAS + list(DOCS))
    finally:
        DOCS.pop(DEC + "?v=b")
    novo = next(f for f in outro.fatos if f.origem == "derivado")
    assert novo.valor == "3.400,00" and novo.fact_id != original.fact_id
    assert original.fact_id not in {f.fact_id for f in outro.fatos}


def test_premissa_nao_verificada_recusa_o_derivado():
    state, dossie = _dossie([HINT_REGRA, HINT_SM], vivas=[u for u in CITADAS + list(DOCS)
                                                          if u != DEC])
    assert not [f for f in dossie.fatos if f.origem == "derivado"]
    blockers = _renda(state, dossie).cobertura.blockers
    assert any("premissa 'salario_minimo.vigente' (r$) sem fato verificado" in b for b in blockers)


def test_jurisdicao_divergente_recusa_o_derivado():
    hint_ma = dict(HINT_REGRA, url=MA,
                   afirmacao="renda familiar per capita de até dois salários mínimos federais")
    state, dossie = _dossie([hint_ma, HINT_SM])
    assert any("jurisdição divergente" in b for b in _renda(state, dossie).cobertura.blockers)


def test_formula_livre_do_modelo_e_recusada():
    with pytest.raises(ValidationError):
        DerivacaoDeclarada(operacao="expressao", unidade_resultado="R$",
                           fatores=[{"requisito": "a", "unidade": "x"},
                                    {"requisito": "b", "unidade": "y"}])
    bruto = {"afirmacao": "O limite em 2026 é R$ 3.242,00 (2 × 1621)", "tipo": "numero",
             "valor": "3.242,00", "unidade": "R$", "fonte": DN, "vigente_desde": "2026-01-01",
             "origem": "derivado", "derivacao": {"formula": "2*1621"},
             "proveniencia": {"issuer_scope": "national"},
             "requisitos": ["renda.valor_vigente"], "paginas": ["renda"]}
    fato = fatos_da_resposta(RespostaDaPesquisa(dados={"fatos": [bruto]}, citacoes=[DN],
                                                auth_mode="chatgpt_plan"))[0]
    assert fato.origem == "pesquisa" and fato.derivacao == {} and fato.proveniencia == {}
    # e, como literal, o 3.242 precisa estar na página citada — nas Diretrizes não está
    state, dossie = _dossie([], fatos=SEM_RENDA + [bruto])
    assert not [f for f in dossie.fatos if f.origem == "derivado"]
