"""Swarm Lab — grids de simulação SINTÉTICA (seed, sem dado real, sem rede, sem mutação).

Uso (da raiz do repo):
  experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/swarm_grid.py --grid principal
  ... --grid parametros | --grid sensibilidade --bloco estacionario|nao_estacionario | --grid diagnostico

Grava results/swarm/swarm_<grid>[_<bloco>].json (determinístico: mesma seed -> mesmo JSON)
e results/swarm/swarm_custo_<grid>[_<bloco>].json (tempo de parede; NÃO determinístico).
Recusa rodar sem results/swarm/PRE-REGISTRO.md (critério escrito antes dos grids).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "src"))

import numpy as np  # noqa: E402

from volc_dil.contracts import manifesto_execucao, sha256_arquivo  # noqa: E402
from volc_dil.swarm import VERSAO_SWARM  # noqa: E402
from volc_dil.swarm.cenario import MICROS, ParametrosCenario  # noqa: E402
from volc_dil.swarm.diagnostico import diagnosticar_seed  # noqa: E402
from volc_dil.swarm.experimento import avaliar_criterio, ic_media, resumir, rodar_cenario  # noqa: E402
from volc_dil.swarm.politicas import (  # noqa: E402
    ASHA,
    EqualBudget,
    GreedyConservador,
    Oraculo,
    SuccessiveHalving,
    ThompsonTopN,
)

SAIDA = LAB / "results" / "swarm"
PRE_REGISTRO = SAIDA / "PRE-REGISTRO.md"
SEED0 = 1_000_000
CANDIDATOS = ("sh_parcial", "sh_madura", "asha_parcial", "asha_madura")
LIMITE_BYTES = 300_000


def cenarios_principais() -> dict[str, ParametrosCenario]:
    P = ParametrosCenario
    return {
        "base": P(nome="base"),
        "sem_atraso": P(nome="sem_atraso", atraso_ciclos=0),
        "atraso_6": P(nome="atraso_6", atraso_ciclos=6),
        "vencedoras_lentas_D3": P(nome="vencedoras_lentas_D3", modo_maturacao="vencedoras_lentas"),
        "vencedoras_lentas_D6": P(nome="vencedoras_lentas_D6", modo_maturacao="vencedoras_lentas", atraso_ciclos=6),
        "maturacao_por_canal_D3": P(nome="maturacao_por_canal_D3", modo_maturacao="por_canal"),
        "ruido_baixo": P(nome="ruido_baixo", valor_evento_brl=2.0),
        "ruido_alto": P(nome="ruido_alto", valor_evento_brl=30.0),
        "nao_estacionario": P(nome="nao_estacionario", troca_vencedora_em=0.5),
        "interferencia": P(nome="interferencia", interferencia=0.5),
        "ideal_sem_saturacao": P(nome="ideal_sem_saturacao", cap_mult_mediana=100.0, atraso_ciclos=0,
                                 valor_evento_brl=2.0),
        "adverso": P(nome="adverso", atraso_ciclos=6, modo_maturacao="vencedoras_lentas", troca_vencedora_em=0.5,
                     interferencia=0.5, valor_evento_brl=30.0),
    }


def fabricas_padrao(D: int, n_final: int = 4, com_thompson: bool = True, com_oraculo: bool = True) -> dict:
    f = {}
    if com_oraculo:
        f["oraculo"] = lambda c: Oraculo(c)
    f.update({
        "equal": lambda c: EqualBudget(),
        "random_sh": lambda c: SuccessiveHalving(promocao="aleatoria", n_final=n_final),
        "greedy_parcial": lambda c: GreedyConservador(decisao="parcial", n_top=n_final),
        "greedy_madura": lambda c: GreedyConservador(decisao="madura", atraso_assumido=D, n_top=n_final),
        "sh_parcial": lambda c: SuccessiveHalving(decisao="parcial", n_final=n_final),
        "sh_madura": lambda c: SuccessiveHalving(decisao="madura", atraso_assumido=D, n_final=n_final),
        "asha_parcial": lambda c: ASHA(decisao="parcial", n_final=n_final),
        "asha_madura": lambda c: ASHA(decisao="madura", atraso_assumido=D, n_final=n_final),
    })
    if com_thompson:
        f["thompson_parcial"] = lambda c: ThompsonTopN(decisao="parcial", n_top=n_final)
        f["thompson_madura"] = lambda c: ThompsonTopN(decisao="madura", atraso_assumido=D, n_top=n_final)
    return f


def seeds(n: int) -> list[int]:
    return [SEED0 + i for i in range(n)]


def _sanear(obj, casas=6):
    if isinstance(obj, dict):
        return {str(k): _sanear(v, casas) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanear(v, casas) for v in obj]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if not math.isfinite(f):
            return None
        return 0.0 if f == 0 else float(f"{f:.{casas}g}")
    return obj


def gravar(nome: str, obj: dict) -> int:
    dados = json.dumps(_sanear(obj, 5), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    if len(dados) > LIMITE_BYTES:
        raise ValueError(f"{nome}: {len(dados)} bytes > {LIMITE_BYTES}")
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / nome).write_bytes(dados + b"\n")
    return len(dados)


def manifesto(nome: str, n_seeds: int, parametros: dict) -> dict:
    fontes = sorted((LAB / "src" / "volc_dil" / "swarm").glob("*.py")) + [Path(__file__)]
    entradas = {"PRE-REGISTRO.md": sha256_arquivo(str(PRE_REGISTRO))}
    entradas.update({f.relative_to(LAB).as_posix(): sha256_arquivo(str(f)) for f in fontes})
    m = manifesto_execucao(nome=nome, seed=SEED0, entradas=entradas,
                           parametros={"n_seeds": n_seeds, "seeds": f"{SEED0}..{SEED0 + n_seeds - 1}",
                                       "versao_swarm": VERSAO_SWARM, **parametros})
    m["natureza"] = "simulacao_sintetica_com_seed_sem_dado_real_nao_validado"
    return m


def _separar_tempo(resumo: dict) -> tuple[dict, dict]:
    tempos = {}
    for pol, r in resumo.items():
        tempos[pol] = r.pop("tempo_medio_ms")
    return resumo, tempos


def _pareado(acum: dict, a: str, b: str, metrica: str) -> dict:
    return ic_media(np.asarray(acum[a][metrica], float) - np.asarray(acum[b][metrica], float))


def _bloco_cenario(params: ParametrosCenario, n: int, fabricas: dict, candidatos=CANDIDATOS,
                   compacto: bool = False) -> tuple[dict, dict]:
    acum = rodar_cenario(params, seeds(n), fabricas)
    resumo, tempos = _separar_tempo(resumir(acum))
    if compacto:
        chaves = ("regret_brl", "frac_orcamento_perdedoras_final", "drawdown_micros", "podadas_incorretas",
                  "taxa_falso_vencedor")
        resumo = {p: {k: r[k] for k in chaves} for p, r in resumo.items()}
    crit = {c: avaliar_criterio(acum, c) for c in candidatos if c in acum}
    pares = {}
    for fam in ("sh", "asha", "greedy", "thompson"):
        a, b = f"{fam}_parcial", f"{fam}_madura"
        if a in acum and b in acum:
            pares[f"{a}_menos_{b}"] = {m: _pareado(acum, a, b, m) for m in ("regret_brl", "podadas_incorretas")}
    out = {"parametros_cenario": params.como_dict(), "resumo": resumo, "criterio": crit, "pareado_parcial_madura": pares}
    if compacto:
        for c in crit.values():
            for k in ("regret_candidato", "regret_baseline"):
                c.pop(k)
    return out, tempos


def grid_principal(n: int) -> tuple[dict, dict]:
    res, custo = {}, {}
    for nome, p in cenarios_principais().items():
        t0 = time.perf_counter()
        res[nome], custo[nome] = _bloco_cenario(p, n, fabricas_padrao(p.atraso_ciclos))
        custo[nome]["_parede_s"] = time.perf_counter() - t0
        print(f"  {nome}: {custo[nome]['_parede_s']:.1f}s", flush=True)
    passa = {c: [s for s, r in res.items() if r["criterio"][c]["supera"]] for c in CANDIDATOS}
    algum = sorted({s for v in passa.values() for s in v})
    if not algum:
        veredito = "nao"
    elif any(len(v) == len(res) for v in passa.values()):
        veredito = "sim_em_simulacao_todas_as_condicoes"
    else:
        veredito = "depende"
    return {"cenarios": res, "veredito_regra_pre_registrada": veredito, "cenarios_em_que_supera": passa}, custo


def _fabricas_parametros(D: int) -> dict:
    f = fabricas_padrao(D, com_thompson=False)
    for k in ("sh_parcial", "sh_madura", "asha_parcial", "asha_madura"):
        f.pop(k)
    for eta in (2, 3):
        for r0 in (20, 60, 150):
            degr = (r0, 3 * r0)
            for dec in ("parcial", "madura"):
                at = D if dec == "madura" else 0
                f[f"sh_e{eta}_r{r0}_cliques_{dec}"] = (lambda e, d, dc, a: lambda c: SuccessiveHalving(
                    eta=e, degraus=d, decisao=dc, atraso_assumido=a))(eta, degr, dec, at)
                f[f"asha_e{eta}_r{r0}_cliques_{dec}"] = (lambda e, d, dc, a: lambda c: ASHA(
                    eta=e, degraus=d, decisao=dc, atraso_assumido=a))(eta, degr, dec, at)
    for dec in ("parcial", "madura"):
        at = D if dec == "madura" else 0
        f[f"sh_e2_r120brl_gasto_{dec}"] = (lambda dc, a: lambda c: SuccessiveHalving(
            degraus=(120, 360), unidade="gasto", decisao=dc, atraso_assumido=a))(dec, at)
        f[f"asha_e2_r120brl_gasto_{dec}"] = (lambda dc, a: lambda c: ASHA(
            degraus=(120, 360), unidade="gasto", decisao=dc, atraso_assumido=a))(dec, at)
    return f


def grid_parametros(n: int) -> tuple[dict, dict]:
    todos = cenarios_principais()
    res, custo = {}, {}
    for nome in ("base", "vencedoras_lentas_D3", "ideal_sem_saturacao"):
        p = todos[nome]
        fab = _fabricas_parametros(p.atraso_ciclos)
        cands = tuple(k for k in fab if k.startswith(("sh_e", "asha_e")))
        t0 = time.perf_counter()
        res[f"degraus__{nome}"], custo[f"degraus__{nome}"] = _bloco_cenario(p, n, fab, candidatos=cands, compacto=True)
        print(f"  degraus {nome}: {time.perf_counter() - t0:.1f}s", flush=True)
        for nf in (1, 2, 4):
            t0 = time.perf_counter()
            chave = f"n_final_{nf}__{nome}"
            res[chave], custo[chave] = _bloco_cenario(p, n, fabricas_padrao(p.atraso_ciclos, n_final=nf), compacto=True)
            print(f"  {chave}: {time.perf_counter() - t0:.1f}s", flush=True)
    return {"cenarios": res}, custo


def grid_sensibilidade(n: int, bloco: str) -> tuple[dict, dict]:
    troca = None if bloco == "estacionario" else 0.5
    res, custo = {}, {}
    for D in (0, 1, 3, 6):
        for modo in ("uniforme", "vencedoras_lentas"):
            for ve in (2.0, 8.0, 30.0):
                nome = f"D{D}__{modo}__ruido{int(ve)}__{bloco}"
                p = ParametrosCenario(nome=nome, atraso_ciclos=D, modo_maturacao=modo, valor_evento_brl=ve,
                                      troca_vencedora_em=troca)
                t0 = time.perf_counter()
                res[nome], custo[nome] = _bloco_cenario(p, n, fabricas_padrao(D, com_thompson=False), compacto=True)
                res[nome].pop("parametros_cenario")
                print(f"  {nome}: {time.perf_counter() - t0:.1f}s", flush=True)
    return {"cenarios": res, "parametros_fixos": ParametrosCenario(troca_vencedora_em=troca).como_dict()}, custo


def grid_diagnostico(n: int) -> tuple[dict, dict]:
    todos = cenarios_principais()
    res = {}
    t0 = time.perf_counter()
    for nome in ("base", "sem_atraso", "atraso_6", "vencedoras_lentas_D3", "vencedoras_lentas_D6",
                 "ruido_baixo", "ideal_sem_saturacao", "interferencia"):
        linhas = [diagnosticar_seed(todos[nome], s) for s in seeds(n)]
        agg = {"spearman_v_escala": ic_media([l["spearman_v_escala"] for l in linhas])}
        for rung in linhas[0]:
            if rung.startswith("rung_"):
                agg[rung] = {k: ic_media([l[rung][k] for l in linhas]) for k in linhas[0][rung]}
        res[nome] = agg
    return {"cenarios": res}, {"_parede_s": time.perf_counter() - t0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", required=True, choices=["principal", "parametros", "sensibilidade", "diagnostico"])
    ap.add_argument("--bloco", default="estacionario", choices=["estacionario", "nao_estacionario"])
    ap.add_argument("--n-seeds", type=int, default=200)
    a = ap.parse_args()
    if not PRE_REGISTRO.exists():
        sys.exit("PRE-REGISTRO.md ausente: o critério precisa ser escrito antes do grid")
    t0 = time.perf_counter()
    if a.grid == "principal":
        corpo, custo = grid_principal(a.n_seeds)
        sufixo = ""
    elif a.grid == "parametros":
        corpo, custo = grid_parametros(a.n_seeds)
        sufixo = ""
    elif a.grid == "sensibilidade":
        corpo, custo = grid_sensibilidade(a.n_seeds, a.bloco)
        sufixo = f"_{a.bloco}"
    else:
        corpo, custo = grid_diagnostico(a.n_seeds)
        sufixo = ""
    nome = f"swarm_{a.grid}{sufixo}"
    corpo["manifesto"] = manifesto(nome, a.n_seeds, {"grid": a.grid, "bloco": a.bloco if a.grid == "sensibilidade" else None,
                                                     "orcamento_ciclo_brl": ParametrosCenario().orcamento_ciclo_micros // MICROS})
    nb = gravar(f"{nome}.json", corpo)
    parede = time.perf_counter() - t0
    gravar(f"swarm_custo_{a.grid}{sufixo}.json", {
        "aviso": "tempo de parede, NAO deterministico; ms por simulacao de T ciclos por politica",
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"), "parede_total_s": parede,
        "por_cenario_ms_por_simulacao": custo, "manifesto_fingerprint": corpo["manifesto"]["fingerprint"]})
    print(f"{nome}.json {nb} bytes, {parede:.1f}s")


if __name__ == "__main__":
    main()
