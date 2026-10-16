"""Origem declarada de cada parâmetro: forma calibrada, documentação da fonte, literatura ou arbitrário.

Regra: dado real versionado no repositório tem n minúsculo (Senac shadow: 1 campanha Google,
16 dias maduros; golden Meta×GAM: 64 campanha-dias, 7 campanhas, tráfego Meta). Ele só escolhe
FORMA e FAIXA (dispersão adimensional, quantização, moeda, cadência), nunca nível monetário.
Literatura citada não foi reverificada nesta execução (sem rede): é "faixa da literatura
segundo a fonte citada", não medição. Tudo o mais é ``arbitrario`` e assim deve ser lido.

``verificar_forma`` compara o mundo default com as faixas de forma (teste em
``test_simulador_estatistica.py``).
"""
from __future__ import annotations

import numpy as np

FORMA_REAL = "forma_real"
DOC_FONTE = "documentacao_fonte"
LITERATURA = "literatura_nao_verificada"
ARBITRARIO = "arbitrario"

_GOLDEN = "backend/tests/goldens/atribuicao-meta-adset-v1.json"
_SENAC = "backend/app/trafego/shadow_experimentos/senac-shadow-20261015/{transformacao.csv,resultado.json}"
_MATRIZ = "docs/data-intelligence/DATA-CAPABILITY-MATRIX.md"

FONTES_PARAMETROS: dict[str, tuple[str, str]] = {
    # mundo
    "roas_mediana": (FORMA_REAL, f"{_GOLDEN}: ROAS campanha-dia (84 linhas com gasto e receita) p50≈0,99; nível de equilíbrio da arbitragem"),
    "roas_sigma": (FORMA_REAL, f"{_GOLDEN}: p10≈0,48 e p90≈1,47 ⇒ σ_log≈0,32 (tráfego Meta, não Search; forma apenas)"),
    "moeda_receita/frac_campanhas_receita_usd": (DOC_FONTE, f"{_MATRIZ} linha JoinAds: receita em USD; o default BRL é simplificação declarada"),
    "cambio_brl_por_usd": (ARBITRARIO, "só define a verdade USD a partir do gerador em BRL; não é câmbio real"),
    "ctr_media": (LITERATURA, "benchmarks de Search (WordStream/LocaliQ 2023–2024: CTR médio ~3–6%); golden Meta tem CTR ~7% mas é outro canal"),
    "cpc (derivado)": (ARBITRARIO, f"derivado de ROAS×RPM×funil; resulta em décimos de real, mesma ordem de grandeza do {_SENAC}"),
    "rpm_mediana_brl/rpm_sigma/mult_rpm_*": (ARBITRARIO, "nenhuma receita por pageview real versionada no repositório"),
    "funil_passos/continuacao/aterrissagem": (ARBITRARIO, "funil de pauta paginada; sem dado de sessão com receita (não identificável)"),
    "amp_diaria/hora_pico/fator_fds_*": (ARBITRARIO, "forma plausível (vale de madrugada, pico à noite); sem série horária real versionada"),
    "share_dispositivo/mult_*_dispositivo/prob_pais": (ARBITRARIO, "maioria mobile e BR; números escolhidos"),
    "limite_diario_x_orcamento": (LITERATURA, "Ajuda do Google Ads: gasto diário pode chegar a 2× o orçamento médio diário; corte rígido modelado"),
    "elasticidade_cpc/overdelivery": (ARBITRARIO, "pacing em expectativa (κ=1); o Google permite até 2× o orçamento diário num dia (documentação Google Ads, não verificada)"),
    "taxa_cliques_invalidos/bot_*": (ARBITRARIO, f"{_MATRIZ}: 'invalid clicks podem ajustar depois' [H]; magnitude escolhida"),
    "tau_aprendizado_h/amp_*_aprendizado/volume_inicial": (LITERATURA, "período de aprendizado de lances automáticos ~até 7 dias (Ajuda do Google Ads); amplitudes arbitrárias"),
    "choque_dia_*/sobredispersao/dispersao_receita": (ARBITRARIO, "heterocedasticidade: variância cresce com a média (Gamma-Poisson) e CV da receita cai com pageviews"),
    "p_pausa_dia": (ARBITRARIO, "gera zero confirmado legítimo"),
    # observador
    "gads_horas_d0": (DOC_FONTE, f"{_MATRIZ}: D0 em 4 passadas/dia (v12_04:404)"),
    "gads_lag_d0_h": (DOC_FONTE, f"{_MATRIZ}: SLO Google ~1 h para custo/cliques [NT]; 3 h é margem escolhida"),
    "gads_d1_hora": (DOC_FONTE, f"{_MATRIZ}: D-1 no dia seguinte; wip usa atraso de 26 h"),
    "gads_frac_credito_d1/gads_backfill_dias": (ARBITRARIO, "0 curvas reais de maturação de custo (ledger guarda hash, não valor)"),
    "join_horas_intradia/join_releituras": (DOC_FONTE, f"{_MATRIZ}: intraday 06/12/18/23 + D-1 relê 3 dias (gerar_flows_joinads.py:29-31)"),
    "join_f0/join_tau_maturacao_h/join_sigma_estimativa": (ARBITRARIO, f"{_MATRIZ}: 0 curvas reais de maturação de receita"),
    "join_quantum_micros": (FORMA_REAL, f"{_MATRIZ}: JoinAds USD com 2 casas; {_SENAC}: dias 0,00 ambíguos"),
    "join_p_troca_chave_sem_dado": (DOC_FONTE, f"{_MATRIZ}: API troca a custom_key calada quando não há dado (gerar_flows_joinads.py:223-226); modelada por linha"),
    "join_consulta_dispositivo": (DOC_FONTE, f"{_MATRIZ}: custom_keys aceitas não incluem dispositivo"),
    "p_zero_falso": (DOC_FONTE, "docs/data-intelligence/LIBRARY-DECISIONS.md: Google Ads MCP 0.0.4 devolve 0 para métrica ausente"),
    "timezone": (DOC_FONTE, f"{_MATRIZ}: custo em America/Sao_Paulo; fuso do date JoinAds não declarado (o simulador declara)"),
    "p_ausente/p_payload_invalido/p_duplicata/p_atraso/atraso_*": (ARBITRARIO, "taxas de defeito escolhidas; nenhuma medição de SLO real"),
}

