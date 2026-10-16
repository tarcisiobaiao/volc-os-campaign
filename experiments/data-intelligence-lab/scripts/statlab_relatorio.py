"""Stat Lab — gera results/statlab/STATLAB-RESULTS.md a partir dos JSONs (números nunca digitados à mão).

Uso: experiments/data-intelligence-lab/.venv/bin/python experiments/data-intelligence-lab/scripts/statlab_relatorio.py
"""

from __future__ import annotations

import json
from pathlib import Path

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


def secao_maturacao(d: dict) -> list[str]:
    L = [f"## 1. Maturação / nowcasting (seed base {d['seed']}, {d['n_simulacoes']} mundos por cenário, "
         f"as_of={d['parametros']['as_of']}, idade final={d['parametros']['idade_final']} dias)", "",
         "Método base: fator m(a) = Σobs(a)/Σfinal nas últimas 28 coortes maduras antes do as_of "
         "(chain-ladder restrito a coortes maduras). Guarda: m(a) < 0,3 ou < 14 coortes válidas → `insuficiente`. "
         "Intervalo 90%: (i) razão empírica final/obs(a) das coortes maduras (preditivo); (ii) bootstrap só do fator. "
         "Limiares são parâmetros de cenário. IC95 de Monte Carlo entre colchetes, **por mundo** (as idades de "
         "um mesmo mundo compartilham o fator e não são independentes); com 0% ou 100% em todos os mundos o IC "
         "normal degenera em largura zero — leia como 'em nenhum/todos os 300 mundos'.", ""]
    for nome, v in d["resultados"].items():
        cm = v["por_metodo"]["coortes_maduras"]
        vt = v.get("verdade_final_por_coorte", {})
        L.append(f"### `{nome}` (seed {v['seed_cenario']})")
        if vt:
            L.append(f"Verdade final por coorte: p5/p50/p95 = {', '.join(f(x) for x in vt['quantis_p5_p50_p95'])}; "
                     f"fração zero = {f(vt['frac_zero'])}.")
        L += ["", "| idade (d) | m(a) médio | MAPE sem guarda | APE máx sem guarda | % insuficiente c/ guarda | "
              "viés rel. c/ guarda | cobertura IC90 razão | cobertura IC90 bootstrap-fator |",
              "|---|---|---|---|---|---|---|---|"]
        for l in cm:
            sg, cg = l["sem_guarda"], l["com_guarda"]
            nsem = l.get("cobertura_razao", {}).get("n_sem_intervalo")
            cov_r = pct(l.get("cobertura_razao")) + (f" (sem IC: {nsem})" if nsem else "")
            fator = f(l["fator_medio"]) if l["frac_fator_indefinido"] == 0 else \
                f"{f(l['fator_medio'])} ({100 * l['frac_fator_indefinido']:.0f}% indef.)"
            L.append(f"| {l['faixa_idade'][0]}–{l['faixa_idade'][1]} | {fator} | {ic(sg['mape'])} | {f(sg['ape_max'])} "
                     f"| {pct(cg['frac_insuficiente_ou_nao_finito'])} | {f(cg['vies_relativo'])} | {cov_r} "
                     f"| {pct(l.get('cobertura_boot'))} |")
        if "regime" in nome:
            lr = v["por_metodo"]["link_ratio"]
            L += ["", "Variante link-ratio (usa coortes parcialmente maduras) no mesmo mundo:", "",
                  "| idade | viés rel. coortes maduras | viés rel. link-ratio | % insuf. link-ratio | APE máx link-ratio sem guarda |",
                  "|---|---|---|---|---|"]
            for a, b in zip(cm, lr):
                L.append(f"| {a['faixa_idade'][0]}–{a['faixa_idade'][1]} | {f(a['com_guarda']['vies_relativo'])} "
                         f"| {f(b['com_guarda']['vies_relativo'])} | {pct(b['com_guarda']['frac_insuficiente_ou_nao_finito'])} "
                         f"| {f(b['sem_guarda']['ape_max'])} |")
        L.append("")
    return L


