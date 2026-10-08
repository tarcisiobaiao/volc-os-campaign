"""Lote com partial failure: plano, mapeamento de falha pelo índice e trava.

O `partial_failure_error` aqui é montado como a API o manda: `google.rpc.Status`
com um `GoogleAdsFailure` REAL da v25 serializado em `details` (Any), cada erro
com `location.field_path_elements[0] = mutate_operations[i]`. O mapeamento
índice → ação foi também provado ao vivo em 08/10/2026 (validate_only na
Crédito Up: operações 1 e 3 de 5 recusadas, cada uma na ação certa).
"""
from __future__ import annotations

import pytest
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.errors.types.criterion_error import CriterionErrorEnum
from google.ads.googleads.v25.errors.types.errors import ErrorLocation, GoogleAdsError, GoogleAdsFailure
from google.ads.googleads.v25.errors.types.mutate_error import MutateErrorEnum
from google.ads.googleads.v25.errors.types.authorization_error import AuthorizationErrorEnum
from google.protobuf import any_pb2

from volc_ads.gads import modo
from volc_ads.gestao import acoes as A
from volc_ads.gestao import lote
from volc_ads.gestao.lote import LoteRecusado

CID = "5478096539"
CAMP = 24278665189
REC = f"customers/{CID}/recommendations/abc123"


def _cliente_proto():
    c = GoogleAdsClient.__new__(GoogleAdsClient)
    c.version = "v25"
    c.use_proto_plus = True
    return c


GT = _cliente_proto().get_type


def _erro(indice: int | None, *, campo="operations", tipo="mutate", nome="RESOURCE_NOT_FOUND"):
    e = GoogleAdsError(message=f"erro na {indice}")
    if tipo == "mutate":
        e.error_code.mutate_error = getattr(MutateErrorEnum.MutateError, nome)
    elif tipo == "criterio":
        e.error_code.criterion_error = getattr(CriterionErrorEnum.CriterionError, nome)
    else:
        e.error_code.authorization_error = getattr(AuthorizationErrorEnum.AuthorizationError, nome)
    if indice is not None:
        e.location.field_path_elements.append(
            ErrorLocation.FieldPathElement(field_name=f"mutate_{campo}" if campo == "operations"
                                           else campo, index=indice))
        e.location.field_path_elements.append(ErrorLocation.FieldPathElement(field_name="create"))
    return e


def _resposta(erros=(), sucessos: dict[int, str] | None = None, n_ops: int = 0):
    resp = GT("MutateGoogleAdsResponse")
    if erros:
        falha = GoogleAdsFailure(errors=list(erros))
        detalhe = any_pb2.Any(
            type_url="type.googleapis.com/google.ads.googleads.v25.errors.GoogleAdsFailure",
            value=GoogleAdsFailure.serialize(falha))
        resp._pb.partial_failure_error.code = 3
        resp._pb.partial_failure_error.message = "partial"
        resp._pb.partial_failure_error.details.append(detalhe)
    for i in range(n_ops):
        r = GT("MutateOperationResponse")
        if sucessos and i in sucessos:
            r.campaign_criterion_result.resource_name = sucessos[i]
        resp.mutate_operation_responses.append(r)
    return resp


class _Servico:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def mutate(self, request):
        self.pedidos.append(request)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    apply_recommendation = mutate
    dismiss_recommendation = mutate


class _Cliente:
    def __init__(self, servico):
        self.servico = servico
        self.get_type = GT

    def get_service(self, nome):
        return self.servico


def _neg(*textos):
    return A.AdicionarNegativas("campanha", CAMP, tuple(A.Termo(t) for t in textos))


# ── plano ───────────────────────────────────────────────────────────────────


