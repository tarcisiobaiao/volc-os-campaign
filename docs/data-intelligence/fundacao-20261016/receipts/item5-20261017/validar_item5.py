"""Gate estrutural do item 5: compara export de rollback × versão nova de cada coletor.

Falha se mudar trigger, cron, timezone, credencial, conexões, nós fora da lista permitida ou settings além de
errorWorkflow; checa sintaxe de todo Code node com `node --check`. Uso: validar_item5.py <rollback> <novos> [id_errwf]
"""
import glob, json, subprocess, sys, tempfile
from pathlib import Path

ROLL, NOVOS = Path(sys.argv[1]), Path(sys.argv[2])
ERRWF = sys.argv[3] if len(sys.argv) > 3 else None
PERMITIDOS = {
    "google_d0": {"Code", "Google Ads - Get Campaigns1", "Google Ads - Get metrics1", "Supabase | Ingestão canônica shadow", "Supabase | Finalizar run"},
    "google_d1": {"Code15", "Google Ads - Get Campaigns", "Google Ads - Get metrics", "Supabase | Ingestão canônica shadow", "Supabase | Finalizar run"},
    "google_termos": {"Code | Normalizar termos e keywords", "Supabase | Ingestão termos e keywords", "Supabase | Finalizar run"},
    "joinads_intraday": {"Normaliza coleta", "Config"},
    "joinads_d1": {"Normaliza coleta", "Config"},
}
falhas, resumo = [], {}
for chave, perm in PERMITIDOS.items():
    (f,) = glob.glob(str(ROLL / f"{chave}__*.json"))
    a, b = json.load(open(f)), json.load(open(NOVOS / f"{chave}.json"))
    na, nb = {n["name"]: n for n in a["nodes"]}, {n["name"]: n for n in b["nodes"]}
    if set(na) != set(nb):
        falhas.append(f"{chave}: conjunto de nós mudou")
    mudados = sorted(n for n in na if json.dumps(na[n], sort_keys=True) != json.dumps(nb.get(n), sort_keys=True))
    fora = [n for n in mudados if n not in perm]
    if fora:
        falhas.append(f"{chave}: nós alterados fora da lista: {fora}")
    for n in na:
        if na[n]["type"].endswith(("scheduleTrigger", "manualTrigger", "webhook")) and na[n] != nb.get(n):
            falhas.append(f"{chave}: trigger {n} mudou")
        if na[n].get("credentials") != nb.get(n, {}).get("credentials"):
            falhas.append(f"{chave}: credencial de {n} mudou")
    if json.dumps(a["connections"], sort_keys=True) != json.dumps(b["connections"], sort_keys=True):
        falhas.append(f"{chave}: conexões mudaram")
    sa = {k: v for k, v in (a.get("settings") or {}).items() if k != "errorWorkflow"}
    sb = {k: v for k, v in (b.get("settings") or {}).items() if k != "errorWorkflow"}
    for k in set(sa) | set(sb):
        if k in sb and sa.get(k) != sb.get(k):
            falhas.append(f"{chave}: setting {k} mudou")
    if ERRWF and (b.get("settings") or {}).get("errorWorkflow") != ERRWF:
        falhas.append(f"{chave}: errorWorkflow não aponta para o comum")
    for n in nb.values():
        if n["type"].endswith(".code"):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as t:
                t.write("(async () => {\n" + n["parameters"]["jsCode"] + "\n})();\n")
            r = subprocess.run(["node", "--check", t.name], capture_output=True, text=True)
            if r.returncode:
                falhas.append(f"{chave}: sintaxe inválida em {n['name']}: {r.stderr[:200]}")
        def strings(x):
            if isinstance(x, dict):
                for v in x.values(): yield from strings(v)
            elif isinstance(x, list):
                for v in x: yield from strings(v)
            elif isinstance(x, str) and x.startswith("=") and n["type"].split(".")[-1] != "code":
                yield x
        for expr in strings(n.get("parameters", {})):
            if expr.count("{{") != expr.count("}}"):
                falhas.append(f"{chave}: expressão desbalanceada em {n['name']}")
    resumo[chave] = {"nos_alterados": mudados, "errorWorkflow": (b.get("settings") or {}).get("errorWorkflow")}
print(json.dumps({"ok": not falhas, "falhas": falhas, "resumo": resumo}, ensure_ascii=False, indent=1))
sys.exit(1 if falhas else 0)
