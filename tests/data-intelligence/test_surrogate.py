"""Contraprovas do portão de viabilidade do surrogate (Fase 6)."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np

from volc_dil.surrogate import Feature, LinhaRotulada, ParametrosPortao, Veredito, avaliar_viabilidade
from volc_dil.surrogate.experiment import Mundo, avaliar_oot, gerar
from volc_dil.surrogate.real_probe import carregar_golden_meta, carregar_senac

RAIZ = Path(__file__).resolve().parents[2]
D0 = date(2026, 1, 1)


def linhas(n_unid: int, n_per: int, *, grao="campaign_day", circular=False, rotulo=1.0):
    out = []
    for u in range(n_unid):
        for t in range(n_per):
            feats = {"engajamento": Feature(0.5, "browser")}
            if circular:
                feats["impressoes_publisher"] = Feature(100.0, "joinads")
            out.append(LinhaRotulada(f"u{u}", D0 + timedelta(days=t), grao, rotulo, True, "joinads", feats))
    return out


def test_alvo_mais_fino_que_o_rotulo_nao_e_identificavel():
    r = avaliar_viabilidade(linhas(30, 80), grao_alvo="session")
    assert r.veredito is Veredito.NAO_IDENTIFICAVEL


def test_graos_misturados_nao_sao_identificaveis():
    xs = linhas(2, 2) + linhas(1, 2, grao="ad_group_day")
    assert avaliar_viabilidade(xs, grao_alvo="campaign_day").veredito is Veredito.NAO_IDENTIFICAVEL


def test_feature_circular_e_removida_antes_de_contar():
    r = avaliar_viabilidade(linhas(30, 80, circular=True), grao_alvo="campaign_day")
    assert r.features_circulares == ["impressoes_publisher"]
    assert r.features_validas == ["engajamento"]
    assert r.veredito is Veredito.VIAVEL_PARA_TESTE


def test_so_features_circulares_e_insuficiente():
    xs = [LinhaRotulada(l.unidade_id, l.periodo, l.grao, l.rotulo, True, "joinads",
                        {"imp": Feature(1.0, "joinads")}) for l in linhas(30, 80)]
    r = avaliar_viabilidade(xs, grao_alvo="campaign_day")
    assert r.veredito is Veredito.DADOS_INSUFICIENTES


def test_rotulo_ausente_nao_conta_como_zero():
    r = avaliar_viabilidade(linhas(30, 80, rotulo=None), grao_alvo="campaign_day")
    assert r.contagens["linhas_maduras"] == 0
    assert r.veredito is Veredito.DADOS_INSUFICIENTES


def test_volume_pequeno_e_dados_insuficientes():
    assert avaliar_viabilidade(linhas(7, 17), grao_alvo="campaign_day").veredito is Veredito.DADOS_INSUFICIENTES
    folgado = ParametrosPortao(min_unidades=1, min_periodos_treino=1, min_periodos_teste=1, min_linhas_maduras=1)
    assert avaliar_viabilidade(linhas(7, 17), grao_alvo="campaign_day", parametros=folgado).veredito is Veredito.VIAVEL_PARA_TESTE


def test_dados_reais_versionados_sao_insuficientes_e_sessao_nao_identificavel():
    senac, meta = carregar_senac(RAIZ), carregar_golden_meta(RAIZ)
    assert avaliar_viabilidade(senac, grao_alvo="campaign_day").veredito is Veredito.DADOS_INSUFICIENTES
    r = avaliar_viabilidade(meta, grao_alvo="campaign_day")
    assert r.veredito is Veredito.DADOS_INSUFICIENTES
    assert set(r.features_circulares) == {"gam_clicks", "gam_impressions"}
    assert avaliar_viabilidade(meta, grao_alvo="session").veredito is Veredito.NAO_IDENTIFICAVEL
    # campo vazio no CSV real vira None, nunca 0
    assert any(l.rotulo is None for l in senac)


def test_mundo_sintetico_e_deterministico():
    a, b = gerar(Mundo(5, 20), 7), gerar(Mundo(5, 20), 7)
    assert np.array_equal(a["y"], b["y"]) and not np.array_equal(a["y"], gerar(Mundo(5, 20), 8)["y"])


def test_feature_circular_infla_metrica_que_o_portao_bloqueia():
    d = gerar(Mundo(20, 60, forca_sinal=0.25), 11)
    valido = avaliar_oot(d, ["s1", "s2", "s3"])["ridge"]["r2_oot"]
    circular = avaliar_oot(d, ["s1", "s2", "s3", "circ"])["ridge"]["r2_oot"]
    assert circular > 0.8 > valido


def test_sinal_nulo_nao_supera_baseline_por_unidade():
    skills = [avaliar_oot(gerar(Mundo(20, 60, forca_sinal=0.0), s), ["s1", "s2", "s3"])["ridge"]["skill_vs_base"]
              for s in range(30)]
    assert abs(float(np.mean(skills))) < 0.01