# Faixas de FORMA (adimensionais) que o mundo default deve respeitar.
FAIXAS_FORMA = {
    "roas_campanha_dia_p10": (0.30, 0.75),
    "roas_campanha_dia_p50": (0.80, 1.25),
    "roas_campanha_dia_p90": (1.20, 2.00),
    "ctr_agregado": (0.02, 0.07),
    "cpc_medio_brl": (0.05, 2.00),
}


def medir_forma(mundo) -> dict[str, float]:
    custo = mundo.diario("custo_final_micros")
    rec = mundo.diario("receita_micros")
    m = custo > 0
    roas = rec[m] / custo[m]
    p10, p50, p90 = np.percentile(roas, [10, 50, 90])
    cl = mundo.diario("cliques").sum()
    return {
        "roas_campanha_dia_p10": float(p10), "roas_campanha_dia_p50": float(p50), "roas_campanha_dia_p90": float(p90),
        "ctr_agregado": float(cl / max(1, mundo.diario("impressoes").sum())),
        "cpc_medio_brl": float(mundo.diario("custo_bruto_micros").sum() / 1e6 / max(1, cl)),
    }


def verificar_forma(mundo) -> dict[str, dict]:
    med = medir_forma(mundo)
    return {k: {"valor": round(v, 6), "faixa": FAIXAS_FORMA[k], "ok": FAIXAS_FORMA[k][0] <= v <= FAIXAS_FORMA[k][1]}
            for k, v in med.items()}
