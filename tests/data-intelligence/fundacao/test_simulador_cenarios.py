"""Simulator Lab — cada cenário nomeado produz o fenômeno que promete; cada adversarial produz a armadilha."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

import numpy as np
import pytest

from volc_dil.fundacao.simulador import (
    ADVERSARIAIS,
    CATALOGO,
    NOMES,
    cenario,
    iso,
    simular,
    soma_ingenua,
    somar_por_moeda,
    visao_as_of,
)

SEED = 20261016
FIM = "9999-12-31T00:00:00+00:00"

OBRIGATORIOS = {"estavel", "campanha_nova_aprendendo", "atraso_receita_longo", "restatement_custo", "fonte_fora_do_ar",
                "outlier_bot", "quebra_regime_rpm", "mudanca_orcamento", "sazonal_fim_de_semana", "escala_10x",
                "vazamento_tentado", "zero_falso", "moeda_misturada", "identidade_trocada"}
PRODUCAO = {"sensor_sem_campanha", "zero_sintetizado_coletor", "dedup_por_segundo", "gatilho_legado_joinads",
            "custo_d0_multiversao", "execucao_presa"}


@lru_cache(maxsize=None)
def _sim(nome: str, n: int = 10, d: int = 21):
    return simular(nome, SEED, n_campanhas=n, n_dias=d)


def test_catalogo_completo_e_documentado():
    assert OBRIGATORIOS | PRODUCAO == set(NOMES)
    assert {"vazamento_tentado", "zero_falso", "moeda_misturada", "identidade_trocada"} <= set(ADVERSARIAIS)
    for nome, e in CATALOGO.items():
        assert e.descricao and e.exercita, nome
        if e.adversarial:
            assert e.armadilhas, nome
        if nome in PRODUCAO:
            assert "RECIBO-LEITURAS-20261016" in e.evidencia, nome
    assert cenario("escala_10x").mundo.n_campanhas == 10 * cenario("estavel").mundo.n_campanhas
    with pytest.raises(KeyError):
        cenario("nao_existe")


def test_estavel_sem_novas_sem_bot_sem_quebra():
    m = _sim("estavel").mundo
    assert not any(c.nova for c in m.campanhas)
    assert m.horario("cliques_bot").sum() == 0 and not m.flags["pico_rpm_hora"].any()
    assert (m.flags["fator_rpm"] == 1).all() and (m.flags["fator_cpc"] == 1).all()


def test_campanha_nova_aprendendo():
    sim = _sim("campanha_nova_aprendendo", 30, 28)
    m = sim.mundo
    novas = [c for c in m.campanhas if c.nova and c.inicio_h + 24 * 12 < m.T]
    assert len(novas) >= 5
    custo, cliq = m.por_hora("custo_bruto_micros"), m.por_hora("cliques")
    razoes, rampa = [], []
    ativo = m.flags["ativo"]
    imp = m.por_hora("impressoes")
    for c in novas:
        ini = max(0, c.inicio_h)
        cedo = slice(ini, ini + 48)
        tarde = slice(ini + 24 * 10, min(m.T, ini + 24 * 12))
        if cliq[c.idx, cedo].sum() > 10 and cliq[c.idx, tarde].sum() > 10:
            razoes.append((custo[c.idx, cedo].sum() / cliq[c.idx, cedo].sum())
                          / (custo[c.idx, tarde].sum() / cliq[c.idx, tarde].sum()))
            a_cedo, a_tarde = ativo[c.idx, cedo], ativo[c.idx, tarde]
            if a_cedo.any() and a_tarde.any():
                rampa.append(imp[c.idx, cedo][a_cedo].mean() / imp[c.idx, tarde][a_tarde].mean())
    assert razoes and np.median(razoes) > 1.2  # CPC alto no aprendizado
    assert rampa and np.median(rampa) < 0.85  # volume em rampa (ruído diário pode inverter um caso isolado)
    # antes do lançamento: nenhum registro (ausência de entidade, não zero)
    ids_antes = {(c.id, d) for c in novas for d in range(max(0, c.inicio_h) // 24)}
    dia = {iso(m.instante_local(i, 0)): i for i in range(m.D)}
    for r in sim.leituras.registros:
        assert (r.entidade, dia.get(r.janela_inicio)) not in ids_antes or r.entidade_tipo != "campaign"


def test_atraso_receita_longo_estimativa_inicial_baixa():
    sim = _sim("atraso_receita_longo")
    prim, fim = {}, {}
    for r in sim.leituras.registros:
        if r.fonte == "joinads" and r.metrica == "revenue" and r.valor is not None and r.entidade_tipo == "campaign":
            k = (r.entidade, r.janela_inicio)
            if r.tipo_leitura == "d1":
                prim[k] = r.valor
            if r.maturidade == "final":
                fim[k] = r.valor
    comuns = [k for k in prim if k in fim and fim[k] > 0]
    assert sum(prim[k] for k in comuns) / sum(fim[k] for k in comuns) < 0.85


def test_restatement_custo_d1_supera_o_fechado():
    sim = _sim("restatement_custo")
    d1 = sum(r.valor for r in sim.leituras.registros if r.fonte == "google_ads" and r.metrica == "cost"
             and r.tipo_leitura == "d1" and r.valor is not None)
    fech = sum(r.valor for r in visao_as_of(sim.leituras.registros, FIM).values()
               if r.fonte == "google_ads" and r.metrica == "cost" and r.entidade_tipo == "campaign")
    assert d1 > 1.05 * fech


def test_fonte_fora_do_ar_gera_unavailable_e_recuperacao():
    L = _sim("fonte_fora_do_ar").leituras
    fora = [r for r in L.registros if r.status == "unavailable"]
    assert {r.fonte for r in fora} >= {"joinads", "google_ads"}
    assert all(r.valor is None for r in fora)
    rec = L.com_armadilha("recuperacao_tardia")
    assert rec and all(r.status in ("late", "zero_confirmed") for r in rec)
    assert any(x["status"] == "failed" for x in L.execucoes)


def test_outlier_bot_custa_sem_render():
    m = _sim("outlier_bot").mundo
    bot = m.flags["bot_hora"]
    assert bot.sum() >= 3
    pv, cl = m.por_hora("pageviews"), m.por_hora("cliques")
    assert pv[bot].sum() / cl[bot].sum() < 0.6 * pv[~bot].sum() / max(1, cl[~bot].sum())
    assert m.horario("cliques_bot_detectados").sum() > 0
    assert (m.diario("custo_bruto_micros") >= m.diario("custo_final_micros")).all()
    assert m.flags["pico_rpm_hora"].sum() >= 1


def test_quebra_regime_rpm_detectavel():
    m = _sim("quebra_regime_rpm", 20, 28).mundo
    rpm = m.diario("receita_micros") / np.maximum(m.diario("pageviews"), 1)
    sel = (m.flags["fator_rpm"] < 1).any(axis=1)
    assert sel.sum() >= 10
    meio = 14
    antes, depois = rpm[sel, :meio].mean(), rpm[sel, meio + 1:].mean()
    assert depois / antes < 0.75
    nao = ~sel
    assert 0.85 < rpm[nao, meio + 1:].mean() / rpm[nao, :meio].mean() < 1.15
    assert (m.flags["fator_cpc"] > 1).any()


def test_mudanca_orcamento_e_saturacao():
    m = _sim("mudanca_orcamento", 20, 30).mundo
    orc = m.flags["orcamento_hora_micros"]
    dobrou = (orc[:, -1] > orc[:, 0] * 1.5)
    assert dobrou.any()
    custo = m.diario("custo_bruto_micros")
    t1 = 10  # mudança em 1/3 do período (dia 10) às 14h
    assert custo[dobrou, t1 + 1:t1 + 9].mean() > 1.3 * custo[dobrou, :t1].mean()
    orc_dia = orc.reshape(m.C, m.D, 24).max(axis=2)
    assert (custo <= 2 * orc_dia).all()  # regra de 2× do orçamento diário nunca violada
    theta = m.flags["theta"]
    assert (theta < 0.999).mean() > 0.3  # orçamento aperta (saturação)
    # mudança intradiária: o orçamento muda dentro do dia da mudança
    assert (orc.reshape(m.C, m.D, 24)[dobrou, t1, 0] != orc.reshape(m.C, m.D, 24)[dobrou, t1, 23]).all()


def test_sazonal_fim_de_semana():
    for nome, faixa in (("sazonal_fim_de_semana", (0.0, 0.7)), ("estavel", (0.8, 1.0))):
        m = _sim(nome).mundo
        imp = m.diario("impressoes").sum(axis=0)
        fds = np.array([d.weekday() >= 5 for d in m.dias])
        r = imp[fds].mean() / imp[~fds].mean()
        assert faixa[0] < r < faixa[1], (nome, r)


def test_vazamento_tentado_observed_at_ve_o_futuro():
    sim = _sim("vazamento_tentado")
    regs = sim.leituras.registros
    m = sim.mundo
    as_of = iso(m.instante_local(10, 1))  # 01:00 do dia 10
    certo = visao_as_of(regs, as_of)
    errado = visao_as_of(regs, as_of, relogio="observed_at")
    futuros = [r for r in errado.values() if r.available_at > as_of]
    assert futuros  # quem filtra por observed_at usa dado que ainda não existia
    diverg = [k for k, r in errado.items() if k in certo and certo[k].valor != r.valor]
    assert diverg
    assert all("retrodatado" in sim.leituras.gabarito[r.obs_id].armadilhas for r in futuros)


def test_zero_falso_existem_zeros_que_a_verdade_diz_ausentes():
    sim = _sim("zero_falso")
    falsos = sim.leituras.com_armadilha("zero_falso")
    assert falsos
    assert all(r.valor == 0 and r.status in ("observed", "partial") and r.motivo is None for r in falsos)
    positivos = [r for r in falsos if (sim.leituras.gabarito[r.obs_id].valor_verdade_cobertura or 0) > 0]
    assert len(positivos) > 0.5 * len(falsos)
    assert not any(r.status in ("missing", "unavailable") for r in sim.leituras.registros)  # o null sumiu


def test_moeda_misturada_soma_ingenua_mistura_grandezas():
    sim = _sim("moeda_misturada")
    v = visao_as_of(sim.leituras.registros, FIM)
    por_moeda = somar_por_moeda(v, "revenue")
    assert set(por_moeda) == {"BRL", "USD"}
    ingenua = soma_ingenua(sim.leituras.registros, "revenue")
    assert ingenua != por_moeda["BRL"] and ingenua != por_moeda["USD"]


def test_identidade_trocada_post_parece_campanha():
    sim = _sim("identidade_trocada")
    ids = {c.id for c in sim.mundo.campanhas}
    trocados = [r for r in sim.leituras.registros if r.custom_key_efetiva != r.custom_key_solicitada
                and r.fonte == "joinads"]
    assert trocados and any(r.entidade in ids for r in trocados)
    certo = visao_as_of(sim.leituras.registros, FIM)
    ingenuo = visao_as_of(sim.leituras.registros, FIM, exigir_custom_key=False)
    contaminado = 0
    for r in ingenuo.values():
        if r.entidade_tipo == "post" and r.entidade in ids:
            contaminado += 1
    assert contaminado > 0
    assert all(r.custom_key_efetiva == r.custom_key_solicitada for r in certo.values())


def test_sensor_sem_campanha():
    sim = _sim("sensor_sem_campanha")
    regs = [r for r in sim.leituras.registros if r.fonte == "site_analytics"]
    por_campanha = [r for r in regs if r.entidade_tipo == "campaign"]
    agregados = [r for r in regs if r.entidade_tipo == "utm_source_medium"]
    assert agregados and len(por_campanha) < 0.1 * len(agregados) * 10
    assert all(r.entidade == "google/cpc" and dict(r.dimensoes)["utm_source"] == "google" for r in agregados)
    # sessões totais preservadas (só a chave de campanha some)
    tot_obs = sum(r.valor for r in regs if r.metrica == "sessions" and r.valor is not None
                  and "duplicata" not in sim.leituras.gabarito[r.obs_id].armadilhas)
    assert abs(tot_obs - sim.mundo.diario("sessoes").sum()) <= 0.05 * sim.mundo.diario("sessoes").sum()


def test_zero_sintetizado_indistinguivel_do_confirmado():
    sim = _sim("zero_sintetizado_coletor")
    L = sim.leituras
    finais = [r for r in L.registros if r.fonte == "google_ads" and r.metrica == "cost" and r.tipo_leitura == "backfill"]
    zeros = [r for r in finais if r.valor == 0]
    assert len(zeros) / len(finais) > 0.6  # forma do recibo: 88/110 linhas campaign_day zeradas
    sinteticos = [r for r in zeros if "zero_sintetizado" in L.gabarito[r.obs_id].armadilhas]
    legitimos = [r for r in L.registros if r.fonte == "google_ads" and r.status == "zero_confirmed"
                 and "zero_sintetizado" not in L.gabarito[r.obs_id].armadilhas]
    assert sinteticos
    assert {r.status for r in sinteticos} == {"zero_confirmed"}
    assert all(r.motivo is None for r in sinteticos)  # nada no registro denuncia o zero inventado
    if legitimos:
        assert {r.status for r in legitimos} == {"zero_confirmed"}
    perdidos = [r for r in L.registros if "zero_sintetizado" in L.gabarito[r.obs_id].armadilhas
                and (L.gabarito[r.obs_id].valor_verdade_final or 0) > 0]
    assert perdidos  # inclusive campanha ativa com linha ausente vira zero


def test_dedup_por_segundo_subconta_mais_com_bot():
    sim = _sim("dedup_por_segundo")
    L = sim.leituras
    m = sim.mundo
    dia = {iso(m.instante_local(i, 0)): i for i in range(m.D)}
    idx = {c.id: c.idx for c in m.campanhas}
    bot_dia = m.flags["bot_hora"].reshape(m.C, m.D, 24).any(axis=2)
    perdas = defaultdict(list)
    for r in L.registros:
        if r.fonte == "site_analytics" and r.metrica == "pageviews" and r.valor is not None:
            g = L.gabarito[r.obs_id]
            assert r.valor <= g.valor_verdade_final
            perdas[bool(bot_dia[idx[r.entidade], dia[r.janela_inicio]])].append(1 - r.valor / max(1, g.valor_verdade_final))
    assert L.com_armadilha("dedup_por_segundo")
    assert perdas[True] and np.mean(perdas[True]) > 1.5 * np.mean(perdas[False])


def test_gatilho_legado_ultimo_dominio_e_custo_zero():
    sim = _sim("gatilho_legado_joinads")
    v = visao_as_of(sim.leituras.registros, FIM)
    leg = sum(r.valor for r in v.values() if r.fonte == "legado_daily_metrics" and r.metrica == "revenue")
    join = sum(r.valor for r in v.values() if r.fonte == "joinads" and r.metrica == "revenue" and r.entidade_tipo == "campaign")
    assert leg < 0.6 * join  # só o último de 3 domínios sobrevive
    zeros = sim.leituras.com_armadilha("custo_zero_inserido")
    assert zeros and all(r.valor == 0 and r.status in ("zero_confirmed", "partial") for r in zeros)


def test_custo_d0_multiversao():
    sim = _sim("custo_d0_multiversao")
    versoes = defaultdict(set)
    for r in sim.leituras.registros:
        if r.fonte == "google_ads" and r.metrica == "cost" and r.tipo_leitura == "intradia" and r.valor is not None:
            versoes[(r.entidade, r.janela_inicio)].add(r.valor)
    assert max(len(s) for s in versoes.values()) >= 12  # recibo: até 14 valores distintos em 16 runs


def test_execucao_presa_sem_entrega_e_recuperada():
    L = _sim("execucao_presa").leituras
    presos = [x for x in L.execucoes if x["status"] == "running"]
    assert presos
    ids = {x["run_id"] for x in presos}
    assert not any(r.run_id in ids for r in L.registros)
    assert L.com_armadilha("recuperacao_tardia")