def secao_shrinkage(d: dict) -> list[str]:
    p = d["parametros"]
    L = [f"## 2. Shrinkage Empirical Bayes ({d['n_simulacoes']} réplicas por cenário, K={p['K_unidades']} unidades, "
         f"top-k={p['top_k']}, intervalo {int(100 * p['nivel_intervalo'])}%)", "",
         "MSE relativo = MSE/MSE do cru na mesma réplica (unidades com n>0). Vencedores por sorte = unidades no "
         "top-k estimado fora do top-k verdadeiro. Calibração = cov(est, verdade)/var(est) (1 = calibrado). "
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
                L.append(f"| {est} | {ic(m.get('mse_relativo_ao_cru'))} | {ic(m.get('vencedores_por_sorte_topk'), 2)} "
                         f"| {ic(m.get('regret_topk'))} | {ic(m.get('inclinacao_calibracao'), 2)} "
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
          "| p (seed) | estratégia | erro uniforme (vs p_W) | decide 'p_W > μ0' até T | t mediano de calendário até decidir |",
          "|---|---|---|---|---|"]
    for nome, v in r["contraprova_atraso"].items():
        for m in ("oraculo", "janela_fechada", "lag_ingenuo"):
            x = v[m]
            L.append(f"| {v['p']} ({v['seed']}) | {m} | {pct(x['erro_uniforme_no_tempo'])} | {pct(x['frac_decidiu_ate_T'])} "
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
         "a implementação própria usa tolerância relativa 1e-12).", "",
         "| cenário (seed) | olhadas | método | FDR realizado | poder | falsas descobertas/réplica | falsos vencedores/réplica | FWER |",
         "|---|---|---|---|---|---|---|---|"]
    for nome, v in r["cenarios"].items():
        for m, x in v["metodos"].items():
            L.append(f"| {nome} ({v['seed_cenario']}) | {v['n_olhadas']} | {m} | {pct(x['fdr_realizado'])} | {pct(x['poder'])} "
                     f"| {ic(x['falsas_descobertas_por_replica'], 2)} | {ic(x['falsos_vencedores_por_replica'], 2)} | {pct(x['fwer'])} |")
    L.append("")
    return L


CONCLUSOES = """## 5. Conclusões (rótulos: demonstrado em simulação / refutado / inadequado para outcome X / não testado)

Nada aqui é "validado": tudo é simulação com seed e distribuições escolhidas por nós.

### Maturação
- **demonstrado em simulação**: com atraso estável, o fator de coortes maduras é quase sem viés agregado (|viés| ≤ 1% fora da idade 0 em `receita_estavel`) e o erro cai com a idade (MAPE 70% → 39% → 22% → 11% → 5% → 1%).
- **demonstrado em simulação**: o guarda converte o trecho explosivo (m(0) ≈ 0,02–0,08; APE máx 5–17×) em `insuficiente` em vez de número; reporte D+1 → m(0) = 0 exato → sem guarda inf/NaN, com guarda 100% `insuficiente`.
- **demonstrado em simulação (resultado negativo)**: o guarda NÃO elimina o erro logo acima do limiar (MAPE ~34–39% em 1–2 dias) e induz viés de seleção quando m(a) estimado oscila em torno do limiar (D+1, idade 1–2: −11%; centavo, idade 0: −10%), porque só passam os mundos cujo fator saiu alto.
- **refutado**: bootstrap só do fator como intervalo preditivo — cobre ~15–30% para 90% nominal nas idades < 30 d (ignora o ruído de processo da parte ainda não reportada). O intervalo por razão empírica cobre ~80–95% (subcobertura leve, pior nas idades baixas) e é indefinido quando obs = 0 (contado, não imputado).
- **refutado sob mudança de regime** (método degrada e não avisa): atraso 2,5× mais lento nas 30 coortes recentes → viés −69% (1–2 d), −53% (3–6 d), −35% (7–13 d), −15% (14–29 d), cobertura IC90 29–45%; atraso 2× mais rápido → +70% (1–2 d), +35% (3–6 d), cobertura 42–49%. Link-ratio reage parcialmente (viés +13% vs +70% no regime rápido; −31% vs −53% no lento em 3–6 d), mas no regime lento o fator vai a ~0,02 na idade 0 (APE máx 14×) e o guarda bloqueia 1–2 d. Detecção de regime: não testada.
- **demonstrado em simulação**: granularidade de centavo (receita diária p5–p95 ≈ US$0,02–1,08, D-1 mudando até D+3; forma dos fatos reais, não parâmetro) não quebra o fator; o problema dominante é a idade 0 (obs = 0 frequente → intervalo indefinido; ~25% `insuficiente`; MAPE ~72%).

### Shrinkage
- **demonstrado em simulação**: Beta-Binomial EB (momentos ou MLE) reduz MSE para ~28% do cru, calibra (inclinação ≈ 1,0 vs 0,33 do cru) e reduz a fração do top-k com n baixo de ~57% para ~8%; mas vencedores por sorte caem só de 7,0 para 5,9 em 10: o ranking continua majoritariamente ruído com n mediano 50 e CVR 3%.
- **demonstrado em simulação (contraprovas)**: (a) vencedores reais raros (prior bimodal): EB sub-cobre justamente os melhores (cobertura top-10% verdadeiro ≈ 57% vs 92% do cru; no unimodal já é 68%); (b) n informativo (orçamento já seguiu a CVR): cobertura 79% (momentos) / 85% (MLE); (c) sem heterogeneidade: EB plug-in colapsa no pooling e sub-cobre (momentos 54%, MLE 85%; Gamma quase homogênea 67–69%) porque ignora a incerteza do hiperparâmetro — e a "calibração" fica indefinida (var(est) ≈ 0); (d) n grande: ganho ~1% (inofensivo).
- **inadequado para receita monetária**: Gamma-Poisson aplicado a dinheiro praticamente não encolhe (peso do prior ~0,0003–0,002 em R$; ~0,000002–0,00001 em centavos), o resultado depende da unidade monetária e a cobertura dos intervalos é 0,2–10%. A implementação recusa valor não inteiro (`ValueError`).
- **demonstrado em simulação**: hurdle (Beta-Binomial × valor lognormal EB) e normal-normal EB com variância empírica agrupada são invariantes a escala; hurdle: MSE 8–27% do cru, cobertura 88–89%, inclusive com valor Pareto(1,8) mal especificado. Normal-normal: **refutado** com cauda pesada (σ_log = 2): cobertura 44% e top-k pior que o cru (regret 0,61 vs 0,50).
- **não testado**: lucro (valores negativos), hiperprior hierárquico completo, intervalos EB com correção para incerteza do hiperparâmetro.

### Confidence sequences
- **demonstrado em simulação**: PrPl-EB mantém erro uniforme ≤ alpha (0,8–1,9% para alpha = 5%) olhando em todo t; Wald recalculado a cada passo erra em 59–79% das trajetórias (32–34% mesmo contando só t ≥ 1000), embora em uma olhada fixa em T cubra (erro 4,5–5,6%).
- **demonstrado em simulação (custo)**: a CS é ~2× mais larga que Wald em T e tem muito menos poder: p = 0,06 vs μ0 = 0,05 com T = 10.000 → CS decide em 53%, Wald de horizonte fixo (válido, uma olhada) em 99%. Sob H0, Wald-peeking "decide" em 16% (vs 2,4% numa olhada). A CS paga a validade com tempo/amostra.
- **inadequado para outcome monetário ilimitado**: normalizar por limite estimado (máximo de piloto de 500) e recortar quebra a cobertura (erro 41% lognormal; 58% Pareto α = 1,5) apesar de só ~0,2% das observações passarem do limite; sem recorte a CS recusa a entrada (`ForaDoSuporte`). Wald também falha (93–94% com peeking; 10–23% numa olhada só).
- **demonstrado em simulação**: atraso de outcome tratado como 0 (lag fixo de 50) → erro 100% (estima p·P(D ≤ L)); esperar a janela fechar (W = 1000) preserva a validade e só atrasa a decisão em W no calendário (mediana 1.463 → 2.463 para p = 0,075).
- **não testado**: CS para diferença entre braços (A/B), versão betting/hedged (mais estreita), CS com atraso sem esperar a janela; comparação numérica com a lib `confseq` (não instalável).

### FDR
- **demonstrado em simulação**: BH numa olhada controla FDR (4,9% para q = 5%; 4,0% com 20% de células verdadeiras); sem correção, FDR 58% e ~24 falsos vencedores por rodada em 1000 células; Bonferroni controla FWER (4%) com poder ~1/3 do BH.
- **demonstrado em simulação**: peeking com BH a cada olhada infla o FDR (10 olhadas ≈ 9%; 50 olhadas ≈ 14%); sob nulo global, BH com 10 olhadas declara algo em ~26% das rodadas (vs 5%). Bonferroni também infla (6,5% / 11%).
- **demonstrado em simulação (limite de dados)**: CVR 3%, lift +30% e 5000 cliques/braço → poder do BH ~14%; o dado típico não sustenta "vencedor" por célula.
- **demonstrado**: BH própria = statsmodels exceto em empate exato p = q·k/m (ponto flutuante; 1 em 3000 casos com p arredondados).
- **não testado**: e-BH com e-valores das CS (válido sob peeking), dependência entre células (mesmo dia/campanha), testes unilaterais.
"""

COMPARACAO = """## 6. Relação com a pesquisa sintética anterior (pesquisa-B, run google-engine-nucleo-20261014-01)

Lida em modo somente leitura (`RELATORIO-B.md`, `experimentos/e1_*`, `e2_*`).

- **Confirma**: Beta-Binomial EB > cru e > média do grupo; o "vencedor" do cru está inflado (B: viés top-5% +0,31..+0,51; aqui 6–7 de 10 do top-k cru são vencedores por sorte). Gamma-Poisson não serve para receita/lucro monetário (B17 refutado lá; aqui mostrado pela dependência da unidade e cobertura ~1–10%). Intervalo do chain-ladder sub-cobre levemente (B: 84–87% para 90%; aqui razão empírica 80–95%). Drift de reporte degrada o fator de coortes maduras (B: −16%, cobertura 75% com drift mais brando; aqui −15% a −69% conforme a idade, cobertura 29–45% com atraso 2,5×).
- **Complementa/contradiz em parte**: B concluiu M ótimo = κ (EB acerta); aqui mostramos onde o EB plug-in FALHA mesmo acertando a média: sub-cobertura sem heterogeneidade, nos vencedores raros reais e com n informativo. B usou lognormal só nos positivos para lucro e refutou; aqui o hurdle (P(conv) × valor|conv) não sofre desse defeito para receita ≥ 0 e foi razoável inclusive com valor Pareto — mas lucro negativo não foi testado.
- **Novo**: guarda de maturação como `ResultadoInsuficiente` + D+1 com fator zero exato; refutação do bootstrap só do fator; link-ratio vs coortes maduras sob regime; cenário de centavo/D+3; cobertura uniforme de CS vs peeking; contraprovas de cauda pesada e atraso para CS; FDR com peeking; sonda confseq.
- **Não refeito**: BF (B mostrou BF ≥ CL; aqui não testado), OPE e bandits.
"""


def main() -> None:
    m, s, c, fd = (carregar(n) for n in ("maturacao.json", "shrinkage.json", "confidence_sequences.json", "fdr.json"))
    sonda = carregar("sonda_confseq.json")
    v = m["versoes"]
    L = ["# STATLAB — resultados (worker D, Fase 4)", "",
         "> Tudo abaixo é **simulação com seed**, sem dado real. Parâmetros (n, CVR, atrasos, limiares, top-k) são de "
         "cenário, nunca defaults operacionais. Gerado por `scripts/statlab_relatorio.py` a partir dos JSONs desta pasta.", "",
         f"Versões: python {v['python']}, numpy {v['numpy']}, scipy {v['scipy']}, statsmodels {v['statsmodels']}, "
         f"statlab {v['statlab']}. Seeds e n de simulações estão em cada seção e em cada JSON.", "",
         "## 0. Sonda `confseq`", "",
         f"- instalação padrão: **{sonda['instalacao_padrao']['resultado']}** — {sonda['instalacao_padrao']['versao_resolvida']}; "
         "build CMake falha: Boost ≥ 1.70 ausente (e Ninja ausente).",
         f"- somente wheel: **{sonda['instalacao_somente_wheel']['resultado']}** — {sonda['instalacao_somente_wheel']['motivo']}.",
         f"- import no venv da sonda: `{sonda['importacao_no_venv_da_sonda'].get('stderr_ultima_linha')}`.",
         f"- decisão: {sonda['decisao']}", ""]
    L += secao_maturacao(m) + secao_shrinkage(s) + secao_cs(c) + secao_fdr(fd)
    L += [CONCLUSOES, COMPARACAO]
    (RES / "STATLAB-RESULTS.md").write_text("\n".join(L) + "\n")
    print(f"gravado {RES / 'STATLAB-RESULTS.md'} ({(RES / 'STATLAB-RESULTS.md').stat().st_size} bytes)")


if __name__ == "__main__":
    main()
