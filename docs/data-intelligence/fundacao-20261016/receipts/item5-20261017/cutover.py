"""Cutover de UM coletor: PUT da versão nova (mesmo id, mesmo cron), confere estado ativo e o que ficou gravado.
Uso: cutover.py <chave> <dir_novos> <dir_saida>   |   rollback: cutover.py --rollback <chave> <dir_rollback> <dir_saida>
Grava o workflow lido depois do PUT (0600) e imprime versionId, ativo, errorWorkflow, cron, timezone e sha."""
import glob, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from n8n_cliente import CANONICOS, chamar
rb = sys.argv[1] == "--rollback"
chave, origem, saida = sys.argv[2:5] if rb else sys.argv[1:4]
wid = CANONICOS[chave]
if rb:
    (f,) = glob.glob(f"{origem}/{chave}__*.json"); w = json.load(open(f))
    corpo = {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
             "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in ("executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveManualExecutions", "saveExecutionProgress", "executionTimeout", "errorWorkflow", "timezone", "callerPolicy")}}
else:
    corpo = json.load(open(f"{origem}/{chave}.json"))
antes = chamar("GET", f"/workflows/{wid}")
chamar("PUT", f"/workflows/{wid}", corpo)
g = chamar("GET", f"/workflows/{wid}")
if antes.get("active") and not g.get("active"):
    chamar("POST", f"/workflows/{wid}/activate"); g = chamar("GET", f"/workflows/{wid}")
os.umask(0o077)
raw = json.dumps(g, sort_keys=True, ensure_ascii=False).encode()
p = f"{saida}/{'rollback_aplicado' if rb else 'implantado'}__{chave}__{g.get('versionId')}.json"
open(p, "wb").write(raw)
cron = [n["parameters"].get("rule") for n in g["nodes"] if n["type"].endswith("scheduleTrigger")]
print(json.dumps({"chave": chave, "id": wid, "versionId_antes": antes.get("versionId"), "versionId_depois": g.get("versionId"),
                  "ativo": g.get("active"), "errorWorkflow": (g.get("settings") or {}).get("errorWorkflow"),
                  "timezone": (g.get("settings") or {}).get("timezone"), "cron": cron, "sha256": hashlib.sha256(raw).hexdigest()}, ensure_ascii=False))
