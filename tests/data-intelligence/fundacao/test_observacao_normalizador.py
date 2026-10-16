"""Normalizador: schema drift, chave substituída (JoinAds), ausência × falha × atraso, sem float.

Os payloads são SINTÉTICOS, no formato descrito em `src/sql/joinads/README.md` (main) — não
são respostas reais da API.
"""
from __future__ import annotations

import json
from datetime import timedelta, timezone

import pytest

from volc_dil.contracts.vocab import Metrica, ValueKind
from volc_dil.fundacao.observacao import (
    CampoMetrica,
    Coletor,
    ContextoLeitura,
    EsquemaPayload,
    PayloadBruto,
    Registro,
    StatusObservacao,
    Unidade,
    agregar_observacoes,
    as_of,
    normalizar,
    observacoes_sem_dado,
)

ESQ = "joinads.key_value.synthetic.v2"


def _data_da_janela(linha, ctx):
    """JoinAds devolve 'DD/MM/AAAA' por dia, ou 'DD/MM/AAAA à DD/MM/AAAA' para intervalo: recusa o intervalo."""
    data = linha.get("date")
    esperado = ctx.janela_inicio.strftime("%d/%m/%Y")
    return None if data == esperado else "data_fora_da_janela"


CAMPOS = (
    CampoMetrica(("impressions",), Metrica.IMPRESSOES, Unidade.CONTAGEM),
    CampoMetrica(("revenue",), Metrica.RECEITA, Unidade.MICROS, ValueKind.REPORTED_REVENUE),
)
ESQUEMAS = {
    ESQ: EsquemaPayload(
        schema_version=ESQ,
        campo_entidade=("custom_value", "custon_value"),
        campos_metrica=CAMPOS,
        campo_chave=("custom_key", "custon_key"),
        campos_obrigatorios=(("date",),),
        validador=_data_da_janela,
    )
}


@pytest.fixture
def ctx(obs):
    d = obs().janela_inicio
    fim = d + timedelta(days=1)
    return ContextoLeitura(
        fonte="joinads",
        conta="dominio-exemplo",
        entidade_tipo="utm_campaign_value",
        grao=("campaign", "day"),
        dimensoes=(("joinads_domain", "exemplo.com.br"),),
        janela_inicio=d,
        janela_fim=fim,
        timezone="America/Sao_Paulo",
        observed_at=fim + timedelta(hours=6),
        available_at=fim + timedelta(hours=6, minutes=1),
        ingested_at=fim + timedelta(hours=6, minutes=2),
        run_id="run-joinads-1",
        lote_id="lote-joinads-1",
        coletor=Coletor("joinads_report_day_before", "2.0.0"),
        moeda="BRL",
        chave_pedida="utm_campaign",
        entidades_esperadas=("23100000001", "23100000002"),
    )


def _payload(linhas, versao=ESQ) -> PayloadBruto:
    return PayloadBruto(versao, json.dumps(linhas).encode())


def _linha(valor="23100000001", **kw):
    base = {"date": "14/10/2026", "custom_key": "utm_campaign", "custom_value": valor, "impressions": 8, "revenue": "0.123456"}
    base.update(kw)
    return base


def _por(res):
    return {(o.entidade.id, o.metrica.value): o for o in res.observacoes}


def test_resposta_integra_observed_zero_e_missing(ctx):
    res = normalizar(_payload([_linha(), _linha("23100000003", impressions=0, revenue="0")]), ESQUEMAS, ctx)
    m = _por(res)
    assert m[("23100000001", "impressions")].status is StatusObservacao.OBSERVED
    assert m[("23100000001", "revenue")].valor == 123_456 and m[("23100000001", "revenue")].moeda == "BRL"
    assert m[("23100000003", "impressions")].status is StatusObservacao.ZERO_CONFIRMED
    falta = m[("23100000002", "revenue")]
    assert (falta.status, falta.valor, falta.motivo) == (StatusObservacao.MISSING, None, "linha_ausente_na_resposta")
    assert res.rejeicoes == () and res.campos_extras == ()
    assert all(o.payload_sha256 == res.payload_sha256 and o.payload_ref.endswith(res.payload_sha256) for o in res.observacoes)


