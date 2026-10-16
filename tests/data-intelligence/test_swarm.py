"""Contraprovas do Swarm Lab (worker E). Simulação sintética; nada aqui toca rede ou produção."""
from __future__ import annotations

import itertools
import re
from pathlib import Path

import numpy as np
import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.swarm import (
    ASHA,
    EqualBudget,
    GreedyConservador,
    MICROS,
    Oraculo,
    ParametrosCenario,
    SuccessiveHalving,
    ThompsonTopN,
    ViolacaoOrcamento,
    gerar_cenario,
    inteirizar,
    simular,
)
from volc_dil.swarm.experimento import rodar_seed, rng_politica
from volc_dil.swarm.simulador import receita_reportada, validar_alocacao

SRC_SWARM = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab" / "src" / "volc_dil" / "swarm"


def _todas(D: int) -> dict:
    return {
        "oraculo": lambda c: Oraculo(c),
        "equal": lambda c: EqualBudget(),
        "random_sh": lambda c: SuccessiveHalving(promocao="aleatoria"),
        "greedy_parcial": lambda c: GreedyConservador(decisao="parcial"),
        "greedy_madura": lambda c: GreedyConservador(decisao="madura", atraso_assumido=D),
        "sh_parcial": lambda c: SuccessiveHalving(decisao="parcial"),
        "sh_madura": lambda c: SuccessiveHalving(decisao="madura", atraso_assumido=D),
        "asha_parcial": lambda c: ASHA(decisao="parcial"),
        "asha_madura": lambda c: ASHA(decisao="madura", atraso_assumido=D),
        "thompson_parcial": lambda c: ThompsonTopN(decisao="parcial"),
    }


# ---------------------------------------------------------------- reprodutibilidade

def test_mesma_seed_mesmo_resultado():
    p = ParametrosCenario(modo_maturacao="vencedoras_lentas", troca_vencedora_em=0.5, interferencia=0.3)
    a, b = gerar_cenario(p, 123), gerar_cenario(p, 123)
    assert np.array_equal(a.v, b.v) and np.array_equal(a.cap_brl, b.cap_brl) and np.array_equal(a.uniformes, b.uniformes)
    r1 = rodar_seed(p, 123, _todas(p.atraso_ciclos))
    r2 = rodar_seed(p, 123, _todas(p.atraso_ciclos))
    for pol in r1:
        x = {k: v for k, v in r1[pol].items() if k != "tempo_s"}
        y = {k: v for k, v in r2[pol].items() if k != "tempo_s"}
        assert x == y, pol
    c = gerar_cenario(p, 124)
    assert not np.array_equal(a.v, c.v)


# ---------------------------------------------------------------- oráculo

def test_oraculo_tem_regret_zero_e_ninguem_bate_o_oraculo_sem_interferencia():
    for seed in range(6):
        p = ParametrosCenario(troca_vencedora_em=0.5 if seed % 2 else None)
        r = rodar_seed(p, seed, _todas(p.atraso_ciclos))
        assert r["oraculo"]["regret_brl"] == 0.0
        for pol, m in r.items():
            assert m["regret_brl"] >= -1e-3, (pol, m["regret_brl"])


def test_oraculo_milp_bate_busca_exaustiva_em_problema_pequeno():
    p = ParametrosCenario(K=4, T=1, orcamento_ciclo_micros=240 * MICROS, minimo_celula_micros=10 * MICROS)
    for seed in range(5):
        cen = gerar_cenario(p, seed)
        a = Oraculo(cen)
        a.reiniciar(4, 1, p.orcamento_ciclo_micros, p.minimo_celula_micros, np.random.default_rng(0))
        valor_oraculo = cen.contribuicao_esperada_brl(0, a._resolver(0))
        melhor = -np.inf
        passos = range(0, 25)  # múltiplos de R$10
        for x in itertools.product(passos, repeat=3):
            resto = 24 - sum(x)
            if resto < 0:
                continue
            aloc = np.array([*x, resto], dtype=np.int64) * 10 * MICROS
            melhor = max(melhor, cen.contribuicao_esperada_brl(0, aloc))
        assert valor_oraculo >= melhor - 1e-6


# ---------------------------------------------------------------- orçamento e dinheiro

