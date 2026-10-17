"""Item 9 da rodada autorizada — leituras SOMENTE de metadados (L6, L7, L8, L13 atualizadas).

- L6 GTM API: GET das versões 35 e 36 e de `versions:live` (nunca create_version/publish). Por tag/trigger/
  variável grava só nome, tipo, pausa, consentimento, nomes de trigger e sha256 do HTML/parâmetros; compara
  com `measurement/gtm/*` da branch fix/measurement-control-plane-20261016 @ db65a78a (via `git show`).
- L7/L8 n8n API: GET /workflows e /executions (includeData=false). Do workflow saem só id, nome, ativo,
  updatedAt, errorWorkflow, timezone, regras de schedule, contagem de tipos de nó; credenciais, parâmetros
  e URLs nunca são gravados nem impressos.
- L13: `ls -l` + `sha256sum` dos arquivos de volumes/functions/volc-ingest no host (SSH; sem abrir .env).

Credenciais: OAuth em ~/.config/volc/google-oauth.json e N8N_BASE_URL/N8N_API_KEY do .env local do checkout
oficial — lidos em memória, nunca impressos. Uso: python3 ler_metadados_item9.py <saida.json>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SAIDA = Path(sys.argv[1])
MED = Path("/Users/mac/Desktop/VOLC-OS-CAMPAIGN/worktrees/measurement-control-plane-20261016")
REF = "db65a78ae081557773d5c9fdb157cfa6a2bb189a"
ENV_OFICIAL = Path("/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/.env")
SSH = ["ssh", "-o", "BatchMode=yes", "-i", str(Path.home() / ".ssh/volc_hetzner_claude_ed25519"), "root@178.156.196.149"]
out: dict = {}


def sha(s: str | bytes) -> str:
    return hashlib.sha256(s if isinstance(s, bytes) else s.replace("\r\n", "\n").strip().encode()).hexdigest()


def http(url, headers=None, data=None, method="GET"):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read() or b"{}")


def git_show(caminho: str, ref: str = REF) -> str:
    return subprocess.run(["git", "-C", str(MED), "show", f"{ref}:{caminho}"], capture_output=True, text=True, check=True).stdout


# ------------------------------------------------------------------ L6 GTM
def gtm():
    cred = json.loads((Path.home() / ".config/volc/google-oauth.json").read_text())
    tok = http("https://oauth2.googleapis.com/token", {"Content-Type": "application/x-www-form-urlencoded"},
               urllib.parse.urlencode({k: cred[k] for k in ("client_id", "client_secret", "refresh_token")} | {"grant_type": "refresh_token"}).encode(),
               "POST")["access_token"]
    man = json.loads(git_show("measurement/gtm/manifest.json"))
    parent = f"accounts/{man['account_id']}/containers/{man['container_id']}"
    H = {"Authorization": "Bearer " + tok}
    base = "https://tagmanager.googleapis.com/tagmanager/v2/" + parent
    vers = {"35": http(base + "/versions/35", H), "36": http(base + "/versions/36", H), "live": http(base + "/versions:live", H)}
    repo = {t["name"]: sha(git_show(t["source"])) for t in man["tags"]}
    repo_v30 = {}
    for nome, src in (("WEBS Wrapper v2", "measurement/gtm/webs-wrapper-v2.html"), ("VOLC Sensor v3", "measurement/gtm/volc-sensor-v3.html")):
        repo_v30[nome] = sha(git_show(src, "128b93ae"))

    def resumo(v):
        trig = {str(t.get("triggerId")): t for t in v.get("trigger", [])}
        def p_sha(o):
            return sha(json.dumps(o.get("parameter", []), sort_keys=True) + json.dumps(o.get("filter", []) + o.get("customEventFilter", []) + o.get("autoEventFilter", []), sort_keys=True))
        tags = {}
        for t in v.get("tag", []):
            html = next((str(p.get("value") or "") for p in t.get("parameter", []) if p.get("key") == "html"), None)
            tags[t["name"]] = {"type": t.get("type"), "paused": bool(t.get("paused", False)),
                               "consent": sorted(str(i.get("value")) for i in t.get("consentSettings", {}).get("consentType", {}).get("list", []) if isinstance(i, dict)),
                               "consent_status": t.get("consentSettings", {}).get("consentStatus"),
                               "triggers": sorted(str(trig.get(i, {}).get("name", i)) for i in t.get("firingTriggerId", [])),
                               "blocking": sorted(str(trig.get(i, {}).get("name", i)) for i in t.get("blockingTriggerId", [])),
                               "sha256": sha(html) if html is not None else p_sha(t)}
        return {"containerVersionId": v.get("containerVersionId"), "name": v.get("name"), "fingerprint": v.get("fingerprint"),
                "n_tags": len(v.get("tag", [])), "n_triggers": len(v.get("trigger", [])), "n_variables": len(v.get("variable", [])),
                "tags": tags, "triggers": {t["name"]: {"type": t.get("type"), "sha256": p_sha(t)} for t in v.get("trigger", [])},
                "variables": {x["name"]: {"type": x.get("type"), "sha256": p_sha(x)} for x in v.get("variable", [])}}

    R = {k: resumo(v) for k, v in vers.items()}
    a, b = R["35"], R["36"]
    diff = {}
    for sec in ("tags", "triggers", "variables"):
        diff[sec] = {"so_v35": sorted(set(a[sec]) - set(b[sec])), "so_v36": sorted(set(b[sec]) - set(a[sec])),
                     "alterados": sorted(n for n in set(a[sec]) & set(b[sec]) if a[sec][n] != b[sec][n])}
    live = R["live"]
    comp = {nome: {"repo_db65a78a": h, "live": live["tags"].get(nome, {}).get("sha256"), "igual": live["tags"].get(nome, {}).get("sha256") == h}
            for nome, h in repo.items()}
    comp_v35 = {nome: {"repo_128b93ae": h, "v35": a["tags"].get(nome, {}).get("sha256"), "igual": a["tags"].get(nome, {}).get("sha256") == h}
                for nome, h in repo_v30.items()}
    return {"versoes": R, "diff_v35_v36": diff, "live_e_v36": live["containerVersionId"] == "36",
            "live_vs_repo_db65a78a": comp, "v35_vs_repo_128b93ae": comp_v35,
            "manifest_live_esperada": [man["live_version_id"], man["live_version_name"]]}


# ------------------------------------------------------------------ L7/L8 n8n
def n8n():
    env = {}
    for l in ENV_OFICIAL.read_text().splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    base, key = env["N8N_BASE_URL"].rstrip("/"), env["N8N_API_KEY"]
    if not base.endswith("/api/v1"):
        base += "/api/v1"
    H = {"X-N8N-API-KEY": key, "accept": "application/json"}
    wfs, cursor = [], None
    while True:
        q = {"limit": 100} | ({"cursor": cursor} if cursor else {})
        r = http(base + "/workflows?" + urllib.parse.urlencode(q), H)
        wfs += r.get("data", [])
        cursor = r.get("nextCursor")
        if not cursor:
            break
    nomes = {w["id"]: w.get("name") for w in wfs}
    saida = []
    for w in wfs:
        nodes = w.get("nodes", [])
        sched = []
        for n in nodes:
            if n.get("type") in ("n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.cron"):
                sched.append({"type": n["type"].split(".")[-1], "disabled": bool(n.get("disabled", False)),
                              "rule": n.get("parameters", {}).get("rule") or n.get("parameters", {}).get("triggerTimes")})
        st = w.get("settings") or {}
        ew = st.get("errorWorkflow")
        saida.append({"id": w["id"], "name": w.get("name"), "active": w.get("active"), "isArchived": w.get("isArchived"),
                      "updatedAt": w.get("updatedAt"), "errorWorkflow": ew, "errorWorkflow_nome": nomes.get(ew),
                      "errorWorkflow_existe": (ew in nomes) if ew else None, "timezone": st.get("timezone"),
                      "schedules": sched, "n_nodes": len(nodes),
                      "webhooks": sum(1 for n in nodes if n.get("type") == "n8n-nodes-base.webhook"),
                      "tipos_de_no": dict(Counter(n.get("type", "?").split(".")[-1] for n in nodes).most_common(6))})
    ativos = [w for w in saida if w["active"]]
    alvo = {"Ps9yLfQkHeaAbyZZ", "7yxs1aOlzWkkkSf9", "TFlmThr4930oPneE", "cpb6tNxt211UkAn2", "jDX397ViVcRQft4A",
            "U0jEfGt30HqbUq1o", "RpxB9ppefxZWujEV", "hN15qFAVOqH0135q", "tKUItcd0AoD9mozV", "svJWqv5r1NSxB8MO", "Q6IunKtTI0gY0KgX"}
    exe = {}
    for w in saida:
        if not (w["active"] or w["id"] in alvo):
            continue
        r = http(base + "/executions?" + urllib.parse.urlencode({"workflowId": w["id"], "limit": 20, "includeData": "false"}), H)
        exe[w["id"]] = [{"status": e.get("status"), "mode": e.get("mode"), "startedAt": e.get("startedAt"),
                         "stoppedAt": e.get("stoppedAt"), "finished": e.get("finished"), "retryOf": bool(e.get("retryOf"))}
                        for e in r.get("data", [])]
    return {"n_workflows": len(saida), "n_ativos": len(ativos), "workflows": saida, "execucoes_ultimas_20": exe,
            "ids_documentados_ausentes": sorted(alvo - set(nomes))}


# ------------------------------------------------------------------ L13 Edge Function
def edge():
    cmd = ("cd /root/supabase/docker/volumes/functions/volc-ingest && ls -l --time-style=+%Y-%m-%dT%H:%M:%S%z . && sha256sum * ; "
           "docker inspect -f '{{.State.Status}} {{.State.StartedAt}}' supabase-edge-functions")
    r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=60)
    linhas = r.stdout.strip().splitlines()
    hashes = {l.split()[1]: l.split()[0] for l in linhas if len(l.split()) == 2 and len(l.split()[0]) == 64}
    repo = {ref: hashlib.sha256(git_show("supabase/functions/volc-ingest/index.ts", ref).encode()).hexdigest()
            for ref in (REF, "128b93ae")}
    repo["db65a78a"] = repo.pop(REF)
    return {"ls": [l for l in linhas if not (len(l.split()) == 2 and len(l.split()[0]) == 64)], "sha256_host": hashes,
            "sha256_repo_index_ts": repo, "host_index_ts_igual_db65a78a": hashes.get("index.ts") == repo["db65a78a"],
            "host_index_ts_igual_128b93ae": hashes.get("index.ts") == repo["128b93ae"], "stderr_linhas": len(r.stderr.splitlines())}


for nome, f in (("gtm", gtm), ("n8n", n8n), ("edge_function", edge)):
    try:
        out[nome] = f()
    except Exception as e:  # nunca imprime corpo de resposta (pode conter dado sensível)
        out[nome] = {"erro": type(e).__name__, "status": getattr(e, "code", None)}
SAIDA.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: (v.get("erro") or "ok") for k, v in out.items()}))