def teste_plano_guarda_a_faixa_de_cada_acao_e_ids_temporarios_do_lote():
    acoes = [A.AlterarStatus("campanha", CAMP, "PAUSED"), _neg("a", "b"),
             A.CriarListaCompartilhada("NEGATIVE_KEYWORDS", "L1", (A.Termo("x"),), (CAMP,)),
             A.CriarListaCompartilhada("NEGATIVE_KEYWORDS", "L2", (A.Termo("y"),))]
    p = lote.montar(acoes, GT, CID)
    assert p.faixas == ((0, 1), (1, 3), (3, 6), (6, 8))
    assert [p.acao_da_operacao(i) for i in (0, 2, 5, 7, 8)] == [0, 1, 2, 3, None]
    assert p.operacoes[3].shared_set_operation.create.resource_name.endswith("/-1")
    assert p.operacoes[6].shared_set_operation.create.resource_name.endswith("/-2")


def teste_status_e_lance_na_mesma_campanha_cabem_no_lote():
    """Campos diferentes do mesmo recurso: aceito ao vivo em 08/10/2026."""
    lote.montar([A.AlterarStatus("campanha", CAMP, "PAUSED"),
                 A.AlterarAlvoDeLance(CAMP, "TARGET_SPEND", "teto_cpc", 1_500_000)], GT, CID)


def teste_duas_acoes_no_mesmo_campo_sao_recusadas():
    with pytest.raises(LoteRecusado, match="campaign_bidding_strategy"):
        lote.montar([A.AlterarAlvoDeLance(CAMP, "TARGET_SPEND", "teto_cpc", 1_500_000),
                     A.TrocarEstrategia(CAMP, "MAXIMIZE_CONVERSIONS")], GT, CID)
    with pytest.raises(LoteRecusado, match="~11"):
        lote.montar([A.AjustarHorario(CAMP, 11, 1.2),
                     A.ProgramarAnuncios(CAMP, remover=(11,))], GT, CID)


def teste_recomendacao_nao_entra_no_mutate():
    with pytest.raises(LoteRecusado, match="aplicar_recomendacoes"):
        lote.montar([A.AplicarRecomendacao(REC)], GT, CID)
    with pytest.raises(LoteRecusado, match="vazio"):
        lote.montar([], GT, CID)


# ── leitura do partial failure ──────────────────────────────────────────────


def teste_falhas_parciais_le_o_googleadsfailure_com_o_indice():
    erros = lote.falhas_parciais(_resposta([_erro(1), _erro(3, tipo="criterio",
                                                            nome="KEYWORD_HAS_INVALID_CHARS")]))
    assert [(e.indice_operacao, e.valor_codigo) for e in erros] == [
        (1, "RESOURCE_NOT_FOUND"), (3, "KEYWORD_HAS_INVALID_CHARS")]
    assert erros[0].caminho_campo == "mutate_operations[1].create"
    assert lote.falhas_parciais(_resposta()) == ()


def teste_mapear_distribui_ok_parcial_e_falhou_com_os_criados():
    acoes = [A.AlterarStatus("campanha", CAMP, "PAUSED"), _neg("a", "b", "c"),
             A.AlterarStatus("grupo", 1, "PAUSED")]
    p = lote.montar(acoes, GT, CID)
    rn = f"customers/{CID}/campaignCriteria/{CAMP}~"
    resp = _resposta([_erro(2, tipo="criterio", nome="KEYWORD_HAS_INVALID_CHARS"), _erro(4)],
                     sucessos={1: rn + "1", 3: rn + "3"}, n_ops=5)
    r = lote.mapear(p, validate_only=False, resposta=resp)
    assert [x.desfecho for x in r.acoes] == ["ok", "parcial", "falhou"]
    assert r.acoes[1].recursos == (rn + "1", rn + "3")  # a do meio falhou: não entra
    assert [e.indice_operacao for e in r.acoes[1].erros] == [2]
    assert not r.tudo_ok and len(r.por_desfecho("parcial")) == 1