@pytest.mark.parametrize("cenario", [
    dict(), dict(atraso_ciclos=0), dict(modo_maturacao="vencedoras_lentas", atraso_ciclos=6),
    dict(troca_vencedora_em=0.4, interferencia=0.5, valor_evento_brl=30.0), dict(K=32, minimo_celula_micros=25 * MICROS),
])
def test_politica_nunca_aloca_acima_do_total_nem_abaixo_do_minimo(cenario):
    p = ParametrosCenario(**cenario)
    for seed in range(3):
        cen = gerar_cenario(p, seed)
        for nome, fab in _todas(p.atraso_ciclos).items():
            res = simular(cen, fab(cen), rng_politica(seed))  # simular valida cada ciclo
            a = res.alocacao
            assert a.dtype == np.int64, nome
            assert (a.sum(axis=1) == p.orcamento_ciclo_micros).all(), nome
            assert (((a == 0) | (a >= p.minimo_celula_micros))).all(), nome


def test_validador_rejeita_float_soma_errada_e_abaixo_do_minimo():
    K, B, m = 4, 400 * MICROS, 10 * MICROS
    validar_alocacao(np.array([100, 100, 100, 100], dtype=np.int64) * MICROS, K, B, m)
    with pytest.raises(ViolacaoOrcamento):
        validar_alocacao(np.array([100.0, 100, 100, 100]) * MICROS, K, B, m)
    with pytest.raises(ViolacaoOrcamento):
        validar_alocacao(np.array([100, 100, 100, 101], dtype=np.int64) * MICROS, K, B, m)
    with pytest.raises(ViolacaoOrcamento):
        validar_alocacao(np.array([5, 195, 100, 100], dtype=np.int64) * MICROS, K, B, m)
    with pytest.raises(ViolacaoOrcamento):
        validar_alocacao(np.array([-10, 210, 100, 100], dtype=np.int64) * MICROS, K, B, m)


def test_inteirizar_propriedades():
    rng = np.random.default_rng(7)
    for _ in range(300):
        K = int(rng.integers(2, 40))
        m = int(rng.integers(1, 30)) * MICROS
        B = m * K + int(rng.integers(0, 10_000)) * MICROS + int(rng.integers(0, MICROS))
        w = rng.exponential(size=K) * (rng.random(K) < 0.7)
        a = inteirizar(w, B, m)
        assert a.dtype == np.int64 and int(a.sum()) == B
        assert ((a == 0) | (a >= m)).all()


def test_dinheiro_em_micros_int_na_fronteira():
    with pytest.raises(TypeError):
        ParametrosCenario(orcamento_ciclo_micros=960.0 * MICROS)  # type: ignore[arg-type]
    p = ParametrosCenario()
    cen = gerar_cenario(p, 5)
    res = simular(cen, SuccessiveHalving(), rng_politica(5))
    assert res.receita_final.dtype == np.int64 and (res.receita_final % 10_000 == 0).all()  # centavo
    rep = receita_reportada(cen, res.receita_final, p.T)
    assert rep.dtype == np.int64 and (rep <= res.receita_final).all()
    gasto = Dinheiro(int(res.alocacao.sum()), "BRL")  # aceita: é int
    assert gasto.micros == p.orcamento_ciclo_micros * p.T
    assert res.contribuicao_esperada.dtype == float  # métrica de simulação, documentada como float


# ---------------------------------------------------------------- Successive Halving

@pytest.mark.parametrize("eta,degraus,n_final,esperado", [
    (2, (30, 90, 270), 2, [8, 4, 2]),
    (3, (30, 120), 2, [6, 2]),
    (2, (30, 90), 4, [8, 4]),
    (4, (30, 90), 1, [4, 1]),
])
def test_sh_poda_o_numero_correto(eta, degraus, n_final, esperado):
    p = ParametrosCenario(atraso_ciclos=0)
    cen = gerar_cenario(p, 11)
    sh = SuccessiveHalving(eta=eta, degraus=degraus, n_final=n_final)
    res = simular(cen, sh, rng_politica(11))
    assert [h["n_depois"] for h in sh.historico] == esperado
    assert res.promovidas.sum() == n_final
    assert ((res.alocacao[-1] > 0) == res.promovidas).all()


def test_sh_sem_ruido_e_sem_atraso_encontra_a_melhor():
    p = ParametrosCenario(atraso_ciclos=0, valor_evento_brl=0.001, cap_mult_mediana=1000.0)
    acertos = 0
    for seed in range(20):
        cen = gerar_cenario(p, seed)
        sh = SuccessiveHalving(eta=2, degraus=(30, 90, 270, 810), n_final=1)
        res = simular(cen, sh, rng_politica(seed))
        escolhida = int(np.flatnonzero(res.promovidas)[0])
        v = cen.v[0]
        assert v[escolhida] >= v.max() * 0.99  # nunca erra por mais que 1%
        acertos += escolhida == int(np.argmax(v))
    assert acertos >= 19


