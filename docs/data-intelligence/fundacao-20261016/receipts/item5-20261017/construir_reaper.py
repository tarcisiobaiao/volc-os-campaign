"""Monta o JSON do reaper em shadow (item 5). Uso: construir_reaper.py <saida.json> <id_error_workflow>"""
import json, os, sys, uuid
from pathlib import Path
AQUI = Path(__file__).resolve().parent
SAIDA, ERRWF = Path(sys.argv[1]), sys.argv[2]
SUPA = {"supabaseApi": {"id": "3lSRuywq3fwQ3z3I", "name": "VOLC Oficial"}}
BASE = "https://database.agenciavolc.com.br/rest/v1"
nid = lambda n: str(uuid.uuid5(uuid.NAMESPACE_URL, f"volc-reaper-shadow-v1:{n}"))
def get(nome, pos, url):
    return {"id": nid(nome), "name": nome, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"method": "GET", "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
                           "options": {"timeout": 30000}},
            "credentials": SUPA, "executeOnce": True, "alwaysOutputData": True, "onError": "continueRegularOutput"}
nos = [
    {"id": nid("Schedule"), "name": "Schedule", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0],
     "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "41 * * * *"}]}}},
    get("Runs Google em running", [240, 0], BASE + "/google_ads_collection_run?status=eq.running&select=run_id,collector,started_at,"
        "google_ads_raw_batch(created_at)&google_ads_raw_batch.order=created_at.desc&google_ads_raw_batch.limit=1"),
    get("Runs JoinAds em running", [480, 0], BASE + "/joinads_collection_run?status=eq.running&select=run_key,collector,started_at,updated_at,"
        "joinads_raw_batch(created_at)&joinads_raw_batch.order=created_at.desc&joinads_raw_batch.limit=1"),
    {"id": nid("Classificar órfãos"), "name": "Classificar órfãos", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [720, 0],
     "parameters": {"jsCode": (AQUI / "codigo" / "reaper_classificar.js").read_text()}},
]
con = {"Schedule": {"main": [[{"node": "Runs Google em running", "type": "main", "index": 0}]]},
       "Runs Google em running": {"main": [[{"node": "Runs JoinAds em running", "type": "main", "index": 0}]]},
       "Runs JoinAds em running": {"main": [[{"node": "Classificar órfãos", "type": "main", "index": 0}]]}}
wf = {"name": "VOLC | Coletores canônicos | Reaper de runs órfãos (shadow)", "nodes": nos, "connections": con,
      "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                   "timezone": "America/Sao_Paulo", "errorWorkflow": ERRWF}}
os.umask(0o077); SAIDA.write_text(json.dumps(wf, ensure_ascii=False, indent=1)); print(len(nos), "nós")
