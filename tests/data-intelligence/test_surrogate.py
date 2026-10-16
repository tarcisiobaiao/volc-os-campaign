"""Contraprovas do portão de viabilidade do surrogate (Fase 6), incluindo respostas a F1-04/05/10/11/16."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from volc_dil.contracts import ContratoViolado
from volc_dil.surrogate import Feature, LinhaRotulada, ParametrosPortao, Veredito, avaliar_viabilidade
from volc_dil.surrogate.experiment import Mundo, avaliar_oot, gerar
from volc_dil.surrogate.real_probe import SENAC, carregar_golden_meta, carregar_senac, contar_zeros_ambiguos_senac

RAIZ = Path(__file__).resolve().parents[2]
D0 = date(2026, 1, 1)
PEQUENO = ParametrosPortao(min_unidades=2, min_periodos_treino_por_unidade=5, min_periodos_teste_por_unidade=2,
                           min_linhas_maduras=10)


def _disp(p: date, atraso_dias: int = 1) -> datetime:
    return datetime(p.year, p.month, p.day, tzinfo=timezone.utc) + timedelta(days=1 + atraso_dias)


def linhas(n_unid, n_per, *, grao="campaign_day", extra=None, rotulo=1.0, origem_extra="joinads", atraso_extra=1):
    out = []
    for u in range(n_unid):
        for t in range(n_per):
            p = D0 + timedelta(days=t)
            feats = {"engajamento": Feature(0.5, "browser", _disp(p))}
            if extra:
                feats[extra] = Feature(100.0, origem_extra, _disp(p, atraso_extra))
            out.append(LinhaRotulada(f"u{u}", p, grao, rotulo, True, "joinads", feats))
    return out


def test_alvo_mais_fino_que_o_rotulo_nao_e_identificavel():
    assert avaliar_viabilidade(linhas(3, 10), grao_alvo="session", parametros=PEQUENO).veredito is Veredito.NAO_IDENTIFICAVEL


def test_f1_05_url_nao_e_aninhada_em_keyword():
    r = avaliar_viabilidade(linhas(3, 10, grao="url_day"), grao_alvo="keyword_day", parametros=PEQUENO)
    assert r.veredito is Veredito.NAO_IDENTIFICAVEL
    assert avaliar_viabilidade(linhas(3, 10, grao="keyword_day"), grao_alvo="campaign_day",
                               parametros=PEQUENO).veredito is Veredito.VIAVEL_PARA_TESTE


def test_graos_misturados_nao_sao_identificaveis():
    xs = linhas(2, 2) + linhas(1, 2, grao="ad_group_day")
    assert avaliar_viabilidade(xs, grao_alvo="campaign_day").veredito is Veredito.NAO_IDENTIFICAVEL


@pytest.mark.parametrize("origem", ["joinads", "JoinAds", "joinads:v2", "joinads ", "gam", "adsense"])
def test_f1_04_variantes_de_origem_da_mesma_receita_sao_circulares(origem):
    r = avaliar_viabilidade(linhas(3, 10, extra="impressoes_publisher", origem_extra=origem), grao_alvo="campaign_day",
                            parametros=PEQUENO)
    assert r.features_circulares == ["impressoes_publisher"]
    assert r.features_validas == ["engajamento"]


def test_f1_04_origem_fora_do_vocabulario_e_erro():
    with pytest.raises(ContratoViolado):
        avaliar_viabilidade(linhas(3, 10, extra="x", origem_extra="fonte_misteriosa"), grao_alvo="campaign_day",
                            parametros=PEQUENO)


def test_f1_04_feature_disponivel_depois_do_horizonte_e_vazamento():
    r = avaliar_viabilidade(linhas(3, 10, extra="receita_d3", origem_extra="browser", atraso_extra=3),
                            grao_alvo="campaign_day", parametros=PEQUENO)
    assert r.features_vazamento == ["receita_d3"]
    sem_as_of = [LinhaRotulada(l.unidade_id, l.periodo, l.grao, l.rotulo, True, "joinads",
                               {"x": Feature(1.0, "browser", None)}) for l in linhas(3, 10)]
    r2 = avaliar_viabilidade(sem_as_of, grao_alvo="campaign_day", parametros=PEQUENO)
    assert r2.features_vazamento == ["x"] and r2.veredito is Veredito.DADOS_INSUFICIENTES


def test_so_features_circulares_e_insuficiente():
    xs = [LinhaRotulada(l.unidade_id, l.periodo, l.grao, l.rotulo, True, "joinads",
                        {"imp": Feature(1.0, "joinads", _disp(l.periodo))}) for l in linhas(3, 10)]
    assert avaliar_viabilidade(xs, grao_alvo="campaign_day", parametros=PEQUENO).veredito is Veredito.DADOS_INSUFICIENTES


def test_rotulo_ausente_nao_conta_como_zero():
    r = avaliar_viabilidade(linhas(3, 10, rotulo=None), grao_alvo="campaign_day", parametros=PEQUENO)
    assert r.contagens["linhas_maduras"] == 0 and r.veredito is Veredito.DADOS_INSUFICIENTES


def test_f1_05_painel_desbalanceado_nao_engana_o_portao():
    # 1 unidade longuíssima + 19 com uma linha cada: contagens brutas "passariam", profundidade não
    p = ParametrosPortao(min_unidades=20, min_periodos_treino_por_unidade=42, min_periodos_teste_por_unidade=18,
                         min_linhas_maduras=1200)
    xs = linhas(1, 1200) + [LinhaRotulada(f"v{i}", D0 + timedelta(days=1199), "campaign_day", 1.0, True, "joinads",
                                          {"engajamento": Feature(0.5, "browser", _disp(D0))}) for i in range(19)]
    r = avaliar_viabilidade(xs, grao_alvo="campaign_day", parametros=p)
    assert r.contagens["unidades_com_rotulo"] == 20 and r.contagens["unidades_com_profundidade"] < 20
    assert r.veredito is Veredito.DADOS_INSUFICIENTES


def test_painel_profundo_e_viavel_com_os_padroes():
    assert avaliar_viabilidade(linhas(50, 90), grao_alvo="campaign_day").veredito is Veredito.VIAVEL_PARA_TESTE
    assert avaliar_viabilidade(linhas(49, 90), grao_alvo="campaign_day").veredito is Veredito.DADOS_INSUFICIENTES


def test_dados_reais_versionados_sao_insuficientes_e_sessao_nao_identificavel():
    senac, meta = carregar_senac(RAIZ), carregar_golden_meta(RAIZ)
    assert avaliar_viabilidade(senac, grao_alvo="campaign_day").veredito is Veredito.DADOS_INSUFICIENTES
    r = avaliar_viabilidade(meta, grao_alvo="campaign_day")
    assert r.veredito is Veredito.DADOS_INSUFICIENTES
    assert set(r.features_circulares) == {"gam_clicks", "gam_impressions"}
    assert avaliar_viabilidade(meta, grao_alvo="session").veredito is Veredito.NAO_IDENTIFICAVEL


def test_f1_16_campo_vazio_do_csv_real_vira_none_nao_zero():
    with open(RAIZ / SENAC, newline="", encoding="utf-8") as f:
        brutas = list(csv.DictReader(f))
    vazios = sum(1 for r in brutas for c in ("clicks", "custo_brl", "valor_conversao_google") if r[c] in ("", "None"))
    nones = sum(1 for l in carregar_senac(RAIZ) for f in l.features.values() if f.valor is None)
    assert vazios > 0 and nones == vazios


def test_f1_11_zero_da_fonte_com_default_0_nao_vira_rotulo():
    zeros = contar_zeros_ambiguos_senac(RAIZ)
    assert zeros >= 1
    assert not any(l.rotulo == 0.0 for l in carregar_senac(RAIZ))


def test_mundo_sintetico_e_deterministico():
    a, b = gerar(Mundo(5, 20), 7), gerar(Mundo(5, 20), 7)
    assert np.array_equal(a["y"], b["y"]) and not np.array_equal(a["y"], gerar(Mundo(5, 20), 8)["y"])


def test_feature_circular_infla_metrica_que_o_portao_bloqueia():
    d = gerar(Mundo(20, 60, forca_sinal=0.25), 11)
    valido = avaliar_oot(d, ["s1", "s2", "s3"])["ridge"]["r2_oot"]
    circular = avaliar_oot(d, ["s1", "s2", "s3", "circ"])["ridge"]["r2_oot"]
    assert circular > 0.8 > valido


def test_f1_10_sinal_nulo_quase_nunca_passa_do_efeito_minimo():
    skills = [avaliar_oot(gerar(Mundo(50, 90, forca_sinal=0.0), s), ["s1", "s2", "s3"])["ridge"]["skill_vs_base"]
              for s in range(20)]
    assert np.mean(np.array(skills) > 0.01) <= 0.1
