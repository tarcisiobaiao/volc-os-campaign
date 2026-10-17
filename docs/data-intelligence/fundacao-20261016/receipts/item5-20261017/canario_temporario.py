"""Canário funcional por CÓPIA TEMPORÁRIA de um coletor canônico (autorização executiva do dono, 17/10 19:46 BRT).

Uso: canario_temporario.py <chave> <candidato.json> <dir_saida>
Nunca toca o workflow canônico. Passos, abortando no primeiro gate que falhar (sem improvisar):
 1. pré-condições: canônico ativo na versão do candidato (mesmos nós), nenhuma execução ativa dele, longe do cron
    canônico (±20 min) e do :07 do D0;
 2. monta a cópia: SÓ o nó de agenda vira um webhook POST de caminho aleatório (respondendo ao receber); o resto do
    grafo, Code nodes, consultas, credenciais por referência e settings ficam iguais; nome marca CANÁRIO TEMPORÁRIO;
 3. cria a cópia INATIVA, relê pela API e compara semanticamente com o candidato (único delta: o gatilho);
 4. ativa, chama o webhook UMA vez, desativa na hora, espera a execução terminar e arquiva a cópia;
 5. grava o export da cópia (0600, fora do Git) e imprime um recibo sem segredo (ids de credencial mascarados).
Limite conhecido e declarado: o corpo de ingestão marca trigger_kind 'schedule' para qualquer modo que não seja
'manual' (expressão do canônico, não alterada); a execução do canário se distingue pelo workflow_id da cópia.
"""
import copy, datetime as dt, hashlib, json, os, sys, time, urllib.request, uuid
sys.path.insert(0, os.path.dirname(__file__))
from n8n_cliente import CANONICOS, _cfg, chamar

chave, cand_path, saida = sys.argv[1], sys.argv[2], sys.argv[3]
wid = CANONICOS[chave]
cand = json.load(open(cand_path))
os.umask(0o077)
agora = lambda: dt.datetime.now(dt.timezone.utc)
recibo = {"chave": chave, "canonico": wid[:4] + "…", "inicio_utc": agora().isoformat(timespec="seconds")}


def falha(motivo):
    recibo["abortado"] = motivo
    print(json.dumps(recibo, ensure_ascii=False, indent=1))
    sys.exit(2)


def semantica(nodes, sem=()):
    out = {}
    for n in nodes:
        if n["name"] in sem:
            continue
        out[n["name"]] = {"type": n["type"], "typeVersion": n.get("typeVersion"), "parameters": n.get("parameters"),
                          "credentials": n.get("credentials"), "disabled": n.get("disabled", False),
                          "onError": n.get("onError"), "alwaysOutputData": n.get("alwaysOutputData")}
    return out


# 1. pré-condições
can = chamar("GET", f"/workflows/{wid}")
if not can.get("active"):
    falha("canonico_inativo")
if semantica(can["nodes"]) != semantica(cand["nodes"]):
    falha("canonico_diferente_do_candidato")
ativas = [e for e in chamar("GET", "/executions", consulta={"workflowId": wid, "status": "running", "limit": 5}).get("data", [])]
if ativas:
    falha("execucao_ativa_do_canonico")
(agenda,) = [n for n in cand["nodes"] if n["type"].endswith("scheduleTrigger")]
cron = agenda["parameters"]["rule"]["interval"][0]["expression"]
brt = agora().astimezone(dt.timezone(dt.timedelta(hours=-3)))
mins, horas = cron.split()[0], cron.split()[1]
proximos = []
for h in (range(24) if horas == "*" else [int(x) for x in horas.split(",")] if "," in horas or horas.isdigit() else range(24)):
    for d in (0, 1):
        t = brt.replace(hour=h, minute=int(mins), second=0, microsecond=0) + dt.timedelta(days=d)
        proximos.append(abs((t - brt).total_seconds()) / 60)
if min(proximos) < 20:
    falha("perto_do_cron_canonico")
if 2 <= brt.minute <= 12:
    falha("perto_do_cron_do_d0")
recibo["cron_canonico"] = cron
recibo["minutos_ate_cron_mais_proximo"] = round(min(proximos))

# 2. cópia: só o gatilho muda
w = copy.deepcopy(cand)
caminho = "item5-canario-" + uuid.uuid4().hex
hook = {"id": str(uuid.uuid4()), "name": "Webhook canário", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
        "position": agenda["position"], "webhookId": str(uuid.uuid4()),
        "parameters": {"httpMethod": "POST", "path": caminho, "responseMode": "onReceived", "options": {}}}
w["nodes"] = [hook if n["name"] == agenda["name"] else n for n in w["nodes"]]
w["connections"] = {("Webhook canário" if k == agenda["name"] else k): v for k, v in w["connections"].items()}
w["name"] = f"CANÁRIO TEMPORÁRIO item5 {chave} — não é o canônico ({agora():%Y%m%dT%H%MZ})"

# 3. cria inativa, relê, compara
criado = chamar("POST", "/workflows", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"], "settings": w["settings"]})
cid = criado["id"]
recibo["copia"] = cid
lido = chamar("GET", f"/workflows/{cid}")
if lido.get("active"):
    falha("copia_criada_ativa")
ok = (semantica(lido["nodes"], (agenda["name"], "Webhook canário")) == semantica(cand["nodes"], (agenda["name"],))
      and json.dumps({k: v for k, v in lido["connections"].items() if k != "Webhook canário"}, sort_keys=True)
      == json.dumps({k: v for k, v in cand["connections"].items() if k != agenda["name"]}, sort_keys=True)
      and lido["connections"].get("Webhook canário") == cand["connections"].get(agenda["name"])
      and {k: (lido.get("settings") or {}).get(k) for k in cand["settings"]} == cand["settings"])
raw = json.dumps(lido, sort_keys=True, ensure_ascii=False).encode()
open(f"{saida}/canario__{chave}__{cid}.json", "wb").write(raw)
recibo["copia_sha256"] = hashlib.sha256(raw).hexdigest()
recibo["delta_semantico_so_gatilho"] = ok
if not ok:
    chamar("POST", f"/workflows/{cid}/archive")
    falha("copia_diverge_do_candidato_arquivada_sem_executar")

# 4. ativa, chama uma vez, desativa, espera, arquiva
base = _cfg()[0][: -len("/api/v1")]
chamar("POST", f"/workflows/{cid}/activate")
t0 = agora()
try:
    req = urllib.request.Request(f"{base}/webhook/{caminho}", data=b"{}", method="POST", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        recibo["webhook_http"] = r.status
finally:
    chamar("POST", f"/workflows/{cid}/deactivate")
    recibo["ativa_por_segundos"] = round((agora() - t0).total_seconds(), 1)
recibo["copia_ativa_depois"] = chamar("GET", f"/workflows/{cid}").get("active")
ex = None
for _ in range(60):
    es = chamar("GET", "/executions", consulta={"workflowId": cid, "limit": 5, "includeData": "false"}).get("data", [])
    if es and es[0].get("stoppedAt"):
        ex = es[0]
        break
    time.sleep(10)
recibo["execucao"] = ({"id": ex["id"], "status": ex["status"], "mode": ex.get("mode"), "inicio": ex["startedAt"],
                       "fim": ex["stoppedAt"]} if ex else "nao_terminou_em_10_min")
if ex:
    chamar("POST", f"/workflows/{cid}/archive")
    recibo["copia_arquivada"] = True
recibo["fim_utc"] = agora().isoformat(timespec="seconds")
print(json.dumps(recibo, ensure_ascii=False, indent=1))
sys.exit(0 if ex and ex["status"] == "success" else 3)