def teste_lista_cuja_criacao_falha_arrasta_itens_e_sai_falhou_e_nao_parcial():
    """Medido ao vivo: DUPLICATE_NAME no SharedSet → itens e vínculo com
    RESOURCE_NOT_FOUND no id temporário. Nada órfão, ação inteira `falhou`."""
    acao = A.CriarListaCompartilhada("NEGATIVE_KEYWORDS", "L", (A.Termo("x"),), (CAMP,))
    p = lote.montar([acao], GT, CID)
    r = lote.mapear(p, validate_only=True, resposta=_resposta([_erro(0), _erro(1), _erro(2)]))
    assert r.acoes[0].desfecho == "falhou"


def teste_erro_sem_indice_derruba_todas():
    p = lote.montar([_neg("a"), A.AlterarStatus("campanha", CAMP, "PAUSED")], GT, CID)
    r = lote.mapear(p, validate_only=True, resposta=_resposta([_erro(None)]))
    assert [x.desfecho for x in r.acoes] == ["falhou", "falhou"]
    assert len(r.erros_gerais) == 1


# ── envio ───────────────────────────────────────────────────────────────────


def teste_validar_pede_partial_failure_e_validate_only_sem_trava():
    serv = _Servico([_resposta([_erro(1)], n_ops=0)])
    acoes = [A.AlterarStatus("campanha", CAMP, "PAUSED"), A.AlterarStatus("grupo", 1, "PAUSED")]
    r = lote.validar(CID, acoes, login_customer_id="1", cliente=_Cliente(serv))
    (req,) = serv.pedidos
    assert (req.partial_failure, req.validate_only, req.customer_id) == (True, True, CID)
    assert len(req.mutate_operations) == 2
    assert [x.desfecho for x in r.acoes] == ["ok", "falhou"]


def teste_validar_marca_recomendacao_como_nao_validavel_e_mantem_a_ordem():
    serv = _Servico([_resposta()])
    acoes = [A.AplicarRecomendacao(REC), A.AlterarStatus("campanha", CAMP, "PAUSED"),
             A.DispensarRecomendacao(REC)]
    r = lote.validar(CID, acoes, login_customer_id="1", cliente=_Cliente(serv))
    assert [x.desfecho for x in r.acoes] == ["nao_validavel", "ok", "nao_validavel"]
    assert [x.acao for x in r.acoes] == acoes
    assert len(serv.pedidos[0].mutate_operations) == 1


def teste_validar_so_recomendacao_nao_chama_a_api():
    serv = _Servico([])
    r = lote.validar(CID, [A.AplicarRecomendacao(REC)], login_customer_id="1",
                     cliente=_Cliente(serv))
    assert serv.pedidos == [] and r.acoes[0].desfecho == "nao_validavel"


def teste_excecao_terminal_com_indice_e_mapeada_sem_retry():
    falha = GoogleAdsFailure(errors=[_erro(0, tipo="auth", nome="USER_PERMISSION_DENIED")])
    serv = _Servico([GoogleAdsException(None, None, falha, "req-9")])
    r = lote.validar(CID, [_neg("a"), A.AlterarStatus("campanha", CAMP, "PAUSED")],
                     login_customer_id="1", cliente=_Cliente(serv))
    assert len(serv.pedidos) == 1
    assert [x.desfecho for x in r.acoes] == ["falhou", "ok"]
    assert r.request_id == "req-9"


def teste_escrita_real_e_bloqueada_antes_de_montar_a_requisicao(monkeypatch):
    monkeypatch.delenv("FORGE_PERMITIR_ESCRITA", raising=False)
    serv = _Servico([])
    p = lote.montar([_neg("a")], GT, CID)
    with pytest.raises(modo.EscritaBloqueada):
        lote.enviar(p, login_customer_id="1", validate_only=False, cliente=_Cliente(serv))
    assert serv.pedidos == []


def teste_aplicar_sem_variavel_de_ambiente_ensaia_mas_nao_escreve(monkeypatch):
    monkeypatch.delenv("FORGE_PERMITIR_ESCRITA", raising=False)
    serv = _Servico([_resposta()])
    with pytest.raises(modo.EscritaBloqueada):
        lote.aplicar(CID, [_neg("a")], login_customer_id="1", motivo="teste da trava de escrita",
                     cliente=_Cliente(serv))
    assert len(serv.pedidos) == 1 and serv.pedidos[0].validate_only is True