def test_contraprova_atraso_forte_decisao_parcial_poda_mais_que_madura():
    """Vencedoras maturam devagar (phi0=0.1) e D=6: SH por receita parcial poda mais top-k."""
    p = ParametrosCenario(atraso_ciclos=6, modo_maturacao="vencedoras_lentas")
    dif = []
    for seed in range(40):
        r = rodar_seed(p, seed, {"sh_parcial": lambda c: SuccessiveHalving(decisao="parcial"),
                                 "sh_madura": lambda c: SuccessiveHalving(decisao="madura", atraso_assumido=6)})
        dif.append(r["sh_parcial"]["podadas_incorretas"] - r["sh_madura"]["podadas_incorretas"])
    dif = np.asarray(dif, float)
    ep = dif.std(ddof=1) / np.sqrt(dif.size)
    assert dif.mean() - 1.96 * ep > 0, (dif.mean(), ep)


def test_contraprova_inversa_maturacao_uniforme_parcial_nao_e_pior_em_poda():
    """Controle: maturação igual para todas -> a ordenação parcial preserva a ordem; não há o efeito."""
    p = ParametrosCenario(atraso_ciclos=6, modo_maturacao="uniforme")
    dif = []
    for seed in range(40):
        r = rodar_seed(p, seed, {"sh_parcial": lambda c: SuccessiveHalving(decisao="parcial"),
                                 "sh_madura": lambda c: SuccessiveHalving(decisao="madura", atraso_assumido=6)})
        dif.append(r["sh_parcial"]["podadas_incorretas"] - r["sh_madura"]["podadas_incorretas"])
    dif = np.asarray(dif, float)
    ep = dif.std(ddof=1) / np.sqrt(dif.size)
    assert dif.mean() - 1.96 * ep <= 0


def test_sem_atraso_parcial_e_madura_sao_identicas():
    p = ParametrosCenario(atraso_ciclos=0)
    r = rodar_seed(p, 3, _todas(0))
    for fam in ("sh", "asha", "greedy"):
        a = {k: v for k, v in r[f"{fam}_parcial"].items() if k != "tempo_s"}
        b = {k: v for k, v in r[f"{fam}_madura"].items() if k != "tempo_s"}
        assert a == b, fam


def test_random_sh_usa_o_mesmo_cronograma_mas_outra_escolha():
    p = ParametrosCenario(atraso_ciclos=0)
    cen = gerar_cenario(p, 2)
    sh, rnd = SuccessiveHalving(), SuccessiveHalving(promocao="aleatoria")
    simular(cen, sh, rng_politica(2))
    simular(cen, rnd, rng_politica(2))
    assert [h["n_depois"] for h in sh.historico] == [h["n_depois"] for h in rnd.historico]


# ---------------------------------------------------------------- ASHA

def test_asha_respeita_slots_e_entrega_n_final():
    p = ParametrosCenario(atraso_ciclos=3)
    for dec in ("parcial", "madura"):
        for seed in range(5):
            cen = gerar_cenario(p, seed)
            asha = ASHA(decisao=dec, atraso_assumido=3, n_slots=5, n_final=3)
            orig = asha.alocar
            maximo = []

            def espiao(obs, _o=orig, _a=asha):
                a = _o(obs)
                maximo.append(int((_a.status == _a.RODANDO).sum()))
                return a

            asha.alocar = espiao
            res = simular(cen, asha, rng_politica(seed))
            assert max(maximo) <= 5
            assert res.promovidas.sum() <= 3 and res.promovidas.any()


def test_sem_ruido_sem_atraso_asha_acha_a_melhor_na_maioria():
    p = ParametrosCenario(atraso_ciclos=0, valor_evento_brl=0.001, cap_mult_mediana=1000.0)
    acertos = 0
    for seed in range(20):
        cen = gerar_cenario(p, seed)
        res = simular(cen, ASHA(n_final=1, degraus=(30, 90, 270)), rng_politica(seed))
        acertos += bool(res.promovidas[int(np.argmax(cen.v[0]))])
    # ASHA promove com poucos concluídos (top 1/eta de 2..3 trials): pode errar mesmo sem ruído.
    assert acertos >= 12


