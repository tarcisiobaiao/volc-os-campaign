"""Respostas à revisão adversarial R2 (thread D): cada teste falha no código anterior à correção.

G2 dedup do caminho real × D1 · G3 portão de cobertura sem earnings · G11 quarentena sem ressuscitar versão
superada · G12 custo campanha × dia com dimensões · G13 mutantes D6/D7/D10 · G17 ids sintéticos ·
G22 fixture assume coletor endurecido (moeda no payload).
"""
from __future__ import annotations

import dataclasses
import hashlib
import itertools
from datetime import date, timedelta
from pathlib import Path

import pytest

from volc_dil.contracts.fingerprint import json_canonico
from volc_dil.fundacao.observacao import adaptar_google_ads_v21, as_of
from volc_dil.fundacao.shadow import _gerador_provisorio as gp
from volc_dil.fundacao.shadow.avaliacao import _imaturo
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado
from volc_dil.fundacao.shadow.kernel import ConfigKernel
from volc_dil.fundacao.shadow.linhas_formato_real import (
    DOMINIO_SINTETICO,
    instante_local,
    linha_joinads_earnings,
    linha_joinads_kv,
    linha_v21,
)
from volc_dil.fundacao.shadow.motor import decidir_no_corte
from volc_dil.fundacao.shadow.politicas import Manter, RegraMargem, equal, exigir_snapshot
from volc_dil.fundacao.shadow.real import observacoes_de_linhas_reais
from volc_dil.fundacao.shadow.snapshot import CambioDeclarado, ConfigCorte, SnapshotAdulterado, construir_snapshot
from volc_dil.fundacao.shadow.tipos import BPS, Acao, Confianca, DecisaoShadow, EntidadeCampanha, PropostaShadow

CONTA, CID = "1234567890", "90000000011"
CAMBIO = (CambioDeclarado("USD", "BRL", 5, 1, "declarado:teste"),)


# --------------------------------------------------------------------------- G2
def _l(run, custo, col_h, atraso_h, dia=date(2026, 10, 14)):
    col = instante_local(dia + timedelta(days=1), col_h)
    return linha_v21(run_id=run, batch_id=run + ":b", customer_id=CONTA, campaign_id=CID, dia=dia, custo_micros=custo,
                     impressoes=10, cliques=1, collected_at=col, created_at=col + timedelta(hours=atraso_h, minutes=1))


def test_g2_releitura_nova_nao_perde_para_leitura_antiga_atrasada():
    # 06h valor A; 08h valor A de novo (releitura); 07h valor B lido às 07h mas gravado às 09h (atrasado)
    linhas = [_l("r06", 5_000_000, 6, 0), _l("r08", 5_000_000, 8, 0), _l("r07", 7_000_000, 7, 2)]
    t = instante_local(date(2026, 10, 15), 10)
    brutas = [o for l in linhas for o in adaptar_google_ads_v21(l)]
    verdade = {k: o.valor for k, o in as_of(brutas, t).items() if o.metrica.value == "cost"}
    assert list(verdade.values()) == [5_000_000]  # a leitura mais recente da fonte (08h) vence (D1)
    for perm in itertools.permutations(linhas):
        a = observacoes_de_linhas_reais(list(perm), [])
        obtido = {k: i.obs.valor for k, i in FluxoIndexado(a.observacoes).as_of(t).items() if i.obs.metrica.value == "cost"}
        assert obtido == verdade
    # e em todo corte intermediário o caminho real = as_of da A sobre todas as leituras
    a = observacoes_de_linhas_reais(linhas, [])
    fi = FluxoIndexado(a.observacoes)
    for h in range(6, 12):
        tt = instante_local(date(2026, 10, 15), h, 30)
        esperado = {k: o.valor for k, o in as_of(brutas, tt).items()}
        assert {k: i.obs.valor for k, i in fi.as_of(tt).items()} == esperado


