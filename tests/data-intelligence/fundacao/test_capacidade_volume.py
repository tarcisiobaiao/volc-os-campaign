"""Modelo de volume: contagens exatas, limites do dedup, escala linear, política e GTM."""
from __future__ import annotations

import math

import pytest

from volc_dil.fundacao.capacidade.volume import (
    Escala,
    Job,
    ParametroInvalido,
    PerfilBytes,
    PerfilGTM,
    Politica,
    calcular_cenario,
    calcular_gtm,
    calcular_job,
)

ESC = Escala(contas=2, campanhas_por_conta=5, grupos_por_campanha=4, anuncios_por_grupo=3, keywords_por_conta=40,
             termos_dia_por_campanha=60)
PERFIL = PerfilBytes(formato="longo", heap_por_observacao=170, indices_por_observacao=100,
                     payload_linha_em_lote={"campanha": 120, "termo": 200},
                     payload_linha_individual={"campanha": 730, "termo": 1130}, manifesto_por_lote=250,
                     rollup_por_linha=300, sobrecarga_particao_bytes=100_000)


def _d0(cron="7 6-23 * * *", lam=10.0, mut=1.0, **kw):
    return Job(nome="d0", fonte="google_ads", base="campanha", cron=cron, janela=(0, 0), metricas_por_linha=8,
               lambda_mudanca_h=lam, fracao_mutavel=mut, **kw)


def test_contagens_exatas_do_job_d0():
    r = calcular_job(_d0(), ESC)
    assert r.execucoes_dia == 18
    assert r.linhas_logicas_novas_dia == 10  # 2 contas × 5 campanhas
    assert r.linhas_lidas_dia == 10 * 18
    assert r.chamadas_dia == 2 * 18  # 1 searchStream por conta por execução


def test_janela_rolante_multiplica_leitura():
    j = Job(nome="termos", fonte="google_ads", base="termo_dia", cron="23 */4 * * *", janela=(1, 7),
            metricas_por_linha=5, p_revisao_fechado=0.0, tipo_payload="termo")
    r = calcular_job(j, ESC)
    assert r.linhas_lidas_dia == 2 * 5 * 60 * 7 * 6
    assert r.versoes_por_linha == 1.0  # nada muda em dia fechado → 1 versão; 41 de 42 leituras redundantes
    assert r.fracao_redundante == pytest.approx(41 / 42)
    assert r.lotes_distintos_dia == pytest.approx(2 * 1)  # só o 1º lote do dia (janela deslizou) é novo


def test_limites_do_dedup_d0():
    assert calcular_job(_d0(lam=0.0), ESC).versoes_por_linha == 1.0
    assert calcular_job(_d0(lam=1e6), ESC).versoes_por_linha == pytest.approx(18.0)
    assert calcular_job(_d0(lam=1e6, mut=0.2), ESC).versoes_por_linha == pytest.approx(1 + 17 * 0.2)


def test_cadencia_curta_le_mais_mas_versoes_limitadas_pelos_eventos():
    lam = 2.0
    v = {}
    for cron in ("0 * * * *", "*/15 * * * *", "*/10 * * * *"):
        v[cron] = calcular_job(_d0(cron=cron, lam=lam), ESC)
    assert v["*/10 * * * *"].linhas_lidas_dia == 6 * v["0 * * * *"].linhas_lidas_dia
    assert v["0 * * * *"].versoes_por_linha < v["*/15 * * * *"].versoes_por_linha < v["*/10 * * * *"].versoes_por_linha
    # nº de versões distintas nunca passa de 1 + nº esperado de eventos no dia (Poisson)
    assert v["*/10 * * * *"].versoes_por_linha <= 1 + lam * 24
    assert v["*/10 * * * *"].fracao_redundante > v["0 * * * *"].fracao_redundante


def test_perfil_horario_uniforme_equivale_a_constante_e_noite_reduz_mudanca():
    uniforme = tuple([1.0] * 24)
    a = calcular_job(_d0(cron="*/10 * * * *", lam=3.0), ESC)
    b = calcular_job(_d0(cron="*/10 * * * *", lam=3.0, perfil_horario=uniforme), ESC)
    assert a.versoes_por_linha == pytest.approx(b.versoes_por_linha)
    dia = tuple([0.0] * 6 + [24 / 18] * 18)  # nada de madrugada
    c = calcular_job(_d0(cron="*/10 * * * *", lam=3.0, perfil_horario=dia), ESC)
    assert c.versoes_por_linha < a.versoes_por_linha
    with pytest.raises(ParametroInvalido):
        _d0(perfil_horario=tuple([2.0] * 24))


def test_dedup_por_lote_rende_menos_que_por_linha_em_janela_grande():
    j = Job(nome="termos", fonte="google_ads", base="termo_dia", cron="23 */4 * * *", janela=(1, 7),
            metricas_por_linha=5, p_revisao_fechado=0.01, tipo_payload="termo")
    r = calcular_job(j, ESC)
    # 2.100 linhas por lote: P(lote igual) = 0,99^2100 ≈ 0 → quase todo lote é "novo"
    assert r.lotes_distintos_dia / r.lotes_dia > 0.99
    assert r.linhas_distintas_dia / r.linhas_lidas_dia < 0.2


