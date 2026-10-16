"""Simulator Lab — propriedades estatísticas básicas e calibração de FORMA (não de números)."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from volc_dil.fundacao.simulador import FONTES_PARAMETROS, ParametrosMundo, cenario, gerar_mundo, verificar_forma

SEED = 20261016


@lru_cache(maxsize=None)
def _mundo(nome: str = "estavel", seed: int = SEED):
    return gerar_mundo(cenario(nome).mundo, seed)  # tamanho do catálogo: 50 × 30 × 24


def test_forma_do_mundo_default_dentro_das_faixas_declaradas():
    for seed in (SEED, SEED + 1, SEED + 2):
        res = verificar_forma(_mundo("estavel", seed))
        assert all(v["ok"] for v in res.values()), (seed, res)


def test_toda_origem_de_parametro_declarada():
    classes = {c for c, _ in FONTES_PARAMETROS.values()}
    assert classes <= {"forma_real", "documentacao_fonte", "literatura_nao_verificada", "arbitrario"}
    assert "arbitrario" in classes and "forma_real" in classes
    assert all(fonte for _, fonte in FONTES_PARAMETROS.values())


def test_ctr_medio_na_faixa_do_parametro():
    m = _mundo()
    alvo = ParametrosMundo().ctr_media
    ctr = m.diario("cliques").sum() / m.diario("impressoes").sum()
    assert 0.7 * alvo < ctr < 1.3 * alvo


def test_sazonalidade_diaria_detectavel():
    m = _mundo()
    por_hora = m.por_hora("impressoes").reshape(m.C, m.D, 24).sum(axis=(0, 1))
    assert por_hora[21] > 2.0 * por_hora[4]
    assert int(np.argmax(por_hora)) in range(18, 24)
    rpm_h = m.por_hora("receita_micros").reshape(m.C, m.D, 24).sum(axis=(0, 1)) / \
        m.por_hora("pageviews").reshape(m.C, m.D, 24).sum(axis=(0, 1))
    assert rpm_h[20] > rpm_h[8]


def test_sazonalidade_semanal_detectavel_por_regressao():
    for nome, esperado in (("estavel", 0.90), ("sazonal_fim_de_semana", 0.60)):
        m = _mundo(nome)
        imp = m.diario("impressoes").sum(axis=0).astype(float)
        fds = np.array([d.weekday() >= 5 for d in m.dias])
        coef = np.exp(np.log(imp[fds]).mean() - np.log(imp[~fds]).mean())
        assert abs(coef - esperado) < 0.08, (nome, coef)


def test_heterocedasticidade_variancia_cresce_com_a_media():
    m = _mundo()
    imp = m.diario("impressoes").astype(float)
    ativos = imp.min(axis=1) > 0
    media, var = imp[ativos].mean(axis=1), imp[ativos].var(axis=1)
    inclinacao = np.polyfit(np.log(media), np.log(var), 1)[0]
    assert inclinacao > 1.2  # Poisson puro daria 1; sobredispersão + choques dão mais


def test_cv_da_receita_cai_com_pageviews():
    m = _mundo()
    rec = m.horario("receita_micros").astype(float).ravel()
    pv = m.horario("pageviews").astype(float).ravel()
    rpm_dia_hora = rec / np.maximum(pv, 1)
    pequeno = (pv >= 1) & (pv <= 3)
    grande = pv >= 30
    cv = lambda x: x.std() / x.mean()  # noqa: E731
    assert cv(rpm_dia_hora[pequeno]) > cv(rpm_dia_hora[grande])


def test_orcamento_satura_parte_das_campanhas():
    m = _mundo()
    theta = m.flags["theta"]
    limitadas = (theta < 0.999).mean()
    assert 0.05 < limitadas < 0.9
    # pacing em expectativa: gasto diário realizado raramente passa muito do orçamento
    orc = np.array([c.orcamento_base_micros for c in m.campanhas])
    assert (m.diario("custo_bruto_micros") > 1.3 * orc[:, None]).mean() < 0.02


def test_dinheiro_em_micros_inteiros():
    m = _mundo()
    for nome in ("custo_bruto_micros", "credito_micros", "custo_final_micros", "receita_micros"):
        a = m.horario(nome)
        assert a.dtype == np.int64 and (a >= 0).all()
    assert all(isinstance(c.orcamento_base_micros, int) and c.orcamento_base_micros % 10_000 == 0 for c in m.campanhas)