# --------------------------------------------------------------------------- G3
def _cenario_cobertura(modo: str, kernel: ConfigKernel = ConfigKernel()):
    dias = [date(2026, 10, 1) + timedelta(days=k) for k in range(8)]
    v21, jo = [], []
    for i, d in enumerate(dias):
        col = instante_local(d + timedelta(days=1), 4)
        v21.append(linha_v21(run_id=f"g{i}", batch_id=f"g{i}:b", customer_id=CONTA, campaign_id=CID, dia=d,
                             custo_micros=10_000_000, impressoes=100, cliques=10, collected_at=col,
                             created_at=col + timedelta(minutes=1)))
        colj = instante_local(d + timedelta(days=1), 8)
        jo.append(linha_joinads_kv(run_key=f"j{i}", batch_key=f"j{i}:kv", domain=DOMINIO_SINTETICO, dia=d, campaign_id=CID,
                                   custom_key="utm_campaign", custom_value=CID, receita_micros=1_500_000, collected_at=colj,
                                   created_at=colj + timedelta(minutes=1)))
        if modo in ("medido_baixo", "medido_alto", "unavailable"):
            e = linha_joinads_earnings(run_key=f"j{i}", batch_key=f"j{i}:e", domain=DOMINIO_SINTETICO, dia=d,
                                       receita_micros=10_000_000 if modo == "medido_baixo" else 1_520_000,
                                       collected_at=colj, created_at=colj + timedelta(minutes=1))
            if modo == "unavailable":
                e.update(data_status="unavailable", revenue_client=None, revenue_gross=None)
            jo.append(e)
    a = observacoes_de_linhas_reais(v21, jo)
    snap = construir_snapshot(FluxoIndexado(a.observacoes), instante_local(dias[-1] + timedelta(days=4), 7),
                              ConfigCorte(cambios=CAMBIO))
    p = decidir_no_corte(snap, RegraMargem(), kernel).propostas[0]
    return p


def test_g3_corte_sem_cobertura_comprovada_e_bloqueado():
    alto = _cenario_cobertura("medido_alto")
    assert alto.acao is Acao.REDUZIR_VERBA and alto.bloqueios == ()  # o portão não bloqueia tudo
    baixo = _cenario_cobertura("medido_baixo")
    assert any(b.startswith("cobertura_receita_baixa") for b in baixo.bloqueios)  # mata o mutante D1
    ausente = _cenario_cobertura("ausente")
    assert ausente.bloqueios and all(b.startswith("cobertura_receita_nao_comprovada") and b.endswith("soma_key_value")
                                     for b in ausente.bloqueios)
    indisp = _cenario_cobertura("unavailable")
    assert indisp.bloqueios and all(b.endswith(":indisponivel") for b in indisp.bloqueios)
    for p in (baixo, ausente, indisp):
        assert p.acao is Acao.REDUZIR_VERBA and p.fator_efetivo_bps == BPS
    # relaxamento declarado (só para sintético sem earnings): soma do kv aceita, earnings unavailable não
    rel = ConfigKernel(cobertura_sem_earnings="aceitar_declarado")
    assert _cenario_cobertura("ausente", rel).bloqueios == ()
    assert _cenario_cobertura("unavailable", rel).bloqueios
    with pytest.raises(ValueError):
        ConfigKernel(cobertura_sem_earnings="ignorar")