def teste_aplicar_so_manda_o_que_o_ensaio_aceitou_inteiro(monkeypatch):
    monkeypatch.setenv("FORGE_PERMITIR_ESCRITA", "1")
    acoes = [A.AlterarStatus("campanha", CAMP, "PAUSED"), _neg("a", "b"),
             A.AlterarStatus("grupo", 1, "PAUSED")]
    ensaio = _resposta([_erro(2, tipo="criterio", nome="KEYWORD_HAS_INVALID_CHARS"), _erro(3)])
    real = _resposta(n_ops=1)
    serv = _Servico([ensaio, real])
    e, r = lote.aplicar(CID, acoes, login_customer_id="1", motivo="teste do envio parcial",
                        cliente=_Cliente(serv))
    assert [x.desfecho for x in e.acoes] == ["ok", "parcial", "falhou"]
    assert serv.pedidos[1].validate_only is False and serv.pedidos[1].partial_failure is True
    assert len(serv.pedidos[1].mutate_operations) == 1
    assert [x.acao for x in r.acoes] == [acoes[0]]
    assert not modo.escrita_permitida()  # a trava fecha de novo ao sair


def teste_aplicar_recusa_recomendacao():
    with pytest.raises(LoteRecusado):
        lote.aplicar(CID, [A.AplicarRecomendacao(REC)], login_customer_id="1", motivo="x" * 12,
                     cliente=_Cliente(_Servico([])))


# ── recomendações ───────────────────────────────────────────────────────────


def teste_pedidos_de_recomendacao_separam_aplicar_e_dispensar():
    rec2 = REC + "2"
    p = lote.montar_pedidos_de_recomendacao(
        [A.AplicarRecomendacao(REC), A.DispensarRecomendacao(rec2), A.AplicarRecomendacao(rec2)],
        GT, CID)
    req, plano = p["aplicar"]
    assert type(req).__name__ == "ApplyRecommendationRequest" and req.partial_failure
    assert [o.resource_name for o in req.operations] == [REC, rec2]
    assert plano.faixas == ((0, 1), (1, 2))
    req, _ = p["dispensar"]
    assert [o.resource_name for o in req.operations] == [rec2]


def teste_mapear_recomendacoes_pelo_indice_de_operations():
    p = lote.montar_pedidos_de_recomendacao(
        [A.AplicarRecomendacao(REC), A.AplicarRecomendacao(REC + "2")], GT, CID)["aplicar"][1]
    resp = GT("ApplyRecommendationResponse")
    resp.results.append(type(resp).meta.fields["results"].message(resource_name=REC))
    resp.results.append(type(resp).meta.fields["results"].message())
    falha = GoogleAdsFailure(errors=[_erro(1, campo="operations_raw")])
    falha.errors[0].location.field_path_elements[0].field_name = "operations"
    resp._pb.partial_failure_error.details.append(any_pb2.Any(
        type_url="type.googleapis.com/google.ads.googleads.v25.errors.GoogleAdsFailure",
        value=GoogleAdsFailure.serialize(falha)))
    r = lote.mapear_recomendacoes(p, resposta=resp)
    assert [x.desfecho for x in r.acoes] == ["ok", "falhou"]
    assert r.acoes[0].recursos == (REC,)


def teste_aplicar_recomendacao_exige_a_trava(monkeypatch):
    monkeypatch.delenv("FORGE_PERMITIR_ESCRITA", raising=False)
    serv = _Servico([])
    with pytest.raises(modo.EscritaBloqueada):
        lote.aplicar_recomendacoes(CID, [A.AplicarRecomendacao(REC)], login_customer_id="1",
                                   motivo="teste da trava de recomendação", cliente=_Cliente(serv))
    assert serv.pedidos == []
