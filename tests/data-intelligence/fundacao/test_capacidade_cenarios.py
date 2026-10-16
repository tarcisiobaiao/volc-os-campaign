"""Cenários e quotas: o modelo reproduz as contagens reais dos coletores canônicos (shadow, 15/10)."""
from __future__ import annotations

import pytest

from volc_dil.fundacao.capacidade import cenarios as cen
from volc_dil.fundacao.capacidade import quotas
from volc_dil.fundacao.capacidade.volume import calcular_job


def _job(nome, jobs=None):
    return next(j for j in (jobs or cen.jobs_vertical_completa()) if j.nome == nome)


def test_agendas_iguais_as_do_repositorio():
    crons = {j.nome: j.cron for j in cen.jobs_atuais()}
    assert crons == {"gads_campanha_d0": "7 6-23 * * *", "gads_campanha_d1": "17 6,14 * * *",
                     "gads_termos": "23 */4 * * *", "gads_keywords": "23 */4 * * *",
                     "joinads_intraday": "15 6-22/2 * * *", "joinads_d1": "20 6 * * *"}


def test_modelo_reproduz_contagens_reais_por_execucao():
    e = cen.ESCALA_ATUAL
    d0 = calcular_job(_job("gads_campanha_d0"), e)
    assert d0.linhas_lidas_dia / d0.execucoes_dia == pytest.approx(5)  # canário 58046: 5 observações
    termos = calcular_job(_job("gads_termos"), e)
    kws = calcular_job(_job("gads_keywords"), e)
    por_run = (termos.linhas_lidas_dia + kws.linhas_lidas_dia) / termos.execucoes_dia
    assert por_run == pytest.approx(2242)  # 2.228 termos + 14 keyword-dia por run
    assert termos.lotes_dia / termos.execucoes_dia + kws.lotes_dia / kws.execucoes_dia == 2  # 2 lotes por run
    assert termos.chamadas_dia / termos.execucoes_dia + kws.chamadas_dia / kws.execucoes_dia == 3  # + listagem de contas
    assert d0.chamadas_dia / d0.execucoes_dia == 5  # customer_client + 4 GAQL (J:P/collector-inventory.json:111-117)
    jd1 = calcular_job(_job("joinads_d1"), e)
    assert jd1.linhas_lidas_dia == pytest.approx(209) and jd1.chamadas_dia == 64  # run 58097


def test_perfil_horario_real_tem_media_1_e_madrugada_baixa():
    p = cen.PERFIL_HORARIO_GADS
    assert sum(p) / 24 == pytest.approx(1.0)
    assert sum(cen.FATIA_IMPRESSOES_POR_HORA_D30) == 100_000
    assert sum(cen.FATIA_IMPRESSOES_POR_HORA_D30[:6]) / 100_000 == pytest.approx(0.0501, abs=1e-4)
    assert cen.LAMBDA_CAMPANHA_ATIVA_H == pytest.approx(17.32, abs=0.01)


def test_cenarios_nao_versionam_identificador_real():
    import inspect
    import re

    fonte = inspect.getsource(cen)
    assert not re.search(r"\b\d{10,11}\b", fonte)  # customer_id / campaign id do Google Ads
    for proibido in ("Crédito Up", "Credito Up", "GTM-", "R$"):
        assert proibido not in fonte


def test_cadencia_so_muda_jobs_intraday():
    base = cen.jobs_vertical_completa()
    novo = cen.aplicar_cadencia(base, "10min")
    for a, b in zip(base, novo):
        if a.nome in cen.INTRADAY:
            assert b.cron == "*/10 * * * *"
        else:
            assert b.cron == a.cron


def test_quota_basic_documentada_e_consumo_atual():
    lim = quotas.limite("operacoes_dia_token_basic")
    assert lim.valor == 15000 and "comum.md:174" in lim.evidencia
    assert quotas.limite("nivel_de_acesso_do_token_volc").valor is None  # não confirmado: não inventar
    rs = [calcular_job(j, cen.ESCALA_ATUAL) for j in cen.jobs_atuais()]
    q = quotas.avaliar_google_ads(rs)
    # R1 F7: D0/D-1 fazem customer_client (1 por execução) + 4 GAQL por conta; termos lista contas + 1; keywords 1
    assert q["operacoes_dia"] == (18 * 4 + 2 * 4 + 6 + 6) + (18 + 2 + 6)
    assert quotas.operacoes_google_ads_linear(cen.jobs_atuais(), cen.ESCALA_ATUAL) == (92, 26)
    assert quotas.contas_maximas(cen.jobs_atuais(), cen.ESCALA_ATUAL, 15000) == 162
    d0_10min = cen.aplicar_cadencia(cen.jobs_atuais(), "10min")
    assert quotas.contas_maximas(d0_10min, cen.ESCALA_ATUAL, 15000) == 24
    assert all(x.estado in {"documentado no repo com fonte oficial citada", "observado no repo", "não confirmado"}
               for x in quotas.LIMITES)
    assert all(x.valor is None for x in quotas.LIMITES if x.estado == "não confirmado")


def test_termos_1x_dia_le_seis_vezes_menos():
    a = [calcular_job(j, cen.ESCALA_ATUAL) for j in cen.jobs_atuais() if j.nome == "gads_termos"][0]
    b = [calcular_job(j, cen.ESCALA_ATUAL) for j in cen.termos_uma_vez_ao_dia(cen.jobs_atuais()) if j.nome == "gads_termos"][0]
    assert a.linhas_lidas_dia == pytest.approx(6 * b.linhas_lidas_dia)
