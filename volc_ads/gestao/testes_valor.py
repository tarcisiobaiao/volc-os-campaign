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
from volc_ads.gestao.valor import (ORIGENS, ORIGENS_QUE_AUTORIZAM, ValorMonetario,
                                   ValorSemAutoridade, medido_na_conta, operador,
                                   sha256_canonico)

CID = "5478096539"
CAMP = 24278665189
BUDGET = 15886629542


def _get_type():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    return c.get_type


GT = _get_type()

NAO_AUTORIZAM = sorted(ORIGENS - ORIGENS_QUE_AUTORIZAM)
EV_OPERADOR = "operador:9f1c-sub/operador@2026-10-15T12:00:00+00:00"
JUST = "verba limita a entrega no fim do dia"
AS_OF = "2026-10-15T11:00:00+00:00"
#: O campo que mede cada alvo (o "antes" guardado tem de ter este campo).
CAMPO = {"orcamento": "verba_diaria_micros", "alvo_tcpa": "tcpa_micros",
         "alvo_teto_cpc": "teto_cpc_micros", "troca_tcpa": "tcpa_micros",
         "troca_teto_cpc": "teto_cpc_micros"}


def _medido(campo: str, micros: int = 2_500_000) -> ValorMonetario:
    return medido_na_conta(micros, fonte="trafego_proposta.valor_atual", ref="prop-1",
                           campo=campo, as_of=AS_OF, registro={campo: micros, "existe": True})


def _valor(origem: str, micros: int = 2_500_000, campo: str = "verba_diaria_micros"
           ) -> ValorMonetario:
    if origem == "operador":
        return ValorMonetario(micros, origem, EV_OPERADOR, JUST)
    if origem == "medido_na_conta":
        return _medido(campo, micros)
    return ValorMonetario(micros, origem, f"{origem}: CPC sugerido R$ 2,50")


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
        ValorMonetario(None, "operador", EV_OPERADOR, JUST).autoriza()


def teste_negativo_nao_e_verba():
    with pytest.raises(AcaoRecusada, match="negativo"):
        ValorMonetario(-5_000_000, "operador", EV_OPERADOR, JUST)


@pytest.mark.parametrize("evidencia", ["", "tarcisio", "operador:", "operador:sem-quando",
                                       "operador:agente@volc@2026-10-15"])  # formato antigo
def teste_operador_exige_a_evidencia_carimbada_pelo_servidor(evidencia):
    with pytest.raises(AcaoRecusada):
        ValorMonetario(1_000_000, "operador", evidencia, JUST).autoriza()


@pytest.mark.parametrize("justificativa", ["", "ok", "         "])
def teste_operador_exige_justificativa(justificativa):
    with pytest.raises(ValorSemAutoridade, match="justificativa"):
        ValorMonetario(1_000_000, "operador", EV_OPERADOR, justificativa).autoriza()


def teste_operador_do_servidor_autoriza():
    v = operador(1_000_000, "9f1c-sub", "operador", "2026-10-15T12:00:00+00:00", JUST)
    assert v.autoriza() == 1_000_000 and v.json()["justificativa"] == JUST


@pytest.mark.parametrize("evidencia", [
    "SELECT metrics.average_cpc FROM keyword_view -- semrush",   # o caso da revisão R-W5
    "SELECT campaign_budget.amount_micros FROM campaign",        # GAQL nunca executada
    "li na conta",
    "medicao:planilha/1#verba_diaria_micros@2026-10-15 sha256=" + "0" * 64,  # fonte estranha
    "medicao:trafego_proposta.valor_atual/1#verba_diaria_micros@x sha256=abc",  # hash curto
])
def teste_medido_na_conta_texto_livre_nao_e_medicao(evidencia):
    with pytest.raises(ValorSemAutoridade, match="leitura guardada"):
        ValorMonetario(36_000_000, "medido_na_conta", evidencia).autoriza()


def teste_semrush_nao_libera_orcamento():
    v = ValorMonetario(36_000_000, "medido_na_conta",
                       "SELECT metrics.average_cpc FROM keyword_view -- semrush")
    a = A.AlterarOrcamento(CAMP, BUDGET, v)  # existe como anotação…
    with pytest.raises(ValorSemAutoridade):   # …e não vira operação
        lote.montar([a], GT, CID)


def teste_medicao_amarrada_ao_registro_por_hash():
    registro = {"verba_diaria_micros": 30_000_000, "existe": True}
    v = medido_na_conta(30_000_000, fonte="trafego_proposta.valor_atual", ref="p1",
                        campo="verba_diaria_micros", as_of=AS_OF, registro=registro)
    assert v.medicao.sha256 == sha256_canonico(registro) and v.autoriza() == 30_000_000
    with pytest.raises(AcaoRecusada, match="não tem"):
        medido_na_conta(31_000_000, fonte="trafego_proposta.valor_atual", ref="p1",
                        campo="verba_diaria_micros", as_of=AS_OF, registro=registro)


def teste_medicao_de_outro_campo_nao_vira_orcamento_nem_tcpa():
    """CPC médio medido não é orçamento; custo medido não é tCPA."""
    with pytest.raises(ValorSemAutoridade, match="só 'verba_diaria_micros'"):
        A.AlterarOrcamento(CAMP, BUDGET, _medido("teto_cpc_micros"))
    with pytest.raises(ValorSemAutoridade, match="só 'tcpa_micros'"):
        A.AlterarAlvoDeLance(CAMP, "MAXIMIZE_CONVERSIONS", "tcpa", _medido("verba_diaria_micros"))


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
    plano = lote.montar([FABRICAS[nome](_valor(origem, campo=CAMPO[nome]))], GT, CID)
    (op,) = plano.operacoes
    type(op).serialize(op)
    assert _CAMPO_NO_PROTO[nome](op) == 2_500_000


def teste_zero_em_troca_de_estrategia_e_sem_alvo_e_nao_numero():
    """0 cru na troca = estratégia sem alvo (o default de sempre), não verba."""
    a = A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS", tcpa=0)
    assert a.tcpa is None and a.tcpa_micros == 0
    lote.montar([a], GT, CID)


def teste_reverso_usa_o_valor_lido_na_conta_como_medido_na_conta():
    a = A.AlterarOrcamento(CAMP, BUDGET, _valor("operador", 35_000_000))
    (rev,) = a.reverso({"verba_diaria_micros": 30_000_000})
    assert rev.verba.origem == "medido_na_conta" and rev.verba.autoriza() == 30_000_000
    assert rev.verba.medicao.fonte == "valor_anterior"
    (op,) = lote.montar([rev], GT, CID).operacoes
    assert op.campaign_budget_operation.update.amount_micros == 30_000_000


def teste_origem_vai_para_o_valor_proposto():
    a = A.AlterarOrcamento(CAMP, BUDGET, _valor("operador"))
    assert a.valor_proposto()["origem_valor"] == {
        "origem": "operador", "evidencia": EV_OPERADOR, "justificativa": JUST}