# ---------------------------------------------------------------- isolamento

LAB = Path(__file__).resolve().parents[2] / "experiments" / "data-intelligence-lab"
_MODULOS_PROIBIDOS = {"requests", "urllib", "urllib3", "http", "socket", "ssl", "subprocess", "supabase", "google",
                      "httpx", "aiohttp", "importlib", "ftplib", "smtplib", "telnetlib", "websocket", "websockets",
                      "paramiko", "pty", "ctypes", "multiprocessing", "asyncio"}
_TEXTOS_PROIBIDOS = ("__import__", "importlib", "subprocess", "socket", "os.system", "os.popen", "os.exec",
                     "eval(", "exec(", "urlopen", "supabase.co", "agenciavolc")


def _arquivos_swarm() -> list[Path]:
    arqs = sorted(SRC_SWARM.glob("*.py")) + sorted((LAB / "scripts").glob("swarm_*.py"))
    assert len(arqs) >= 10, arqs  # guarda: o glob não pode silenciosamente achar nada
    return arqs


def _violacoes(texto: str) -> list[str]:
    import ast

    achados = []
    for no in ast.walk(ast.parse(texto)):
        if isinstance(no, ast.Import):
            achados += [a.name for a in no.names if a.name.split(".")[0] in _MODULOS_PROIBIDOS]
        elif isinstance(no, ast.ImportFrom) and no.module and no.module.split(".")[0] in _MODULOS_PROIBIDOS:
            achados.append(no.module)
    achados += [t for t in _TEXTOS_PROIBIDOS if t in texto]
    return achados


def test_modulo_swarm_nao_tem_caminho_para_rede_ou_mutacao_real():
    """AST de todos os imports (inclusive dentro de função) + busca textual de import dinâmico,
    subprocess, socket e hosts reais, em swarm/*.py e scripts/swarm_*.py."""
    # Única exceção, explícita e estreita: o executor de mutação usa subprocess para rodar pytest
    # local num diretório temporário, e "socket" aparece lá só como TEXTO do mutante SW8.
    excecoes = {"swarm_mutantes.py": {"subprocess", "socket"}}
    for f in _arquivos_swarm():
        assert set(_violacoes(f.read_text())) == excecoes.get(f.name, set()), f


def test_detector_anti_rede_pega_as_formas_escondidas():
    """Contraprova do próprio detector (F2-18): formas que o regex antigo deixava passar."""
    for codigo in ("def f():\n    import socket\n", "x = 1; import subprocess\n",
                   "def g():\n    from urllib.request import urlopen\n", "m = __import__('so' + 'cket')\n",
                   "import importlib\nimportlib.import_module('requests')\n", "import os\nos.system('curl x')\n"):
        assert _violacoes(codigo), codigo
    assert _violacoes("import numpy as np\nfrom scipy import stats\n") == []


def test_regra_de_parada_igual_a_do_optuna_em_caso_feito_a_mao():
    """Regra conferida contra optuna 5.0 SuccessiveHalvingPruner (60/60 sequências, sonda isolada;
    results/swarm/swarm_crosscheck_optuna.json). Aqui o caso à mão fixa a semântica."""
    from volc_dil.swarm.regras import asha_parada_na_chegada

    vals = np.array([[1.0, 0], [2.0, 0], [0.0, 0], [3.0, 0]])
    assert asha_parada_na_chegada(vals, 2).tolist() == [2, 2, 1, 2]



# ---------------------------------------------------------------- critério (F2-03) e regressão do veredito

def _acum_sintetico(**politicas):
    """politica=(regret, frac_perdedoras, drawdown, excesso) -> acum no formato de rodar_cenario."""
    out = {}
    for nome, (reg, frac, dd, exc) in politicas.items():
        n = len(reg)
        out[nome] = {"regret_brl": list(reg), "frac_orcamento_perdedoras_final": list(np.broadcast_to(frac, n)),
                     "drawdown_micros": list(np.broadcast_to(dd, n)),
                     "excesso_perdedoras_vs_oraculo_final": list(np.broadcast_to(exc, n))}
    return out


