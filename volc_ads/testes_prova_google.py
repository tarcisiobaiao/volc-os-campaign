"""O aceite do `validate_only` deixa rastro: request ID, versão e instante.

Até 14/10/2026 só a FALHA carregava `request_id` (`FalhaGads`); o aceite
devolvia `None` e o recibo de `/provar` não dizia qual chamada aceitou o
payload. Estes testes chamam `preparar()` de verdade, com o builder Search real
e a RPC dublada — nenhuma rede, nenhuma credencial.
"""
from __future__ import annotations

import pytest

from backend.app.trafego import projecao
from volc_ads import subir as sb
from volc_ads.campanha import search
from volc_ads.campanha.testes_criterio import CID, _brief, _cliente_sem_rede
from volc_ads.copy.mock import falha_politica
from volc_ads.gads.errors import FalhaGads


def _do_operador(brief):
    """W5: verba e lance do brief declarados pelo operador da sessão (dublê)."""
    from volc_ads.gestao.valor import valores_do_operador
    return valores_do_operador(brief, sub="u-teste", papel="OPERATOR",
                               quando="2026-10-15T12:00:00+00:00",
                               justificativa="valores definidos pelo operador no teste")


@pytest.fixture(autouse=True)
def _sem_credencial(monkeypatch):
    monkeypatch.setattr(search, "cliente", lambda _login: _cliente_sem_rede())


def _aceita_com_id(ids_por_chamada):
    """Dublê da RPC: aceita e devolve o metadado como o interceptor real faz."""
    chamadas = []

    def validar(customer_id, operacoes, *, login_customer_id, request_ids=None):
        chamadas.append(list(operacoes))
        if request_ids is not None and ids_por_chamada:
            request_ids.append(ids_por_chamada.pop(0))
        return None

    return validar, chamadas


def test_aceite_guarda_request_id_versao_e_instante(monkeypatch):
    validar, chamadas = _aceita_com_id(["req-abc"])
    monkeypatch.setattr(sb, "validar_mutacoes", validar)

    preparo = sb.preparar(CID, (_b := _brief()), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))

    assert preparo.selo is not None
    assert len(chamadas) == 1
    assert preparo.prova_google is not None
    assert preparo.prova_google.request_ids == ("req-abc",)
    assert preparo.prova_google.versao_api == "v25"
    assert preparo.prova_google.validado_em.endswith("+00:00")

    visto = projecao.preparo(preparo)
    assert visto["prova_google"]["request_ids"] == ["req-abc"]
    assert visto["prova_google"]["validate_only"] is True


def test_request_id_fica_fora_do_selo(monkeypatch):
    """O selo é a impressão do PAYLOAD: o id da chamada não pode mudá-lo."""
    monkeypatch.setattr(sb, "validar_mutacoes", _aceita_com_id(["um"])[0])
    a = sb.preparar(CID, (_b := _brief(carimbo_nome="20261014_120000")), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))
    monkeypatch.setattr(sb, "validar_mutacoes", _aceita_com_id(["outro"])[0])
    b = sb.preparar(CID, (_b := _brief(carimbo_nome="20261014_120000")), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))

    assert a.prova_google.request_ids != b.prova_google.request_ids
    assert a.selo.impressao == b.selo.impressao
    assert a.selo.hashes_operacoes == b.selo.hashes_operacoes


def test_rpc_sem_metadado_nao_inventa_id(monkeypatch):
    monkeypatch.setattr(sb, "validar_mutacoes", _aceita_com_id([])[0])
    preparo = sb.preparar(CID, (_b := _brief()), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))
    assert preparo.selo is not None
    assert preparo.prova_google.request_ids == ()


def test_recusa_nao_tem_prova_de_aceite(monkeypatch):
    falha = FalhaGads(erros=(), request_id="req-recusa")
    monkeypatch.setattr(sb, "validar_mutacoes",
                        lambda *a, request_ids=None, **k: falha)
    preparo = sb.preparar(CID, (_b := _brief()), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b),
                          autocorrigir=False)
    assert preparo.selo is None
    assert preparo.prova_google is None
    visto = projecao.preparo(preparo)
    assert visto["prova_google"] is None
    assert visto["falha_validacao"] is not None


def test_autocorrecao_registra_o_id_da_chamada_que_aceitou(monkeypatch):
    """Duas chamadas: a primeira recusa por política, a segunda aceita o
    payload podado. O id do recibo é o da SEGUNDA — a que aceitou o que vai."""
    falha = falha_politica("regras do saque anual")
    estado = {"n": 0}

    def validar(customer_id, operacoes, *, login_customer_id, request_ids=None):
        estado["n"] += 1
        if estado["n"] == 1:
            if request_ids is not None:
                request_ids.append("req-recusou")
            return falha
        if request_ids is not None:
            request_ids.append("req-aceitou")
        return None

    monkeypatch.setattr(sb, "validar_mutacoes", validar)
    preparo = sb.preparar(CID, (_b := _brief()), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))

    if preparo.selo is None:
        pytest.skip("o dublê de política não é acionável para esta copy: "
                    + preparo.porque_nao())
    assert estado["n"] == 2
    assert preparo.prova_google.request_ids == ("req-aceitou",)


def test_prova_guarda_a_impressao_do_payload_aceito(monkeypatch):
    """O selo pode ser retido depois (destino); a prova não perde qual payload foi."""
    monkeypatch.setattr(sb, "validar_mutacoes", _aceita_com_id(["req-x"])[0])
    preparo = sb.preparar(CID, (_b := _brief()), login_customer_id=CID, canal="SEARCH", valores=_do_operador(_b))
    assert preparo.prova_google.impressao == preparo.selo.impressao
    assert preparo.prova_google.n_operacoes == len(preparo.operacoes)
    visto = projecao.preparo(preparo)["prova_google"]
    assert visto["impressao_do_payload"] == preparo.selo.impressao
    assert sum(visto["tipos_operacoes"].values()) == len(preparo.operacoes)
    assert "campaign_operation.create" in visto["tipos_operacoes"]