def test_chave_substituida_vira_invalid_e_nunca_entidade_falsa(ctx):
    # pedi utm_campaign; a API devolveu land_uri com valor "/" (README JoinAds, armadilha 2)
    res = normalizar(_payload([_linha("/", custom_key="land_uri", impressions=8)]), ESQUEMAS, ctx)
    assert {o.entidade.id for o in res.observacoes} == {"23100000001", "23100000002"}  # "/" não virou campanha
    assert all(o.status is StatusObservacao.INVALID for o in res.observacoes)
    assert all(o.motivo == "chave_substituida:utm_campaign->land_uri" for o in res.observacoes)
    assert [r.motivo for r in res.rejeicoes] == ["chave_substituida"]
    assert dict(res.rejeicoes[0].detalhe) == {"devolvida": "land_uri", "pedida": "utm_campaign"}


def test_campo_obrigatorio_ausente_e_invalid_com_motivo(ctx):
    sem_receita = _linha()
    del sem_receita["revenue"]
    sem_data = _linha("23100000002")
    del sem_data["date"]
    m = _por(normalizar(_payload([sem_receita, sem_data]), ESQUEMAS, ctx))
    assert m[("23100000001", "revenue")].status is StatusObservacao.INVALID
    assert m[("23100000001", "revenue")].motivo == "campo_obrigatorio_ausente:revenue"
    assert m[("23100000001", "impressions")].status is StatusObservacao.OBSERVED  # o resto da linha vale
    assert m[("23100000002", "impressions")].motivo == "campo_obrigatorio_ausente:date"


def test_sem_identidade_vai_para_rejeicao(ctx):
    sem_id = _linha()
    del sem_id["custom_value"]
    res = normalizar(_payload([sem_id, "lixo"]), ESQUEMAS, ctx)
    assert sorted(r.motivo for r in res.rejeicoes) == ["campo_obrigatorio_ausente:custom_value", "linha_nao_objeto"]
    # entidades esperadas não podem ser dadas como ausentes: a resposta teve linhas rejeitadas
    assert {o.motivo for o in res.observacoes} == {"resposta_com_linhas_rejeitadas"}


def test_campos_extras_ignorados_e_registrados_aliases_aceitos(ctx):
    linha = {"date": "14/10/2026", "custon_key": "utm_campaign", "custon_value": "23100000001",
             "impressions": 8, "revenue": "1.5", "active_view": 3, "ecpm": "0.2"}
    res = normalizar(_payload([linha]), ESQUEMAS, ctx)
    assert res.campos_extras == ("active_view", "ecpm")
    assert _por(res)[("23100000001", "revenue")].valor == 1_500_000


@pytest.mark.parametrize(
    "bruto, motivo",
    [("1,5", "valor_invalido:revenue"), ("NaN", "valor_invalido:revenue"), (True, "valor_invalido:revenue"),
     ("0.0000001", "precisao_acima_de_micros:revenue")],
)
def test_valores_monetarios_recusados(ctx, bruto, motivo):
    o = _por(normalizar(_payload([_linha(revenue=bruto)]), ESQUEMAS, ctx))[("23100000001", "revenue")]
    assert (o.status, o.valor, o.motivo) == (StatusObservacao.INVALID, None, motivo)


def test_float_que_escapa_do_parse_e_recusado(ctx):
    # bytes com número float: o normalizador lê com Decimal; float só chega se alguém montar o payload mal
    from volc_dil.fundacao.observacao.normalizador import _converter

    assert _converter(0.1, CAMPOS[1]) == (None, "float_recusado:revenue")
    o = _por(normalizar(_payload([_linha(revenue=0.1)]), ESQUEMAS, ctx))[("23100000001", "revenue")]
    assert o.valor == 100_000  # 0.1 do JSON lido como Decimal('0.1'), não 0.1000000000000000055


@pytest.mark.parametrize("bruto, motivo", [(-1, "contagem_negativa:impressions"), ("2.5", "contagem_fracionaria:impressions")])
def test_contagens_recusadas(ctx, bruto, motivo):
    o = _por(normalizar(_payload([_linha(impressions=bruto)]), ESQUEMAS, ctx))[("23100000001", "impressions")]
    assert (o.status, o.motivo) == (StatusObservacao.INVALID, motivo)