def test_criterio_supera_quando_as_tres_condicoes_valem():
    from volc_dil.swarm.experimento import avaliar_criterio

    rng = np.random.default_rng(1)
    z = rng.normal(size=50)
    ac = _acum_sintetico(equal=(1000 + 5 * z, 0.7, 5e9, 0.5), greedy_parcial=(100 + 5 * z, 0.2, 2e9, 0.05),
                         sh_parcial=(50 + 5 * rng.normal(size=50), 0.2, 2e9, 0.05))
    r = avaliar_criterio(ac, "sh_parcial")
    assert r["melhor_baseline"] == "greedy_parcial" and r["supera"] and r["regret_ok"]
    assert r["falsos_vencedores_ok"] and r["drawdown_ok"]


def test_criterio_usa_ics_marginais_e_nao_o_pareado():
    """Mata o mutante SW1: diferença pareada nitidamente < 0, mas ICs marginais se cruzam."""
    from volc_dil.swarm.experimento import avaliar_criterio

    rng = np.random.default_rng(2)
    base = 100 + 30 * rng.normal(size=50)
    ac = _acum_sintetico(equal=(base + 500, 0.7, 5e9, 0.5), greedy_parcial=(base, 0.2, 2e9, 0.05),
                         sh_parcial=(base - 5 + 0.01 * rng.normal(size=50), 0.2, 2e9, 0.05))
    r = avaliar_criterio(ac, "sh_parcial")
    assert r["dif_pareada_regret"]["ic95"][1] < 0          # o pareado diria "melhor"
    assert r["regret_candidato"]["ic95"][1] >= r["regret_baseline"]["ic95"][0]  # marginais se cruzam
    assert not r["regret_ok"] and not r["supera"]


def test_criterio_escolhe_o_baseline_de_menor_regret():
    """Mata SW2: contra o pior baseline (equal) o candidato 'superaria'; contra o melhor, não."""
    from volc_dil.swarm.experimento import avaliar_criterio

    z = np.random.default_rng(3).normal(size=50)
    ac = _acum_sintetico(equal=(1000 + z, 0.7, 5e9, 0.5), random_sh=(1200 + z, 0.7, 9e9, 0.5),
                         greedy_parcial=(100 + z, 0.2, 2e9, 0.05), sh_parcial=(500 + z, 0.2, 2e9, 0.05))
    r = avaliar_criterio(ac, "sh_parcial")
    assert r["melhor_baseline"] == "greedy_parcial" and not r["supera"]


@pytest.mark.parametrize("cand_frac,cand_dd,ok_falsos,ok_dd", [(0.5, 2e9, False, True), (0.2, 4e9, True, False)])
def test_criterio_exige_falsos_vencedores_e_drawdown(cand_frac, cand_dd, ok_falsos, ok_dd):
    """Mata SW3: regret muito melhor não basta se falsos vencedores ou drawdown pioram."""
    from volc_dil.swarm.experimento import avaliar_criterio

    rng = np.random.default_rng(4)
    ac = _acum_sintetico(greedy_parcial=(100 + rng.normal(size=50), 0.2 + 0.01 * rng.normal(size=50),
                                         2e9 + 1e7 * rng.normal(size=50), 0.05),
                         sh_parcial=(10 + rng.normal(size=50), cand_frac, cand_dd, 0.05))
    r = avaliar_criterio(ac, "sh_parcial")
    assert r["regret_ok"] and r["falsos_vencedores_ok"] is ok_falsos and r["drawdown_ok"] is ok_dd
    assert not r["supera"]


def test_criterio_exploratorio_le_a_metrica_relativa_ao_oraculo():
    from volc_dil.swarm.experimento import avaliar_criterio, avaliar_criterio_exploratorio

    z = np.random.default_rng(5).normal(size=50)
    # frac absoluta pior (0.4 vs 0.2) mas excesso sobre o oráculo igual: só o exploratório aprova
    ac = _acum_sintetico(greedy_parcial=(100 + z, 0.2, 2e9, 0.05), sh_parcial=(10 + z, 0.4, 2e9, 0.05))
    assert not avaliar_criterio(ac, "sh_parcial")["supera"]
    r = avaliar_criterio_exploratorio(ac, "sh_parcial")
    assert r["metrica_falsos"] == "excesso_perdedoras_vs_oraculo_final" and r["supera"]


def test_drawdown_maximo_valor_conhecido():
    from volc_dil.swarm.simulador import drawdown_maximo

    # acumulado 0,10,-20,-15,-25 -> pico 10, vale -25 -> 35
    assert drawdown_maximo(np.array([10, -30, 5, -10])) == 35
    assert drawdown_maximo(np.array([5, 5, 5])) == 0
    assert drawdown_maximo(np.array([-7, 2])) == 7


