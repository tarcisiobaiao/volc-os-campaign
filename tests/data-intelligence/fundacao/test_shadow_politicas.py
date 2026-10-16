"""Políticas shadow: catálogo, saída tipada, executavel=False, guardião 72 h e baselines herdadas."""
from __future__ import annotations

from datetime import timedelta

import pytest

from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado
from volc_dil.fundacao.shadow.motor import decidir_no_corte
from volc_dil.fundacao.shadow.politicas import (
    Guardiao72h,
    Manter,
    RegraMargem,
    catalogo_padrao,
    equal,
    greedy_conservador,
    regra_margem_imatura,
)
from volc_dil.fundacao.shadow.snapshot import construir_snapshot
from volc_dil.fundacao.shadow.tipos import (
    BPS,
    Acao,
    Confianca,
    EntidadeCampanha,
    ExecucaoProibida,
    PropostaShadow,
)


@pytest.fixture(scope="module")
def snap_base():
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    fi = FluxoIndexado(fs.observacoes)
    return construir_snapshot(fi, cortes[-2], cfg.corte), cfg


def test_proposta_nunca_executavel():
    e = EntidadeCampanha("1", "2")
    with pytest.raises(ExecucaoProibida):
        PropostaShadow("p", "v", "t", "f", e, Acao.PAUSAR, 0, Confianca.ALTA, "m", executavel=True)
    with pytest.raises(ValueError):
        PropostaShadow("p", "v", "t", "f", e, Acao.PAUSAR, 5000, Confianca.ALTA, "m")
    with pytest.raises(TypeError):
        PropostaShadow("p", "v", "t", "f", e, Acao.MANTER, BPS, Confianca.ALTA, "m", evidencia={"x": 1.5})
    p = PropostaShadow("p", "v", "t", "f", e, Acao.REDUZIR_VERBA, 7000, Confianca.MEDIA, "m", bloqueios=("x",))
    assert p.fator_efetivo_bps == BPS and p.para_json()["executavel"] is False


def test_catalogo_inteiro_decide_e_passa_pelo_kernel(snap_base):
    snap, cfg = snap_base
    for pol in catalogo_padrao():
        dec = decidir_no_corte(snap, pol, cfg.kernel)
        assert {p.entidade for p in dec.propostas} == set(snap.campanhas)
        assert all(p.executavel is False and p.fingerprint_corte == snap.fingerprint for p in dec.propostas)
        assert all(p.politica == pol.nome for p in dec.propostas)


def test_regra_margem_corta_o_que_tem_margem_madura_ruim(snap_base):
    snap, cfg = snap_base
    dec = decidir_no_corte(snap, RegraMargem(), cfg.kernel)
    por_id = {p.entidade.campaign_id[-1]: p for p in dec.propostas}
    # ROAS verdadeiros do gerador: 1,50 1,25 1,08 0,90 0,60 0,45
    assert por_id["0"].acao is Acao.MANTER and por_id["1"].acao is Acao.MANTER
    assert por_id["3"].acao is Acao.REDUZIR_VERBA
    assert por_id["4"].acao is Acao.PAUSAR and por_id["5"].acao is Acao.PAUSAR
    ev = por_id["5"].evidencia_dict()
    assert ev["dias_imaturos_usados"] == 0 and ev["n_dias"] >= 3 and "margem_bps" in ev


def test_regra_margem_sem_maturidade_e_insuficiente():
    fs, cortes, cfg = preparar("base", passo_horas=24, dia_inicial=2)
    snap = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[0], cfg.corte)  # dia 2: nada maduro
    dec = RegraMargem().decidir(snap)
    assert dec.propostas and all(p.acao is Acao.INSUFICIENTE for p in dec.propostas)
    assert all("imatura" in " ".join(p.evidencia_dict()["recusas"]) or p.evidencia_dict()["n_dias"] == 0
               for p in dec.propostas)


def test_guardiao_rebaixa_corte_de_campanha_nova_a_alerta():
    fs, cortes, cfg = preparar("campanha_nova", passo_horas=24, dia_inicial=9)
    fi = FluxoIndexado(fs.observacoes)
    nova = EntidadeCampanha("1234567890", "24000000001")
    vistos_corte = vistos_alerta = 0
    for t in cortes:
        snap = construir_snapshot(fi, t, cfg.corte)
        cru = {p.entidade: p for p in regra_margem_imatura().decidir(snap).propostas}
        guard = {p.entidade: p for p in Guardiao72h(regra_margem_imatura()).decidir(snap).propostas}
        if cru[nova].acao in (Acao.PAUSAR, Acao.REDUZIR_VERBA):
            vistos_corte += 1
            g = guard[nova]
            if g.evidencia_dict()["dias_com_dado_maduro"] < 3:
                vistos_alerta += 1
                assert g.acao is Acao.ALERTA and g.fator_bps == BPS
                assert g.evidencia_dict()["acao_original"] in ("pausar", "reduzir_verba")
        for e, p in guard.items():  # campanhas maduras passam intactas
            if e != nova:
                assert (p.acao, p.fator_bps) == (cru[e].acao, cru[e].fator_bps)
    assert vistos_corte >= 1 and vistos_alerta >= 1


def test_guardiao_nunca_propoe_corte_em_campanha_nova_em_todos_os_cortes():
    fs, cortes, cfg = preparar("campanha_nova", passo_horas=6, dia_inicial=6)
    fi = FluxoIndexado(fs.observacoes)
    g = Guardiao72h(regra_margem_imatura())
    for t in cortes:
        snap = construir_snapshot(fi, t, cfg.corte)
        for p in g.decidir(snap).propostas:
            ev = p.evidencia_dict()
            idade = ev["horas_desde_primeiro_custo"]
            if idade is None or idade < 72 or ev["dias_com_dado_maduro"] < 3:
                assert p.acao not in (Acao.PAUSAR, Acao.REDUZIR_VERBA)


def test_baselines_herdadas_reaproveitam_o_replay_v0(snap_base):
    snap, cfg = snap_base
    eq = equal().decidir(snap)
    fatores = [p.fator_bps for p in eq.propostas if p.acao is not Acao.INSUFICIENTE]
    assert len(fatores) >= 2 and len(set(fatores)) > 1  # igualar verbas desiguais muda fatores
    total_antes = sum(p.evidencia_dict()["verba_proxy_micros"] for p in eq.propostas if p.acao is not Acao.INSUFICIENTE)
    total_depois = sum(p.evidencia_dict()["verba_proposta_micros"] for p in eq.propostas if p.acao is not Acao.INSUFICIENTE)
    assert total_antes == total_depois  # orçamento fecha (validar_decisao herdado)
    gr = greedy_conservador().decidir(snap)
    assert gr.propostas and "herdada:greedy_conservador" in gr.propostas[0].versao_politica


def test_manter_e_cega_a_dados(snap_base):
    snap, _ = snap_base
    dec = Manter().decidir(snap)
    assert all(p.acao is Acao.MANTER and p.fator_bps == BPS for p in dec.propostas)


def test_dia_corte_e_janela(snap_base):
    snap, _ = snap_base
    assert max(f.dia for f in snap.fatos) <= snap.dia_corte
    assert min(f.dia for f in snap.fatos) >= snap.dia_corte - timedelta(days=snap.config.janela_dias)
