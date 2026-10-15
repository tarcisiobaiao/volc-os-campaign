"""`ValorMonetario`: só operador e medido_na_conta viram verba ou lance.

A prova que importa é a negativa: um CPC de SERP ou de ferramenta externa NÃO
monta requisição — nem a de `validate_only`. O cliente aqui é de mentira e
conta as chamadas; nenhuma rede, nenhuma trava aberta (`FORGE_PERMITIR_ESCRITA`
nunca é definida neste arquivo).
"""
from __future__ import annotations

import pytest
from google.ads.googleads.client import GoogleAdsClient

from volc_ads.gestao import acoes as A
from volc_ads.gestao import lote
from volc_ads.gestao.acoes import AcaoRecusada
from volc_ads.gestao.valor import (CAMPOS_MEDIDOS, ORIGENS, ORIGENS_QUE_AUTORIZAM,
                                   ValorMonetario, ValorSemAutoridade, medido_na_conta,
                                   operador)

CID = "5478096539"
CAMP = 24278665189
BUDGET = 15886629542


def _get_type():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    return c.get_type


GT = _get_type()

GAQL_ORCAMENTO = ("SELECT campaign.id, campaign_budget.amount_micros FROM campaign "
                  f"WHERE campaign.id = {CAMP}")
GAQL_CPC = ("SELECT campaign.id, metrics.average_cpc FROM campaign "
            "WHERE segments.date DURING LAST_30_DAYS")
NAO_AUTORIZAM = sorted(ORIGENS - ORIGENS_QUE_AUTORIZAM)


def _valor(origem: str, micros: int = 2_500_000) -> ValorMonetario:
    evidencia = {"operador": "operador:tarcisio@2026-10-15T12:00:00+00:00",
                 "medido_na_conta": GAQL_CPC}.get(origem, f"{origem}: CPC sugerido R$ 2,50")
    return ValorMonetario(micros, origem, evidencia)


#: Toda ação que põe dinheiro na conta, montada com um valor de certa origem.
FABRICAS = {
    "orcamento": lambda v: A.AlterarOrcamento(CAMP, BUDGET, v),
    "alvo_tcpa": lambda v: A.AlterarAlvoDeLance(CAMP, "MAXIMIZE_CONVERSIONS", "tcpa", v),
    "alvo_teto_cpc": lambda v: A.AlterarAlvoDeLance(CAMP, "TARGET_SPEND", "teto_cpc", v),
    "troca_tcpa": lambda v: A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS", tcpa=v),
    "troca_teto_cpc": lambda v: A.TrocarEstrategia(CAMP, "TARGET_SPEND", teto_cpc=v),
}


class _Servico:
    def __init__(self):
        self.pedidos = []

    def mutate(self, request):  # pragma: no cover - não pode ser chamado
        self.pedidos.append(request)
        raise AssertionError("uma requisição saiu com valor sem autoridade")


class _Cliente:
    def __init__(self, servico):
        self.servico = servico
        self.get_type = GT

    def get_service(self, nome):
        return self.servico


# ── o valor em si ───────────────────────────────────────────────────────────


def teste_serp_e_ferramenta_externa_estao_entre_as_origens_que_nao_autorizam():
    assert {"serp", "ferramenta_externa", "keyword_planner", "dataforseo",
            "estimativa_modelo", "nao_informada"} <= set(NAO_AUTORIZAM)
    assert ORIGENS_QUE_AUTORIZAM == {"operador", "medido_na_conta"}


@pytest.mark.parametrize("origem", NAO_AUTORIZAM)
def teste_origem_que_nao_autoriza_levanta_em_autoriza(origem):
    with pytest.raises(ValorSemAutoridade, match="anotação"):
        _valor(origem).autoriza()


@pytest.mark.parametrize("origem", sorted(ORIGENS_QUE_AUTORIZAM))
def teste_operador_e_medido_na_conta_autorizam(origem):
    assert _valor(origem).autoriza() == 2_500_000


def teste_ausencia_nao_e_zero_nem_verba():
    with pytest.raises(ValorSemAutoridade, match="ausente"):
        ValorMonetario(None, "operador", "operador:x@2026-10-15").autoriza()


@pytest.mark.parametrize("evidencia", ["", "tarcisio", "operador:", "operador:sem-quando"])
def teste_operador_exige_quem_e_quando(evidencia):
    with pytest.raises(AcaoRecusada):
        ValorMonetario(1_000_000, "operador", evidencia).autoriza()


@pytest.mark.parametrize("evidencia", [
    "li na conta",                                       # frase, não consulta
    "SELECT campaign.id FROM campaign",                  # consulta sem campo de dinheiro
    "metrics.average_cpc segundo a planilha",            # campo sem consulta
])
def teste_medido_na_conta_exige_a_gaql_com_campo_de_dinheiro(evidencia):
    with pytest.raises(ValorSemAutoridade, match="GAQL"):
        ValorMonetario(1_000_000, "medido_na_conta", evidencia).autoriza()


