"""Roda o modelo de capacidade (frente B) sobre a grade de cenários e grava JSON + Markdown.

Entradas: `benchmarks/capacidade/pg_medicoes.json` (bytes medidos no PostgreSQL descartável) e
`benchmarks/capacidade/horas_campanha_d30.json` (perfil horário real). Saídas: `modelo.json`
(manifesto com versões e hashes) e `MODELO.md` (gerado; não editar à mão).

Uso: <python> -I experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parents[1]
sys.path.insert(0, str(LAB / "src"))

from volc_dil.contracts import manifesto_execucao, sha256_arquivo, sha256_codigo  # noqa: E402
from volc_dil.fundacao.capacidade import cenarios as cen  # noqa: E402
from volc_dil.fundacao.capacidade import quotas  # noqa: E402
from volc_dil.fundacao.capacidade.volume import (  # noqa: E402
    GB, PerfilBytes, PerfilGTM, calcular_cenario, calcular_gtm, calcular_job)

BENCH = REPO / "docs" / "data-intelligence" / "fundacao-20261016" / "benchmarks" / "capacidade"
SEED = 20261016  # o modelo é determinístico; a seed só identifica a execução


def _medicao(pg: dict, variante: str, n: int, part: bool = False) -> dict:
    for m in pg["medicoes"]:
        if m["variante"] == variante and m["n_alvo"] == n and m["particionada"] == part:
            return m
    raise KeyError((variante, n, part))


def perfis(pg: dict) -> dict[str, PerfilBytes]:
    pay = pg["payload"]
    lote = {"campanha": pay["campanha_lote_pglz"]["bytes_por_linha_api"], "termo": pay["termo_lote_pglz"]["bytes_por_linha_api"]}
    ind = {"campanha": pay["campanha_linha_pglz"]["bytes_por_linha_api"], "termo": pay["termo_linha_pglz"]["bytes_por_linha_api"]}
    largo = _medicao(pg, "largo", 10**6)["tamanho"]
    rollup = largo["total_bytes"] / largo["linhas"]
    h7 = _medicao(pg, "longo", 10**7)["tamanho"]
    p7 = _medicao(pg, "longo", 10**7, True)["tamanho"]
    sobre = max(0.0, (p7["total_bytes"] - h7["total_bytes"]) / max(1, p7["folhas"]))
    out = {}
    for nome, variante, formato in (("v21_replica", "v21", "largo"), ("largo_tipado", "largo", "largo"),
                                    ("longo_tipado", "longo", "longo"), ("largo_jsonb", "jsonb", "largo")):
        t = _medicao(pg, variante, 10**6)["tamanho"]
        out[nome] = PerfilBytes(formato=formato, heap_por_observacao=t["heap_por_linha"],
                                indices_por_observacao=t["indices_por_linha"], payload_linha_em_lote=lote,
                                payload_linha_individual=ind, manifesto_por_lote=250.0, rollup_por_linha=rollup,
                                sobrecarga_particao_bytes=sobre, origem=f"pg_medicoes.json: {variante} 1e6 (sem partição)")
    return out


GRADE_POLITICAS = (  # (política, perfil)
    ("v21_atual", "v21_replica"),
    ("compacto_sem_dedup", "largo_tipado"),
    ("compacto_dedup_lote", "largo_tipado"),
    ("compacto_dedup_linha", "largo_tipado"),
    ("compacto_dedup_linha_em_lote", "largo_tipado"),
    ("compacto_dedup_sem_indices", "largo_tipado"),
    ("recomendada", "largo_tipado"),
    ("compacto_sem_dedup", "longo_tipado"),
    ("compacto_dedup_linha", "longo_tipado"),
)


def rodar() -> dict:
    pg_path, horas_path = BENCH / "pg_medicoes.json", BENCH / "horas_campanha_d30.json"
    pg = json.loads(pg_path.read_text(encoding="utf-8"))
    pfs = perfis(pg)
    conjuntos = {"atual": cen.jobs_atuais(), "vertical_completa": cen.jobs_vertical_completa()}
    grade = []
    for nome_conj, jobs_base in conjuntos.items():
        for cad in cen.CADENCIAS:
            jobs = cen.aplicar_cadencia(jobs_base, cad)
            for fator in cen.FATORES_CRESCIMENTO:
                esc = cen.com_escala(cen.ESCALA_ATUAL, fator)
                for pol_nome, perf_nome in GRADE_POLITICAS:
                    r = calcular_cenario(jobs, esc, pfs[perf_nome], cen.POLITICAS[pol_nome])
                    grade.append({"jobs": nome_conj, "cadencia": cad, "crescimento": fator, "politica": pol_nome,
                                  "perfil": perf_nome, **r.resumo(),
                                  "quota_google_ads": quotas.avaliar_google_ads(r.jobs),
                                  "chamadas_por_fonte": quotas.chamadas_por_fonte(r.jobs)})
    # detalhe por job no cenário atual e na vertical completa (escala atual)
    detalhe = {}
    for nome_conj, jobs_base in conjuntos.items():
        for cad in cen.CADENCIAS:
            detalhe[f"{nome_conj}/{cad}"] = [
                {**asdict(calcular_job(j, cen.ESCALA_ATUAL)), "cron": j.cron, "janela": j.janela,
                 "linhas_distintas_dia": calcular_job(j, cen.ESCALA_ATUAL).linhas_distintas_dia,
                 "fracao_redundante": calcular_job(j, cen.ESCALA_ATUAL).fracao_redundante, "confirmacao": j.confirmacao}
                for j in cen.aplicar_cadencia(jobs_base, cad)]
    # termos 1×/dia vs 4 h
    termos = {}
    for rot, jobs in (("4h", cen.jobs_atuais()), ("1x_dia", cen.termos_uma_vez_ao_dia(cen.jobs_atuais()))):
        rs = [calcular_job(j, cen.ESCALA_ATUAL) for j in jobs if j.nome in ("gads_termos", "gads_keywords")]
        termos[rot] = {"linhas_lidas_dia": sum(r.linhas_lidas_dia for r in rs),
                       "linhas_distintas_dia": sum(r.linhas_distintas_dia for r in rs),
                       "chamadas_dia": sum(r.chamadas_dia for r in rs)}
    # sensibilidade: p de revisão (fechados) e λ no D0, vertical completa ×100, horária 24 h, recomendada
    sens = []
    base_jobs = cen.aplicar_cadencia(cen.jobs_vertical_completa(), "horaria_24h")
    esc100 = cen.com_escala(cen.ESCALA_ATUAL, 100)
    for p_mult in (0.25, 1.0, 3.0):
        for lam_mult in (0.25, 1.0, 4.0):
            js = [replace(j, p_revisao_fechado=min(1.0, j.p_revisao_fechado * p_mult),
                          lambda_mudanca_h=j.lambda_mudanca_h * lam_mult) for j in base_jobs]
            r = calcular_cenario(js, esc100, pfs["largo_tipado"], cen.POLITICAS["recomendada"])
            sens.append({"mult_p_revisao": p_mult, "mult_lambda": lam_mult, "gb_dia": r.gb_dia,
                         "acumulado_gb": r.acumulado_gb, "observacoes_dia": r.observacoes_dia})
    # GTM: medido hoje (115 eventos em ~30 dias) e por tráfego pago (819 cliques/30 d) com crescimento
    gtm = {"medido_raw_events": calcular_gtm(PerfilGTM(sessoes_dia=115 / 30, eventos_por_sessao=1, duracao_sessao_s=10,
                                                       origem="J:EA/schema-inventory.json:116 (115 linhas desde 15/09)"))}
    for fator in cen.FATORES_CRESCIMENTO:
        gtm[f"trafego_pago_x{fator}"] = calcular_gtm(PerfilGTM(sessoes_dia=819 / 30 * fator, eventos_por_sessao=8,
                                                               duracao_sessao_s=90,
                                                               origem="PREMISSA: 1 sessão por clique pago, 8 eventos, 90 s"))
    corpo = {
        "seed": SEED, "escala_atual": asdict(cen.ESCALA_ATUAL), "premissas": cen.premissas(),
        "perfis_bytes": {k: asdict(v) for k, v in pfs.items()}, "politicas": {k: asdict(v) for k, v in cen.POLITICAS.items()},
        "cadencias": cen.CADENCIAS, "limites_api": quotas.tabela_limites(), "grade": grade, "detalhe_jobs": detalhe,
        "termos_4h_vs_1x": termos, "sensibilidade": sens, "gtm": gtm,
    }
    codigo = sha256_codigo([str(p) for p in (LAB / "src" / "volc_dil" / "fundacao" / "capacidade").glob("*.py")]
                           + [str(Path(__file__))])
    corpo["manifesto"] = manifesto_execucao(
        nome="fundacao_capacidade_modelo", seed=SEED,
        entradas={"pg_medicoes.json": sha256_arquivo(str(pg_path)), "horas_campanha_d30.json": sha256_arquivo(str(horas_path))},
        parametros={"fatores": list(cen.FATORES_CRESCIMENTO), "cadencias": list(cen.CADENCIAS)},
        codigo_sha256=codigo, resultado=grade)
    return corpo


def _f(x: float, casas: int = 2) -> str:
    if x is None:
        return "–"
    if abs(x) >= 1000:
        return f"{x:,.0f}".replace(",", ".")
    return f"{x:.{casas}f}".replace(".", ",")


def _gb(x: float) -> str:
    if x < 0.01:
        return f"{x * 1024:.2f} MB".replace(".", ",")
    return f"{_f(x)} GB"


def markdown(c: dict) -> str:
    g = c["grade"]
    sel = lambda **kw: [x for x in g if all(x[k] == v for k, v in kw.items())]  # noqa: E731
    m = c["manifesto"]
    L = ["# Modelo de capacidade — resultado (GERADO)", "",
         "> Gerado por `experiments/data-intelligence-lab/scripts/fundacao_capacidade_modelo.py` a partir de "
         "`pg_medicoes.json` e `horas_campanha_d30.json`. Não editar à mão. Modelo determinístico; bytes medidos em "
         "PostgreSQL 16 descartável com DDL de medição (aproximação, ver `04-CADENCIA-E-CAPACIDADE.md`).", "",
         f"- fingerprint `{m['fingerprint'][:16]}…`, código `{m['codigo_sha256'][:16]}…`, resultado `{m['resultado_sha256'][:16]}…`",
         f"- entradas: " + ", ".join(f"`{k}` `{v[:12]}…`" for k, v in m["entradas_sha256"].items()), ""]
    L += ["## 1. Perfis de bytes (medidos, 1e6 linhas, sem partição)", "",
          "| perfil | formato | heap B/obs | índices B/obs | payload B/linha em lote (campanha/termo) | payload B/linha individual |",
          "|---|---|---:|---:|---|---|"]
    for k, p in c["perfis_bytes"].items():
        L.append(f"| {k} | {p['formato']} | {_f(p['heap_por_observacao'],1)} | {_f(p['indices_por_observacao'],1)} | "
                 f"{_f(p['payload_linha_em_lote']['campanha'],0)} / {_f(p['payload_linha_em_lote']['termo'],0)} | "
                 f"{_f(p['payload_linha_individual']['campanha'],0)} / {_f(p['payload_linha_individual']['termo'],0)} |")
    L += ["", "## 2. Jobs na escala atual (agenda documentada)", "",
          "| job | cron | janela | exec/dia | chamadas/dia | linhas lidas/dia | linhas distintas/dia | redundância | confirmação |",
          "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for j in c["detalhe_jobs"]["vertical_completa/atual"]:
        L.append(f"| {j['nome']} | `{j['cron']}` | D-{j['janela'][1]}..D-{j['janela'][0]} | {j['execucoes_dia']} | "
                 f"{_f(j['chamadas_dia'],0)} | {_f(j['linhas_lidas_dia'],0)} | {_f(j['linhas_distintas_dia'],1)} | "
                 f"{_f(100*j['fracao_redundante'],1)}% | {j['confirmacao'][:60]} |")
    t = c["termos_4h_vs_1x"]
    L += ["", f"Termos+keywords: a cada 4 h lê {_f(t['4h']['linhas_lidas_dia'],0)} linhas/dia para "
          f"{_f(t['4h']['linhas_distintas_dia'],0)} distintas; 1×/dia lê {_f(t['1x_dia']['linhas_lidas_dia'],0)} para "
          f"{_f(t['1x_dia']['linhas_distintas_dia'],0)} ({_f(t['4h']['chamadas_dia'],0)} → {_f(t['1x_dia']['chamadas_dia'],0)} chamadas/dia).", ""]
    for conj in ("atual", "vertical_completa"):
        L += [f"## 3. Cadência × crescimento — jobs `{conj}`", "",
              "| cadência intraday | × | ops Google Ads/dia | % Basic (15 mil) | chamadas JoinAds/dia | GB/dia v21 | GB/dia recomendada | 13 m v21 | 13 m recomendada | 3 a v21 | 3 a recomendada |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for cad in c["cadencias"]:
            for f in (1, 10, 100, 1000):
                v = sel(jobs=conj, cadencia=cad, crescimento=f, politica="v21_atual")[0]
                r = sel(jobs=conj, cadencia=cad, crescimento=f, politica="recomendada")[0]
                q = v["quota_google_ads"]
                L.append(f"| {cad} | {f} | {_f(q['operacoes_dia'],0)} | {_f(100*q['operacoes_dia_token_basic']['uso'],1)}% | "
                         f"{_f(v['chamadas_por_fonte'].get('joinads',0),0)} | {_gb(v['gb_dia'])} | {_gb(r['gb_dia'])} | "
                         f"{_gb(v['acumulado_gb']['13m'])} | {_gb(r['acumulado_gb']['13m'])} | {_gb(v['acumulado_gb']['3a'])} | "
                         f"{_gb(r['acumulado_gb']['3a'])} |")
        L.append("")
    L += ["## 4. Políticas de gravação — vertical completa, horária 24 h, ×100", "",
          "| política | perfil | observações/dia | linhas de payload/dia | GB/dia | 30 d | 13 m | 3 a |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for pol, perf in GRADE_POLITICAS:
        x = sel(jobs="vertical_completa", cadencia="horaria_24h", crescimento=100, politica=pol, perfil=perf)[0]
        L.append(f"| {pol} | {perf} | {_f(x['observacoes_dia'],0)} | {_f(x['linhas_payload_dia'],0)} | {_gb(x['gb_dia'])} | "
                 f"{_gb(x['acumulado_gb']['30d'])} | {_gb(x['acumulado_gb']['13m'])} | {_gb(x['acumulado_gb']['3a'])} |")
    L += ["", "## 5. Sensibilidade (vertical completa, horária 24 h, ×100, recomendada)", "",
          "| × p de revisão | × λ | observações/dia | GB/dia | 3 a |", "|---:|---:|---:|---:|---:|"]
    for s in c["sensibilidade"]:
        L.append(f"| {s['mult_p_revisao']} | {s['mult_lambda']} | {_f(s['observacoes_dia'],0)} | {_gb(s['gb_dia'])} | {_gb(s['acumulado_gb']['3a'])} |")
    L += ["", "## 6. GTM (orientado a evento; lote 10 s ou 20 eventos)", "",
          "| cenário | eventos/dia | requisições/dia | eventos/requisição | GB/dia | 3 a |", "|---|---:|---:|---:|---:|---:|"]
    for k, v in c["gtm"].items():
        L.append(f"| {k} | {_f(v['eventos_dia'],0)} | {_f(v['requisicoes_dia'],0)} | {_f(v['eventos_por_requisicao'],1)} | "
                 f"{_gb(v['gb_dia'])} | {_gb(v['acumulado_gb']['3a'])} |")
    L += ["", "## 7. Premissas (não medidas)", ""]
    for k, v in c["premissas"].items():
        L.append(f"- `{k}`: {v}")
    L.append("")
    return "\n".join(L)


def main() -> int:
    c = rodar()
    (BENCH / "modelo.json").write_text(json.dumps(c, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n",
                                       encoding="utf-8")
    (BENCH / "MODELO.md").write_text(markdown(c), encoding="utf-8")
    print(c["manifesto"]["fingerprint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
