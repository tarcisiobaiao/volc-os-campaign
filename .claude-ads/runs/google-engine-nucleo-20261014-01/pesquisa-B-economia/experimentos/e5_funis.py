"""E5 — Relatório "proporção de campanhas lucrativas por modelo de funil" (B35).
DADOS 100% SINTÉTICOS. Mostra o desenho estatístico, não números da operação.

Funções puras (só stdlib), candidatas a delta do integrador:
  * wilson(k, n)            intervalo de Wilson para proporção
  * classificar_campanha()  lucrativa / prejuízo / indeterminada / não elegível,
                            pelo intervalo do lucro diário MÉDIO em dias maduros
  * n_para_margem(p, e)     tamanho de amostra para meia-largura e

Rodar: python -I e5_funis.py [saida.json]
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys

Z95 = 1.959963984540054
T95 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
       10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Intervalo de Wilson (1927) para k sucessos em n. None se n == 0."""
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError("k fora de [0, n]")
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - meia), min(1.0, centro + meia)


def n_para_margem(p: float, margem: float, z: float = Z95) -> int:
    """Campanhas necessárias para meia-largura ~ margem (aprox. normal)."""
    return math.ceil(z * z * p * (1 - p) / (margem * margem))


def _t(gl: int) -> float:
    chaves = sorted(T95)
    for c in chaves:
        if gl <= c:
            return T95[c]
    return Z95


def classificar_campanha(lucro_diario: list[float | None], *, dias_minimos: int = 7,
                         receita_reconciliada: bool = True) -> dict:
    """Classe de ROI com amostra. `lucro_diario` só de dias com janela FECHADA e
    receita reconciliada (vw_gads_arbitragem_campanha_dia.utilizavel_para_otimizacao).
    None = dia sem lucro apurável: não vira zero.
    """
    if not receita_reconciliada:
        return {"classe": "nao_elegivel", "motivo": "receita nao reconciliada"}
    dias = [v for v in lucro_diario if v is not None]
    if len(dias) < dias_minimos:
        return {"classe": "nao_elegivel", "motivo": f"{len(dias)} dia(s) apuravel(is) < {dias_minimos}"}
    m = statistics.fmean(dias)
    s = statistics.stdev(dias) if len(dias) > 1 else 0.0
    meia = _t(len(dias) - 1) * s / math.sqrt(len(dias))
    ic = (m - meia, m + meia)
    classe = "lucrativa" if ic[0] > 0 else "prejuizo" if ic[1] < 0 else "indeterminada"
    return {"classe": classe, "lucro_medio_dia": round(m, 4), "ic95": [round(ic[0], 4), round(ic[1], 4)],
            "dias": len(dias)}


def demo(seed: int = 20261014) -> dict:
    rnd = random.Random(seed)
    # modelos de funil sintéticos: (n campanhas lançadas, P(campanha de fato lucrativa))
    modelos = {"funil_A": (3, 0.40), "funil_B": (8, 0.40), "funil_C": (25, 0.40),
               "funil_D": (60, 0.55), "funil_E": (150, 0.40)}
    linhas = {}
    for nome, (n, p) in modelos.items():
        cont = {"lucrativa": 0, "prejuizo": 0, "indeterminada": 0, "nao_elegivel": 0}
        for _ in range(n):
            lucrativa = rnd.random() < p
            mu = rnd.uniform(5, 40) * (1 if lucrativa else -1)       # R$/dia sintético
            dias_vida = rnd.choice([3, 5, 10, 14, 21, 30])
            serie = [rnd.gauss(mu, 35.0) for _ in range(dias_vida)]
            # 15% dos dias sem receita reconciliada -> None (não zero)
            serie = [None if rnd.random() < 0.15 else v for v in serie]
            cont[classificar_campanha(serie)["classe"]] += 1
        avaliadas = cont["lucrativa"] + cont["prejuizo"] + cont["indeterminada"]
        linhas[nome] = {
            "lancadas": n, "p_verdadeira": p, **cont,
            "prop_lucrativa_entre_avaliadas": round(cont["lucrativa"] / avaliadas, 3) if avaliadas else None,
            "wilson95": [round(v, 3) for v in wilson(cont["lucrativa"], avaliadas)] if avaliadas else None,
        }
    return {
        "rotulo": "SINTETICO — desenho do relatorio, nao resultado da operacao",
        "modelos": linhas,
        "n_para_margem_10pp_p50": n_para_margem(0.5, 0.10),
        "n_para_margem_15pp_p50": n_para_margem(0.5, 0.15),
        "wilson_exemplos": {"1_de_2": wilson(1, 2), "2_de_3": wilson(2, 3), "20_de_50": wilson(20, 50)},
        "leitura": ("Com 3 ou 8 campanhas o intervalo cobre quase todo [0,1]; ordenar modelos pela "
                    "proporção observada premia o acaso. Mostrar proporção + Wilson + n, e "
                    "'indeterminada' como classe própria; sem limiar de vencedor."),
    }


if __name__ == "__main__":
    saida = demo()
    destino = sys.argv[1] if len(sys.argv) > 1 else "e5_resultado.json"
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(saida, fh, indent=1, ensure_ascii=False)
    print(json.dumps(saida, indent=1, ensure_ascii=False))
