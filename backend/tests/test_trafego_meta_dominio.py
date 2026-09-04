from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.trafego.meta import credenciais as cred
from app.trafego.meta import dominio as dom


AGORA = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def referencia(**mudancas):
    base = {
        "ativo_id": "asset:meta-ad-account:piloto",
        "provider": "1password",
        "nome_logico": "META_ADS_READ_TOKEN",
        "estado": "referenced",
        "verificacao_estado": "verified",
        "verificado_em": AGORA,
        "valido_ate": date(2099, 1, 1),
    }
    base.update(mudancas)
    return cred.ReferenciaDeCredencial(**base)


def test_conta_canonica_remove_act_mas_recusa_nome():
    assert dom.conta_canonica("act_123456") == "123456"
    with pytest.raises(dom.ContratoMetaInvalido):
        dom.conta_canonica("conta-piloto")


def test_identidade_e_deterministica_e_nome_nao_participa():
    primeiro = dom.id_interno(
        conta_externa="123", tipo="campaign", id_externo_meta="456")
    segundo = dom.id_interno(
        conta_externa="act_123", tipo="campaign", id_externo_meta="456")
    outro_tipo = dom.id_interno(
        conta_externa="123", tipo="adset", id_externo_meta="456")
    assert primeiro == segundo
    assert primeiro != outro_tipo


def test_prontidao_nao_colapsa_ausencia_falha_e_sucesso():
    assert cred.prontidao_da_referencia(None) == "CONFIG_MISSING"
    assert cred.prontidao_da_referencia(
        referencia(verificacao_estado="unverified", verificado_em=None)
    ) == "REFERENCE_PRESENT"
    assert cred.prontidao_da_referencia(
        referencia(verificacao_estado="partial")
    ) == "RESOLUTION_UNTESTED"
    assert cred.prontidao_da_referencia(
        referencia(verificacao_estado="failed")
    ) == "RESOLUTION_FAILED"
    assert cred.prontidao_da_referencia(referencia()) == "READY_FOR_READ"


def test_verificacao_sem_carimbo_e_recusada():
    with pytest.raises(dom.ContratoMetaInvalido, match="sem carimbo"):
        cred.prontidao_da_referencia(
            referencia(verificacao_estado="verified", verificado_em=None))


def test_segredo_nao_aparece_em_repr_ou_str():
    material = "token-ultrassecreto"
    segredo = cred.SegredoEfemero(material)
    assert material not in repr(segredo)
    assert material not in str(segredo)


def test_documento_meta_recusa_chave_sensivel_aninhada_sem_repetir_valor():
    material = "nao-pode-vazar"
    with pytest.raises(dom.ContratoMetaInvalido) as erro:
        dom.validar_documento_seguro({"config": {"access_token": material}})
    assert material not in str(erro.value)


def test_hierarquia_vazia_ainda_distingue_zero_observado_de_nao_lido():
    leitura = dom.LeituraDaHierarquia(
        conta_externa="123", campanhas=(), conjuntos=(), anuncios=(),
        criativos=(), paginas_lidas=4)
    assert leitura.contagens == {
        "campaign": 0, "adset": 0, "ad": 0, "creative": 0}
    with pytest.raises(dom.ContratoMetaInvalido, match="completa"):
        dom.LeituraDaHierarquia(
            conta_externa="123", campanhas=(), conjuntos=(), anuncios=(),
            criativos=(), paginas_lidas=0)