# --------------------------------------------------------------------------- G11
def test_g11_quarentena_nao_ressuscita_versao_superada(obs):
    d = obs().janela_inicio
    velho = obs(valor=5_000_000, observed_at=d + timedelta(days=1, hours=5), available_at=d + timedelta(days=1, hours=6),
                ingested_at=d + timedelta(days=1, hours=6), payload=b"old")
    a = obs(valor=9_000_000, observed_at=d + timedelta(days=1, hours=9), available_at=d + timedelta(days=1, hours=10),
            ingested_at=d + timedelta(days=1, hours=10), payload=b"p1")
    b = obs(valor=1_000_000, observed_at=d + timedelta(days=1, hours=9), available_at=d + timedelta(days=1, hours=10),
            ingested_at=d + timedelta(days=1, hours=10), payload=b"p2")
    t = d + timedelta(days=1, hours=11)
    fi = FluxoIndexado([velho, a, b], ambiguidade="quarentena")
    assert fi.as_of(t) == {}  # o fato sai: nem 9, nem 1, e muito menos o 5 superado
    assert {i.obs.valor for i in fi.ambiguos_em(t)[velho.chave_natural]} == {9_000_000, 1_000_000}
    assert fi.as_of(d + timedelta(days=1, hours=7))[velho.chave_natural].obs.valor == 5_000_000  # antes do empate
    novo = obs(valor=3_000_000, observed_at=d + timedelta(days=1, hours=12), available_at=d + timedelta(days=1, hours=13),
               ingested_at=d + timedelta(days=1, hours=13), payload=b"p3")
    fi2 = FluxoIndexado([velho, a, b, novo], ambiguidade="quarentena")
    t2 = d + timedelta(days=1, hours=14)
    assert fi2.as_of(t2)[velho.chave_natural].obs.valor == 3_000_000 and fi2.ambiguos_em(t2) == {}  # empate superado
    snap = construir_snapshot(fi, t + timedelta(days=4))
    assert any(x.startswith("versao_ambigua:custo:") for x in snap.bloqueios_de(EntidadeCampanha(velho.conta, velho.entidade.id)))


# --------------------------------------------------------------------------- G12
def test_g12_custo_com_dimensoes_nao_e_escolhido_ao_acaso(obs):
    a = obs(valor=5_000_000, dimensoes=(("device", "desktop"),), payload=b"a")
    b = obs(valor=7_000_000, dimensoes=(("device", "mobile"),), payload=b"b")
    t = a.janela_inicio + timedelta(days=5)
    ent = EntidadeCampanha(a.conta, a.entidade.id)
    for ordem in ([a, b], [b, a]):
        s = construir_snapshot(FluxoIndexado(ordem), t)
        f = s.fato(ent, a.janela_inicio.date())
        assert f.custo.valor is None and f.custo_status == "invalid" and f.custo_versoes == 2
        assert any(x.startswith("custo_so_com_dimensoes:") for x in s.bloqueios_de(ent))
    total = obs(valor=12_000_000, payload=b"total")
    s = construir_snapshot(FluxoIndexado([a, b, total]), t)
    f = s.fato(ent, a.janela_inicio.date())
    assert f.custo.valor.micros == 12_000_000 and not s.bloqueios_de(ent)
    assert any(d.codigo == "custo_dimensionado_ignorado" for d in s.diagnosticos_dados)


# --------------------------------------------------------------------------- G13 (mutantes D6, D7, D10)
def test_d6_politica_que_altera_o_snapshot_e_pega_na_segunda_checagem():
    fs, cortes, cfg = gp.preparar("base", passo_horas=24, hora_inicial=7)
    snap = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[-2], cfg.corte)

    class Adulteradora:
        nome, versao = "adulteradora", "x@1"

        def decidir(self, s):
            exigir_snapshot(s)
            dec = Manter().decidir(s)
            object.__setattr__(s, "fatos", s.fatos[1:])  # trapaça: mexe no snapshot depois de lido
            return DecisaoShadow(tuple(dataclasses.replace(p, politica=self.nome) for p in dec.propostas))

    with pytest.raises(SnapshotAdulterado):
        decidir_no_corte(snap, Adulteradora(), cfg.kernel)


