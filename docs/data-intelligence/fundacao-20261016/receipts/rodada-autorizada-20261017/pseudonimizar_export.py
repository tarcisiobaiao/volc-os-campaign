"""Pseudonimizador em fluxo da exportação read-only (rodada autorizada, item 1).

Lê do stdin as linhas JSON de `export_snapshot.sql` (vindas pelo SSH; nunca gravadas em disco cruas),
troca todo identificador operacional por um pseudônimo HMAC-SHA256 determinístico (chave aleatória de 32 bytes,
gravada 0600 no próprio diretório de artefatos e apagada com ele) e grava só o resultado pseudonimizado.

- id só de dígitos → 12 dígitos sem zero à esquerda (o parser de chave de campanha continua aceitando);
  o mesmo espaço de nomes "campaign" para `campaign_id` (Google e JoinAds), `resource_id` e o `custom_value`
  de `utm_campaign`, de modo que a junção custo × receita sobrevive; texto → `t_` + 16 hex.
- uuid/chaves textuais (run, lote, observação, request id, domínio, ad unit) → prefixo + 16 hex.
- verificação final: nenhum valor cru de identificador aparece em nenhum arquivo gravado.
Imprime só contagens, intervalos e hashes (nunca valores).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path

saida = Path(sys.argv[1])
assert saida.is_dir() and (saida.stat().st_mode & 0o077) == 0, "diretório de artefatos precisa ser 0700"
os.umask(0o077)
chave_arq = saida / "chave.hmac"
if not chave_arq.exists():
    chave_arq.write_bytes(secrets.token_bytes(32))
os.chmod(chave_arq, 0o600)
CHAVE = chave_arq.read_bytes()
crus: set[str] = set()
mapa: dict[tuple[str, str], str] = {}


def _h(ns: str, v: str) -> bytes:
    return hmac.new(CHAVE, f"{ns}\x00{v}".encode(), hashlib.sha256).digest()


def p(ns: str, v, prefixo: str | None = None):
    if v is None:
        return None
    v = str(v)
    crus.add(v)
    k = (ns, v)
    if k not in mapa:
        d = _h(ns, v)
        if v.isascii() and v.isdigit() and prefixo is None:
            out = str(10**11 + int.from_bytes(d[:8], "big") % (9 * 10**11))
        else:
            out = f"{prefixo or 't'}_{d[:8].hex()}"
        mapa[k] = out
    return mapa[k]


arqs = {t: open(saida / f"{t}.jsonl", "w", encoding="utf-8") for t in ("v21", "v21_run", "joinads", "joinads_run")}
cont = {t: 0 for t in arqs}
meta = None
for linha in sys.stdin:
    linha = linha.strip()
    if not linha.startswith("{"):
        continue
    r = json.loads(linha)
    t = r.pop("_t")
    if t == "meta":
        meta = r
        continue
    if t == "v21":
        cust, camp = p("customer", r["customer_id"]), p("campaign", r["campaign_id"])
        moedas = r.pop("payload_currencies") or []
        payload = {"metrics": ({"_linha_presente": 1} if r.pop("payload_metrics_line") else {})}
        if len(moedas) == 1:
            payload["customer"] = {"currencyCode": moedas[0]}
        r.update(observation_id=p("obs", r["observation_id"], "obs"), run_id=p("run", r["run_id"], "run"),
                 batch_id=p("batch", r["batch_id"], "lote"), customer_id=cust, campaign_id=camp,
                 resource_id=p("campaign", r["resource_id"]), batch_request_id=p("req", r["batch_request_id"], "req"),
                 observation_key=f"campaign_day:{cust}:{camp}:{r['metric_date']}", ad_group_id=None, criterion_id=None,
                 dimensions={}, batch_payload=payload, n_moedas_payload=len(moedas))
    elif t == "v21_run":
        r["run_id"] = p("run", r["run_id"], "run")
    elif t == "joinads":
        moedas = r.pop("payload_currencies") or []
        ck = r.get("custom_key")
        ck_req = r.pop("batch_request_custom_key", None)
        r.update(observation_key=p("jobs", r["observation_key"], "jobs"), run_key=p("jrun", r["run_key"], "jrun"),
                 batch_key=p("jbatch", r["batch_key"], "jlote"), domain=p("domain", r["domain"], "dom"),
                 campaign_id=p("campaign", r["campaign_id"]),
                 custom_value=p("campaign" if ck == "utm_campaign" else f"kv:{ck}", r["custom_value"]),
                 ad_unit_name=p("adunit", r["ad_unit_name"], "au"), post_id=None, land_uri=None,
                 batch_request_meta=({"custom_key": ck_req} if ck_req else {}),
                 batch_payload=({"currency": moedas[0]} if len(moedas) == 1 else {}), n_moedas_payload=len(moedas))
    elif t == "joinads_run":
        r["run_key"] = p("jrun", r["run_key"], "jrun")
    arqs[t].write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    cont[t] += 1
for f in arqs.values():
    f.close()
assert meta is not None and meta["tx_read_only"] == "on" and meta["tx_isolation"] == "repeatable read", "transação não era RR read-only"
(saida / "meta.json").write_text(json.dumps(meta, sort_keys=True) + "\n")
# injetividade e ausência de valor cru
assert len(set(mapa.values())) == len(mapa), "colisão de pseudônimo"
vazados = 0
for t in arqs:
    txt = (saida / f"{t}.jsonl").read_text(encoding="utf-8")
    vazados += sum(1 for v in crus if len(v) >= 6 and f'"{v}"' in txt)
assert vazados == 0, f"{vazados} identificadores crus apareceram na saída"
for arq in saida.iterdir():
    os.chmod(arq, 0o600)
resumo = {"linhas": cont, "identificadores_pseudonimizados": len(mapa),
          "por_espaco": {ns: sum(1 for k in mapa if k[0] == ns) for ns in sorted({k[0] for k in mapa})},
          "identificadores_crus_na_saida": vazados, "snapshot_at": meta["snapshot_at"],
          "sha256": {f"{t}.jsonl": hashlib.sha256((saida / f"{t}.jsonl").read_bytes()).hexdigest() for t in arqs}}
print(json.dumps(resumo, indent=1, sort_keys=True))
