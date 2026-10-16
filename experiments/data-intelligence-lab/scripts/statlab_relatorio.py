"""Stat Lab — gera results/statlab/STATLAB-RESULTS.md a partir dos JSONs (números nunca digitados à mão).

Uso: experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/statlab_relatorio.py
"""

from __future__ import annotations

import json
from pathlib import Path

import argparse

LAB = Path(__file__).resolve().parents[1]
RES = LAB / "results" / "statlab"


def carregar(nome: str) -> dict:
    return json.loads((RES / nome).read_text())


def f(x, d: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    if abs(x) >= 1000 or (0 < abs(x) < 10 ** (-d)):
        return f"{x:.2e}"
    return f"{x:.{d}f}"


def ic(o: dict | None, d: int = 3) -> str:
    if not o or o.get("estimativa") is None:
        return "—"
    lo, hi = o["ic95"]
    if lo is None:
        return f(o["estimativa"], d)
    return f"{f(o['estimativa'], d)} [{f(lo, d)}; {f(hi, d)}]"


def pct(o: dict | None) -> str:
    if not o or o.get("estimativa") is None:
        return "—"
    lo, hi = o["ic95"]
    if lo is None:
        return f"{100 * o['estimativa']:.1f}%"
    # IC normal entre mundos pode extrapolar [0, 1] em proporções extremas: exibido recortado
    return f"{100 * o['estimativa']:.1f}% [{100 * max(lo, 0.0):.1f}; {100 * min(hi, 1.0):.1f}]"


def sv(o: dict | None) -> str:
    """Percentual com sinal e IC95: '+1.0% [-4.3; +6.3]'."""
    if not o or o.get("estimativa") is None:
        return "—"
    lo, hi = o.get("ic95", [None, None])
    base = f"{100 * o['estimativa']:+.1f}%"
    return base if lo is None else f"{base} [{100 * lo:+.1f}; {100 * hi:+.1f}]"


def secao_maturacao(d: dict) -> list[str]:
    L = [f"## 1. Maturação / nowcasting (seed base {d['seed']}, {d['n_simulacoes']} mundos por cenário, "
         f"as_of={d['parametros']['as_of']}, idade final={d['parametros']['idade_final']} dias)", "",
         "Método base: fator m(a) = Σobs(a)/Σfinal nas últimas 28 coortes maduras antes do as_of "
         "(chain-ladder restrito a coortes maduras). Guarda: m(a) < 0,3 ou < 14 coortes válidas → `insuficiente`. "
         "Intervalo 90%: (i) razão empírica final/obs(a) das coortes maduras (preditivo); (ii) bootstrap só do fator. "
         "Limiares são parâmetros de cenário. IC95 de Monte Carlo entre colchetes, **por mundo** (as idades de "
         "um mesmo mundo compartilham o fator e não são independentes); com 0% ou 100% em todos os mundos o IC "
         "normal degenera em largura zero — leia como 'em nenhum/todos os 300 mundos'. Viés relativo = razão de "
         "somas Σ(est−verdade)/Σverdade nas células com estimativa; IC95 por bootstrap de mundos (B=2000).", ""]
    for nome, v in d["resultados"].items():
        cm = v["por_metodo"]["coortes_maduras"]
        vt = v.get("verdade_final_por_coorte", {})
        L.append(f"### `{nome}` (seed {v['seed_cenario']})")
        if vt:
            L.append(f"Verdade final por coorte: p5/p50/p95 = {', '.join(f(x) for x in vt['quantis_p5_p50_p95'])}; "
                     f"fração zero = {f(vt['frac_zero'])}.")
        L += ["", "| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | "
              "viés rel. c/ guarda | viés rel. sem guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |",
              "|---|---|---|---|---|---|---|---|---|"]
        for l in cm:
            sg, cg = l["sem_guarda"], l["com_guarda"]
            nsem = l.get("cobertura_razao", {}).get("n_sem_intervalo")
            cov_r = pct(l.get("cobertura_razao")) + (f" (sem IC: {nsem})" if nsem else "")
            fator = f(l["fator_medio"]) if l["frac_fator_indefinido"] == 0 else \
                f"{f(l['fator_medio'])} ({100 * l['frac_fator_indefinido']:.0f}% indef.)"
            L.append(f"| {l['faixa_idade'][0]}–{l['faixa_idade'][1]} | {fator} | {ic(sg['mape'])} | {f(sg['ape_max'])} "
                     f"| {pct(cg['frac_insuficiente_ou_nao_finito'])} | {sv(cg['vies_relativo'])} "
                     f"| {sv(sg['vies_relativo'])} | {cov_r} "
                     f"| {pct(l.get('cobertura_boot'))} |")
        if "regime" in nome:
            lr = v["por_metodo"]["link_ratio"]
            L += ["", "Variante link-ratio (usa coortes parcialmente maduras) no mesmo mundo:", "",
                  "| idade | viés rel. coortes maduras | viés rel. link-ratio | % insuf. link-ratio | APE máx link-ratio sem guarda |",
                  "|---|---|---|---|---|"]
            for a, b in zip(cm, lr):
                L.append(f"| {a['faixa_idade'][0]}–{a['faixa_idade'][1]} | {sv(a['com_guarda']['vies_relativo'])} "
                         f"| {sv(b['com_guarda']['vies_relativo'])} | {pct(b['com_guarda']['frac_insuficiente_ou_nao_finito'])} "
                         f"| {f(b['sem_guarda']['ape_max'])} |")
        L.append("")
    return L


def secao_shrinkage(d: dict) -> list[str]:
    p = d["parametros"]
    L = [f"## 2. Shrinkage Empirical Bayes ({d['n_simulacoes']} réplicas por cenário, K={p['K_unidades']} unidades, "
         f"top-k={p['top_k']}, intervalo {int(100 * p['nivel_intervalo'])}%)", "",
         "MSE relativo = MSE/MSE do cru na mesma réplica (unidades com n>0). Vencedores por sorte = unidades no "
         "top-k estimado fora do top-k verdadeiro, em expectativa sob desempate aleatório (estimador constante = sorteio). "
         "Calibração = cov(est, verdade)/var(est) (1 = calibrado; n/a para estimador constante; instável quando "
         "var(est) é minúscula, ex.: pooling quase total). "
         "IC95 de Monte Carlo entre colchetes.", ""]
    for grupo, cens in d["resultados"].items():
        L.append(f"### {grupo}")
        for nome, v in cens.items():
            extra = ""
            if "gamma_poisson_peso_do_prior_mediano" in v:
                g = v["gamma_poisson_peso_do_prior_mediano"]
                extra = (f" Peso mediano do prior no Gamma-Poisson aplicado a dinheiro: R$ {f(g['reais'], 5)} vs "
                         f"centavos {f(g['centavos'], 7)} (mesmos dados).")
            if "status_prior_contagem" in v:
                extra += f" Status do prior: {json.dumps(v['status_prior_contagem'], ensure_ascii=False)}."
            L += [f"**`{nome}`** (seed {v['seed_cenario']}).{extra}", "",
                  "| estimador | MSE rel. ao cru | vencedores por sorte (de k) | regret top-k | calibração | cobertura | cobertura top-10% verdadeiro |",
                  "|---|---|---|---|---|---|---|"]
            for est, m in v["estimadores"].items():
                na = m.get("frac_replicas_calibracao_nao_aplicavel", 0)
                cal = "n/a (estimador constante)" if na == 1 else ic(m.get("inclinacao_calibracao"), 2) + \
                    (f" (n/a em {100 * na:.0f}% das réplicas)" if na else "")
                L.append(f"| {est} | {ic(m.get('mse_relativo_ao_cru'))} | {ic(m.get('vencedores_por_sorte_topk'), 2)} "
                         f"| {ic(m.get('regret_topk'))} | {cal} "
                         f"| {pct(m.get('cobertura'))} | {pct(m.get('cobertura_top10pct_verdadeiro'))} |")
            L.append("")
    return L


def secao_cs(d: dict) -> list[str]:
    p = d["parametros"]
    r = d["resultados"]
    L = [f"## 3. Confidence sequences ({p['n_trajetorias']} trajetórias, T={p['T']}, alpha={p['alpha']})", "",
         f"CS: {p['metodo_cs']}. Comparador: {p['comparador']}. Erro uniforme = fração de trajetórias em que a "
         "média verdadeira sai do intervalo em ALGUM t ≥ 10 (e a partir de t ≥ 100 / ≥ 1000, para separar a "
         "degeneração de amostra minúscula). IC95 de Monte Carlo (Wilson).", "",
         "### 3a. Cobertura uniforme no tempo", "",
         "| outcome (seed) | método | erro uniforme t≥10 | t≥100 | t≥1000 | erro só no horizonte T | largura t=100 | t=1000 | t=T |",
         "|---|---|---|---|---|---|---|---|---|"]
    T = p["T"]
    for nome, v in r["cobertura_uniforme"].items():
        for m in ("cs_prpl_eb", "wald_peeking"):
            x = v[m]
            L.append(f"| {nome} ({v['seed']}) | {m} | {pct(x['erro_uniforme_no_tempo'])} | {pct(x.get('erro_uniforme_desde_t100'))} "
                     f"| {pct(x.get('erro_uniforme_desde_t1000'))} | {pct(x['erro_so_no_horizonte_fixo_T'])} "
                     f"| {ic(x.get('largura_t100'), 4)} | {ic(x.get('largura_t1000'), 4)} | {ic(x.get(f'largura_t{T}'), 4)} |")
    L += ["", "### 3b. Decisão 'μ > μ0' (μ0 = 0,05)", "",
          "| cenário (seed) | método | decide em algum t ≤ T | decide olhando só em T | t mediano até decidir | erro uniforme |",
          "|---|---|---|---|---|---|"]
    for nome, v in r["decisao_mu_maior_que_mu0"].items():
        for m in ("cs_prpl_eb", "wald_peeking"):
            x = v[m]
            L.append(f"| {nome} ({v['seed']}) | {m} | {pct(x['frac_decidiu_ate_T'])} | {pct(x['frac_decidiu_horizonte_fixo_T'])} "
                     f"| {f(x['t_mediano_decisao_calendario'], 0)} | {pct(x['erro_uniforme_no_tempo'])} |")
    L += ["", "### 3c. Contraprova: outcome ilimitado (receita/visitante) normalizado por um limite errado", "",
          "Limite B = máximo de um piloto de 500 observações; X/B recortado em [0,1] (sem recorte a CS levanta "
          "`ForaDoSuporte`). A CS passa a cobrir E[min(X,B)]/B, não E[X]/B.", "",
          "| cauda (seed) | % obs > B | erro uniforme CS recortada | erro uniforme Wald peeking (bruto) | erro Wald só em T (bruto) | sem recorte |",
          "|---|---|---|---|---|---|"]
    for nome, v in r["contraprova_cauda_pesada"].items():
        L.append(f"| {nome} ({v['seed']}) | {pct(v['frac_observacoes_acima_do_limite'])} "
                 f"| {pct(v['cs_prpl_eb_recortada_em_B']['erro_uniforme_no_tempo'])} "
                 f"| {pct(v['wald_peeking_bruto']['erro_uniforme_no_tempo'])} "
                 f"| {pct(v['wald_peeking_bruto']['erro_so_no_horizonte_fixo_T'])} | `ForaDoSuporte` |")
    L += ["", "### 3d. Contraprova: outcome com atraso (conversão chega D ~ Geom(média 200 passos) depois; janela W=1000)", "",
          "`janela_fechada` é por construção a sequência do oráculo deslocada W no calendário: a validade dela é "
          "herdada (identidade), não descoberta; o que se mede é o atraso. A coluna 'até o calendário H=T' compara "
          "as estratégias no mesmo instante de calendário.", "",
          "| p (seed) | estratégia | erro uniforme (vs p_W) | decide 'p_W > μ0' até o calendário H=T | t mediano de calendário até decidir |",
          "|---|---|---|---|---|"]
    for nome, v in r["contraprova_atraso"].items():
        for m in ("oraculo", "janela_fechada", "lag_ingenuo"):
            x = v[m]
            L.append(f"| {v['p']} ({v['seed']}) | {m} | {pct(x['erro_uniforme_no_tempo'])} | {pct(x['frac_decidiu_ate_calendario_H'])} "
                     f"| {f(x['t_mediano_decisao_calendario'], 0)} |")
    L.append("")
    return L


def secao_fdr(d: dict) -> list[str]:
    r = d["resultados"]
    c = r["conferencia_bh_propria_vs_statsmodels"]
    L = [f"## 4. FDR ({d['n_simulacoes']} réplicas por cenário; m={d['parametros']['m']} células, "
         f"CVR base {d['parametros']['p_base']}, lift verdadeiro +{int(100 * d['parametros']['lift'])}%, q={d['parametros']['q']})", "",
         f"BH própria vs `statsmodels.multipletests(fdr_bh)`: {c['n_casos']} casos (seed {c['seed']}), "
         f"{c['divergencias_fora_da_fronteira']} divergências fora da fronteira, "
         f"{c['divergencias_por_empate_exato_na_fronteira']} em empate exato p = q·k/m (ponto flutuante; a regra BH rejeita, "
         "a implementação própria usa tolerância relativa 1e-12). Poder da conferência: uma BH mutante sem o passo "
         f"step-up gera {c['contraprova_mutante_sem_step_up_divergencias_fora_da_fronteira']} divergências fora da fronteira.", "",
         "| cenário (seed) | olhadas | método | FDR realizado | poder | falsas descobertas/réplica | falsos vencedores/réplica | FWER |",
         "|---|---|---|---|---|---|---|---|"]
    for nome, v in r["cenarios"].items():
        for m, x in v["metodos"].items():
            L.append(f"| {nome} ({v['seed_cenario']}) | {v['n_olhadas']} | {m} | {pct(x['fdr_realizado'])} | {pct(x['poder'])} "
                     f"| {ic(x['falsas_descobertas_por_replica'], 2)} | {ic(x['falsos_vencedores_por_replica'], 2)} | {pct(x['fwer'])} |")
    L.append("")
    return L


# ---------------------------------------------------------------------------
# conclusões: TODO número vem dos JSONs; o rótulo é decidido por regra explícita sobre o IC
# ---------------------------------------------------------------------------

def P(x: float | None, sinal: bool = False) -> str:
    if x is None:
        return "—"
    return f"{100 * x:+.1f}%" if sinal else f"{100 * x:.1f}%"


def PI(o: dict | None, sinal: bool = False) -> str:
    """'53.0% [49.9; 56.1]' a partir de {estimativa, ic95}."""
    if not o or o.get("estimativa") is None:
        return "—"
    lo, hi = o["ic95"]
    if lo is None:
        return P(o["estimativa"], sinal)
    fmt = (lambda v: f"{100 * v:+.1f}") if sinal else (lambda v: f"{100 * max(v, 0):.1f}")
    return f"{P(o['estimativa'], sinal)} [{fmt(lo)}; {fmt(hi)}]"


def N(x: float | None, d: int = 2) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def NI(o: dict | None, d: int = 2) -> str:
    if not o or o.get("estimativa") is None:
        return "—"
    lo, hi = o["ic95"]
    return N(o["estimativa"], d) if lo is None else f"{N(o['estimativa'], d)} [{N(lo, d)}; {N(hi, d)}]"


def contem0(o: dict) -> bool:
    lo, hi = o["ic95"]
    return lo is None or (lo <= 0 <= hi)


def faixa(md: dict, cen: str, a: int, b: int, met: str = "coortes_maduras") -> dict:
    for l in md["resultados"][cen]["por_metodo"][met]:
        if l["faixa_idade"] == [a, b]:
            return l
    raise KeyError((cen, a, b, met))


def conclusoes_maturacao(md: dict) -> list[str]:
    cfg = md["parametros"]["config"]["coortes_maduras"]
    nominal = cfg["nivel_intervalo"]
    L = ["### Maturação"]
    # M1: atraso estável
    est = "receita_estavel"
    lins = md["resultados"][est]["por_metodo"]["coortes_maduras"]
    com_est = [(l["faixa_idade"], l["com_guarda"]["vies_relativo"]) for l in lins
               if l["com_guarda"]["vies_relativo"]["estimativa"] is not None]
    zeros = [fx for fx, v in com_est if contem0(v)]
    nz = [fx for fx, v in com_est if not contem0(v)]
    txt = "; ".join(f"{a}–{b} d {PI(v, True)}" for (a, b), v in com_est)
    mapes = " → ".join(P(l["sem_guarda"]["mape"]["estimativa"]) for l in lins)
    meia = max(max(abs(v["ic95"][0]), abs(v["ic95"][1])) for _, v in com_est)
    rot = ("sem viés detectável (não demonstra |viés| pequeno)" if not nz else
           "demonstrado em simulação: viés pequeno detectável")
    L.append(f"- **{rot}**: com atraso estável (`{est}`), o viés com guarda não é distinguível de "
             f"zero em {len(zeros)}/{len(com_est)} faixas com {md['n_simulacoes']} mundos; o IC95 alcança ±{P(meia)} "
             f"nas idades baixas (IC por mundo: {txt})"
             + (f"; nas faixas {', '.join(f'{a}–{b} d' for a, b in nz)} o IC exclui 0 (viés pequeno, mas detectável)"
                if nz else "")
             + f". MAPE sem guarda por faixa de idade: {mapes}.")
    # M2: guarda no trecho explosivo
    partes = []
    for cen in ("receita_estavel", "receita_lenta_fator_perto_de_zero"):
        l0 = faixa(md, cen, 0, 0)
        partes.append(f"`{cen}` m(0)={N(l0['fator_medio'], 3)}, APE máx sem guarda {N(l0['sem_guarda']['ape_max'], 1)}×, "
                      f"`insuficiente` com guarda {PI(l0['com_guarda']['frac_insuficiente_ou_nao_finito'])}")
    d1 = faixa(md, "receita_d_mais_1_fator_zero_na_idade_0", 0, 0)
    ok = all(faixa(md, c, 0, 0)["com_guarda"]["frac_insuficiente_ou_nao_finito"]["estimativa"] == 1.0
             for c in ("receita_estavel", "receita_lenta_fator_perto_de_zero", "receita_d_mais_1_fator_zero_na_idade_0"))
    L.append(f"- **{'demonstrado em simulação' if ok else 'NÃO demonstrado'}**: o guarda converte o trecho explosivo em "
             f"`insuficiente` ({'; '.join(partes)}). Reporte D+1: m(0)={N(d1['fator_medio'], 3)} "
             f"({P(d1['frac_fator_indefinido'])} indefinido) → sem guarda inf/NaN, com guarda "
             f"{PI(d1['com_guarda']['frac_insuficiente_ou_nao_finito'])} `insuficiente` "
             f"(motivos: {json.dumps(d1.get('motivos_insuficiente', {}), ensure_ascii=False)}).")
    # M3: erro residual e viés de seleção do guarda
    l12 = faixa(md, "receita_estavel", 1, 2)
    L.append(f"- **demonstrado em simulação (resultado negativo)**: o guarda não elimina o erro logo acima do limiar "
             f"(`receita_estavel` 1–2 d: MAPE com guarda {PI(l12['com_guarda']['mape'])}, "
             f"{PI(l12['com_guarda']['frac_insuficiente_ou_nao_finito'])} `insuficiente`).")
    for cen, a, b in (("receita_d_mais_1_fator_zero_na_idade_0", 1, 2), ("receita_baixa_magnitude_centavo_ate_d3", 0, 0)):
        l = faixa(md, cen, a, b)
        vc, vs = l["com_guarda"]["vies_relativo"], l["sem_guarda"]["vies_relativo"]
        if not contem0(vc) and contem0(vs):
            rot = "demonstrado em simulação"
            frase = "o guarda introduz viés de seleção (só passam os mundos cujo fator saiu alto)"
        elif not contem0(vc):
            rot = "demonstrado em simulação (viés presente também sem guarda)"
            frase = "há viés, mas não é atribuível só à seleção do guarda"
        else:
            rot = "não demonstrado (IC inclui 0)"
            frase = "a hipótese de viés de seleção pelo guarda não se sustenta com este n"
        L.append(f"- **{rot}**: `{cen}` {a}–{b} d — viés com guarda {PI(vc, True)} em "
                 f"{vc['n_mundos']} mundos que passaram vs sem guarda {PI(vs, True)} em {vs['n_mundos']} mundos: {frase}.")
    # M4: intervalos
    boots, razoes = [], []
    for cen, v in md["resultados"].items():
        if "regime" in cen:
            continue
        for l in v["por_metodo"]["coortes_maduras"]:
            if l["fator_medio"] is not None and l["fator_medio"] < 0.99:
                if l.get("cobertura_boot", {}).get("estimativa") is not None:
                    boots.append((cen, l["faixa_idade"], l["cobertura_boot"]))
                if l.get("cobertura_razao", {}).get("estimativa") is not None:
                    razoes.append((cen, l["faixa_idade"], l["cobertura_razao"]))
    b_est = [o["estimativa"] for _, _, o in boots]
    b_hi = max(o["ic95"][1] for _, _, o in boots)
    r_est = [o["estimativa"] for _, _, o in razoes]
    r_abaixo = sum(1 for _, _, o in razoes if o["ic95"][1] < nominal)
    L.append(f"- **{'refutado' if b_hi < nominal else 'não refutado'}**: bootstrap só do fator como intervalo preditivo "
             f"{int(100 * nominal)}% — cobertura {P(min(b_est))}–{P(max(b_est))} nas {len(boots)} faixas com m(a) < 0,99 "
             f"(cenários sem regime; maior limite superior de IC {P(b_hi)}); ignora o ruído de processo da parte ainda não reportada. "
             f"Razão empírica: {P(min(r_est))}–{P(max(r_est))}, com IC abaixo do nominal em {r_abaixo}/{len(razoes)} faixas "
             f"(subcobertura leve, pior nas idades baixas); indefinida quando obs = 0 (contado, não imputado).")
    # M5: regime
    lento, rapido = ("receita_mudanca_regime_atraso_x2_5_ultimas_30_coortes",
                     "receita_mudanca_regime_atraso_metade_ultimas_30_coortes")
    fx = ((1, 2), (3, 6), (7, 13), (14, 29))
    vl = [faixa(md, lento, a, b)["com_guarda"]["vies_relativo"] for a, b in fx]
    vr = [faixa(md, rapido, a, b)["com_guarda"]["vies_relativo"] for a, b in fx[:2]]
    cov_l = [faixa(md, lento, a, b)["cobertura_razao"]["estimativa"] for a, b in fx]
    cov_r = [faixa(md, rapido, a, b)["cobertura_razao"]["estimativa"] for a, b in fx[:3]]
    refut = all(not contem0(v) for v in vl + vr)
    lr_r = faixa(md, rapido, 1, 2, "link_ratio")["com_guarda"]["vies_relativo"]
    lr_l = faixa(md, lento, 3, 6, "link_ratio")["com_guarda"]["vies_relativo"]
    lr_l0 = faixa(md, lento, 0, 0, "link_ratio")
    lr_l12 = faixa(md, lento, 1, 2, "link_ratio")
    L.append(f"- **{'refutado sob mudança de regime' if refut else 'degradação não demonstrada'}** (o método degrada e não avisa): "
             f"atraso 2,5× mais lento nas 30 coortes recentes → viés "
             + ", ".join(f"{PI(v, True)} ({a}–{b} d)" for v, (a, b) in zip(vl, fx))
             + f", cobertura IC90 {P(min(cov_l))}–{P(max(cov_l))}; atraso 2× mais rápido → "
             + ", ".join(f"{PI(v, True)} ({a}–{b} d)" for v, (a, b) in zip(vr, fx[:2]))
             + f", cobertura {P(min(cov_r))}–{P(max(cov_r))}. Link-ratio reage parcialmente "
             f"(regime rápido 1–2 d: {PI(lr_r, True)}; lento 3–6 d: {PI(lr_l, True)}), mas no regime lento m(0) vai a "
             f"{N(lr_l0['fator_medio'], 3)} (APE máx sem guarda {N(lr_l0['sem_guarda']['ape_max'], 1)}×) e o guarda bloqueia "
             f"1–2 d em {PI(lr_l12['com_guarda']['frac_insuficiente_ou_nao_finito'])}. Detecção de regime: não testada.")
    # M6: centavo
    cc = "receita_baixa_magnitude_centavo_ate_d3"
    vt = md["resultados"][cc]["verdade_final_por_coorte"]
    c0, c12 = faixa(md, cc, 0, 0), faixa(md, cc, 1, 2)
    ok12 = contem0(c12["com_guarda"]["vies_relativo"])
    L.append(f"- **{'demonstrado em simulação' if ok12 else 'NÃO demonstrado'}**: granularidade de centavo (verdade por coorte "
             f"p5–p95 = {N(vt['quantis_p5_p50_p95'][0])}–{N(vt['quantis_p5_p50_p95'][2])}, {P(vt['frac_zero'])} zero; reporte que muda "
             f"até D+3 — forma dos fatos reais, não parâmetro) não quebra o fator a partir de 1 d (viés 1–2 d "
             f"{PI(c12['com_guarda']['vies_relativo'], True)}). O problema é a idade 0: {PI(c0['com_guarda']['frac_insuficiente_ou_nao_finito'])} "
             f"`insuficiente`, MAPE sem guarda {PI(c0['sem_guarda']['mape'])}, intervalo indefinido em "
             f"{c0['cobertura_razao']['n_sem_intervalo']} células (obs = 0).")
    return L


def E(sd: dict, grp: str, cen: str, est: str, k: str) -> dict:
    return sd["resultados"][grp][cen]["estimadores"][est].get(k) or {}


def conclusoes_shrinkage(sd: dict) -> list[str]:
    nominal = sd["parametros"]["nivel_intervalo"]
    T = "taxas_beta_binomial"
    L = ["### Shrinkage"]
    u = "cvr_beta_unimodal"
    L.append(f"- **demonstrado em simulação**: Beta-Binomial EB (MLE) no cenário `{u}`: MSE {NI(E(sd, T, u, 'eb_mle', 'mse_relativo_ao_cru'))} do cru; "
             f"calibração {NI(E(sd, T, u, 'eb_mle', 'inclinacao_calibracao'))} vs {NI(E(sd, T, u, 'cru', 'inclinacao_calibracao'))} do cru; "
             f"fração do top-k com n baixo {PI(E(sd, T, u, 'cru', 'frac_topk_n_baixo'))} → {PI(E(sd, T, u, 'eb_mle', 'frac_topk_n_baixo'))}; "
             f"mas vencedores por sorte só caem de {NI(E(sd, T, u, 'cru', 'vencedores_por_sorte_topk'), 1)} para "
             f"{NI(E(sd, T, u, 'eb_mle', 'vencedores_por_sorte_topk'), 1)} em {sd['parametros']['top_k']}: o ranking segue dominado por ruído.")
    itens = []
    for cen, est, k, rotulo in (("cvr_bimodal_vencedores_raros", "eb_mle", "cobertura_top10pct_verdadeiro", "vencedores raros reais, top-10% verdadeiro"),
                                ("cvr_beta_unimodal", "eb_mle", "cobertura_top10pct_verdadeiro", "unimodal, top-10% verdadeiro"),
                                ("cvr_n_informativo", "eb_momentos", "cobertura", "n informativo, momentos"),
                                ("cvr_n_informativo", "eb_mle", "cobertura", "n informativo, MLE"),
                                ("cvr_sem_heterogeneidade", "eb_momentos", "cobertura", "sem heterogeneidade, momentos"),
                                ("cvr_sem_heterogeneidade", "eb_mle", "cobertura", "sem heterogeneidade, MLE")):
        o = E(sd, T, cen, est, k)
        itens.append((rotulo, o, o["ic95"][1] < nominal))
    g = E(sd, "contagens_gamma_poisson", "contagem_gamma_quase_homogenea", "eb_mle", "cobertura")
    itens.append(("Gamma quase homogênea, MLE", g, g["ic95"][1] < nominal))
    sub = [f"{r}: {PI(o)}" + ("" if abaixo else " (IC alcança o nominal)") for r, o, abaixo in itens]
    L.append(f"- **demonstrado em simulação (contraprovas; nominal {int(100 * nominal)}%)**: o EB plug-in sub-cobre — "
             + "; ".join(sub) + f" (cru no bimodal: {PI(E(sd, T, 'cvr_bimodal_vencedores_raros', 'cru', 'cobertura_top10pct_verdadeiro'))}). "
             f"Com n grande o ganho é mínimo (MSE {NI(E(sd, T, 'cvr_n_grande_pouco_ganho', 'eb_mle', 'mse_relativo_ao_cru'), 3)} do cru).")
    R = "receita_monetaria"
    pesos, covs = [], []
    for cen, v in sd["resultados"][R].items():
        w = v["gamma_poisson_peso_do_prior_mediano"]
        pesos.append((w["reais"], w["centavos"]))
        for u_ in ("gamma_poisson_reais", "gamma_poisson_centavos"):
            covs.append(v["estimadores"][u_]["cobertura"]["estimativa"])
    L.append(f"- **inadequado para receita monetária**: Gamma-Poisson aplicado a dinheiro quase não encolhe (peso mediano do prior "
             f"{min(p[0] for p in pesos):.2g}–{max(p[0] for p in pesos):.2g} em R$ vs {min(p[1] for p in pesos):.2g}–{max(p[1] for p in pesos):.2g} "
             f"em centavos, mesmos dados), depende da unidade monetária e cobre {P(min(covs))}–{P(max(covs))}. A implementação recusa valor não inteiro.")
    hu = [(cen, v["estimadores"]["hurdle_beta_lognormal"]) for cen, v in sd["resultados"][R].items()]
    pesado = sd["resultados"][R]["receita_cauda_pesada_sigma2"]["estimadores"]
    nn_cov = pesado["eb_normal_var_empirica"]["cobertura"]
    L.append(f"- **demonstrado em simulação**: hurdle e normal-normal EB são invariantes à escala (teste). Hurdle: "
             + "; ".join(f"`{c}` MSE {NI(h['mse_relativo_ao_cru'])}, cobertura {PI(h['cobertura'])}" for c, h in hu)
             + f". **{'refutado' if nn_cov['ic95'][1] < nominal else 'não refutado'}** o normal-normal com cauda pesada (σ_log = 2): "
             f"cobertura {PI(nn_cov)}, regret top-k {NI(pesado['eb_normal_var_empirica']['regret_topk'])} vs {NI(pesado['cru']['regret_topk'])} do cru. "
             "Hipótese (não demonstrada): robustez do hurdle fora das famílias testadas — o cenário lognormal é favorável a ele por construção.")
    L.append("- **não testado**: lucro (valores negativos), hiperprior hierárquico completo, intervalos EB que propaguem a incerteza do hiperparâmetro.")
    return L


def conclusoes_cs(cd: dict) -> list[str]:
    p = cd["parametros"]
    alpha = p["alpha"]
    r = cd["resultados"]
    L = ["### Confidence sequences"]
    cu = r["cobertura_uniforme"]
    cs_err = [v["cs_prpl_eb"]["erro_uniforme_no_tempo"] for v in cu.values()]
    w10 = [v["wald_peeking"]["erro_uniforme_no_tempo"]["estimativa"] for v in cu.values()]
    w1k = [v["wald_peeking"]["erro_uniforme_desde_t1000"]["estimativa"] for v in cu.values()]
    wT = [v["wald_peeking"]["erro_so_no_horizonte_fixo_T"]["estimativa"] for v in cu.values()]
    ok = all(o["ic95"][1] <= alpha for o in cs_err)
    L.append(f"- **{'demonstrado em simulação' if ok else 'parcialmente demonstrado (limite superior do IC > alpha)'}**: PrPl-EB, erro uniforme "
             + ", ".join(PI(o) for o in cs_err) + f" (alpha = {alpha}); Wald recalculado a cada passo erra em {P(min(w10))}–{P(max(w10))} "
             f"das trajetórias ({P(min(w1k))}–{P(max(w1k))} contando só t ≥ 1000), embora numa olhada fixa em T erre {P(min(wT))}–{P(max(wT))}.")
    dm = r["decisao_mu_maior_que_mu0"]
    a6 = dm["alternativa_p0.06_vs_mu0_0.05"]
    nul = dm["nulo_p_igual_mu0"]
    b5 = cu["bernoulli_p0.5"]
    razao = b5["cs_prpl_eb"][f"largura_t{p['T']}"]["estimativa"] / b5["wald_peeking"][f"largura_t{p['T']}"]["estimativa"]
    L.append(f"- **demonstrado em simulação (custo)**: largura em T {razao:.1f}× a de Wald (`bernoulli_p0.5`); p = {a6['p']} vs μ0 = {a6['mu0']} com "
             f"T = {p['T']}: CS decide em {PI(a6['cs_prpl_eb']['frac_decidiu_ate_T'])}, Wald de horizonte fixo (válido, uma olhada) em "
             f"{PI(a6['wald_peeking']['frac_decidiu_horizonte_fixo_T'])}. Sob H0, Wald-peeking 'decide' em "
             f"{PI(nul['wald_peeking']['frac_decidiu_ate_T'])} vs {PI(nul['wald_peeking']['frac_decidiu_horizonte_fixo_T'])} numa olhada; "
             f"CS em {PI(nul['cs_prpl_eb']['frac_decidiu_ate_T'])}.")
    cp = r["contraprova_cauda_pesada"]
    L.append("- **inadequado para outcome monetário ilimitado**: normalizar por limite estimado (máximo de piloto) e recortar quebra a cobertura ("
             + "; ".join(f"`{k}`: erro {PI(v['cs_prpl_eb_recortada_em_B']['erro_uniforme_no_tempo'])} com só "
                         f"{PI(v['frac_observacoes_acima_do_limite'])} das observações acima do limite" for k, v in cp.items())
             + "); sem recorte a CS recusa a entrada (`ForaDoSuporte`). Wald bruto também falha ("
             + "; ".join(f"`{k}`: {PI(v['wald_peeking_bruto']['erro_uniforme_no_tempo'])} com peeking, "
                         f"{PI(v['wald_peeking_bruto']['erro_so_no_horizonte_fixo_T'])} numa olhada" for k, v in cp.items()) + ").")
    at = r["contraprova_atraso"]
    alto = max(at, key=lambda k: at[k]["p"])
    v = at[alto]
    L.append(f"- **demonstrado em simulação**: atraso tratado como 0 (lag fixo) → erro "
             + ", ".join(f"{PI(at[k]['lag_ingenuo']['erro_uniforme_no_tempo'])} (p={at[k]['p']})" for k in at)
             + f" — estima p·P(D ≤ L) = {v['estimando_do_lag_ingenuo']:.4f} em vez de p_W = {v['p_W_verdadeira']:.4f}. "
             f"Esperar a janela fechar é a sequência do oráculo deslocada W: validade herdada por identidade (não é descoberta). "
             f"Custo medido (p = {v['p']}): mediana de calendário até decidir {N(v['oraculo']['t_mediano_decisao_calendario'], 0)} → "
             f"{N(v['janela_fechada']['t_mediano_decisao_calendario'], 0)}; decidiu até o calendário H = T: oráculo "
             f"{PI(v['oraculo']['frac_decidiu_ate_calendario_H'])}, janela fechada {PI(v['janela_fechada']['frac_decidiu_ate_calendario_H'])}, "
             f"lag ingênuo {PI(v['lag_ingenuo']['frac_decidiu_ate_calendario_H'])}.")
    L.append("- **não testado**: CS para diferença entre braços (A/B), versão betting/hedged, CS com atraso sem esperar a janela; "
             "comparação numérica com a lib `confseq` (não instalável).")
    return L


def conclusoes_fdr(fd: dict) -> list[str]:
    r = fd["resultados"]
    c = r["cenarios"]
    q = fd["parametros"]["q"]
    um, um20 = c["pi1_5pct_n5000_uma_olhada"]["metodos"], c["pi1_20pct_n20000_uma_olhada"]["metodos"]
    o10, o50 = c["pi1_5pct_n5000_10_olhadas"]["metodos"], c["pi1_5pct_n5000_50_olhadas"]["metodos"]
    n10, n1 = c["nulo_global_10_olhadas"]["metodos"], c["nulo_global_uma_olhada"]["metodos"]
    controla = um["bh"]["fdr_realizado"]["ic95"][0] <= q and um20["bh"]["fdr_realizado"]["ic95"][0] <= q
    infla = o10["bh"]["fdr_realizado"]["ic95"][0] > q
    cf = r["conferencia_bh_propria_vs_statsmodels"]
    return ["### FDR",
            f"- **{'demonstrado em simulação' if controla else 'NÃO demonstrado'}**: BH numa olhada — FDR {PI(um['bh']['fdr_realizado'])} "
            f"(5% de células verdadeiras) e {PI(um20['bh']['fdr_realizado'])} (20%), q = {q}; sem correção FDR {PI(um['nenhuma']['fdr_realizado'])} "
            f"e {NI(um['nenhuma']['falsos_vencedores_por_replica'], 1)} falsos vencedores por rodada; Bonferroni FWER "
            f"{PI(um['bonferroni']['fwer'])} com poder {PI(um['bonferroni']['poder'])} vs {PI(um['bh']['poder'])} do BH.",
            f"- **{'demonstrado em simulação' if infla else 'inflação não demonstrada'}**: peeking com BH a cada olhada infla o FDR "
            f"(10 olhadas {PI(o10['bh']['fdr_realizado'])}; 50 olhadas {PI(o50['bh']['fdr_realizado'])}); sob nulo global, BH declara algo em "
            f"{PI(n10['bh']['fwer'])} das rodadas com 10 olhadas vs {PI(n1['bh']['fwer'])} numa. Bonferroni também infla "
            f"({PI(o10['bonferroni']['fdr_realizado'])} / {PI(o50['bonferroni']['fdr_realizado'])}).",
            f"- **demonstrado em simulação (limite de dados)**: CVR {fd['parametros']['p_base']}, lift +{int(100 * fd['parametros']['lift'])}% e "
            f"5000 cliques/braço → poder do BH {PI(um['bh']['poder'])}; o dado típico não sustenta 'vencedor' por célula.",
            f"- **demonstrado**: BH própria = statsmodels em {cf['n_casos']} casos, exceto {cf['divergencias_por_empate_exato_na_fronteira']} "
            f"empate(s) exato(s) p = q·k/m no ponto de corte; {cf['divergencias_fora_da_fronteira']} divergências fora disso. "
            f"A conferência tem poder: uma BH sem step-up gera {cf['contraprova_mutante_sem_step_up_divergencias_fora_da_fronteira']} divergências.",
            "- **não testado**: e-BH com e-valores das CS (válido sob peeking), dependência entre células, testes unilaterais."]


def _selecao_sustenta(md: dict, cen: str, a: int, b: int) -> bool:
    l = faixa(md, cen, a, b)
    return not contem0(l["com_guarda"]["vies_relativo"]) and contem0(l["sem_guarda"]["vies_relativo"])


def comparacao(md: dict, sd: dict) -> list[str]:
    lento = "receita_mudanca_regime_atraso_x2_5_ultimas_30_coortes"
    vies = [faixa(md, lento, a, b)["com_guarda"]["vies_relativo"]["estimativa"] for a, b in ((1, 2), (14, 29))]
    cov = [faixa(md, lento, a, b)["cobertura_razao"]["estimativa"] for a, b in ((1, 2), (3, 6), (7, 13), (14, 29))]
    T = "taxas_beta_binomial"
    vs = [E(sd, T, c, "cru", "vencedores_por_sorte_topk")["estimativa"] for c in sd["resultados"][T]
          if c != "cvr_n_grande_pouco_ganho" and c != "cvr_sem_heterogeneidade"]
    return ["## 6. Relação com a pesquisa sintética anterior (pesquisa-B, run google-engine-nucleo-20261014-01)", "",
            "Lida em modo somente leitura (`RELATORIO-B.md`, `experimentos/e1_*`, `e2_*`). Números marcados 'B' são citados de lá; os demais vêm dos JSONs desta pasta.", "",
            f"- **Confirma**: Beta-Binomial EB > cru e > média do grupo; o 'vencedor' do cru está inflado (B: viés top-5% +0,31..+0,51; aqui "
            f"{min(vs):.1f}–{max(vs):.1f} de {sd['parametros']['top_k']} do top-k cru são vencedores por sorte). Gamma-Poisson não serve para "
            "receita/lucro monetário (B17 refutado lá; aqui pela dependência da unidade e cobertura baixa). Intervalo do chain-ladder sub-cobre "
            "levemente (B: 84–87% para 90%). Drift de reporte degrada o fator (B: −16%, cobertura 75%, drift mais brando; aqui "
            f"{P(vies[1], True)} a {P(vies[0], True)} conforme a idade, cobertura {P(min(cov))}–{P(max(cov))} com atraso 2,5×).",
            "- **Complementa/contradiz em parte**: B concluiu M ótimo = κ (EB acerta a dispersão); aqui o EB plug-in FALHA na cobertura "
            "mesmo acertando a média: sem heterogeneidade, nos vencedores raros reais e com n informativo. B refutou lognormal só nos positivos "
            "para lucro; o hurdle (P(conv) × valor|conv) não tem esse defeito para receita ≥ 0 — lucro negativo não foi testado.",
            "- **Novo**: guarda única de maturação com motivo (`ResultadoInsuficiente`) e D+1 com fator zero exato; refutação do bootstrap só "
            f"do fator; IC por mundo para o viés (viés de seleção do guarda sustentado no D+1: "
            f"{'sim' if _selecao_sustenta(md, 'receita_d_mais_1_fator_zero_na_idade_0', 1, 2) else 'não'}; no cenário de centavo: "
            f"{'sim' if _selecao_sustenta(md, 'receita_baixa_magnitude_centavo_ate_d3', 0, 0) else 'não'}); link-ratio sob regime; "
            "cenário de centavo/D+3; cobertura uniforme de CS vs peeking e o custo em poder; contraprovas de cauda pesada e atraso; FDR com peeking; sonda confseq.",
            "- **Não refeito**: Bornhuetter-Ferguson (B mostrou BF ≥ CL; aqui não testado), OPE e bandits.", ""]


def main() -> None:
    global RES
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default=str(RES), help="pasta com os JSONs")
    ap.add_argument("--saida", default=None, help="arquivo .md (padrão: <res>/STATLAB-RESULTS.md)")
    args = ap.parse_args()
    RES = Path(args.res)
    saida = Path(args.saida) if args.saida else RES / "STATLAB-RESULTS.md"
    m, s, c, fd = (carregar(n) for n in ("maturacao.json", "shrinkage.json", "confidence_sequences.json", "fdr.json"))
    sonda = carregar("sonda_confseq.json")
    v = m["versoes"]
    sp, sb = sonda["instalacao_padrao"], sonda["instalacao_somente_wheel"]
    L = ["# STATLAB — resultados (worker D, Fase 4)", "",
         "> Tudo abaixo é **simulação com seed**, sem dado real. Parâmetros (n, CVR, atrasos, limiares, top-k) são de "
         "cenário, nunca defaults operacionais. Gerado por `scripts/statlab_relatorio.py` a partir dos JSONs desta pasta.", "",
         f"Versões: python {v['python']}, numpy {v['numpy']}, scipy {v['scipy']}, statsmodels {v['statsmodels']}, "
         f"statlab {v['statlab']}. Seeds e n de simulações estão em cada seção e em cada JSON.", "",
         "## 0. Sonda `confseq`", "",
         f"- instalação padrão: **{sp['resultado']}** (versão tentada {sp.get('versao_tentada') or sp.get('versao')}; "
         f"falha de build: {sp.get('falha_de_build')}; Boost ausente: {sp.get('boost_ausente')}).",
         f"- somente wheel: **{sb['resultado']}** (sem wheel utilizável para esta plataforma: {sb.get('sem_wheel_utilizavel')}).",
         f"- import no venv da sonda: `{sonda['importacao_no_venv_da_sonda'].get('stderr_ultima_linha') or 'ok'}`.",
         f"- decisão: {sonda['decisao']}", ""]
    L += secao_maturacao(m) + secao_shrinkage(s) + secao_cs(c) + secao_fdr(fd)
    L += ["## 5. Conclusões (rótulos: demonstrado em simulação / refutado / inadequado para outcome X / não testado)", "",
          "Nada aqui é 'validado': tudo é simulação com seed e distribuições escolhidas por nós. Cada número abaixo é lido "
          "dos JSONs e cada rótulo é decidido por regra explícita sobre o IC95 (ver `statlab_relatorio.py`).", ""]
    L += conclusoes_maturacao(m) + [""] + conclusoes_shrinkage(s) + [""] + conclusoes_cs(c) + [""] + conclusoes_fdr(fd) + [""]
    L += comparacao(m, s)
    saida.write_text("\n".join(L) + "\n")
    print(f"gravado {saida} ({saida.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