def test_valor_nulo_da_fonte_e_missing_nao_zero(ctx):
    o = _por(normalizar(_payload([_linha(revenue=None)]), ESQUEMAS, ctx))[("23100000001", "revenue")]
    assert (o.status, o.valor, o.motivo) == (StatusObservacao.MISSING, None, "valor_nulo_na_fonte:revenue")


def test_intervalo_de_datas_e_linha_duplicada(ctx):
    m = _por(normalizar(_payload([_linha(date="13/10/2026 à 14/10/2026"), _linha("23100000002"), _linha("23100000002")]), ESQUEMAS, ctx))
    assert m[("23100000001", "revenue")].motivo == "data_fora_da_janela"
    assert m[("23100000002", "revenue")].motivo == "linha_duplicada"


def test_janela_aberta_vira_partial_com_cobertura(ctx):
    d = ctx.janela_inicio
    intra = ContextoLeitura(**{**ctx.__dict__, "observed_at": d + timedelta(hours=12),
                               "available_at": d + timedelta(hours=12), "ingested_at": d + timedelta(hours=12)})
    o = _por(normalizar(_payload([_linha()]), ESQUEMAS, intra))[("23100000001", "revenue")]
    # R1-F17: sem cobertura declarada pela fonte, não se fabrica 50% pelo relógio
    assert (o.status, o.valor, o.cobertura_ppm, o.motivo) == (StatusObservacao.PARTIAL, 123_456, None, "janela_aberta;cobertura_desconhecida")
    # cobertura declarada pela fonte passa intacta (mata M11: cobertura constante)
    for declarada in (1, 250_000, 999_999):
        dec = ContextoLeitura(**{**intra.__dict__, "cobertura_ppm": declarada})
        o = _por(normalizar(_payload([_linha()]), ESQUEMAS, dec))[("23100000001", "revenue")]
        assert (o.cobertura_ppm, o.motivo) == (declarada, "janela_aberta")


def test_schema_desconhecido_e_payload_nao_json(ctx):
    res = normalizar(_payload([_linha()], versao="joinads.key_value.synthetic.v3"), ESQUEMAS, ctx)
    assert res.observacoes == () and res.rejeicoes[0].motivo == "schema_desconhecido"
    res = normalizar(PayloadBruto(ESQ, b"<html>502 Bad Gateway</html>"), ESQUEMAS, ctx)
    assert {o.status for o in res.observacoes} == {StatusObservacao.INVALID}
    assert {o.motivo for o in res.observacoes} == {"payload_nao_json"}


def test_ausencia_falha_e_atraso_distintos_de_ponta_a_ponta(ctx):
    """missing (respondeu sem linha) × unavailable (não respondeu) × late (ainda não publicou)."""
    ok = normalizar(_payload([_linha()]), ESQUEMAS, ctx).observacoes  # 23100000002 → missing
    erro = PayloadBruto(ESQ, b'{"status": 503}')
    ctx_b = ContextoLeitura(**{**ctx.__dict__, "conta": "dominio-b", "lote_id": "lote-b"})
    ctx_c = ContextoLeitura(**{**ctx.__dict__, "conta": "dominio-c", "lote_id": "lote-c"})
    falhou = observacoes_sem_dado(ctx_b, erro, CAMPOS, StatusObservacao.UNAVAILABLE, "http_503")
    atrasou = observacoes_sem_dado(ctx_c, PayloadBruto(ESQ, b"[]"), CAMPOS, StatusObservacao.LATE, "d-1_nao_publicado_ate_06h")
    r = Registro(ok + falhou + atrasou)
    estado = as_of(r.observacoes, ctx.ingested_at + timedelta(days=1))
    receitas = [o for o in estado.values() if o.metrica is Metrica.RECEITA]
    por_status = {}
    for o in receitas:
        por_status.setdefault(o.status.value, []).append(o)
    assert {k: len(v) for k, v in por_status.items()} == {"observed": 1, "missing": 1, "unavailable": 2, "late": 2}
    ag = agregar_observacoes(receitas)
    assert ag.valor is None and dict(ag.por_status) == {"late": 2, "missing": 1, "observed": 1, "unavailable": 2}
    with pytest.raises(ValueError):
        observacoes_sem_dado(ctx, erro, CAMPOS, StatusObservacao.OBSERVED, "x")
