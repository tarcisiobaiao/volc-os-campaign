"""Replay/shadow com o snapshot real pseudonimizado (rodada autorizada, item 1).

Uso: python rodar_replay_real.py <dir_artefatos>   (com o PYTHONPATH do lab)
Lê só os JSONL do diretório 0700; grava ledgers e o resumo completo SÓ nesse diretório; imprime no stdout
apenas agregados (contagens, razões, datas, códigos de bloqueio sem entidade, hashes, tempos) — nenhum
identificador, nenhum valor monetário absoluto.

Variantes (mesmo snapshot):
  E  estrito — contrato como está: moeda só com prova no payload (hoje nenhuma das duas fontes declara);
  H  hipótese declarada — moeda atestada BRL (Google) e USD (JoinAds) e câmbio USD→BRL 27/5 como PARÂMETRO de
     simulação (não é prova, não é cotação), para ver o que o kernel faria se a moeda estivesse provada;
  H-sem-presos — H sem as linhas dos runs v21 presos em `running`, para medir o efeito deles.
Políticas: manter, equal, greedy_conservador, regra_margem (madura 72 h), guardiao_72h(regra_margem) e a
anti-baseline regra_margem_null_zero (ausente vira zero), que precisa ser recusada.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from volc_dil.fundacao.observacao import AdaptacaoImpossivel, ObservacaoInvalida, adaptar_google_ads_v21, adaptar_joinads_v2
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado
from volc_dil.fundacao.shadow.ledger import LedgerShadow, SinkJsonl, verificar_cadeia
from volc_dil.fundacao.shadow.motor import ConfigShadow, auditar_null_zero, executar_replay
from volc_dil.fundacao.shadow.politicas import Guardiao72h, Manter, RegraMargem, equal, greedy_conservador, regra_margem_null_zero
from volc_dil.fundacao.shadow.real import carregar_jsonl, cortes_do_fluxo, deduplicar
from volc_dil.fundacao.shadow.snapshot import CambioDeclarado, ConfigCorte, construir_snapshot
from volc_dil.fundacao.shadow.versao import versao_codigo

A = Path(sys.argv[1])
v21 = carregar_jsonl(A / "v21.jsonl")
ja = carregar_jsonl(A / "joinads.jsonl")
runs = carregar_jsonl(A / "v21_run.jsonl")
jruns = carregar_jsonl(A / "joinads_run.jsonl")
meta = json.loads((A / "meta.json").read_text())
snap_at = datetime.fromisoformat(meta["snapshot_at"])
out: dict = {"natureza": "testado_em_replay (snapshot real read-only pseudonimizado)", "versao_codigo": versao_codigo(),
             "snapshot_at": meta["snapshot_at"],
             "entradas_sha256": {f: hashlib.sha256((A / f).read_bytes()).hexdigest() for f in
                                 ("v21.jsonl", "v21_run.jsonl", "joinads.jsonl", "joinads_run.jsonl")}}


def r4(x):
    return None if x is None else round(float(x), 4)


def sem_ent(code: str) -> str:  # código de bloqueio/motivo sem data nem id
    return re.sub(r":\d{4}-\d{2}-\d{2}.*$", "", re.sub(r"\b\d{6,}\b", "<id>", code))


# ------------------------------------------------------------------ 1. qualidade e cobertura direto das linhas
q: dict = {}
q["v21_linhas"] = len(v21)
q["v21_dias"] = sorted({l["metric_date"] for l in v21})
q["v21_campanhas"] = len({l["campaign_id"] for l in v21})
q["v21_runs_com_linhas"] = len({l["run_id"] for l in v21})
q["v21_por_run_status"] = dict(Counter(l["run_status"] for l in v21))
q["v21_moeda_coluna"] = dict(Counter(l["currency_code"] for l in v21))
q["v21_moeda_no_payload"] = dict(Counter(l["n_moedas_payload"] for l in v21))
z = [l for l in v21 if Decimal(str(l["metrics"].get("cost_micros", 0))) == 0 and Decimal(str(l["metrics"].get("impressions", 0))) == 0]
q["v21_zero_custo_e_impr"] = len(z)
q["v21_zero_sem_linha_de_metrica"] = sum(1 for l in z if not l["batch_payload"]["metrics"])
q["v21_zero_com_linha_de_metrica"] = sum(1 for l in z if l["batch_payload"]["metrics"])
q["v21_nao_zero_sem_linha"] = sum(1 for l in v21 if l not in z and not l["batch_payload"]["metrics"])
q["v21_metrica_ausente"] = dict(Counter(k for l in v21 for k in ("cost_micros", "impressions", "clicks", "conversions") if k not in l["metrics"]))
# campanhas por dia: com custo > 0 em alguma leitura x só zero sintetizado
por_cd = defaultdict(list)
for l in v21:
    por_cd[(l["metric_date"], l["campaign_id"])].append(l)
q["v21_campanha_dia"] = {d: {"celulas": sum(1 for (dd, _) in por_cd if dd == d),
                             "com_custo_positivo": sum(1 for (dd, c), ls in por_cd.items() if dd == d and any(Decimal(str(x["metrics"].get("cost_micros", 0))) > 0 for x in ls)),
                             "so_zero_sintetizado": sum(1 for (dd, c), ls in por_cd.items() if dd == d and all(not x["batch_payload"]["metrics"] for x in ls))}
                         for d in q["v21_dias"]}
q["ja_linhas"] = dict(Counter(l["endpoint"] for l in ja))
q["ja_moeda_coluna"] = dict(Counter(l["currency_code"] for l in ja))
q["ja_moeda_no_payload"] = dict(Counter(l["n_moedas_payload"] for l in ja))
q["ja_data_status"] = dict(Counter(f"{l['endpoint']}|{l['data_status']}" for l in ja).most_common())
q["ja_hash_zero"] = sum(1 for l in ja if l["batch_payload_sha256"] == "0" * 64)
q["ja_kv_valores_distintos"] = len({l["custom_value"] for l in ja if l["endpoint"] == "key_value_campaign_adunit"})
q["ja_kv_chave_pedida_igual_devolvida"] = dict(Counter((l.get("batch_request_meta") or {}).get("custom_key") == l["custom_key"] for l in ja if l["endpoint"] == "key_value_campaign_adunit"))
camp_g = {l["campaign_id"] for l in v21}
camp_ja = {l["custom_value"] for l in ja if l["endpoint"] == "key_value_campaign_adunit"}
q["juncao_kv_com_campanha_google"] = {"kv_que_casam": len(camp_ja & camp_g), "kv_sem_campanha_google": len(camp_ja - camp_g),
                                      "campanhas_google_sem_kv": len(camp_g - camp_ja)}
# cobertura kv/earnings por dia, última leitura de cada célula (razão; sem valores absolutos)
ult: dict = {}
for l in sorted(ja, key=lambda x: (x["collected_at"], x["observation_key"])):
    if l["endpoint"] == "earnings":
        ult[("e", l["metric_date"])] = l
    else:
        ult[("k", l["metric_date"], l["custom_value"], l["ad_unit_name"])] = l
cob = {}
for d in sorted({l["metric_date"] for l in ja}):
    e = ult.get(("e", d))
    kv = sum(Decimal(str(l["revenue_client"] or 0)) for k, l in ult.items() if k[0] == "k" and k[1] == d)
    cob[d] = r4(kv / Decimal(str(e["revenue_client"]))) if e and e["revenue_client"] not in (None, 0) and Decimal(str(e["revenue_client"])) != 0 else None
q["cobertura_kv_sobre_earnings_por_dia"] = cob
# dias com custo E receita
dias_custo, dias_rec = set(q["v21_dias"]), {d for d, v in cob.items() if v is not None}
q["dias_com_custo_e_receita"] = sorted(dias_custo & dias_rec)
out["qualidade"] = q

# ------------------------------------------------------------------ 2. runs presos
presos = [r for r in runs if r["status"] == "running" and datetime.fromisoformat(r["started_at"]) < snap_at - timedelta(minutes=30)]
out["runs_presos"] = {
    "v21_por_status": dict(Counter(r["status"] for r in runs)),
    "presos": [{"collector": r["collector"], "started_at": r["started_at"], "horas_preso": r4((snap_at - datetime.fromisoformat(r["started_at"])).total_seconds() / 3600),
                "n_obs": r["n_obs"], "n_obs_campaign_day": r["n_obs_campaign_day"], "ultima_obs": r["max_obs_created_at"],
                "batches_written": r["batches_written"], "finished_at": r["finished_at"]} for r in presos],
    "runs_v21_por_coletor_status": dict(Counter(f"{r['collector']}|{r['status']}" for r in runs)),
    "joinads_por_status": dict(Counter(f"{r['collector']}|v{r['collector_version']}|{r['status']}" for r in jruns)),
}
ids_presos = {r["run_id"] for r in presos}


# ------------------------------------------------------------------ 3. replay
def adaptar(linhas_v21, linhas_ja, atestar: bool):
    brutas, dead = [], Counter()
    for linhas, f, m in ((linhas_v21, adaptar_google_ads_v21, "BRL"), (linhas_ja, adaptar_joinads_v2, "USD")):
        for l in linhas:
            try:
                brutas.extend(f(l, moeda_atestada=m if atestar else None))
            except (AdaptacaoImpossivel, ObservacaoInvalida, KeyError) as e:
                dead[type(e).__name__] += 1
    vers, desc, quar = deduplicar(brutas)
    st = Counter((o.fonte, o.metrica.value, o.status.value, sem_ent(o.motivo or "")) for o in vers)
    return vers, {"brutas": len(brutas), "versoes": len(vers), "leituras_sem_nova_versao": desc, "quarentena": len(quar),
                  "dead_letter": dict(dead),
                  "status_por_metrica": {"|".join(k): n for k, n in sorted(st.items())}}


POLS = (Manter(), equal(), greedy_conservador(), RegraMargem(), Guardiao72h(RegraMargem()), regra_margem_null_zero())


def resumo_replay(vers, cfg, rotulo):
    fi = FluxoIndexado(vers, ambiguidade="quarentena")
    cortes = cortes_do_fluxo(fi, timedelta(hours=1))
    led_dir = A / f"ledger_{rotulo}"
    led_dir.mkdir(mode=0o700, exist_ok=True)
    for f in led_dir.glob("*.jsonl"):
        f.unlink()
    led = LedgerShadow(SinkJsonl(led_dir))
    t0 = time.perf_counter()
    res = executar_replay(fi, cortes, POLS, config=cfg, seed=None, ledger=led)
    dt = time.perf_counter() - t0
    pol = {}
    for p in POLS:
        acoes, bloq, motivos, assin = Counter(), Counter(), Counter(), []
        nb = 0
        for d in res.da_politica(p.nome):
            assin.append(d.decisao.assinatura())
            for pr in d.decisao.propostas:
                acoes[pr.acao.value] += 1
                if pr.bloqueada:
                    nb += 1
                    for b in pr.bloqueios:
                        bloq[sem_ent(b)] += 1
                elif pr.acao.value in ("pausar", "reduzir_verba", "aumentar_verba"):
                    motivos["nao_bloqueada:" + pr.acao.value] += 1
        trocas = sum(1 for a, b in zip(assin, assin[1:]) if a != b)
        pol[p.nome] = {"propostas_por_acao": dict(acoes), "propostas_bloqueadas": nb, "bloqueios": dict(bloq.most_common()),
                       "mudancas_de_verba_nao_bloqueadas": dict(motivos), "trocas_entre_cortes": trocas, "cortes": len(assin)}
    # auditoria null→zero em cortes diários às 07h locais (mesmos snapshots para todas as políticas)
    snaps = [construir_snapshot(fi, t, cfg.corte) for t in cortes if t.astimezone(ZONA).hour == 7]
    aud = {p.nome: auditar_null_zero(p, snaps) for p in POLS}
    ult = construir_snapshot(fi, cortes[-1], cfg.corte) if cortes else None
    fatos = Counter((f.custo.estado.value, f.receita.estado.value) for f in ult.fatos) if ult else Counter()
    cobs = {c.dia.isoformat(): {"fracoes": [[m, r4(f) if f is not None else None, d] for m, f, d in c.fracoes],
                                "bloqueios": sorted({sem_ent(b) for b in c.bloqueios}), "denominador": c.denominador}
            for c in (ult.cobertura if ult else ())}
    return {"n_cortes": len(cortes), "primeiro_corte": cortes[0].isoformat() if cortes else None,
            "ultimo_corte": cortes[-1].isoformat() if cortes else None, "n_decisoes": len(res.decisoes),
            "decisoes_sha256": res.sha256(), "ledger_sha256": led.sha256(),
            "ledger_cadeia_ok": verificar_cadeia(led_dir / "ledger.jsonl") == len(res.decisoes),
            "tempo_s": round(dt, 2), "ms_por_corte": round(1000 * dt / max(1, len(cortes)), 1),
            "politicas": pol, "auditoria_null_zero": aud,
            "ultimo_snapshot": {"fatos_custo_receita": {f"{a}|{b}": n for (a, b), n in sorted(fatos.items())},
                                "bloqueios_entidade": sorted({sem_ent(b) for _, bs in ult.bloqueios_entidade for b in bs}) if ult else [],
                                "cobertura": cobs}}


from zoneinfo import ZoneInfo  # noqa: E402
ZONA = ZoneInfo("America/Sao_Paulo")
cambio = (CambioDeclarado("USD", "BRL", 27, 5, "hipotese:parametro_de_simulacao"),)
vE, aE = adaptar(v21, ja, atestar=False)
vH, aH = adaptar(v21, ja, atestar=True)
vP, aP = adaptar([l for l in v21 if l["run_id"] not in ids_presos], ja, atestar=True)
out["adaptacao"] = {"E": aE, "H": aH, "H_sem_presos": aP}
out["replay"] = {"E": resumo_replay(vE, ConfigShadow(ConfigCorte()), "E"),
                 "H": resumo_replay(vH, ConfigShadow(ConfigCorte(cambios=cambio)), "H"),
                 "H_sem_presos": resumo_replay(vP, ConfigShadow(ConfigCorte(cambios=cambio)), "H_sem_presos")}
out["efeito_runs_presos"] = {"linhas_v21_dos_presos": sum(1 for l in v21 if l["run_id"] in ids_presos),
                             "decisoes_iguais_H_vs_H_sem_presos": out["replay"]["H"]["decisoes_sha256"] == out["replay"]["H_sem_presos"]["decisoes_sha256"]}
(A / "resumo_replay.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n")
print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True, default=str))
