"""Contrato tipado de viabilidade: estados de evidência, dinheiro em micros, as_of obrigatório,
autorização versionada da tolerância, parâmetros versionados e nada posterior ao as_of."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Autorizacao,
    Cambio,
    ContratoViabilidadeViolado,
    EntradaViabilidade,
    Evidencia,
    JanelaObservada,
    MedidaContagem,
    MedidaMonetaria,
    PerdaMaxima,
    PontoSimulacao,
    SimulacaoEntrada,
    Taxa,
    hash_entrada,
)

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
EFETIVO = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def _autorizacao(**kw) -> Autorizacao:
    base = dict(authorization_id="AUTH-T-0001", version="1", issuer="owner:teste", effective_at=EFETIVO, expires_at=None, disponivel_em=EFETIVO)
    base.update(kw)
    return Autorizacao.emitir(**base)


def _perda(valor="300", horizonte=14, autorizacao=None) -> PerdaMaxima:
    return PerdaMaxima(valor=Dinheiro.de_decimal(valor, "BRL"), horizonte_dias=horizonte, autorizacao=autorizacao or _autorizacao())


def _cambio(taxa="5.25", **kw) -> Cambio:
    base = dict(taxa=Decimal(taxa), de="USD", para="BRL", proveniencia="literal_app", evidencia=Evidencia.ESTIMATED,
                effective_at=EFETIVO, disponivel_em=EFETIVO, versao="2026-10-01")
    base.update(kw)
    return Cambio(**base)


def _taxa(valor="1", **kw) -> Taxa:
    base = dict(valor=Decimal(valor), evidencia=Evidencia.ATTESTED, proveniencia="tela", effective_at=EFETIVO, disponivel_em=EFETIVO, versao="v1")
    base.update(kw)
    return Taxa(**base)


def _entrada(**sobrescreve) -> EntradaViabilidade:
    base = dict(
        candidato_id="cand-0001",
        vertical="educacao",
        pais="BR",
        fonte_custo="google_ads",
        fonte_receita="joinads",
        as_of=AS_OF,
        janela=JanelaObservada(inicio="2026-09-26", fim="2026-10-14", dias_maduros=16, dias_imaturos=3),  # 16 maduros + 3 imaturos = span 19
        cliques=MedidaContagem(valor=634, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        custo=MedidaMonetaria(valor=Dinheiro.de_decimal("554.75", "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        receita=MedidaMonetaria(valor=Dinheiro.de_decimal("7.77", "USD"), evidencia=Evidencia.RECONCILED, moeda_evidencia=Evidencia.ATTESTED, disponivel_em=AS_OF),
        cambio=_cambio(),
        revshare=_taxa(),
        imposto=Taxa(valor=None, evidencia=Evidencia.UNKNOWN, proveniencia="ausente"),
        perda_maxima=_perda(),
    )
    base.update(sobrescreve)
    return EntradaViabilidade(**base)


# --------------------------------------------------------------------------- V1 (mantidos)
def test_estados_de_evidencia_obrigatorios_existem():
    assert {e.value for e in Evidencia} == {
        "observed", "attested", "reconciled", "estimated", "projected", "absent", "unknown", "invalid", "immature",
    }


def test_entrada_valida_constroi():
    e = _entrada()
    assert e.custo.valor.micros == 554_750_000
    assert e.receita.moeda_evidencia is Evidencia.ATTESTED
    assert e.freshness_sla_dias == 7 and not hasattr(e, "freshness")


def test_ausencia_nunca_vira_zero():
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria(valor=Dinheiro(0, "BRL"), evidencia=Evidencia.ABSENT, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)
    m = MedidaMonetaria(valor=None, evidencia=Evidencia.ABSENT, moeda_evidencia=Evidencia.UNKNOWN, disponivel_em=AS_OF)
    assert m.valor is None and not m.tem_valor()


def test_valor_presente_exige_evidencia_com_valor():
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaMonetaria(valor=None, evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)


def test_dinheiro_nao_entra_como_float():
    with pytest.raises(TypeError):
        Dinheiro.de_decimal(1.5, "BRL")  # type: ignore[arg-type]


def test_as_of_obrigatorio_e_com_timezone():
    with pytest.raises(ContratoViabilidadeViolado):
        _entrada(as_of=None)
    with pytest.raises(ContratoViabilidadeViolado):
        _entrada(as_of=datetime(2026, 10, 15, 12, 0))


def test_observacao_posterior_ao_as_of_e_recusada():
    depois = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ContratoViabilidadeViolado, match="as_of"):
        _entrada(custo=MedidaMonetaria(valor=Dinheiro(1, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=depois))


def test_hash_da_entrada_e_deterministico_e_sensivel():
    a, b = _entrada(), _entrada()
    assert hash_entrada(a) == hash_entrada(b)
    c = _entrada(cliques=MedidaContagem(valor=635, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF))
    assert hash_entrada(c) != hash_entrada(a)


def test_perda_maxima_ausente_e_representavel_sem_inventar():
    e = _entrada(perda_maxima=PerdaMaxima(valor=None, horizonte_dias=None, autorizacao=None))
    assert e.perda_maxima.valor is None and not e.perda_maxima.informada()


# --------------------------------------------------------------------------- Autorizacao
def test_autorizacao_hash_e_sha256_do_json_canonico():
    a = _autorizacao()
    esperado = hashlib.sha256(json.dumps(
        {"authorization_id": "AUTH-T-0001", "version": "1", "issuer": "owner:teste", "effective_at": EFETIVO.isoformat(), "expires_at": None},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert a.hash == esperado and len(a.hash) == 64


def test_autorizacao_hash_errado_e_recusado():
    a = _autorizacao()
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        Autorizacao(authorization_id=a.authorization_id, version=a.version, hash="0" * 64, issuer=a.issuer,
                    effective_at=a.effective_at, expires_at=a.expires_at, disponivel_em=a.disponivel_em)
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        Autorizacao(authorization_id=a.authorization_id, version=a.version, hash="abc", issuer=a.issuer,
                    effective_at=a.effective_at, expires_at=a.expires_at, disponivel_em=a.disponivel_em)


@pytest.mark.parametrize("issuer", ["owner", "OWNER", "bia", "Agente", "chat", "", "   ", "owner:", ":tarcisio"])
def test_autorizacao_issuer_sem_identidade_e_recusado(issuer):
    with pytest.raises(ContratoViabilidadeViolado, match="issuer"):
        _autorizacao(issuer=issuer)


def test_autorizacao_issuer_com_identidade_passa():
    assert _autorizacao(issuer="owner:tarcisio@exemplo").issuer == "owner:tarcisio@exemplo"


def test_autorizacao_issuer_identidade_enderecavel_nua_passa_e_texto_livre_nao():
    # reconciliação do integrador: uma identidade endereçável (contém '@') vale sem prefixo de papel
    assert _autorizacao(issuer="tarcisio@exemplo").issuer == "tarcisio@exemplo"
    with pytest.raises(ContratoViabilidadeViolado, match="issuer"):
        _autorizacao(issuer="tarcisio")


def test_autorizacao_datas_coerentes():
    with pytest.raises(ContratoViabilidadeViolado, match="effective_at"):
        _autorizacao(effective_at=EFETIVO + timedelta(days=1), disponivel_em=EFETIVO)
    with pytest.raises(ContratoViabilidadeViolado, match="expires_at"):
        _autorizacao(expires_at=EFETIVO)
    with pytest.raises(ContratoViabilidadeViolado, match="timezone"):
        _autorizacao(effective_at=datetime(2026, 10, 1))


def test_autorizacao_vigente_em():
    a = _autorizacao(expires_at=EFETIVO + timedelta(days=10))
    assert a.vigente_em(EFETIVO) and a.vigente_em(EFETIVO + timedelta(days=9, hours=23))
    assert not a.vigente_em(EFETIVO + timedelta(days=10)) and not a.vigente_em(EFETIVO - timedelta(seconds=1))
    assert _autorizacao().vigente_em(EFETIVO + timedelta(days=3650))


def test_autorizacao_json_inverso():
    a = _autorizacao(expires_at=EFETIVO + timedelta(days=10))
    assert Autorizacao.de_json(a.para_json()) == a


# --------------------------------------------------------------------------- PerdaMaxima
def test_perda_maxima_com_valor_sem_autorizacao_e_recusada():
    with pytest.raises(ContratoViabilidadeViolado, match="autorização versionada"):
        PerdaMaxima(valor=Dinheiro.de_decimal("300", "BRL"), horizonte_dias=14, autorizacao=None)


def test_perda_maxima_informada_exige_os_tres():
    assert _perda().informada()
    assert not PerdaMaxima(valor=None, horizonte_dias=14, autorizacao=_autorizacao()).informada()
    assert not PerdaMaxima(valor=Dinheiro.de_decimal("300", "BRL"), horizonte_dias=None, autorizacao=_autorizacao()).informada()
    assert not hasattr(_perda(), "proveniencia")


def test_perda_maxima_autorizacao_expirada_no_as_of_nao_vigora_e_a_entrada_recusa():
    expirada = _autorizacao(expires_at=AS_OF - timedelta(days=1))
    pm = _perda(autorizacao=expirada)
    assert pm.informada() and not pm.vigente_em(AS_OF) and pm.vigente_em(AS_OF - timedelta(days=2))
    with pytest.raises(ContratoViabilidadeViolado, match="vigente"):
        _entrada(perda_maxima=pm)
    futura = _autorizacao(effective_at=AS_OF + timedelta(days=1), disponivel_em=AS_OF + timedelta(days=1))
    with pytest.raises(ContratoViabilidadeViolado, match="as_of"):
        _entrada(perda_maxima=_perda(autorizacao=futura))


# --------------------------------------------------------------------------- Cambio / Taxa versionados
def test_cambio_com_taxa_exige_effective_at_e_disponivel_em():
    with pytest.raises(ContratoViabilidadeViolado, match="effective_at"):
        _cambio(effective_at=None)
    with pytest.raises(ContratoViabilidadeViolado, match="disponivel_em"):
        _cambio(disponivel_em=None)
    ausente = Cambio(taxa=None, de="USD", para="BRL", proveniencia="ausente", evidencia=Evidencia.ABSENT)
    assert ausente.effective_at is None and len(ausente.hash) == 64


def test_cambio_hash_computado_e_verificado():
    c = _cambio()
    esperado = hashlib.sha256(json.dumps(
        {"taxa": "5.25", "de": "USD", "para": "BRL", "proveniencia": "literal_app", "evidencia": "estimated", "effective_at": EFETIVO.isoformat(), "versao": "2026-10-01"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert c.hash == esperado
    assert _cambio(hash=esperado).hash == esperado
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        _cambio(hash="0" * 64)
    assert _cambio(versao="outra").hash != c.hash


def test_taxa_com_valor_exige_effective_at_e_disponivel_em_e_hash():
    with pytest.raises(ContratoViabilidadeViolado, match="effective_at"):
        _taxa(effective_at=None)
    with pytest.raises(ContratoViabilidadeViolado, match="disponivel_em"):
        _taxa(disponivel_em=None)
    t = _taxa()
    assert len(t.hash) == 64 and _taxa(hash=t.hash) == t
    with pytest.raises(ContratoViabilidadeViolado, match="hash"):
        _taxa(hash="f" * 64)
    assert Taxa(valor=None, evidencia=Evidencia.UNKNOWN, proveniencia="ausente").effective_at is None


def test_parametro_disponivel_apos_as_of_e_recusado():
    depois = AS_OF + timedelta(hours=1)
    with pytest.raises(ContratoViabilidadeViolado, match="cambio.disponivel_em"):
        _entrada(cambio=_cambio(disponivel_em=depois, effective_at=depois))
    with pytest.raises(ContratoViabilidadeViolado, match="revshare.disponivel_em"):
        _entrada(revshare=_taxa(disponivel_em=depois, effective_at=depois))
    with pytest.raises(ContratoViabilidadeViolado, match="imposto.disponivel_em"):
        _entrada(imposto=_taxa("0.1", disponivel_em=depois, effective_at=depois))
    # vigência futura publicada antes do as_of: a taxa ainda não vale no as_of
    with pytest.raises(ContratoViabilidadeViolado, match="cambio.effective_at"):
        _entrada(cambio=_cambio(effective_at=depois, disponivel_em=AS_OF))


# --------------------------------------------------------------------------- Medidas
def test_medida_monetaria_negativa_e_recusada():
    with pytest.raises(ContratoViabilidadeViolado, match="nunca negativos"):
        MedidaMonetaria(valor=Dinheiro(-1, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)
    with pytest.raises(ContratoViabilidadeViolado):
        MedidaContagem(valor=-1, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)


def test_observado_em_posterior_ao_disponivel_em_e_recusado():
    with pytest.raises(ContratoViabilidadeViolado, match="observado_em"):
        MedidaMonetaria(valor=Dinheiro(1, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF, observado_em=AS_OF + timedelta(seconds=1))
    with pytest.raises(ContratoViabilidadeViolado, match="observado_em"):
        MedidaContagem(valor=1, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF, observado_em=AS_OF + timedelta(seconds=1))
    m = MedidaMonetaria(valor=Dinheiro(1, "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF,
                        observado_em=AS_OF - timedelta(days=1), flags_qualidade=("b", "a"))
    assert m.flags_qualidade == ("a", "b")


def test_visitas_zero_constroi_e_visitas_e_opcional():
    e = _entrada(visitas=MedidaContagem(valor=0, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF))
    assert e.visitas is not None and e.visitas.valor == 0
    assert _entrada().visitas is None


# --------------------------------------------------------------------------- Janela
def test_janela_com_cobertura_e_dias_de_custo_e_receita():
    j = JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=4, dias_custo_maduro=4, dias_receita_madura=3, dias_custo_sem_receita=1, cobertura_receita_ppm=750_000)
    assert j.cobertura_receita_ppm == 750_000 and JanelaObservada.de_json(j.para_json()) == j
    with pytest.raises(ContratoViabilidadeViolado, match="dias_custo_maduro"):
        JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=4, dias_custo_maduro=3)
    with pytest.raises(ContratoViabilidadeViolado, match="cobertura"):
        JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=4, cobertura_receita_ppm=1_000_001)
    assert JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=4).cobertura_receita_ppm is None


def test_janela_fim_posterior_ao_as_of_e_recusada():
    # a janela observada não pode terminar depois da data do próprio as_of (lookahead por construção)
    with pytest.raises(ContratoViabilidadeViolado, match="janela.fim posterior ao as_of"):
        _entrada(janela=JanelaObservada("2026-10-10", "2026-10-16", dias_maduros=7))
    # fim no MESMO dia do as_of (2026-10-15 12:00Z → 2026-10-15) é aceito
    assert _entrada(janela=JanelaObservada("2026-10-10", "2026-10-15", dias_maduros=6)).janela.fim == "2026-10-15"


def test_janela_contagens_nunca_excedem_o_span_de_dias():
    # span = (fim - inicio).days + 1 = 4
    with pytest.raises(ContratoViabilidadeViolado, match="dias_maduros \\+ dias_imaturos"):
        JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=4, dias_imaturos=1)
    with pytest.raises(ContratoViabilidadeViolado, match="dias_maduros \\+ dias_imaturos"):
        JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=5, dias_custo_maduro=5)
    with pytest.raises(ContratoViabilidadeViolado, match="dias_receita_madura"):
        JanelaObservada("2026-10-01", "2026-10-04", dias_maduros=3, dias_receita_madura=5)
    # encaixe exato: 16 maduros + 3 imaturos em 19 dias
    j = JanelaObservada("2026-09-26", "2026-10-14", dias_maduros=16, dias_imaturos=3, dias_custo_maduro=16, dias_receita_madura=16)
    assert j.span_dias == 19
    # a configuração antiga das fixtures (16 + 3 em 16 dias) é exatamente o que a regra recusa
    with pytest.raises(ContratoViabilidadeViolado, match="span"):
        JanelaObservada("2026-09-26", "2026-10-11", dias_maduros=16, dias_imaturos=3)


@pytest.mark.parametrize("inicio,fim", [("2026-13-01", "2026-10-04"), ("2026-10-01", "ontem"), ("20261001", "2026-10-04"), ("2026-10-01T00:00", "2026-10-04")])
def test_janela_datas_precisam_ser_iso_aaaa_mm_dd(inicio, fim):
    with pytest.raises(ContratoViabilidadeViolado, match="AAAA-MM-DD"):
        JanelaObservada(inicio, fim, dias_maduros=1)


# --------------------------------------------------------------------------- Simulação com câmbio
def test_simulacao_aceita_cambio_opcional_e_respeita_as_of():
    s = SimulacaoEntrada("CPC_BID", "USD", (PontoSimulacao(1, 1, 1),), AS_OF, "MANUAL_CPC", "", _cambio())
    e = _entrada(simulacao=s)
    assert e.simulacao.cambio.taxa == Decimal("5.25")
    tarde = _cambio(effective_at=AS_OF + timedelta(days=1), disponivel_em=AS_OF + timedelta(days=1))
    with pytest.raises(ContratoViabilidadeViolado, match="simulacao.cambio"):
        _entrada(simulacao=SimulacaoEntrada("CPC_BID", "USD", (PontoSimulacao(1, 1, 1),), AS_OF, "MANUAL_CPC", "", tarde))


# --------------------------------------------------------------------------- JSON
def test_para_json_e_de_json_sao_inversos_com_todos_os_campos():
    e = _entrada(
        visitas=MedidaContagem(valor=700, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF, fonte="ga4", observado_em=AS_OF - timedelta(days=1), flags_qualidade=("amostrado",)),
        custo=MedidaMonetaria(valor=Dinheiro.de_decimal("554.75", "BRL"), evidencia=Evidencia.OBSERVED, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF,
                              fonte="google_ads", observado_em=AS_OF - timedelta(days=2), flags_qualidade=("datas_duplicadas=1",)),
        janela=JanelaObservada("2026-09-26", "2026-10-14", 16, 3, dias_custo_maduro=16, dias_receita_madura=12, dias_custo_sem_receita=4, cobertura_receita_ppm=750_000),
        imposto=_taxa("0.15"),
        perda_maxima=_perda(autorizacao=_autorizacao(expires_at=AS_OF + timedelta(days=30))),
        simulacao=SimulacaoEntrada("CPC_BID", "USD", (PontoSimulacao(100_000, 1000, 80_000_000),), AS_OF, "MANUAL_CPC", "search", _cambio()),
        flags_qualidade=("x",), freshness_sla_dias=3, volume_diario_possivel=50,
        cpc_intervalo=(Dinheiro(1, "BRL"), Dinheiro(2, "BRL")),
    )
    j = e.para_json()
    assert "freshness" not in j and j["freshness_sla_dias"] == 3
    assert j["perda_maxima"]["autorizacao"]["hash"] == e.perda_maxima.autorizacao.hash
    assert EntradaViabilidade.de_json(json.loads(json.dumps(j))) == e
    assert hash_entrada(EntradaViabilidade.de_json(j)) == hash_entrada(e)