def test_d7_corte_de_campanha_nova_conta_como_sinal_imaturo():
    def p(ev):
        return PropostaShadow("x", "v", "t", "f", EntidadeCampanha("1", "2"), Acao.PAUSAR, 0, Confianca.BAIXA, "m", ev)

    assert _imaturo(p({"horas_desde_primeiro_custo": 10, "dias_imaturos_usados": 0}))
    assert _imaturo(p({"horas_desde_primeiro_custo": 71, "dias_imaturos_usados": 0}))
    assert not _imaturo(p({"horas_desde_primeiro_custo": 100, "dias_imaturos_usados": 0}))
    assert _imaturo(p({"horas_desde_primeiro_custo": 100, "dias_imaturos_usados": 1}))


def test_d10_custo_parcial_nunca_conta_como_fechado():
    fs, cortes, cfg = gp.preparar("base", passo_horas=24, hora_inicial=7)
    so_parcial = [o for o in fs.observacoes if not (o.fonte == "google_ads" and o.observed_at >= o.janela_fim)]
    assert any(o.status.value == "partial" for o in so_parcial)
    snap = construir_snapshot(FluxoIndexado(so_parcial), cortes[-2], cfg.corte)
    regra = RegraMargem().decidir(snap)
    assert all(p.acao is Acao.INSUFICIENTE for p in regra.propostas)
    assert any("custo_partial" in r for p in regra.propostas for r in p.evidencia_dict()["recusas"])
    assert all(p.acao is Acao.INSUFICIENTE for p in equal().decidir(snap).propostas)  # sem custo fechado em D-1


# --------------------------------------------------------------------------- G17 e G22
def test_g17_sem_prefixo_de_campanha_real_no_pacote():
    import volc_dil.fundacao.shadow as pacote

    proibido = "24278" + "6651"  # montado para este teste não conter o próprio padrão
    for f in Path(pacote.__file__).parent.glob("*.py"):
        assert proibido not in f.read_text(encoding="utf-8"), f.name


def test_g22_sem_moeda_no_payload_o_real_sai_invalid_e_nada_e_cortado():
    """A fixture assume o coletor ENDURECIDO (moeda no payload bruto). Com o v21 de hoje (moeda só na coluna,
    'BRL' fixo), o adaptador da A não aceita a moeda e o custo sai `invalid moeda_nao_provada`."""
    dias = [date(2026, 10, 1) + timedelta(days=k) for k in range(8)]
    v21, jo = [], []
    for i, d in enumerate(dias):
        col = instante_local(d + timedelta(days=1), 4)
        l = linha_v21(run_id=f"h{i}", batch_id=f"h{i}:b", customer_id=CONTA, campaign_id=CID, dia=d, custo_micros=10_000_000,
                      impressoes=100, cliques=10, collected_at=col, created_at=col + timedelta(minutes=1))
        payload = {k: v for k, v in l["batch_payload"].items() if k != "customer"}  # coletor de hoje
        l.update(batch_payload=payload, batch_payload_sha256=hashlib.sha256(json_canonico(payload).encode()).hexdigest())
        v21.append(l)
        colj = instante_local(d + timedelta(days=1), 8)
        jo.append(linha_joinads_kv(run_key=f"j{i}", batch_key=f"j{i}:kv", domain=DOMINIO_SINTETICO, dia=d, campaign_id=CID,
                                   custom_key="utm_campaign", custom_value=CID, receita_micros=1_000_000, collected_at=colj,
                                   created_at=colj + timedelta(minutes=1)))
    a = observacoes_de_linhas_reais(v21, jo)
    custos = [o for o in a.observacoes if o.fonte == "google_ads" and o.metrica.value == "cost"]
    assert custos and all(o.status.value == "invalid" and o.motivo == "moeda_nao_provada" for o in custos)
    snap = construir_snapshot(FluxoIndexado(a.observacoes), instante_local(dias[-1] + timedelta(days=4), 7),
                              ConfigCorte(cambios=CAMBIO))
    assert all(p.acao is Acao.INSUFICIENTE for p in RegraMargem().decidir(snap).propostas)
