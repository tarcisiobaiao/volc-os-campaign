"""Prova vertical shadow: custo real (Google Ads, broker de leitura) × receita no grão
reconciliável (campanha × dia, JoinAds por utm_campaign) → recomendação que NÃO é executada.

Duas etapas, dois ambientes, de propósito:

    # 1. coleta (backend/.venv: tem google-ads; o lab não tem)
    PYTHONPATH=tools/freedom-lab/src:. backend/.venv/bin/python -m volc_lab.prova_vertical coletar <dir>
    # 2. replay sem API (.venv-lab: duckdb/pandas), quantas vezes quiser
    PYTHONPATH=tools/freedom-lab/src .venv-lab/bin/python -m volc_lab.prova_vertical rodar <dir>

Regras inspiradas em supabase/migrations/v17_04_arbitragem_reconciliada.sql (não
aplicada em produção), sem reproduzi-la inteira: aqui não há project_id nem o roteador
GAM (0 linhas de GAM para a campanha), e a receita vem em USD com câmbio fixo. O que
vale: só receita com chave comum (campanha × dia), uma linha por dia de cada lado,
mesma campaign_id nos dois snapshots; janela aberta (últimos 3 dias no fuso da conta,
que o conector D-1 reescreve) não entra em decisão; receita ausente fica nula.
Os limiares de decisão abaixo são PARÂMETROS DO LABORATÓRIO, não a política do dono.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# Conta e MCC entram pelo ambiente na coleta (LAB_ADS_CUSTOMER, LAB_ADS_MCC); o código
# e os recibos só carregam a forma mascarada. A campanha é o objeto da prova.
CAMPANHA = "24278665189"
GAQL = ("SELECT segments.date, metrics.clicks, metrics.cost_micros, metrics.conversions, "
        "metrics.conversions_value FROM campaign WHERE campaign.id = 24278665189 "
        "AND segments.date DURING LAST_30_DAYS ORDER BY segments.date")

PARAMETROS = {
    "cambio_usd_brl": 5.25,          # o mesmo câmbio fixo que o app usa desde 18/02
    "dias_imaturos": 3,              # conector D-1 reescreve 3 dias
    "min_cliques_maduros": 200,
    "estresse_receita": 2.0,         # e se a receita madura dobrar
    "estresse_cambio": 1.5,          # e se o câmbio estiver 50% subestimado
    "roas_equilibrio": 1.0,
    "roas_aumentar": 1.5,
    "max_custo_sem_receita": 0.10,   # fração do custo maduro sem receita que ainda permite decidir
}
FUSO_CONTA = ZoneInfo("America/Sao_Paulo")


class SnapshotInvalido(ValueError):
    pass


def _data_local(instante: str) -> date:
    return datetime.fromisoformat(instante.replace("Z", "+00:00")).astimezone(FUSO_CONTA).date()


def carregar_snapshots(d: Path):
    custo = json.loads((d / "custo_ads_snapshot.json").read_text())
    receita = json.loads((d / "receita_joinads_snapshot.json").read_text())
    for nome, doc in (("custo", custo), ("receita", receita)):
        if str(doc.get("campaign_id")) != CAMPANHA:
            raise SnapshotInvalido(f"{nome}: campaign_id {doc.get('campaign_id')!r} ≠ {CAMPANHA}")
        datas = [l["date"] for l in doc["linhas"]]
        if len(datas) != len(set(datas)):
            raise SnapshotInvalido(f"{nome}: data repetida no snapshot (o join somaria duas vezes)")
    # O dado mais velho manda: a receita lida antes do custo ainda não viu dias que o custo já viu.
    as_of = min(_data_local(custo["lido_em"]), _data_local(receita["lido_em"]))
    return custo, receita, as_of


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def coletar(d: Path) -> None:
    import os

    from volc_lab.brokers import google_ads
    from volc_lab.brokers.recibos import mascarar

    conta, mcc = os.environ.get("LAB_ADS_CUSTOMER", ""), os.environ.get("LAB_ADS_MCC", "")
    if not (conta and mcc):
        raise SystemExit("defina LAB_ADS_CUSTOMER e LAB_ADS_MCC no ambiente da coleta")
    linhas = google_ads.ler(conta, GAQL, login_customer_id=mcc, destino_recibo=d / "recibos-ads.jsonl")
    snap = {"_sobre": "Custo diário lido pelo broker Google Ads (search_stream, leitura).",
            "conta": mascarar(conta), "campaign_id": CAMPANHA, "moeda": "BRL", "fuso": "America/Sao_Paulo",
            "gaql_sha256": hashlib.sha256(GAQL.encode()).hexdigest(), "lido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "linhas": [{"date": r.segments.date, "clicks": int(r.metrics.clicks),
                        "cost_micros": int(r.metrics.cost_micros), "conversions": float(r.metrics.conversions),
                        "conversions_value": float(r.metrics.conversions_value)} for r in linhas]}
    (d / "custo_ads_snapshot.json").write_text(json.dumps(snap, indent=1, ensure_ascii=False))
    print({"linhas": len(snap["linhas"]), "custo_brl": round(sum(l["cost_micros"] for l in snap["linhas"]) / 1e6, 2)})


def transformar(d: Path, as_of: date | None = None):
    import duckdb

    custo_doc, receita_doc, as_of_snap = carregar_snapshots(d)
    as_of = as_of or as_of_snap
    custo, receita = custo_doc["linhas"], receita_doc["linhas"]
    con = duckdb.connect()
    con.execute("create table custo(date date, clicks bigint, cost_micros bigint, conversions double, conversions_value double)")
    con.executemany("insert into custo values (?,?,?,?,?)",
                    [(l["date"], l["clicks"], l["cost_micros"], l["conversions"], l["conversions_value"]) for l in custo])
    con.execute("create table receita(date date, revenue_usd double)")
    con.executemany("insert into receita values (?,?)", [(l["date"], l["revenue_usd"]) for l in receita])
    corte = as_of - timedelta(days=PARAMETROS["dias_imaturos"])
    df = con.execute(f"""
        select coalesce(c.date, r.date) as date,
               c.cost_micros / 1e6 as custo_brl, c.clicks,
               r.revenue_usd, r.revenue_usd * {PARAMETROS['cambio_usd_brl']} as receita_brl,
               c.conversions_value as valor_conversao_google,
               coalesce(c.date, r.date) < date '{corte}' as maduro,
               case when c.date is null then 'sem_custo'
                    when r.date is null or r.revenue_usd is null then 'receita_ausente'
                    else 'reconciliado' end as estado
          from custo c full outer join receita r on r.date = c.date
         order by 1""").df()
    return df, corte


def janela(df, inicio=None, fim=None):
    import pandas as pd

    m = df[df["maduro"] & (df["estado"] == "reconciliado")]
    if inicio:
        m = m[m["date"] >= pd.Timestamp(inicio)]
    if fim:
        m = m[m["date"] <= pd.Timestamp(fim)]
    if m.empty:  # janela sem dia reconciliado: ausência, não zero
        return {"dias": 0, "custo_brl": None, "receita_brl": None, "cliques": None, "roas": None,
                "cpc": None, "rpc": None, "contribuicao_bruta": None}
    custo, receita, cliques = m["custo_brl"].sum(), m["receita_brl"].sum(), int(m["clicks"].sum())
    return {"dias": int(len(m)), "custo_brl": round(float(custo), 2), "receita_brl": round(float(receita), 2),
            "cliques": cliques, "roas": round(float(receita / custo), 4) if custo else None,
            "cpc": round(float(custo / cliques), 4) if cliques else None,
            "rpc": round(float(receita / cliques), 4) if cliques else None,
            "contribuicao_bruta": round(float(receita - custo), 2)}


def decidir(madura: dict, lacunas: list[str], fracao_custo_sem_receita: float = 0.0):
    from volc_lab.brokers.valor_operacional import RecomendacaoShadow

    p = PARAMETROS
    if fracao_custo_sem_receita > p["max_custo_sem_receita"]:
        return RecomendacaoShadow(CAMPANHA, "evidencia_insuficiente",
                                  (f"{fracao_custo_sem_receita:.0%} do custo maduro não tem receita reconciliada",),
                                  None, tuple(lacunas))
    if madura["roas"] is None or (madura["cliques"] or 0) < p["min_cliques_maduros"]:
        return RecomendacaoShadow(CAMPANHA, "evidencia_insuficiente",
                                  (f"cliques maduros {madura['cliques']} < {p['min_cliques_maduros']}",), None, tuple(lacunas))
    estressado = madura["roas"] * p["estresse_receita"] * p["estresse_cambio"]
    motivos = [f"ROAS maduro {madura['roas']:.3f} em {madura['cliques']} cliques",
               f"ROAS sob estresse (receita ×{p['estresse_receita']}, câmbio ×{p['estresse_cambio']}) = {estressado:.3f}"]
    if estressado < p["roas_equilibrio"]:
        direcao = "pausar"
        motivos.append("mesmo no estresse a campanha não paga o próprio custo")
    elif madura["roas"] < p["roas_equilibrio"]:
        direcao = "reduzir"
    elif madura["roas"] >= p["roas_aumentar"]:
        direcao = "aumentar"
    else:
        direcao = "manter"
    # Nenhum valor monetário sugerido: o broker não calcula verba nem lance.
    return RecomendacaoShadow(CAMPANHA, direcao, tuple(motivos), None, tuple(lacunas))


def rodar(d: Path) -> dict:
    t0 = time.perf_counter()
    df, corte = transformar(d)
    as_of = corte + timedelta(days=PARAMETROS["dias_imaturos"])
    madura = janela(df)
    recente = janela(df, inicio=corte - timedelta(days=5))
    maduros = df[df["maduro"]]
    sem_receita = maduros[(maduros["estado"] == "receita_ausente") & (maduros["custo_brl"].fillna(0) > 0)]
    sem_custo = maduros[(maduros["estado"] == "sem_custo") & (maduros["receita_brl"].fillna(0) > 0)]
    custo_maduro = float(maduros["custo_brl"].sum())
    fracao = float(sem_receita["custo_brl"].sum()) / custo_maduro if custo_maduro else 1.0
    lacunas = [
        "receita sem histórico as-of (upsert do último valor); maturidade inferida pela regra D-1, não auditada",
        f"câmbio fixo {PARAMETROS['cambio_usd_brl']} (o mesmo do app); sem câmbio diário",
        "gam_metrics com 0 linhas para a campanha; ausência real ou RLS não distinguida",
        "receita JoinAds lida sob RLS da sessão humana e sem project_id; receita oculta por RLS não é visível aqui",
        "revshare e imposto vêm da configuração da tela, não de contrato; ROAS aqui é bruto",
        "só grão campanha × dia; sem receita por URL, sessão, hora ou placement",
        "conversions_value do Google é valor estático por conversão, não receita; ignorado na decisão",
        "limiares são parâmetros do laboratório, não a política do dono (volc_ads/inteligencia_decisao/politicas.py)",
        "joinads_metrics.revenue tem DEFAULT 0 (src/sql/joinads/01_joinads_metrics.sql): receita 0,00 pode ser default, não medição",
        "chave de joinads_metrics inclui joinads_domain; não está provado que o snapshot somou todos os domínios da campanha",
        "fuso do campo date do JoinAds não declarado; o custo está em America/Sao_Paulo",
    ]
    if len(sem_receita):
        lacunas.append(f"dias maduros com custo e sem receita (ausentes, não zero): "
                       f"{sem_receita['date'].dt.date.astype(str).tolist()} = {fracao:.1%} do custo maduro")
    if len(sem_custo):
        lacunas.append(f"dias maduros com receita e sem linha de custo: {sem_custo['date'].dt.date.astype(str).tolist()}")
    rec = decidir(madura, lacunas, fracao)
    df.assign(date=df["date"].dt.date).to_csv(d / "transformacao.csv", index=False)
    saida = {"campanha": CAMPANHA, "as_of": str(as_of), "corte_maturidade": str(corte), "parametros": PARAMETROS,
             "codigo_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "janela_madura": madura, "janela_madura_recente": recente,
             "fracao_custo_maduro_sem_receita": round(fracao, 4),
             "valor_conversao_google_total": round(float(df["valor_conversao_google"].sum()), 2),
             "recomendacao": asdict(rec)}
    # A duração fica fora do artefato hasheado, para o replay reproduzir o mesmo SHA.
    (d / "resultado.json").write_text(json.dumps(saida, indent=1, ensure_ascii=False, default=str))
    return saida | {"duracao_s": round(time.perf_counter() - t0, 3)}


if __name__ == "__main__":
    acao, d = sys.argv[1], Path(sys.argv[2])
    if acao == "coletar":
        coletar(d)
    else:
        print(json.dumps(rodar(d), indent=1, ensure_ascii=False, default=str))