def test_escala_linear_em_contas():
    jobs = [_d0()]
    pol = Politica(dedup_observacao=True, dedup_payload="linha")
    r1 = calcular_cenario(jobs, ESC, PERFIL, pol)
    r10 = calcular_cenario(jobs, ESC.crescer(10), PERFIL, pol)
    assert r10.observacoes_dia == pytest.approx(10 * r1.observacoes_dia)
    assert r10.chamadas_dia == pytest.approx(10 * r1.chamadas_dia)
    assert r10.bytes_dia == pytest.approx(10 * r1.bytes_dia)


def test_politicas_ordenam_o_custo():
    jobs = [_d0(lam=0.5), Job(nome="t", fonte="google_ads", base="termo_dia", cron="23 */4 * * *", janela=(1, 7),
                              metricas_por_linha=5, p_revisao_fechado=0.02, tipo_payload="termo")]
    cru = calcular_cenario(jobs, ESC, PERFIL, Politica(dedup_observacao=False, dedup_payload="nenhum"))
    dd = calcular_cenario(jobs, ESC, PERFIL, Politica(dedup_observacao=True, dedup_payload="linha"))
    sem_idx = calcular_cenario(jobs, ESC, PERFIL, Politica(dedup_observacao=True, dedup_payload="linha", com_indices=False))
    assert dd.bytes_dia < cru.bytes_dia
    assert sem_idx.bytes_indices_dia == 0 and sem_idx.bytes_dia < dd.bytes_dia
    ret = calcular_cenario(jobs, ESC, PERFIL, Politica(dedup_observacao=True, dedup_payload="linha",
                                                       retencao_bruto_dias=396, rollup_diario=True))
    assert ret.acumulado_gb["30d"] > dd.acumulado_gb["30d"]  # rollup soma no começo
    bruto_3a = dd.acumulado_gb["3a"]
    assert ret.acumulado_gb["3a"] < bruto_3a  # e economiza no horizonte longo
    assert dd.acumulado_gb["3a"] == pytest.approx(dd.bytes_dia * 1096 / 1024**3)


def test_formato_longo_multiplica_observacoes_por_metrica():
    largo = PerfilBytes(**{**PERFIL.__dict__, "formato": "largo"})
    pol = Politica(dedup_observacao=False, dedup_payload="nenhum")
    a = calcular_cenario([_d0()], ESC, PERFIL, pol)
    b = calcular_cenario([_d0()], ESC, largo, pol)
    assert a.observacoes_dia == 8 * b.observacoes_dia


def test_particao_soma_sobrecarga_por_mes_e_fator_proporcional():
    pol = Politica(dedup_observacao=True, dedup_payload="linha")
    a = calcular_cenario([_d0()], ESC, PERFIL, pol)
    b = calcular_cenario([_d0()], ESC, PERFIL, Politica(dedup_observacao=True, dedup_payload="linha", particao_mensal=True))
    assert (b.acumulado_gb["3a"] - a.acumulado_gb["3a"]) * 1024**3 == pytest.approx(37 * 100_000)
    p2 = PerfilBytes(**{**PERFIL.__dict__, "fator_particao": 1.035})
    c = calcular_cenario([_d0()], ESC, p2, Politica(dedup_observacao=True, dedup_payload="linha", particao_mensal=True))
    extra = (a.bytes_observacao_dia + a.bytes_indices_dia) * 0.035
    assert c.bytes_dia - a.bytes_dia == pytest.approx(extra)


@pytest.mark.parametrize("kw", [dict(janela=(2, 1)), dict(fracao_ativa=1.5), dict(lambda_mudanca_h=-1),
                                dict(cron="7 6-23 * * 1")])
def test_job_invalido(kw):
    base = dict(nome="x", fonte="g", base="campanha", cron="0 * * * *", janela=(0, 0), metricas_por_linha=1)
    with pytest.raises(Exception):
        Job(**{**base, **kw})


def test_retencao_sem_rollup_e_perda_de_dado():
    with pytest.raises(ParametroInvalido):
        Politica(dedup_observacao=True, dedup_payload="linha", retencao_bruto_dias=90)


@pytest.mark.parametrize("e, t, esperado", [(20, 5, 1), (5, 60, 5), (60, 300, 30), (100, 50, 5), (0, 30, 0)])
def test_gtm_lote_por_contagem_ou_tempo(e, t, esperado):
    r = calcular_gtm(PerfilGTM(sessoes_dia=1000, eventos_por_sessao=e, duracao_sessao_s=t))
    assert r["requisicoes_por_sessao"] == esperado
    assert r["eventos_dia"] == 1000 * e
    assert r["requisicoes_dia"] == 1000 * esperado
    assert math.isclose(r["acumulado_gb"]["30d"], r["gb_dia"] * 30)


def test_linha_em_lote_deduplica_como_linha_e_comprime_como_lote():
    j = Job(nome="t", fonte="google_ads", base="termo_dia", cron="23 */4 * * *", janela=(1, 7), metricas_por_linha=5,
            p_revisao_fechado=0.02, tipo_payload="termo")
    r = {m: calcular_cenario([j], ESC, PERFIL, Politica(dedup_observacao=True, dedup_payload=m))
         for m in ("nenhum", "lote", "linha", "linha_em_lote")}
    assert r["linha_em_lote"].linhas_payload_dia == r["linha"].linhas_payload_dia
    assert r["linha_em_lote"].bytes_payload_dia < r["linha"].bytes_payload_dia < r["nenhum"].bytes_payload_dia
    assert r["lote"].bytes_payload_dia == pytest.approx(r["nenhum"].bytes_payload_dia, rel=0.05)