def test_perdedora_e_contribuicao_nao_positiva_v_ate_1():
    """Mata SW4: célula com v=0,8 (contribuição −20%) é perdedora; v=1,2 não."""
    from volc_dil.swarm.simulador import metricas_execucao

    p = ParametrosCenario(K=4, T=6, orcamento_ciclo_micros=400 * MICROS, minimo_celula_micros=10 * MICROS)
    cen = gerar_cenario(p, 0)
    cen.v[:] = np.array([0.3, 0.8, 1.0, 1.2])
    res = simular(cen, EqualBudget(), rng_politica(0))
    m = metricas_execucao(res, cen, res.contribuicao_esperada)
    assert m["frac_orcamento_perdedoras_final"] == pytest.approx(0.75)


def test_madura_usa_so_linhas_com_idade_maior_ou_igual_a_D():
    """Mata SW6: SH madura decide exatamente D ciclos depois da parcial (degrau em gasto, determinístico)."""
    for D in (1, 3, 5):
        p = ParametrosCenario(atraso_ciclos=D)
        cen = gerar_cenario(p, 9)
        sh_p = SuccessiveHalving(degraus=(120, 360), unidade="gasto", decisao="parcial")
        sh_m = SuccessiveHalving(degraus=(120, 360), unidade="gasto", decisao="madura", atraso_assumido=D)
        simular(cen, sh_p, rng_politica(9))
        simular(cen, sh_m, rng_politica(9))
        assert sh_p.historico[0]["t"] == 2  # 2 ciclos × R$60 = R$120
        assert sh_m.historico[0]["t"] == 2 + D
    g = GreedyConservador(decisao="madura", atraso_assumido=3)
    obs = type("O", (), {"acumulado": lambda self, idade_minima=0: idade_minima})()
    assert g._dados(obs, "madura", 3) == 3 and g._dados(obs, "parcial", 3) == 0


# Valores fixados com o código que gerou os JSON de results/swarm (seeds 500..505, cenário base).
# (soma do regret R$, soma de frac_orcamento_perdedoras_final, soma do drawdown em micros)
_FIXADOS_BASE = {
    "oraculo": (0.000000, 1.735987002, 2979700000),
    "equal": (86955.874257, 4.687500000, 31682180000),
    "random_sh": (98262.113042, 4.000000000, 58446620000),
    "greedy_parcial": (41962.783888, 1.526011229, 14902820000),
    "greedy_madura": (46045.458027, 1.422372155, 17205090000),
    "sh_parcial": (49744.760217, 1.750000000, 20303850000),
    "sh_madura": (53966.596774, 1.500000000, 21871380000),
    "asha_parcial": (48041.494625, 1.750000000, 16303720000),
    "asha_madura": (63815.275094, 1.750000000, 28461350000),
    "thompson_parcial": (33017.727907, 1.653840769, 11150490000),
}


def test_regressao_do_veredito_em_seeds_fixas():
    """Regressão (F2-03): fixa métricas e o veredito em 6 seeds do cenário base. Qualquer mudança em
    simulador, políticas (inclusive prior do Thompson e espera da madura) ou critério quebra aqui."""
    from volc_dil.swarm.experimento import avaliar_criterio, rodar_cenario

    p = ParametrosCenario()
    ac = rodar_cenario(p, list(range(500, 506)), _todas(3))
    for nome, (reg, frac, dd) in _FIXADOS_BASE.items():
        assert sum(ac[nome]["regret_brl"]) == pytest.approx(reg, abs=1e-4), nome
        assert sum(ac[nome]["frac_orcamento_perdedoras_final"]) == pytest.approx(frac, abs=1e-8), nome
        assert sum(ac[nome]["drawdown_micros"]) == dd, nome
    for c in ("sh_parcial", "sh_madura", "asha_parcial", "asha_madura"):
        r = avaliar_criterio(ac, c)
        assert r["melhor_baseline"] == "greedy_parcial" and r["supera"] is False, c
        assert r["regret_ok"] is False and r["falsos_vencedores_ok"] is True and r["drawdown_ok"] is True, c
    assert all(x == 0.0 for x in ac["oraculo"]["excesso_perdedoras_vs_oraculo_final"])
    assert sum(ac["oraculo"]["frac_orcamento_perdedoras_final"]) > 1.0  # F2-01: a métrica absoluta pune o ótimo
