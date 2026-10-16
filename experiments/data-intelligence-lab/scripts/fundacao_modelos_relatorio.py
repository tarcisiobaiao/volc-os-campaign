"""Gera results/fundacao/modelos/RESUMO.md a partir dos JSONs m*.json (nenhum número digitado à mão).

Uso: python -I scripts/fundacao_modelos_relatorio.py [--verificar]
``--verificar`` regenera em memória e falha se o RESUMO.md versionado divergir (usado por teste).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RES = Path(__file__).resolve().parents[1] / "results" / "fundacao" / "modelos"


def _f(x, casas=3, pct=False):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "sim" if x else "não"
    v = 100 * x if pct else x
    return f"{v:.{casas}f}" + ("%" if pct else "")


def _ic(d, casas=3, pct=False):
    if not isinstance(d, dict) or d.get("estimativa") is None:
        return "—"
    lo, hi = d.get("ic95", [None, None])
    if lo is None:
        return _f(d["estimativa"], casas, pct)
    return f"{_f(d['estimativa'], casas, pct)} [{_f(lo, casas, pct)}; {_f(hi, casas, pct)}]"


def _carregar(nome):
    p = RES / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def gerar() -> str:
    L = ["# RESUMO — Model Lab (worker F) · gerado de `m*.json` por `scripts/fundacao_modelos_relatorio.py`", "",
         "> Tudo é **simulação com seed** (teto: \"testado com sintético\"). IC95 por bootstrap de seeds entre colchetes.",
         "> Hipóteses e critérios: `PRE-REGISTRO.md`. Itens pós-registro estão marcados.", ""]
    m1 = _carregar("m1_maturacao.json")
    if m1:
        r = m1["resultados"]
        A, B = r["A_receita_estavel"], r["B_custo_d0_intradiario"]
        L += ["## M1 — Maturação", "", "### A. Receita JoinAds (`estavel`), MAPE do total diário por idade (dias)", "",
              "| método | idade 0 | idade 1 | idade 2 |", "|---|---|---|---|"]
        for m, v in A["mape_por_idade"].items():
            L.append(f"| {m} | " + " | ".join(_ic(v[str(a)], 1, True) for a in range(3)) + " |")
        L += ["", f"- H1a (BF − CL, MAPE idade 0): {_ic(A['H1a_bf_menos_cl_mape_idade0'], 2, True)} → suportada: "
                  f"{_f(A['H1a_suportada'])}",
              f"- Cobertura do IC80 do chain-ladder (razão empírica): " + ", ".join(
                  f"idade {a}: {_ic(A['cobertura_ic80_cl'][str(a)], 1, True)}" for a in range(3)), "",
              "### B. Custo D0 intradiário (`custo_d0_multiversao`), wMAPE do final por hora da leitura", "",
              "| hora | m(h) médio | chain-ladder intradiário | D0 como final |", "|---|---|---|---|"]
        for h in B["fator_medio_por_hora"]:
            L.append(f"| {h}h | {_f(B['fator_medio_por_hora'][h])} | {_ic(B['wmape_por_hora']['cl_intradiario'][h], 1, True)} | "
                     f"{_ic(B['wmape_por_hora']['d0_como_final'][h], 1, True)} |")
        L += ["", f"- H1b razão wMAPE (CL/naive) até 18h: {_ic(B['H1b_razao_wmape_cl_sobre_naive_ate_18h'])} → suportada: "
                  f"{_f(B['H1b_suportada'])}",
              f"- versões distintas de custo por campanha-dia (mediana): {_ic(B['versoes_distintas_mediana_por_campanha_dia'], 1)}", ""]
        for rot, chave in (("pré-registrado (k=0,5, escala MAD)", m1),
                           ("PÓS-REGISTRO exploratório (k=1, escala max(MAD, dp))", _carregar("m1_maturacao_pos_registro.json"))):
            if not chave:
                continue
            rr = chave["resultados"]
            c1, c2 = rr["C1_regime_stat_lab_herdado"], rr["C2_regime_simulador"]
            L += [f"### C. Regime de maturação — monitor {rot}", "",
                  f"- C1 (Stat Lab herdado) calibração FA/mundo: " + ", ".join(f"h={c['h']:g}: {_f(c['fa_por_mundo'], 2)}"
                                                                           for c in c1["calibracao"])
                  + f" → h={c1['h']:g}, calibrou: {_f(c1.get('calibrou'))}",
                  "", "| cenário C1 | detecção | viés 1–2 d CL | viés 1–2 d CL+monitor | insuf. 1–2 d CL+monitor | cobertura 3–6 d CL | cobertura 3–6 d CL+monitor |",
                  "|---|---|---|---|---|---|---|"]
            for n, c in c1["cenarios"].items():
                f12, f36 = c["faixas"]["1-2"], c["faixas"]["3-6"]
                L.append(f"| {n} | {_f(c['taxa_deteccao'], 2)} | {_ic(f12['cl']['vies'], 1, True)} | {_ic(f12['mon']['vies'], 1, True)} | "
                         f"{_ic(f12['mon']['insuf'], 1, True)} | {_ic(f36['cl']['cob'], 1, True)} | {_ic(f36['mon']['cob'], 1, True)} |")
            L += ["", f"- C2 (simulador, JoinAds troca de observador no dia {c2['dia_troca']}): calibração "
                      + ", ".join(f"h={c['h']:g}: {_f(c['fa_por_mundo'], 2)}" for c in c2["calibracao"])
                      + f" → h={c2['h']:g}, calibrou: {_f(c2.get('calibrou'))}; detecção em 15 dias: "
                        f"{_f(c2['taxa_deteccao_em_15_dias'], 2)}; atraso: {_ic(c2['atraso_deteccao_dias'], 1)} dias", "",
                  "| idade | viés CL | viés fator fixo | viés CL+monitor (publicados) | insuf. CL+monitor |", "|---|---|---|---|---|"]
            for a in range(1, 7):
                v = c2["vies_relativo_coortes_pos_troca"]
                L.append(f"| {a} | {_ic(v['chain_ladder'][str(a)], 1, True)} | {_ic(v['fator_fixo'][str(a)], 1, True)} | "
                         f"{_ic(v['chain_ladder_monitor'][str(a)], 1, True)} | {_ic(c2['frac_insuficiente']['chain_ladder_monitor'][str(a)], 1, True)} |")
            L.append("")
    m2 = _carregar("m2_eb.json")
    if m2:
        r = m2["resultados"]
        L += ["## M2 — Empirical Bayes em campanha nova", "", "| k (dias) | alvo | razão MSE EB/cru | vencedores por sorte cru | EB | EB − cru |",
              "|---|---|---|---|---|---|"]
        for k in ("1", "3", "7"):
            for alvo in ("ctr", "rpm"):
                b = r[k][alvo]
                if "razao_mse_eb_sobre_cru" not in b:
                    L.append(f"| {k} | {alvo} | insuficiente ({b.get('motivo', '')}) | — | — | — |")
                    continue
                L.append(f"| {k} | {alvo} | {_ic(b['razao_mse_eb_sobre_cru'])} | {_ic(b['sorte_cru'], 2)} | {_ic(b['sorte_eb'], 2)} | "
                         f"{_ic(b['dif_sorte_eb_menos_cru'], 2)} |")
        L += ["", f"- viés relativo do CTR cru (k=1) contra os 14 dias seguintes: {_ic(r['1']['ctr']['vies_relativo_ctr_cru_vs_futuro'], 1, True)}",
              f"- H2 critérios: {r['H2_criterios']} → suportada: {_f(r['H2_suportada'])}", ""]
    m3 = _carregar("m3_mudanca.json")
    if m3:
        r = m3["resultados"]
        L += ["## M3 — Detecção de mudança (log RPM maduro)", "", f"Limiares calibrados (FA alvo 0,02/campanha-semana): {r['limiares_calibrados']}", "",
              "| método | poder (≤14 d) | alarmes falsos/semana (teste) | atraso mediano (dias) |", "|---|---|---|---|"]
        for n, v in r["por_metodo"].items():
            L.append(f"| {n} | {_ic(v['poder'], 2)} | {_ic(v['fa_semana'], 3)} | {_ic(v['atraso'], 1)} |")
        L += ["", f"- CUSUM − média móvel (poder): {_ic(r['H3_poder_cusum_menos_media_movel'], 3)}; BOCPD − média móvel: "
                  f"{_ic(r['H3_poder_bocpd_menos_media_movel'], 3)} (CUSUM supera: {_f(r['H3_cusum_supera'])}; BOCPD supera: {_f(r['H3_bocpd_supera'])}) → H3 suportada: {_f(r['H3_suportada'])}", ""]
    m4 = _carregar("m4_sequencial.json")
    if m4:
        r = m4["resultados"]
        L += ["## M4 — Sequencial e FDR", "", f"μ0 (taxa de destino derivada do simulador) = {_f(r['mu0_taxa_destino_derivada_do_simulador'])}", "",
              "| regime | FDR BH | poder BH | FDR e-BH | poder e-BH |", "|---|---|---|---|---|"]
        for reg in ("uma_olhada", "olhadas_10", "olhadas_50"):
            b = r["fdr"][reg]
            L.append(f"| {reg} | {_f(b['bh']['fdr'])} ± {_f(b['bh']['ep_mc'])} | {_f(b['bh']['poder'])} | {_f(b['ebh']['fdr'])} ± "
                     f"{_f(b['ebh']['ep_mc'])} | {_f(b['ebh']['poder'])} |")
        if "fdr_efeito_fraco_descritivo" in r:
            L += ["", "Descritivo adicional (efeito fraco, lift 1,10; não é hipótese pré-registrada):", "",
                  "| regime | FDR BH | poder BH | FDR e-BH | poder e-BH |", "|---|---|---|---|---|"]
            for reg in ("uma_olhada", "olhadas_10", "olhadas_50"):
                b = r["fdr_efeito_fraco_descritivo"][reg]
                L.append(f"| {reg} | {_f(b['bh']['fdr'])} ± {_f(b['bh']['ep_mc'])} | {_f(b['bh']['poder'])} | {_f(b['ebh']['fdr'])} ± "
                         f"{_f(b['ebh']['ep_mc'])} | {_f(b['ebh']['poder'])} |")
        c = r["cs"]
        L += ["", f"- CS PrPl-EB na taxa de destino: erro uniforme {_ic(c['taxa_destino_erro_uniforme'], 3)} (α = {c['alpha']}, "
                  f"{c['n_trajetorias']} trajetórias)",
              f"- receita/sessão normalizada por limite da janela inicial: recusa (`ForaDoSuporte`) em {_ic(c['receita_limite_violado_recusa'], 3)}; "
              f"recortada: erro uniforme {_ic(c['receita_recortada_erro_uniforme'], 3)}",
              f"- H4a (e-BH controla): {_f(r['fdr']['H4a_ebh_controla'])}; BH infla com peeking: {_f(r['fdr']['bh_infla_com_peeking'])}; "
              f"H4b: {_f(r['H4b_suportada'])}", ""]
    m5 = _carregar("m5_causal.json")
    if m5:
        r = m5["resultados"]
        L += ["## M5 — Causal (`mudanca_orcamento`)", ""]
        for parte, rot in (("a", "H5a: dobra aleatória do cenário"), ("b", "H5b: dobra para o top 30% de ROAS recente")):
            L += [f"### {rot}", "", "| desfecho | ATT verdadeiro (R$/camp-dia) | viés antes/depois | viés corte transversal | viés DiD | viés controle sintético | IC DiD cobre verdade | tendências paralelas passou | placebo passou |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for k, b in r[parte].items():
                v = b["vies"]
                L.append(f"| {k} | {_ic(b['verdade_att'], 2)} | {_ic(v['antes_depois'], 2)} | {_ic(v['corte_transversal'], 2)} | "
                         f"{_ic(v['did'], 2)} | {_ic(v['controle_sintetico'], 2)} | {_f(b['frac_did_ic_cobre_verdade'], 2)} | "
                         f"{_f(b['frac_tendencias_paralelas_passou'], 2)} | {_f(b['frac_placebo_temporal_passou'], 2)} |")
            L.append("")
        L += [f"- |viés antes/depois| − |viés DiD| no lucro (H5b, cond. 2): {_ic(r['b']['lucro']['abs_vies_antes_depois_menos_did'], 2)}",
              f"- H5b critérios: {r.get('H5b_criterios')}",
              f"- H5a: {_f(r['H5a_suportada'])}; H5b: {_f(r['H5b_suportada'])}", ""]
    m6 = _carregar("m6_surrogate.json")
    if m6:
        r = m6["resultados"]
        L += ["## M6 — Surrogate (portão herdado reaberto com o simulador)", "", "| caso | veredito | cobertura da feature de sessão no grão campanha |", "|---|---|---|"]
        for n, b in r["portao"].items():
            L.append(f"| {n} | {b['veredito']} | {_f(b['cobertura_feature_sessoes_no_grao_campanha'], 3)} |")
        L += ["", "| cenário | skill fora do tempo (Ridge sessões+cliques vs média da campanha) | cobertura |", "|---|---|---|"]
        for n, b in r["skill"].items():
            L.append(f"| {n} | {_ic(b['skill'], 3)} | {_ic(b['cobertura_feature_sessao'], 3)} |")
        L.append("")
    m7 = _carregar("m7_bandits.json")
    if m7:
        r = m7["resultados"]
        L += ["## M7 — Bandits e OPE", ""]
        for cen in ("estavel", "quebra_regime_rpm"):
            b = r[cen]
            L += [f"### {cen}", "", "| política | pseudo-regret (escala do 1º dia) |", "|---|---|"]
            for n, v in b["regret"].items():
                L.append(f"| {n} | {_ic(v, 1)} |")
            L += ["", f"- LinUCB − equal {_ic(b['linucb_menos_equal'], 1)}; LinUCB − greedy {_ic(b['linucb_menos_greedy'], 1)}; "
                      f"Thompson − equal {_ic(b['thompson_menos_equal'], 1)}; Thompson − greedy {_ic(b['thompson_menos_greedy'], 1)} → H7a: "
                      f"{_f(b['H7a_suportada'])}"]
            for alvo, o in b["ope"].items():
                w1 = o["mundo1_muitos_logs"]
                L.append(f"- OPE alvo `{alvo}` (mundo 1, {w1['ips']['n_logs']} logs): viés IPS {_f(w1['ips']['vies'])} ± {_f(w1['ips']['ep_mc'])}, "
                         f"SNIPS {_f(w1['snips']['vies'])} (dp {_f(w1['snips']['dp'])} vs IPS {_f(w1['ips']['dp'])}), DR {_f(w1['dr']['vies'])} "
                         f"(dp {_f(w1['dr']['dp'])}), propensão inventada {_f(w1['ips_propensao_inventada']['vies'])} ± "
                         f"{_f(w1['ips_propensao_inventada']['ep_mc'])}")
            L.append("")
        L += [f"- Sem propensão: {r['sem_propensao']}", f"- H7b por alvo: {r.get('H7b_por_alvo')}", f"- H7b: {_f(r['H7b_suportada'])}", ""]
    m8 = _carregar("m8_conformal.json")
    if m8:
        r = m8["resultados"]
        L += ["## M8 — Conformal (90% nominal, lucro diário maduro)", "", "| cenário | método | cobertura teste | cobertura campanhas quebradas pós-quebra | não quebradas | largura mediana (R$) |",
              "|---|---|---|---|---|---|"]
        for cen in ("estavel", "quebra_regime_rpm"):
            for m in ("split", "aci"):
                b = r[cen][m]
                L.append(f"| {cen} | {m} | {_ic(b['cobertura_teste'], 3)} | {_ic(b['cobertura_quebradas_pos'], 3)} | "
                         f"{_ic(b['cobertura_nao_quebradas'], 3)} | {_ic(b['largura_mediana'], 1)} |")
        L += ["", f"- H8a: {_f(r['H8a_suportada'])}; H8b: {_f(r['H8b_suportada'])}", ""]
    m9 = _carregar("m9_anomalia.json")
    if m9:
        r = m9["resultados"]
        L += ["## M9 — Anomalias", "", "| detector (`outlier_bot`, razão cliques/sessões) | precisão | recall | F1 |", "|---|---|---|---|"]
        for n, b in r["outlier_bot"].items():
            L.append(f"| {n} | {_ic(b['precisao'], 2)} | {_ic(b['recall'], 2)} | {_ic(b['f1'], 2)} |")
        L += ["", f"- dias com bot por mundo: {_f(r['n_dias_bot_medio'], 1)}; MAD − z (F1) {_ic(r['f1_robusto_mad_menos_zscore'], 2)}; "
                  f"sazonal − z {_ic(r['f1_sazonal_robusto_menos_zscore'], 2)} → H9a: {_f(r['H9a_suportada'])}",
              f"- `fonte_fora_do_ar`: {r['fonte_fora_do_ar']} → H9b: {_f(r['H9b_suportada'])}",
              f"- `zero_falso` (zero implausível): precisão {_ic(r['zero_falso']['precisao'], 2)}, recall {_ic(r['zero_falso']['recall'], 2)} → "
              f"H9c: {_f(r['H9c_suportada'])}", ""]
    m10 = _carregar("m10_alocacao.json")
    if m10:
        r = m10["resultados"]
        L += ["## M10 — Alocação de orçamento (regret em R$ nos 15 dias, contra oráculo de grade)", ""]
        for cen in ("mudanca_orcamento", "estavel"):
            b = r[cen]
            L += [f"### {cen}", "", f"curvas identificáveis: {_ic(b['frac_curvas_identificaveis'], 2)}; desvio de log gasto mediano: "
                                   f"{_ic(b['desvio_log_gasto_mediano'], 3)}; b mediano: {_ic(b.get('b_mediano'), 2)}; fração de b no teto (0,95): "
                                   f"{_ic(b.get('frac_b_no_teto'), 2)}; violações de restrição: {b['violacoes_de_restricao']}; "
                                   f"histórico as_of: último dia maduro (mediana) {b.get('ultimo_dia_maduro_mediano', '—')}, "
                                   f"células maduras {_ic(b.get('frac_celulas_maduras_hist'), 2)}", "",
                  "| política | regret |", "|---|---|"]
            for n, v in b["regret"].items():
                L.append(f"| {n} | {_ic(v, 0)} |")
            L += ["", "- côncava − " + "; ".join(f"{x}: {_ic(b[f'concava_menos_{x}'], 0)}" for x in ("equal", "proporcional_herdado",
                                                                                                    "greedy", "status_quo")), ""]
        L += [f"- H10a: {_f(r['H10a_suportada'])}; H10b (não supera equal sem variação): {_f(r['H10b_suportada_nao_supera_equal_sem_variacao'])}", ""]
    m12 = _carregar("m12_tabular.json")
    if m12:
        r = m12["resultados"]
        L += ["## M12 — Tabular (lucro final de amanhã, rolling origin)", "", "| cenário | modelo | MAE (R$) | MAE relativo à média dos maduros |", "|---|---|---|---|"]
        for cen in ("estavel", "quebra_regime_rpm"):
            b = r[cen]
            for n, v in b["mae"].items():
                rel = b.get(f"mae_rel_{n}_sobre_media_maduros")
                L.append(f"| {cen} | {n} | {_ic(v, 2)} | {_ic(rel, 3) if rel else '—'} |")
        for cen in ("estavel", "quebra_regime_rpm"):
            b = r[cen]
            L.append(f"- {cen}: vazamento detectado por metadado {_f(b['deteccao_vazamento_metadado'], 2)}, empírico "
                     f"{_f(b['deteccao_vazamento_empirica'], 2)} (ganho de MAE com a feature do futuro {_ic(b['ganho_mae_com_vazamento'], 2)}); "
                     f"alarme falso empírico no modelo honesto {_f(b['alarme_falso_empirico_modelo_honesto'], 2)}")
        L += [f"- H12: {_f(r['H12_suportada'])}", ""]
    L += _errata()
    return "\n".join(L) + "\n"


def _errata() -> list:
    """Errata datada (revisão adversarial R2): resultado antigo preservado em errata_20261016/."""
    d = RES / "errata_20261016"
    m5o, m10o = (json.loads((d / n).read_text(encoding="utf-8")) if (d / n).exists() else None
                 for n in ("m5_causal_pre_errata.json", "m10_alocacao_pre_errata.json"))
    m5n, m10n = _carregar("m5_causal.json"), _carregar("m10_alocacao.json")
    if not (m5o and m10o and m5n and m10n):
        return []
    L = ["## Errata 2026-10-16 (revisão adversarial R2) — resultado antigo preservado em `errata_20261016/`", "",
         "| achado | o que estava errado | antes | depois |", "|---|---|---|---|"]
    o, n = m5o["resultados"], m5n["resultados"]
    L.append(f"| G9 (M5/H5b) | o script testava só a condição 1 do pré-registro (DiD enviesado); faltava a condição 2 "
             f"(antes/depois mais enviesado que o DiD) | H5b suportada: {_f(o['H5b_suportada'])} | H5b suportada: "
             f"{_f(n['H5b_suportada'])} (critérios {n['H5b_criterios']}) |")
    o, n = m10o["resultados"], m10n["resultados"]
    fmt = lambda r, c: f"regret côncava {_ic(r[c]['regret']['concava'], 0)}, equal {_ic(r[c]['regret']['equal'], 0)}"  # noqa: E731
    L.append(f"| G10 (M10) | histórico de decisão era a verdade diária do mundo, inclusive dias imaturos | "
             f"`mudanca_orcamento`: {fmt(o, 'mudanca_orcamento')}; H10a {_f(o['H10a_suportada'])}, H10b "
             f"{_f(o['H10b_suportada_nao_supera_equal_sem_variacao'])} | painel as_of maduro: {fmt(n, 'mudanca_orcamento')}; "
             f"H10a {_f(n['H10a_suportada'])}, H10b {_f(n['H10b_suportada_nao_supera_equal_sem_variacao'])} |")
    L.append("| G13-F4 | `TabelaVersoes` ordenada pela chegada (regra pré-D1) sobrevivia aos testes de comportamento | — | "
             "testes `test_preliminar_atrasada_nao_substitui_a_final_r2_g13_f4` e "
             "`test_equivalencia_com_coletas_atrasadas_e_recuperacao_tardia` matam o mutante |")
    return L + [""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true")
    a = ap.parse_args()
    texto = gerar()
    destino = RES / "RESUMO.md"
    if a.verificar:
        ok = destino.exists() and destino.read_text(encoding="utf-8") == texto
        print("RESUMO.md em sincronia" if ok else "RESUMO.md DIVERGE dos JSONs")
        sys.exit(0 if ok else 1)
    destino.write_text(texto, encoding="utf-8")
    print(destino)


if __name__ == "__main__":
    main()
