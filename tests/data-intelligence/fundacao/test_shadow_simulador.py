"""Shadow sobre o Simulator Lab (thread E). Pulado se o simulador não estiver no checkout (worktree D
antes do merge); roda no branch integrado."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

sim_mod = pytest.importorskip("volc_dil.fundacao.simulador")

from volc_dil.fundacao.shadow.avaliacao import avaliar  # noqa: E402
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado  # noqa: E402
from volc_dil.fundacao.shadow.fonte_simulador import (  # noqa: E402
    cortes_do_simulador,
    fluxo_do_simulador,
    observacoes_do_simulador,
    registro_para_observacao,
)
from volc_dil.fundacao.shadow.motor import ConfigShadow, executar_replay  # noqa: E402
from volc_dil.fundacao.shadow.politicas import Guardiao72h, Manter, RegraMargem, equal, regra_margem_null_zero  # noqa: E402
from volc_dil.fundacao.shadow.snapshot import ConfigCorte, construir_snapshot  # noqa: E402
from volc_dil.fundacao.shadow.tipos import BPS, Acao  # noqa: E402

SEED = 20261016
TAM = dict(n_campanhas=6, n_dias=12)


def _cfg(fs):
    return ConfigShadow(ConfigCorte(cambios=fs.cambios))


def _cortes(fs):
    return cortes_do_simulador(fs, passo=timedelta(hours=24))


@pytest.fixture(scope="module")
def estavel():
    return fluxo_do_simulador("estavel", SEED, **TAM)


def test_adaptador_aplica_as_regras_do_contrato():
    sim = sim_mod.simular("zero_falso", SEED, **TAM)
    for r in sim.leituras.registros:
        o = registro_para_observacao(r, sim_mod.VERSAO_SIMULADOR)
        if o is None:
            assert r.metrica == "pageviews"
            continue
        if r.status == "observed" and r.valor == 0:
            assert o.status.value == "missing" and o.motivo == "observado_zero_sem_confirmacao"
        if r.custom_key_efetiva and r.custom_key_solicitada and r.custom_key_efetiva != r.custom_key_solicitada:
            assert o.status.value == "invalid" and o.motivo.startswith("chave_substituida")
        elif r.status == "zero_confirmed" and r.fonte == "google_ads" and r.entidade_tipo == "campaign":
            assert o.status.value == "missing" and o.motivo == "zero_sem_prova_de_linha"
        elif r.status == "late":
            assert o.status.value in ("observed", "zero_confirmed", "missing")
            if o.status.value == "observed":
                assert o.valor == r.valor and o.motivo.startswith("coleta_atrasada")
        if o.metrica.value == "revenue" and o.fonte == "joinads":
            assert dict(o.dimensoes)["revenue_basis"] == "client"
        assert o.available_at.isoformat().startswith(r.available_at[:19])
    ad = observacoes_do_simulador(sim.leituras.registros)
    assert ad.rejeitados == [] and ad.por_regra


def test_snapshot_reproduz_o_consumidor_correto_do_simulador(estavel):
    """Valores fechados do snapshot = `visao_as_of` da E, salvo entrega fora de ordem (divergência documentada)."""
    sim = estavel.verdade.sim
    fi = FluxoIndexado(estavel.observacoes, ambiguidade="quarentena")
    t = _cortes(estavel)[-1]
    snap = construir_snapshot(fi, t, _cfg(estavel).corte)
    visao = sim_mod.visao_as_of(sim.leituras.registros, sim_mod.iso(t))
    por = {}
    for r in visao.values():
        if r.fonte == "google_ads" and r.metrica == "cost" and r.entidade_tipo == "campaign":
            por[(r.entidade, r.janela_inicio)] = r
    iguais = divergentes = 0
    for f in snap.fatos:
        if f.custo_status != "observed":
            continue
        ini = sim_mod.iso(sim.mundo.instante_local((f.dia - sim.mundo.dias[0]).days, 0))
        r = por.get((f.entidade.campaign_id, ini))
        if r is None:
            continue
        if r.valor == f.custo.valor.micros:
            iguais += 1
        else:
            divergentes += 1
    assert iguais > 0 and divergentes <= iguais // 10


def test_zero_sintetizado_do_coletor_nao_vira_corte():
    fs = fluxo_do_simulador("zero_sintetizado_coletor", SEED, n_campanhas=4, n_dias=10)
    assert fs.meta["regras_aplicadas"].get("zero_confirmed->missing:zero_sem_prova_de_linha", 0) > 0
    res = executar_replay(fs.observacoes, _cortes(fs), [RegraMargem(), regra_margem_null_zero()], config=_cfg(fs))
    snap_ids = {}
    for d in res.da_politica("regra_margem"):
        for p in d.decisao.propostas:
            if p.evidencia_dict().get("custo_micros", 0) == 0:
                assert p.acao not in (Acao.PAUSAR, Acao.REDUZIR_VERBA)
                snap_ids[p.entidade] = True
    mortas = [p for d in res.da_politica("regra_margem_null_zero") for p in d.decisao.propostas
              if p.motivo.startswith("campanha_morta")]
    assert snap_ids and mortas


def test_identidade_trocada_vira_bloqueio_de_dia():
    fs = fluxo_do_simulador("identidade_trocada", SEED, **TAM)
    fi = FluxoIndexado(fs.observacoes, ambiguidade="quarentena")
    snap = construir_snapshot(fi, _cortes(fs)[-1], _cfg(fs).corte)
    assert any("custom_key_substituida" in c.bloqueios for c in snap.cobertura)


def test_retrodatado_so_vazaria_com_corte_por_observed_at():
    fs = fluxo_do_simulador("vazamento_tentado", SEED, **TAM)
    cortes = _cortes(fs)
    honesto = executar_replay(fs.observacoes, cortes, [RegraMargem()], config=_cfg(fs))
    trapaca = [dataclasses.replace(o, available_at=max(o.observed_at, o.janela_inicio), ingested_at=o.ingested_at)
               for o in fs.observacoes]
    errado = executar_replay(trapaca, cortes, [RegraMargem()], config=_cfg(fs))
    assert honesto.sha256() != errado.sha256()  # cortar por observed_at muda o que se "sabia"


def test_moeda_misturada_exige_cambio_declarado():
    fs = fluxo_do_simulador("moeda_misturada", SEED, **TAM)
    fi = FluxoIndexado(fs.observacoes, ambiguidade="quarentena")
    t = _cortes(fs)[-1]
    sem = RegraMargem().decidir(construir_snapshot(fi, t, ConfigCorte()))
    usd = {c.id for c in fs.verdade.sim.mundo.campanhas if c.moeda_receita == "USD"}
    assert usd
    for p in sem.propostas:
        if p.entidade.campaign_id in usd and p.evidencia_dict()["n_dias"]:
            pytest.fail("receita USD sem câmbio virou margem")
    com = RegraMargem().decidir(construir_snapshot(fi, t, _cfg(fs).corte))
    assert any(p.entidade.campaign_id in usd and "margem_bps" in p.evidencia_dict() for p in com.propostas)


def test_verdade_simulador_e_pareada(estavel):
    v = estavel.verdade
    cels = v.celulas()
    pausa = v.lucros({c: 0 for c in cels})
    assert all(x == 0 for x in pausa.values())
    m = estavel.verdade.sim.mundo
    base = v.lucros({c: BPS for c in cels})
    custo, rec = m.diario("custo_final_micros"), m.diario("receita_micros")
    for c, ent in enumerate(v.ents):
        for i, d in enumerate(v.dias):
            if (ent, d) in base and not v.usd[c]:
                assert base[(ent, d)] == int(rec[c, i]) - int(custo[c, i])


def test_divergencia_do_contrafactual_so_onde_a_verba_muda_no_dia(estavel):
    assert estavel.verdade.divergencia_manter_vs_mundo()["celulas_divergentes"] == 0
    mud = fluxo_do_simulador("mudanca_orcamento", SEED, **TAM)
    assert mud.verdade.divergencia_manter_vs_mundo()["celulas_divergentes"] > 0  # documentado em 06 §7.2


def test_cenario_so_de_sensor_nao_muda_decisoes(estavel):
    base = executar_replay(estavel.observacoes, _cortes(estavel), [RegraMargem(), equal()], config=_cfg(estavel))
    for nome in ("sensor_sem_campanha",):  # dedup_por_segundo também injeta bots no MUNDO: muda a verdade
        fs = fluxo_do_simulador(nome, SEED, **TAM)
        r = executar_replay(fs.observacoes, _cortes(fs), [RegraMargem(), equal()], config=_cfg(fs))
        assert [d.decisao.assinatura() for d in r.decisoes] == [d.decisao.assinatura() for d in base.decisoes], nome


def test_replay_e_avaliacao_no_simulador(estavel):
    res = executar_replay(estavel.observacoes, _cortes(estavel), [Manter(), equal(), RegraMargem(), Guardiao72h(RegraMargem())],
                          config=_cfg(estavel))
    a = avaliar(res, estavel.verdade, hora_decisao=0)
    assert a["natureza"] == "testado_com_sintetico" and a["n_celulas"] > 0
    assert all(v["regret_vs_oraculo_micros"] >= 0 for v in a["politicas"].values())