@pytest.mark.parametrize("campo", CAMPOS_MEDIDOS)
def teste_toda_gaql_com_campo_medido_autoriza(campo):
    assert medido_na_conta(10_000, f"SELECT {campo} FROM campaign").autoriza() == 10_000


def teste_origem_desconhecida_e_recusada_na_construcao():
    with pytest.raises(AcaoRecusada, match="desconhecida"):
        ValorMonetario(1_000_000, "chute", "x")


# ── as ações: número cru não entra, origem errada não monta requisição ──────


@pytest.mark.parametrize("nome", sorted(FABRICAS))
def teste_numero_cru_sem_origem_e_recusado_na_construcao(nome):
    with pytest.raises(AcaoRecusada, match="sem origem"):
        FABRICAS[nome](2_500_000)


@pytest.mark.parametrize("origem", ["serp", "ferramenta_externa"])
@pytest.mark.parametrize("nome", sorted(FABRICAS))
def teste_serp_e_ferramenta_externa_nao_montam_operacao(nome, origem):
    acao = FABRICAS[nome](_valor(origem))  # o valor pode existir como anotação…
    with pytest.raises(ValorSemAutoridade):  # …mas não vira MutateOperation
        lote.montar([acao], GT, CID)


@pytest.mark.parametrize("origem", ["serp", "ferramenta_externa"])
@pytest.mark.parametrize("nome", sorted(FABRICAS))
def teste_serp_e_ferramenta_externa_sao_recusadas_inclusive_em_validate_only(nome, origem):
    serv = _Servico()
    with pytest.raises(ValorSemAutoridade):
        lote.validar(CID, [FABRICAS[nome](_valor(origem))], login_customer_id="1",
                     cliente=_Cliente(serv))
    assert serv.pedidos == []  # nenhuma requisição saiu, nem a de ensaio


@pytest.mark.parametrize("origem", ["serp", "ferramenta_externa"])
def teste_aplicar_recusa_antes_do_ensaio_e_da_trava(monkeypatch, origem):
    monkeypatch.delenv("FORGE_PERMITIR_ESCRITA", raising=False)
    serv = _Servico()
    with pytest.raises(ValorSemAutoridade):
        lote.aplicar(CID, [FABRICAS["orcamento"](_valor(origem))], login_customer_id="1",
                     motivo="prova W5", cliente=_Cliente(serv))
    assert serv.pedidos == []


def teste_um_valor_ruim_derruba_o_lote_inteiro_antes_da_requisicao():
    """Não há 'partial' para verba sem autoridade: o lote não é montado."""
    serv = _Servico()
    acoes = [A.AlterarStatus("campanha", CAMP, "PAUSED"),
             FABRICAS["orcamento"](_valor("serp"))]
    with pytest.raises(ValorSemAutoridade):
        lote.validar(CID, acoes, login_customer_id="1", cliente=_Cliente(serv))
    assert serv.pedidos == []


_CAMPO_NO_PROTO = {
    "orcamento": lambda op: op.campaign_budget_operation.update.amount_micros,
    "alvo_tcpa": lambda op: op.campaign_operation.update.maximize_conversions.target_cpa_micros,
    "alvo_teto_cpc": lambda op: op.campaign_operation.update.target_spend.cpc_bid_ceiling_micros,
    "troca_tcpa": lambda op: op.campaign_operation.update.maximize_conversions.target_cpa_micros,
    "troca_teto_cpc": lambda op: op.campaign_operation.update.target_spend.cpc_bid_ceiling_micros,
}


@pytest.mark.parametrize("origem", sorted(ORIGENS_QUE_AUTORIZAM))
@pytest.mark.parametrize("nome", sorted(FABRICAS))
def teste_operador_e_medido_na_conta_montam_a_operacao(nome, origem):
    plano = lote.montar([FABRICAS[nome](_valor(origem))], GT, CID)
    (op,) = plano.operacoes
    type(op).serialize(op)
    assert _CAMPO_NO_PROTO[nome](op) == 2_500_000


def teste_zero_em_troca_de_estrategia_e_sem_alvo_e_nao_numero():
    """0 cru na troca = estratégia sem alvo (o default de sempre), não verba."""
    a = A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS", tcpa=0)
    assert a.tcpa is None and a.tcpa_micros == 0
    lote.montar([a], GT, CID)


def teste_reverso_usa_o_valor_lido_na_conta_como_medido_na_conta():
    a = A.AlterarOrcamento(CAMP, BUDGET, operador(35_000_000, "tarcisio", "2026-10-15"))
    (rev,) = a.reverso({"verba_diaria_micros": 30_000_000})
    assert rev.verba.origem == "medido_na_conta" and rev.verba.autoriza() == 30_000_000
    (op,) = lote.montar([rev], GT, CID).operacoes
    assert op.campaign_budget_operation.update.amount_micros == 30_000_000


def teste_origem_vai_para_o_valor_proposto():
    a = A.AlterarOrcamento(CAMP, BUDGET, _valor("operador"))
    assert a.valor_proposto()["origem_valor"] == {
        "origem": "operador", "evidencia": "operador:tarcisio@2026-10-15T12:00:00+00:00"}
