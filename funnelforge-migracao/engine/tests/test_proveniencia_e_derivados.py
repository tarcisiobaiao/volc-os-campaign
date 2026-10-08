"""Proveniência GENÉRICA (emissor declarado e comprovado no documento — nunca
pelo hostname), hints do operador conferidos no documento e o fato derivado
com linhagem. O caso Senac é só regressão: nenhuma regra aqui é do Senac."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from funnelforge.domain.models import DerivacaoDeclarada
from funnelforge.pipeline.dossie import RespostaDaPesquisa, fatos_da_resposta
from funnelforge.pipeline.proveniencia import proveniencia_do_documento
from tests.test_dossie_factual import (
    CITADAS,
    FATOS_COMPLETOS,
    RENDA,
    _estado,
    _n,
    _Pesquisa,
    _Verificador,
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
           "Art. 1º A partir de 1º de janeiro de 2026, o salário mínimo será de R$ 1.621,00 "
           "(mil seiscentos e vinte e um reais).")
EDITAL_MA = ("SENAC Departamento Regional no Maranhão. Edital PSG nº 56/2026. Conforme diretrizes "
             "do Conselho Nacional, a renda familiar per capita de até 02 (dois) salários "
             "mínimos federais.")
DOCS = {DN: DIRETRIZES, ES: DIRETRIZES, MA: EDITAL_MA, DEC: DECRETO}

NACIONAL_DN = {"emissor": "Departamento Nacional", "tipo_de_emissor": "instituicao_oficial",
               "escopo": "nacional", "jurisdicao": "BR"}
REGIONAL_MA = {"emissor": "Departamento Regional no Maranhão",
               "tipo_de_emissor": "instituicao_oficial", "escopo": "subnacional",
               "jurisdicao": "BR-MA"}
GOVERNO = {"emissor": "Presidência da República", "tipo_de_emissor": "governo",
           "escopo": "nacional", "jurisdicao": "BR"}


def ler(url):
    if url not in DOCS:
        return {"ok": False, "motivo": "página não lida (ReadError)"}
    return {"ok": True, "motivo": "", "status": 200, "content_type": "application/pdf",
            "sha256": f"sha-{len(DOCS[url])}", "titulo": "", "texto": DOCS[url]}


HINT_REGRA = dict(NACIONAL_DN, url=DN, requisitos=[RENDA], paginas=["renda"], tipo="condicao",
                  valor="2", unidade="salários mínimos federais",
                  afirmacao="A renda familiar mensal per capita não pode ultrapassar dois "
                            "salários mínimos federais")
HINT_SM = dict(GOVERNO, url=DEC, requisitos=["salario_minimo.vigente"], paginas=["renda"],
               tipo="numero", valor="1.621,00", unidade="R$", vigente_desde="2026-01-01",
               afirmacao="A partir de 1º de janeiro de 2026 o salário mínimo será de R$ 1.621,00")
SEM_RENDA = [f for f in FATOS_COMPLETOS
             if not set(f["requisitos"]) & {RENDA, "renda.valor_vigente", "salario_minimo.vigente"}]


class _Bloqueado(_Verificador):
    """Verificador cujo transporte é recusado para algumas URLs (WAF)."""

    def __init__(self, vivas, bloqueadas=()):
        super().__init__(vivas=vivas)
        self.bloqueadas_ = set(bloqueadas)

    def bloqueada(self, url):
        return url in self.bloqueadas_


def _dossie(hints, vivas=None, fatos=SEM_RENDA, hoje=HOJE, verificador=None):
    from funnelforge.pipeline.dossie import compilar_dossie
    from tests.test_dossie_factual import _Deps, _registrar_canais
    state = _estado()
    citadas = CITADAS + list(DOCS)
    dossie = compilar_dossie(state, _Deps(verificador or _Verificador(vivas=vivas or citadas)),
                             _Pesquisa(fatos, [], [], citacoes=citadas),
                             registrar_canais=_registrar_canais, hoje=hoje,
                             hints=hints, ler_documento=ler)
    return state, dossie


def _renda(state, dossie):
    return dossie.pagina(_n(state, "renda"))


# --- proveniência -----------------------------------------------------------

def test_documento_de_emissor_nacional_comprovado_no_proprio_documento():
    p = proveniencia_do_documento(DN, ler(DN), NACIONAL_DN)
    assert p["emissor_verificado"] and (p["escopo"], p["jurisdicao"]) == ("nacional", "BR")
    assert p["tipo_de_emissor"] == "instituicao_oficial" and p["document_version"] == "10"
    assert "departamento nacional" in p["trecho_de_autoria"] and p["content_sha256"]
    d = proveniencia_do_documento(DEC, ler(DEC), GOVERNO)
    assert d["emissor_verificado"] and d["tipo_de_emissor"] == "governo"


def test_espelho_de_outro_host_com_autoria_nacional_no_documento_e_aceito():
    p = proveniencia_do_documento(ES, ler(ES), NACIONAL_DN)
    assert p["emissor_verificado"] and p["escopo"] == "nacional"
    state, dossie = _dossie([dict(HINT_REGRA, url=ES), HINT_SM])
    regra = next(v for v in _renda(state, dossie).cobertura.vinculos if v["papel"] == "regra")
    assert regra["url"] == ES and regra["emissor"] == "Departamento Nacional"


def test_pagina_regional_sem_autoria_nacional_nao_prova_regra_do_pais():
    # declarar "nacional" não basta: a frase do emissor não está no documento
    falso = proveniencia_do_documento(MA, ler(MA), NACIONAL_DN)
    assert not falso["emissor_verificado"] and falso["escopo"] == "desconhecido"
    honesto = proveniencia_do_documento(MA, ler(MA), REGIONAL_MA)
    assert (honesto["escopo"], honesto["jurisdicao"]) == ("subnacional", "BR-MA")
    hint_ma = dict(HINT_REGRA, **REGIONAL_MA, url=MA,
                   afirmacao="renda familiar per capita de até dois salários mínimos federais")
    state, dossie = _dossie([hint_ma, HINT_SM])
    cob = _renda(state, dossie).cobertura
    assert cob.ready_to_write                                   # a página não morre
    assert not [v for v in cob.vinculos if v["papel"] == "regra"]
    assert any(d["tipo"] == "ativo" for d in cob.desativados)  # só a ferramenta sai


# --- hints e indisponibilidade ---------------------------------------------------

def test_hint_e_conferido_no_documento_e_inacessivel_vira_indisponivel_nao_falso():
    errado = dict(HINT_SM, valor="1.700,00",
                  afirmacao="A partir de 1º de janeiro de 2026 o salário mínimo será de R$ 1.700,00")
    state, dossie = _dossie([HINT_REGRA, errado])
    fatos = {f.source_url: f for f in dossie.fatos if f.origem == "hint_do_operador"}
    assert fatos[DN].status == "verified" and fatos[DN].proveniencia["escopo"] == "nacional"
    assert fatos[DEC].status == "unverified"
    assert fatos[DEC].motivo_do_status.startswith("hint não sustentado")
    fora = dict(HINT_SM, url="https://www.planalto.gov.br/indisponivel.htm")
    _, d2 = _dossie([HINT_REGRA, fora])
    f2 = next(f for f in d2.fatos if f.source_url.endswith("indisponivel.htm"))
    assert f2.status == "unavailable" and f2.motivo_do_status.startswith("hint não lido")


def test_fonte_oficial_inacessivel_nao_vira_fato_falso_e_a_pagina_segue():
    verif = _Bloqueado(vivas=[u for u in CITADAS + list(DOCS) if u != DEC], bloqueadas=[DEC])
    state, dossie = _dossie([HINT_REGRA, HINT_SM], verificador=verif)
    sm = next(f for f in dossie.fatos if f.source_url == DEC)
    assert sm.status == "unavailable"                            # nem verified, nem falso
    cob = _renda(state, dossie).cobertura
    req = next(r for r in cob.requisitos if r.requisito_id == "salario_minimo.vigente")
    assert req.estado == "unavailable" and not req.central
    assert cob.ready_to_write and cob.estado == "degraded"       # detalhe sai, página segue
    assert any(d["requisito"] == "salario_minimo.vigente" and "indisponível" in d["instrucao"]
               for d in cob.degradacoes)
    assert any(d["tipo"] == "ativo" for d in cob.desativados)  # ferramenta do valor sai
    regra = next(r for r in cob.requisitos if r.requisito_id == RENDA)
    assert regra.estado == "verified"                            # a regra continua


def test_fonte_oficial_alternativa_destrava_o_requisito():
    alternativa = "https://www.in.gov.br/web/dou/-/decreto-n-12.797"
    DOCS[alternativa] = DECRETO
    try:
        verif = _Bloqueado(vivas=[u for u in CITADAS + list(DOCS) if u != DEC], bloqueadas=[DEC])
        state, dossie = _dossie([HINT_REGRA, HINT_SM, dict(HINT_SM, url=alternativa)],
                                verificador=verif)
    finally:
        DOCS.pop(alternativa)
    cob = _renda(state, dossie).cobertura
    req = next(r for r in cob.requisitos if r.requisito_id == "salario_minimo.vigente")
    assert req.estado == "verified" and cob.estado == "ready"
    derivado = next(f for f in dossie.fatos if f.origem == "derivado")
    assert alternativa in derivado.derivacao["fontes_das_premissas"]


# --- derivados ----------------------------------------------------------------

def test_derivacao_2_x_1621_e_3242_com_linhagem():
    state, dossie = _dossie([HINT_REGRA, HINT_SM])
    renda = _renda(state, dossie)
    assert renda.cobertura.estado == "ready", (renda.cobertura.degradacoes,
                                               renda.cobertura.desativados)
    derivado = next(f for f in dossie.fatos if f.origem == "derivado")
    d = derivado.derivacao
    assert (derivado.valor, derivado.unidade, d["formula"]) == ("3.242,00", "R$", "2 × 1621")
    assert d["metodo"] == "deterministic_multiplication" and d["jurisdicao"] == "BR"
    premissas = {f.fact_id: f for f in dossie.fatos if f.fact_id in d["premissas"]}
    assert {f.source_url for f in premissas.values()} == {DN, DEC}
    assert derivado.vigente_desde == date(2026, 1, 1) and derivado.source_url == ""
    assert "não é valor publicado literalmente" in derivado.afirmacao
    req = next(r for r in renda.cobertura.requisitos if r.requisito_id == "renda.valor_vigente")
    assert req.estado == "derived"
    valor = next(v for v in renda.cobertura.vinculos if v["papel"] == "valor_vigente")
    assert valor["fact_id"] == derivado.fact_id and valor["formula"] == "2 × 1621"
    from funnelforge.pipeline.dossie import projecao_para_o_prompt
    proj = projecao_para_o_prompt(dossie.model_dump(mode="json"), renda.page_number)
    item = next(f for f in proj["fatos"] if f["id"] == derivado.fact_id)
    assert item["derivacao"] == "2 × 1621" and set(item["premissas"]) == set(d["premissas"])


def test_mudanca_de_vigencia_ou_de_premissa_invalida_o_derivado():
    _, base = _dossie([HINT_REGRA, HINT_SM])
    original = next(f for f in base.fatos if f.origem == "derivado")
    DOCS[DEC + "?v=2027"] = DECRETO.replace("2026", "2027")
    try:
        futuro = dict(HINT_SM, url=DEC + "?v=2027", vigente_desde="2027-01-01",
                      afirmacao="A partir de 1º de janeiro de 2027 o salário mínimo será de "
                                "R$ 1.621,00")
        state, dossie = _dossie([HINT_REGRA, futuro], vivas=CITADAS + list(DOCS))
    finally:
        DOCS.pop(DEC + "?v=2027")
    assert not [f for f in dossie.fatos if f.origem == "derivado"]
    assert any("premissa ainda não vigente" in d["instrucao"]
               for d in _renda(state, dossie).cobertura.degradacoes)
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
    assert any("premissa 'salario_minimo.vigente' (r$) sem fato verificado" in d["instrucao"]
               for d in _renda(state, dossie).cobertura.degradacoes)


def test_jurisdicao_divergente_recusa_o_derivado():
    hint_ma = dict(HINT_REGRA, **REGIONAL_MA, url=MA,
                   afirmacao="renda familiar per capita de até dois salários mínimos federais")
    state, dossie = _dossie([hint_ma, HINT_SM])
    assert any("jurisdição divergente" in d["instrucao"]
               for d in _renda(state, dossie).cobertura.degradacoes)


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
    _, dossie = _dossie([], fatos=SEM_RENDA + [bruto])
    assert not [f for f in dossie.fatos if f.origem == "derivado"]
